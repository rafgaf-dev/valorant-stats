variable "aws_region" {
  description = "AWS region for regional resources. CloudFront and Budgets are global."
  type        = string
  default     = "eu-west-1"
}
