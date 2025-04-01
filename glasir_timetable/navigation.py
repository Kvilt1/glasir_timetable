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

from glasir_timetable import logger, add_error
from glasir_timetable.extractors import extract_timetable_data
# Import directly from homework_parser to avoid circular import
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.api_client import (
    fetch_homework_for_lessons,
    fetch_timetable_for_week,
    extract_lname_from_page,
    extract_timer_value_from_page
)
from glasir_timetable.js_navigation.js_integration import (
    navigate_to_week_js,
    return_to_baseline_js,
    JavaScriptIntegrationError,
    verify_myupdate_function,
    get_student_id
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
            lname_value = await extract_lname_from_page(page)
        
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
                       api_cookies=None, processed_weeks=None, use_api=False):
    """
    Process multiple weeks based on the provided directions/offsets.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_weeks: Set of already processed week numbers
        use_api: Whether to use the API-based approach instead of JavaScript navigation
        
    Returns:
        int: Number of successfully processed weeks
    """
    if processed_weeks is None:
        processed_weeks = set()
        
    logger.info(f"Processing {len(directions)} additional weeks")
    
    # Initialize counter for successful weeks
    success_count = 0
    
    # Extract lname and timer values for API calls if needed
    lname_value = None
    timer_value = None
    if use_api:
        try:
            # Extract values needed for API calls
            lname_value = await extract_lname_from_page(page)
            timer_value = await extract_timer_value_from_page(page)
            logger.info(f"Using API-based approach with lname={lname_value}")
        except Exception as e:
            logger.warning(f"Failed to extract lname/timer values: {e}. Will try to extract them during processing.")
    
    # Process each direction (week offset)
    for direction in directions:
        try:
            if use_api:
                # Process the week using API-based approach
                result = await process_single_week_api(
                    page=page,
                    week_offset=direction,
                    output_dir=output_dir,
                    teacher_map=teacher_map,
                    api_cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value
                )
                
                if result.get("success", False):
                    success_count += 1
                    # Add to processed weeks if we can extract the week number
                    if result.get("filename"):
                        # Extract week number from filename (e.g., "2025 Vika 14 - 2025.03.31-2025.04.06.json")
                        match = re.search(r'Vika (\d+)', result.get("filename", ""))
                        if match:
                            week_num = int(match.group(1))
                            processed_weeks.add(week_num)
            else:
                # Process the week using JS-based navigation
                success = await process_single_week(
                    page=page,
                    week_offset=direction,
                    teacher_map=teacher_map,
                    student_id=student_id,
                    output_dir=output_dir,
                    api_cookies=api_cookies,
                    processed_weeks=processed_weeks
                )
                
                if success:
                    success_count += 1
                
        except Exception as e:
            logger.error(f"Error processing week with offset {direction}: {e}")
    
    logger.info(f"Successfully processed {success_count} of {len(directions)} additional weeks")
    return success_count


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
    Process a single week using the API-based approach.
    
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
    """
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
        
        # Generate the output filename and path
        filename = generate_week_filename(timetable_data)
        output_path = os.path.join(output_dir, filename)
        
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
    Navigate to a specific week and extract timetable data using API-based navigation.
    
    Args:
        page: The Playwright page object
        week_offset: Offset from the current week (-1 for previous week, etc.)
        teacher_map: Dictionary mapping teacher initials to full names
        api_cookies: Dictionary of cookies for API requests
        lname_value: Optional dynamically extracted lname value to use with API
        timer_value: Optional timer value to use with API
        
    Returns:
        tuple: (timetable_data, week_info, lesson_ids)
    """
    try:
        # Get student ID for API call
        student_id = await get_student_id(page)
        
        # Get lname_value if not provided
        if lname_value is None:
            lname_value = await extract_lname_from_page(page)
            logger.info(f"Extracted lname value: {lname_value}")
        
        # Get timer_value if not provided
        if timer_value is None:
            timer_value = await extract_timer_value_from_page(page)
            logger.info(f"Extracted timer value: {timer_value}")
            
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
            for event in timetable_data.get("events", []):
                lesson_id = event.get("lessonId")
                if lesson_id and lesson_id in homework_map:
                    event["description"] = homework_map[lesson_id]
        
        return timetable_data, week_info, lesson_ids
        
    except Exception as e:
        logger.error(f"Error in navigate_and_extract_api: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None, None, [] 