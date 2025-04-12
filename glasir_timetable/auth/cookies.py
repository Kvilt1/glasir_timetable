import orjson
import os
import aiofiles # Keep import for consistency, though direct use is removed
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from playwright.async_api import Page
from glasir_timetable.shared import logger
from glasir_timetable.auth.login import login as playwright_login
from glasir_timetable.storage.profile_manager import ProfileData

DEFAULT_COOKIE_EXPIRY_HOURS = 24

async def load_cookies_for_profile(profile: ProfileData) -> Optional[Dict[str, Any]]:
    """
    Load saved cookies for a user profile using ProfileData's async method.
    """
    try:
        # Use the async method from ProfileData
        cookie_data = await profile.load_cookies()
        if cookie_data is None:
             logger.info(f"No cookie data loaded for user {profile.username} via ProfileData.")
             return None

        # Perform validation (optional, could be done in ProfileData too)
        if not isinstance(cookie_data, dict) or not all(k in cookie_data for k in ("cookies", "created_at", "expires_at")):
            logger.warning(f"Invalid cookie data format loaded for user {profile.username}")
            # Optionally delete invalid file? For now, just return None.
            # await profile.delete_cookies_file() # Example if needed
            return None
        return cookie_data
    except Exception as e: # Catch broader exceptions during async load or validation
        logger.error(f"Failed to load cookies for user {profile.username} via ProfileData: {e}")
        return None

async def save_cookies_for_profile(profile: ProfileData, cookie_data: Dict[str, Any]) -> None:
    """
    Save cookies for a user profile using ProfileData's async method.
    """
    try:
        # Use the async method from ProfileData
        await profile.save_cookies(cookie_data)
        # Logging can be handled within save_cookies or kept here if specific context needed
        logger.info(f"Initiated saving cookies for user {profile.username} via ProfileData.")
    except Exception as e:
        logger.error(f"Failed to save cookies for user {profile.username} via ProfileData: {e}")
        # Re-raise or handle as appropriate

def is_cookies_valid(cookie_data: Optional[Dict[str, Any]]) -> bool:
    """
    Check if cookies are still valid (not expired).
    """
    if not cookie_data:
        return False
    try:
        expires_at = datetime.fromisoformat(cookie_data["expires_at"])
        return datetime.now() < expires_at
    except Exception:
        logger.error("Error checking cookie expiry")
        return False

async def refresh_cookies_for_profile(
    profile: ProfileData,
    page: Page,
    username: str,
    password: str,
    expiry_hours: int = DEFAULT_COOKIE_EXPIRY_HOURS
) -> Optional[Dict[str, Any]]:
    """
    Perform login and save fresh cookies for the profile.
    """
    try:
        await playwright_login(page, username, password)
        cookies = await page.context.cookies()
        cookie_data = {
            "cookies": cookies,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        }
        await save_cookies_for_profile(profile, cookie_data)
        return cookie_data
    except Exception:
        logger.error(f"Failed to refresh cookies for user {profile.username}")
        return None

async def get_valid_cookies_for_profile(
    profile: ProfileData,
    page: Page,
    username: str,
    password: str,
    expiry_hours: int = DEFAULT_COOKIE_EXPIRY_HOURS
) -> Dict[str, Any]:
    """
    Load cookies for profile, refresh if expired or missing.
    """
    cookie_data = await load_cookies_for_profile(profile)
    if not is_cookies_valid(cookie_data):
        logger.info(f"Cookies expired or missing for user {profile.username}, refreshing...")
        cookie_data = await refresh_cookies_for_profile(profile, page, username, password, expiry_hours)
        if not cookie_data:
            raise RuntimeError(f"Failed to refresh cookies for user {profile.username}")
    else:
        logger.info(f"Using existing valid cookies for user {profile.username}")
    return cookie_data

async def inject_cookies_to_context(page: Page, cookie_data: Dict[str, Any]) -> None:
    """
    Inject saved cookies into Playwright context.
    """
    try:
        cookies = cookie_data.get("cookies", [])
        await page.context.add_cookies(cookies)
        logger.info("Injected cookies into Playwright context")
    except Exception:
        logger.error("Failed to inject cookies into Playwright context")

def export_cookies_for_httpx(cookie_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert saved cookies to a dict for httpx.
    """
    cookies_list = cookie_data.get("cookies", [])
    cookie_dict = {}
    for c in cookies_list:
        name = c.get("name")
        value = c.get("value")
        if name and value:
            cookie_dict[name] = value
    return cookie_dict