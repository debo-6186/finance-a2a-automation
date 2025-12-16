# Finance A2A Automation - Terraform Configuration
# This configuration deploys the complete infrastructure on AWS

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "finance-a2a"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google API Key for Gemini"
  type        = string
  sensitive   = true
}

variable "perplexity_api_key" {
  description = "Perplexity API Key"
  type        = string
  sensitive   = true
}

variable "firebase_project_id" {
  description = "Firebase Project ID"
  type        = string
}

# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Public Subnets
resource "aws_subnet" "public_1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-1a"
  }
}

resource "aws_subnet" "public_2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-1b"
  }
}

# Private Subnets for RDS
resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "${var.project_name}-private-1a"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "${var.project_name}-private-1b"
  }
}

# Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-alb-sg"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 10001
    to_port         = 10001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    from_port = 10001
    to_port   = 10003
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-sg"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS database"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

# RDS Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-postgres"
  engine         = "postgres"
  engine_version = "15.15"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_encrypted     = true

  db_name  = "finance_a2a"
  username = "postgres"
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  skip_final_snapshot = true
  publicly_accessible = false

  tags = {
    Name = "${var.project_name}-postgres"
  }
}

# Secrets Manager
resource "aws_secretsmanager_secret" "api_keys" {
  name        = "${var.project_name}/api-keys"
  description = "API keys for finance a2a services"
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = aws_secretsmanager_secret.api_keys.id
  secret_string = jsonencode({
    GOOGLE_API_KEY      = var.google_api_key
    PERPLEXITY_API_KEY  = var.perplexity_api_key
    FIREBASE_PROJECT_ID = var.firebase_project_id
  })
}

resource "aws_secretsmanager_secret" "database" {
  name        = "${var.project_name}/database"
  description = "Database credentials for finance a2a"
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    username = "postgres"
    password = var.db_password
    host     = aws_db_instance.postgres.endpoint
    port     = "5432"
    database = "finance_a2a"
  })
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "host_agent" {
  name              = "/ecs/${var.project_name}-host-agent"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-host-agent-logs"
  }
}

resource "aws_cloudwatch_log_group" "stockanalyser_agent" {
  name              = "/ecs/${var.project_name}-stockanalyser-agent"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-stockanalyser-agent-logs"
  }
}

resource "aws_cloudwatch_log_group" "stockreport_agent" {
  name              = "/ecs/${var.project_name}-stockreport-agent"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-stockreport-agent-logs"
  }
}

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]

  enable_deletion_protection = false

  tags = {
    Name = "${var.project_name}-alb"
  }
}

# Target Group
resource "aws_lb_target_group" "host_agent" {
  name        = "${var.project_name}-host-tg"
  port        = 10001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.project_name}-host-tg"
  }
}

# Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.host_agent.arn
  }
}

# Service Discovery
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "stockanalyser" {
  name = "stockanalyser-agent"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 60
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "stockreport" {
  name = "stockreport-agent"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 60
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# IAM Roles
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.api_keys.arn,
          aws_secretsmanager_secret.database.arn
        ]
      }
    ]
  })
}

# ECS Task Definition - Stock Report Analyser
resource "aws_ecs_task_definition" "stockreport_agent" {
  family                   = "${var.project_name}-stockreport-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "stockreport-agent"
      image     = "156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/stockreport-agent:latest"
      essential = true
      portMappings = [
        {
          containerPort = 10003
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "FALSE"
        }
      ]
      secrets = [
        {
          name      = "GOOGLE_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.stockreport_agent.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:10003/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-stockreport-agent"
  }
}

# ECS Task Definition - Stock Analyser
resource "aws_ecs_task_definition" "stockanalyser_agent" {
  family                   = "${var.project_name}-stockanalyser-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "stockanalyser-agent"
      image     = "156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/stockanalyser-agent:latest"
      essential = true
      portMappings = [
        {
          containerPort = 10002
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "FALSE"
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/finance_a2a"
        }
      ]
      secrets = [
        {
          name      = "GOOGLE_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
        },
        {
          name      = "PERPLEXITY_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:PERPLEXITY_API_KEY::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.stockanalyser_agent.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:10002/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-stockanalyser-agent"
  }
}

# ECS Task Definition - Host Agent
resource "aws_ecs_task_definition" "host_agent" {
  family                   = "${var.project_name}-host-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "host-agent"
      image     = "156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/host-agent:latest"
      essential = true
      portMappings = [
        {
          containerPort = 10001
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "FALSE"
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/finance_a2a"
        },
        {
          name  = "FREE_USER_MESSAGE_LIMIT"
          value = "30"
        },
        {
          name  = "STOCK_ANALYSER_URL"
          value = "http://stockanalyser-agent.local:10002"
        },
        {
          name  = "STOCK_REPORT_ANALYSER_URL"
          value = "http://stockreport-agent.local:10003"
        }
      ]
      secrets = [
        {
          name      = "GOOGLE_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
        },
        {
          name      = "FIREBASE_PROJECT_ID"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:FIREBASE_PROJECT_ID::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.host_agent.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:10001/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-host-agent"
  }
}

# ECS Service - Stock Report Analyser
resource "aws_ecs_service" "stockreport_agent" {
  name            = "stockreport-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.stockreport_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.stockreport.arn
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "${var.project_name}-stockreport-service"
  }
}

# ECS Service - Stock Analyser
resource "aws_ecs_service" "stockanalyser_agent" {
  name            = "stockanalyser-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.stockanalyser_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.stockanalyser.arn
  }

  depends_on = [aws_ecs_service.stockreport_agent]

  tags = {
    Name = "${var.project_name}-stockanalyser-service"
  }
}

# ECS Service - Host Agent (with ALB)
resource "aws_ecs_service" "host_agent" {
  name            = "host-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.host_agent.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.host_agent.arn
    container_name   = "host-agent"
    container_port   = 10001
  }

  depends_on = [aws_lb_listener.http, aws_ecs_service.stockanalyser_agent]

  tags = {
    Name = "${var.project_name}-host-service"
  }
}

# Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "rds_endpoint" {
  description = "Endpoint of the RDS database"
  value       = aws_db_instance.postgres.endpoint
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "application_url" {
  description = "URL to access the application"
  value       = "http://${aws_lb.main.dns_name}"
}
