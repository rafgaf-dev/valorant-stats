.PHONY: help install dev lint format typecheck test build validate-infra check capture-fixtures collect-local infra-bootstrap infra-init infra-plan infra-apply set-api-key invoke deploy-frontend upload-photos delete-player clean

PYTHON ?= python3
NPM ?= corepack npm
TERRAFORM ?= terraform
FRONTEND_HOST ?= 127.0.0.1
FRONTEND_PORT ?= 5173

# On WSL with the repository on a Windows drive (/mnt/c/...), a venv on the Linux filesystem
# is much faster, e.g. `export VENV=$HOME/.cache/valorant-stats-venv`.
VENV ?= collector/.venv
VENV_BIN := $(abspath $(VENV))/bin
VENV_STAMP := $(VENV)/.installed
NODE_STAMP := frontend/node_modules/.package-lock.json
TF_OUTPUT = $(TERRAFORM) -chdir=infrastructure output -raw

export COREPACK_ENABLE_DOWNLOAD_PROMPT := 0

help:
	@printf '%s\n' \
		'make install           Install collector and frontend dependencies' \
		'make dev               Run the frontend with sample data (LOCAL=1: real data from make collect-local)' \
		'make lint              Lint and format-check all code' \
		'make format            Apply formatters (ruff, terraform fmt)' \
		'make typecheck         Type-check the frontend' \
		'make test              Run collector and frontend tests' \
		'make build             Create a production frontend build' \
		'make validate-infra    Run terraform validate without a backend' \
		'make check             Run everything CI runs' \
		'make capture-fixtures  Save pseudonymized HenrikDev responses (needs HENRIKDEV_API_KEY; PLAYER=<id>, OFFLINE=1, REFRESH=1)' \
		'make collect-local     Run the collector against the real API into collector/.local (needs HENRIKDEV_API_KEY; PLAYER=<id>)' \
		'' \
		'AWS (uses your AWS_PROFILE; see infrastructure/README.md):' \
		'make infra-bootstrap   Create the Terraform state bucket once and write infrastructure/backend.hcl' \
		'make infra-init        Initialise Terraform against the state bucket' \
		'make infra-plan        Show what would change in AWS and save the plan' \
		'make infra-apply       Apply the saved plan' \
		'make set-api-key       Store HENRIKDEV_API_KEY in Secrets Manager' \
		'make invoke            Run the collector Lambda once and show its result' \
		'make deploy-frontend   Build and publish the frontend (CI does this on merge to main)' \
		'make upload-photos     Publish config/photos/<player-id>.webp next to each summary' \
		'make delete-player     Delete all stored data for PLAYER=<id> (asks for confirmation)'

install: $(VENV_STAMP) $(NODE_STAMP)

$(VENV_STAMP): collector/requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install -r collector/requirements-dev.txt
	touch $@

$(NODE_STAMP): frontend/package-lock.json
	$(NPM) --prefix frontend ci

dev: $(NODE_STAMP)
	$(if $(LOCAL),DEV_DATA_DIR=$(abspath collector/.local/data)) $(NPM) --prefix frontend run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

lint: install
	cd collector && $(VENV_BIN)/ruff check . && $(VENV_BIN)/ruff format --check .
	$(NPM) --prefix frontend run lint
	$(TERRAFORM) -chdir=infrastructure fmt -check -recursive

format: $(VENV_STAMP)
	cd collector && $(VENV_BIN)/ruff check --fix . && $(VENV_BIN)/ruff format .
	$(TERRAFORM) -chdir=infrastructure fmt -recursive

typecheck: $(NODE_STAMP)
	$(NPM) --prefix frontend run typecheck

test: install
	cd collector && $(VENV_BIN)/pytest --cov --cov-report=term-missing
	$(NPM) --prefix frontend test

build: $(NODE_STAMP)
	$(NPM) --prefix frontend run build

