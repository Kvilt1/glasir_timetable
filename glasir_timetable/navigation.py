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

from glasir_timetable import logger
from glasir_timetable.extractors import extract_timetable_data
from glasir_timetable.js_navigation.js_integration import (
    navigate_to_week_js,
    return_to_baseline_js,
    JavaScriptIntegrationError
)
from glasir_timetable.utils import (
    normalize_dates,
    normalize_week_number,
    generate_week_filename,
    save_json_data
)
from glasir_timetable.utils.error_utils import error_screenshot_context


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


async def navigate_and_extract(page, week_offset, teacher_map, student_id, batch_size=3):
    """
    Navigate to a specific week and extract its timetable data.
    
    Args:
        page: The Playwright page object
        week_offset: The offset from current week (0=current, 1=next, -1=previous)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        batch_size: Number of homework items to process in parallel (default: 3)
        
    Returns:
        tuple: (timetable_data, week_info) if successful, (None, None) if navigation failed
    """
    async with with_week_navigation(page, week_offset, student_id) as week_info:
        if not week_info:
            return None, None
            
        # Extract timetable data
        timetable_data, week_details = await extract_timetable_data(page, teacher_map, batch_size=batch_size)
        return timetable_data, week_info


async def process_single_week(page, week_offset, teacher_map, student_id, output_dir, processed_weeks=None, batch_size=3):
    """
    Process a single week - navigate, extract, and save data.
    
    Args:
        page: The Playwright page object
        week_offset: Offset from current week (0=current, 1=next, -1=previous)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        processed_weeks: Optional set of already processed week numbers to avoid duplicates
        batch_size: Number of homework items to process in parallel (default: 3)
        
    Returns:
        dict: Week information if successful, None if failed or already processed
    """
    if processed_weeks is None:
        processed_weeks = set()
        
    context_name = "forward_week" if week_offset > 0 else "backward_week" if week_offset < 0 else "current_week"
    
    async with error_screenshot_context(page, f"{context_name}_{abs(week_offset)}", "navigation_errors"):
        try:
            # Navigate and extract data
            timetable_data, week_info = await navigate_and_extract(page, week_offset, teacher_map, student_id, batch_size=batch_size)
            
            # Skip if navigation failed or already processed
            if not week_info or week_info.get('weekNumber') in processed_weeks:
                logger.info(f"Week navigation failed or already processed (offset {week_offset}), skipping.")
                return None
                
            # Get standardized week information
            week_num = week_info.get('weekNumber')
            year = week_info.get('year')
            start_date = week_info.get('startDate')
            end_date = week_info.get('endDate')
            
            # Mark as processed
            processed_weeks.add(week_num)
            
            # Normalize dates and week number
            start_date, end_date = normalize_dates(start_date, end_date, year)
            week_num = normalize_week_number(week_num)
            
            # Generate filename
            filename = generate_week_filename(year, week_num, start_date, end_date)
            output_path = os.path.join(output_dir, filename)
            
            # Save data to JSON file
            save_json_data(timetable_data, output_path)
            
            logger.info(f"Timetable data for Week {week_num} saved to {output_path}")
            return week_info
            
        except Exception as e:
            logger.error(f"Error processing week (offset {week_offset}): {e}")
            return None


async def process_weeks(page, directions, teacher_map, student_id, output_dir, processed_weeks=None, batch_size=3):
    """
    Process multiple weeks in the specified directions.
    
    Args:
        page: The Playwright page object
        directions: List of week offsets to process (positive for forward, negative for backward)
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: The student ID GUID
        output_dir: Directory to save output files
        processed_weeks: Optional set of already processed week numbers
        batch_size: Number of homework items to process in parallel (default: 3)
        
    Returns:
        list: Successfully processed week information
    """
    if processed_weeks is None:
        processed_weeks = set()
        
    results = []
    for direction in directions:
        result = await process_single_week(
            page=page,
            week_offset=direction,
            teacher_map=teacher_map,
            student_id=student_id,
            output_dir=output_dir,
            processed_weeks=processed_weeks,
            batch_size=batch_size
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