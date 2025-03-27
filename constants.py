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

# Mapping from subject codes to full names
SUBJECT_CODE_MAPPING = {
    "evf": "Evnafrøði",
    "søg": "Søga",
    "alf": "Alisfrøði",
    "før": "Føroyskt",
    "stø": "Støddfrøði",
    "mik": "Mikrobiologi",
    "rel": "Religion",
    # Exam-related mappings
    "Várroynd": "Spring Exam",
    "Várroynd-før": "Spring Exam - Føroyskt",
    "Várroynd-alf": "Spring Exam - Alisfrøði",
    "Várroynd-stø": "Spring Exam - Støddfrøði",
    "Várroynd-evf": "Spring Exam - Evnafrøði",
    # Add more mappings as needed
}

# Special room formatting rules
ROOM_FORMAT_MAPPING = {
    "BIJ st. 608": "Bt.608",
    "TJA st. 322": "TIA St. 322",
    "PEY st. 606": "PEY 606",
    "JOH st. 319": "JOH St. 319",
    "BIJ st. NLH": "BL at NLH",
    "TJA st. 510": "TIA st. 510",
    "HSV st. 615": "HSV S. 615",
    "TJA st. 419": "LIA S. 419",
    "JBJ st. 418": "JBI st. 418",
    "PEY st. 611": "PEY St 611",
    "DTH st. 514": "rel St. 324",
    "HSV st. 614": "HSV St. 615",
    "JOH st. 514": "JOH st. 514",
    # Add more mappings as needed
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