#!/usr/bin/env python3
"""
Lambda function to clear all tables in the finance_a2a database.
This handles foreign key constraints properly using TRUNCATE CASCADE.
"""

import os
import json
import psycopg2
from urllib.parse import urlparse


def lambda_handler(event, context):
    """
    Lambda handler to clear all tables in the database.
    """
    print("Starting database table clearing...")

    # Get database URL from environment variable
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'DATABASE_URL environment variable not set'})
        }

    # Parse database URL
    parsed = urlparse(database_url)
    db_config = {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path[1:],  # Remove leading '/'
        'user': parsed.username,
        'password': parsed.password
    }

    print(f"Connecting to database: {db_config['database']} on {db_config['host']}:{db_config['port']}")

    try:
        # Connect to database
        conn = psycopg2.connect(**db_config)
        conn.autocommit = False  # Use transaction
        cursor = conn.cursor()

        print("Connected to database successfully")

        # Get counts before deletion
        print("Getting row counts before deletion...")
        cursor.execute("""
            SELECT
                'users' as table_name,
                COUNT(*) as row_count
            FROM users
            UNION ALL
            SELECT 'conversation_sessions', COUNT(*) FROM conversation_sessions
            UNION ALL
            SELECT 'conversation_messages', COUNT(*) FROM conversation_messages
            UNION ALL
            SELECT 'agent_states', COUNT(*) FROM agent_states
        """)

        before_counts = cursor.fetchall()
        print("Counts before deletion:")
        for table, count in before_counts:
            print(f"  {table}: {count}")

        # Truncate all tables with CASCADE
        print("Truncating all tables...")
        cursor.execute("""
            TRUNCATE TABLE
                users,
                conversation_sessions,
                conversation_messages,
                agent_states
            CASCADE
        """)

        # Get counts after deletion
        print("Getting row counts after deletion...")
        cursor.execute("""
            SELECT
                'users' as table_name,
                COUNT(*) as row_count
            FROM users
            UNION ALL
            SELECT 'conversation_sessions', COUNT(*) FROM conversation_sessions
            UNION ALL
            SELECT 'conversation_messages', COUNT(*) FROM conversation_messages
            UNION ALL
            SELECT 'agent_states', COUNT(*) FROM agent_states
        """)

        after_counts = cursor.fetchall()
        print("Counts after deletion:")
        for table, count in after_counts:
            print(f"  {table}: {count}")

        # Commit transaction
        conn.commit()
        print("Transaction committed successfully")

        # Vacuum tables
        print("Vacuuming tables...")
        conn.autocommit = True  # VACUUM can't run in transaction
        cursor.execute("VACUUM ANALYZE users")
        cursor.execute("VACUUM ANALYZE conversation_sessions")
        cursor.execute("VACUUM ANALYZE conversation_messages")
        cursor.execute("VACUUM ANALYZE agent_states")
        print("Vacuum completed")

        cursor.close()
        conn.close()

        result = {
            'message': 'All tables cleared successfully',
            'before': dict(before_counts),
            'after': dict(after_counts)
        }

        print(f"Result: {result}")

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        if 'conn' in locals():
            try:
                conn.rollback()
                conn.close()
            except:
                pass

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


if __name__ == '__main__':
    # For local testing
    os.environ['DATABASE_URL'] = 'postgresql://postgres:password@localhost:5432/finance_a2a'
    result = lambda_handler({}, {})
    print(json.dumps(result, indent=2))
