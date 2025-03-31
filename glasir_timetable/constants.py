#!/usr/bin/env python3
"""
Constants and mappings used by the Glasir Timetable application.
"""

# Timetable block times according to timetable.md
BLOCK_TIMES = {
    1: ("08:10", "09:40"),
    2: ("10:05", "11:35"),
    3: ("12:10", "13:40"),
    4: ("13:55", "15:25"),
    5: ("15:30", "17:00"),
    6: ("17:15", "18:45"),
    "All day": ("08:10", "15:25")  # Full day block spanning from first to last regular block
}

# Mapping from Faroese day names to English
DAY_NAME_MAPPING = {
    "Mánadagur": "Monday",
    "Týsdagur": "Tuesday",
    "Mikudagur": "Wednesday",
    "Hósdagur": "Thursday",
    "Fríggjadagur": "Friday",
    "Leygardagur": "Saturday",
    "Sunnudagur": "Sunday"
}

# Days order for sorting
DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# CSS classes that indicate a cancelled class (all use text-decoration:line-through)
CANCELLED_CLASS_INDICATORS = [
    'lektionslinje_lesson1',
    'lektionslinje_lesson2',
    'lektionslinje_lesson3',
    'lektionslinje_lesson4',
    'lektionslinje_lesson5',
    'lektionslinje_lesson7',
    'lektionslinje_lesson10',
    'lektionslinje_lessoncancelled'
] 