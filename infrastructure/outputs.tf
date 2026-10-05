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
