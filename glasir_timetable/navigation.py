#!/usr/bin/env python3
"""
Centralized navigation utilities for the Glasir Timetable application.

This module provides unified functions for week navigation, eliminating code duplication
and providing consistent patterns for JavaScript-based navigation throughout the codebase.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional, Callable, Set
from contextlib import asynccontextmanager
from datetime import datetime
import re
import json
import time

from playwright.async_api import Page
from glasir_timetable import logger, add_error
from glasir_timetable.extractors import extract_timetable_data
# Import directly from homework_parser to avoid circular import
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.api_client import (
    fetch_homework_for_lessons,
    fetch_timetable_for_week,
    fetch_weeks_data,
    fetch_timetables_for_weeks,
    get_student_id,
    extract_week_range
)
from glasir_timetable.js_navigation.js_integration import (
    navigate_to_week_js,
    return_to_baseline_js,
    JavaScriptIntegrationError,
    verify_myupdate_function,
)
from glasir_timetable.utils import (
    normalize_dates,
    normalize_week_number,
    generate_week_filename,
    save_json_data
)
from glasir_timetable.utils.error_utils import error_screenshot_context
from glasir_timetable.models import TimetableData
from glasir_timetable.utils.model_adapters import dict_to_timetable_data
from glasir_timetable.utils.param_utils import parse_dynamic_params
from glasir_timetable.utils.error_utils import handle_errors, evaluate_js_safely
from glasir_timetable.constants import (
    GLASIR_BASE_URL,
    GLASIR_TIMETABLE_URL,
    STUDENT_ID_FILE
)


@asynccontextmanager
async def with_week_navigation(page, week_offset, student_id, return_to_baseline=True):
    """
    Context manager for safely navigating to a week and ensuring return to baseline.
    
    Args:
        page: The Playwright page object
        week_offset: The offset from the current week (0=current, 1=next, -1=previous)
        student_id: The student ID GUID
        return_to_baseline: Whether to return to current week (baseline) after operation (default: True)
        
    Yields:
        dict: Information about the week that was navigated to, or None if navigation failed
    """
    week_info = None
    try:
        # Navigate to specified week
        week_info = await navigate_to_week_js(page, week_offset, student_id)
        yield week_info
    finally:
        # Return to baseline only if requested
        if return_to_baseline:
            try:
                await return_to_baseline_js(page, 0, student_id)
            except Exception as e:
                logger.error(f"Error returning to baseline: {e}")


async def navigate_and_extract(page, week_offset, teacher_map, student_id, api_cookies=None, use_models=True):
    """
    Navigate to a specific week and extract timetable data using JavaScript-based navigation.
    
    This function uses the JavaScript MyUpdate() function to navigate to a specific week
    offset, then extracts the timetable data from the page, and merges in homework.
    
    Args:
        page: The playwright page object
        week_offset: Week offset (0=current, positive=forward, negative=backward)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID (GUID format)
        api_cookies: Optional cookies for API-based homework extraction
        use_models: Whether to convert the result to Pydantic models
        
    Returns:
        tuple: (timetable_data, week_info, homework_lesson_ids)
    """
    try:
        # Verify the MyUpdate function exists
        my_update_exists = await verify_myupdate_function(page)
        if not my_update_exists:
            logger.error("MyUpdate function not available for JavaScript navigation")
            return None, None, []
            
        # Extract lname value dynamically if we have API cookies
        lname_value = None
        if api_cookies:
            content = await page.content()
            lname_value, _ = parse_dynamic_params(content)
        
        # Navigate to the target week
        logger.info(f"Navigating to week offset {week_offset}...")
        week_info = await navigate_to_week_js(page, week_offset, student_id)
        logger.info(f"Navigated to: {week_info.get('title', f'Week offset {week_offset}')}")
        
        if not week_info:
            return None, None, []
            
        # Extract timetable data including lesson IDs for homework
        timetable_data, week_details, homework_lesson_ids = await extract_timetable_data(
            page, teacher_map, use_models=False  # Always use dictionary during extraction
        )
        
        # Use week_details if available, otherwise use week_info
        # Ensure that the returned week_info has all required keys
        if week_details and 'week_num' in week_details:
            # Use the more detailed information from extraction
            week_info = week_details
        elif week_info:
            # Make sure week_info has all necessary keys
            if 'week_num' not in week_info and 'weekNum' in week_info:
                week_info['week_num'] = week_info['weekNum']
                
            if 'start_date' not in week_info and 'startDate' in week_info:
                week_info['start_date'] = week_info['startDate']
                
            if 'end_date' not in week_info and 'endDate' in week_info:
                week_info['end_date'] = week_info['endDate']
                
            if 'year' not in week_info:
                # Use year from timetable_data weekInfo if available
                if timetable_data and 'weekInfo' in timetable_data and 'year' in timetable_data['weekInfo']:
                    week_info['year'] = timetable_data['weekInfo']['year']
                else:
                    # Fallback to current year
                    week_info['year'] = datetime.now().year
        
        # Handle API-based homework extraction if we have lesson IDs and cookies
        if homework_lesson_ids and api_cookies:
            logger.info(f"Fetching homework via API for {len(homework_lesson_ids)} lessons")
            
            # Use concurrent individual requests directly with dynamic lname value if available
            homework_map = await fetch_homework_for_lessons(
                cookies=api_cookies,
                lesson_ids=homework_lesson_ids,
                lname_value=lname_value
            )
            logger.info(f"Fetched {len(homework_map)} homework entries using concurrent requests")
                
            # Merge homework descriptions into events
            merged_count = 0
            for event in timetable_data.get("events", []):
                lesson_id = event.get("lessonId")
                if lesson_id and lesson_id in homework_map:
                    event["description"] = homework_map[lesson_id]
                    merged_count += 1
            
            logger.info(f"Merged {merged_count} homework descriptions into events")
        
        # Convert to model if requested (after homework merging)
        if use_models:
            model_data, success = dict_to_timetable_data(timetable_data)
            if success:
                return model_data, week_info, homework_lesson_ids
        
        return timetable_data, week_info, homework_lesson_ids
    except JavaScriptIntegrationError as e:
        logger.error(f"JavaScript navigation error: {e}")
        return None, None, []
    except Exception as e:
        logger.error(f"Navigation error: {e}")
        return None, None, []


async def process_single_week(page, week_offset, teacher_map, student_id, output_dir, 
                             api_cookies=None, processed_weeks=None, use_models=True):
    """
    Process a single week, extract and save its timetable data.
    
    Args:
        page: The Playwright page object
        week_offset: Offset from current week (0=current, 1=next, -1=previous)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_weeks: Set of already processed week numbers (to avoid duplicates)
        use_models: Whether to use Pydantic models (default: True)
        
    Returns:
        bool: True if successful, False if failed or already processed
    """
    if processed_weeks is None:
        processed_weeks = set()
    
    # Extract timetable data with model support and fetch homework via API
    timetable_data, week_info, _ = await navigate_and_extract(
        page, week_offset, teacher_map, student_id, api_cookies, use_models=use_models
    )
    
    if not timetable_data:
        return False
    
    # Get week info depending on whether we have a model or dictionary
    if isinstance(timetable_data, TimetableData):
        # Extract from model
        week_num = timetable_data.week_info.week_number
        start_date = timetable_data.week_info.start_date
        end_date = timetable_data.week_info.end_date
        year = timetable_data.week_info.year
        
        # Also update the week_info dictionary to match
        week_info = {
            "week_num": week_num,
            "start_date": start_date,
            "end_date": end_date,
            "year": year
        }
    else:
        # Extract from week_info for dictionary case
        week_num = week_info.get('week_num', 0)
        start_date = week_info.get('start_date', '')
        end_date = week_info.get('end_date', '')
        year = week_info.get('year', datetime.now().year)
    
    # Skip if we've already processed this week
    if week_num in processed_weeks:
        logger.info(f"Skipping week {week_num} (already processed)")
        return False
    
    # Add to processed weeks
    processed_weeks.add(week_num)
    
    # Normalize dates and week number
    start_date, end_date = normalize_dates(start_date, end_date, year)
    week_num = normalize_week_number(week_num)
    
    # Generate filename with standardized format
    filename = generate_week_filename(year, week_num, start_date, end_date)
    output_path = os.path.join(output_dir, filename)
    
    # Save data to JSON file
    result = save_json_data(timetable_data, output_path)
    
    if result:
        logger.info(f"Saved week {week_num} data to {output_path}")
        return True
    else:
        logger.error(f"Failed to save week {week_num} data")
        return False


async def process_weeks(page, directions, teacher_map, student_id, output_dir, 
                       api_cookies=None, processed_weeks=None, use_api=False,
                       lname_value=None, timer_value=None):
    """
    Process multiple weeks using either JavaScript navigation or API-based extraction.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_weeks: Set of already processed week numbers (to avoid duplicates)
        use_api: Whether to use API-based extraction instead of JavaScript navigation
        lname_value: Optional pre-extracted lname value for API requests
        timer_value: Optional pre-extracted timer value for API requests
        
    Returns:
        Set of processed week numbers
    """
    if processed_weeks is None:
        processed_weeks = set()
        
    # Define a progress logging function
    def log_progress(current, total, step_name=""):
        percent = int((current / total) * 100)
        progress_bar = f"[{'=' * (percent // 5)}>{' ' * (20 - (percent // 5))}]"
        logger.info(f"Processing weeks: {progress_bar} {percent}% ({current}/{total}) {step_name}")
    
    # Sort directions to process current week first (offset 0)
    directions = sorted(directions, key=lambda x: abs(x))
    
    # Choose the processing approach based on the use_api flag
    if use_api:
        # Only extract if not provided     
        if lname_value is None or timer_value is None:
            content = await page.content()
            lname_value, timer_value = parse_dynamic_params(content)
        logger.info(f"Using API-based approach with lname={lname_value}, timer={timer_value}")
        
        # Process each week using the API-based method
        total_weeks = len(directions)
        for idx, week_offset in enumerate(directions):
            log_progress(idx + 1, total_weeks, f"Week offset {week_offset}")
            
            # Use API-based processing
            result = await process_single_week_api(
                page=page,
                week_offset=week_offset,
                output_dir=output_dir,
                teacher_map=teacher_map,
                api_cookies=api_cookies,
                lname_value=lname_value,
                timer_value=timer_value
            )
            
            # Check if the processing was successful and has week info
            if result and result.get("success") and not result.get("skipped"):
                # Extract week info from the timetable data that was saved
                # This is a simplified approach - we should enhance process_single_week_api 
                # to return the week_info directly in the result
                week_info_path = os.path.join(output_dir, result.get("filename", ""))
                if os.path.exists(week_info_path):
                    try:
                        with open(week_info_path, 'r', encoding='utf-8') as f:
                            imported_data = json.load(f)
                            if "weekInfo" in imported_data:
                                week_info = imported_data["weekInfo"]
                                if 'year' in week_info and ('weekNumber' in week_info or 'week_num' in week_info):
                                    year = week_info.get('year')
                                    week_num = week_info.get('weekNumber', week_info.get('week_num'))
                                    # Add to processed weeks using standard format
                                    processed_weeks.add(f"{year}-{week_num}")
                                    logger.info(f"Added week {year}-{week_num} to processed weeks")
                    except Exception as e:
                        logger.error(f"Error extracting week info from saved file: {e}")
    else:
        # Use JavaScript-based navigation
        logger.info("Using JavaScript-based navigation approach")
        
        # Process each week using navigation
        total_weeks = len(directions)
        for idx, week_offset in enumerate(directions):
            log_progress(idx + 1, total_weeks, f"Week offset {week_offset}")
            
            # Use navigation-based processing
            processed = await process_single_week(
                page=page,
                week_offset=week_offset,
                teacher_map=teacher_map,
                student_id=student_id,
                output_dir=output_dir,
                api_cookies=api_cookies,
                processed_weeks=processed_weeks
            )
    
    return processed_weeks


async def get_week_directions(args):
    """
    Generate a list of week directions (offsets) based on command-line arguments.
    
    Args:
        args: Command-line arguments
        
    Returns:
        list: Week offset directions
    """
    directions = []
    
    # Forward weeks (positive offsets)
    if args.weekforward:
        for i in range(1, args.weekforward + 1):
            directions.append(i)
    
    # Backward weeks (negative offsets)
    if args.weekbackward:
        for i in range(1, args.weekbackward + 1):
            directions.append(-i)
    
    # If both --weekforward and --weekbackward are provided, sort from closest to current week to farthest
    if args.weekforward and args.weekbackward:
        directions.sort(key=lambda x: abs(x))
    
    return directions 


async def extract_min_max_week_offsets(page, api_cookies=None, use_api=False, student_id=None, lname_value=None, timer_value=None):
    """
    Extract the minimum and maximum week offsets available in the timetable.
    
    Supports both direct HTML parsing (original method) and API-based extraction.
    
    Args:
        page: The Playwright page object containing the timetable
        api_cookies: Optional cookies for API-based extraction (required if use_api=True)
        use_api: Whether to use the API approach rather than HTML parsing
        student_id: Student ID for API requests (required if use_api=True)
        lname_value: Optional lname value for API requests
        timer_value: Optional timer value for API requests
        
    Returns:
        tuple: (min_offset, max_offset) - the earliest and latest available week offsets
        
    Raises:
        ValueError: If no week offset values can be found
    """
    if use_api:
        if not api_cookies:
            logger.error("API cookies required for API-based week range extraction")
            raise ValueError("API cookies required for API-based week range extraction")
            
        if not student_id:
            logger.error("Student ID required for API-based week range extraction")
            raise ValueError("Student ID required for API-based week range extraction")
            
        # Use the API-based approach
        return await extract_week_range(
            cookies=api_cookies,
            student_id=student_id,
            lname_value=lname_value,
            timer_value=timer_value
        )
    else:
        # Original HTML parsing approach
        # Get the page content
        content = await page.content()
        
        # Use regular expressions to find all week offset values in the MyUpdate function calls
        import re
        pattern = r"MyUpdate\('/i/udvalg\.asp', '[^']*&v=(-?\d+)'[^']*\)"
        matches = re.findall(pattern, content)
        
        if not matches:
            logger.error("No week offset values found in page content")
            raise ValueError("Failed to extract week offset range from timetable. Cannot determine available weeks.")
        
        # Convert to integers and find min/max
        offsets = [int(match) for match in matches]
        min_offset = min(offsets)
        max_offset = max(offsets)
        
        logger.info(f"Extracted week offset range: {min_offset} to {max_offset}")
        return min_offset, max_offset


async def process_single_week_api(
    page, 
    week_offset, 
    output_dir, 
    teacher_map, 
    api_cookies=None,
    lname_value=None,
    timer_value=None
):
    """
    DEPRECATED by the concurrent logic in process_weeks when use_api=True.
    Process a single week using the API-based approach. Kept for potential other uses or reference.
    
    Args:
        page: The Playwright page object
        week_offset: Offset from the current week (-1 for previous week, etc.)
        output_dir: Directory to save the JSON file
        teacher_map: Dictionary mapping teacher initials to full names
        api_cookies: Dictionary of cookies for API requests
        lname_value: Optional dynamically extracted lname value to use with API
        timer_value: Optional timer value to use with API
        
    Returns:
        dict: Result of processing, including success status and any errors
              
              NOTE FOR FUTURE IMPROVEMENT: This function should return the week_info
              directly in the result dictionary along with success/failure status.
              This would make it easier for callers to access week_info without
              having to read the saved file.
    """
    logger.warning("process_single_week_api is deprecated for use within process_weeks(use_api=True)")
    try:
        # Extract timetable using API-based approach
        timetable_data, week_info, lesson_ids = await navigate_and_extract_api(
            page, 
            week_offset, 
            teacher_map,
            api_cookies=api_cookies,
            lname_value=lname_value,
            timer_value=timer_value
        )
        
        if not timetable_data:
            return {
                "success": False,
                "error": f"Failed to extract timetable data for week offset {week_offset}"
            }
        
        # Normalize dates - handle format based on type
        if "weekInfo" in timetable_data and isinstance(timetable_data, dict):
            # Extract year and dates from week_info
            week_info = timetable_data.get("weekInfo", {})
            year = week_info.get("year")
            start_date = week_info.get("startDate")
            end_date = week_info.get("endDate")
            
            # Normalize individual dates
            if start_date and end_date and year:
                start_date, end_date = normalize_dates(start_date, end_date, year)
                week_info["startDate"] = start_date
                week_info["endDate"] = end_date
        else:
            # If it's a model or another format, skip normalization here
            logger.warning("Skipping date normalization due to unknown format")
        
        # Normalize week number if needed
        if "weekInfo" in timetable_data and "weekNumber" in timetable_data["weekInfo"]:
            timetable_data["weekInfo"]["weekNumber"] = normalize_week_number(timetable_data["weekInfo"]["weekNumber"])
        
        # Extract values needed for filename generation
        if "weekInfo" in timetable_data:
            week_info_dict = timetable_data["weekInfo"]
            year = week_info_dict.get("year", datetime.now().year)
            week_num = week_info_dict.get("weekNumber", 0)
            start_date = week_info_dict.get("startDate", "")
            end_date = week_info_dict.get("endDate", "")
            
            # Generate the output filename and path
            filename = generate_week_filename(year, week_num, start_date, end_date)
            output_path = os.path.join(output_dir, filename)
        else:
            # Fallback if weekInfo is not available
            logger.error("Could not generate filename: weekInfo missing from timetable data")
            return {
                "success": False,
                "error": "Could not generate filename: weekInfo missing from timetable data"
            }
        
        # If file already exists, skip it
        if os.path.exists(output_path):
            return {
                "success": True,
                "skipped": True,
                "message": f"Week already exported: {filename}"
            }
        
        # Save the JSON data to disk
        save_json_data(timetable_data, output_path)
        
        return {
            "success": True,
            "message": f"Week successfully exported: {filename}",
            "filename": filename
        }
        
    except Exception as e:
        # Log the error and return error data
        logger.error(f"Error processing week offset {week_offset}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return {
            "success": False,
            "error": str(e)
        } 


async def navigate_and_extract_api(
    page, 
    week_offset, 
    teacher_map,
    api_cookies=None,
    lname_value=None,
    timer_value=None
):
    """
    Extract timetable data using API-based approach without page navigation.
    
    Args:
        page: The playwright page object (used mainly for parameter extraction)
        week_offset: Week offset (0=current, positive=forward, negative=backward)
        teacher_map: Dictionary mapping teacher initials to full names
        api_cookies: Cookies for API requests
        lname_value: Optional pre-extracted lname value
        timer_value: Optional pre-extracted timer value
        
    Returns:
        tuple: (timetable_data, week_info, lesson_ids)
    """
    try:
        if not api_cookies:
            logger.error("No API cookies provided")
            return None, None, []
            
        # Get lname_value if not provided
        if lname_value is None:
            content = await page.content()
            lname_value, _ = parse_dynamic_params(content)
            logger.info(f"Extracted lname value: {lname_value}")
        
        # Get timer_value if not provided
        if timer_value is None:
            content = await page.content()
            _, timer_value = parse_dynamic_params(content)
            logger.info(f"Extracted timer value: {timer_value}")
            
        # Get student_id if needed for API calls
        student_id = await get_student_id(page)
        if not student_id:
            logger.error("Could not extract student ID")
            return None, None, []
        
        # Use API to fetch the HTML for the specified week
        week_html = await fetch_timetable_for_week(
            cookies=api_cookies,
            student_id=student_id,
            week_offset=week_offset,
            lname_value=lname_value,
            timer_value=timer_value
        )
        
        if not week_html:
            logger.error("Failed to fetch timetable HTML from API")
            return None, None, []
        
        # Set the HTML content on the page
        # Replace backticks in the HTML with escaped backticks for JavaScript
        escaped_html = week_html.replace('`', '\\`')
        await page.evaluate(f"""
        document.getElementById('MyWindowMain').innerHTML = `{escaped_html}`;
        """)
        
        # Extract timetable data from the current page state
        timetable_data, week_info, lesson_ids = await extract_timetable_data(page, teacher_map)
        
        # Fetch homework
        homework_map = {}
        if api_cookies and lesson_ids:
            homework_map = await fetch_homework_for_lessons(
                cookies=api_cookies,
                lesson_ids=lesson_ids,
                lname_value=lname_value,
                timer_value=timer_value
            )
            
            logger.info(f"Fetched homework for {len(homework_map)}/{len(lesson_ids)} lessons")
            
            # Add homework to timetable data
            merged_count = 0
            for event in timetable_data.get("events", []):
                lesson_id = event.get("lessonId")
                if lesson_id and lesson_id in homework_map:
                    event["description"] = homework_map[lesson_id]
                    merged_count += 1
            
            logger.info(f"Merged {merged_count} homework descriptions into events")
        
        return timetable_data, week_info, lesson_ids
        
    except Exception as e:
        logger.error(f"Error in navigate_and_extract_api: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None, None, []


async def get_student_id(page):
    """
    Extract the student ID from the given page.
    
    This function tries multiple methods to extract the student ID:
    1. First checks if the ID is saved in student-id.json
    2. If not found, tries the JS integration function if available
    3. Falls back to direct extraction from the page content
    
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
                    if data and 'student_id' in data and data['student_id']:
                        logger.info(f"Loaded student ID from file: {data['student_id']}")
                        return data['student_id']
            except Exception as e:
                logger.error(f"Error loading student ID from file: {e}")
                # Continue with extraction methods

        # Try using the JS integration function
        from glasir_timetable.js_navigation.js_integration import get_student_id as js_get_student_id
        
        try:
            # Check if glasirTimetable is available
            has_js_integration = await page.evaluate("typeof window.glasirTimetable === 'object'")
            
            if has_js_integration:
                # Use the JS integration function
                student_id = await js_get_student_id(page)
                if student_id:
                    # Save the student ID for future use
                    try:
                        with open(STUDENT_ID_FILE, 'w') as f:
                            json.dump({'student_id': student_id}, f)
                        logger.info(f"Saved student ID to file: {student_id}")
                    except Exception as e:
                        logger.error(f"Error saving student ID to file: {e}")
                    return student_id
        except Exception as e:
            logger.debug(f"JS integration for student ID extraction not available: {e}")
            # Continue with fallback methods
        
        # Direct extraction methods if JS integration is not available
        
        # Try to extract from localStorage first
        try:
            local_storage = await page.evaluate("localStorage.getItem('StudentId')")
            if local_storage:
                student_id = local_storage.strip()
                # Save the student ID for future use
                try:
                    with open(STUDENT_ID_FILE, 'w') as f:
                        json.dump({'student_id': student_id}, f)
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
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump({'student_id': student_id}, f)
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
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump({'student_id': student_id}, f)
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
                with open(STUDENT_ID_FILE, 'w') as f:
                    json.dump({'student_id': student_id}, f)
                logger.info(f"Saved student ID to file: {student_id}")
            except Exception as e:
                logger.error(f"Error saving student ID to file: {e}")
            return student_id
            
        logger.warning("Could not extract student ID from page using any method")
        return None
            
    except Exception as e:
        logger.error(f"Error extracting student ID: {e}")
        return None 


