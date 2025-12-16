# AWS Deployment Guide for Finance A2A Automation

This guide will help you deploy the multi-agent finance automation system to AWS using ECS Fargate, RDS, and other AWS services.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Load Balancer                │
│                      (Public Internet)                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌────────────────────┐
│  Host Agent   │ │Stock Analyser │ │Stock Report Agent  │
│ ECS Service   │ │  ECS Service  │ │   ECS Service      │
│   (Fargate)   │ │   (Fargate)   │ │    (Fargate)       │
│  Port: 10001  │ │  Port: 10002  │ │   Port: 10003      │
└───────┬───────┘ └───────┬───────┘ └─────────┬──────────┘
        │                 │                    │
        └─────────────────┼────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  RDS Postgres │
                  │   Database    │
                  └───────────────┘
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
3. **Docker** installed locally
4. **API Keys**:
   - Google API Key (Gemini)
   - Firebase Project credentials
   - Perplexity API Key
   - Activepieces credentials (optional)

## Deployment Options

We'll cover two deployment approaches:

### Option A: AWS ECS Fargate (Recommended - Fully Managed)
- Serverless container orchestration
- No EC2 instances to manage
- Auto-scaling built-in
- Pay only for what you use

### Option B: AWS ECS with EC2
- More control over underlying infrastructure
- Better for cost optimization at scale
- Requires instance management

---

## Option A: ECS Fargate Deployment (Step-by-Step)

### Step 1: Set Up AWS Infrastructure

#### 1.1 Create VPC and Subnets

```bash
# Create VPC
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=finance-a2a-vpc}]'

# Save the VPC ID from the output
export VPC_ID=<vpc-id-from-output>

# Create Public Subnet 1 (us-east-1a)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=finance-a2a-public-1a}]'

export PUBLIC_SUBNET_1=<subnet-id-from-output>

# Create Public Subnet 2 (us-east-1b)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=finance-a2a-public-1b}]'

export PUBLIC_SUBNET_2=<subnet-id-from-output>

# Create Private Subnet 1 (for RDS)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.11.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=finance-a2a-private-1a}]'

export PRIVATE_SUBNET_1=<subnet-id-from-output>

# Create Private Subnet 2 (for RDS)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.12.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=finance-a2a-private-1b}]'

export PRIVATE_SUBNET_2=<subnet-id-from-output>

# Create Internet Gateway
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=finance-a2a-igw}]'

export IGW_ID=<igw-id-from-output>

# Attach Internet Gateway to VPC
aws ec2 attach-internet-gateway \
  --vpc-id $VPC_ID \
  --internet-gateway-id $IGW_ID

# Create Route Table for public subnets
aws ec2 create-route-table \
  --vpc-id $VPC_ID \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=finance-a2a-public-rt}]'

export ROUTE_TABLE_ID=<route-table-id-from-output>

# Create route to Internet Gateway
aws ec2 create-route \
  --route-table-id $ROUTE_TABLE_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate route table with public subnets
aws ec2 associate-route-table \
  --subnet-id $PUBLIC_SUBNET_1 \
  --route-table-id $ROUTE_TABLE_ID

aws ec2 associate-route-table \
  --subnet-id $PUBLIC_SUBNET_2 \
  --route-table-id $ROUTE_TABLE_ID
```

#### 1.2 Create Security Groups

```bash
# Security Group for ALB
aws ec2 create-security-group \
  --group-name finance-a2a-alb-sg \
  --description "Security group for Application Load Balancer" \
  --vpc-id $VPC_ID

export ALB_SG=<security-group-id-from-output>

# Allow HTTP/HTTPS traffic to ALB
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Security Group for ECS Tasks
aws ec2 create-security-group \
  --group-name finance-a2a-ecs-sg \
  --description "Security group for ECS tasks" \
  --vpc-id $VPC_ID

export ECS_SG=<security-group-id-from-output>

# Allow traffic from ALB to ECS tasks
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10001 \
  --source-group $ALB_SG

aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10002 \
  --source-group $ALB_SG

aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10003 \
  --source-group $ALB_SG

# Allow inter-agent communication within ECS security group
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10001 \
  --source-group $ECS_SG

aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10002 \
  --source-group $ECS_SG

aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG \
  --protocol tcp \
  --port 10003 \
  --source-group $ECS_SG

# Security Group for RDS
aws ec2 create-security-group \
  --group-name finance-a2a-rds-sg \
  --description "Security group for RDS database" \
  --vpc-id $VPC_ID

export RDS_SG=<security-group-id-from-output>

# Allow PostgreSQL traffic from ECS tasks
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG \
  --protocol tcp \
  --port 5432 \
  --source-group $ECS_SG
```

