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

# Track if console listener is already attached
_console_listener_attached = False

class JavaScriptIntegrationError(Exception):
    """Exception raised for errors in JavaScript integration."""
    pass

async def inject_timetable_script(page):
    """
    Inject the timetable navigation JavaScript into the page.
    
    Args:
        page: The Playwright page object
        
    Raises:
        JavaScriptIntegrationError: If the script could not be injected or evaluated
    """
    try:
        # Get the path to the JavaScript file
        script_path = Path(__file__).parent / "timetable_navigation.js"
        
        # Check if the file exists
        if not script_path.exists():
            raise JavaScriptIntegrationError(f"JavaScript file not found at {script_path}")
        
        # Read the JavaScript code
        with open(script_path, "r") as f:
            js_code = f.read()
        
        # Inject the script into the page
        await page.evaluate(js_code)
        print("JavaScript navigation script injected")
        
        # Verify that the script was properly injected by checking the glasirTimetable object
        check_result = await page.evaluate("typeof window.glasirTimetable === 'object'")
        if not check_result:
            raise JavaScriptIntegrationError("JavaScript integration failed - glasirTimetable object not found")
        
        print("JavaScript integration verified")
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to inject JavaScript: {str(e)}")

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
    try:
        # Check if the MyUpdate function exists using our injected function
        exists = await page.evaluate("glasirTimetable.checkMyUpdateExists()")
        if exists:
            print("MyUpdate function verified and available")
            return True
        else:
            print("WARNING: MyUpdate function not found on the page!")
            return False
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to verify MyUpdate function: {str(e)}")

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
    try:
        student_id = await page.evaluate("glasirTimetable.getStudentId()")
        if not student_id:
            raise JavaScriptIntegrationError("Could not extract student ID from the page")
        
        # Validate the format of the student ID (should be a GUID)
        if not re.match(r'^[{]?[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}[}]?$', student_id):
            print(f"WARNING: Student ID does not match expected GUID format: {student_id}")
        
        print(f"Found student ID: {student_id}")
        return student_id
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to get student ID: {str(e)}")

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
    try:
        # If no student ID provided, extract it from the page
        if student_id is None:
            student_id = await get_student_id(page)
        
        # Verify MyUpdate exists before attempting navigation
        if not await verify_myupdate_function(page):
            raise JavaScriptIntegrationError("Cannot navigate: MyUpdate function not available")
        
        # Call the JavaScript function to navigate
        print(f"Navigating to week offset {week_offset}...")
        week_info = await page.evaluate(f"glasirTimetable.navigateToWeek({week_offset}, '{student_id}')")
        
        # Wait for navigation to complete (additional safeguard)
        await page.wait_for_load_state("networkidle")
        
        # Validate the returned week info
        if not week_info or not week_info.get('weekNumber'):
            print("WARNING: Navigation succeeded but returned incomplete week information")
        else:
            print(f"Navigated to: Week {week_info.get('weekNumber')} ({week_info.get('startDate')} - {week_info.get('endDate')})")
        
        return week_info
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to navigate to week {week_offset}: {str(e)}")

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
    try:
        # Extract data using JavaScript
        js_data = await page.evaluate("glasirTimetable.extractTimetableData()")
        
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
            print("WARNING: No classes found in the timetable data")
        
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
            print("WARNING: Week number is missing in extracted data")
        
        return timetable_data, {
            "week_num": week_info.get("weekNumber"),
            "year": week_info.get("year"),
            "start_date": week_info.get("startDate"),
            "end_date": week_info.get("endDate")
        }
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to extract timetable data: {str(e)}")

async def return_to_baseline_js(page, original_week_offset=0, student_id=None):
    """
    Return to the baseline week (usually the current week) using JavaScript navigation.
    
    Args:
        page: The Playwright page object
        original_week_offset: The offset of the original week (default: 0 for current week)
        student_id: The student ID GUID. If None, it will be extracted from the page.
        
    Returns:
        dict: Information about the week that was navigated to
        
    Raises:
        JavaScriptIntegrationError: If navigation fails
    """
    try:
        # Navigate back to the baseline
        return await navigate_to_week_js(page, original_week_offset, student_id)
    except Exception as e:
        raise JavaScriptIntegrationError(f"Failed to return to baseline week: {str(e)}")

