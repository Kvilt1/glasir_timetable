#!/usr/bin/env python3
"""
Utility modules for the Glasir Timetable application.
"""
import logging

logger = logging.getLogger("glasir_timetable")

from glasir_timetable.shared.formatting import (
    format_academic_year,
    format_iso_date,
    parse_time_range
)
# Removed validator import as CORRECT.json is no longer used 
from glasir_timetable.shared.date_utils import (
    to_iso_date
) 

# Removed import from glasir_timetable.shared.file_utils as it no longer exists
# save_json_data functionality is likely handled by AccountProfile or storage modules now

# Import error handling utilities
from glasir_timetable.shared.error_utils import (
    error_screenshot_context,
    register_console_listener,
    default_console_listener,
    GlasirError,
    JavaScriptError,
)

# Import concurrency manager
from .concurrency_manager import ConcurrencyManager

# Import additional utility functions as needed