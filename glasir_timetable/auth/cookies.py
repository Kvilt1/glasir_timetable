
from datetime import datetime
from typing import Optional, Dict, Any
from glasir_timetable.shared import logger
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
