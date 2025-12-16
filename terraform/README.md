# Terraform Deployment for Finance A2A Automation

This directory contains Terraform configuration to deploy the Finance A2A Automation system to AWS.

## Prerequisites

1. **Terraform** installed (version >= 1.0)
2. **AWS CLI** configured with appropriate credentials
3. **Docker images** pushed to ECR (run `../deploy.sh` first)

## Quick Start

### 1. Initialize Terraform

```bash
cd terraform
terraform init
```

### 2. Configure Variables

Copy the example variables file and edit it:

```bash
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

Fill in your values:
- `db_password`: Strong password for PostgreSQL database
- `google_api_key`: Your Google Gemini API key
- `perplexity_api_key`: Your Perplexity API key
- `firebase_project_id`: Your Firebase project ID

### 3. Review the Plan

```bash
terraform plan
```

This will show you all resources that will be created.

### 4. Apply the Configuration

```bash
terraform apply
```

Type `yes` when prompted to create the resources.

### 5. Get the Application URL

After deployment completes, Terraform will output the ALB DNS name:

```bash
terraform output application_url
```

Access your application at: `http://<alb-dns-name>/health`

## What Gets Deployed

This Terraform configuration creates:

### Networking
- VPC with CIDR 10.0.0.0/16
- 2 Public subnets (for ECS tasks and ALB)
- 2 Private subnets (for RDS)
- Internet Gateway
- Route tables and associations

### Security
- Security groups for ALB, ECS tasks, and RDS
- IAM roles for ECS task execution
- Secrets Manager secrets for API keys and database credentials

### Database
- RDS PostgreSQL instance (db.t3.micro)
- Automated backups (7-day retention)
- Encryption at rest

### Compute
- ECS Fargate cluster
- CloudWatch log groups for each service

### Load Balancing
- Application Load Balancer
- Target group for host agent
- HTTP listener (port 80)

### Service Discovery
- Private DNS namespace for inter-agent communication
- Service discovery for stockanalyser-agent and stockreport-agent

## Resource Naming

All resources are named with the prefix specified in `project_name` variable (default: `finance-a2a`).

## Estimated Costs

- **RDS PostgreSQL (db.t3.micro)**: ~$15-20/month
- **ECS Fargate**: ~$60/month (for 3 services)
- **Application Load Balancer**: ~$20/month
- **Data Transfer**: ~$10/month
- **Total**: ~$105-120/month

## Manual Steps After Terraform

After Terraform creates the infrastructure, you need to:

1. **Create ECS Task Definitions** (see main AWS_DEPLOYMENT_GUIDE.md)
2. **Create ECS Services** to run the tasks
3. **Configure domain name** (optional, using Route 53)
4. **Set up HTTPS** (optional, using ACM)

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

Type `yes` when prompted.

**Warning**: This will delete all resources including the database!

## Terraform State

This configuration uses local state. For production deployments:

1. Configure S3 backend for state storage
2. Enable state locking with DynamoDB
3. Use Terraform workspaces for multiple environments

Example backend configuration:

```hcl
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "finance-a2a/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}
```

## Outputs

After `terraform apply`, you can view outputs at any time:

```bash
# View all outputs
terraform output

# View specific output
terraform output alb_dns_name
terraform output rds_endpoint
```

## Troubleshooting

### Error: VPC CIDR conflict
If you get a CIDR conflict error, the VPC already exists. Either:
- Delete the existing VPC
- Change the CIDR in `main.tf`

### Error: DB instance already exists
If the database already exists:
- Delete it manually
- Import it into Terraform state

### Error: Secret already exists
If secrets already exist in Secrets Manager:
- Delete them manually
- Import them into Terraform state

## Next Steps

1. Complete ECS service deployment (see AWS_DEPLOYMENT_GUIDE.md)
2. Set up monitoring and alerting
3. Configure auto-scaling policies
4. Set up CI/CD pipeline
5. Configure custom domain with Route 53
6. Enable HTTPS with ACM certificate

## Support

For issues:
- Check Terraform documentation: https://www.terraform.io/docs
- Review AWS provider documentation: https://registry.terraform.io/providers/hashicorp/aws
- See main deployment guide: ../AWS_DEPLOYMENT_GUIDE.md