@handle_errors(default_return=None, error_category="navigating_timetable")
async def navigate_to_week(page: Page, week_offset: int = 0, max_attempts: int = 3) -> bool:
    """
    Navigate to a specific week in the timetable.
    
    Args:
        page: Playwright page instance with already loaded timetable
        week_offset: Week offset (0 = current week, 1 = next week, etc.)
        max_attempts: Maximum number of navigation attempts
        
    Returns:
        True if navigation succeeded, False otherwise
    """
    logger.info(f"Navigating to week with offset {week_offset}")
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Get required lname value for the update call
            content = await page.content()
            lname_value, _ = parse_dynamic_params(content)
            
            # Construct the week navigation JavaScript
            js_code = f"""
            try {{
                const weekOffset = {week_offset};
                const lnameValue = '{lname_value}';
                
                // Try the standard MyUpdate function
                if (typeof MyUpdate === 'function') {{
                    MyUpdate('v', weekOffset, 'udvalg.asp', lnameValue);
                    return true;
                }}
                
                // Fallback: Manual update using direct form submission
                const form = document.createElement('form');
                form.method = 'post';
                form.action = 'udvalg.asp';
                
                const vInput = document.createElement('input');
                vInput.type = 'hidden';
                vInput.name = 'v';
                vInput.value = weekOffset;
                form.appendChild(vInput);
                
                const lnameInput = document.createElement('input');
                lnameInput.type = 'hidden';
                lnameInput.name = 'lname';
                lnameInput.value = lnameValue;
                form.appendChild(lnameInput);
                
                document.body.appendChild(form);
                form.submit();
                return true;
            }} catch (error) {{
                console.error('Week navigation error:', error);
                return false;
            }}
            """
            
            # Execute the JavaScript for navigation
            result = await evaluate_js_safely(
                page, 
                js_code, 
                error_message=f"Navigation to week {week_offset} failed (attempt {attempt})",
                error_category="week_navigation",
                reraise=False
            )
            
            if result:
                # Wait for navigation to complete
                try:
                    # Load event marks page load completion
                    await page.wait_for_load_state("load", timeout=10000)
                    
                    # Additional check: verify that the week has changed by looking for updated content
                    updated = await page.wait_for_selector(".time_8_16", timeout=5000)
                    if updated:
                        logger.info(f"Successfully navigated to week with offset {week_offset}")
                        return True
                except Exception as nav_e:
                    logger.warning(f"Navigation wait error (attempt {attempt}): {nav_e}")
            
            # Sleep before retrying
            if attempt < max_attempts:
                logger.warning(f"Week navigation attempt {attempt} failed, retrying...")
                await asyncio.sleep(1)  # Short delay before retry
                
        except Exception as e:
            logger.error(f"Error navigating to week {week_offset} (attempt {attempt}): {e}")
            if attempt < max_attempts:
                await asyncio.sleep(1)
    
    logger.error(f"Failed to navigate to week {week_offset} after {max_attempts} attempts")
    return False


