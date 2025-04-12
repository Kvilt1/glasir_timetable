from bs4 import BeautifulSoup
from typing import Dict
import re
from glasir_timetable.shared import logger

def parse_teacher_html(html: str) -> Dict[str, str]:
    """
    Parse teacher list HTML into {initials: full_name} dict.
    """
    teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")

        # Try select element first
        select = soup.find("select")
        if select:
            for option in select.find_all("option"):
                initials = option.get("value")
                full_name = option.get_text(strip=True)
                if initials and initials != "-1":
                    teacher_map[initials] = full_name

        # Fallback: regex parse
        if not teacher_map:
            patterns = [
                r'([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)',
                r'([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, html)
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name

    except Exception as e:
        logger.error("Error parsing teacher HTML")

    return teacher_map