import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

"""
Centralized Logger Module for Stock Analyser Agent

This module implements a singleton pattern for logging setup to ensure that:
1. Logging is only initialized once, regardless of how many times setup_logging() is called
2. All modules use the same log file and configuration
3. Uses a single rotating log file instead of multiple timestamped files

Usage:
    from logger import setup_logging, get_logger
    setup_logging()  # Only needs to be called once
    logger = get_logger(__name__)
    logger.info("Your log message")
"""

# Global variable to store the current log file path
_current_log_file_path = None
_logging_initialized = False

def setup_logging():
    """Setup logging configuration to save logs to a single rotating file (singleton pattern)"""
    global _current_log_file_path, _logging_initialized
    
    # If logging is already initialized, return the existing log file path
    if _logging_initialized and _current_log_file_path:
        return _current_log_file_path
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Use a fixed log filename for rotation
    log_filename = "stock_analyser.log"
    log_filepath = os.path.join(log_dir, log_filename)
    
    # Configure rotating file handler
    # maxBytes=10MB, backupCount=5 (keeps 5 backup files)
    rotating_handler = RotatingFileHandler(
        log_filepath,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    # Configure formatter with custom timestamp format (dd-mm-yyyy hh:mm:ss)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%d-%m-%Y %H:%M:%S'
    )
    rotating_handler.setFormatter(formatter)
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add our handlers
    root_logger.addHandler(rotating_handler)
    root_logger.addHandler(console_handler)
    
    # Store the log file path globally and mark as initialized
    _current_log_file_path = log_filepath
    _logging_initialized = True
    
    return log_filepath

def get_logger(name: str = None):
    """Get a logger instance with the specified name"""
    if name is None:
        name = __name__
    return logging.getLogger(name)

def is_logging_initialized():
    """Check if logging has been initialized"""
    global _logging_initialized
    return _logging_initialized

def get_log_file_path():
    """Returns the current log file path where logs are being saved"""
    global _current_log_file_path
    if _current_log_file_path:
        return f"Log file is saved at: {_current_log_file_path}"
    else:
        return "Logging not initialized yet. Call setup_logging() first." 