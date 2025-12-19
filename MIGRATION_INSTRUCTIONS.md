# Database Migration Instructions

## Problem
The login API is failing with a foreign key constraint violation error because the code tries to update user IDs when a user logs in with a different Firebase UID but the same email.

## Solution
Update the foreign key constraints to support `ON UPDATE CASCADE`, which will automatically update related records when a user ID changes.

## RDS Endpoint
```
finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com:5432
```

## Migration Options

### Option 1: Run from Local Machine (Requires Public Access or SSH Tunnel)

**Note:** Your RDS instance is in a private subnet and not publicly accessible. You'll need to either:
1. Temporarily enable public access in RDS settings
2. Set up an SSH tunnel through a bastion host
3. Use AWS Systems Manager Session Manager for port forwarding

If you have public access or a tunnel set up:

```bash
cd host_agent
python3 apply_migration.py
```

### Option 2: Execute SQL Directly

Connect to your RDS database using any method (psql, pgAdmin, DBeaver, etc.) and run:

```sql
-- File: host_agent/fix_foreign_key_constraints.sql

-- Drop existing foreign key constraints
ALTER TABLE conversation_sessions DROP CONSTRAINT IF EXISTS conversation_sessions_user_id_fkey;
ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_user_id_fkey;
ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_session_id_fkey;
ALTER TABLE agent_states DROP CONSTRAINT IF EXISTS agent_states_session_id_fkey;
ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_session_id_fkey;
ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_user_id_fkey;

-- Re-create foreign key constraints with CASCADE UPDATE
ALTER TABLE conversation_sessions
    ADD CONSTRAINT conversation_sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE conversation_messages
    ADD CONSTRAINT conversation_messages_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE conversation_messages
    ADD CONSTRAINT conversation_messages_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE agent_states
    ADD CONSTRAINT agent_states_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE stock_recommendations
    ADD CONSTRAINT stock_recommendations_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
    ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE stock_recommendations
    ADD CONSTRAINT stock_recommendations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON UPDATE CASCADE ON DELETE CASCADE;
```

### Option 3: Run via ECS Exec (Recommended for Private RDS)

If you have ECS Exec enabled on your tasks:

```bash
./run_migration_in_ecs.sh
```

Or manually:

```bash
# Get the task ARN
TASK_ARN=$(aws ecs list-tasks \
    --cluster finance-a2a-cluster \
    --service-name host-agent \
    --region us-east-1 \
    --query 'taskArns[0]' \
    --output text)

# Execute command in the container
aws ecs execute-command \
    --cluster finance-a2a-cluster \
    --task "$TASK_ARN" \
    --container host-agent \
    --region us-east-1 \
    --interactive \
    --command "/bin/bash"

# Then inside the container:
cd /app/host_agent
./run_migration_aws.sh
```

### Option 4: Use AWS Systems Manager Session Manager (Port Forward)

```bash
# Start a port forwarding session to RDS
aws ssm start-session \
    --target <ec2-instance-id-in-same-vpc> \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters '{
        "host":["finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com"],
        "portNumber":["5432"],
        "localPortNumber":["5432"]
    }'

# Then in another terminal:
PGPASSWORD='ParisSwiss*0610' psql \
    -h localhost \
    -p 5432 \
    -U postgres \
    -d finance_a2a \
    -f host_agent/fix_foreign_key_constraints.sql
```

### Option 5: Quick Fix - Execute via AWS Lambda (Easiest)

Create a Lambda function in the same VPC as your RDS instance and run the migration from there.

## Verification

After running the migration, verify the constraints were updated:

```sql
-- Check foreign key constraints
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.update_rule,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_schema = 'public'
ORDER BY tc.table_name;
```

You should see `update_rule = 'CASCADE'` for all foreign keys.

## Test the Login

After applying the migration, test the login again:

```bash
curl -X POST https://dtwugznkn4ata.cloudfront.net/api/login \
    -H 'Content-Type: application/json' \
    -d '{"id_token":"<your-firebase-id-token>"}'
```

The login should now succeed even if the user's Firebase UID has changed.
