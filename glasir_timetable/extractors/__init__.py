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
from glasir_timetable.extractors.navigation import (
    analyze_week_structure,
    find_week_v_value,
    navigate_to_week,
    get_current_week_info,
    return_to_baseline
) 