@handle_errors(default_return=None, error_category="extracting_student_data")
async def extract_student_info(page: Page) -> Dict[str, Any]:
    """
    Extract student information from the page after login.
    
    Args:
        page: Playwright page instance after successful login
        
    Returns:
        Dictionary with student information
    """
    logger.info("Extracting student information...")
    
    try:
        # Wait for the page to stabilize
        await page.wait_for_load_state("networkidle", timeout=5000)
        
        # Extract student ID and dynamic parameters
        student_id = await get_student_id(page)
        
        content = await page.content()
        lname_value, timer_value = parse_dynamic_params(content)
        
        # Extract student name from the page
        student_name = await page.evaluate("""() => {
            // Try to find name in welcome text first
            const welcomeElement = document.querySelector('.welcome');
            if (welcomeElement) {
                const nameMatch = welcomeElement.textContent.match(/Vælkomin\s+(.+?)\s*!/i);
                if (nameMatch) return nameMatch[1].trim();
            }
            
            // Try other possible elements
            const possibleSelectors = [
                '.student-name', 
                '.user-info',
                'h1', 
                '.header-content'
            ];
            
            for (const selector of possibleSelectors) {
                const element = document.querySelector(selector);
                if (element && element.textContent.trim()) {
                    return element.textContent.trim();
                }
            }
            
            return null;
        }""")
        
        result = {
            "student_id": student_id,
            "student_name": student_name,
            "lname_value": lname_value,
            "timer_value": timer_value
        }
        
        logger.info(f"Extracted student info: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error extracting student info: {e}")
        return {
            "student_id": None,
            "student_name": None,
            "lname_value": None,
            "timer_value": None
        }


