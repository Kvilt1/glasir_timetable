#!/usr/bin/env python3
"""
Utilities for handling student information such as student ID, name, and class.
Supports per-account persistent storage of student info.
"""
import os
import json
import re
import logging
from typing import Optional
from glasir_timetable.utils import logger

# Default student ID path (global)
student_id_path = "glasir_timetable/student-id.json"

def set_student_id_path(path: str):
    global student_id_path
    student_id_path = path
    logger.info(f"[DEBUG] Student ID path set to: {student_id_path}")
def set_student_id_path_for_user(username: str):
    """
    Set the student_id_path global variable to the per-user student-id.json path.
    """
    path = os.path.join(os.path.dirname(__file__), "accounts", username, "student-id.json")
    set_student_id_path(path)

async def get_student_id(page) -> Optional[str]:
    """
    Extract the student ID from the page or saved file.

    - Checks if student-id.json exists and contains 'id', returns it if so.
    - Otherwise, extracts GUID, name, and class from page content.
    - Saves all three fields merged into the JSON file.
    - Returns the ID or None.

    Args:
        page: The Playwright page object

    Returns:
        str or None
    """
    try:
        # Check saved file first
        if os.path.exists(student_id_path):
            try:
                with open(student_id_path, 'r') as f:
                    data = json.load(f)
                if data and 'id' in data and data['id']:
                    logger.info(f"[DEBUG] (get_student_id) Loaded ID from file: {data['id']}")
                    return data['id']
            except Exception as e:
                logger.warning(f"[DEBUG] (get_student_id) Failed to load ID from file: {e}")

        # Extract from page content
        try:
            content = await page.content()
        except Exception as e:
            logger.error(f"[DEBUG] (get_student_id) Cannot get page content: {e}")
            return None

        # Extract GUID
        guid_match = re.search(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}", content)
        student_id = guid_match.group(0).strip() if guid_match else None

        # Extract name and class
        name_class_match = re.search(r"N[æ&aelig;]mingatímatalva:\s*([^,]+),\s*([^\s<]+)", content, re.IGNORECASE)
        student_name = name_class_match.group(1).strip() if name_class_match else None
        student_class = name_class_match.group(2).strip() if name_class_match else None

        # Save merged info if ID found
        if student_id:
            try:
                existing = {}
                if os.path.exists(student_id_path):
                    try:
                        with open(student_id_path, 'r') as f:
                            existing = json.load(f)
                    except Exception:
                        pass
                merged = dict(existing) if isinstance(existing, dict) else {}
                merged['id'] = student_id
                if student_name:
                    merged['name'] = student_name
                if student_class:
                    merged['class'] = student_class
                with open(student_id_path, 'w') as f:
                    json.dump(merged, f, indent=4)
                logger.info(f"[DEBUG] (get_student_id) Saved ID, name, class to file: {merged}")
            except Exception as e:
                logger.warning(f"[DEBUG] (get_student_id) Failed to save ID/name/class: {e}")
            return student_id

        logger.warning("[DEBUG] (get_student_id) Could not extract student ID from page content")
        return None

    except Exception as e:
        logger.error(f"[DEBUG] (get_student_id) Unexpected error: {e}")
        return None


def get_account_student_info_path(username: str) -> str:
    """
    Get the path to the student_info.json file for a given account.
    """
    base_dir = os.path.join("glasir_timetable", "accounts", username)
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "student_info.json")


def load_student_info(username: str) -> Optional[dict]:
    """
    Load student info (id, name, class) for the given account.
    Returns None if not found or invalid.
    """
    path = get_account_student_info_path(username)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if all(k in data for k in ("id", "name", "class")):
            return data
    except Exception as e:
        logger.error(f"Error loading student info for account '{username}': {e}")
    return None


