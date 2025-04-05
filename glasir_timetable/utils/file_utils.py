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

def save_raw_response(
    content: str,
    directory: str,
    filename: str,
    request_url: Optional[str] = None,
    request_method: Optional[str] = None,
    request_headers: Optional[Dict[str, Any]] = None,
    request_payload: Optional[Union[Dict[str, Any], str]] = None
) -> bool:
    """
    Save raw API response content (and optionally request details) to a file.
    
    Args:
        content: Raw text content from the API response
        directory: Directory to save the file in
        filename: Filename to use for the saved file
        request_url: Request URL (optional)
        request_method: HTTP method (optional)
        request_headers: Request headers (optional)
        request_payload: Request payload/body (optional)
        
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        # Import global config and counter
        from glasir_timetable import raw_response_config, raw_response_counter

        # Prefix filename with call order number
        prefix = f"{raw_response_counter}_"
        if not filename.startswith(prefix):
            filename = prefix + filename

        # Increment the global counter
        import glasir_timetable
        glasir_timetable.raw_response_counter += 1
        # Ensure the target directory exists
        os.makedirs(directory, exist_ok=True)
        
        from glasir_timetable import raw_response_config
        
        save_request_details = raw_response_config.get("save_request_details", False)
        include_request = save_request_details and request_url is not None
        
        # If including request info, save as JSON object
        if include_request:
            # Change extension to .json if not already
            if not filename.endswith(".json"):
                filename = filename.rsplit(".", 1)[0] + ".json" if "." in filename else filename + ".json"
            file_path = os.path.join(directory, filename)
            
            data = {
                "request": {
                    "url": request_url,
                    "method": request_method,
                    "headers": request_headers,
                    "payload": request_payload
                },
                "response": content
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Raw request+response saved to {file_path}")
            return True
        else:
            # Save plain response content as before
            file_path = os.path.join(directory, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Raw response saved to {file_path}")
            return True
        
    except Exception as e:
        logger.error(f"Error saving raw response to {file_path}: {e}")
        return False