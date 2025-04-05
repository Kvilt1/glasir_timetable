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

async def get_student_id(page) -> Optional[str]:
    """
    Extract the student ID from the page.
    
    This function tries multiple methods to extract the student ID:
    1. First checks if the ID is saved in student-id.json
    2. Falls back to direct extraction from the page content
    
    Args:
        page: The Playwright page object
        
    Returns:
        str: The student ID or None if not found
    """
    try:
        logger.info(f"[DEBUG] Checking student-id.json path: {student_id_path}")
        exists = os.path.exists(student_id_path)
        logger.info(f"[DEBUG] Does student-id.json exist at this path? {exists}")
        if exists:
            try:
                with open(student_id_path, 'r') as f:
                    data = json.load(f)
                    # Support both old format (student_id) and new format (id)
                    if data:
                        if 'id' in data and data['id']:
                            logger.info(f"[DEBUG] Loaded student ID from file: {data['id']}")
                            return data['id']
                        elif 'student_id' in data and data['student_id']:
                            logger.info(f"[DEBUG] Loaded student ID from file (old format): {data['student_id']}")
                            # If using old format, try to update to new format if we have name and class
                            if 'name' in data and 'class' in data:
                                try:
                                    with open(student_id_path, 'w') as f:
                                        json.dump({
                                            'id': data['student_id'],
                                            'name': data['name'],
                                            'class': data['class']
                                        }, f, indent=4)
                                    logger.info(f"[DEBUG] Updated student-id.json to new format")
                                except Exception as e:
                                    logger.error(f"[DEBUG] Error updating student-id.json format: {e}")
                            return data['student_id']
            except Exception as e:
                logger.error(f"[DEBUG] Error loading student ID from file: {e}")
                # Continue with extraction methods
        
        logger.info("[DEBUG] student-id.json not found or invalid, attempting extraction from page")
        # Before accessing page, check if it is closed
        try:
            _ = await page.title()
            logger.info("[DEBUG] Page appears to be open, proceeding with extraction")
        except Exception as e:
            logger.error(f"[DEBUG] Cannot access page, it may be closed: {e}")
            return None
        
        # Try to extract from localStorage first
        try:
            local_storage = await page.evaluate("localStorage.getItem('StudentId')")
            if local_storage:
                student_id = local_storage.strip()
                # Save the student ID for future use
                try:
                    existing_data = {}
                    if os.path.exists(student_id_path):
                        try:
                            with open(student_id_path, 'r') as f:
                                existing_data = json.load(f)
                        except Exception:
                            pass
                    save_data = {'id': student_id}
                    if existing_data and 'name' in existing_data and 'class' in existing_data:
                        save_data['name'] = existing_data['name']
                        save_data['class'] = existing_data['class']
                    with open(student_id_path, 'w') as f:
                        json.dump(save_data, f, indent=4)
                    logger.info(f"[DEBUG] Saved student ID from localStorage to file: {student_id}")
                except Exception as e:
                    logger.error(f"[DEBUG] Error saving student ID from localStorage: {e}")
                return student_id
        except Exception:
            pass
        
        # Try to find it in inputs or data attributes
        try:
            student_id = await page.evaluate("""() => {
                const hiddenInput = document.querySelector('input[name="StudentId"]');
                if (hiddenInput && hiddenInput.value) return hiddenInput.value;
                const elemWithData = document.querySelector('[data-student-id]');
                if (elemWithData) return elemWithData.getAttribute('data-student-id');
                return null;
            }""")
        except Exception as e:
            logger.error(f"[DEBUG] Error evaluating page for student ID inputs/data attributes: {e}")
            return None
        
        if student_id:
            student_id = student_id.strip()
            try:
                existing_data = {}
                if os.path.exists(student_id_path):
                    try:
                        with open(student_id_path, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                with open(student_id_path, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"[DEBUG] Saved student ID from inputs/data attributes to file: {student_id}")
            except Exception as e:
                logger.error(f"[DEBUG] Error saving student ID from inputs/data attributes: {e}")
            return student_id
        
        # Try to find it in script tags or function calls
        try:
            content = await page.content()
        except Exception as e:
            logger.error(f"[DEBUG] Cannot get page content, page may be closed: {e}")
            return None
        
        match = re.search(r"MyUpdate\s*\(\s*['\"](\d+)['\"].*?,.*?['\"]([a-zA-Z0-9-]+)['\"]", content)
        if match:
            student_id = match.group(2).strip()
            try:
                existing_data = {}
                if os.path.exists(student_id_path):
                    try:
                        with open(student_id_path, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                with open(student_id_path, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"[DEBUG] Saved student ID from script content to file: {student_id}")
            except Exception as e:
                logger.error(f"[DEBUG] Error saving student ID from script content: {e}")
            return student_id
        
        guid_pattern = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
        match = re.search(guid_pattern, content)
        if match:
            student_id = match.group(0).strip()
            try:
                existing_data = {}
                if os.path.exists(student_id_path):
                    try:
                        with open(student_id_path, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                with open(student_id_path, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"[DEBUG] Saved student ID from GUID pattern to file: {student_id}")
            except Exception as e:
                logger.error(f"[DEBUG] Error saving student ID from GUID pattern: {e}")
            return student_id
        
        logger.warning("[DEBUG] Could not extract student ID from page using any method")
        return None
        
    except Exception as e:
        logger.error(f"[DEBUG] Error extracting student ID: {e}")
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