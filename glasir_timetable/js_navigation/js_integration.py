#!/usr/bin/env python3
"""
Integration module for JavaScript-based navigation of the Glasir timetable system.
This module injects and uses JavaScript functions to navigate the timetable instead
of simulating UI interactions.
"""
import os
import json
from pathlib import Path
import time
import re
import asyncio
import logging
from glasir_timetable import logger, add_error
from glasir_timetable.utils.error_utils import (
    evaluate_js_safely,
    error_screenshot_context,
    register_console_listener,
    unregister_console_listener,
    handle_errors,
    JavaScriptError
)

# JavaScript content cache
_JS_CACHE = None

class JavaScriptIntegrationError(Exception):
    """Exception raised for errors in JavaScript integration."""
    pass

@handle_errors(error_category="javascript_errors", error_class=JavaScriptIntegrationError)
def get_timetable_script():
    """
    Get the timetable navigation JavaScript content.
    Uses caching to avoid reading the file on every call.
    
    Returns:
        str: The JavaScript code
        
    Raises:
        JavaScriptIntegrationError: If the JavaScript file could not be read
    """
    global _JS_CACHE
    
    # Return cached content if available
    if _JS_CACHE is not None:
        return _JS_CACHE
    
    # Get the path to the JavaScript file
    script_path = Path(__file__).parent / "timetable_navigation.js"
    
    # Check if the file exists
    if not script_path.exists():
        raise JavaScriptIntegrationError(f"JavaScript file not found at {script_path}")
    
    # Read the JavaScript code and cache it
    with open(script_path, "r") as f:
        _JS_CACHE = f.read()
    
    logger.info("JavaScript file loaded and cached")
    return _JS_CACHE

async def inject_timetable_script(page):
    """
    Inject the timetable navigation JavaScript into the page.
    
    Args:
        page: The Playwright page object
        
    Raises:
        JavaScriptIntegrationError: If the script could not be injected or evaluated
    """
    async with error_screenshot_context(page, "inject_script", "javascript_errors"):
        # Get the JavaScript code from cache
        js_code = get_timetable_script()
        
        # Inject the script into the page
        await evaluate_js_safely(
            page, 
            js_code, 
            error_message="Failed to inject JavaScript navigation script"
        )
        logger.info("JavaScript navigation script injected")
        
        # Verify that the script was properly injected by checking the glasirTimetable object
        check_result = await evaluate_js_safely(
            page,
            "typeof window.glasirTimetable === 'object'",
            error_message="Failed to verify JavaScript integration"
        )
        
        if not check_result:
            raise JavaScriptIntegrationError("JavaScript integration failed - glasirTimetable object not found")
        
        # Ensure console listener is attached
        register_console_listener(page)
        
        logger.info("JavaScript integration verified")

async def verify_myupdate_function(page):
    """
    Verify that the MyUpdate function exists and is callable.
    
    Args:
        page: The Playwright page object
        
    Returns:
        bool: True if the function exists and is callable
        
    Raises:
        JavaScriptIntegrationError: If the verification fails
    """
    async with error_screenshot_context(page, "verify_myupdate", "javascript_errors"):
        # Check if the MyUpdate function exists using our injected function
        exists = await evaluate_js_safely(
            page,
            "glasirTimetable.checkMyUpdateExists()",
            error_message="Failed to verify MyUpdate function"
        )
        
        if exists:
            logger.info("MyUpdate function verified and available")
            return True
        else:
            logger.warning("WARNING: MyUpdate function not found on the page!")
            return False

async def get_student_id(page):
    """
    Get the student ID from the page using the injected JavaScript.
    
    Args:
        page: The Playwright page object
        
    Returns:
        str: The student ID GUID
        
    Raises:
        JavaScriptIntegrationError: If the student ID could not be extracted
    """
    async with error_screenshot_context(page, "get_student_id", "javascript_errors"):
        student_id = await evaluate_js_safely(
            page,
            "glasirTimetable.getStudentId()",
            error_message="Could not extract student ID from the page"
        )
        
        if not student_id:
            raise JavaScriptIntegrationError("Could not extract student ID from the page")
        
        # Validate the format of the student ID (should be a GUID)
        if not re.match(r'^[{]?[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}[}]?$', student_id):
            logger.warning(f"WARNING: Student ID does not match expected GUID format: {student_id}")
        
        logger.info(f"Found student ID: {student_id}")
        return student_id