# A separate data directory, so validation never touches the real backend or needs AWS access.
validate-infra:
	TF_DATA_DIR=.terraform-validate $(TERRAFORM) -chdir=infrastructure init -backend=false -input=false
	TF_DATA_DIR=.terraform-validate $(TERRAFORM) -chdir=infrastructure validate

check: lint typecheck test build validate-infra

capture-fixtures:
	$(PYTHON) collector/scripts/capture_fixtures.py $(if $(PLAYER),--player $(PLAYER)) $(if $(OFFLINE),--offline) $(if $(REFRESH),--refresh)

collect-local: $(VENV_STAMP)
	PYTHONPATH=collector/src $(VENV_BIN)/python -m collector.local $(if $(PLAYER),--player $(PLAYER))

infra-bootstrap:
	$(TERRAFORM) -chdir=infrastructure/bootstrap init -input=false
	$(TERRAFORM) -chdir=infrastructure/bootstrap apply
	$(TERRAFORM) -chdir=infrastructure/bootstrap output -raw backend_config > infrastructure/backend.hcl

infra-init:
	$(TERRAFORM) -chdir=infrastructure init -input=false -backend-config=backend.hcl

infra-plan:
	$(TERRAFORM) -chdir=infrastructure plan -input=false -out=tfplan

infra-apply:
	$(TERRAFORM) -chdir=infrastructure apply tfplan

# The key is piped through stdin so it never appears in the process list or shell history.
set-api-key:
	@test -n "$$HENRIKDEV_API_KEY" || { echo "Set HENRIKDEV_API_KEY first." >&2; exit 1; }
	@printf '%s' "$$HENRIKDEV_API_KEY" | aws secretsmanager put-secret-value \
		--secret-id "$$($(TF_OUTPUT) api_key_secret_arn)" \
		--secret-string file:///dev/stdin --query VersionId --output text

# Prints the function's last log lines, then its response.
invoke:
	@response=$$(mktemp); \
	aws lambda invoke --cli-read-timeout 310 --log-type Tail --query LogResult --output text \
		--function-name "$$($(TF_OUTPUT) collector_function_name)" \
		"$$response" | base64 -d; \
	echo; cat "$$response"; echo; rm -f "$$response"

deploy-frontend: build
	SITE_BUCKET="$$($(TF_OUTPUT) site_bucket)" DISTRIBUTION_ID="$$($(TF_OUTPUT) distribution_id)" \
		scripts/deploy-frontend.sh frontend/dist

# Photos stay out of git; they're uploaded straight from config/photos/ to the data bucket.
upload-photos:
	@bucket="$$($(TF_OUTPUT) data_bucket)"; distribution="$$($(TF_OUTPUT) distribution_id)"; found=0; \
	for photo in config/photos/*.webp; do \
		[ -e "$$photo" ] || continue; found=1; id="$$(basename "$$photo" .webp)"; \
		echo "Uploading $$id"; \
		aws s3 cp "$$photo" "s3://$$bucket/data/players/$$id/photo.webp" --only-show-errors \
			--content-type image/webp --cache-control "public, max-age=3600"; \
		aws cloudfront create-invalidation --distribution-id "$$distribution" \
			--paths "/data/players/$$id/photo.webp" --query Invalidation.Id --output text; \
	done; \
	[ "$$found" = 1 ] || echo "No photos in config/photos/ (expected <player-id>.webp)."

# Asks for the player id again before deleting anything.
delete-player: $(VENV_STAMP)
	@test -n "$(PLAYER)" || { echo "Usage: make delete-player PLAYER=<id>" >&2; exit 1; }
	PYTHONPATH=collector/src $(VENV_BIN)/python collector/scripts/delete_player.py --player "$(PLAYER)" \
		--table "$$($(TF_OUTPUT) table_name)" --bucket "$$($(TF_OUTPUT) data_bucket)" \
		--distribution "$$($(TF_OUTPUT) distribution_id)"

clean:
	rm -rf frontend/dist frontend/node_modules $(VENV) collector/.pytest_cache collector/.ruff_cache collector/.coverage collector/.fixture-cache collector/.local
