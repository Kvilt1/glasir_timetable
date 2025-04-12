from bs4 import BeautifulSoup
from typing import Dict
import re
from glasir_timetable.shared import logger

# Compiled regex patterns for teacher extraction fallback
_RE_TEACHER_WITH_LINK = re.compile(r'([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)')
_RE_TEACHER_NO_LINK = re.compile(r'([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)')
def parse_teacher_html(html: str) -> Dict[str, str]:
    """
    Parse teacher list HTML into {initials: full_name} dict.
    """
    teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")

        # Try select element first
        select_tag = soup.select_one("select") # Use select_one
        if select_tag:
            for option in select_tag.select("option"): # Use select
                initials = option.get("value")
                full_name = option.get_text(strip=True)
                if initials and initials != "-1":
                    teacher_map[initials] = full_name

        # Fallback: regex parse
        if not teacher_map:
            # Use pre-compiled patterns
            compiled_patterns = [_RE_TEACHER_WITH_LINK, _RE_TEACHER_NO_LINK]
            for compiled_pattern in compiled_patterns:
                matches = compiled_pattern.findall(html)
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name

    except Exception as e:
        logger.error("Error parsing teacher HTML")

    return teacher_map