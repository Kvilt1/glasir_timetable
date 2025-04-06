#!/usr/bin/env python3
"""
Authentication utilities for the Glasir Timetable application.

This module provides helper functions for checking authentication data validity.
"""

from glasir_timetable.cookie_auth import load_cookies, is_cookies_valid
from glasir_timetable.student_utils import load_student_info
from glasir_timetable import logger

def is_full_auth_data_valid(username: str, cookie_path: str) -> bool:
    """
    Check if both cookies and student info are valid.

    Returns True if:
    - cookies.json exists and is not expired
    - student_info.json exists and contains id, name, class
    
    Args:
        username: The username for the account
        cookie_path: Path to the cookie file
        
    Returns:
        bool: True if all authentication data is valid, False otherwise
    """
    try:
        # Check cookie validity
        cookie_data = load_cookies(cookie_path)
        if not cookie_data or not is_cookies_valid(cookie_data):
            logger.debug(f"Cookies invalid or expired for user {username}")
            return False
    except Exception as e:
        logger.debug(f"Error checking cookie validity: {e}")
        return False

    try:
        # Check student info validity
        student_info = load_student_info(username)
        if not student_info:
            logger.debug(f"Student info missing or invalid for user {username}")
            return False
    except Exception as e:
        logger.debug(f"Error checking student info: {e}")
        return False

    # Both cookies and student info are valid
    logger.debug(f"All authentication data valid for user {username}")
    return True