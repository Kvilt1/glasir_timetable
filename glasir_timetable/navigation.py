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
from glasir_timetable.extractors.timetable import extract_timetable_data, parse_timetable_html, extract_student_info # Import parse_timetable_html and extract_student_info
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
    Process multiple weeks using API-based extraction with parallel fetching.
    
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
    
    # Ensure directions are unique
    directions = list(set(directions))
    
    # Sort directions from highest positive to largest negative value
    directions.sort(reverse=True)
    
    # Add current week (offset 0) if it's not already in directions
    all_week_offsets = [] 
    if 0 not in directions:
        all_week_offsets = [0]
    all_week_offsets.extend(directions)
    
    # Only extract if not provided     
    if lname_value is None or timer_value is None:
        content = await page.content()
        lname_value, timer_value = parse_dynamic_params(content)
    logger.info(f"Using API-based approach with lname={lname_value}, timer={timer_value}")
    
    # PARALLEL FETCH: Get all timetable HTML content for all weeks at once
    logger.info(f"Fetching timetable HTML for {len(all_week_offsets)} weeks in parallel...")
    weeks_html_content = await fetch_timetables_for_weeks(
        cookies=api_cookies,
        student_id=student_id,
        week_offsets=all_week_offsets,
        lname_value=lname_value,
        timer_value=timer_value
    )
    logger.info(f"Completed parallel fetch: received data for {sum(1 for v in weeks_html_content.values() if v)} of {len(all_week_offsets)} weeks")
    
    # Extract student info once before the loop
    student_info = await extract_student_info(page)
    if not student_info or student_info.get("student_name") == "Unknown":
         logger.error("Failed to extract student info before processing weeks. Aborting.")
         return processed_weeks # Or raise an error

    # Now process each week sequentially using the pre-fetched HTML
    total_weeks = len(all_week_offsets)
    for idx, week_offset in enumerate(all_week_offsets):
        log_progress(idx + 1, total_weeks, f"Processing week offset {week_offset}")
        
        # Check if we have HTML content for this week
        html_content = weeks_html_content.get(week_offset)
        if html_content is None:
            logger.error(f"Failed to fetch HTML content for week offset {week_offset}")
            continue
        
        try:
            # Directly parse the fetched HTML content
            # No need to use page.evaluate or extract_timetable_data(page, ...) anymore
            timetable_data, week_info, lesson_ids = await parse_timetable_html(
                html_content=html_content,
                teacher_map=teacher_map,
                student_info=student_info # Pass pre-extracted student_info
            )

            if not timetable_data:
                logger.error(f"Failed to extract timetable data for week offset {week_offset}")
                continue
                
            # Fetch homework in parallel for this week's lessons
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
                
                # Generate a unique week identifier
                week_id = f"{year}-{week_num}"
                
                # If this week is already processed, skip it
                if week_id in processed_weeks:
                    logger.info(f"Week {week_id} already processed, skipping")
                    continue
                
                # If file already exists, skip it
                if os.path.exists(output_path):
                    logger.info(f"Week already exported: {filename}")
                    processed_weeks.add(week_id)
                    continue
                
                # Save the JSON data to disk
                save_json_data(timetable_data, output_path)
                
                # Add to processed weeks
                processed_weeks.add(week_id)
                logger.info(f"Week successfully exported: {filename}")
            else:
                # Fallback if weekInfo is not available
                logger.error(f"Could not generate filename: weekInfo missing from timetable data for week offset {week_offset}")
                
        except Exception as e:
            logger.error(f"Error processing week offset {week_offset}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
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
    
    # Ensure no duplicates
    directions = list(set(directions))
    
    # Sort from highest positive value to largest negative value
    directions.sort(reverse=True)
    
    logger.info(f"Generated {len(directions)} unique week directions from highest ({max(directions) if directions else 0}) to lowest ({min(directions) if directions else 0})")
    
    return directions


async def extract_min_max_week_offsets(page, api_cookies=None, student_id=None, lname_value=None, timer_value=None):
    """
    Extract the minimum and maximum week offsets available in the timetable using API-based extraction.
    This enhanced version scans multiple academic years by using the v_override parameter.
    
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
    
    # Get week data from initial response (for week 0) to extract all available weeks
    logger.info(f"Fetching initial week data to extract all available week offsets...")
    
    try:
        # Fetch the initial data with v=0 (current academic year)
        initial_response = await fetch_timetable_for_week(
            cookies=api_cookies,
            student_id=student_id,
            week_offset=0,
            lname_value=lname_value,
            timer_value=timer_value
        )
        
        if not initial_response:
            logger.error("Failed to fetch initial week data")
            raise ValueError("Failed to fetch initial week data for extracting week range")
        
        # Extract all week offsets from the HTML response
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(initial_response, 'html.parser')
        
        # Find all links with week offsets in the v parameter
        week_links = soup.find_all('a', onclick=lambda v: v and 'v=' in v)
        
        # Use a set to collect unique offsets
        unique_offsets = set()
        for link in week_links:
            onclick = link.get('onclick', '')
            offset_match = re.search(r'v=(-?\d+)', onclick)
            if offset_match:
                offset = int(offset_match.group(1))
                unique_offsets.add(offset)
        
        if not unique_offsets:
            logger.error("No week offsets found in the initial response")
            raise ValueError("No week offsets found in the initial response")
        
        # Convert set to list and sort
        all_offsets = list(unique_offsets)
        # Sort the offsets from highest positive value to largest negative value
        all_offsets.sort(reverse=True)
        
        # Calculate min and max offsets
        min_offset = min(all_offsets)
        max_offset = max(all_offsets)
        
        logger.info(f"Extracted {len(all_offsets)} unique week offsets from initial response")
        logger.info(f"Week offset range: {min_offset} to {max_offset}")
        logger.info(f"Week offsets in descending order: {all_offsets}")
        
        return min_offset, max_offset
        
    except Exception as e:
        logger.error(f"Error extracting week range from initial response: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Fall back to the previous multi-year scanning approach if initial extraction fails
        logger.info("Falling back to multi-year scanning approach...")
        
        # Define v_override values to scan multiple academic years
        # 0 = current year, -52 = previous year, +52 = next year
        v_override_values = ["0", "-52", "52"]
        all_offsets = []
        errors = []
        
        logger.info(f"Scanning for available weeks across multiple academic years...")
        
        # Fetch offsets for each academic year
        for v_value in v_override_values:
            try:
                logger.info(f"Checking for weeks with v_override={v_value}")
                
                # Use the enhanced extract_week_range function
                min_offset, max_offset = await extract_week_range(
                    cookies=api_cookies,
                    student_id=student_id,
                    lname_value=lname_value,
                    timer_value=timer_value,
                    v_override=v_value
                )
                
                # Check if we got valid results
                if min_offset is not None and max_offset is not None:
                    # For non-default v_override (not "0"), adjust offsets to account for the year difference
                    if v_value == "-52":
                        # For previous year, adjust offsets (e.g., convert relative -12 to absolute -64)
                        adjusted_min = min_offset - 52
                        adjusted_max = max_offset - 52
                        logger.info(f"Adjusted previous year offsets from ({min_offset}, {max_offset}) to ({adjusted_min}, {adjusted_max})")
                        all_offsets.extend(range(adjusted_min, adjusted_max + 1))
                    elif v_value == "52":
                        # For next year, adjust offsets (e.g., convert relative +12 to absolute +64)
                        adjusted_min = min_offset + 52
                        adjusted_max = max_offset + 52
                        logger.info(f"Adjusted next year offsets from ({min_offset}, {max_offset}) to ({adjusted_min}, {adjusted_max})")
                        all_offsets.extend(range(adjusted_min, adjusted_max + 1))
                    else:
                        # For current year, use offsets as-is
                        logger.info(f"Using current year offsets: ({min_offset}, {max_offset})")
                        all_offsets.extend(range(min_offset, max_offset + 1))
            except Exception as e:
                logger.warning(f"Failed to get week range for v_override={v_value}: {e}")
                errors.append(str(e))
                # Continue with other v_override values, don't abort
        
        # Check if we got any valid offsets
        if not all_offsets:
            error_details = "\n".join(errors) if errors else "No error details available"
            logger.error(f"Failed to extract any valid week offsets. Errors: {error_details}")
            raise ValueError(f"Failed to extract week offset range. No valid offsets found.")
        
        # Remove duplicates in fallback approach too
        all_offsets = list(set(all_offsets))
        
        # Calculate the global min/max from all collected offsets
        min_global_offset = min(all_offsets)
        max_global_offset = max(all_offsets)
        
        # Sort all offsets from highest positive to largest negative for --all-weeks
        all_offsets.sort(reverse=True)
        logger.info(f"Sorted offsets from highest positive to largest negative: {all_offsets[:10]}...")
        
        logger.info(f"Multi-year week scanning complete. Full offset range: {min_global_offset} to {max_global_offset}")
        return min_global_offset, max_global_offset


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
        
        # Get student information before parsing timetable
        from glasir_timetable.extractors.timetable import extract_student_info
        student_info = await extract_student_info(page)
        
        # Extract timetable data using the new parse_timetable_html function
        from glasir_timetable.extractors.timetable import parse_timetable_html
        timetable_data, week_info, lesson_ids = await parse_timetable_html(
            html_content=week_html,
            teacher_map=teacher_map,
            student_info=student_info
        )
        
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