#!/usr/bin/env python3
"""
Main entry point for the Glasir Timetable application.
"""
import os
import json
import asyncio
import sys
import argparse
import re
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path if running as script
if __name__ == "__main__":
    # Get the parent directory of this file
    parent_dir = Path(__file__).resolve().parent
    # Add to sys.path if not already there
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

# Now the imports will work both when run as a script and when imported as a module
from tqdm import tqdm
from playwright.async_api import async_playwright
from glasir_timetable import logger, setup_logging, stats, update_stats, error_collection, get_error_summary, clear_errors, add_error
from glasir_timetable.auth import login_to_glasir
from glasir_timetable.extractors import (
    extract_teacher_map, 
    extract_timetable_data,
    get_current_week_info
)

# Import JavaScript navigation functions
from glasir_timetable.js_navigation import (
    export_all_weeks
)
from glasir_timetable.js_navigation.js_integration import (
    inject_timetable_script,
    get_student_id,
    navigate_to_week_js,
    return_to_baseline_js,
    test_javascript_integration,
    JavaScriptIntegrationError
)

# Import utility functions
from glasir_timetable.utils import (
    normalize_dates,
    normalize_week_number,
    generate_week_filename,
    convert_keys_to_camel_case,
    save_json_data
)

# Import error handling utilities
from glasir_timetable.utils.error_utils import (
    error_screenshot_context,
    register_console_listener,
    handle_errors,
    resource_cleanup_context,
    async_resource_cleanup_context
)

def is_new_format(timetable_data):
    """
    Check if the timetable data is in the new format.
    
    Args:
        timetable_data (dict): The timetable data to check
        
    Returns:
        bool: True if the data is in the new format, False otherwise
    """
    return isinstance(timetable_data, dict) and timetable_data.get("formatVersion") == 2