### Step 2: Create RDS PostgreSQL Database

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name finance-a2a-db-subnet-group \
  --db-subnet-group-description "Subnet group for finance a2a database" \
  --subnet-ids $PRIVATE_SUBNET_1 $PRIVATE_SUBNET_2

# Create RDS PostgreSQL instance
aws rds create-db-instance \
  --db-instance-identifier finance-a2a-postgres \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.4 \
  --master-username postgres \
  --master-user-password <YOUR_STRONG_PASSWORD> \
  --allocated-storage 20 \
  --vpc-security-group-ids $RDS_SG \
  --db-subnet-group-name finance-a2a-db-subnet-group \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "mon:04:00-mon:05:00" \
  --storage-encrypted \
  --publicly-accessible false

# Wait for the database to be available (this may take 5-10 minutes)
aws rds wait db-instance-available \
  --db-instance-identifier finance-a2a-postgres

# Get the database endpoint
aws rds describe-db-instances \
  --db-instance-identifier finance-a2a-postgres \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text

export DB_ENDPOINT=<endpoint-from-output>
```

### Step 3: Store Secrets in AWS Secrets Manager

```bash
# Create secret for database credentials
aws secretsmanager create-secret \
  --name finance-a2a/database \
  --description "Database credentials for finance a2a" \
  --secret-string '{
    "username": "postgres",
    "password": "<YOUR_STRONG_PASSWORD>",
    "host": "'$DB_ENDPOINT'",
    "port": "5432",
    "database": "finance_a2a"
  }'

# Create secret for API keys
aws secretsmanager create-secret \
  --name finance-a2a/api-keys \
  --description "API keys for finance a2a services" \
  --secret-string '{
    "GOOGLE_API_KEY": "<YOUR_GOOGLE_API_KEY>",
    "PERPLEXITY_API_KEY": "<YOUR_PERPLEXITY_API_KEY>",
    "FIREBASE_PROJECT_ID": "<YOUR_FIREBASE_PROJECT_ID>",
    "ACTIVEPIECES_USERNAME": "<YOUR_USERNAME>",
    "ACTIVEPIECES_PASSWORD": "<YOUR_PASSWORD>"
  }'
```

### Step 4: Create ECR Repositories

```bash
# Create ECR repositories for each agent
aws ecr create-repository --repository-name finance-a2a/host-agent
aws ecr create-repository --repository-name finance-a2a/stockanalyser-agent
aws ecr create-repository --repository-name finance-a2a/stockreport-agent

# Get ECR login credentials
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <YOUR_AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
```

### Step 5: Build and Push Docker Images

```bash
# Set your AWS account ID
export AWS_ACCOUNT_ID=<your-aws-account-id>
export AWS_REGION=us-east-1

# Build and push host agent
cd host_agent
docker build -t finance-a2a/host-agent:latest .
docker tag finance-a2a/host-agent:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/host-agent:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/host-agent:latest

# Build and push stock analyser agent
cd ../stockanalyser_agent
docker build -t finance-a2a/stockanalyser-agent:latest .
docker tag finance-a2a/stockanalyser-agent:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/stockanalyser-agent:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/stockanalyser-agent:latest

# Build and push stock report agent
cd ../stockreport_analyser_agent
docker build -t finance-a2a/stockreport-agent:latest .
docker tag finance-a2a/stockreport-agent:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/stockreport-agent:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/stockreport-agent:latest

cd ..
```

### Step 6: Create ECS Cluster

```bash
# Create ECS cluster
aws ecs create-cluster \
  --cluster-name finance-a2a-cluster \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1
```

### Step 7: Create IAM Roles

```bash
# Create task execution role (for pulling images and accessing secrets)
cat > task-execution-role-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name finance-a2a-task-execution-role \
  --assume-role-policy-document file://task-execution-role-trust-policy.json

# Attach AWS managed policies
aws iam attach-role-policy \
  --role-name finance-a2a-task-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Create custom policy for Secrets Manager access
cat > secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:finance-a2a/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name finance-a2a-task-execution-role \
  --policy-name SecretsManagerAccess \
  --policy-document file://secrets-policy.json

# Create task role (for application runtime permissions)
aws iam create-role \
  --role-name finance-a2a-task-role \
  --assume-role-policy-document file://task-execution-role-trust-policy.json

