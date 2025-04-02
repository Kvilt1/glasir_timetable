#!/usr/bin/env python3
"""
Export functionality for the Glasir Timetable application.
This module provides functions for exporting all weeks of data.
"""

import os
import json
import asyncio
import time
from tqdm import tqdm
from datetime import datetime

from glasir_timetable import logger, update_stats, add_error
from glasir_timetable.utils import (
    normalize_dates, 
    normalize_week_number, 
    generate_week_filename,
    save_json_data
)
from glasir_timetable.js_navigation.js_integration import (
    get_student_id,
    navigate_to_week_js,
    return_to_baseline_js,
    JavaScriptIntegrationError
)
# Import directly from submodules to avoid circular dependencies
from glasir_timetable.extractors.timetable import extract_timetable_data
from glasir_timetable.extractors.homework_parser import parse_homework_html_response
from glasir_timetable.api_client import fetch_homework_for_lessons
from glasir_timetable.navigation import with_week_navigation, navigate_and_extract

async def export_all_weeks(
    page, 
    output_dir, 
    teacher_map, 
    student_id=None,
    api_cookies=None,
    concurrent_homework=True,
    max_concurrent_homework=5
):
    """
    Export all available timetable weeks to JSON files using JavaScript-based navigation.
    
    When concurrent_homework is True (default):
    - Process each week's homework independently and concurrently with week navigation
    - Save each week as soon as its homework processing is complete
    
    When concurrent_homework is False (legacy mode):
    - Uses a three-pass approach: first extract all timetable data, then fetch all homework
      in one batch, and finally combine and save results
    
    Args:
        page: Playwright page object
        output_dir: Directory to save output files
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID for JavaScript navigation (optional)
        api_cookies: Cookies for API requests
        concurrent_homework: Whether to process homework concurrently with week navigation
        max_concurrent_homework: Maximum number of concurrent homework requests
    
    Returns:
        dict: Summary of processing results
    """
    # Create result summary dictionary
    results = {
        "total_weeks": 0,
        "processed_weeks": 0,
        "errors": [],
        "skipped": 0
    }
    
    # Keep track of processed weeks using v_value which is unique across all weeks
    processed_v_values = set()
    
    # Get student ID if not provided
    if not student_id:
        try:
            student_id = await get_student_id(page)
            logger.info(f"Found student ID: {student_id}")
        except JavaScriptIntegrationError as e:
            logger.error(f"Failed to get student ID: {str(e)}")
            return results
    
    # Get all available weeks using JavaScript
    try:
        # First check if the glasirTimetable object exists
        has_timetable = await page.evaluate("""
        () => {
            console.log("Checking for glasirTimetable object:", window.glasirTimetable);
            return {
                exists: typeof window.glasirTimetable === 'object',
                functions: window.glasirTimetable ? Object.keys(window.glasirTimetable) : []
            };
        }
        """)
        
        logger.info(f"glasirTimetable exists: {has_timetable['exists']}, available functions: {has_timetable['functions']}")
        
        if not has_timetable['exists'] or 'getAllWeeks' not in has_timetable['functions']:
            logger.error("glasirTimetable object not initialized correctly or getAllWeeks function missing")
            # Try re-injecting the script
            logger.info("Attempting to re-inject the script...")
            from glasir_timetable.js_navigation.js_integration import inject_timetable_script
            await inject_timetable_script(page)
        
        # Use JavaScript to extract all available weeks
        all_weeks = await page.evaluate("""
        () => {
            console.log("Calling getAllWeeks function");
            try {
                if (!window.glasirTimetable || typeof window.glasirTimetable.getAllWeeks !== 'function') {
                    console.error("getAllWeeks function not available:", window.glasirTimetable);
                    return null;
                }
                
                const weeks = window.glasirTimetable.getAllWeeks();
                console.log("Found weeks:", weeks ? weeks.length : 0);
                return weeks;
            } catch (error) {
                console.error("Error in getAllWeeks:", error);
                return null;
            }
        }
        """)
        
        if not all_weeks:
            logger.error("Failed to extract all weeks using JavaScript")
            return results
            
        logger.info(f"Found {len(all_weeks)} weeks using JavaScript")
    except Exception as e:
        logger.error(f"Failed to get all weeks: {str(e)}")
        return results
    
    # Update statistics
    results["total_weeks"] = len(all_weeks)
    update_stats("total_weeks", len(all_weeks), increment=False)
    
    # Sort weeks by v_value to ensure sequential processing (first year first)
    # v_value is negative and increases toward 0, so sort in reverse
    all_weeks.sort(key=lambda w: w.get('v', 0), reverse=True)
    
    if concurrent_homework:
        # Process with concurrent homework (new approach)
        return await export_all_weeks_concurrent(
            page=page,
            all_weeks=all_weeks,
            teacher_map=teacher_map,
            student_id=student_id,
            output_dir=output_dir,
            api_cookies=api_cookies,
            max_concurrent_homework=max_concurrent_homework,
            processed_v_values=processed_v_values,
            results=results
        )
    else:
        # Process with the original three-pass approach
        return await export_all_weeks_sequential(
            page=page,
            all_weeks=all_weeks,
            teacher_map=teacher_map,
            student_id=student_id,
            output_dir=output_dir,
            api_cookies=api_cookies,
            processed_v_values=processed_v_values,
            results=results
        )

