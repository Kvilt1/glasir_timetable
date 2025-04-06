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

async def process_weeks(
    directions,
    teacher_map,
    student_id,
    output_dir,
    api_cookies,
    lname_value,
    timer_value,
    processed_weeks=None,
    dynamic_range=False
):
    """
    Process multiple weeks using API-based extraction.

    Args:
        directions: List of week offsets to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests (required)
        lname_value: Pre-extracted lname value for API requests (required)
        timer_value: Pre-extracted timer value for API requests (required)
        processed_weeks: Optional set of already processed week numbers
        dynamic_range: If True, dynamically extract all week offsets (default False)

    Returns:
        Set of processed week numbers
    """
    if processed_weeks is None:
        processed_weeks = set()

    if dynamic_range:
        # Fetch week 0 timetable first to extract all week offsets dynamically
        logger.info("Fetching week 0 timetable to extract all week offsets...")
        week0_html = await fetch_timetable_for_week(
            cookies=api_cookies,
            student_id=student_id,
            week_offset=0,
            lname_value=lname_value,
            timer_value=timer_value
        )
        if not week0_html:
            logger.error("Failed to fetch week 0 timetable, cannot proceed with all weeks extraction.")
            return processed_weeks

        # Parse week offsets from the week 0 timetable HTML
        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(week0_html, "lxml")
        week_links = soup.find_all("a", onclick=True)
        offsets = set()
        for link in week_links:
            onclick = link.get("onclick", "")
            match = re.search(r"v=(-?\d+)", onclick)
            if match:
                offsets.add(int(match.group(1)))
        # Always include week 0
        offsets.add(0)
        week_offsets = sorted(offsets)
        logger.info(f"Extracted {len(week_offsets)} week offsets from week 0 timetable: {week_offsets}")
    else:
        # Use the provided directions list
        week_offsets = sorted(set(directions))
        logger.info(f"Using provided week offsets: {week_offsets}")

    # Create a shared HTTP client for all homework fetches
    import httpx
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=True) as shared_client:
        total_weeks = len(week_offsets)
        for idx, week_offset in enumerate(week_offsets):
            logger.info(f"Processing week {idx+1}/{total_weeks} (offset {week_offset})")
            try:
                week_html = await fetch_timetable_for_week(
                    cookies=api_cookies,
                    student_id=student_id,
                    week_offset=week_offset,
                    lname_value=lname_value,
                    timer_value=timer_value
                )
                if not week_html:
                    logger.warning(f"No timetable HTML for week offset {week_offset}")
                    continue

                # Parse timetable HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(week_html, "lxml")
                # Placeholder: parse timetable data, week_info, lesson_ids
                timetable_data, week_info, lesson_ids = await parse_timetable_html(
                    html_content=week_html,
                    teacher_map=teacher_map,
                    student_info={"student_name": "Unknown", "class": "Unknown"}
                )

                if not timetable_data:
                    logger.warning(f"No timetable data for week offset {week_offset}")
                    continue

                # Fetch homework for lessons
                homework_map = {}
                if api_cookies and lesson_ids:
                    homework_map = await fetch_homework_for_lessons(
                        cookies=api_cookies,
                        lesson_ids=lesson_ids,
                        max_concurrent=20,
                        lname_value=lname_value,
                        timer_value=timer_value,
                        client=shared_client
                    )
                    logger.info(f"Fetched homework for {len(homework_map)}/{len(lesson_ids)} lessons")

                    # Merge homework into timetable data
                    merged_count = 0
                    for event in timetable_data.get("events", []):
                        lesson_id = event.get("lessonId")
                        if lesson_id and lesson_id in homework_map:
                            event["description"] = homework_map[lesson_id]
                            merged_count += 1
                    logger.info(f"Merged {merged_count} homework descriptions into events")

                # Normalize dates
                if "weekInfo" in timetable_data and isinstance(timetable_data, dict):
                    week_info = timetable_data.get("weekInfo", {})
                    year = week_info.get("year")
                    start_date = week_info.get("startDate")
                    end_date = week_info.get("endDate")
                    if start_date and end_date and year:
                        start_date, end_date = normalize_dates(start_date, end_date, year)
                        week_info["startDate"] = start_date
                        week_info["endDate"] = end_date
                else:
                    logger.warning("Skipping date normalization due to unknown format")

                if "weekInfo" in timetable_data and "weekNumber" in timetable_data["weekInfo"]:
                    timetable_data["weekInfo"]["weekNumber"] = normalize_week_number(timetable_data["weekInfo"]["weekNumber"])

                if "weekInfo" in timetable_data:
                    week_info_dict = timetable_data["weekInfo"]
                    year = week_info_dict.get("year", datetime.now().year)
                    week_num = week_info_dict.get("weekNumber", 0)
                    start_date = week_info_dict.get("startDate", "")
                    end_date = week_info_dict.get("endDate", "")
                    filename = generate_week_filename(year, week_num, start_date, end_date)
                    output_path = os.path.join(output_dir, filename)
                    week_id = f"{year}-W{week_num}-{start_date}"
                    if week_id in processed_weeks:
                        logger.info(f"Week {week_id} already processed, skipping")
                        continue
                    save_json_data(timetable_data, output_path)
                    processed_weeks.add(week_id)
                    logger.info(f"Week successfully exported: {filename}")
                else:
                    logger.warning(f"Could not generate filename: weekInfo missing for week offset {week_offset}")

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