@handle_errors(default_return=None, error_category="navigating_lesson_page")
async def navigate_to_note_page(page: Page, lesson_id: str) -> bool:
    """
    Navigate to the note page for a specific lesson.
    
    Args:
        page: Playwright page instance with already loaded timetable
        lesson_id: ID of the lesson to navigate to
        
    Returns:
        True if navigation succeeded, False otherwise
    """
    logger.info(f"Navigating to note page for lesson {lesson_id}")
    
    try:
        # Get required lname value for the update call
        content = await page.content()
        lname_value, _ = parse_dynamic_params(content)
        
        # Construct the navigation JavaScript
        js_code = f"""
        try {{
            const lessonId = '{lesson_id}';
            const lnameValue = '{lname_value}';
            
            // Try the standard MyUpdate function
            if (typeof MyUpdate === 'function') {{
                MyUpdate('q', lessonId, 'note.asp', lnameValue);
                return true;
            }}
            
            // Fallback: Manual update using direct form submission
            const form = document.createElement('form');
            form.method = 'post';
            form.action = 'note.asp';
            
            const qInput = document.createElement('input');
            qInput.type = 'hidden';
            qInput.name = 'q';
            qInput.value = lessonId;
            form.appendChild(qInput);
            
            const lnameInput = document.createElement('input');
            lnameInput.type = 'hidden';
            lnameInput.name = 'lname';
            lnameInput.value = lnameValue;
            form.appendChild(lnameInput);
            
            document.body.appendChild(form);
            form.submit();
            return true;
        }} catch (error) {{
            console.error('Lesson navigation error:', error);
            return false;
        }}
        """
        
        # Execute the JavaScript for navigation
        result = await evaluate_js_safely(
            page, 
            js_code, 
            error_message=f"Navigation to lesson {lesson_id} failed",
            error_category="lesson_navigation",
            reraise=False
        )
        
        if result:
            # Wait for navigation to complete
            try:
                # Load event marks page load completion
                await page.wait_for_load_state("load", timeout=10000)
                
                # Additional check: verify the content has loaded
                note_form = await page.wait_for_selector("form[name='NotesForm']", timeout=5000)
                if note_form:
                    logger.info(f"Successfully navigated to note page for lesson {lesson_id}")
                    return True
            except Exception as nav_e:
                logger.warning(f"Note page navigation wait error: {nav_e}")
        
        logger.error(f"Failed to navigate to note page for lesson {lesson_id}")
        return False
        
    except Exception as e:
        logger.error(f"Error navigating to note page: {e}")
        return False


@handle_errors(default_return=None, error_category="submitting_note")
async def submit_note(page: Page, lesson_id: str, note_text: str) -> bool:
    """
    Submit a note for a specific lesson.
    
    Args:
        page: Playwright page instance with already loaded note page
        lesson_id: ID of the lesson
        note_text: Text of the note to submit
        
    Returns:
        True if submission succeeded, False otherwise
    """
    logger.info(f"Submitting note for lesson {lesson_id}")
    
    try:
        # Get required lname and timer values for the form submission
        content = await page.content()
        lname_value, timer_value = parse_dynamic_params(content)
        
        # Check if we have a NotesForm
        notes_form = await page.query_selector("form[name='NotesForm']")
        if not notes_form:
            logger.error("Note form not found on the page")
            return False
            
        # Fill note text in textarea
        note_textarea = await page.query_selector("textarea[name='note']")
        if note_textarea:
            await note_textarea.fill(note_text)
            
            # Submit the form
            await page.click("input[type='submit']")
            
            # Wait for submission to complete
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            logger.info(f"Successfully submitted note for lesson {lesson_id}")
            return True
        else:
            logger.error("Note textarea not found on the page")
            return False
            
    except Exception as e:
        logger.error(f"Error submitting note: {e}")
        return False 