#!/usr/bin/env python3
# Extractors package initialization

"""
Extractors for the Glasir Timetable application.
"""
import logging
from glasir_timetable import logger

# Re-export functions from submodules
from glasir_timetable.extractors.teacher_map import extract_teacher_map
from glasir_timetable.extractors.timetable import extract_timetable_data, get_week_info, extract_homework_content
from glasir_timetable.js_navigation.js_integration import get_current_week_info 