async def export_all_weeks_concurrent(
    page, 
    all_weeks,
    teacher_map, 
    student_id,
    output_dir,
    api_cookies,
    max_concurrent_homework,
    processed_v_values,
    results
):
    """
    Export all weeks with concurrent homework processing.
    Homework is processed independently and simultaneously with week navigation and extraction.
    
    Args:
        page: Playwright page object
        all_weeks: List of all weeks to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID for JavaScript navigation
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        max_concurrent_homework: Maximum number of concurrent homework requests
        processed_v_values: Set of already processed v_values
        results: Dictionary to track results
        
    Returns:
        dict: Updated results dictionary
    """
    # Create a semaphore to limit concurrent homework requests
    homework_semaphore = asyncio.Semaphore(max_concurrent_homework)
    
    # Shared dictionary for homework results
    homework_results = {}
    
    # Track pending tasks for each week
    week_tasks = {}
    
    # Queue for lesson IDs to process
    homework_queue = []
    
    # Flag to indicate that all weeks have been processed
    all_weeks_processed = asyncio.Event()
    
    # Async function to process a batch of lesson homework
    async def process_homework_batch(batch):
        try:
            # Fetch homework for the entire batch in one API call
            homework_html = await fetch_homework_for_lessons(
                cookies=api_cookies,
                lesson_ids=batch
            )
            
            # Store results in shared dictionary
            if homework_html:
                for lesson_id, content in homework_html.items():
                    homework_results[lesson_id] = content
                
                logger.info(f"Successfully fetched homework for {len(homework_html)}/{len(batch)} lessons in batch")
            return True
        except Exception as e:
            logger.error(f"Error fetching homework for batch of {len(batch)} lessons: {e}")
            return False
        
    # Async function to process a single lesson homework
    async def process_single_lesson(lesson_id):
        async with homework_semaphore:
            try:
                # Fetch homework for this lesson
                homework_html = await fetch_homework_for_lessons(
                    cookies=api_cookies,
                    lesson_ids=[lesson_id]
                )
                
                # Store result in shared dictionary
                if homework_html and lesson_id in homework_html:
                    homework_results[lesson_id] = homework_html[lesson_id]
                    return True
                return False
            except Exception as e:
                logger.error(f"Error fetching homework for lesson {lesson_id}: {e}")
                return False
    
    # Async function to continuously process homework from the queue
    async def homework_processor():
        while True:
            # If the queue is empty and all weeks have been processed, exit
            if not homework_queue and all_weeks_processed.is_set():
                break
            
            # If the queue has enough items to fill the batch or all weeks are processed
            # and there are still items in the queue, process them
            if len(homework_queue) >= max_concurrent_homework or (all_weeks_processed.is_set() and homework_queue):
                # Take at most max_concurrent_homework items from the queue
                batch_size = min(max_concurrent_homework, len(homework_queue))
                batch = homework_queue[:batch_size]
                homework_queue[:batch_size] = []
                
                logger.info(f"Processing batch of {len(batch)} homework items, {len(homework_queue)} remaining in queue")
                # Process the entire batch in one go rather than as individual lessons
                await process_homework_batch(batch)
            else:
                # Wait a short time for more items to be added to the queue
                await asyncio.sleep(0.1)
    
    # Async function to save a week with homework data
    async def save_week_with_homework(week_data):
        try:
            # Merge homework data into timetable data
            merged_count = 0
            for event in week_data["timetable_data"].get("events", []):
                lesson_id = event.get("lessonId")
                if lesson_id and lesson_id in homework_results:
                    event["description"] = homework_results[lesson_id]
                    merged_count += 1
            
            # Save the merged data
            save_json_data(week_data["timetable_data"], week_data["output_path"])
            logger.info(f"Saved week {week_data['week_num']} with {merged_count} homework items")
            return True
        except Exception as e:
            logger.error(f"Error saving week {week_data['week_num']}: {e}")
            return False
    
    # Start the homework processor
    homework_processor_task = asyncio.create_task(homework_processor())
    
    # Process all weeks with concurrent homework processing
    with tqdm(total=len(all_weeks), desc="Processing weeks", unit="week") as pbar:
        start_time = time.time()
        
        # List to store week data for saving later
        weeks_to_save = []
        
        for week_index, week in enumerate(all_weeks):
            # Skip based on v_value
            v_value = week.get('v')
            if v_value is None or v_value in processed_v_values:
                results["skipped"] += 1
                pbar.update(1)
                continue
            
            # Get week info
            week_num = week.get('weekNum', 0)
            academic_year = week.get('academicYear', 0)
            
            pbar.set_description(f"Week {week_num} (v={v_value}, year={academic_year})")
            
            try:
                # Extract timetable data without fetching homework yet
                async with with_week_navigation(page, v_value, student_id, return_to_baseline=False) as week_info:
                    # Skip if navigation failed
                    if not week_info:
                        error_msg = f"Failed to navigate to week {week_num} (v={v_value})"
                        results["errors"].append({"week": week_num, "error": error_msg})
                        logger.error(error_msg)
                        pbar.update(1)
                        continue
                    
                    # Extract timetable data without homework
                    timetable_data, week_details, homework_lesson_ids = await extract_timetable_data(
                        page, teacher_map, use_models=False
                    )
                    
                    # Skip if no data or no events
                    if not timetable_data or "events" not in timetable_data:
                        pbar.update(1)
                        continue
                    
                    # Get standardized week information
                    year = week_info.get('year', datetime.now().year)
                    start_date = week_info.get('startDate')
                    end_date = week_info.get('endDate')
                    
                    # Normalize and validate dates
                    start_date, end_date = normalize_dates(start_date, end_date, year)
                    
                    # Normalize week number
                    normalized_week_num = normalize_week_number(week_num)
                    
                    # Generate filename for saving
                    filename = generate_week_filename(year, normalized_week_num, start_date, end_date)
                    output_path = os.path.join(output_dir, filename)
                    
                    # Store week data for later saving
                    week_data = {
                        "timetable_data": timetable_data,
                        "filename": filename,
                        "output_path": output_path,
                        "week_num": week_num
                    }
                    weeks_to_save.append(week_data)
                    
                    # Add lesson IDs to the homework queue if we have API cookies
                    if api_cookies:
                        for event in timetable_data.get("events", []):
                            lesson_id = event.get("lessonId")
                            if lesson_id and lesson_id not in homework_results:
                                if lesson_id not in homework_queue:
                                    homework_queue.append(lesson_id)
                    else:
                        # If no API cookies, just save without homework
                        save_json_data(week_data["timetable_data"], week_data["output_path"])
                    
                    # Mark as processed
                    processed_v_values.add(v_value)
                    results["processed_weeks"] += 1
                    update_stats("processed_weeks")
                    
                    # Update progress bar
                    pbar.set_postfix({
                        "success": results["processed_weeks"], 
                        "homework_queue": len(homework_queue)
                    })
            
            except Exception as e:
                # Handle errors
                error_msg = f"Error processing week {week_num}: {str(e)}"
                results["errors"].append({"week": week_num, "error": error_msg})
                add_error("extraction_errors", error_msg, {"v_value": v_value, "week_num": week_num})
                logger.error(error_msg)
                
                # Take a screenshot for debugging
                try:
                    await page.screenshot(path=f"error_week_{week_num}.png")
                except Exception as screenshot_error:
                    logger.error(f"Failed to take error screenshot: {str(screenshot_error)}")
            
            finally:
                pbar.update(1)
    
    # Signal that all weeks have been processed
    all_weeks_processed.set()
    
    # Wait for the homework processor to finish
    await homework_processor_task
    
    # Save all weeks with the processed homework
    logger.info(f"Saving {len(weeks_to_save)} weeks with processed homework...")
    save_tasks = []
    for week_data in weeks_to_save:
        save_tasks.append(save_week_with_homework(week_data))
    
    if save_tasks:
        await asyncio.gather(*save_tasks)
    
    return results