async def extract_homework_content_js(page, lesson_id):
    """
    Extract homework content for a specific lesson using direct JavaScript calls.
    
    Args:
        page: The Playwright page object.
        lesson_id: The unique ID of the lesson from the speech bubble onclick attribute.
        
    Returns:
        str: The extracted homework content, or None if no content was found.
    """
    try:
        # Check if the JavaScript integration is available
        check_result = await page.evaluate("typeof window.glasirTimetable === 'object' && typeof window.glasirTimetable.extractHomeworkContent === 'function'")
        if not check_result:
            print("JavaScript homework extraction not available, falling back to UI method")
            return None
            
        # Call the JavaScript function directly
        homework_content = await page.evaluate(f"glasirTimetable.extractHomeworkContent('{lesson_id}')")
        
        # If content is a string, clean up any HTML tags
        if isinstance(homework_content, str):
            import re
            cleaned_content = re.sub(r'<[^>]*>', '', homework_content)
            return cleaned_content.strip()
        
        return homework_content
    except Exception as e:
        print(f"JavaScript homework extraction failed: {e}")
        return None

def _console_listener(msg):
    """Console listener callback function to print browser console messages."""
    print(f"BROWSER CONSOLE: {msg.text}")

async def extract_all_homework_content_js(page, lesson_ids):
    """
    Extract homework content for multiple lessons in parallel using JavaScript.
    
    Args:
        page: The Playwright page object.
        lesson_ids: List of lesson IDs to extract homework for.
        
    Returns:
        dict: Mapping of lesson IDs to their homework content.
    """
    global _console_listener_attached
    
    try:
        # Check if the JavaScript integration is available
        check_result = await page.evaluate("typeof window.glasirTimetable === 'object' && typeof window.glasirTimetable.extractAllHomeworkContent === 'function'")
        
        if not check_result:
            print("Parallel JavaScript homework extraction not available")
            return {}
            
        # Call the JavaScript function with all lesson IDs
        print(f"Using parallel JavaScript method for homework extraction ({len(lesson_ids)} notes)")
        print(f"Calling JavaScript extractAllHomeworkContent with {len(lesson_ids)} IDs")
        
        # Wait slightly longer before calling to ensure scripts are ready
        await page.wait_for_timeout(200)
        
        # Add console listener to capture JavaScript console logs - only if not already attached
        if not _console_listener_attached:
            page.on("console", _console_listener)
            _console_listener_attached = True
        
        # Call the JavaScript function
        homework_map = await page.evaluate(f"glasirTimetable.extractAllHomeworkContent({json.dumps(lesson_ids)})")
        
        # Debug information about what was returned
        print(f"JavaScript returned homework data for {len(homework_map) if homework_map else 0} lessons")
        for lesson_id, content in (homework_map or {}).items():
            if content:
                print(f"Found homework for {lesson_id}: {content[:30]}...")
            else:
                print(f"No content for {lesson_id}")
        
        # Clean up any HTML tags in the content
        import re
        cleaned_map = {}
        for lesson_id, content in (homework_map or {}).items():
            if isinstance(content, str):
                cleaned_content = re.sub(r'<[^>]*>', '', content).strip()
                cleaned_map[lesson_id] = cleaned_content
                print(f"Cleaned homework for {lesson_id}: {cleaned_content[:30]}...")
            else:
                cleaned_map[lesson_id] = content
                print(f"No cleaning needed for {lesson_id} (value type: {type(content)})")
        
        return cleaned_map
    except Exception as e:
        print(f"Parallel JavaScript homework extraction failed: {e}")
        # Print stack trace for debugging
        import traceback
        traceback.print_exc()
        return {}

async def test_javascript_integration(page):
    """
    Test the JavaScript integration to verify it's working correctly.
    
    Args:
        page: The Playwright page object
        
    Returns:
        bool: True if the integration is working correctly
        
    Raises:
        JavaScriptIntegrationError: If the test fails
    """
    try:
        print("Testing JavaScript integration...")
        
        # 1. Verify MyUpdate function exists
        my_update_exists = await verify_myupdate_function(page)
        if not my_update_exists:
            print("WARNING: MyUpdate function not found, but trying to continue...")
        
        # 2. Try to get student ID
        student_id = await get_student_id(page)
        print(f"Test: Student ID extraction successful - {student_id}")
        
        # 3. Try to extract current week info
        week_info = await page.evaluate("glasirTimetable.extractWeekInfo()")
        print(f"Test: Week info extraction successful - Week {week_info.get('weekNumber')}")
        
        # 4. Try a simple navigation to current week (offset 0) and back
        if my_update_exists:
            current_week = await navigate_to_week_js(page, 0, student_id)
            print(f"Test: Navigation to current week successful - Week {current_week.get('weekNumber')}")
            
            # 5. Test homework extraction function if available
            homework_function_exists = await page.evaluate("typeof window.glasirTimetable.extractHomeworkContent === 'function'")
            if homework_function_exists:
                print("Test: Homework extraction function is available")
                # We don't actually need to call it with real data for the test
            else:
                print("WARNING: Homework extraction function is not available")
        
        print("JavaScript integration test completed successfully")
        return True
    except Exception as e:
        raise JavaScriptIntegrationError(f"JavaScript integration test failed: {str(e)}")

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