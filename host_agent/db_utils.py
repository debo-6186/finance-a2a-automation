"""
Database utility for direct SQL queries and modifications.
Provides simple interface for querying and modifying Postgres tables.
"""

import os
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

# Get database URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://debojyotichakraborty@localhost:5432/finance_a2a")

# Create engine
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_connection():
    """
    Context manager for database connection.

    Usage:
        with get_db_connection() as db:
            result = db.execute(...)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


class DBQuery:
    """Utility class for database queries and modifications."""

    @staticmethod
    def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dictionaries.

        Args:
            query: SQL query string (use :param_name for parameters)
            params: Dictionary of parameters for the query

        Returns:
            List of dictionaries containing query results

        Example:
            results = DBQuery.execute_query(
                "SELECT * FROM users WHERE email = :email",
                {"email": "test@example.com"}
            )
        """
        with get_db_connection() as db:
            try:
                result = db.execute(text(query), params or {})
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
            except SQLAlchemyError as e:
                logger.error(f"Query execution error: {e}")
                raise

    @staticmethod
    def execute_update(query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Execute an INSERT, UPDATE, or DELETE query.

        Args:
            query: SQL query string (use :param_name for parameters)
            params: Dictionary of parameters for the query

        Returns:
            Number of rows affected

        Example:
            rows_affected = DBQuery.execute_update(
                "UPDATE users SET paid_user = :paid WHERE id = :user_id",
                {"paid": True, "user_id": "123"}
            )
        """
        with get_db_connection() as db:
            try:
                result = db.execute(text(query), params or {})
                db.commit()
                return result.rowcount
            except SQLAlchemyError as e:
                logger.error(f"Update execution error: {e}")
                raise

    @staticmethod
    def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a table.

        Args:
            table_name: Name of the table

        Returns:
            List of column information dictionaries
        """
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """
        return DBQuery.execute_query(query, {"table_name": table_name})

    @staticmethod
    def list_tables() -> List[str]:
        """
        List all tables in the database.

        Returns:
            List of table names
        """
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        results = DBQuery.execute_query(query)
        return [row['table_name'] for row in results]

    @staticmethod
    def get_all_records(table_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all records from a table (with limit).

        Args:
            table_name: Name of the table
            limit: Maximum number of records to return (default: 100)

        Returns:
            List of records as dictionaries
        """
        query = f"SELECT * FROM {table_name} LIMIT :limit"
        return DBQuery.execute_query(query, {"limit": limit})

    @staticmethod
    def insert_record(table_name: str, data: Dict[str, Any]) -> int:
        """
        Insert a record into a table.

        Args:
            table_name: Name of the table
            data: Dictionary of column:value pairs

        Returns:
            Number of rows inserted

        Example:
            DBQuery.insert_record("users", {
                "id": "123",
                "email": "test@example.com",
                "paid_user": False
            })
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f":{key}" for key in data.keys()])
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return DBQuery.execute_update(query, data)

    @staticmethod
    def update_record(table_name: str, data: Dict[str, Any], where_clause: str,
                     where_params: Optional[Dict[str, Any]] = None) -> int:
        """
        Update records in a table.

        Args:
            table_name: Name of the table
            data: Dictionary of column:value pairs to update
            where_clause: WHERE clause (without WHERE keyword, use :param for values)
            where_params: Dictionary of parameters for WHERE clause

        Returns:
            Number of rows updated

        Example:
            DBQuery.update_record(
                "users",
                {"paid_user": True},
                "id = :user_id",
                {"user_id": "123"}
            )
        """
        set_clause = ", ".join([f"{key} = :{key}" for key in data.keys()])
        query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"

        # Merge data and where_params
        all_params = {**data, **(where_params or {})}
        return DBQuery.execute_update(query, all_params)

    @staticmethod
    def delete_record(table_name: str, where_clause: str,
                     where_params: Optional[Dict[str, Any]] = None) -> int:
        """
        Delete records from a table.

        Args:
            table_name: Name of the table
            where_clause: WHERE clause (without WHERE keyword, use :param for values)
            where_params: Dictionary of parameters for WHERE clause

        Returns:
            Number of rows deleted

        Example:
            DBQuery.delete_record(
                "users",
                "id = :user_id",
                {"user_id": "123"}
            )
        """
        query = f"DELETE FROM {table_name} WHERE {where_clause}"
        return DBQuery.execute_update(query, where_params or {})


# Example usage functions
def example_queries():
    """Example usage of the DBQuery utility."""

    # List all tables
    tables = DBQuery.list_tables()
    print(f"Tables: {tables}")

    # Get schema for a table
    schema = DBQuery.get_table_schema("users")
    print(f"Users table schema: {schema}")

    # Get all users
    users = DBQuery.get_all_records("users")
    print(f"Users: {users}")

    # Query with parameters
    paid_users = DBQuery.execute_query(
        "SELECT * FROM users WHERE paid_user = :paid",
        {"paid": True}
    )
    print(f"Paid users: {paid_users}")

    # Update a record
    rows_updated = DBQuery.update_record(
        "users",
        {"paid_user": True},
        "email = :email",
        {"email": "test@example.com"}
    )
    print(f"Updated {rows_updated} rows")

    # Insert a record
    # rows_inserted = DBQuery.insert_record("users", {
    #     "id": "test_123",
    #     "email": "newuser@example.com",
    #     "paid_user": False
    # })

    # Delete a record
    # rows_deleted = DBQuery.delete_record(
    #     "users",
    #     "id = :user_id",
    #     {"user_id": "test_123"}
    # )


if __name__ == "__main__":
    # Run examples
    example_queries()