def save_student_info(username: str, info: dict) -> None:
    """
    Save student info (id, name, class) for the given account.
    """
    path = get_account_student_info_path(username)
    try:
        with open(path, "w") as f:
            json.dump(info, f, indent=4)
        logger.info(f"Saved student info for account '{username}' to {path}")
    except Exception as e:
        logger.error(f"Error saving student info for account '{username}': {e}")


async def extract_and_save_student_info(page, username: str) -> Optional[dict]:
    """
    Extract student info from the Playwright page and save it for the account.
    If info already exists, load and return it.
    """
    existing = load_student_info(username)
    if existing:
        return existing

    # Attempt extraction
    try:
        # Check if page is open
        try:
            _ = await page.title()
        except Exception as e:
            logger.error(f"Cannot access page to extract student info: {e}")
            return None

        # Extract name and class using JS
        try:
            student_name = await page.evaluate(
                "document.querySelector('.main-content h1')?.textContent.trim() || 'Unknown'"
            )
            class_name = await page.evaluate(
                "document.querySelector('.main-content p')?.textContent.match(/Class: ([^,]+)/)?.[1] || 'Unknown'"
            )
        except Exception as e:
            logger.warning(f"Error extracting student name/class via JS: {e}")
            student_name = "Unknown"
            class_name = "Unknown"

        # Extract student ID using existing function
        student_id = await get_student_id(page)
        if not student_id:
            logger.error("Failed to extract student ID during student info extraction")
            return None

        info = {
            "id": student_id,
            "name": student_name,
            "class": class_name
        }
        save_student_info(username, info)
        return info

    except Exception as e:
        logger.error(f"Failed to extract and save student info for account '{username}': {e}")
        return None

import re

async def get_or_extract_student_info(page, weeks_html: str) -> dict:
    """
    Load student info (id, name, class) from per-account file if available.
    If missing, extract from weeks API HTML response and save.

    Args:
        page: Playwright page object (for fallback ID extraction)
        weeks_html: HTML response from weeks API (udvalg.asp)

    Returns:
        dict with keys 'id', 'name', 'class'
    """
    # Try load from file
    info = None
    try:
        if os.path.exists(student_id_path):
            with open(student_id_path, 'r') as f:
                info = json.load(f)
            if info and all(k in info and info[k] for k in ("id", "name", "class")):
                logger.info(f"[DEBUG] Loaded student info from file: {info}")
                return info
    except Exception as e:
        logger.warning(f"[DEBUG] Could not load student info from file: {e}")

    # Extract student ID (reuse existing function)
    student_id = None
    try:
        student_id = await get_student_id(page)
    except Exception as e:
        logger.warning(f"[DEBUG] Could not extract student ID: {e}")

    # Parse weeks_html for name and class
    student_name = None
    student_class = None
    try:
        match = re.search(r"N[æ&aelig;]mingatímatalva:\s*([^,]+),\s*([^\s<]+)", weeks_html, re.IGNORECASE)
        if match:
            student_name = match.group(1).strip()
            student_class = match.group(2).strip()
            logger.info(f"[DEBUG] Extracted student name/class from weeks HTML: {student_name}, {student_class}")
    except Exception as e:
        logger.warning(f"[DEBUG] Could not parse weeks HTML for student info: {e}")

    # Save if we have at least ID
    info = {}
    if student_id:
        info['id'] = student_id
    if student_name:
        info['name'] = student_name
    if student_class:
        info['class'] = student_class

    # Fill missing with "Unknown"
    if 'name' not in info or not info['name']:
        info['name'] = "Unknown"
    if 'class' not in info or not info['class']:
        info['class'] = "Unknown"

    # Save to file if we have ID
    if 'id' in info and info['id']:
        try:
            with open(student_id_path, 'w') as f:
                json.dump(info, f, indent=4)
            logger.info(f"[DEBUG] Saved student info to file: {info}")
        except Exception as e:
            logger.warning(f"[DEBUG] Could not save student info to file: {e}")

    return info
    return None