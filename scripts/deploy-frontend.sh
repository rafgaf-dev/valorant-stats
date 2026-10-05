#!/usr/bin/env bash
# Uploads the built frontend to the site bucket and refreshes CloudFront's copy of the page.
#
#   SITE_BUCKET=... DISTRIBUTION_ID=... scripts/deploy-frontend.sh [dist-dir]
#
# Order matters: new hashed assets go up first and old ones are removed last, so a visitor
# who loads index.html mid-deploy never gets a page pointing at missing files.
set -euo pipefail

: "${SITE_BUCKET:?Set SITE_BUCKET}"
: "${DISTRIBUTION_ID:?Set DISTRIBUTION_ID}"
dist="${1:-frontend/dist}"
test -f "$dist/index.html" || { echo "No build in $dist; run make build first." >&2; exit 1; }

echo "Uploading assets"
aws s3 sync "$dist/assets" "s3://$SITE_BUCKET/assets" --only-show-errors \
	--cache-control "public, max-age=31536000, immutable"

echo "Uploading index.html and other top-level files"
aws s3 sync "$dist" "s3://$SITE_BUCKET" --only-show-errors --delete \
	--exclude "assets/*" --cache-control "no-cache"

echo "Removing assets the new build no longer uses"
aws s3 sync "$dist/assets" "s3://$SITE_BUCKET/assets" --only-show-errors --delete \
	--cache-control "public, max-age=31536000, immutable"

echo "Invalidating the cached page"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
	--paths "/" "/index.html" --query "Invalidation.Id" --output text
