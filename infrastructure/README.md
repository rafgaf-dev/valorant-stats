# Infrastructure

Terraform for the collector: a DynamoDB table, the data bucket, the HenrikDev key
secret, the collector Lambda, its schedule, alarms, and a monthly budget. The
CloudFront site is added in milestone 6.

All commands run from the repository root with your AWS credentials available, for
example `export AWS_PROFILE=personal`. Nothing here contains secrets or account IDs:
those live in the gitignored `terraform.tfvars`, `backend.hcl`, and Secrets Manager.

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

5. **API key.** With `HENRIKDEV_API_KEY` exported:

   ```bash
   make set-api-key
   ```

6. **First run.** Invoke the collector once and check the result:

   ```bash
   make invoke
   ```

7. **Schedule.** Set `schedule_enabled = true` in `terraform.tfvars`, then plan and
   apply again. This also turns on the "no successful run in 12 hours" alarm.

## Costs

Expected around $1–2 a month: Secrets Manager ($0.40), three custom metrics
(~$0.90), two alarms ($0.20), and cents for Lambda, DynamoDB, and S3. The budget
emails at 80% of actual and 100% of forecast spend (default $5).

## Teardown

`terraform -chdir=infrastructure destroy` removes everything except the state
bucket, which has `prevent_destroy` set. The data bucket is emptied automatically;
the secret is recoverable for 7 days after deletion.
