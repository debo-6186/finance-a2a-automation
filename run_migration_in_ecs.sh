#!/bin/bash
# Helper script to run database migration in AWS ECS using ECS Exec
# This script connects to a running ECS task and executes the migration

set -e

echo "========================================="
echo "Run Migration in AWS ECS"
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
echo "Executing migration in ECS task..."
echo "========================================="
echo ""

# Execute the migration script in the ECS container
aws ecs execute-command \
    --cluster "$CLUSTER_NAME" \
    --task "$TASK_ARN" \
    --container "host-agent" \
    --region "$REGION" \
    --interactive \
    --command "/bin/bash -c 'cd /app && cat > run_migration.sh << '\''EOF'\''
#!/bin/bash
set -e

echo \"=========================================\"
echo \"Database Migration - Fix Foreign Keys\"
echo \"=========================================\"
echo \"\"

# Install psycopg2 if not available
echo \"Installing dependencies...\"
pip install --quiet psycopg2-binary 2>&1 > /dev/null || echo \"psycopg2 already installed\"
echo \"\"

# Run the Python migration script
echo \"Running migration...\"
python3 << PYTHON_SCRIPT
import os
import psycopg2

DATABASE_URL = os.getenv(\"DATABASE_URL\")
if not DATABASE_URL:
    print(\"ERROR: DATABASE_URL not set\")
    exit(1)

# Parse database URL
url = DATABASE_URL.replace(\"postgresql://\", \"\")
user_part, rest = url.split(\"@\", 1)
host_port, db_name = rest.split(\"/\", 1)

if \":\" in user_part:
    username, password = user_part.split(\":\", 1)
else:
    username = user_part
    password = \"\"

if \":\" in host_port:
    host, port = host_port.split(\":\", 1)
else:
    host = host_port
    port = \"5432\"

print(f\"Connecting to database: {db_name} on {host}:{port}\")

try:
    conn = psycopg2.connect(
        host=host,
        port=port,
        database=db_name,
        user=username,
        password=password
    )
    conn.autocommit = False
    cursor = conn.cursor()
    print(\"Connected successfully\\n\")
    print(\"Applying migration...\")
    print(\"=\" * 60)

    migration_sql = \"\"\"
    ALTER TABLE conversation_sessions DROP CONSTRAINT IF EXISTS conversation_sessions_user_id_fkey;
    ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_user_id_fkey;
    ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_session_id_fkey;
    ALTER TABLE agent_states DROP CONSTRAINT IF EXISTS agent_states_session_id_fkey;
    ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_session_id_fkey;
    ALTER TABLE stock_recommendations DROP CONSTRAINT IF EXISTS stock_recommendations_user_id_fkey;

    ALTER TABLE conversation_sessions ADD CONSTRAINT conversation_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE;
    ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE;
    ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES conversation_sessions(id) ON UPDATE CASCADE ON DELETE CASCADE;
    ALTER TABLE agent_states ADD CONSTRAINT agent_states_session_id_fkey FOREIGN KEY (session_id) REFERENCES conversation_sessions(id) ON UPDATE CASCADE ON DELETE CASCADE;
    ALTER TABLE stock_recommendations ADD CONSTRAINT stock_recommendations_session_id_fkey FOREIGN KEY (session_id) REFERENCES conversation_sessions(id) ON UPDATE CASCADE ON DELETE CASCADE;
    ALTER TABLE stock_recommendations ADD CONSTRAINT stock_recommendations_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE;
    \"\"\"

    cursor.execute(migration_sql)
    print(\"Migration executed successfully\")
    print(\"=\" * 60)

    conn.commit()
    print(\"\\nMigration committed successfully!\")
    print(\"Foreign key constraints now support CASCADE UPDATE and CASCADE DELETE\")

    cursor.close()
    conn.close()

except Exception as e:
    print(f\"ERROR: {e}\")
    if '\''conn'\'' in locals():
        conn.rollback()
        conn.close()
    exit(1)

PYTHON_SCRIPT

echo \"\"
echo \"Migration completed successfully!\"
echo \"=========================================\"
EOF
chmod +x run_migration.sh && ./run_migration.sh'"

echo ""
echo "========================================="
echo "Migration execution completed!"
echo "========================================="