async def extract_min_max_week_offsets(api_cookies, student_id, lname_value, timer_value):
    """
    Extract the minimum and maximum week offsets available using API calls only.
    
    Args:
        api_cookies: Cookies for API requests (required)
        student_id: Student ID GUID (required)
        lname_value: Extracted lname value (required)
        timer_value: Extracted timer value (required)
        
    Returns:
        tuple: (min_offset, max_offset)
    """
    if not api_cookies or not student_id:
        raise ValueError("API cookies and student_id are required")
    
    try:
        # Fetch the initial week's HTML via API
        initial_response = await fetch_timetable_for_week(
            cookies=api_cookies,
            student_id=student_id,
            week_offset=0,
            lname_value=lname_value,
            timer_value=timer_value
        )
        if not initial_response:
            raise ValueError("Failed to fetch initial week data for extracting week range")
        
        from bs4 import BeautifulSoup
        import re
        soup = BeautifulSoup(initial_response, 'html.parser')
        week_links = soup.find_all('a', onclick=lambda v: v and 'v=' in v)
        unique_offsets = set()
        for link in week_links:
            onclick = link.get('onclick', '')
            match = re.search(r'v=(-?\d+)', onclick)
            if match:
                unique_offsets.add(int(match.group(1)))
        if not unique_offsets:
            raise ValueError("No week offsets found in initial API response")
        offsets = sorted(unique_offsets)
        return min(offsets), max(offsets)
    except Exception as e:
        logger.error(f"Error extracting week offsets via API: {e}")
        # Fallback: scan multiple academic years
        v_override_values = ["0", "-52", "52"]
        all_offsets = []
    
        import asyncio
        tasks = []
        for v_value in v_override_values:
            tasks.append(
                extract_week_range(
                    cookies=api_cookies,
                    student_id=student_id,
                    lname_value=lname_value,
                    timer_value=timer_value,
                    v_override=v_value
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
        for v_value, result in zip(v_override_values, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get week range for v_override={v_value}: {result}")
                continue
            min_off, max_off = result
            if v_value == "-52":
                min_off -= 52
                max_off -= 52
            elif v_value == "52":
                min_off += 52
                max_off += 52
            all_offsets.extend(range(min_off, max_off + 1))
    
        if not all_offsets:
            raise ValueError("Failed to extract any week offsets via API fallback")
        return min(all_offsets), max(all_offsets)


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
        
        # Check if page is open before extracting lname
        try:
            _ = await page.title()
            logger.info("[DEBUG] Page appears open before extracting lname/timer")
        except Exception as e:
            logger.error(f"[DEBUG] Page likely closed before extracting lname/timer: {e}")
        
        # Get lname_value if not provided
        if lname_value is None:
            try:
                content = await page.content()
                lname_value, _ = parse_dynamic_params(content)
                logger.info(f"Extracted lname value: {lname_value}")
            except Exception as e:
                logger.error(f"[DEBUG] Failed to extract lname: {e}")
                lname_value = None
        
        # Get timer_value if not provided
        if timer_value is None:
            try:
                content = await page.content()
                _, timer_value = parse_dynamic_params(content)
                logger.info(f"Extracted timer value: {timer_value}")
            except Exception as e:
                logger.error(f"[DEBUG] Failed to extract timer: {e}")
                timer_value = None
        
        # Check if page is open before get_student_id
        try:
            _ = await page.title()
            logger.info("[DEBUG] Page appears open before get_student_id()")
        except Exception as e:
            logger.error(f"[DEBUG] Page likely closed before get_student_id(): {e}")
        
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
        
        # Check if page is open before extract_student_info
        try:
            _ = await page.title()
            logger.info("[DEBUG] Page appears open before extract_student_info()")
        except Exception as e:
            logger.error(f"[DEBUG] Page likely closed before extract_student_info(): {e}")
        
        # Get student information before parsing timetable
        from glasir_timetable.extractors.timetable import extract_student_info
        try:
            student_info = await extract_student_info(page)
        except Exception as e:
            logger.error(f"[DEBUG] Failed to extract student info: {e}")
            student_info = {"studentName": "Unknown", "class": "Unknown"}
        
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