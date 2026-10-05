# Peer-review votes ("Was this review fair?"): a small Lambda behind CloudFront at /api/*.
# Its function URL requires IAM auth and only CloudFront may call it, through Origin Access
# Control, so the viewer address CloudFront forwards can be trusted.

# Hashes viewer addresses into per-day voter ids; the addresses themselves are never stored.
resource "random_password" "voter_key" {
  length  = 64
  special = false
}

resource "aws_cloudwatch_log_group" "votes" {
  name              = "/aws/lambda/${local.name}-votes"
  retention_in_days = 14
}

resource "aws_lambda_function" "votes" {
  function_name    = "${local.name}-votes"
  description      = "Counts peer-review votes, one per viewer per player per day."
  role             = aws_iam_role.votes.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "votes.handler.handler"
  filename         = data.archive_file.collector.output_path # same source tree as the collector
  source_code_hash = data.archive_file.collector.output_base64sha256
  memory_size      = 128
  timeout          = 5

  environment {
    variables = {
      # Only the ids: this function has no use for the Riot IDs in the players file.
      PLAYER_IDS = jsonencode([for player in jsondecode(local.players_json) : player.id])
      TABLE_NAME = aws_dynamodb_table.collector.name
      VOTER_KEY  = random_password.voter_key.result
    }
  }

  logging_config {
    log_format = "Text" # JSON lines, like the collector
    log_group  = aws_cloudwatch_log_group.votes.name
  }

  lifecycle {
    precondition {
      condition     = local.players_file_exists
      error_message = "Create ${var.players_file} from config/players.example.json before deploying."
    }
  }
}

resource "aws_lambda_function_url" "votes" {
  function_name      = aws_lambda_function.votes.function_name
  authorization_type = "AWS_IAM"
}

# CloudFront needs both permissions to call a function URL through Origin Access Control.
resource "aws_lambda_permission" "votes_url_from_cloudfront" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.votes.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.site.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "votes_from_cloudfront" {
  statement_id             = "AllowCloudFrontInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.votes.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.site.arn
  invoked_via_function_url = true
}

resource "aws_iam_role" "votes" {
  name               = "${local.name}-votes"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "votes" {
  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.votes.arn}:*"]
  }

  # Counts and voter records live in the players' partitions (plan section 4). A vote is one
  # TransactWriteItems call, which needs PutItem and UpdateItem on the table.
  statement {
    sid       = "CountVotes"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.collector.arn]
  }
}

resource "aws_iam_role_policy" "votes" {
  name   = "votes"
  role   = aws_iam_role.votes.id
  policy = data.aws_iam_policy_document.votes.json
}
