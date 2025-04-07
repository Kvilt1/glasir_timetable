#!/usr/bin/env python3
"""
Authentication utilities for the Glasir Timetable application.

This module provides helper functions for checking authentication data validity.
"""

import os
import json
from glasir_timetable.cookie_auth import load_cookies, is_cookies_valid
from glasir_timetable.student_utils import load_student_info
from glasir_timetable import logger

def is_auth_data_valid_simple(username: str, cookie_path: str) -> bool:
    """
    Check if both cookies and student info are valid (simple boolean).

    Returns True if:
    - cookies.json exists and is not expired
    - student_info.json exists and contains id, name, class
    """
    try:
        cookie_data = load_cookies(cookie_path)
        if not cookie_data or not is_cookies_valid(cookie_data):
            logger.debug(f"Cookies invalid or expired for user {username}")
            return False
    except Exception as e:
        logger.debug(f"Error checking cookie validity: {e}")
        return False

    try:
        student_info = load_student_info(username)
        if not student_info:
            logger.debug(f"Student info missing or invalid for user {username}")
            return False
    except Exception as e:
        logger.debug(f"Error checking student info: {e}")
        return False

    logger.debug(f"All authentication data valid for user {username}")
    return True

def is_full_auth_data_valid(username, cookie_path):
    """
    Check if both cookies and student ID are valid for the given user.
    Returns (is_valid: bool, student_info_dict: dict or None)
    """
    try:
        cookie_data = load_cookies(cookie_path)
        cookies_ok = is_cookies_valid(cookie_data)
    except Exception:
        cookies_ok = False

    # Check student-id.json file directly
    try:
        student_id_path = os.path.join("glasir_timetable", "accounts", username, "student-id.json")
        info = None
        if os.path.exists(student_id_path):
            with open(student_id_path, "r") as f:
                info = json.load(f)
        id_ok = info is not None and "id" in info and info["id"]
    except Exception:
        info = None
        id_ok = False

    logger.info(f"[DEBUG] is_full_auth_data_valid: cookies_ok={cookies_ok}")
    logger.info(f"[DEBUG] is_full_auth_data_valid: student_id_info={info}")
    logger.info(f"[DEBUG] is_full_auth_data_valid: id_ok={id_ok}")

    return (cookies_ok and id_ok), info