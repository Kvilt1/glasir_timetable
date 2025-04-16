#!/usr/bin/env python3
"""
Utility functions for formatting and date handling.
"""
import re
from functools import lru_cache
from glasir_timetable.shared.date_utils import to_iso_date # Removed unused convert_date_format, normalize_dates, parse_time_range

@lru_cache()
def format_academic_year(year_code):
    """
    Parse year code like '2425' into '2024-2025'
    """
    if len(year_code) == 4:
        return f"20{year_code[:2]}-20{year_code[2:]}"
    return year_code  # Return as is if format is unexpected

# def get_timeslot_info(start_col_index): # Moved to parsers/timetable_parser.py
#     """
#     Maps the starting column index of a lesson TD to its time slot.
#     ... (rest of docstring and code) ...
#     """
#     pass # Function moved

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

def parse_time_range(time_range_str):
    """Stub for parse_time_range. Accepts a string and returns it as a tuple (start, end)."""
    # TODO: Implement actual parsing logic if needed
    return time_range_str, time_range_str