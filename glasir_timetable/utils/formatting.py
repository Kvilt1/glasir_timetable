#!/usr/bin/env python3
"""
Utility functions for formatting and date handling.
"""
import re
from glasir_timetable.utils.date_utils import convert_date_format, to_iso_date, normalize_dates, parse_time_range

def format_date(date_str, year):
    """Format date from DD/MM to YYYY-MM-DD"""
    if not date_str:
        return ""
    
    # Use the consolidated date utilities for conversion
    iso_date = to_iso_date(date_str, year)
    return iso_date if iso_date else date_str

def format_academic_year(year_code):
    """
    Parse year code like '2425' into '2024-2025'
    """
    if len(year_code) == 4:
        return f"20{year_code[:2]}-20{year_code[2:]}"
    return year_code  # Return as is if format is unexpected

def get_timeslot_info(start_col_index):
    """
    Maps the starting column index of a lesson TD to its time slot.
    """
    # Column indices are 0-based in this calculation
    if 2 <= start_col_index <= 25:
        return {"slot": "1", "time": "08:10-09:40"}
    elif 26 <= start_col_index <= 50:
        return {"slot": "2", "time": "10:05-11:35"}
    elif 51 <= start_col_index <= 71:
        return {"slot": "3", "time": "12:10-13:40"}
    elif 72 <= start_col_index <= 90:
        return {"slot": "4", "time": "13:55-15:25"}
    elif 91 <= start_col_index <= 111:
        return {"slot": "5", "time": "15:30-17:00"}
    elif 112 <= start_col_index <= 131:
        return {"slot": "6", "time": "17:15-18:45"}
    else:
        return {"slot": "N/A", "time": "N/A"}  # Fallback

def normalize_room_format(teacher, room, class_code=None):
    """
    Normalize room format to match expected output.
    """
    from glasir_timetable.constants import ROOM_FORMAT_MAPPING
    
    # Create the default format
    default_format = f"{teacher} {room}"
    
    # Check if we have a special mapping for this room
    if default_format in ROOM_FORMAT_MAPPING:
        return ROOM_FORMAT_MAPPING[default_format]
    
    # If not, apply some general formatting rules
    if "st." in room:
        # For rooms with "st.", try to format like "Teacher St. Room"
        return f"{teacher} {room.replace('st.', 'St.')}"
    
    return default_format 

def normalize_week_number(week_num):
    """
    Normalize week numbers to standard 1-53 range.
    
    Args:
        week_num (int): The week number to normalize
        
    Returns:
        int: Normalized week number
    """
    from glasir_timetable import logger
    
    if isinstance(week_num, str):
        try:
            week_num = int(week_num)
        except ValueError:
            logger.warning(f"Could not convert week number '{week_num}' to integer, using as is")
            return week_num
    
    if week_num > 53:  # Standard weeks are 1-53
        # Extract the actual week number by taking the last digit(s)
        if week_num < 100:
            # For numbers like 67, 78, etc.
            normalized_week = week_num % 10
        else:
            # For larger numbers, take the last two digits and then mod 53
            normalized_week = week_num % 100
            if normalized_week > 53:
                normalized_week = normalized_week % 10
        
        logger.info(f"Normalized week number from {week_num} to {normalized_week}")
        return normalized_week
    
    return week_num

def generate_week_filename(year, week_num, start_date, end_date):
    """
    Generate a consistent filename for the week.
    
    Args:
        year (int): The year
        week_num (int): The week number
        start_date (str): The start date
        end_date (str): The end date
        
    Returns:
        str: Formatted filename
    """
    from glasir_timetable import logger
    
    # For weeks that span across two years (like Week 1), prioritize the end date year
    # This aligns with the requirement that cross-year weeks should be filed under the second year
    if start_date and end_date:
        # Extract years from dates
        start_year = None
        end_year = None
        
        if '.' in start_date:
            parts = start_date.split('.')
            if len(parts) > 0:
                try:
                    start_year = int(parts[0])
                except ValueError:
                    start_year = year
        else:
            start_year = year
            
        if '.' in end_date:
            parts = end_date.split('.')
            if len(parts) > 0:
                try:
                    end_year = int(parts[0])
                except ValueError:
                    end_year = year
        else:
            end_year = year
        
        # If the start and end years are different, ALWAYS use the end year for the filename
        # This ensures cross-year weeks appear under the second year
        if start_year and end_year and start_year != end_year:
            logger.debug(f"Cross-year week: start_year={start_year}, end_year={end_year}, using end_year")
            return f"{end_year} Vika {week_num} - {start_date}-{end_date}.json"
        elif start_year:
            # Use start_year if both are the same or end_year is missing
            return f"{start_year} Vika {week_num} - {start_date}-{end_date}.json"
    
    # Fallback to the provided year
    return f"{year} Vika {week_num} - {start_date}-{end_date}.json"

def to_camel_case(snake_str):
    """
    Convert a snake_case or regular string to camelCase.
    
    Args:
        snake_str (str): The string to convert
        
    Returns:
        str: The camelCase version of the string
    """
    # First, handle strings that may have spaces
    components = snake_str.replace('_', ' ').split(' ')
    # First word lowercase, all others capitalized
    return components[0].lower() + ''.join(x.title() for x in components[1:])

def convert_keys_to_camel_case(data):
    """
    Convert all dictionary keys from snake_case or other formats to camelCase.
    
    Args:
        data: The data to convert (can be a dict or a list of dicts)
        
    Returns:
        The data with all dict keys converted to camelCase
    """
    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            # Convert current key
            new_key = to_camel_case(key)
            # Recursively convert any nested structures
            if isinstance(value, (dict, list)):
                new_dict[new_key] = convert_keys_to_camel_case(value)
            else:
                new_dict[new_key] = value
        return new_dict
    elif isinstance(data, list):
        return [convert_keys_to_camel_case(item) for item in data]
    else:
        return data

def format_iso_date(date_str, year=None):
    """
    Format a date string to ISO 8601 format (YYYY-MM-DD).
    Uses the to_iso_date function from date_utils.
    
    Args:
        date_str (str): The date string to format
        year (int, optional): The year to use if not in the date string
        
    Returns:
        str: Date in ISO 8601 format or original string if parsing fails
    """
    iso_date = to_iso_date(date_str, year)
    if iso_date:
        return iso_date
    return date_str