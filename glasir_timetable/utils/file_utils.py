#!/usr/bin/env python3
"""
File utility functions for the Glasir Timetable application.
"""
import os
import json
from typing import Any, Dict, Optional, Union

from glasir_timetable import logger

def save_json_data(
    data: Any,
    output_path: str,
    format_type: Optional[str] = None,
    create_dirs: bool = True,
    indent: int = 2
) -> bool:
    """
    Save data to a JSON file with consistent settings.
    
    Args:
        data: The data to save
        output_path: Path to save the JSON file
        format_type: Optional format type for timetable data ('event-centric', 'traditional', 'dual')
        create_dirs: Whether to create parent directories if they don't exist
        indent: Indentation level for the JSON file
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        # Create parent directories if they don't exist
        if create_dirs:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
        # Format selection for timetable data
        data_to_save = data
        if format_type and format_type != "dual":
            # Import here to avoid circular imports
            from glasir_timetable.main import select_format
            # Only apply format selection if it appears to be timetable data
            try:
                data_to_save = select_format(data, format_type)
                logger.info(f"Using {format_type} format")
            except (AttributeError, TypeError, KeyError):
                # If format selection fails, use the original data
                logger.warning(f"Format selection failed, saving original data")
                data_to_save = data
        
        # Save data to JSON file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=indent)
            
        logger.info(f"Data saved to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving data to {output_path}: {e}")
        return False 