locals {
  # Tracked players come from the gitignored players file; validate and CI fall back to the
  # committed example. The precondition below stops a plan that would deploy the example.
  players_file_exists = fileexists(var.players_file)
  players_json        = local.players_file_exists ? file(var.players_file) : file("${path.module}/../config/players.example.json")
}

data "archive_file" "collector" {
  type        = "zip"
  source_dir  = "${path.module}/../collector/src"
  output_path = "${path.module}/.build/collector.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

resource "aws_cloudwatch_log_group" "collector" {
  name              = "/aws/lambda/${local.name}-collector"
  retention_in_days = 14
}

# No reserved concurrency: new accounts often can't reserve any (the unreserved pool must
# stay at 10 or more), and runs can't overlap anyway (every 6 hours, 5-minute timeout).
resource "aws_lambda_function" "collector" {
  function_name    = "${local.name}-collector"
  description      = "Imports Valorant matches from the HenrikDev API and publishes summaries."
  role             = aws_iam_role.collector.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "collector.handler.handler"
  filename         = data.archive_file.collector.output_path
  source_code_hash = data.archive_file.collector.output_base64sha256
  memory_size      = 256
  timeout          = 300

  environment {
    variables = {
      PLAYERS           = jsonencode(jsondecode(local.players_json))
      TABLE_NAME        = aws_dynamodb_table.collector.name
      DATA_BUCKET       = aws_s3_bucket.data.id
      API_KEY_SECRET_ID = aws_secretsmanager_secret.henrikdev_api_key.arn
    }
  }

  logging_config {
    log_format = "Text" # the collector already writes JSON lines
    log_group  = aws_cloudwatch_log_group.collector.name
  }

  lifecycle {
    precondition {
      condition     = local.players_file_exists
      error_message = "Create ${var.players_file} from config/players.example.json before deploying."
    }
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "collector" {
  name               = "${local.name}-collector"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "collector" {
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.collector.arn}:*"]
  }

  statement {
    sid       = "ReadApiKey"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.henrikdev_api_key.arn]
  }

  statement {
    sid       = "StoreMatches"
    actions   = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.collector.arn]
  }

  statement {
    sid       = "PublishSummaries"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/data/players/*/summary.json"]
  }
}

resource "aws_iam_role_policy" "collector" {
  name   = "collector"
  role   = aws_iam_role.collector.id
  policy = data.aws_iam_policy_document.collector.json
}