export TASK_EXECUTION_ROLE_ARN=$(aws iam get-role --role-name finance-a2a-task-execution-role --query 'Role.Arn' --output text)
export TASK_ROLE_ARN=$(aws iam get-role --role-name finance-a2a-task-role --query 'Role.Arn' --output text)
```

### Step 8: Create ECS Task Definitions

Create task definition files for each service. I'll provide a template for the host agent:

```bash
cat > host-agent-task-def.json <<EOF
{
  "family": "finance-a2a-host-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "$TASK_EXECUTION_ROLE_ARN",
  "taskRoleArn": "$TASK_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "host-agent",
      "image": "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/finance-a2a/host-agent:latest",
      "portMappings": [
        {
          "containerPort": 10001,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "environment": [
        {
          "name": "STOCK_ANALYSER_URL",
          "value": "http://stockanalyser-agent.local:10002"
        },
        {
          "name": "STOCK_REPORT_ANALYSER_URL",
          "value": "http://stockreport-agent.local:10003"
        },
        {
          "name": "FREE_USER_MESSAGE_LIMIT",
          "value": "30"
        }
      ],
      "secrets": [
        {
          "name": "GOOGLE_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:finance-a2a/api-keys:GOOGLE_API_KEY::"
        },
        {
          "name": "FIREBASE_PROJECT_ID",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:finance-a2a/api-keys:FIREBASE_PROJECT_ID::"
        },
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:finance-a2a/database:password::"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/finance-a2a-host-agent",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:10001/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
EOF

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/finance-a2a-host-agent
aws logs create-log-group --log-group-name /ecs/finance-a2a-stockanalyser-agent
aws logs create-log-group --log-group-name /ecs/finance-a2a-stockreport-agent

# Register task definition
aws ecs register-task-definition --cli-input-json file://host-agent-task-def.json
```

### Step 9: Create Application Load Balancer

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name finance-a2a-alb \
  --subnets $PUBLIC_SUBNET_1 $PUBLIC_SUBNET_2 \
  --security-groups $ALB_SG \
  --scheme internet-facing \
  --type application

export ALB_ARN=<alb-arn-from-output>

# Create target groups
aws elbv2 create-target-group \
  --name finance-a2a-host-tg \
  --protocol HTTP \
  --port 10001 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30

export HOST_TG_ARN=<target-group-arn>

# Create listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$HOST_TG_ARN
```

### Step 10: Create Service Discovery (for inter-agent communication)

```bash
# Create private DNS namespace
aws servicediscovery create-private-dns-namespace \
  --name local \
  --vpc $VPC_ID

export NAMESPACE_ID=<namespace-id-from-output>

# Create service discovery services
aws servicediscovery create-service \
  --name stockanalyser-agent \
  --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
  --health-check-custom-config FailureThreshold=1

export STOCKANALYSER_SERVICE_ID=<service-id>

aws servicediscovery create-service \
  --name stockreport-agent \
  --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
  --health-check-custom-config FailureThreshold=1

export STOCKREPORT_SERVICE_ID=<service-id>
```

### Step 11: Create ECS Services

```bash
# Create Stock Report Analyser service
aws ecs create-service \
  --cluster finance-a2a-cluster \
  --service-name stockreport-agent \
  --task-definition finance-a2a-stockreport-agent \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$PUBLIC_SUBNET_1,$PUBLIC_SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$STOCKREPORT_SERVICE_ID"

# Create Stock Analyser service
aws ecs create-service \
  --cluster finance-a2a-cluster \
  --service-name stockanalyser-agent \
  --task-definition finance-a2a-stockanalyser-agent \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$PUBLIC_SUBNET_1,$PUBLIC_SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$STOCKANALYSER_SERVICE_ID"

# Create Host Agent service with ALB
aws ecs create-service \
  --cluster finance-a2a-cluster \
  --service-name host-agent \
  --task-definition finance-a2a-host-agent \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$PUBLIC_SUBNET_1,$PUBLIC_SUBNET_2],securityGroups=[$ECS_SG],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=$HOST_TG_ARN,containerName=host-agent,containerPort=10001 \
  --health-check-grace-period-seconds 60
```

### Step 12: Get Your Application URL

```bash
# Get the ALB DNS name
aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' \
  --output text

# Your application will be available at:
# http://<alb-dns-name>/health
# http://<alb-dns-name>/chats
```

---

## Option B: Alternative - AWS ECS with EC2

If you prefer EC2 instances for better cost control at scale:

1. Launch an ECS-optimized EC2 Auto Scaling Group
2. Use EC2 launch type instead of Fargate in task definitions
3. Configure capacity providers for the cluster
4. Benefits: Lower cost at scale, more control
5. Tradeoffs: Need to manage instances, patching, scaling

---

## Cost Estimation

### Fargate Deployment (Monthly):
- **RDS PostgreSQL (db.t3.micro)**: ~$15-20/month
- **ECS Fargate Tasks**:
  - Host Agent (2 tasks, 0.5 vCPU, 1GB): ~$30/month
  - Stock Analyser (1 task, 0.5 vCPU, 1GB): ~$15/month
  - Stock Report Analyser (1 task, 0.5 vCPU, 1GB): ~$15/month
- **Application Load Balancer**: ~$20/month
- **Data Transfer**: ~$10/month (varies with usage)
- **CloudWatch Logs**: ~$5/month

**Total**: ~$110-120/month for basic setup

### Cost Optimization Tips:
1. Use Fargate Spot for non-critical workloads (70% cost savings)
2. Use Aurora Serverless v2 for database auto-scaling
3. Implement auto-scaling policies to scale down during low usage
4. Use CloudWatch alarms to monitor costs

---

## Monitoring and Logging

### CloudWatch Dashboards
```bash
# Create a dashboard for monitoring
aws cloudwatch put-dashboard \
  --dashboard-name finance-a2a-dashboard \
  --dashboard-body file://dashboard.json
```

### Key Metrics to Monitor:
- ECS Service CPU/Memory utilization
- RDS Database connections and query performance
- ALB target health and request count
- Application errors and response times

### Set Up Alarms
```bash
# Example: High CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name finance-a2a-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

---

## Scaling Configuration

### Auto-Scaling for ECS Services

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/finance-a2a-cluster/host-agent \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Create scaling policy based on CPU
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/finance-a2a-cluster/host-agent \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling-policy \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

---

## Security Best Practices

1. **Use AWS Secrets Manager** for all sensitive credentials
2. **Enable VPC Flow Logs** for network monitoring
3. **Use AWS WAF** with ALB to protect against common attacks
4. **Enable RDS encryption** at rest and in transit
5. **Implement IAM roles** with least privilege principle
6. **Enable AWS CloudTrail** for audit logging
7. **Use AWS Certificate Manager** for HTTPS certificates
8. **Implement rate limiting** at API Gateway or ALB level

---

## CI/CD Pipeline (Optional)

### Using AWS CodePipeline

```bash
# Create CodeBuild project for building Docker images
# Create CodePipeline for automated deployments
# Configure GitHub webhook for automatic builds on push
```

See `ci-cd-setup.md` for detailed CI/CD configuration.

---

## Troubleshooting

### Common Issues:

1. **Tasks fail to start**:
   - Check CloudWatch logs
   - Verify secrets are accessible
   - Ensure security groups allow inter-service communication

2. **Database connection failures**:
   - Verify RDS security group allows ECS security group
   - Check database endpoint is correct
   - Verify credentials in Secrets Manager

3. **Inter-agent communication fails**:
   - Ensure Service Discovery is working
   - Check DNS resolution within VPC
   - Verify security group rules

### Useful Commands:

```bash
# View ECS task logs
aws logs tail /ecs/finance-a2a-host-agent --follow

# Check service status
aws ecs describe-services \
  --cluster finance-a2a-cluster \
  --services host-agent

# View task details
aws ecs describe-tasks \
  --cluster finance-a2a-cluster \
  --tasks <task-arn>
```

---

## Cleanup

To delete all resources and avoid charges:

```bash
# Delete ECS services
aws ecs delete-service --cluster finance-a2a-cluster --service host-agent --force
aws ecs delete-service --cluster finance-a2a-cluster --service stockanalyser-agent --force
aws ecs delete-service --cluster finance-a2a-cluster --service stockreport-agent --force

# Delete ECS cluster
aws ecs delete-cluster --cluster finance-a2a-cluster

# Delete RDS instance
aws rds delete-db-instance \
  --db-instance-identifier finance-a2a-postgres \
  --skip-final-snapshot

# Delete ALB
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN

# Delete target groups
aws elbv2 delete-target-group --target-group-arn $HOST_TG_ARN

# Delete VPC resources (subnets, route tables, internet gateway, VPC)
# ... (detailed cleanup commands)
```

---

## Next Steps

1. Set up custom domain with Route 53
2. Configure HTTPS with AWS Certificate Manager
3. Implement CI/CD pipeline
4. Set up monitoring and alerting
5. Configure backup and disaster recovery
6. Implement multi-region deployment for high availability

---

## Support

For issues or questions:
- Check CloudWatch logs for application errors
- Review AWS documentation
- Contact your DevOps team

**Last Updated**: 2025-12-04
