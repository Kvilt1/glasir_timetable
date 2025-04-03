#!/usr/bin/env python3
"""
Centralized navigation utilities for the Glasir Timetable application.

This module provides unified functions for API-based navigation throughout the codebase.
All JavaScript-based navigation has been removed in favor of direct API calls.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional, Callable, Set
from datetime import datetime
import re
import json
import time

from playwright.async_api import Page
from glasir_timetable import logger, add_error
# Import from the new student_utils module
from glasir_timetable.student_utils import get_student_id
# Import directly from homework_parser to avoid circular import
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.extractors.timetable import extract_timetable_data
from glasir_timetable.api_client import (
    fetch_homework_for_lessons,
    fetch_timetable_for_week,
    fetch_weeks_data,
    fetch_timetables_for_weeks,
    extract_week_range
)

# Import utility functions
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

async def process_weeks(page, directions, teacher_map, student_id, output_dir, 
                       api_cookies=None, processed_weeks=None, lname_value=None, timer_value=None):
    """
    Process multiple weeks using API-based extraction.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_weeks: Set of already processed week numbers (to avoid duplicates)
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
            # to return the week_info directly in the result dictionary
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


async def extract_min_max_week_offsets(page, api_cookies=None, student_id=None, lname_value=None, timer_value=None):
    """
    Extract the minimum and maximum week offsets available in the timetable using API-based extraction.
    
    Args:
        page: The Playwright page object containing the timetable
        api_cookies: Cookies for API requests
        student_id: Student ID for API requests
        lname_value: Optional lname value for API requests
        timer_value: Optional timer value for API requests
        
    Returns:
        tuple: (min_offset, max_offset) - the earliest and latest available week offsets
        
    Raises:
        ValueError: If no week offset values can be found
    """
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