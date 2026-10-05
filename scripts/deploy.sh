#!/usr/bin/env bash
# Deploys infrastructure and collector changes, then runs the collector once:
#
#   make deploy          shows the plan and asks before applying it
#   make deploy YES=1    applies without asking
#
# Covers infrastructure/, collector/, and config/players.json. The frontend deploys itself
# from GitHub Actions on every merge to main.
set -euo pipefail
cd "$(dirname "$0")/.."

tf() { "${TERRAFORM:-terraform}" -chdir=infrastructure "$@"; }

test -f infrastructure/backend.hcl || {
	echo "No infrastructure/backend.hcl; run make infra-bootstrap first." >&2
	exit 1
}

# The plan holds the Lambda settings, Riot IDs included; don't leave it lying around.
trap 'rm -f infrastructure/tfplan' EXIT

echo "==> Initialising Terraform"
# Quiet unless it fails; also installs providers added since the last run.
if ! output=$(tf init -input=false -backend-config=backend.hcl 2>&1); then
	echo "$output" >&2
	exit 1
fi

echo "==> Planning"
status=0
tf plan -input=false -out=tfplan -detailed-exitcode || status=$?
case $status in
	0) echo "==> No infrastructure changes" ;;
	2)
		if [[ "${YES:-}" != 1 ]]; then
			read -r -p "Apply this plan? [y/N] " answer
			[[ "$answer" == [yY] ]] || { echo "Not applied."; exit 1; }
		fi
		echo "==> Applying"
		tf apply -input=false tfplan
		;;
	*) exit "$status" ;;
esac

echo "==> Running the collector"
make --no-print-directory invoke TERRAFORM="${TERRAFORM:-terraform}"
