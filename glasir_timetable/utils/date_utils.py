#!/usr/bin/env python3
"""
Utility functions for handling date formats in the Glasir Timetable project.
Provides consistent date parsing and formatting across the application.
"""
import re
from datetime import datetime

def detect_date_format(date_str):
    """
    Detect the format of a date string.
    
    Args:
        date_str (str): The date string to analyze
        
    Returns:
        str: The detected format ('period', 'hyphen', 'slash', or 'unknown')
    """
    if not date_str:
        return 'unknown'
        
    if '.' in date_str:
        return 'period'
    elif '-' in date_str:
        return 'hyphen'
    elif '/' in date_str:
        return 'slash'
    else:
        return 'unknown'

def parse_date(date_str, year=None):
    """
    Parse a date string in various formats and return standardized components.
    
    Args:
        date_str (str): The date string to parse
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        dict: Dictionary with 'year', 'month', 'day' as keys or None if parsing fails
    """
    if not date_str:
        return None
        
    # If we don't have a year, use current year
    if year is None:
        year = datetime.now().year
        
    format_type = detect_date_format(date_str)
    
    # Handle period format (DD.MM.YYYY or DD.MM)
    if format_type == 'period':
        # Try DD.MM.YYYY format
        match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
        if match:
            day, month, year = match.groups()
            return {
                'day': day.zfill(2),
                'month': month.zfill(2),
                'year': year
            }
        
        # Try DD.MM format
        match = re.match(r'(\d{1,2})\.(\d{1,2})', date_str)
        if match:
            day, month = match.groups()
            return {
                'day': day.zfill(2),
                'month': month.zfill(2),
                'year': str(year)
            }
    
    # Handle hyphen format (YYYY-MM-DD)
    elif format_type == 'hyphen':
        parts = date_str.split('-')
        if len(parts) == 3:
            year, month, day = parts
            return {
                'day': day.zfill(2),
                'month': month.zfill(2),
                'year': year
            }
    
    # Handle slash format (DD/MM or MM/DD)
    elif format_type == 'slash':
        parts = date_str.split('/')
        if len(parts) == 2:
            # Assume DD/MM format (European)
            day, month = parts
            return {
                'day': day.zfill(2),
                'month': month.zfill(2),
                'year': str(year)
            }
        
        # Handle DD/MM-YYYY format (like 24/3-2025)
        match = re.match(r'(\d{1,2})/(\d{1,2})-(\d{4})', date_str)
        if match:
            day, month, year = match.groups()
            return {
                'day': day.zfill(2),
                'month': month.zfill(2),
                'year': year
            }
    
    # Try to handle DD/MM-YYYY format (like "24/3-2025") if not caught by the slash format handler
    pattern = re.compile(r'(\d{1,2})/(\d{1,2})-(\d{4})')
    match = pattern.match(date_str)
    
    if match:
        day, month, year = match.groups()
        # Format with leading zeros
        return {
            'day': day.zfill(2),
            'month': month.zfill(2),
            'year': year
        }
    
    # If we got here, we couldn't parse the date
    return None

def format_date(date_dict, output_format='hyphen'):
    """
    Format a date dictionary to a specific output format.
    
    Args:
        date_dict (dict): Dictionary with 'year', 'month', 'day' keys
        output_format (str): The desired output format ('hyphen', 'period', 'slash', 'filename', 'iso')
        
    Returns:
        str: Formatted date string or None if input is invalid
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

def convert_date_format(date_str, output_format='hyphen', year=None):
    """
    Convert a date string from any supported format to the specified output format.
    
    Args:
        date_str (str): The date string to convert
        output_format (str): The desired output format ('hyphen', 'period', 'slash', 'filename', 'iso')
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        str: The date in the requested format or None if parsing fails
    """
    parsed = parse_date(date_str, year)
    if parsed:
        return format_date(parsed, output_format)
    return None

def is_valid_date(date_str):
    """
    Check if a string is a valid date in any of the supported formats.
    
    Args:
        date_str (str): The date string to validate
        
    Returns:
        bool: True if the string is a valid date, False otherwise
    """
    return parse_date(date_str) is not None

def get_filename_date_format(start_date_str, end_date_str, year=None):
    """
    Format dates specifically for the timetable filename format.
    
    Args:
        start_date_str (str): Start date in any supported format
        end_date_str (str): End date in any supported format
        year (int, optional): Year to use if not in the date strings
        
    Returns:
        str: Formatted as "MM.DD-MM.DD" for use in filenames or None if parsing fails
    """
    start_parsed = parse_date(start_date_str, year)
    end_parsed = parse_date(end_date_str, year)
    
    if not start_parsed or not end_parsed:
        return None
        
    start_filename = format_date(start_parsed, 'filename')
    end_filename = format_date(end_parsed, 'filename')
    
    if start_filename and end_filename:
        # This creates the MM.DD-MM.DD format needed for the filename
        return f"{start_filename}-{end_filename}"
    
    return None

def to_iso_date(date_str, year=None):
    """
    Convert a date string to ISO 8601 format (YYYY-MM-DD).
    
    Args:
        date_str (str): The date string to convert
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        str: Date in ISO 8601 format or None if parsing fails
    """
    if not date_str:
        return None
        
    # Try using our standard converter first
    iso_date = convert_date_format(date_str, 'iso', year)
    if iso_date:
        return iso_date
    
    # Try to handle edge cases directly
    # Handle DD/MM-YYYY format (like "24/3-2025")
    pattern = re.compile(r'(\d{1,2})/(\d{1,2})-(\d{4})')
    match = pattern.match(date_str)
    
    if match:
        day, month, year = match.groups()
        # Format with leading zeros
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # If nothing worked, return None
    return None 