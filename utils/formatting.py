#!/usr/bin/env python3
"""
Utility functions for formatting and date handling.
"""

def format_date(date_str, year):
    """Format date from DD/MM to YYYY-MM-DD"""
    if not date_str:
        return ""
    try:
        day, month = date_str.split('/')
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except ValueError:
        return date_str

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