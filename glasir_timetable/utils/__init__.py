#!/usr/bin/env python3
"""
Utility modules for the Glasir Timetable application.
"""
from glasir_timetable.utils.formatting import (
    format_academic_year,
    get_timeslot_info,
    normalize_dates,
    normalize_week_number,
    generate_week_filename,
    convert_keys_to_camel_case,
    to_camel_case,
    format_iso_date,
    parse_time_range
)
# Removed validator import as CORRECT.json is no longer used 
from glasir_timetable.utils.date_utils import (
    detect_date_format,
    parse_date,
    format_date,
    convert_date_format,
    is_valid_date,
    get_filename_date_format,
    to_iso_date
) 

# Import additional utility functions as needed 