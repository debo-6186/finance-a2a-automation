# Clear All Tables - Deployment Guide

This guide provides multiple methods to clear all data from the database tables while properly handling foreign key constraints.

## Methods

### Method 1: Via SQL File (Recommended - Fastest)

**Prerequisites**: Bastion host SSH access

```bash
# 1. Wait for bastion to be ready (test connection)
ssh -i ~/.ssh/finance-a2a-bastion ec2-user@100.48.207.30 "echo 'Connected'"

# 2. Run the SQL script
ssh -i ~/.ssh/finance-a2a-bastion ec2-user@100.48.207.30 \
  "psql -h finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com \
   -U postgres -d finance_a2a" < clear_all_tables.sql
```

### Method 2: Via Local Database GUI (DBeaver, pgAdmin, etc.)

**Setup SSH Tunnel**:
- Host: `100.48.207.30`
- User: `ec2-user`
- Private Key: `~/.ssh/finance-a2a-bastion`

**Database Connection**:
- Host: `finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com`
- Port: `5432`
- Database: `finance_a2a`
- User: `postgres`
- Password: `ParisSwiss*0610`

**Then run**: Copy contents of `clear_all_tables.sql` and execute

### Method 3: Via AWS Lambda

**Deploy the Lambda**:

```bash
# 1. Create deployment package
cd /path/to/finance-a2a-automation
zip clear_tables_lambda.zip clear_tables_lambda.py

# 2. Create Lambda function (one-time)
aws lambda create-function \
  --function-name finance-a2a-clear-tables \
  --runtime python3.11 \
  --role arn:aws:iam::156041436571:role/finance-a2a-migration-lambda-role \
  --handler clear_tables_lambda.lambda_handler \
  --timeout 60 \
  --memory-size 256 \
  --zip-file fileb://clear_tables_lambda.zip \
  --vpc-config SubnetIds=subnet-03e80f9009fa9b522,subnet-0cded4ea775862589,SecurityGroupIds=sg-003a1a706ce3d6aac \
  --environment Variables="{DATABASE_URL=postgresql://postgres:ParisSwiss*0610@finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com:5432/finance_a2a}" \
  --region us-east-1

# 3. Invoke Lambda
aws lambda invoke \
  --function-name finance-a2a-clear-tables \
  --region us-east-1 \
  clear_response.json && cat clear_response.json
```

### Method 4: Direct psql Command

```bash
# Single command via bastion
ssh -i ~/.ssh/finance-a2a-bastion ec2-user@100.48.207.30 \
  "psql -h finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com \
   -U postgres -d finance_a2a \
   -c 'TRUNCATE TABLE users, conversation_sessions, conversation_messages, agent_states CASCADE;'"
```

## What the Script Does (Step by Step)

1. **Shows current row counts** - Displays how many records exist before deletion
2. **Truncates all tables with CASCADE** - Deletes all data while handling foreign key constraints automatically
3. **Shows final row counts** - Confirms all tables are empty (0 rows)
4. **Vacuums tables** - Reclaims disk space and updates statistics

## Tables Cleared

- `users` - All user accounts
- `conversation_sessions` - All conversation sessions
- `conversation_messages` - All messages
- `agent_states` - All agent state data

## Foreign Key Handling

The script uses `TRUNCATE ... CASCADE` which:
- Automatically handles foreign key constraints
- Faster than DELETE (doesn't generate individual delete operations)
- Properly clears all dependent data in correct order

## Safety

- Runs in a transaction (can rollback on error)
- Shows before/after counts for verification
- No schema changes - only data deletion
