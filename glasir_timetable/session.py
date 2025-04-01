import httpx
import re
import logging
from typing import Tuple, Optional, Dict, Any
from playwright.async_api import Page
from bs4 import BeautifulSoup
import time

from .utils.error_utils import handle_errors, GlasirScrapingError
from .constants import (
    DEFAULT_LNAME_FALLBACK,
    DEFAULT_TIMER_FALLBACK,
    GLASIR_TIMETABLE_URL,
)

logger = logging.getLogger(__name__)

# Regex patterns copied from the original api_client.py
LNAME_REGEX_PATTERNS = [
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',(\d+),"),  # Try specific JS first
    re.compile(r"lname=(\d+)"), # Check query params
    re.compile(r"'lname':\s*'(\d+)'"), # Check inline script data
    re.compile(r"name='lname'\s*value='(\d+)'"), # Check hidden input
]
TIMER_REGEX_PATTERNS = [
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"), # Try specific JS first
    re.compile(r"timer=(\d+)"), # Check query params
    re.compile(r"'timer':\s*'(\d+)'"), # Check inline script data
    re.compile(r"name='timer'\s*value='(\d+)'"), # Check hidden input
]

# Add more specific patterns based on the actual page structure
LNAME_SCRIPT_PATTERN = re.compile(r"lname=([^&\"'\s]+)")
LNAME_MYUPDATE_PATTERN = re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\"")
TIMER_WINDOW_PATTERN = re.compile(r"timer\s*=\s*(\d+)")
FORD_LNAME_PATTERN = re.compile(r"lname=Ford(\d+,\d+)")

async def get_dynamic_session_params(page: Page) -> Tuple[Optional[str], Optional[int]]:
    """
    Extract the essential dynamic session parameters (lname and timer) from the page content
    after authentication, minimizing JavaScript execution.
    
    Args:
        page: Authenticated Playwright page object
        
    Returns:
        A tuple containing (lname, timer) values. Either can be None if extraction fails.
    """
    logger.info("Extracting dynamic session parameters (lname/timer) from authenticated page...")
    
    # Get the page content once to avoid multiple requests
    try:
        content = await page.content()
    except Exception as e:
        logger.error(f"Failed to get page content: {e}")
        return None, None
    
    # First try to extract using regex on plain HTML/JS content
    lname = None
    timer = None
    
    # Extract lname - try various patterns
    for pattern in [LNAME_SCRIPT_PATTERN, LNAME_MYUPDATE_PATTERN, FORD_LNAME_PATTERN] + LNAME_REGEX_PATTERNS:
        match = pattern.search(content)
        if match:
            lname = match.group(1)
            logger.info(f"Found lname value using regex: {lname}")
            break
    
    # Extract timer - try various patterns
    for pattern in [TIMER_WINDOW_PATTERN] + TIMER_REGEX_PATTERNS:
        match = pattern.search(content)
        if match:
            try:
                timer = int(match.group(1))
                logger.info(f"Found timer value using regex: {timer}")
                break
            except ValueError:
                logger.warning(f"Found timer string but couldn't convert to integer: {match.group(1)}")
    
    # If regex approach failed for either value, try minimal JS evaluation as fallback
    if not lname:
        logger.warning("Couldn't extract lname using regex, trying JavaScript evaluation...")
        try:
            # Simple script to extract lname from MyUpdate function
            lname_js = """() => {
                if (document.documentElement.outerHTML.includes('lname=Ford')) {
                    const match = document.documentElement.outerHTML.match(/lname=Ford([\\d,]+)/);
                    return match ? 'Ford' + match[1] : null;
                }
                if (typeof MyUpdate === 'function') {
                    const myUpdateStr = MyUpdate.toString();
                    const match = myUpdateStr.match(/lname=([^&"]+)/);
                    return match ? match[1] : null;
                }
                return null;
            }"""
            lname = await page.evaluate(lname_js)
            if lname:
                logger.info(f"Found lname value using JS evaluation: {lname}")
        except Exception as e:
            logger.error(f"JavaScript evaluation for lname failed: {e}")
    
    if not timer:
        logger.warning("Couldn't extract timer using regex, trying JavaScript evaluation...")
        try:
            # Simple script to extract timer
            timer_js = """() => {
                if (typeof timer !== 'undefined') {
                    return timer;
                }
                
                const scripts = Array.from(document.querySelectorAll('script'));
                for (const script of scripts) {
                    if (script.textContent && script.textContent.includes('timer')) {
                        const match = script.textContent.match(/timer\\s*=\\s*(\\d+)/);
                        if (match) return parseInt(match[1], 10);
                    }
                }
                
                // Fallback: just return current timestamp
                return Date.now();
            }"""
            timer = await page.evaluate(timer_js)
            if timer:
                logger.info(f"Found timer value using JS evaluation: {timer}")
        except Exception as e:
            logger.error(f"JavaScript evaluation for timer failed: {e}")
            # Use a timestamp fallback
            timer = int(time.time() * 1000)
            logger.warning(f"Using fallback timestamp for timer: {timer}")
    
    if not lname:
        logger.warning(f"Could not extract lname, falling back to {DEFAULT_LNAME_FALLBACK}")
        lname = DEFAULT_LNAME_FALLBACK
    
    if not timer:
        logger.warning(f"Could not extract timer, falling back to {DEFAULT_TIMER_FALLBACK}")
        timer = DEFAULT_TIMER_FALLBACK
    
    return lname, timer


