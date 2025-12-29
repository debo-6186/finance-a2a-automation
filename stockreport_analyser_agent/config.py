"""
Configuration management for Host Agent.
Handles environment-based settings for local vs production deployment.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration class with common settings."""

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "local")  # 'local' or 'production'

    # Google API Configuration
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_GENAI_USE_VERTEXAI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

    # Firebase Configuration
    FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "warm-rookery-461602-i8")
    FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    # Host Agent Configuration
    HOST_AGENT_PORT = int(os.getenv("HOST_AGENT_PORT", "10001"))
    STOCK_ANALYSER_AGENT_URL = os.getenv("STOCK_ANALYSER_AGENT_URL", "http://localhost:10002")
    STOCK_REPORT_ANALYSER_AGENT_URL = os.getenv("STOCK_REPORT_ANALYSER_AGENT_URL", "http://localhost:10003")

    # Free user message limit
    FREE_USER_MESSAGE_LIMIT = int(os.getenv("FREE_USER_MESSAGE_LIMIT", "30"))

    @classmethod
    def is_local(cls):
        """Check if running in local environment."""
        return cls.ENVIRONMENT.lower() == "local"

    @classmethod
    def is_production(cls):
        """Check if running in production environment."""
        return cls.ENVIRONMENT.lower() == "production"


class LocalConfig(Config):
    """Configuration for local development."""

    # Database Configuration - Local PostgreSQL
    DATABASE_URL = os.getenv(
        "DATABASE_URL_LOCAL",
        "postgresql://debojyotichakraborty@localhost:5432/finance_a2a"
    )

    # File Storage Configuration - Local filesystem
    STORAGE_TYPE = "local"
    LOCAL_STORAGE_PATH = os.getenv(
        "LOCAL_STORAGE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "local_storage", "portfolios")
    )

    # S3 Configuration (not used in local)
    S3_BUCKET_NAME = None

    @classmethod
    def get_storage_config(cls):
        """Get storage configuration for local environment."""
        return {
            "type": cls.STORAGE_TYPE,
            "path": cls.LOCAL_STORAGE_PATH
        }


class ProductionConfig(Config):
    """Configuration for production deployment."""

    # Database Configuration - AWS RDS
    DATABASE_URL = os.getenv(
        "DATABASE_URL_PRODUCTION",
        os.getenv("DATABASE_URL")  # Fallback to DATABASE_URL if specific one not set
    )

    # File Storage Configuration - AWS S3
    STORAGE_TYPE = "s3"
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "finance-a2a-portfolio-statements")

    # Local storage path (not used in production)
    LOCAL_STORAGE_PATH = None

    @classmethod
    def get_storage_config(cls):
        """Get storage configuration for production environment."""
        return {
            "type": cls.STORAGE_TYPE,
            "bucket_name": cls.S3_BUCKET_NAME
        }


def get_config():
    """
    Get the appropriate configuration based on the ENVIRONMENT variable.

    Returns:
        LocalConfig or ProductionConfig instance
    """
    env = os.getenv("ENVIRONMENT", "local").lower()

    if env == "production":
        return ProductionConfig
    else:
        return LocalConfig


# Export the current configuration
current_config = get_config()
