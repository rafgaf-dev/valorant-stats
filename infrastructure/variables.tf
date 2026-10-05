variable "aws_region" {
  description = "AWS region for regional resources. CloudFront and Budgets are global."
  type        = string
  default     = "eu-west-1"
}

variable "alert_email" {
  description = "Email address for alarm and budget notifications. Set it in the gitignored terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget; alerts at 80% of actual and 100% of forecast spend."
  type        = number
  default     = 5
}

variable "players_file" {
  description = "Tracked players (gitignored). Passed to the collector as the PLAYERS variable."
  type        = string
  default     = "../config/players.json"
}

variable "collector_schedule" {
  description = "EventBridge Scheduler expression for collector runs."
  type        = string
  default     = "rate(6 hours)"
}

variable "schedule_enabled" {
  description = "Whether the schedule runs. Kept off until a manual invocation has been checked."
  type        = bool
  default     = false
}

variable "github_oidc_subject_prefix" {
  description = <<-EOT
    Prefix of the OIDC `sub` claim for this repository, in GitHub's immutable-subject format:
    repo:<owner>@<owner id>/<repo>@<repo id>. The numeric IDs (public, not secrets) mean a
    deleted and recreated repository with the same name can't assume the deploy role. Find
    it with: gh api repos/<owner>/<repo>/actions/oidc/customization/sub
  EOT
  type        = string
  default     = "repo:rafgaf-dev@329276944/valorant-stats@1370670436"

  validation {
    condition     = can(regex("^repo:[^/@]+@[0-9]+/[^/@]+@[0-9]+$", var.github_oidc_subject_prefix))
    error_message = "Use the immutable format repo:<owner>@<owner id>/<repo>@<repo id>."
  }
}