async def export_all_weeks_sequential(
    page, 
    all_weeks,
    teacher_map, 
    student_id,
    output_dir,
    api_cookies,
    processed_v_values,
    results
):
    """
    Original three-pass approach for exporting all weeks.
    
    First pass: Extract all timetable data
    Second pass: Fetch all homework at once
    Third pass: Merge and save all data
    
    Args:
        page: Playwright page object
        all_weeks: List of all weeks to process
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID for JavaScript navigation
        output_dir: Directory to save output files
        api_cookies: Cookies for API requests
        processed_v_values: Set of already processed v_values
        results: Dictionary to track results
        
    Returns:
        dict: Updated results dictionary
    """
    # Store extracted timetable data for all weeks
    all_timetable_data = []
    
    # Track all lesson IDs and their mapping to weeks/events
    all_lesson_ids = []
    lesson_mapping = {}  # Maps lesson_id -> (week_index, event_index)
    
    # FIRST PASS: Process each week and collect timetable data and lesson IDs
    logger.info("FIRST PASS: Extracting timetable data for all weeks...")
    with tqdm(total=len(all_weeks), desc="Extracting timetable data", unit="week",
         bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
        start_time = time.time()
        
        for week in all_weeks:
            # Skip based on v_value instead of week_num
            v_value = week.get('v')
            if v_value is None:
                results["skipped"] += 1
                pbar.update(1)
                continue
                
            if v_value in processed_v_values:
                results["skipped"] += 1
                pbar.update(1)
                continue
            
            # Get week info
            week_num = week.get('weekNum', 0)
            academic_year = week.get('academicYear', 0)
            
            pbar.set_description(f"Week {week_num} (v={v_value}, year={academic_year})")
            
            try:
                # Use the with_week_navigation context manager for safer navigation
                async with with_week_navigation(page, v_value, student_id, return_to_baseline=False) as week_info:
                    # Skip if navigation failed
                    if not week_info:
                        error_msg = f"Failed to navigate to week {week_num} (v={v_value})"
                        results["errors"].append({"week": week_num, "error": error_msg})
                        logger.error(error_msg)
                        pbar.update(1)
                        continue
                    
                    # Extract timetable data without fetching homework yet
                    timetable_data, week_details, homework_lesson_ids = await extract_timetable_data(
                        page, teacher_map, use_models=False
                    )
                    
                    # Skip if no data or no events
                    if not timetable_data or "events" not in timetable_data:
                        pbar.update(1)
                        continue
                    
                    # Get standardized week information
                    year = week_info.get('year', datetime.now().year)
                    start_date = week_info.get('startDate')
                    end_date = week_info.get('endDate')
                    
                    # Normalize and validate dates
                    start_date, end_date = normalize_dates(start_date, end_date, year)
                    
                    # Normalize week number
                    normalized_week_num = normalize_week_number(week_num)
                    
                    # Generate filename for later saving
                    filename = generate_week_filename(year, normalized_week_num, start_date, end_date)
                    output_path = os.path.join(output_dir, filename)
                    
                    # Store week data and metadata for later processing
                    week_index = len(all_timetable_data)
                    week_data = {
                        "timetable_data": timetable_data,
                        "filename": filename,
                        "output_path": output_path
                    }
                    all_timetable_data.append(week_data)
                    
                    # Collect all lesson IDs from this week and map to their location
                    for event_index, event in enumerate(timetable_data.get("events", [])):
                        lesson_id = event.get("lessonId")
                        if lesson_id:
                            all_lesson_ids.append(lesson_id)
                            lesson_mapping[lesson_id] = (week_index, event_index)
                    
                    # Mark as processed using v_value instead of week_num
                    processed_v_values.add(v_value)
                    results["processed_weeks"] += 1
                    update_stats("processed_weeks")
                    
                    # Calculate and display statistics
                    elapsed = time.time() - start_time
                    items_per_min = 60 * results["processed_weeks"] / elapsed if elapsed > 0 else 0
                    remaining = (len(all_weeks) - pbar.n) / items_per_min * 60 if items_per_min > 0 else 0
                    
                    pbar.set_postfix({
                        "success": results["processed_weeks"], 
                        "rate": f"{items_per_min:.1f}/min",
                        "lesson_ids": len(all_lesson_ids)
                    })
            
            except Exception as e:
                # Handle errors
                error_msg = f"Error processing week {week_num}: {str(e)}"
                results["errors"].append({"week": week_num, "error": error_msg})
                add_error("extraction_errors", error_msg, {"v_value": v_value, "week_num": week_num})
                logger.error(error_msg)
                
                # Take a screenshot for debugging
                try:
                    await page.screenshot(path=f"error_week_{week_num}.png")
                except Exception as screenshot_error:
                    logger.error(f"Failed to take error screenshot: {str(screenshot_error)}")
            
            finally:
                pbar.update(1)
    
    # SECOND PASS: Fetch all homework data in one batch
    logger.info(f"SECOND PASS: Fetching homework for {len(all_lesson_ids)} lessons across {len(all_timetable_data)} weeks...")
    
    all_homework = {}
    if api_cookies and all_lesson_ids:
        try:
            # Use the optimized batch function to fetch all homework at once
            all_homework = await fetch_homework_for_lessons(
                cookies=api_cookies,
                lesson_ids=all_lesson_ids
            )
            
            logger.info(f"Successfully fetched homework for {len(all_homework)}/{len(all_lesson_ids)} lessons")
            
        except Exception as e:
            logger.error(f"Error fetching homework data: {e}")
    
    # THIRD PASS: Merge homework and save all weeks
    logger.info("THIRD PASS: Merging homework and saving all weeks...")
    
    saved_count = 0
    with tqdm(total=len(all_timetable_data), desc="Saving weeks", unit="week") as pbar:
        for week_data in all_timetable_data:
            try:
                # Merge homework data into this week's timetable data
                merged_count = 0
                for event_index, event in enumerate(week_data["timetable_data"].get("events", [])):
                    lesson_id = event.get("lessonId")
                    if lesson_id and lesson_id in all_homework:
                        event["description"] = all_homework[lesson_id]
                        merged_count += 1
                
                # Save the merged data to disk
                save_json_data(week_data["timetable_data"], week_data["output_path"])
                saved_count += 1
                
                pbar.set_postfix({"merged": merged_count})
                
            except Exception as e:
                logger.error(f"Error merging homework or saving week: {e}")
            
            finally:
                pbar.update(1)
    
    logger.info(f"Successfully saved {saved_count}/{len(all_timetable_data)} weeks with homework data")
    
    return results

async def export_all_weeks_api(
    page, 
    output_dir, 
    teacher_map, 
    api_cookies,
    navigation_service=None
):
    """
    Export all available timetable weeks to JSON files using API-based approach.
    
    This implementation uses API calls to fetch data without navigating the page,
    which preserves the lname value throughout the process.
    
    Args:
        page: Playwright page object
        output_dir: Directory to save output files
        teacher_map: Dictionary mapping teacher initials to full names
        api_cookies: Cookies for API requests
        navigation_service: Optional navigation service for additional functionality
        
    Returns:
        dict: Summary of processing results
    """
    from glasir_timetable.navigation import navigate_and_extract_api, process_single_week_api
    from glasir_timetable.js_navigation.js_integration import get_student_id
    from glasir_timetable.api_client import fetch_weeks_data
    from glasir_timetable.utils.param_utils import parse_dynamic_params
    
    # Create result summary dictionary
    results = {
        "total_weeks": 0,
        "processed_weeks": 0,
        "errors": [],
        "skipped": 0
    }
    
    # Keep track of processed weeks using v_value which is unique across all weeks
    processed_v_values = set()
    
    # Extract required values for API calls
    try:
        # Get student ID
        student_id = await get_student_id(page)
        logger.info(f"Found student ID: {student_id}")
        
        # Get lname and timer values
        content = await page.content()
        lname_value, timer_value = parse_dynamic_params(content)
        logger.info(f"Found lname value: {lname_value}")
        logger.info(f"Found timer value: {timer_value}")
        
    except Exception as e:
        logger.error(f"Failed to extract required values: {str(e)}")
        return results
    
    # First, try to get all weeks using the API
    try:
        logger.info("Attempting to get all weeks using API...")
        all_weeks = []
        
        # First, get weeks from the current view/academic year
        current_weeks_data = await fetch_weeks_data(
            cookies=api_cookies,
            student_id=student_id,
            lname_value=lname_value,
            timer_value=timer_value
        )
        
        if current_weeks_data and "weeks" in current_weeks_data:
            all_weeks.extend(current_weeks_data["weeks"])
            logger.info(f"Found {len(current_weeks_data['weeks'])} weeks from current view")
        
        # If we need more comprehensive coverage, we need to navigate through different academic years
        # This is a workaround since the API doesn't provide a direct way to get all weeks across all years
        
        # First, try to discover additional years by navigating to different pivot points
        # These offset values often correspond to the first week of different academic years
        year_pivot_offsets = [-53, -105, -157, -209, -261]  # Approximations for different academic years
        
        for pivot in year_pivot_offsets:
            try:
                logger.info(f"Fetching weeks at year pivot offset {pivot}...")
                pivot_weeks_data = await fetch_weeks_data(
                    cookies=api_cookies,
                    student_id=student_id,
                    lname_value=lname_value,
                    timer_value=timer_value,
                    v_override=str(pivot)  # Use specific offset as year pivot
                )
                
                if pivot_weeks_data and "weeks" in pivot_weeks_data:
                    new_weeks = pivot_weeks_data["weeks"]
                    logger.info(f"Found {len(new_weeks)} weeks at pivot {pivot}")
                    
                    # Add only weeks we haven't seen before
                    for week in new_weeks:
                        if week not in all_weeks and "offset" in week:
                            all_weeks.append(week)
            except Exception as e:
                logger.warning(f"Error fetching weeks at pivot {pivot}: {e}")
        
        # As a fallback, if we're still not getting enough weeks, try using the JS integration
        if len(all_weeks) < 50:  # If we found suspiciously few weeks
            logger.info("Attempting to use JavaScript to discover all available weeks...")
            try:
                # Try to get comprehensive list of weeks using JavaScript
                js_weeks = await page.evaluate("""
                () => {
                    if (window.glasirTimetable && typeof window.glasirTimetable.getAllWeeks === 'function') {
                        return window.glasirTimetable.getAllWeeks();
                    }
                    return null;
                }
                """)
                
                if js_weeks:
                    logger.info(f"Found {len(js_weeks)} weeks using JavaScript")
                    
                    # Convert JS format to API format
                    for js_week in js_weeks:
                        if "v" in js_week:  # JavaScript version uses 'v' for offset
                            api_week = {
                                "offset": js_week["v"],
                                "week_number": js_week.get("weekNum", "")
                            }
                            # Add if we don't already have this offset
                            if not any(w.get("offset") == api_week["offset"] for w in all_weeks):
                                all_weeks.append(api_week)
            except Exception as e:
                logger.warning(f"Error using JavaScript fallback: {e}")
        
        # Remove duplicates based on offset
        seen_offsets = set()
        unique_weeks = []
        for week in all_weeks:
            offset = week.get("offset")
            if offset is not None and offset not in seen_offsets:
                seen_offsets.add(offset)
                unique_weeks.append(week)
        
        all_weeks = unique_weeks
        
        if not all_weeks:
            logger.error("Failed to extract any weeks using API or fallbacks")
            return results
            
        logger.info(f"Found total of {len(all_weeks)} unique weeks after deduplication")
    except Exception as e:
        logger.error(f"Failed to get all weeks: {str(e)}")
        return results
    
    # Update statistics
    results["total_weeks"] = len(all_weeks)
    update_stats("total_weeks", len(all_weeks), increment=False)
    
    # Sort weeks by offset to ensure sequential processing
    all_weeks.sort(key=lambda w: w.get('offset', 0))
    
    # Process each week sequentially
    start_time = time.time()
    with tqdm(total=len(all_weeks), desc="Processing weeks", unit="week") as pbar:
        for week in all_weeks:
            try:
                offset = week.get('offset')
                week_num = week.get('week_number')
                
                # Check if we've already processed this week
                if offset in processed_v_values:
                    logger.info(f"Week {week_num} (offset {offset}) already processed, skipping")
                    results["skipped"] += 1
                    continue
                
                # Process this week using API-based navigation
                week_result = await process_single_week_api(
                    page=page,
                    week_offset=offset,
                    output_dir=output_dir,
                    teacher_map=teacher_map,
                    api_cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value
                )
                
                if week_result.get("success"):
                    processed_v_values.add(offset)
                    results["processed_weeks"] += 1
                    update_stats("processed_weeks")
                else:
                    error_msg = week_result.get("error", "Unknown error")
                    results["errors"].append({"week": week_num, "error": error_msg})
                    add_error("extraction_errors", error_msg, {"offset": offset, "week_num": week_num})
                
                # Calculate and display statistics
                elapsed = time.time() - start_time
                items_per_min = 60 * results["processed_weeks"] / elapsed if elapsed > 0 else 0
                remaining = (len(all_weeks) - pbar.n) / items_per_min * 60 if items_per_min > 0 else 0
                
                pbar.set_postfix({
                    "success": results["processed_weeks"],
                    "rate": f"{items_per_min:.1f}/min",
                    "remaining": f"{remaining:.1f}min"
                })
                
            except Exception as e:
                # Handle errors
                error_msg = f"Error processing week {week.get('week_number')}: {str(e)}"
                results["errors"].append({"week": week.get('week_number'), "error": error_msg})
                add_error("extraction_errors", error_msg, {"offset": week.get('offset'), "week_num": week.get('week_number')})
                logger.error(error_msg)
                
                # Take a screenshot for debugging
                try:
                    await page.screenshot(path=f"error_week_{week.get('week_number')}.png")
                except Exception as screenshot_error:
                    logger.error(f"Failed to take error screenshot: {str(screenshot_error)}")
            
            finally:
                pbar.update(1)
    
    logger.info(f"All weeks processed. Successfully exported {results['processed_weeks']}/{results['total_weeks']} weeks.")
    return results 