async def navigate_to_week_js(page, week_offset, student_id=None):
    """
    Navigate to a specific week using the JavaScript MyUpdate function.
    
    Args:
        page: The Playwright page object
        week_offset: The offset from the current week (0=current, 1=next, -1=previous)
        student_id: The student ID GUID. If None, it will be extracted from the page.
        
    Returns:
        dict: Information about the week that was navigated to
        
    Raises:
        JavaScriptIntegrationError: If navigation fails
    """
    async with error_screenshot_context(page, f"navigate_week_{week_offset}", "navigation_errors"):
        # If no student ID provided, extract it from the page
        if student_id is None:
            student_id = await get_student_id(page)
        
        # Verify MyUpdate exists before attempting navigation
        if not await verify_myupdate_function(page):
            raise JavaScriptIntegrationError("Cannot navigate: MyUpdate function not available")
        
        # Call the JavaScript function to navigate
        logger.info(f"Navigating to week offset {week_offset}...")
        week_info = await evaluate_js_safely(
            page,
            f"glasirTimetable.navigateToWeek({week_offset}, '{student_id}')",
            error_message=f"Failed to navigate to week {week_offset}"
        )
        
        # Wait for navigation to complete (additional safeguard)
        await page.wait_for_load_state("networkidle")
        
        # Validate the returned week info
        if not week_info or not week_info.get('weekNumber'):
            logger.warning("WARNING: Navigation succeeded but returned incomplete week information")
        else:
            logger.info(f"Navigated to: Week {week_info.get('weekNumber')} ({week_info.get('startDate')} - {week_info.get('endDate')})")
        
        return week_info

async def extract_timetable_data_js(page, teacher_map=None):
    """
    Extract timetable data using the injected JavaScript functions.
    
    Args:
        page: The Playwright page object
        teacher_map: Optional dictionary mapping teacher initials to full names
        
    Returns:
        tuple: (timetable_data, week_info) where timetable_data is the structured data and
               week_info contains week metadata
               
    Raises:
        JavaScriptIntegrationError: If data extraction fails
    """
    async with error_screenshot_context(page, "extract_timetable", "extraction_errors"):
        # Extract data using JavaScript
        js_data = await evaluate_js_safely(
            page,
            "glasirTimetable.extractTimetableData()",
            error_message="Failed to extract timetable data"
        )
        
        if not js_data:
            raise JavaScriptIntegrationError("Failed to extract timetable data - empty response")
        
        # Get week info
        week_info = js_data.get("weekInfo", {})
        if not week_info:
            raise JavaScriptIntegrationError("Failed to extract week information")
        
        # Get class data and enhance it with teacher names from the provided map
        classes = js_data.get("classes", [])
        
        # Check if we found any classes
        if not classes:
            logger.warning("WARNING: No classes found in the timetable data")
        
        # If teacher_map was provided, use it to replace the teacherFullName field
        if teacher_map:
            for class_info in classes:
                teacher_code = class_info.get("teacher")
                if teacher_code and teacher_code in teacher_map:
                    class_info["teacherFullName"] = teacher_map[teacher_code]
        
        # Structure the data in the format expected by the application
        timetable_data = {
            "week_number": week_info.get("weekNumber"),
            "year": week_info.get("year"),
            "date_range": {
                "start_date": week_info.get("startDate"),
                "end_date": week_info.get("endDate")
            },
            "classes": classes
        }
        
        # Ensure essential fields are present
        if not timetable_data["week_number"]:
            logger.warning("WARNING: Week number is missing in extracted data")
        
        return timetable_data, {
            "week_num": week_info.get("weekNumber"),
            "year": week_info.get("year"),
            "start_date": week_info.get("startDate"),
            "end_date": week_info.get("endDate")
        }

async def return_to_baseline_js(page, original_week_offset=0, student_id=None):
    """
    Return to the baseline week (usually the current week) using JavaScript navigation.
    
    Args:
        page: The Playwright page object
        original_week_offset: The offset to navigate to (defaults to 0, the current week)
        student_id: The student ID GUID. If None, it will be extracted from the page.
        
    Raises:
        JavaScriptIntegrationError: If navigation fails
    """
    # Use existing navigate_to_week_js function with baseline week offset
    return await navigate_to_week_js(page, original_week_offset, student_id)

