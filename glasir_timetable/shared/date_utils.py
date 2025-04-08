#!/usr/bin/env python3
"""
Utility functions for handling date formats in the Glasir Timetable project.
Provides consistent date parsing and formatting across the application.
"""
import re
from datetime import datetime
from functools import lru_cache

# Pre-compile regex patterns for better performance
PERIOD_DATE_FULL = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')
PERIOD_DATE_SHORT = re.compile(r'(\d{1,2})\.(\d{1,2})')
HYPHEN_DATE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')
SLASH_DATE_SHORT = re.compile(r'(\d{1,2})/(\d{1,2})')
SLASH_DATE_WITH_YEAR = re.compile(r'(\d{1,2})/(\d{1,2})-(\d{4})')

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

@lru_cache(maxsize=256)
def parse_date(date_str, year=None):
    """
    Parse a date string in various formats and return standardized components.
    Cached for better performance with frequently used dates.
    
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

@lru_cache(maxsize=128)
def convert_date_format(date_str, output_format='hyphen', year=None):
    """
    Convert a date string from any supported format to the specified output format.
    Cached for better performance with frequently used conversions.
    
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

@lru_cache(maxsize=128)
def to_iso_date(date_str, year=None):
    """
    Convert a date string to ISO 8601 format (YYYY-MM-DD).
    Cached for better performance with frequently accessed dates.
    
    Args:
        date_str (str): The date string to convert
        year (int, optional): The year to use if not present in the date string
        
    Returns:
        str: Date in ISO 8601 format or None if parsing fails
    """
    if not date_str:
        return None
        
    # Use our standard converter
    return convert_date_format(date_str, 'iso', year)

def normalize_dates(start_date, end_date, year):
    """
    Normalize date format to ensure consistency.
    
    Args:
        start_date (str): The start date
        end_date (str): The end date
        year (int): The year
        
    Returns:
        tuple: Normalized (start_date, end_date)
    """
    # Add better logging for debugging date issues
    from glasir_timetable import logger
    logger.debug(f"Normalizing dates: start={start_date}, end={end_date}, year={year}")
    
    # Check for year transitions (December to January)
    if start_date and end_date:
        # Try to extract month values
        start_month = None
        end_month = None
        
        # Parse dates to extract month values reliably
        start_parsed = parse_date(start_date, year)
        end_parsed = parse_date(end_date, year)
        
        if start_parsed and end_parsed:
            try:
                start_month = int(start_parsed['month'])
                end_month = int(end_parsed['month'])
            except (ValueError, KeyError):
                pass
        
        # Handle year transitions (December to January)
        if start_month and end_month:
            logger.debug(f"Detected months: start_month={start_month}, end_month={end_month}")
            
            if start_month == 12 and end_month == 1:
                # December to January transition
                if not start_date.startswith(str(year)):
                    start_date = f"{year}.{start_date}"
                if not end_date.startswith(str(year+1)):
                    end_date = f"{year+1}.{end_date}"
                logger.debug(f"Year transition detected, updated dates: start={start_date}, end={end_date}")
                return start_date, end_date
            
            # Account for academic year transitions (July/August)
            if start_month == 7 and end_month == 8:
                # July to August transition (academic year boundary)
                if not start_date.startswith(str(year)):
                    start_date = f"{year}.{start_date}"
                if not end_date.startswith(str(year)):
                    end_date = f"{year}.{end_date}"
                logger.debug(f"Academic year transition detected, updated dates: start={start_date}, end={end_date}")
                return start_date, end_date
    
    # Standard case - ensure dates have year prefix
    if start_date and not start_date.startswith(str(year)):
        start_date = f"{year}.{start_date}"
    if end_date and not end_date.startswith(str(year)):
        end_date = f"{year}.{end_date}"
    
    # Replace any hyphens with periods for consistency
    if start_date:
        start_date = start_date.replace('-', '.')
    if end_date:
        end_date = end_date.replace('-', '.')
    
    logger.debug(f"Normalized dates: start={start_date}, end={end_date}")
    return start_date, end_date

def parse_time_range(time_range):
    """
    Parse a time range string (e.g., "10:05-11:35") into start and end times.
    
    Args:
        time_range (str): Time range in format "HH:MM-HH:MM"
        
    Returns:
        tuple: (start_time, end_time) or (None, None) if parsing fails
    """
    if not time_range or '-' not in time_range:
        return None, None
    
    parts = time_range.split('-')
    if len(parts) != 2:
        return None, None
    
    return parts[0].strip(), parts[1].strip() 