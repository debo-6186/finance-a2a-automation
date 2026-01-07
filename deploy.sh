#!/bin/bash

# Finance A2A Automation - AWS Deployment Script
# This script automates the deployment of the multi-agent system to AWS

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install it first."
    exit 1
fi

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME="finance-a2a"
CLUSTER_NAME="${PROJECT_NAME}-cluster"

print_info "Starting deployment for Finance A2A Automation"
print_info "AWS Region: $AWS_REGION"

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
print_info "AWS Account ID: $AWS_ACCOUNT_ID"

# Step 1: Create ECR Repositories
print_info "Step 1/6: Creating ECR repositories..."

# Note: stockreport-agent removed - now integrated into host-agent
for repo in host-agent stockanalyser-agent; do
    if aws ecr describe-repositories --repository-names ${PROJECT_NAME}/${repo} --region $AWS_REGION 2>/dev/null; then
        print_warning "ECR repository ${PROJECT_NAME}/${repo} already exists"
    else
        aws ecr create-repository \
            --repository-name ${PROJECT_NAME}/${repo} \
            --region $AWS_REGION \
            --image-scanning-configuration scanOnPush=true
        print_info "Created ECR repository: ${PROJECT_NAME}/${repo}"
    fi
done

# Step 2: Build and Push Docker Images
print_info "Step 2/6: Building and pushing Docker images..."

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build and push Host Agent
print_info "Building Host Agent..."
docker build --platform linux/amd64 -f host_agent/Dockerfile -t ${PROJECT_NAME}/host-agent:latest .
docker tag ${PROJECT_NAME}/host-agent:latest \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}/host-agent:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}/host-agent:latest

# Build and push Stock Analyser Agent
print_info "Building Stock Analyser Agent..."
docker build --platform linux/amd64 -f stockanalyser_agent/Dockerfile -t ${PROJECT_NAME}/stockanalyser-agent:latest .
docker tag ${PROJECT_NAME}/stockanalyser-agent:latest \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}/stockanalyser-agent:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}/stockanalyser-agent:latest

# Stock Report Agent removed - now integrated into Host Agent

print_info "All images built and pushed successfully!"

# Step 3: Create Secrets (if they don't exist)
print_info "Step 3/6: Checking AWS Secrets Manager..."

if aws secretsmanager describe-secret --secret-id ${PROJECT_NAME}/api-keys --region $AWS_REGION 2>/dev/null; then
    print_warning "Secret ${PROJECT_NAME}/api-keys already exists. Skipping creation."
else
    print_warning "Please create secrets manually in AWS Secrets Manager:"
    print_warning "  1. ${PROJECT_NAME}/database - Database credentials"
    print_warning "  2. ${PROJECT_NAME}/api-keys - API keys (GOOGLE_API_KEY, etc.)"
fi

# Step 4: Create ECS Cluster
print_info "Step 4/6: Creating ECS cluster..."

if aws ecs describe-clusters --clusters $CLUSTER_NAME --region $AWS_REGION --query 'clusters[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
    print_warning "ECS cluster $CLUSTER_NAME already exists"
else
    aws ecs create-cluster \
        --cluster-name $CLUSTER_NAME \
        --region $AWS_REGION \
        --capacity-providers FARGATE FARGATE_SPOT \
        --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1
    print_info "Created ECS cluster: $CLUSTER_NAME"
fi

# Step 5: Create CloudWatch Log Groups
print_info "Step 5/6: Creating CloudWatch log groups..."

# Note: stockreport-agent removed - now integrated into host-agent
for agent in host-agent stockanalyser-agent; do
    LOG_GROUP="/ecs/${PROJECT_NAME}-${agent}"
    if aws logs describe-log-groups --log-group-name-prefix $LOG_GROUP --region $AWS_REGION --query 'logGroups[0]' 2>/dev/null | grep -q "$LOG_GROUP"; then
        print_warning "Log group $LOG_GROUP already exists"
    else
        aws logs create-log-group --log-group-name $LOG_GROUP --region $AWS_REGION
        print_info "Created log group: $LOG_GROUP"
    fi
done

# Step 6: Run Database Migrations
print_info "Step 6/8: Running database migrations via ECS task..."

# Check if host-agent service exists (needed for network config)
if aws ecs describe-services --cluster $CLUSTER_NAME --services host-agent --region $AWS_REGION --query 'services[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
    print_info "Running migration task (this may take a few minutes)..."

    # Make the script executable
    chmod +x run_migrations_task.sh

    # Run the migration script
    if ./run_migrations_task.sh; then
        print_info "✓ Database migrations completed successfully"
    else
        print_error "Migration failed! Stopping deployment."
        exit 1
    fi
else
    print_warning "host-agent service does not exist yet. Skipping migrations."
    print_warning "You will need to run migrations manually after first deployment using:"
    print_warning "  ./run_migrations_task.sh"
fi

echo ""

# Step 7: Update ECS Services
print_info "Step 7/8: Updating ECS services with new images..."

# Check if services exist and update them
for service in host-agent stockanalyser-agent; do
    if aws ecs describe-services --cluster $CLUSTER_NAME --services $service --region $AWS_REGION --query 'services[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
        print_info "Forcing new deployment for service: $service"
        aws ecs update-service \
            --cluster $CLUSTER_NAME \
            --service $service \
            --force-new-deployment \
            --region $AWS_REGION \
            --no-cli-pager > /dev/null
        print_info "✓ Deployment triggered for $service"
    else
        print_warning "Service $service does not exist yet. Skipping update."
    fi
done

# Step 8: Summary
print_info "Step 8/8: Deployment complete!"

cat << EOF

${GREEN}========================================
Deployment Status
========================================${NC}

✓ ECR repositories created
✓ Docker images built and pushed
✓ ECS cluster verified: $CLUSTER_NAME
✓ CloudWatch log groups created
✓ Database migrations completed
✓ ECS services updated (if they exist)

${YELLOW}Post-Deployment Tasks:${NC}
1. Update frontend environment variables with API CloudFront URL
2. Deploy frontend to Firebase Hosting

${GREEN}Useful Commands:${NC}
# Run migrations manually
./run_migrations_task.sh

# Monitor ECS services
aws ecs describe-services --cluster $CLUSTER_NAME --services host-agent stockanalyser-agent --region $AWS_REGION

# View service logs
aws logs tail /ecs/${PROJECT_NAME}-host-agent --follow --region $AWS_REGION
aws logs tail /ecs/${PROJECT_NAME}-stockanalyser-agent --follow --region $AWS_REGION

# View migration logs
aws logs tail /ecs/${PROJECT_NAME}-migration --follow --region $AWS_REGION

# Check CloudFront URL
cd terraform && terraform output cloudfront_url

# List ECR images
aws ecr list-images --repository-name ${PROJECT_NAME}/host-agent --region $AWS_REGION

EOF
