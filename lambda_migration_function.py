"""
AWS Lambda function to run database migration.
Deploy this to Lambda in the same VPC as your RDS instance.

Required:
- Lambda must be in the same VPC as RDS
- Lambda security group must allow outbound to RDS security group on port 5432
- Add psycopg2 layer or package psycopg2-binary with the function
- Set environment variable: DATABASE_URL
"""

import os
import json
import psycopg2


def lambda_handler(event, context):
    """
    Run database migration to add CASCADE UPDATE to foreign key constraints.
    """

    print("Starting database migration...")

    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')

    if not database_url:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'DATABASE_URL environment variable not set'
            })
        }

    # Parse database URL
    try:
        url = database_url.replace("postgresql://", "")
        user_part, rest = url.split("@", 1)
        host_port, db_name = rest.split("/", 1)

        if ":" in user_part:
            username, password = user_part.split(":", 1)
        else:
            username = user_part
            password = ""

        if ":" in host_port:
            host, port = host_port.split(":", 1)
        else:
            host = host_port
            port = "5432"

        print(f"Connecting to database: {db_name} on {host}:{port}")

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Failed to parse DATABASE_URL: {str(e)}'
            })
        }

    # Migration SQL
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

    # Connect to database and run migration
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=db_name,
            user=username,
            password=password,
            sslmode='require'  # RDS requires SSL
        )
        conn.autocommit = False
        cursor = conn.cursor()

        print("Connected to database successfully")
        print("Executing migration...")

        # Execute migration
        cursor.execute(migration_sql)

        print("Migration executed successfully")

        # Commit changes
        conn.commit()

        print("Migration committed successfully")

        cursor.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Migration completed successfully',
                'details': 'Foreign key constraints updated with CASCADE UPDATE and CASCADE DELETE'
            })
        }

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Database error: {str(e)}'
            })
        }

    except Exception as e:
        print(f"Unexpected error: {e}")

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Unexpected error: {str(e)}'
            })
        }


if __name__ == "__main__":
    # For local testing
    os.environ['DATABASE_URL'] = 'postgresql://postgres:ParisSwiss*0610@finance-a2a-postgres.cmfakuca6d6h.us-east-1.rds.amazonaws.com:5432/finance_a2a'
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))
