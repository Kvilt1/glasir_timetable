#!/usr/bin/env python3
"""
Converter utility to transform existing timetable JSON files to the new format.
"""
import os
import json
import argparse
import sys
import re
from pathlib import Path
import logging
from datetime import datetime

# Add parent directory to path if running as script
parent_dir = Path(__file__).resolve().parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Now import the formatting functions
from glasir_timetable.utils.formatting import (
    convert_keys_to_camel_case,
    format_iso_date,
    parse_time_range
)

from glasir_timetable import logger
from glasir_timetable.utils.file_utils import save_json_data

# Configure logger
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("converter")

def convert_date_to_iso(date_str):
    """
    Convert date from "DD/MM-YYYY" format to ISO 8601 "YYYY-MM-DD" format.
    
    Args:
        date_str (str): Date string in DD/MM-YYYY format
        
    Returns:
        str: Date in ISO 8601 format
    """
    if not date_str:
        return date_str
    
    # Try to handle DD/MM-YYYY format (like "24/3-2025")
    pattern = re.compile(r'(\d{1,2})/(\d{1,2})-(\d{4})')
    match = pattern.match(date_str)
    
    if match:
        day, month, year = match.groups()
        # Format with leading zeros
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # Fallback to other date formats
    try:
        # Try using date_utils directly
        from glasir_timetable.utils.date_utils import parse_date
        
        # Try to parse the date
        parsed_date = parse_date(date_str)
        if parsed_date:
            year = parsed_date['year']
            month = parsed_date['month']
            day = parsed_date['day']
            return f"{year}-{month}-{day}"
    except Exception as e:
        logger.debug(f"Failed to parse date using date_utils: {e}")
    
    # Return original if we can't convert it
    logger.warning(f"Could not convert date format: {date_str}")
    return date_str

def convert_to_new_format(json_data):
    """
    Convert traditional timetable format to the new event-centric format.
    
    Args:
        json_data (dict): Timetable data in traditional format
        
    Returns:
        dict: Timetable data in new event-centric format
    """
    # Extract student info
    student_info = json_data.get("student_info", {})
    
    # Convert student_info to camelCase
    student_info_camel = {
        "studentName": student_info.get("student_name"),
        "class": student_info.get("class")
    }
    
    # Extract week key and data
    week_key = None
    week_data = None
    for key, value in json_data.items():
        if key != "student_info" and isinstance(value, dict):
            week_key = key
            week_data = value
            break
    
    if not week_key or not week_data:
        raise ValueError("Could not find week data in JSON")
    
    # Parse week info from the key
    # Format is typically "Week X: YYYY.MM.DD to YYYY.MM.DD"
    week_info = {}
    try:
        parts = week_key.split(":")
        if len(parts) == 2:
            week_num = parts[0].replace("Week", "").strip()
            week_info["weekNum"] = int(week_num)
            
            date_range = parts[1].strip()
            date_parts = date_range.split(" to ")
            
            if len(date_parts) == 2:
                start_date = date_parts[0].strip()
                end_date = date_parts[1].strip()
                
                # Try to parse dates
                try:
                    start_dt = datetime.strptime(start_date, "%Y.%m.%d")
                    end_dt = datetime.strptime(end_date, "%Y.%m.%d")
                    
                    week_info["startDate"] = start_date
                    week_info["endDate"] = end_date
                    week_info["year"] = start_dt.year
                except ValueError:
                    logger.warning(f"Could not parse dates from week key: {week_key}")
            
    except Exception as e:
        logger.warning(f"Error parsing week info: {e}")
    
    # Create flattened events list
    all_events = []
    
    # Process each day's classes
    for day, classes in week_data.items():
        for class_info in classes:
            # Create a new event object with camelCase keys and standardized date format
            event = {}
            
            # Map known keys to their camelCase equivalents 
            # and apply data transformations where needed
            if "name" in class_info:
                event["title"] = class_info["name"]
            elif "Name" in class_info:
                event["title"] = class_info["Name"]
                
            if "level" in class_info:
                event["level"] = class_info["level"]
            elif "Level" in class_info:
                event["level"] = class_info["Level"]
                
            if "Year" in class_info:
                event["year"] = class_info["Year"]
                
            # Add day information
            event["day"] = day
            
            # Convert date to ISO format if possible
            if "date" in class_info:
                date_str = class_info["date"]
                iso_date = convert_date_to_iso(date_str)
                event["date"] = iso_date
                
            # Handle teacher information
            if "Teacher" in class_info:
                event["teacher"] = class_info["Teacher"]
            if "Teacher short" in class_info:
                event["teacherShort"] = class_info["Teacher short"]
                
            # Location
            if "Location" in class_info:
                event["location"] = class_info["Location"]
                
            # Handle time information
            if "Time slot" in class_info:
                event["timeSlot"] = class_info["Time slot"]
                
            if "Time" in class_info:
                time_range = class_info["Time"]
                event["timeRange"] = time_range
                
                # Parse start and end times
                start_time, end_time = parse_time_range(time_range)
                if start_time and end_time:
                    event["startTime"] = start_time
                    event["endTime"] = end_time
                    
            # Handle cancelled status
            if "Cancelled" in class_info:
                event["cancelled"] = class_info["Cancelled"]
                
            # Handle homework/description
            if "Homework" in class_info:
                event["description"] = class_info["Homework"]
                
            # Add exam-specific details if available
            if "exam_subject" in class_info:
                event["examSubject"] = class_info["exam_subject"]
            if "exam_level" in class_info:
                event["examLevel"] = class_info["exam_level"]
            if "exam_type" in class_info:
                event["examType"] = class_info["exam_type"]
                
            # Add to events list
            all_events.append(event)
    
    # Sort events by date and time
    all_events.sort(key=lambda x: (x.get("date", ""), x.get("timeSlot", ""), x.get("startTime", "")))
    
    # Create the new format
    return {
        "studentInfo": student_info_camel,
        "events": all_events,
        "weekInfo": week_info
    }

