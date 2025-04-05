#!/usr/bin/env python3
# Package initialization
"""
Glasir Timetable - A tool for extracting timetable data from Glasir's website.

This package uses JavaScript-based navigation by default for faster and more
reliable timetable extraction.
"""

__all__ = [
    "logger",
    "add_error",
    "get_error_summary",
    "clear_errors",
    "update_stats",
    "configure_raw_responses",
]

__version__ = "1.1.0"

import sys
import os
import logging
from pathlib import Path
from collections import defaultdict

# Global error collection with configurable verbosity
error_collection = {
    "homework_errors": [],
    "navigation_errors": [],
    "extraction_errors": [],
    "general_errors": [],
    "javascript_errors": [],
    "console_errors": [],
    "auth_errors": [],
    "resource_errors": []
}

# Global configuration for error handling
error_config = {
    "collect_details": False,  # Whether to collect detailed error information
    "collect_tracebacks": False,  # Whether to collect tracebacks
    "error_limit": 100  # Maximum number of errors to store per category
}

# Global configuration for raw response saving
raw_response_config = {
    "save_enabled": False,
    "directory": "glasir_timetable/raw_responses/",
    "save_request_details": False  # New flag to control saving request info
}

# Explicitly disable raw response saving by default for performance
raw_response_config["save_enabled"] = False

# Global counter for numbering saved raw responses during a script run
raw_response_counter = 1

# Statistics tracking
stats = {
    "total_weeks": 0,
    "processed_weeks": 0,
    "start_time": None,
    "homework_success": 0,
    "homework_failed": 0
}

# Configure logging
def setup_logging(level=logging.INFO):
    """Configure logging for the application"""
    logger = logging.getLogger("glasir_timetable")
    logger.setLevel(level)
    
    # Only add handler if none exist to avoid duplicate logs
    if not logger.handlers:
        # Create a custom handler that uses tqdm.write for output
        class TqdmLoggingHandler(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    from tqdm import tqdm
                    tqdm.write(msg)
                except Exception:
                    self.handleError(record)
        
        console_handler = TqdmLoggingHandler()
        console_handler.setLevel(level)
        
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', 
                                     datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
    
    return logger

# Set up the logger when the module is imported
logger = setup_logging() 

def add_error(error_type, message, details=None):
    """Add an error to the error collection with respect to configuration"""
    # Ensure the error type exists in the collection
    if error_type not in error_collection:
        error_collection[error_type] = []
    
    # Check if we've reached the error limit for this category
    if len(error_collection[error_type]) >= error_config["error_limit"]:
        return
    
    error_data = {"message": message}
    
    # Only include details if configured to do so
    if error_config["collect_details"] and details:
        # Filter out tracebacks if not configured to collect them
        if not error_config["collect_tracebacks"] and details.get("traceback"):
            details = {k: v for k, v in details.items() if k != "traceback"}
        error_data["details"] = details
        
    error_collection[error_type].append(error_data)

def get_error_summary():
    """Get a summary of all errors"""
    total_errors = sum(len(errors) for errors in error_collection.values())
    return {
        "total": total_errors,
        "by_type": {k: len(v) for k, v in error_collection.items() if len(v) > 0}
    }

def clear_errors():
    """Clear all errors"""
    for key in error_collection:
        error_collection[key] = []

def update_stats(key, value=1, increment=True):
    """Update statistics tracking"""
    if increment and key in stats:
        stats[key] += value
    else:
        stats[key] = value 

def configure_raw_responses(save: bool, directory: str = None, save_request_details: bool = False):
    """Configure the raw response saving functionality.
    
    Args:
        save: Whether to save raw responses
        directory: Directory to save raw responses to (if None, uses default)
        save_request_details: Whether to save request details along with responses
    """
    global raw_response_config
    raw_response_config["save_enabled"] = save
    raw_response_config["save_request_details"] = save_request_details
    if directory is not None:
        raw_response_config["directory"] = directory
    
    # Create the directory if it doesn't exist and saving is enabled
    if save and directory is not None:
        import os
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Raw responses will be saved to: {directory}")
    elif save:
        import os
        os.makedirs(raw_response_config["directory"], exist_ok=True)
        logger.info(f"Raw responses will be saved to: {raw_response_config['directory']}")
    else:
        logger.info("Raw response saving is disabled")
