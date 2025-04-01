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

from glasir_timetable import logger, add_error
from glasir_timetable.extractors import extract_timetable_data
# Import directly from homework_parser to avoid circular import
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.api_client import (
    fetch_homework_for_lessons,
    fetch_timetable_for_week,
    fetch_weeks_data,
    extract_lname_from_page,
    extract_timer_value_from_page,
    fetch_timetables_for_weeks,
    get_student_id
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
    Fetches timetable HTML concurrently if using the API approach.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID (Only needed if use_api=False)
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests (Required if use_api=True)
        processed_weeks: Set of already processed week numbers
        use_api: Whether to use the API-based approach instead of JavaScript navigation
        
    Returns:
        int: Number of successfully processed weeks
    """
    if processed_weeks is None:
        processed_weeks = set()
    
    total_weeks = len(directions)
    if total_weeks == 0:
        logger.info("No weeks to process")
        return 0
        
    logger.info(f"Processing {total_weeks} additional weeks. API mode: {use_api}")
    
    # Setup progress tracking
    start_time = time.time()
    success_count = 0
    last_progress_time = start_time
    progress_interval = 5.0  # seconds between progress updates
    
    def log_progress(current, total, step_name=""):
        nonlocal last_progress_time
        current_time = time.time()
        elapsed = current_time - start_time
        
        if current > 0 and elapsed > 0:
            estimated_total = elapsed * total / current
            remaining = estimated_total - elapsed
            
            # Format time nicely
            if remaining < 60:
                time_str = f"{remaining:.1f} seconds"
            elif remaining < 3600:
                time_str = f"{remaining/60:.1f} minutes"
            else:
                time_str = f"{remaining/3600:.1f} hours"
                
            logger.info(f"Progress: {current}/{total} weeks {step_name} ({(current/total*100):.1f}%) - Est. remaining: {time_str}")
        else:
            logger.info(f"Progress: {current}/{total} weeks {step_name} (0%) - Starting...")
            
        last_progress_time = current_time
    
    if use_api:
        if not api_cookies:
            logger.error("API cookies are required for API-based processing.")
            return 0
            
        # --- API-based Concurrent Processing ---
        lname_value = None
        timer_value = None
        week_html_map = {}
        all_lesson_ids = []
        processed_data_cache = {} # Cache processed data before homework is added {offset: data}
        week_details_cache = {} # Cache details needed for saving {offset: {filename, output_path, week_num}}

        try:
            # 1. Extract common values needed for API calls
            student_api_id = await get_student_id(page) # Still need student ID for API
            if not student_api_id:
                 logger.error("Failed to get student ID for API calls.")
                 return 0
                 
            lname_value = await extract_lname_from_page(page)
            timer_value = await extract_timer_value_from_page(page)
            logger.info(f"Using API-based approach with lname={lname_value}, timer={timer_value}")

            # 2. Fetch all timetable HTMLs concurrently
            week_html_map = await fetch_timetables_for_weeks(
                cookies=api_cookies,
                student_id=student_api_id,
                week_offsets=directions,
                lname_value=lname_value,
                timer_value=timer_value
            )
            logger.info(f"Fetched HTML for {len([html for html in week_html_map.values() if html])} out of {len(directions)} weeks.")
            
            # 2.1 Retry logic for any weeks that failed to fetch
            failed_offsets = [offset for offset in directions if offset not in week_html_map or week_html_map[offset] is None]
            if failed_offsets:
                logger.info(f"Retrying {len(failed_offsets)} failed week fetches...")
                max_retries = 2
                for retry in range(max_retries):
                    if not failed_offsets:
                        break
                        
                    logger.info(f"Retry attempt {retry+1}/{max_retries} for offsets: {failed_offsets}")
                    # Generate a new timer value for retry to avoid caching issues
                    retry_timer = int(time.time() * 1000)
                    
                    # Retry with increased timeout and slightly lower concurrency
                    retry_html_map = await fetch_timetables_for_weeks(
                        cookies=api_cookies,
                        student_id=student_api_id,
                        week_offsets=failed_offsets,
                        max_concurrent=min(3, len(failed_offsets)),  # Lower concurrency
                        lname_value=lname_value,
                        timer_value=retry_timer
                    )
                    
                    # Update the main map with successful retries
                    successful_retries = 0
                    for offset, html in retry_html_map.items():
                        if html:
                            week_html_map[offset] = html
                            successful_retries += 1
                    
                    logger.info(f"Retry {retry+1} succeeded for {successful_retries}/{len(failed_offsets)} weeks")
                    
                    # Update the list of failed offsets for potential next retry
                    failed_offsets = [offset for offset in failed_offsets if offset not in retry_html_map or retry_html_map[offset] is None]
                
                # Final logging after all retries
                if failed_offsets:
                    logger.warning(f"After all retries, still failed to fetch {len(failed_offsets)} weeks: {failed_offsets}")
                else:
                    logger.info("Successfully fetched all weeks after retries")

        except Exception as e:
            logger.error(f"Failed during initial API setup or concurrent fetch: {e}")
            # Proceed to process any HTML that was successfully fetched
            
        # 3. Process each week's HTML sequentially (using page for extraction)
        processed_count = 0
        for offset in directions:
            try:
                week_html = week_html_map.get(offset)
                if not week_html:
                    logger.warning(f"Skipping week offset {offset}: No HTML fetched.")
                    continue

                # Update progress periodically
                processed_count += 1
                current_time = time.time()
                if current_time - last_progress_time >= progress_interval or processed_count == total_weeks:
                    log_progress(processed_count, total_weeks, "processed")

                # Inject HTML into the page
                escaped_html = week_html.replace('`', '\\\\`')
                # Fix triple-quoted string to avoid linter errors
                js_code = """
                document.getElementById('MyWindowMain').innerHTML = `{html}`;
                """.format(html=escaped_html)
                await page.evaluate(js_code)
                
                # Extract data from the injected HTML
                timetable_data, week_info, lesson_ids = await extract_timetable_data(page, teacher_map)

                if not timetable_data or not week_info:
                    logger.error(f"Failed to extract timetable data from HTML for week offset {offset}")
                    continue
                    
                # Normalize data
                year = week_info.get("year")
                start_date = week_info.get("startDate")
                end_date = week_info.get("endDate")
                week_num_raw = week_info.get("weekNumber")

                if start_date and end_date and year:
                    start_date, end_date = normalize_dates(start_date, end_date, year)
                    week_info["startDate"] = start_date
                    week_info["endDate"] = end_date
                
                week_num = normalize_week_number(week_num_raw) if week_num_raw else 0
                week_info["weekNumber"] = week_num
                timetable_data["weekInfo"] = week_info # Ensure updated info is stored

                # Generate filename and path
                filename = generate_week_filename(year, week_num, start_date, end_date)
                output_path = os.path.join(output_dir, filename)

                # Check if already processed (file exists)
                if os.path.exists(output_path):
                    logger.info(f"Week already exported (offset {offset}): {filename}")
                    # Add to processed_weeks set based on filename
                    if week_num not in processed_weeks:
                        processed_weeks.add(week_num)
                        logger.debug(f"Added week {week_num} to processed_weeks set based on existing file.")
                    success_count += 1 # Count skipped as success for this run's purpose
                    continue # Skip further processing for this week

                # Store data and details for later homework association and saving
                processed_data_cache[offset] = timetable_data
                all_lesson_ids.extend(lesson_ids)
                week_details_cache[offset] = {
                    "filename": filename, 
                    "output_path": output_path,
                    "week_num": week_num,
                    "year": year,
                    "start_date": start_date,
                    "end_date": end_date
                }
                
            except Exception as e:
                logger.error(f"Error processing fetched HTML for week offset {offset}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")

        # 4. Fetch all homework concurrently
        homework_map = {}
        if all_lesson_ids:
            unique_lesson_ids = list(set(all_lesson_ids))
            logger.info(f"Fetching homework for {len(unique_lesson_ids)} unique lessons across processed weeks.")
            try:
                # Update progress for homework fetch
                log_progress(0, len(processed_data_cache), "homework fetch")
                
                # Consider using fetch_homework_for_lessons_with_retry if available/needed
                homework_map = await fetch_homework_for_lessons(
                    cookies=api_cookies,
                    lesson_ids=unique_lesson_ids,
                    lname_value=lname_value,
                    timer_value=timer_value
                )
                
                # Update progress after homework fetch
                log_progress(len(processed_data_cache), len(processed_data_cache), "homework fetch")
                logger.info(f"Fetched homework for {len(homework_map)} lessons.")
            except Exception as e:
                logger.error(f"Error fetching homework concurrently: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")

        # 5. Associate homework and save files
        saved_count = 0
        for offset, timetable_data in processed_data_cache.items():
            try:
                # Add homework to timetable data
                if homework_map:
                    for event in timetable_data.get("events", []):
                        lesson_id = event.get("lessonId")
                        if lesson_id and lesson_id in homework_map:
                            event["description"] = homework_map[lesson_id] # Assuming description field is correct
                
                # Save the processed data
                details = week_details_cache.get(offset)
                if details:
                    output_path = details["output_path"]
                    filename = details["filename"]
                    week_num = details["week_num"]
                    
                    # Ensure we have a valid filename by regenerating it if needed
                    if filename.endswith("0 - None-None.json") or "None" in filename:
                        year = details.get("year", datetime.now().year)
                        start_date = details.get("start_date", "")
                        end_date = details.get("end_date", "")
                        week_num = details.get("week_num", 0)
                        
                        # Extract from timetable_data.weekInfo if we have it
                        if "weekInfo" in timetable_data:
                            week_info = timetable_data["weekInfo"]
                            if not year or year == 0:
                                year = week_info.get("year", datetime.now().year)
                            if not week_num or week_num == 0:
                                week_num = week_info.get("weekNumber", offset)
                            if not start_date:
                                start_date = week_info.get("startDate", "")
                            if not end_date:
                                end_date = week_info.get("endDate", "")
                                
                        # If we're still missing the week number, use the offset as a last resort
                        if not week_num or week_num == 0:
                            # For negative offsets, they are likely previous weeks
                            # For positive offsets, they are likely next weeks
                            current_week = datetime.now().isocalendar()[1]
                            week_num = current_week + offset
                            
                        # Create a better filename
                        filename = f"{year} Vika {week_num}"
                        if start_date and end_date:
                            filename += f" - {start_date}-{end_date}"
                        filename += ".json"
                        
                        output_path = os.path.join(output_dir, filename)
                    
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(timetable_data, f, ensure_ascii=False, indent=4)
                    
                    saved_count += 1
                    if saved_count % 5 == 0 or saved_count == len(processed_data_cache):
                        log_progress(saved_count, len(processed_data_cache), "saved")
                        
                    logger.info(f"Successfully processed and saved week offset {offset} as {filename}")
                    
                    if week_num not in processed_weeks:
                         processed_weeks.add(week_num) # Add successfully saved week
                    success_count += 1
                else:
                     logger.error(f"Could not save data for offset {offset}: Missing cached details.")

            except Exception as e:
                logger.error(f"Error associating homework or saving file for offset {offset}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
        # --- End of API-based Concurrent Processing ---

    else:
        # --- Original JS-based Sequential Processing ---
        logger.info("Using JS-based navigation approach.")
        if not student_id:
            logger.warning("Student ID might be required for JS navigation but was not provided.")
            
        for i, direction in enumerate(directions):
            # Update progress periodically
            if (i+1) % 5 == 0 or i+1 == total_weeks or time.time() - last_progress_time >= progress_interval:
                log_progress(i+1, total_weeks, "JS navigation")
                
            try:
                # Process the week using JS-based navigation
                # Note: process_single_week handles its own file saving and processed_weeks update
                success = await process_single_week(
                    page=page,
                    week_offset=direction,
                    teacher_map=teacher_map,
                    student_id=student_id, # Pass student_id here
                    output_dir=output_dir,
                    api_cookies=api_cookies, # May be used internally by process_single_week for homework
                    processed_weeks=processed_weeks # Pass the set to be updated
                )
                
                if success:
                    success_count += 1
                
            except Exception as e:
                logger.error(f"Error processing week with offset {direction} using JS method: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
        # --- End of JS-based Sequential Processing ---

    logger.info(f"Finished processing. Successfully processed/skipped {success_count} of {len(directions)} requested weeks.")
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
    DEPRECATED by the concurrent logic in process_weeks when use_api=True.
    Navigate to a specific week and extract timetable data using API-based navigation.
    Kept for potential other uses or reference.
    
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
    logger.warning("navigate_and_extract_api is deprecated for use within process_weeks(use_api=True)")
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


async def get_student_id(page):
    """
    Extract the student ID from the given page.
    
    This function tries multiple methods to extract the student ID:
    1. First tries the JS integration function if available
    2. Falls back to direct extraction from the page content if JS integration is not available
    
    Args:
        page: The Playwright page object
        
    Returns:
        str: The student ID or None if not found
    """
    try:
        # First try using the JS integration function
        from glasir_timetable.js_navigation.js_integration import get_student_id as js_get_student_id
        
        try:
            # Check if glasirTimetable is available
            has_js_integration = await page.evaluate("typeof window.glasirTimetable === 'object'")
            
            if has_js_integration:
                # Use the JS integration function
                return await js_get_student_id(page)
        except Exception as e:
            logger.debug(f"JS integration for student ID extraction not available: {e}")
            # Continue with fallback methods
        
        # Direct extraction methods if JS integration is not available
        
        # Try to extract from localStorage first
        try:
            local_storage = await page.evaluate("localStorage.getItem('StudentId')")
            if local_storage:
                return local_storage.strip()
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
            return student_id.strip()
            
        # Try to find it in script tags or function calls
        content = await page.content()
        
        # Look for MyUpdate function call with student ID
        match = re.search(r"MyUpdate\s*\(\s*['\"](\d+)['\"].*?,.*?['\"]([a-zA-Z0-9-]+)['\"]", content)
        if match:
            return match.group(2).strip()
            
        # Look for a GUID pattern anywhere in the page
        guid_pattern = r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
        match = re.search(guid_pattern, content)
        if match:
            return match.group(0).strip()
            
        logger.warning("Could not extract student ID from page using any method")
        return None
            
    except Exception as e:
        logger.error(f"Error extracting student ID: {e}")
        return None 