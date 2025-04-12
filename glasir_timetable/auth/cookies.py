import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from playwright.async_api import Page
from glasir_timetable.shared import logger
from glasir_timetable.auth.login import login as playwright_login
from glasir_timetable.storage.profile_manager import ProfileData

DEFAULT_COOKIE_EXPIRY_HOURS = 24

def load_cookies_for_profile(profile: ProfileData) -> Optional[Dict[str, Any]]:
    """
    Load saved cookies for a user profile.
    """
    try:
        if not profile.cookies_path.exists():
            logger.info(f"No cookie file found for user {profile.username}")
            return None
        with open(profile.cookies_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not all(k in data for k in ("cookies", "created_at", "expires_at")):
            logger.warning(f"Invalid cookie file format for user {profile.username}")
            return None
        return data
    except Exception:
        logger.error(f"Failed to load cookies for user {profile.username}")
        return None

def save_cookies_for_profile(profile: ProfileData, cookie_data: Dict[str, Any]) -> None:
    """
    Save cookies for a user profile.
    """
    try:
        os.makedirs(profile.base_dir, exist_ok=True)
        with open(profile.cookies_path, "w", encoding="utf-8") as f:
            json.dump(cookie_data, f, indent=2)
        logger.info(f"Saved cookies for user {profile.username}")
    except Exception:
        logger.error(f"Failed to save cookies for user {profile.username}")

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
        save_cookies_for_profile(profile, cookie_data)
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
    cookie_data = load_cookies_for_profile(profile)
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