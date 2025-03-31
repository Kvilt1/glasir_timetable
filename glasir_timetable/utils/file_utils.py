#!/usr/bin/env python3
"""
File utility functions for the Glasir Timetable application.
"""
import os
import json
from typing import Any, Dict, Optional, Union

from glasir_timetable import logger
from glasir_timetable.models import TimetableData
from glasir_timetable.utils.model_adapters import timetable_data_to_dict

def save_json_data(
    data: Union[Dict[str, Any], TimetableData],
    output_path: str,
    create_dirs: bool = True,
    indent: int = 2
) -> bool:
    """
    Save data to a JSON file with consistent settings.
    
    Args:
        data: The data to save (dict or TimetableData model)
        output_path: Path to save the JSON file
        create_dirs: Whether to create parent directories if they don't exist
        indent: Indentation level for the JSON file
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        # Create parent directories if they don't exist
        if create_dirs:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
        # Convert model to dictionary if needed
        data_to_save = data
        if isinstance(data, TimetableData):
            data_to_save = timetable_data_to_dict(data)
            logger.info(f"Converted model to dictionary for serialization")
        
        # Save data to JSON file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=indent)
            
        logger.info(f"Data saved to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving data to {output_path}: {e}")
        return False 