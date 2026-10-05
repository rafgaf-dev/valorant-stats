# Alarms email through SNS (the subscription must be confirmed from the email it sends).
# The topic isn't encrypted: CloudWatch can't publish to a topic using the AWS-managed key,
# and alarm notifications contain nothing sensitive.
resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Fires when the handler raises, which it does only when every player failed.
resource "aws_cloudwatch_metric_alarm" "collector_errors" {
  alarm_name          = "${local.name}-collector-errors"
  alarm_description   = "The collector failed for every player."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.collector.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Fires when no run has succeeded for 12 hours (two missed six-hourly runs), including when
# runs stop altogether. Only active while the schedule is enabled.
resource "aws_cloudwatch_metric_alarm" "collector_stale" {
  alarm_name          = "${local.name}-collector-stale"
  alarm_description   = "No successful collector run in the last 12 hours."
  namespace           = "ValorantStats"
  metric_name         = "SuccessfulRuns"
  dimensions          = { Service = "collector" }
  statistic           = "Sum"
  period              = 43200
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  actions_enabled     = var.schedule_enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Fires when the votes function fails (rejected votes are normal responses, not errors).
resource "aws_cloudwatch_metric_alarm" "votes_errors" {
  alarm_name          = "${local.name}-votes-errors"
  alarm_description   = "The votes function raised an error."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.votes.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
