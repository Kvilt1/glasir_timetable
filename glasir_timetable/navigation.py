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

from glasir_timetable import logger
from glasir_timetable.extractors import extract_timetable_data
# Import directly from homework_parser to avoid circular import
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.api_client import fetch_homework_for_lessons, fetch_timetable_for_week, extract_lname_from_page, extract_timer_value_from_page
from glasir_timetable.js_navigation.js_integration import (
    navigate_to_week_js,
    return_to_baseline_js,
    JavaScriptIntegrationError,
    verify_myupdate_function
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
async def with_week_navigation(page, week_offset, student_id):
    """
    Context manager for safely navigating to a week and ensuring return to baseline.
    
    Args:
        page: The Playwright page object
        week_offset: The offset from the current week (0=current, 1=next, -1=previous)
        student_id: The student ID GUID
        
    Yields:
        dict: Information about the week that was navigated to, or None if navigation failed
    """
    week_info = None
    try:
        # Navigate to specified week
        week_info = await navigate_to_week_js(page, week_offset, student_id)
        yield week_info
    finally:
        # Always return to baseline
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


async def process_single_week_api(page, week_offset, teacher_map, student_id, output_dir, 
                                 api_cookies=None, processed_weeks=None, use_models=True):
    """
    Process a single week, extract and save its timetable data using direct API calls.
    This is an alternative to the JavaScript-based implementation that uses direct API requests.
    
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
    
    # Extract timetable data with API-based approach
    timetable_data, week_info, _ = await navigate_and_extract_api(
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
    Process multiple weeks in the specified directions.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process (positive for forward, negative for backward)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_weeks: Optional set of already processed week numbers
        use_api: Whether to use direct API calls (True) or JavaScript navigation (False)
        
    Returns:
        list: Successfully processed week information
    """
    if processed_weeks is None:
        processed_weeks = set()
        
    results = []
    for direction in directions:
        # Choose between API-based or JS-based implementation
        if use_api:
            logger.info(f"Using API-based implementation for week offset {direction}")
            result = await process_single_week_api(
                page=page,
                week_offset=direction,
                teacher_map=teacher_map,
                student_id=student_id,
                output_dir=output_dir,
                api_cookies=api_cookies,
                processed_weeks=processed_weeks
            )
        else:
            logger.info(f"Using JavaScript-based implementation for week offset {direction}")
            result = await process_single_week(
                page=page,
                week_offset=direction,
                teacher_map=teacher_map,
                student_id=student_id,
                output_dir=output_dir,
                api_cookies=api_cookies,
                processed_weeks=processed_weeks
            )
        
        if result:
            results.append(result)
            
    return results


async def get_week_directions(args):
    """
    Generate a list of week directions based on command line arguments.
    
    Args:
        args: Command line arguments with weekforward and weekbackward attributes
        
    Returns:
        list: Week direction offsets
    """
    directions = []
    
    # Add backward weeks (negative offsets)
    for i in range(1, args.weekbackward + 1):
        directions.append(-i)
        
    # Add forward weeks (positive offsets)
    for i in range(1, args.weekforward + 1):
        directions.append(i)
        
    return directions


async def navigate_and_extract_api(page, week_offset, teacher_map, student_id, api_cookies=None, use_models=True):
    """
    Navigate to a specific week and extract timetable data using direct API calls.
    
    This function uses the direct API endpoint (udvalg.asp) to fetch timetable data
    for a specific week offset. It then sets the HTML content and extracts data using
    the same extraction functions as the JavaScript-based navigation.
    
    Args:
        page: The playwright page object
        week_offset: Week offset (0=current, positive=forward, negative=backward)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID (GUID format)
        api_cookies: Cookies for API-based timetable and homework extraction
        use_models: Whether to convert the result to Pydantic models
        
    Returns:
        tuple: (timetable_data, week_info, homework_lesson_ids)
    """
    if not api_cookies:
        logger.error("API cookies required for direct API navigation")
        return None, None, []
    
    try:
        # Extract lname value dynamically
        lname_value = await extract_lname_from_page(page)
        
        # Extract timer value dynamically
        timer_value = await extract_timer_value_from_page(page)
        
        # Make the direct API call to fetch timetable data
        html_content = await fetch_timetable_for_week(
            cookies=api_cookies,
            student_id=student_id,
            week_offset=week_offset,
            lname_value=lname_value,
            timer_value=timer_value
        )
        
        if not html_content:
            logger.error(f"Failed to fetch timetable data for week offset {week_offset}")
            return None, None, []
        
        # Set the content on the page so we can use the existing extraction functions
        # The extractors expect page content, so we need to set it before extraction
        await page.set_content(html_content)
        
        # Now extract the data using the existing extraction function
        # This works because the API returns the same HTML we'd get from JS navigation
        timetable_data, week_details, homework_lesson_ids = await extract_timetable_data(
            page, teacher_map, use_models=False  # Always use dictionary during extraction
        )
        
        # Process week info from the extracted data
        week_info = week_details if week_details else {}
        
        # Ensure week_info has all required keys
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
            if timetable_data and 'events' in timetable_data:
                for event in timetable_data['events']:
                    if 'lessonId' in event and event['lessonId'] in homework_map:
                        event['description'] = homework_map[event['lessonId']]
                        merged_count += 1
                
                logger.info(f"Merged {merged_count} homework descriptions into events")
        
        # Convert to model if requested
        if use_models and timetable_data:
            try:
                model_data, success = dict_to_timetable_data(timetable_data)
                logger.debug("Converted timetable data to Pydantic model")
                if success:
                    timetable_data = model_data
            except Exception as e:
                logger.error(f"Error converting to model: {e}")
        
        return timetable_data, week_info, homework_lesson_ids
    
    except Exception as e:
        logger.error(f"Error in API-based timetable extraction: {e}")
        return None, None, [] 