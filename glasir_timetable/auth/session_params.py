import re
from typing import Dict

from glasir_timetable.shared import logger

LNAME_PATTERNS = [
    re.compile(r"lname=([^&\"'\s]+)"),
    re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\""),
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"),
    re.compile(r"name=['\"]lname['\"]\s*value=['\"]([^'\"]+)['\"]"),
]


def extract_session_params_from_html(html: str) -> Dict[str, str]:
    """
    Extract 'lname' from HTML content.
    """
    lname = None
    # Extract lname
    for pattern in LNAME_PATTERNS:
        match = pattern.search(html)
        if match:
            lname = match.group(1)
            logger.debug(f"Extracted lname: {lname}")
            break

    if not lname:
        logger.warning("Could not extract 'lname' from HTML")
    return {"lname": lname}
