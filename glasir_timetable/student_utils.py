#!/usr/bin/env python3
"""
Utilities for handling student information such as student ID, name, and class.
"""
import os
import json
import re
import logging
from typing import Optional
from glasir_timetable.utils import logger
from glasir_timetable.constants import STUDENT_ID_FILE

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
        # First check if the student ID is already saved
        if os.path.exists(STUDENT_ID_FILE):
            try:
                with open(STUDENT_ID_FILE, 'r') as f:
                    data = json.load(f)
                    # Support both old format (student_id) and new format (id)
                    if data:
                        if 'id' in data and data['id']:
                            logger.info(f"Loaded student ID from file: {data['id']}")
                            return data['id']
                        elif 'student_id' in data and data['student_id']:
                            logger.info(f"Loaded student ID from file (old format): {data['student_id']}")
                            # If using old format, try to update to new format if we have name and class
                            if 'name' in data and 'class' in data:
                                try:
                                    with open(STUDENT_ID_FILE, 'w') as f:
                                        json.dump({
                                            'id': data['student_id'],
                                            'name': data['name'],
                                            'class': data['class']
                                        }, f, indent=4)
                                    logger.info(f"Updated student-id.json to new format")
                                except Exception as e:
                                    logger.error(f"Error updating student-id.json format: {e}")
                            return data['student_id']
            except Exception as e:
                logger.error(f"Error loading student ID from file: {e}")
                # Continue with extraction methods
            
        # Direct extraction methods
        
        # Try to extract from localStorage first
        try:
            local_storage = await page.evaluate("localStorage.getItem('StudentId')")
            if local_storage:
                student_id = local_storage.strip()
                # Save the student ID for future use
                try:
                    # Don't overwrite the name and class if they exist
                    existing_data = {}
                    if os.path.exists(STUDENT_ID_FILE):
                        try:
                            with open(STUDENT_ID_FILE, 'r') as f:
                                existing_data = json.load(f)
                        except Exception:
                            pass
                    
                    # Prepare the data to save
                    save_data = {'id': student_id}
                    if existing_data and 'name' in existing_data and 'class' in existing_data:
                        save_data['name'] = existing_data['name']
                        save_data['class'] = existing_data['class']
                    
                    with open(STUDENT_ID_FILE, 'w') as f:
                        json.dump(save_data, f, indent=4)
                    logger.info(f"Saved student ID to file: {student_id}")
                except Exception as e:
                    logger.error(f"Error saving student ID to file: {e}")
                return student_id
        except Exception:
            pass
            
        # Try to find it in inputs or data attributes
        student_id = await page.evaluate("""() => {
            // Check if it's in a hidden input
            const hiddenInput = document.querySelector('input[name="StudentId"]');
            if (hiddenInput && hiddenInput.value) return hiddenInput.value;
            
            // Check if there's a data attribute with student ID
            const elemWithData = document.querySelector('[data-student-id]');
            if (elemWithData) return elemWithData.getAttribute('data-student-id');
            
            return null;
        }""")
        
        if student_id:
            student_id = student_id.strip()
            # Save the student ID for future use
            try:
                # Don't overwrite the name and class if they exist
                existing_data = {}
                if os.path.exists(STUDENT_ID_FILE):
                    try:
                        with open(STUDENT_ID_FILE, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                
                # Prepare the data to save
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"Saved student ID to file: {student_id}")
            except Exception as e:
                logger.error(f"Error saving student ID to file: {e}")
            return student_id
            
        # Try to find it in script tags or function calls
        content = await page.content()
        
        # Look for MyUpdate function call with student ID
        match = re.search(r"MyUpdate\s*\(\s*['\"](\d+)['\"].*?,.*?['\"]([a-zA-Z0-9-]+)['\"]", content)
        if match:
            student_id = match.group(2).strip()
            # Save the student ID for future use
            try:
                # Don't overwrite the name and class if they exist
                existing_data = {}
                if os.path.exists(STUDENT_ID_FILE):
                    try:
                        with open(STUDENT_ID_FILE, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                
                # Prepare the data to save
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"Saved student ID to file: {student_id}")
            except Exception as e:
                logger.error(f"Error saving student ID to file: {e}")
            return student_id
            
        # Look for a GUID pattern anywhere in the page
        guid_pattern = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
        match = re.search(guid_pattern, content)
        if match:
            student_id = match.group(0).strip()
            # Save the student ID for future use
            try:
                # Don't overwrite the name and class if they exist
                existing_data = {}
                if os.path.exists(STUDENT_ID_FILE):
                    try:
                        with open(STUDENT_ID_FILE, 'r') as f:
                            existing_data = json.load(f)
                    except Exception:
                        pass
                
                # Prepare the data to save
                save_data = {'id': student_id}
                if existing_data and 'name' in existing_data and 'class' in existing_data:
                    save_data['name'] = existing_data['name']
                    save_data['class'] = existing_data['class']
                
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump(save_data, f, indent=4)
                logger.info(f"Saved student ID to file: {student_id}")
            except Exception as e:
                logger.error(f"Error saving student ID to file: {e}")
            return student_id
            
        logger.warning("Could not extract student ID from page using any method")
        return None
            
    except Exception as e:
        logger.error(f"Error extracting student ID: {e}")
        return None 