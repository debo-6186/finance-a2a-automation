#!/usr/bin/env python3
"""
Database initialization script for the Host Agent.
Creates the PostgreSQL database and tables for session management.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the host_agent directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, engine, Base
from sqlalchemy.exc import SQLAlchemyError

# Load environment variables
load_dotenv()

# Set up loggingapi
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_database():
    """Create the database if it doesn't exist."""
    try:
        # Extract database name from DATABASE_URL
        database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/finance_a2a")
        
        # Parse the URL to get database name
        if "postgresql://" in database_url:
            db_name = database_url.split("/")[-1]
        else:
            db_name = "finance_a2a"
        
        # Create a connection to PostgreSQL server (without specifying database)
        server_url = database_url.rsplit("/", 1)[0] + "/postgres"
        temp_engine = engine.create_engine(server_url)
        
        with temp_engine.connect() as conn:
            # Check if database exists
            result = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not result.fetchone():
                # Create database
                conn.execute(f"CREATE DATABASE {db_name}")
                logger.info(f"Created database: {db_name}")
            else:
                logger.info(f"Database {db_name} already exists")
        
        temp_engine.dispose()
        
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        logger.info("You may need to create the database manually or check PostgreSQL connection")
        return False
    
    return True


def main():
    """Main function to initialize the database."""
    logger.info("Starting database initialization...")
    
    # Check if DATABASE_URL is set
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set, using default: postgresql://postgres:password@localhost:5432/finance_a2a")
    
    try:
        # Try to create database first
        if create_database():
            logger.info("Database created/verified successfully")
        
        # Initialize tables
        logger.info("Creating database tables...")
        init_db()
        logger.info("Database initialization completed successfully!")
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute("SELECT version()")
            version = result.fetchone()[0]
            logger.info(f"Connected to PostgreSQL: {version}")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        logger.error("Please check your PostgreSQL connection and credentials")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
