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
from glasir_timetable.utils import normalize_dates, normalize_week_number, generate_week_filename
from glasir_timetable.js_navigation.js_integration import (
    get_student_id,
    navigate_to_week_js,
    extract_all_homework_content_js,
    return_to_baseline_js,
    JavaScriptIntegrationError
)
from glasir_timetable.extractors import extract_timetable_data

async def export_all_weeks(
    page, 
    output_dir, 
    teacher_map, 
    student_id=None
):
    """
    Export all available timetable weeks to JSON files using JavaScript-based navigation.
    
    Args:
        page: Playwright page object
        output_dir: Directory to save output files
        teacher_map: Dictionary mapping teacher initials to full names
        student_id: Student ID for JavaScript navigation (optional)
    
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
    # Don't use week numbers as they repeat across academic years
    processed_v_values = set()
    
    # If student_id not provided, get it from the page
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
        logger.error(f"Error getting all weeks: {str(e)}")
        return results
    
    # Update statistics
    results["total_weeks"] = len(all_weeks)
    update_stats("total_weeks", len(all_weeks), increment=False)
    
    # Process each week with progress bar
    with tqdm(total=len(all_weeks), desc="Processing weeks", unit="week",
         bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]") as pbar:
        start_time = time.time()
        
        # Sort weeks by v_value to ensure sequential processing (first year first)
        # v_value is negative and increases toward 0, so sort in reverse
        all_weeks.sort(key=lambda w: w.get('v', 0), reverse=True)
        
        for week in all_weeks:
            # Skip based on v_value instead of week_num
            v_value = week.get('v')
            if v_value is None:
                logger.warning(f"No v-value for week {week.get('weekNum')}, skipping")
                pbar.update(1)
                results["skipped"] += 1
                continue
                
            # Skip if already processed using v_value
            if v_value in processed_v_values:
                pbar.update(1)
                results["skipped"] += 1
                logger.debug(f"Skipping already processed week with v_value={v_value}")
                continue
            
            week_num = week.get('weekNum')
            academic_year = week.get('academicYear', 0)
            
            pbar.set_description(f"Week {week_num} (v={v_value}, year={academic_year})")
            
            try:
                # Navigate to the week using JavaScript
                week_info = await navigate_to_week_js(page, v_value, student_id)
                
                # Skip if navigation failed
                if not week_info:
                    error_msg = f"Failed to navigate to week {week_num} (v={v_value})"
                    results["errors"].append({"week": week_num, "error": error_msg})
                    logger.error(error_msg)
                    pbar.update(1)
                    continue
                
                # Extract timetable data
                timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                
                # Get standardized week information
                year = week_info.get('year', datetime.now().year)
                start_date = week_info.get('startDate')
                end_date = week_info.get('endDate')
                
                # Normalize and validate dates
                start_date, end_date = normalize_dates(start_date, end_date, year)
                
                # Normalize week number
                normalized_week_num = normalize_week_number(week_num)
                
                # Generate filename
                filename = generate_week_filename(year, normalized_week_num, start_date, end_date)
                output_path = os.path.join(output_dir, filename)
                
                # Save data to JSON file
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                
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
                    "ETA": f"{remaining:.1f}m"
                })
                
                # Log success
                logger.debug(f"Timetable data for Week {normalized_week_num} saved to {output_path}")
            
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
                # Return to baseline
                try:
                    await return_to_baseline_js(page, 0, student_id)
                except Exception as e:
                    logger.error(f"Error returning to baseline: {str(e)}")
                
                # Wait between requests
                await asyncio.sleep(0.2)  # Short delay for JS-based navigation
                
                # Update progress
                pbar.update(1)
    
    # Return results summary
    return results 