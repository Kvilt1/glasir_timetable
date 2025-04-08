import httpx
import re
import logging
from typing import Tuple, Optional, Dict, Any
from playwright.async_api import Page
from bs4 import BeautifulSoup
import time
import warnings

from .utils.error_utils import handle_errors, GlasirScrapingError
from .utils.param_utils import parse_dynamic_params
from .constants import GLASIR_TIMETABLE_URL

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
TIMER_MYUPDATE_PATTERN = re.compile(r"MyUpdate\s*\([^,]*,[^,]*,[^,]*,[^,]*,\s*(\d+)")
FORD_LNAME_PATTERN = re.compile(r"lname=Ford(\d+,\d+)")

async def get_dynamic_session_params(page: Page) -> Tuple[Optional[str], Optional[int]]:
    """
    DEPRECATED: Use parse_dynamic_params from utils.param_utils instead.
    
    Extract the essential dynamic session parameters (lname and timer) from the page content
    after authentication, minimizing JavaScript execution.
    
    Args:
        page: Authenticated Playwright page object
        
    Returns:
        A tuple containing (lname, timer) values. Either can be None if extraction fails.
    """
    warnings.warn(
        "get_dynamic_session_params is deprecated. Use parse_dynamic_params from utils.param_utils instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    logger.info("Extracting dynamic session parameters (lname/timer) from authenticated page...")
    
    # Get the page content once to avoid multiple requests
    try:
        content = await page.content()
        # Use the new utility function
        return parse_dynamic_params(content)
    except Exception as e:
        logger.error(f"Failed to get page content: {e}")
        return None, None


class AuthSessionManager:
    """Manages dynamic session parameters required for Glasir API interactions."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._lname: Optional[str] = None
        self._timer: Optional[str] = None
        self._cached_params: Dict[str, str] = {}

class SessionParameterError(Exception):
    """Raised when required session parameters cannot be extracted."""
    pass

@property
async def lname(self) -> str:
    """Get the 'lname' parameter, fetching if necessary."""
    if self._lname is None:
        await self.fetch_and_cache_params()
    if self._lname is None:
        logger.error("Failed to extract 'lname' parameter")
        raise SessionParameterError("Missing required session parameter 'lname'")
    return self._lname

@property
async def timer(self) -> str:
    """Get the 'timer' parameter, fetching if necessary."""
    if self._timer is None:
        await self.fetch_and_cache_params()
    if self._timer is None:
        logger.error("Failed to extract 'timer' parameter")
        raise SessionParameterError("Missing required session parameter 'timer'")
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
                 response = await self._client.get(
                     GLASIR_TIMETABLE_URL,
                     timeout=30.0,
                     follow_redirects=True,
                     verify=True
                 )
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

        # Use the new utility function for parameter extraction
        try:
            lname, timer = parse_dynamic_params(content)
            return lname, str(timer) if timer is not None else None
        except Exception as e:
            logger.error(f"Error extracting parameters from content: {e}")
            return None, None


    async def fetch_and_cache_params(self, page: Optional[Page] = None) -> None:
        """
        Fetch and cache 'lname' and 'timer' parameters.
        
        Args:
            page: Optional Playwright page object to extract parameters from.
                 If None, will fetch via httpx.
        """
        logger.debug("Fetching and caching session parameters")
        try:
            # First try to fetch page content using httpx client with robust configuration
            if page is None:
                try:
                    # Configure a robust client for better connection handling
                    client_kwargs = {
                        "timeout": 30.0,
                        "follow_redirects": True,
                        "verify": True
                    }
                    
                    # Verify DNS resolution first
                    try:
                        domain = GLASIR_TIMETABLE_URL.split("//")[1].split("/")[0]
                        import socket
                        socket.gethostbyname(domain)
                    except socket.gaierror as e:
                        logger.error(f"DNS resolution failed for {domain}: {e}")
                        raise httpx.ConnectError(f"DNS resolution failed: {e}")
                    
                    logger.info("Fetching timetable page to extract dynamic parameters")
                    response = await self._client.get(
                        GLASIR_TIMETABLE_URL,
                        **client_kwargs
                    )
                    response.raise_for_status()
                    content = response.text
                    
                    # Use the utility function to parse parameters
                    lname, timer = parse_dynamic_params(content)
                except Exception as e:
                    logger.error(f"Failed to fetch parameters via httpx: {e}")
                    lname, timer = None, None
            else:
                # If page is provided, use it
                logger.info("Using provided Playwright page to extract dynamic parameters")
                try:
                    content = await page.content()
                    lname, timer = parse_dynamic_params(content)
                except Exception as e:
                    logger.error(f"Failed to extract parameters from page: {e}")
                    lname, timer = None, None
                
            # Cache the extracted values
            if lname:
                self._lname = lname
                self._cached_params["lname"] = lname
                logger.debug(f"Cached lname parameter: {lname}")
            else:
                logger.warning("Failed to extract lname parameter")
                
            if timer:
                self._timer = str(timer)
                self._cached_params["timer"] = str(timer)
                logger.debug(f"Cached timer parameter: {timer}")
            else:
                logger.warning("Failed to extract timer parameter")
                
            # For timer, we can still use a fallback (current timestamp)
            if not self._timer:
                current_time = str(int(time.time() * 1000))
                self._timer = current_time
                self._cached_params["timer"] = current_time
                logger.warning(f"Using current timestamp for timer: {current_time}")
                
        except Exception as e:
            logger.error(f"Error fetching session parameters: {e}")
            # Only set timer fallback, not lname
            self._timer = self._timer or str(int(time.time() * 1000))

    def clear_cache(self):
        """Clear all cached session parameters to force refresh on next use."""
        logger.info("Clearing session parameter cache")
        self._lname = None
        self._timer = None
        self._cached_params = {} 