class AuthSessionManager:
    """Manages dynamic session parameters required for Glasir API interactions."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._lname: Optional[str] = None
        self._timer: Optional[str] = None
        self._cached_params: Dict[str, str] = {}

    @property
    async def lname(self) -> str:
        """Get the 'lname' parameter, fetching if necessary."""
        if self._lname is None:
            await self.fetch_and_cache_params()
        if self._lname is None: # Still None after fetch attempt
             logger.warning(f"Could not extract lname, falling back to {DEFAULT_LNAME_FALLBACK}")
             return DEFAULT_LNAME_FALLBACK
        return self._lname

    @property
    async def timer(self) -> str:
        """Get the 'timer' parameter, fetching if necessary."""
        if self._timer is None:
            await self.fetch_and_cache_params()
        if self._timer is None: # Still None after fetch attempt
            logger.warning(f"Could not extract timer, falling back to {DEFAULT_TIMER_FALLBACK}")
            return DEFAULT_TIMER_FALLBACK
        return self._timer

    async def get_params(self) -> Dict[str, str]:
        """Get both 'lname' and 'timer' parameters."""
        lname = await self.lname
        timer = await self.timer
        return {"lname": lname, "timer": timer}

    def _search_patterns(self, content: str, patterns: list[re.Pattern]) -> Optional[str]:
        """Search content using a list of regex patterns."""
        for pattern in patterns:
            match = pattern.search(content)
            if match:
                found_value = match.group(1)
                logger.debug(f"Found value using pattern {pattern.pattern}: {found_value}")
                return found_value
        return None

    @handle_errors(default_return=({},), reraise=True, error_category="extracting_lname_timer")
    async def extract_lname_and_timer(self, page: Optional[Page] = None, content: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Extracts 'lname' and 'timer' values required for API calls.

        Prioritizes extracting from Playwright page object if provided,
        otherwise fetches content via httpx. Uses multiple regex patterns
        and fallback values.

        Args:
            page: Optional Playwright Page object.
            content: Optional HTML content string. If None and page is None, fetches content.

        Returns:
            A tuple containing (lname, timer). Values can be None if extraction fails.
        """
        logger.info("Attempting to extract lname and timer...")
        if page:
            logger.debug("Using Playwright page content for extraction.")
            try:
                content = await page.content() # Get fresh content
            except Exception as e:
                logger.error(f"Failed to get content from Playwright page: {e}")
                content = None # Fallback to fetch if page.content fails

        if not content:
             logger.debug("Fetching page content via httpx.")
             try:
                 response = await self._client.get(GLASIR_TIMETABLE_URL)
                 response.raise_for_status()
                 content = response.text
             except httpx.RequestError as e:
                 logger.error(f"HTTP request failed when fetching for lname/timer: {e}")
                 raise GlasirScrapingError(f"Failed to fetch initial page content: {e}") from e
             except httpx.HTTPStatusError as e:
                 logger.error(f"HTTP status error when fetching for lname/timer: {e.response.status_code}")
                 raise GlasirScrapingError(f"Failed status code {e.response.status_code} fetching initial page content.") from e

        if not content:
            logger.error("Failed to obtain page content for lname/timer extraction.")
            return None, None

        # --- Extraction Logic ---
        lname = self._search_patterns(content, LNAME_REGEX_PATTERNS)
        timer = self._search_patterns(content, TIMER_REGEX_PATTERNS)

        if not lname:
            logger.warning("Could not extract 'lname'.")
        else:
            logger.info(f"Successfully extracted lname: {lname}")

        if not timer:
            logger.warning("Could not extract 'timer'.")
        else:
            logger.info(f"Successfully extracted timer: {timer}")

        return lname, timer


    async def fetch_and_cache_params(self, page: Optional[Page] = None) -> None:
        """Fetches and caches lname and timer."""
        logger.debug("Fetching and caching lname and timer.")
        lname, timer = await self.extract_lname_and_timer(page=page)
        if lname:
            self._lname = lname
            self._cached_params["lname"] = lname
        if timer:
            self._timer = timer
            self._cached_params["timer"] = timer

        if not self._lname or not self._timer:
             logger.warning("Failed to extract one or both session parameters (lname/timer). Subsequent API calls might fail or use fallbacks.")


    def clear_cache(self):
        """Clears the cached lname and timer."""
        logger.debug("Clearing cached session parameters (lname/timer).")
        self._lname = None
        self._timer = None
        self._cached_params = {} 