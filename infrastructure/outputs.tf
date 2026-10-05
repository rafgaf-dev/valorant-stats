output "collector_function_name" {
  description = "For `make invoke`."
  value       = aws_lambda_function.collector.function_name
}

output "api_key_secret_arn" {
  description = "For `make set-api-key`."
  value       = aws_secretsmanager_secret.henrikdev_api_key.arn
}

output "data_bucket" {
  description = "Holds data/players/<id>/summary.json and photo.webp."
  value       = aws_s3_bucket.data.id
}

output "table_name" {
  value = aws_dynamodb_table.collector.name
}

output "site_url" {
  description = "The public site."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "site_bucket" {
  description = "Deploy target for the built frontend (a GitHub environment secret)."
  value       = aws_s3_bucket.site.id
}

output "distribution_id" {
  description = "For cache invalidations (a GitHub environment secret)."
  value       = aws_cloudfront_distribution.site.id
}

output "deploy_role_arn" {
  description = "Assumed by the deploy workflow through OIDC (a GitHub environment secret)."
  value       = aws_iam_role.deploy.arn
}
