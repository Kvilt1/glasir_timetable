#!/usr/bin/env python3
"""
Constants and mappings used by the Glasir Timetable application.
"""

# Mapping from Faroese day names to English
DAY_NAME_MAPPING = {
    "Mánadagur": "Monday",
    "Týsdagur": "Tuesday",
    "Mikudagur": "Wednesday",
    "Hósdagur": "Thursday",
    "Fríggjadagur": "Friday",
    "Leygardagur": "Saturday",
    "Sunnudagur": "Sunday",
}

# CSS classes that indicate a cancelled class (all use text-decoration:line-through)
CANCELLED_CLASS_INDICATORS = [
    "lektionslinje_lesson1",
    "lektionslinje_lesson2",
    "lektionslinje_lesson3",
    "lektionslinje_lesson4",
    "lektionslinje_lesson5",
    "lektionslinje_lesson7",
    "lektionslinje_lesson10",
    "lektionslinje_lessoncancelled",
]

# URLs
GLASIR_BASE_URL = "https://tg.glasir.fo"
GLASIR_TIMETABLE_URL = f"{GLASIR_BASE_URL}/132n/"

# Default headers for API requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Cache settings
TEACHER_MAP_CACHE_TTL = 86400  # 24 hours in seconds

# --- Concurrency Settings ---

# Default limits (used when no dynamic config exists or dynamic fails)
DEFAULT_WEEK_FETCH_CONCURRENCY = (
    5  # Default parallel week HTML fetch requests (Producer)
)
DEFAULT_HOMEWORK_FETCH_CONCURRENCY = 20  # Default parallel homework detail requests
DEFAULT_WEEK_PROCESS_CONCURRENCY = (
    4  # Default parallel week data processing tasks (Consumer) - Adjust based on CPU/IO
)

# Maximum limits (used for --force-max-concurrency flag)
# These represent reasonable upper bounds to avoid overwhelming the server.
FORCE_MAX_WEEK_FETCH_CONCURRENCY = 10
FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY = 30

# Concurrency config file name
CONCURRENCY_CONFIG_FILENAME = "concurrency_config.json"
