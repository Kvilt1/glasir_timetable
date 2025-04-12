#!/usr/bin/env python3
"""
Utility functions for handling date formats in the Glasir Timetable project.
Provides consistent date parsing and formatting across the application.
"""
import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional, Tuple

# Pre-compile regex patterns for better performance
PERIOD_DATE_FULL = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
PERIOD_DATE_SHORT = re.compile(r'(\d{1,2})\.(\d{1,2})')
HYPHEN_DATE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')
SLASH_DATE_SHORT = re.compile(r'(\d{1,2})/(\d{1,2})')
SLASH_DATE_WITH_YEAR = re.compile(r'(\d{1,2})/(\d{1,2})-(\d{4})')

# def detect_date_format(date_str): # Removed as unused
#     """
#     Detect the format of a date string.
#     ... (rest of docstring and code) ...
#     """
#     pass # Function removed
@lru_cache(maxsize=256)
def parse_date(date_str: str, year: Optional[int] = None) -> Optional[Dict[str, str]]:
    """
    Parse a date string in various formats and return standardized components.
    Cached for better performance with frequently used dates.
    
    Args:
        date_str (str): The date string to parse
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        Optional[Dict[str, str]]: Dictionary with 'year', 'month', 'day' keys,
                                  or None if parsing fails.
    """
    if not date_str:
        return None
        
    # If we don't have a year, use current year
    if year is None:
        year = datetime.now().year
        
    # Handle period format (DD.MM.YYYY or DD.MM)
    match = PERIOD_DATE_FULL.match(date_str)
    if match:
        day, month, year = match.groups()
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': year
        }
    
    match = PERIOD_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups()
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': str(year)
        }
    
    # Handle hyphen format (YYYY-MM-DD)
    match = HYPHEN_DATE.match(date_str)
    if match:
        year, month, day = match.groups()
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': year
        }
    
    # Handle slash format (DD/MM)
    match = SLASH_DATE_SHORT.match(date_str)
    if match:
        # Assume DD/MM format (European)
        day, month = match.groups()
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': str(year)
        }
    
    # Handle DD/MM-YYYY format (like 24/3-2025)
    match = SLASH_DATE_WITH_YEAR.match(date_str)
    if match:
        day, month, year = match.groups()
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': year
        }
    
    # If we got here, we couldn't parse the date
    return None

def format_date(date_dict: Optional[Dict[str, str]], output_format: str = 'hyphen') -> Optional[str]:
    """
    Format a date dictionary to a specific output format.
    
    Args:
        date_dict (dict): Dictionary with 'year', 'month', 'day' keys
        output_format (str): The desired output format ('hyphen', 'period', 'slash', 'filename', 'iso')
        
    Returns:
        Optional[str]: Formatted date string or None if input is invalid.
    """
    if not date_dict:
        return None
        
    # Ensure all required keys exist
    required_keys = ['year', 'month', 'day']
    if not all(key in date_dict for key in required_keys):
        return None
        
    year = date_dict['year']
    month = date_dict['month']
    day = date_dict['day']
    
    if output_format == 'hyphen':
        return f"{year}-{month}-{day}"
    elif output_format == 'period':
        return f"{day}.{month}.{year}"
    elif output_format == 'slash':
        return f"{day}/{month}/{year}"
    elif output_format == 'filename':
        return f"{month}.{day}"  # Used in filename formatting: MM.DD
    elif output_format == 'iso':
        return f"{year}-{month}-{day}"  # ISO 8601 format YYYY-MM-DD
    else:
        return None

@lru_cache(maxsize=128)
def convert_date_format(date_str: str, output_format: str = 'hyphen', year: Optional[int] = None) -> Optional[str]:
    """
    Convert a date string from any supported format to the specified output format.
    Cached for better performance with frequently used conversions.
    
    Args:
        date_str (str): The date string to convert
        output_format (str): The desired output format ('hyphen', 'period', 'slash', 'filename', 'iso')
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        Optional[str]: The date in the requested format or None if parsing fails.
    """
    parsed = parse_date(date_str, year)
    if parsed:
        return format_date(parsed, output_format)
    return None

# def is_valid_date(date_str): # Removed as unused
#     """
#     Check if a string is a valid date in any of the supported formats.
#     ... (rest of docstring and code) ...
#     """
#     pass # Function removed
# def get_filename_date_format(start_date_str, end_date_str, year=None): # Removed as unused
#     """
#     Format dates specifically for the timetable filename format.
#     ... (rest of docstring and code) ...
#     """
#     pass # Function removed
@lru_cache(maxsize=128)
def to_iso_date(date_str: str, year: Optional[int] = None) -> Optional[str]:
    """
    Convert a date string to ISO 8601 format (YYYY-MM-DD).
    Cached for better performance with frequently accessed dates.
    
    Args:
        date_str (str): The date string to convert
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        Optional[str]: Date in ISO 8601 format (YYYY-MM-DD) or None if parsing fails.
    """
    if not date_str:
        return None
        
    # Use our standard converter
    return convert_date_format(date_str, 'iso', year)

# def normalize_dates(start_date, end_date, year): # Removed as unused
#     """
#     Normalize date format to ensure consistency.
#     ... (rest of docstring and code) ...
#     """
#     pass # Function removed

def parse_time_range(time_range: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a time range string (e.g., "10:05-11:35") into start and end times.
    
    Args:
        time_range (str): Time range in format "HH:MM-HH:MM"
        
    Returns:
        Tuple[Optional[str], Optional[str]]: (start_time, end_time) strings,
                                             or (None, None) if parsing fails.
    """
    if not time_range or '-' not in time_range:
        return None, None
    
    parts = time_range.split('-')
    if len(parts) != 2:
        return None, None
    
    return parts[0].strip(), parts[1].strip() 