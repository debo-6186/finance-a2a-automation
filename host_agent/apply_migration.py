#!/usr/bin/env python3
"""
Apply database migration to fix foreign key constraints.
This script adds CASCADE UPDATE to all foreign key constraints.
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://debojyotichakraborty@localhost:5432/finance_a2a")

def parse_database_url(url):
    """Parse PostgreSQL database URL."""
    # Remove postgresql:// prefix
    url = url.replace("postgresql://", "")

    # Parse user@host:port/database format
    if "@" in url:
        user_part, rest = url.split("@", 1)
        host_part, db = rest.split("/", 1)

        if ":" in host_part:
            host, port = host_part.split(":", 1)
        else:
            host = host_part
            port = "5432"

        return {
            "user": user_part,
            "host": host,
            "port": port,
            "database": db
        }
    else:
        raise ValueError("Invalid database URL format")


def apply_migration():
    """Apply the migration to fix foreign key constraints."""

    # Parse database URL
    db_params = parse_database_url(DATABASE_URL)

    print(f"Connecting to database: {db_params['database']} on {db_params['host']}:{db_params['port']}")

    try:
        # Connect to database
        conn = psycopg2.connect(**db_params)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Connected to database successfully")

        # Read migration SQL file
        migration_file = os.path.join(os.path.dirname(__file__), "fix_foreign_key_constraints.sql")
        with open(migration_file, 'r') as f:
            migration_sql = f.read()

        print("\nApplying migration...")
        print("=" * 60)

        # Execute migration
        cursor.execute(migration_sql)

        print("Migration executed successfully")

        # Commit changes
        conn.commit()
        print("Migration committed successfully")

        print("=" * 60)
        print("\nForeign key constraints have been updated with CASCADE UPDATE and CASCADE DELETE")
        print("User ID updates will now cascade to all related tables")

        cursor.close()
        conn.close()

        print("\nDatabase migration completed successfully!")
        return True

    except psycopg2.Error as e:
        print(f"\nError applying migration: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        if 'conn' in locals():
            conn.close()
        return False


if __name__ == "__main__":
    print("Database Migration Script")
    print("=" * 60)
    print("This will update foreign key constraints to support CASCADE UPDATE")
    print("=" * 60)
    print()

    # Confirm before proceeding
    response = input("Do you want to proceed? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Migration cancelled")
        sys.exit(0)

    success = apply_migration()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)