async def extract_homework_content_js(page, lesson_id):
    """
    Extract homework content for a specific lesson using JavaScript.
    
    Args:
        page: The Playwright page object
        lesson_id: The ID of the lesson to extract homework for
        
    Returns:
        dict: The homework content
        
    Raises:
        JavaScriptIntegrationError: If homework extraction fails
    """
    async with error_screenshot_context(page, f"extract_homework_{lesson_id}", "extraction_errors"):
        homework = await evaluate_js_safely(
            page,
            f"glasirTimetable.extractHomeworkContent('{lesson_id}')",
            error_message=f"Failed to extract homework for lesson {lesson_id}"
        )
        
        if homework:
            logger.info(f"Extracted homework for lesson {lesson_id}")
        else:
            logger.info(f"No homework found for lesson {lesson_id}")
            
        return homework

async def extract_all_homework_content_js(page, lesson_ids):
    """
    Extract homework content for multiple lessons using JavaScript.
    
    Args:
        page: The Playwright page object
        lesson_ids: List of lesson IDs to extract homework for
        
    Returns:
        dict: Dictionary mapping lesson IDs to homework content
        
    Raises:
        JavaScriptIntegrationError: If homework extraction fails
    """
    if not lesson_ids:
        logger.warning("No lesson IDs provided for homework extraction")
        return {}
    
    homework_data = {}
    
    # Ensure console listener is attached
    register_console_listener(page)
    
    # Track extraction progress
    from tqdm import tqdm
    logger.info(f"Extracting homework for {len(lesson_ids)} lessons...")
    
    for lesson_id in tqdm(lesson_ids, desc="Extracting homework"):
        try:
            # Extract homework for this lesson
            homework = await extract_homework_content_js(page, lesson_id)
            
            # Store result (even if empty)
            homework_data[lesson_id] = homework
            
            # Small delay to avoid overloading the server
            await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error extracting homework for lesson {lesson_id}: {e}")
            add_error("homework_errors", f"Failed to extract homework for lesson {lesson_id}", str(e))
            
            # Store null for this lesson
            homework_data[lesson_id] = None
    
    logger.info(f"Extracted homework data for {len(homework_data)} lessons")
    return homework_data

async def test_javascript_integration(page):
    """
    Test the JavaScript integration to ensure it's working correctly.
    
    Args:
        page: The Playwright page object
        
    Raises:
        JavaScriptIntegrationError: If the test fails
    """
    async with error_screenshot_context(page, "js_test", "javascript_errors"):
        logger.info("Testing JavaScript integration...")
        
        # Step 1: Inject the script
        await inject_timetable_script(page)
        
        # Step 2: Verify key functions are available
        test_functions = [
            "glasirTimetable.checkMyUpdateExists",
            "glasirTimetable.getStudentId",
            "glasirTimetable.navigateToWeek",
            "glasirTimetable.extractTimetableData"
        ]
        
        for func_name in test_functions:
            result = await evaluate_js_safely(
                page,
                f"typeof {func_name} === 'function'",
                error_message=f"Function {func_name} is not available"
            )
            
            if not result:
                raise JavaScriptIntegrationError(f"JavaScript integration test failed: Function {func_name} is not available")
                
        # Step 3: Try to extract current page data
        student_id = await get_student_id(page)
        if not student_id:
            raise JavaScriptIntegrationError("JavaScript integration test failed: Could not get student ID")
            
        # Test navigation if MyUpdate is available
        my_update_exists = await verify_myupdate_function(page)
        if my_update_exists:
            # Try a simple navigation to the current week (offset 0)
            week_info = await navigate_to_week_js(page, 0, student_id)
            if not week_info or not week_info.get('weekNumber'):
                raise JavaScriptIntegrationError("JavaScript integration test failed: Navigation unsuccessful")
                
        logger.info("JavaScript integration test passed")
        return True

# Export all functions that should be importable
__all__ = [
    "JavaScriptIntegrationError",
    "inject_timetable_script",
    "verify_myupdate_function",
    "get_student_id",
    "navigate_to_week_js",
    "extract_timetable_data_js",
    "return_to_baseline_js",
    "test_javascript_integration",
    "extract_homework_content_js",
    "extract_all_homework_content_js"  # Add the new function to exports
] 