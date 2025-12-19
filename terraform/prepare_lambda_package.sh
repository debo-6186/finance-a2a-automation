#!/bin/bash
# Script to prepare Lambda deployment package for database migration

set -e

echo "========================================="
echo "Preparing Lambda Migration Package"
echo "========================================="
echo ""

# Create temporary directory
TEMP_DIR=$(mktemp -d)
echo "Working directory: $TEMP_DIR"

# Copy Lambda function
echo "Copying Lambda function..."
cp ../lambda_migration_function.py "$TEMP_DIR/"

# Install psycopg2-binary for Lambda (Linux x86_64)
echo "Installing psycopg2-binary for Linux x86_64..."
pip install \
    --platform manylinux2014_x86_64 \
    --target="$TEMP_DIR/" \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    --upgrade \
    psycopg2-binary 2>&1 | grep -v "Requirement already satisfied" || true

# Create ZIP package
echo "Creating deployment package..."
cd "$TEMP_DIR"
zip -r migration_lambda.zip . > /dev/null

# Move to terraform directory
echo "Moving package to terraform directory..."
mv migration_lambda.zip "$OLDPWD/"

# Cleanup
cd "$OLDPWD"
rm -rf "$TEMP_DIR"

echo ""
echo "========================================="
echo "Package created: migration_lambda.zip"
echo "Size: $(du -h migration_lambda.zip | cut -f1)"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. cd terraform"
echo "2. terraform init (if not already done)"
echo "3. terraform apply -target=aws_lambda_function.migration"
echo "4. aws lambda invoke --function-name finance-a2a-db-migration --region us-east-1 response.json && cat response.json"
