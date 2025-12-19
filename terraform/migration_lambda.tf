# Lambda function to run database migration
# This creates a one-time Lambda function to update foreign key constraints

# Lambda execution role
resource "aws_iam_role" "migration_lambda_role" {
  name = "${var.project_name}-migration-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-migration-lambda-role"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "migration_lambda_basic" {
  role       = aws_iam_role.migration_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach VPC execution policy (for Lambda in VPC)
resource "aws_iam_role_policy_attachment" "migration_lambda_vpc" {
  role       = aws_iam_role.migration_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Security group for Lambda
resource "aws_security_group" "migration_lambda" {
  name        = "${var.project_name}-migration-lambda-sg"
  description = "Security group for migration Lambda function"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]  # Allow access to RDS in VPC
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # For AWS API calls
  }

  tags = {
    Name = "${var.project_name}-migration-lambda-sg"
  }
}

# Update RDS security group to allow Lambda access
resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.migration_lambda.id
  security_group_id        = aws_security_group.rds.id
  description              = "Allow Lambda migration function to access RDS"
}

# Lambda function
resource "aws_lambda_function" "migration" {
  filename      = "migration_lambda.zip"
  function_name = "${var.project_name}-db-migration"
  role          = aws_iam_role.migration_lambda_role.arn
  handler       = "lambda_migration_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 256

  source_code_hash = filebase64sha256("migration_lambda.zip")

  vpc_config {
    subnet_ids         = [aws_subnet.private_1.id, aws_subnet.private_2.id]
    security_group_ids = [aws_security_group.migration_lambda.id]
  }

  environment {
    variables = {
      DATABASE_URL = "postgresql://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/finance_a2a"
    }
  }

  # psycopg2-binary is included in the deployment package

  tags = {
    Name = "${var.project_name}-migration-lambda"
  }
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "migration_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.migration.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-migration-lambda-logs"
  }
}

# Output the Lambda function name
output "migration_lambda_function_name" {
  description = "Name of the migration Lambda function"
  value       = aws_lambda_function.migration.function_name
}

output "migration_lambda_invoke_command" {
  description = "AWS CLI command to invoke the migration Lambda"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.migration.function_name} --region ${var.aws_region} migration_response.json && cat migration_response.json"
}
