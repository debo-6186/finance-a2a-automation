#!/bin/bash
# Script to run all database migrations on AWS RDS via ECS
# This executes the run_migrations.py script which runs all SQL migrations in order

set -e

echo "========================================="
echo "Run All Database Migrations on AWS ECS"
echo "========================================="
echo ""

# Configuration
CLUSTER_NAME="finance-a2a-cluster"
SERVICE_NAME="host-agent"
REGION="us-east-1"

echo "Getting running task for service: $SERVICE_NAME"
echo ""

# Get the task ARN for the host-agent service
TASK_ARN=$(aws ecs list-tasks \
    --cluster "$CLUSTER_NAME" \
    --service-name "$SERVICE_NAME" \
    --region "$REGION" \
    --query 'taskArns[0]' \
    --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" == "None" ]; then
    echo "ERROR: No running tasks found for service $SERVICE_NAME in cluster $CLUSTER_NAME"
    echo ""
    echo "Please ensure the ECS service is running and try again."
    exit 1
fi

echo "Found task: $TASK_ARN"
echo ""
echo "Running all migrations in ECS task..."
echo "========================================="
echo ""

# Execute the migration script in the ECS container
aws ecs execute-command \
    --cluster "$CLUSTER_NAME" \
    --task "$TASK_ARN" \
    --container "host-agent" \
    --region "$REGION" \
    --interactive \
    --command "/bin/bash -c 'cd /app && python migrations/run_migrations.py'"

echo ""
echo "========================================="
echo "Migration execution completed!"
echo "========================================="
echo ""
echo "This will have run all migrations including:"
echo "  - 000_add_portfolio_statement_uploaded_field.sql"
echo "  - 001_add_stock_recommendations_table.sql"
echo "  - 002_add_input_format_column.sql"
echo "  - 003_add_portfolio_analysis_table.sql"
echo "  - 004_add_user_whitelist_table.sql (NEW)"
echo ""