async def main():
    """
    Main entry point for the Glasir Timetable application.
    """
    # Initialize statistics
    from glasir_timetable import stats, update_stats, clear_errors
    clear_errors()  # Clear any errors from previous runs
    update_stats("start_time", time.time(), increment=False)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Extract timetable data from Glasir')
    parser.add_argument('--email', type=str, help='Email for login')
    parser.add_argument('--password', type=str, help='Password for login')
    parser.add_argument('--credentials-file', type=str, default='glasir_timetable/credentials.json', help='JSON file with email and password')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--all-weeks', action='store_true', help='Extract all available weeks from all academic years')
    parser.add_argument('--output-dir', type=str, default='glasir_timetable/weeks', help='Directory to save output files')
    parser.add_argument('--test-js', action='store_true', help='Test the JavaScript integration before extracting data')
    parser.add_argument('--headless', action='store_false', dest='headless', default=True, help='Run in non-headless mode (default: headless=True)')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                        default='INFO', help='Set the logging level')
    parser.add_argument('--log-file', type=str, help='Log to a file instead of console')
    args = parser.parse_args()
    
    # Configure logging based on command-line arguments
    log_level = getattr(logging, args.log_level)
    if args.log_file:
        # Add file handler if log file is specified
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(file_handler)
    
    # Set the log level
    logger.setLevel(log_level)
    for handler in logger.handlers:
        handler.setLevel(log_level)
    
    # Load credentials
    credentials = {}
    if os.path.exists(args.credentials_file):
        try:
            with open(args.credentials_file, 'r') as f:
                credentials = json.load(f)
        except FileNotFoundError:
            logger.error(f"{args.credentials_file} not found. Please create a credentials.json file with 'email' and 'password' fields.")
            return
    
    # Command line arguments override credentials file
    if args.email:
        credentials["email"] = args.email
    if args.password:
        credentials["password"] = args.password
    
    # Check for required credentials
    if "email" not in credentials or "password" not in credentials:
        logger.error("Email and password must be provided either in credentials file or as command line arguments")
        return
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir, exist_ok=True)
        logger.debug(f"Created output directory: {args.output_dir}")
    
    # Initialize Playwright
    async with async_playwright() as p:
        # Setup resources with cleanup context
        resources = {
            "browser": None,
            "context": None,
            "page": None
        }
        
        # Define cleanup functions
        cleanup_funcs = {
            "browser": lambda browser: asyncio.create_task(browser.close())
        }
        
        # Use async resource cleanup context manager
        async with async_resource_cleanup_context(resources, cleanup_funcs):
            # Initialize browser and page
            resources["browser"] = await p.chromium.launch(headless=args.headless)
            resources["context"] = await resources["browser"].new_context()
            resources["page"] = await resources["context"].new_page()
            page = resources["page"]
            
            # Register console listener
            register_console_listener(page)
            
            async with error_screenshot_context(page, "main", "general_errors"):
                # Login to Glasir
                await login_to_glasir(page, credentials["email"], credentials["password"])
                
                # Initialize student_id for JavaScript navigation
                student_id = None
                
                async with error_screenshot_context(page, "js_init", "javascript_errors"):
                    # Inject the JavaScript navigation script
                    await inject_timetable_script(page)
                    
                    # Test the JavaScript integration if requested
                    if args.test_js:
                        logger.info("Testing JavaScript integration...")
                        await test_javascript_integration(page)
                        logger.info("JavaScript integration test passed!")
                        
                    # Get student ID (needed for navigation)
                    student_id = await get_student_id(page)
                    logger.info(f"Found student ID: {student_id}")
                
                # Extract dynamic teacher mapping from the page
                teacher_map = await extract_teacher_map(page)
                
                # Process all weeks if requested
                if args.all_weeks:
                    logger.info("Processing all weeks from all academic years...")
                    
                    # Export all weeks using the dedicated function
                    export_results = await export_all_weeks(
                        page=page,
                        output_dir=args.output_dir,
                        teacher_map=teacher_map,
                        student_id=student_id
                    )
                    
                    # Log results
                    logger.info(f"Completed processing all weeks. Extracted {export_results['processed_weeks']} of {export_results['total_weeks']} weeks.")
                    if export_results['errors']:
                        logger.warning(f"Encountered {len(export_results['errors'])} errors during extraction.")
                    
                    # Skip the rest of the processing since we've already handled all weeks
                    return
                
                # Extract and save current week data (unless we're only getting all weeks)
                logger.info("Processing current week...")
                
                # Extract current week data
                timetable_data, week_info = await extract_timetable_data(page, teacher_map)
                
                # Format filename with standardized format
                start_date = week_info['start_date']
                end_date = week_info['end_date']
                
                # Normalize dates and week number
                start_date, end_date = normalize_dates(start_date, end_date, week_info['year'])
                week_num = normalize_week_number(week_info['week_num'])
                
                # Generate filename
                filename = generate_week_filename(week_info['year'], week_num, start_date, end_date)
                output_path = os.path.join(args.output_dir, filename)
                
                # Save data to JSON file
                save_json_data(timetable_data, output_path)
                    
                logger.info(f"Timetable data saved to {output_path}")
                
                # Store processed weeks to avoid duplicates
                processed_weeks = {week_info['week_num']}
                
                # Process backward weeks if requested
                for i in range(1, args.weekbackward + 1):
                    logger.info(f"Processing week backward {i}...")
                    
                    async with error_screenshot_context(page, f"backward_week_{i}", "navigation_errors"):
                        try:
                            # Navigate using JavaScript
                            week_info = await navigate_to_week_js(page, -i, student_id)
                            
                            # Skip if navigation failed or we've already processed this week
                            if not week_info or week_info.get('weekNumber') in processed_weeks:
                                logger.info(f"Week navigation failed or already processed, skipping.")
                                # Return to baseline
                                await return_to_baseline_js(page, 0, student_id)
                                continue
                                
                            # Extract timetable data
                            timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                            
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
                            output_path = os.path.join(args.output_dir, filename)
                            
                            # Save data to JSON file
                            save_json_data(timetable_data, output_path)
                            
                            logger.info(f"Timetable data for Week {week_num} saved to {output_path}")
                        finally:
                            # Always try to return to baseline, even if there was an error
                            try:
                                await return_to_baseline_js(page, 0, student_id)
                            except Exception as e:
                                logger.error(f"Error returning to baseline: {e}")
                        
                # Process forward weeks if requested
                for i in range(1, args.weekforward + 1):
                    logger.info(f"Processing week forward {i}...")
                    
                    async with error_screenshot_context(page, f"forward_week_{i}", "navigation_errors"):
                        try:
                            # Navigate using JavaScript
                            week_info = await navigate_to_week_js(page, i, student_id)
                            
                            # Skip if navigation failed or we've already processed this week
                            if not week_info or week_info.get('weekNumber') in processed_weeks:
                                logger.info(f"Week navigation failed or already processed, skipping.")
                                # Return to baseline
                                await return_to_baseline_js(page, 0, student_id)
                                continue
                            
                            # Extract timetable data
                            timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                            
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
                            output_path = os.path.join(args.output_dir, filename)
                            
                            # Save data to JSON file
                            save_json_data(timetable_data, output_path)
                            
                            logger.info(f"Timetable data for Week {week_num} saved to {output_path}")
                        finally:
                            # Always try to return to baseline, even if there was an error
                            try:
                                await return_to_baseline_js(page, 0, student_id)
                            except Exception as e:
                                logger.error(f"Error returning to baseline: {e}")

            # Print summary of errors
            error_summary = get_error_summary()
            if error_summary:
                logger.info("\nError Summary:")
                for category, count in error_summary.items():
                    logger.info(f"  {category}: {count}")
            
            # Calculate and log statistics
            end_time = time.time()
            start_time = stats.get("start_time", end_time)
            elapsed = end_time - start_time
            logger.info(f"Extraction completed in {elapsed:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())