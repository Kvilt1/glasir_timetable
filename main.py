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
import getpass

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
    async_resource_cleanup_context,
    configure_error_handling
)

# Import navigation utilities
from glasir_timetable.navigation import (
    process_weeks,
    process_single_week,
    navigate_and_extract,
    get_week_directions
)

from glasir_timetable.models import TimetableData
from glasir_timetable.utils.model_adapters import timetable_data_to_dict

# Import service factory for dependency injection
from glasir_timetable.service_factory import create_services, get_service

def generate_credentials_file(file_path, username, password):
    """
    Generate a credentials file with the provided username and password.
    
    Args:
        file_path (str): Path where the file should be created
        username (str): Username to save
        password (str): Password to save
    """
    credentials = {
        "username": username,
        "password": password
    }
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(credentials, f, indent=4)
    logger.info(f"Credentials saved to {file_path}")

def prompt_for_credentials():
    """
    Prompt the user to enter their username and password interactively.
    
    Returns:
        dict: Dictionary with username and password keys
    """
    print("\nNo credentials found. Please enter your Glasir login details:")
    username = input("Username (without @glasir.fo): ")
    password = getpass.getpass("Password: ")
    return {"username": username, "password": password}

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
    parser.add_argument('--username', type=str, help='Username for login (without @glasir.fo)')
    parser.add_argument('--password', type=str, help='Password for login')
    parser.add_argument('--credentials-file', type=str, default='glasir_timetable/credentials.json', help='JSON file with username and password')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--all-weeks', action='store_true', help='Extract all available weeks from all academic years')
    parser.add_argument('--output-dir', type=str, default='glasir_timetable/weeks', help='Directory to save output files')
    parser.add_argument('--test-js', action='store_true', help='Test the JavaScript integration before extracting data')
    parser.add_argument('--headless', action='store_false', dest='headless', default=True, help='Run in non-headless mode (default: headless=True)')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                        default='INFO', help='Set the logging level')
    parser.add_argument('--log-file', type=str, help='Log to a file instead of console')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of homework items to process in parallel (default: 5)')
    parser.add_argument('--unlimited-batch-size', action='store_true', help='Process all homework items in a single batch (overrides --batch-size)')
    parser.add_argument('--collect-error-details', action='store_true', help='Collect detailed error information')
    parser.add_argument('--collect-tracebacks', action='store_true', help='Collect tracebacks for errors')
    parser.add_argument('--enable-screenshots', action='store_true', help='Enable screenshots on errors')
    parser.add_argument('--error-limit', type=int, default=100, help='Maximum number of errors to store per category')
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
    
    # Load or prompt for credentials
    credentials = {}
    
    # First check command line arguments
    if args.username and args.password:
        credentials["username"] = args.username
        credentials["password"] = args.password
        logger.info("Using credentials provided via command line arguments")
        
        # Save the credentials to file for future use
        generate_credentials_file(args.credentials_file, args.username, args.password)
    # Then try to load from credentials file
    elif os.path.exists(args.credentials_file):
        try:
            with open(args.credentials_file, 'r') as f:
                credentials = json.load(f)
            logger.info(f"Loaded credentials from {args.credentials_file}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error reading {args.credentials_file}: {e}")
            credentials = prompt_for_credentials()
            generate_credentials_file(args.credentials_file, credentials["username"], credentials["password"])
    # If no credentials available, prompt user
    else:
        logger.info(f"No credentials file found at {args.credentials_file}")
        credentials = prompt_for_credentials()
        generate_credentials_file(args.credentials_file, credentials["username"], credentials["password"])
    
    # Check for required credentials
    if "username" not in credentials or "password" not in credentials:
        logger.error("Username and password must be provided")
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
            
            # Configure error handling based on command-line arguments
            configure_error_handling(
                collect_details=args.collect_error_details,
                collect_tracebacks=args.collect_tracebacks,
                error_limit=args.error_limit
            )
            
            # Get service instances from service factory
            services = create_services()
            auth_service = services["auth_service"]
            navigation_service = services["navigation_service"]
            extraction_service = services["extraction_service"]
            
            # Set effective batch size (override with a large number if unlimited is set)
            if args.unlimited_batch_size:
                import sys
                effective_batch_size = sys.maxsize  # Use maximum integer value
                logger.info(f"Using unlimited batch size for homework extraction")
            else:
                effective_batch_size = args.batch_size
                logger.info(f"Using batch size of {effective_batch_size} for homework extraction")
            
            async with error_screenshot_context(page, "main", "general_errors", take_screenshot=args.enable_screenshots):
                # Login to Glasir using the authentication service
                login_success = await auth_service.login(credentials["username"], credentials["password"], page)
                if not login_success:
                    logger.error("Authentication failed. Please check your credentials.")
                    return
                
                # Initialize student_id for JavaScript navigation
                student_id = None
                
                async with error_screenshot_context(page, "js_init", "javascript_errors", take_screenshot=args.enable_screenshots):
                    # Inject the JavaScript navigation script
                    await inject_timetable_script(page)
                    
                    # Test the JavaScript integration if requested
                    if args.test_js:
                        logger.info("Testing JavaScript integration...")
                        await test_javascript_integration(page)
                        logger.info("JavaScript integration test passed!")
                        
                    # Get student ID using the navigation service
                    student_id = await navigation_service.get_student_id(page)
                    logger.info(f"Found student ID: {student_id}")
                
                # Extract dynamic teacher mapping using the extraction service
                teacher_map = await extraction_service.extract_teacher_map(page)
                
                # Process all weeks if requested
                if args.all_weeks:
                    logger.info("Processing all weeks from all academic years...")
                    
                    # Export all weeks using the dedicated function
                    export_results = await export_all_weeks(
                        page=page,
                        output_dir=args.output_dir,
                        teacher_map=teacher_map,
                        student_id=student_id,
                        batch_size=effective_batch_size
                    )
                    
                    # Log results
                    logger.info(f"Completed processing all weeks. Extracted {export_results['processed_weeks']} of {export_results['total_weeks']} weeks.")
                    if export_results['errors']:
                        logger.warning(f"Encountered {len(export_results['errors'])} errors during extraction.")
                    
                    # Skip the rest of the processing since we've already handled all weeks
                    return
                
                # Process specific weeks
                else:
                    # Extract current week's timetable data
                    logger.info("Extracting current week's timetable data...")
                    
                    # Extract timetable data using HTML parsing
                    try:
                        # Extract current week's data
                        timetable_data, week_info = await extract_timetable_data(page, teacher_map, batch_size=effective_batch_size)
                    except Exception as e:
                        logger.error(f"Error extracting current week's timetable data: {e}")
                        return
                    
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
                    
                    # If additional weeks are requested, process them
                    if args.weekforward > 0 or args.weekbackward > 0:
                        logger.info(f"Processing additional weeks: {args.weekforward} forward, {args.weekbackward} backward")
                        
                        # Get the week directions
                        directions = await get_week_directions(args)
                        
                        # Process all requested weeks
                        additional_results = await process_weeks(
                            page=page,
                            directions=directions,
                            teacher_map=teacher_map,
                            student_id=student_id,
                            output_dir=args.output_dir,
                            processed_weeks={week_info['week_num']} if week_info else set(),
                            batch_size=effective_batch_size
                        )

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