.PHONY: help install dev lint format typecheck test build validate-infra check capture-fixtures collect-local clean

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

export COREPACK_ENABLE_DOWNLOAD_PROMPT := 0

help:
	@printf '%s\n' \
		'make install           Install collector and frontend dependencies' \
		'make dev               Run the frontend with sample data from frontend/dev-data' \
		'make lint              Lint and format-check all code' \
		'make format            Apply formatters (ruff, terraform fmt)' \
		'make typecheck         Type-check the frontend' \
		'make test              Run collector and frontend tests' \
		'make build             Create a production frontend build' \
		'make validate-infra    Run terraform validate without a backend' \
		'make check             Run everything CI runs' \
		'make capture-fixtures  Save pseudonymized HenrikDev responses (needs HENRIKDEV_API_KEY; PLAYER=<id>, OFFLINE=1, REFRESH=1)' \
		'make collect-local     Run the collector against the real API into collector/.local (needs HENRIKDEV_API_KEY; PLAYER=<id>)'

install: $(VENV_STAMP) $(NODE_STAMP)

$(VENV_STAMP): collector/requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install -r collector/requirements-dev.txt
	touch $@

$(NODE_STAMP): frontend/package-lock.json
	$(NPM) --prefix frontend ci

dev: $(NODE_STAMP)
	$(NPM) --prefix frontend run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

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

validate-infra:
	$(TERRAFORM) -chdir=infrastructure init -backend=false -input=false
	$(TERRAFORM) -chdir=infrastructure validate

check: lint typecheck test build validate-infra

capture-fixtures:
	$(PYTHON) collector/scripts/capture_fixtures.py $(if $(PLAYER),--player $(PLAYER)) $(if $(OFFLINE),--offline) $(if $(REFRESH),--refresh)

collect-local: $(VENV_STAMP)
	PYTHONPATH=collector/src $(VENV_BIN)/python -m collector.local $(if $(PLAYER),--player $(PLAYER))

clean:
	rm -rf frontend/dist frontend/node_modules $(VENV) collector/.pytest_cache collector/.ruff_cache collector/.coverage collector/.fixture-cache collector/.local
