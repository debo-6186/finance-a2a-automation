"""
Database migration runner for the Host Agent.
Runs SQL migration files in order.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import database module
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine, init_db
from sqlalchemy import text
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(migration_file: str):
    """
    Run a single migration file.

    Args:
        migration_file: Path to the SQL migration file
    """
    logger.info(f"Running migration: {migration_file}")

    try:
        # Read the migration file
        with open(migration_file, 'r') as f:
            sql_content = f.read()

        # Execute the migration
        with engine.connect() as conn:
            # Split by semicolons and execute each statement
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]

            for statement in statements:
                # Remove comment lines from the beginning of statements
                lines = statement.split('\n')
                non_comment_lines = [line for line in lines if not line.strip().startswith('--')]
                clean_statement = '\n'.join(non_comment_lines).strip()

                # Skip empty statements
                if not clean_statement:
                    continue

                logger.info(f"Executing statement: {clean_statement[:100]}...")
                try:
                    conn.execute(text(clean_statement))
                    conn.commit()
                except Exception as stmt_error:
                    # Check if error is about column already existing
                    error_msg = str(stmt_error).lower()
                    if 'already exists' in error_msg or 'duplicate column' in error_msg:
                        logger.warning(f"Column/object already exists, skipping: {stmt_error}")
                        conn.rollback()
                        continue
                    else:
                        # Re-raise other errors
                        raise

        logger.info(f"Successfully completed migration: {migration_file}")
        return True

    except Exception as e:
        logger.error(f"Error running migration {migration_file}: {e}")
        return False


def run_all_migrations():
    """Run all migration files in order."""
    migrations_dir = Path(__file__).parent

    # Get all .sql files and sort them
    migration_files = sorted(migrations_dir.glob('*.sql'))

    if not migration_files:
        logger.info("No migration files found")
        return

    logger.info(f"Found {len(migration_files)} migration file(s)")

    success_count = 0
    failed_count = 0

    for migration_file in migration_files:
        if run_migration(str(migration_file)):
            success_count += 1
        else:
            failed_count += 1
            logger.warning(f"Stopping migrations due to failure in {migration_file}")
            break

    logger.info(f"Migration summary: {success_count} successful, {failed_count} failed")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    logger.info("Initializing database schema...")
    try:
        init_db()
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        sys.exit(1)

    logger.info("Starting database migrations...")
    run_all_migrations()
    logger.info("Database migrations completed")
