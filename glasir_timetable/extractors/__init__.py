#!/usr/bin/env python3
# Extractors package initialization

from .teacher_map import extract_teacher_map
from .timetable import extract_timetable_data, get_week_info, extract_homework_content
from .navigation import (
    analyze_week_structure,
    find_week_v_value,
    navigate_to_week,
    get_current_week_info,
    return_to_baseline
) 