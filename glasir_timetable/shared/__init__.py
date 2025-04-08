#!/usr/bin/env python3
"""
Utility modules for the Glasir Timetable application.
"""
import logging

logger = logging.getLogger("glasir_timetable")

from glasir_timetable.shared.formatting import (
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
from glasir_timetable.shared.date_utils import (
    detect_date_format,
    parse_date,
    format_date,
    convert_date_format,
    is_valid_date,
    get_filename_date_format,
    to_iso_date
) 

from glasir_timetable.shared.file_utils import (
    save_json_data
)

# Import error handling utilities
from glasir_timetable.shared.error_utils import (
    handle_errors,
    error_screenshot_context,
    resource_cleanup_context,
    async_resource_cleanup_context,
    evaluate_js_safely,
    register_console_listener,
    unregister_console_listener,
    default_console_listener,
    GlasirError,
    JavaScriptError,
    ExtractionError,
    NavigationError,
    AuthenticationError
)

# Import additional utility functions as needed 