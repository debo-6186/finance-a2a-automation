#!/bin/bash
# Script to run database migration from within AWS ECS container
# This should be executed using ECS Exec or as part of a deployment

set -e  # Exit on error

echo "========================================="
echo "Database Migration - Fix Foreign Keys"
echo "========================================="
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    exit 1
fi

echo "Database URL: ${DATABASE_URL%%@*}@[REDACTED]"
echo ""

# Install psycopg2 if not available
echo "Installing dependencies..."
pip install --quiet psycopg2-binary 2>&1 > /dev/null || echo "psycopg2 already installed"

# Run the Python migration script
echo "Running migration..."
python3 << 'PYTHON_SCRIPT'
import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

# Parse database URL
url = DATABASE_URL.replace("postgresql://", "")
user_part, rest = url.split("@", 1)
host_port, db_name = rest.split("/", 1)

# Handle password in username
if ":" in user_part:
    username, password = user_part.split(":", 1)
else:
    username = user_part
    password = ""

# Handle port in host
if ":" in host_port:
    host, port = host_port.split(":", 1)
else:
    host = host_port
    port = "5432"

print(f"Connecting to database: {db_name} on {host}:{port}")

try:
    # Connect to database
    conn = psycopg2.connect(
        host=host,
        port=port,
        database=db_name,
        user=username,
        password=password
    )
    conn.autocommit = False
    cursor = conn.cursor()

    print("Connected successfully")
    print("")
    print("Applying migration...")
    print("=" * 60)

    # Drop and recreate foreign key constraints with CASCADE
    migration_sql = """
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
    """

    # Execute migration
    cursor.execute(migration_sql)

    print("Migration executed successfully")
    print("=" * 60)

    # Commit changes
    conn.commit()
    print("")
    print("Migration committed successfully!")
    print("Foreign key constraints now support CASCADE UPDATE and CASCADE DELETE")

    cursor.close()
    conn.close()

except psycopg2.Error as e:
    print(f"ERROR: Database error: {e}")
    if 'conn' in locals():
        conn.rollback()
        conn.close()
    exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

PYTHON_SCRIPT

echo ""
echo "Migration completed successfully!"
echo "========================================="
