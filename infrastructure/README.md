# Infrastructure

Terraform for the whole site: the collector (DynamoDB table, data bucket, API key secret,
Lambda, schedule), the votes function, alarms and a monthly budget, and the public site
(CloudFront in front of private buckets, plus a GitHub Actions deploy role).

All commands run from the repository root with your AWS credentials available, for
example `export AWS_PROFILE=personal`. Nothing here contains secrets or account IDs:
those live in the gitignored `terraform.tfvars` and `backend.hcl`, in Secrets Manager, and
in GitHub environment secrets.

## What deploys where

| Change | How it reaches AWS |
| --- | --- |
| `frontend/` | The Deploy workflow, on merge to `main` (or `make deploy-frontend`) |
| `infrastructure/`, `collector/`, `config/players.json` | `make deploy`, run locally: it plans, applies after you confirm, and runs the collector |
| `config/photos/<player-id>.webp` | `make upload-photos`, run locally (photos never enter git) |
| The HenrikDev key | `make set-api-key`, run locally |

Terraform stays a local, reviewed step because it needs the gitignored players file and
settings, and because a CI role able to apply it would need near-administrator access.

## Everyday deploys

After changing the infrastructure, the collector, or `config/players.json`:

```bash
make deploy
```

It initialises Terraform (installing any new providers), shows the plan, applies it
once you answer `y`, and then runs the collector so the summary is up to date. With no
changes it skips straight to the collector run. `YES=1` skips the question, and the
individual steps (`make infra-init`, `infra-plan`, `infra-apply`, `invoke`) still work
on their own.

## First deployment

1. **State bucket (once).** Creates a private, versioned bucket for Terraform state
   and writes `infrastructure/backend.hcl`:

   ```bash
   make infra-bootstrap
   ```

2. **Settings.** Copy `terraform.tfvars.example` to `terraform.tfvars` and set
   `alert_email`. Make sure `config/players.json` exists; the plan refuses to deploy
   without it.

3. **Plan and apply.** Review the plan before applying it:

   ```bash
   make infra-init
   make infra-plan
   make infra-apply
   ```

4. **Confirm the alert email.** AWS sends a subscription confirmation to
   `alert_email`; alarms aren't delivered until it is confirmed.

5. **API key and first run.** With `HENRIKDEV_API_KEY` exported:

   ```bash
   make set-api-key
   make invoke
   ```

6. **GitHub deploy environment (once).** The deploy role only trusts the repository's
   `production` environment, restricted to `main`. Create it and store the deploy
   settings as environment secrets (they contain the account ID, so they stay out of
   the public logs):

   ```bash
   repo=rafgaf-dev/valorant-stats
   gh api -X PUT "repos/$repo/environments/production" \
     -F "deployment_branch_policy[protected_branches]=false" \
     -F "deployment_branch_policy[custom_branch_policies]=true"
   gh api -X POST "repos/$repo/environments/production/deployment-branch-policies" \
     -f name=main -f type=branch
   output() { terraform -chdir=infrastructure output -raw "$1"; }
   output deploy_role_arn | gh secret set AWS_DEPLOY_ROLE_ARN --env production --repo "$repo"
   output site_bucket | gh secret set SITE_BUCKET --env production --repo "$repo"
   output distribution_id | gh secret set DISTRIBUTION_ID --env production --repo "$repo"
   gh variable set SITE_URL --env production --repo "$repo" \
     --body "$(terraform -chdir=infrastructure output -raw site_url)"
   ```

7. **Publish the site.** Run the Deploy workflow from the Actions tab (or
   `gh workflow run deploy.yml`), and upload any photos:

   ```bash
   make upload-photos
   ```

   The URL is `terraform -chdir=infrastructure output -raw site_url`.

8. **Schedule.** Set `schedule_enabled = true` in `terraform.tfvars`, then plan and
   apply again. This also turns on the "no successful run in 12 hours" alarm.

## Removing a player

```bash
make delete-player PLAYER=<id>
```

It asks for the id again, then deletes the player's DynamoDB items, every version of
their summaries and photo, and CloudFront's cached copies. Remove them from
`config/players.json` and plan and apply as well, or the next scheduled run recreates
the data.

## The site

CloudFront serves the built frontend from the site bucket and `/data/*` (summaries and
photos) from the data bucket. Both buckets are private and readable only by this
distribution. `/api/*` goes, uncached, to the votes function's URL, which requires
IAM auth: only this distribution can call it, through Origin Access Control. Because
CloudFront can only sign a POST whose body hash it is given, the page sends an
`x-amz-content-sha256` header with each vote. Every response carries HSTS and a strict Content Security Policy that
allows only the site's own scripts, styles, fonts, images, and data. Caching follows each
object's `Cache-Control`: `index.html` is revalidated, hashed assets are immutable, and
summaries are cached for five minutes.

## Costs

Expected around $1–2 a month: Secrets Manager ($0.40), three custom metrics
(~$0.90), three alarms ($0.30), and cents for Lambda, DynamoDB, S3, and CloudFront at
friend-group traffic. The budget emails at 80% of actual and 100% of forecast spend
(default $5).

## Teardown

`terraform -chdir=infrastructure destroy` removes everything except the state bucket,
which has `prevent_destroy` set. Both content buckets are emptied automatically; the
secret is recoverable for 7 days after deletion.
