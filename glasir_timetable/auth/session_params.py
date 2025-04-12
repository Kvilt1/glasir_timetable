import re
import time
from typing import Optional, Dict
from playwright.async_api import Page
from glasir_timetable.shared import logger

LNAME_PATTERNS = [
    re.compile(r"lname=([^&\"'\s]+)"),
    re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\""),
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"),
    re.compile(r"name=['\"]lname['\"]\s*value=['\"]([^'\"]+)['\"]"),
]

TIMER_PATTERNS = [
    re.compile(r"timer\s*=\s*(\d+)"),
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"),
    re.compile(r"name=['\"]timer['\"]\s*value=['\"](\d+)['\"]"),
]

async def extract_session_params_from_page(page: Page) -> Dict[str, str]:
    """
    Extract 'lname' and 'timer' from Playwright page content.
    """
    try:
        html = await page.content()
        return extract_session_params_from_html(html)
    except Exception as e:
        logger.error(f"Failed to extract session params from page: {e}")
        return {}

def extract_session_params_from_html(html: str) -> Dict[str, str]:
    """
    Extract 'lname' and 'timer' from HTML content.
    """
    lname = None
    timer = None

    # Extract lname
    for pattern in LNAME_PATTERNS:
        match = pattern.search(html)
        if match:
            lname = match.group(1)
            logger.debug(f"Extracted lname: {lname}")
            break

    # Use current timestamp as timer fallback
    timer_val = int(time.time() * 1000)

    # Try to extract timer from HTML
    for pattern in TIMER_PATTERNS:
        match = pattern.search(html)
        if match:
            try:
                timer_val = int(match.group(1))
                logger.debug(f"Extracted timer: {timer_val}")
                break
            except ValueError:
                continue

    if not lname:
        logger.warning("Could not extract 'lname' from HTML")
    return {"lname": lname, "timer": str(timer_val)}

async def get_or_refresh_session_params(
    page: Page,
    cache: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Get cached session params or extract fresh from page.
    """
    if cache and cache.get("lname") and cache.get("timer"):
        return cache
    params = await extract_session_params_from_page(page)
    if not params.get("lname"):
        raise RuntimeError("Failed to extract 'lname' session param")
    return params