def convert_to_dual_format(json_data):
    """
    Convert to a format that includes both traditional and event-centric structures.
    
    Args:
        json_data (dict): Timetable data in either format
        
    Returns:
        dict: Timetable data in dual format
    """
    # Check if it's already in the dual format
    if "formatVersion" in json_data and "traditional" in json_data and "eventCentric" in json_data:
        return json_data
    
    # Check if it's in the new event-centric format
    if "events" in json_data and "studentInfo" in json_data:
        # TODO: Implement conversion from event-centric to traditional
        # For now, just return the event-centric format
        return {
            "eventCentric": json_data,
            "formatVersion": 2,
            # Traditional format would need to be reconstructed
            "traditional": {"error": "Conversion from event-centric to traditional not implemented"}
        }
    
    # Assume it's in the traditional format
    # Convert to event-centric
    event_centric = convert_to_new_format(json_data)
    
    # Return both formats
    return {
        "traditional": json_data,
        "eventCentric": event_centric,
        "formatVersion": 2
    }

def convert_file(file_path, output_dir=None, format_type="new", overwrite=False):
    """
    Convert a single JSON file to the new format.
    
    Args:
        file_path (str): Path to the JSON file
        output_dir (str, optional): Directory to save the converted file
        format_type (str): Format type to convert to ('new', 'dual')
        overwrite (bool): Whether to overwrite the original file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Convert to the requested format
        if format_type == "dual":
            converted_data = convert_to_dual_format(json_data)
        else:
            converted_data = convert_to_new_format(json_data)
        
        # Determine output path
        if overwrite:
            output_path = file_path
        elif output_dir:
            # Create the output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Get the filename
            filename = os.path.basename(file_path)
            
            # Create the output path
            output_path = os.path.join(output_dir, filename)
        else:
            # If not overwriting and no output directory specified,
            # add "_new" suffix to the filename
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_new{ext}"
        
        # Save the converted data using utility function
        result = save_json_data(converted_data, output_path, create_dirs=True)
        
        if result:
            logger.info(f"Converted {file_path} → {output_path}")
        return result
    
    except Exception as e:
        logger.error(f"Error converting {file_path}: {e}")
        return False

def convert_directory(directory, output_dir=None, format_type="new", overwrite=False):
    """
    Convert all JSON files in a directory to the new format.
    
    Args:
        directory (str): Directory containing JSON files
        output_dir (str, optional): Directory to save converted files
        format_type (str): Format type to convert to ('new', 'dual')
        overwrite (bool): Whether to overwrite original files
        
    Returns:
        tuple: (success_count, failure_count)
    """
    success_count = 0
    failure_count = 0
    
    # Get all JSON files in the directory
    json_files = list(Path(directory).glob("*.json"))
    logger.info(f"Found {len(json_files)} JSON files in {directory}")
    
    for file_path in json_files:
        result = convert_file(str(file_path), output_dir, format_type, overwrite)
        if result:
            success_count += 1
        else:
            failure_count += 1
    
    return success_count, failure_count

def main():
    """Main entry point for the converter script."""
    parser = argparse.ArgumentParser(description="Convert timetable JSON files to the new format")
    parser.add_argument("--input", required=True, help="Input file or directory")
    parser.add_argument("--output-dir", help="Directory to save converted files")
    parser.add_argument("--format", choices=["new", "dual"], default="new",
                       help="Format to convert to (new=event-centric only, dual=both formats)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite original files")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO",
                       help="Logging level")
    
    args = parser.parse_args()
    
    # Set logging level
    logger.setLevel(getattr(logging, args.log_level))
    
    # Check if input is a file or directory
    input_path = args.input
    output_dir = args.output_dir
    
    if os.path.isfile(input_path):
        logger.info(f"Converting single file: {input_path}")
        success = convert_file(input_path, output_dir, args.format, args.overwrite)
        if success:
            logger.info("Conversion successful")
        else:
            logger.error("Conversion failed")
    
    elif os.path.isdir(input_path):
        logger.info(f"Converting all JSON files in directory: {input_path}")
        success_count, failure_count = convert_directory(input_path, output_dir, args.format, args.overwrite)
        logger.info(f"Conversion complete. Success: {success_count}, Failures: {failure_count}")
    
    else:
        logger.error(f"Input path not found: {input_path}")
        return 1
    
    return 0

if __name__ == "__main__":
    main() 