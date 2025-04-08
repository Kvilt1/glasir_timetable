#!/usr/bin/env python3
# Extractors package initialization

"""
Extractors package for the Glasir Timetable application.

This package contains modules for extracting data from the Glasir website,
including timetable data, teacher information, and homework content.
"""
import logging
from glasir_timetable.shared import logger

# Re-export functions from submodules
from glasir_timetable.data.teacher_map import extract_teacher_map
from glasir_timetable.data.timetable import extract_timetable_data, get_week_info
# Remove this import to break circular dependency
# from glasir_timetable.js_navigation.js_integration import get_current_week_info
# Import homework parser after other imports to avoid circular dependencies
from glasir_timetable.data.homework_parser import parse_homework_html_response, clean_homework_text

__all__ = [
    'extract_timetable_data',
    'extract_teacher_map',
    'parse_homework_html_response',
    'clean_homework_text'
] 