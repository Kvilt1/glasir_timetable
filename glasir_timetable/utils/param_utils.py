#!/usr/bin/env python3
"""
Utility functions for extracting dynamic parameters from HTML content.
"""

import re
import logging
import time
from typing import Tuple, Optional

from ..constants import (
    DEFAULT_TIMER_FALLBACK,
)

logger = logging.getLogger(__name__)

# Regex patterns for parameter extraction
LNAME_REGEX_PATTERNS = [
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',(\d+),"),  # Try specific JS first
    re.compile(r"lname=(\d+)"),  # Check query params
    re.compile(r"'lname':\s*'(\d+)'"),  # Check inline script data
    re.compile(r"name='lname'\s*value='(\d+)'"),  # Check hidden input
]
TIMER_REGEX_PATTERNS = [
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"),  # Try specific JS first
    re.compile(r"timer=(\d+)"),  # Check query params
    re.compile(r"'timer':\s*'(\d+)'"),  # Check inline script data
    re.compile(r"name='timer'\s*value='(\d+)'"),  # Check hidden input
]

# Additional specific patterns
LNAME_SCRIPT_PATTERN = re.compile(r"lname=([^&\"'\s]+)")
LNAME_MYUPDATE_PATTERN = re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\"")
TIMER_WINDOW_PATTERN = re.compile(r"timer\s*=\s*(\d+)")
TIMER_MYUPDATE_PATTERN = re.compile(r"MyUpdate\s*\([^,]*,[^,]*,[^,]*,[^,]*,\s*(\d+)")
FORD_LNAME_PATTERN = re.compile(r"lname=Ford(\d+,\d+)")

def parse_dynamic_params(html_content: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Extract the essential dynamic session parameters (lname and timer) from HTML content.
    
    Args:
        html_content: HTML content from the Glasir timetable page
        
    Returns:
        A tuple containing (lname, timer) values. Either can be None if extraction fails.
    """
    logger.info("Extracting dynamic session parameters (lname/timer) from HTML content...")
    
    if not html_content:
        logger.error("Empty HTML content provided.")
        return None, None
    
    # Extract lname - try various patterns
    lname = None
    for pattern in [LNAME_SCRIPT_PATTERN, LNAME_MYUPDATE_PATTERN, FORD_LNAME_PATTERN] + LNAME_REGEX_PATTERNS:
        match = pattern.search(html_content)
        if match:
            lname = match.group(1)
            logger.info(f"Found lname value using regex: {lname}")
            break
    
    # Use current timestamp directly for timer as it's more reliable
    timer = int(time.time() * 1000)
    logger.info(f"Using current timestamp for timer: {timer}")
    
    # Only try to extract timer with regex as a backup if needed for debugging
    timer_from_html = None
    for pattern in [TIMER_WINDOW_PATTERN, TIMER_MYUPDATE_PATTERN] + TIMER_REGEX_PATTERNS:
        match = pattern.search(html_content)
        if match:
            try:
                timer_from_html = int(match.group(1))
                logger.debug(f"Found timer value in HTML using regex (not used): {timer_from_html}")
                break
            except ValueError:
                logger.debug(f"Found timer string but couldn't convert to integer: {match.group(1)}")
    
    # Apply fallback if needed for lname
    if not lname:
        logger.warning("Could not extract lname, returning None")
    
    return lname, timer 