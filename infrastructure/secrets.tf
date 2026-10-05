# The HenrikDev API key. Terraform creates only the empty secret; the value is set with
# `make set-api-key`, so it never enters Terraform state or git.
resource "aws_secretsmanager_secret" "henrikdev_api_key" {
  name                    = "${local.name}/henrikdev-api-key"
  description             = "HenrikDev API key used by the collector Lambda."
  recovery_window_in_days = 7
}
