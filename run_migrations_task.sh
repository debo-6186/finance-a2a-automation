#!/bin/bash
# Script to run database migrations as an ECS Fargate task
# This is the production-standard approach for running migrations

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME="finance-a2a"
CLUSTER_NAME="${PROJECT_NAME}-cluster"
TASK_FAMILY="${PROJECT_NAME}-migration"

print_info "========================================="
print_info "Database Migration Runner (ECS Fargate)"
print_info "========================================="
echo ""

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
print_info "AWS Account ID: $AWS_ACCOUNT_ID"
print_info "AWS Region: $AWS_REGION"
print_info "ECS Cluster: $CLUSTER_NAME"
echo ""

# Step 1: Register/Update Task Definition
print_info "Step 1/5: Registering migration task definition..."

# Replace placeholders in task definition and create temp file
TEMP_TASK_DEF=$(mktemp)
cat task-definition-migration.json | \
    sed "s/\${AWS_ACCOUNT_ID}/$AWS_ACCOUNT_ID/g" | \
    sed "s/\${AWS_REGION}/$AWS_REGION/g" > "$TEMP_TASK_DEF"

# Register the task definition
TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
        --cli-input-json "file://$TEMP_TASK_DEF" \
        --region $AWS_REGION \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)

# Clean up temp file
rm -f "$TEMP_TASK_DEF"

if [ -z "$TASK_DEFINITION_ARN" ]; then
    print_error "Failed to register task definition"
    exit 1
fi

print_info "Task definition registered: $TASK_DEFINITION_ARN"
echo ""

# Step 2: Create CloudWatch Log Group (if it doesn't exist)
print_info "Step 2/5: Ensuring CloudWatch log group exists..."

LOG_GROUP="/ecs/${PROJECT_NAME}-migration"
if aws logs describe-log-groups --log-group-name-prefix $LOG_GROUP --region $AWS_REGION --query 'logGroups[0]' 2>/dev/null | grep -q "$LOG_GROUP"; then
    print_info "Log group already exists: $LOG_GROUP"
else
    aws logs create-log-group --log-group-name $LOG_GROUP --region $AWS_REGION
    print_info "Created log group: $LOG_GROUP"
fi
echo ""

# Step 3: Get VPC and Subnet information from existing service
print_info "Step 3/5: Getting network configuration from host-agent service..."

# Get network configuration from the host-agent service
NETWORK_CONFIG=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services host-agent \
    --region $AWS_REGION \
    --query 'services[0].networkConfiguration.awsvpcConfiguration' \
    --output json 2>/dev/null)

if [ -z "$NETWORK_CONFIG" ] || [ "$NETWORK_CONFIG" == "null" ]; then
    print_error "Could not retrieve network configuration from host-agent service"
    print_error "Please ensure the host-agent service is running or provide network config manually"
    exit 1
fi

SUBNETS=$(echo $NETWORK_CONFIG | jq -r '.subnets | join(",")')
SECURITY_GROUPS=$(echo $NETWORK_CONFIG | jq -r '.securityGroups | join(",")')
ASSIGN_PUBLIC_IP=$(echo $NETWORK_CONFIG | jq -r '.assignPublicIp')

print_info "Using network configuration:"
print_debug "  Subnets: $SUBNETS"
print_debug "  Security Groups: $SECURITY_GROUPS"
print_debug "  Assign Public IP: $ASSIGN_PUBLIC_IP"
echo ""

# Step 4: Run the Migration Task
print_info "Step 4/5: Starting migration task..."
print_warning "This will run all SQL migrations in order. Please wait..."
echo ""

TASK_ARN=$(aws ecs run-task \
    --cluster $CLUSTER_NAME \
    --task-definition $TASK_DEFINITION_ARN \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUPS],assignPublicIp=$ASSIGN_PUBLIC_IP}" \
    --region $AWS_REGION \
    --query 'tasks[0].taskArn' \
    --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
    print_error "Failed to start migration task"
    exit 1
fi

print_info "Migration task started: $TASK_ARN"
echo ""

# Step 5: Wait for Task to Complete
print_info "Step 5/5: Waiting for migration task to complete..."
print_info "You can monitor logs at: https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups/log-group/\$252Fecs\$252F${PROJECT_NAME}-migration"
echo ""

# Wait for task to complete
MAX_WAIT_TIME=600  # 10 minutes
WAIT_INTERVAL=10
ELAPSED_TIME=0

while [ $ELAPSED_TIME -lt $MAX_WAIT_TIME ]; do
    TASK_STATUS=$(aws ecs describe-tasks \
        --cluster $CLUSTER_NAME \
        --tasks $TASK_ARN \
        --region $AWS_REGION \
        --query 'tasks[0].lastStatus' \
        --output text)

    print_debug "Task status: $TASK_STATUS (waited ${ELAPSED_TIME}s)"

    if [ "$TASK_STATUS" == "STOPPED" ]; then
        break
    fi

    sleep $WAIT_INTERVAL
    ELAPSED_TIME=$((ELAPSED_TIME + WAIT_INTERVAL))
done

echo ""

# Check final status
TASK_EXIT_CODE=$(aws ecs describe-tasks \
    --cluster $CLUSTER_NAME \
    --tasks $TASK_ARN \
    --region $AWS_REGION \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

TASK_STOP_REASON=$(aws ecs describe-tasks \
    --cluster $CLUSTER_NAME \
    --tasks $TASK_ARN \
    --region $AWS_REGION \
    --query 'tasks[0].stoppedReason' \
    --output text)

if [ "$TASK_EXIT_CODE" == "0" ]; then
    print_info "========================================="
    print_info "${GREEN}✓ Migration completed successfully!${NC}"
    print_info "========================================="
    echo ""
    print_info "Migrations that were run:"
    print_info "  - 000_add_portfolio_statement_uploaded_field.sql"
    print_info "  - 001_add_stock_recommendations_table.sql"
    print_info "  - 002_add_input_format_column.sql"
    print_info "  - 003_add_portfolio_analysis_table.sql"
    print_info "  - 004_add_user_whitelist_table.sql"
    echo ""
    exit 0
else
    print_error "========================================="
    print_error "Migration task failed!"
    print_error "========================================="
    print_error "Exit code: $TASK_EXIT_CODE"
    print_error "Stop reason: $TASK_STOP_REASON"
    echo ""
    print_error "Check logs for details:"
    print_error "aws logs tail $LOG_GROUP --follow --region $AWS_REGION"
    echo ""
    exit 1
fi
