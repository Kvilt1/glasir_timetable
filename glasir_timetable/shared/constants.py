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

# DAY_MAP_DA_TO_EN = DAY_NAME_MAPPING # Removed as unused

# TIME_SLOTS_REAL = [...] # Removed as unused

# LEVEL_MAP = {...} # Removed as unused

# URLs
GLASIR_BASE_URL = "https://tg.glasir.fo"
GLASIR_TIMETABLE_URL = f"{GLASIR_BASE_URL}/132n/"
NOTE_ASP_URL = f"{GLASIR_BASE_URL}/i/note.asp"
TEACHER_MAP_URL = f"{GLASIR_BASE_URL}/i/teachers.asp"
TIMETABLE_INFO_URL = f"{GLASIR_BASE_URL}/i/udvalg.asp"

# Default headers for API requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Default fallback values

# File paths
TEACHER_CACHE_FILE = "glasir_timetable/accounts/global/teacher_cache.json"
STUDENT_ID_FILE = "glasir_timetable/student-id.json"

# Auth cookie file path
AUTH_COOKIES_FILE = "cookies.json"

# Data directory for storing timetable data
DATA_DIR = "glasir_timetable/weeks"