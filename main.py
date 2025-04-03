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
from glasir_timetable.cookie_auth import (
    check_and_refresh_cookies,
    set_cookies_in_playwright_context,
    create_requests_session_with_cookies,
    test_cookies_with_requests,
    load_cookies,
    estimate_cookie_expiration
)
from glasir_timetable.extractors import (
    extract_teacher_map, 
    extract_timetable_data
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
    get_week_directions,
    navigate_and_extract_api,
    extract_min_max_week_offsets
)

from glasir_timetable.models import TimetableData
from glasir_timetable.utils.model_adapters import timetable_data_to_dict

# Import service factory for dependency injection
from glasir_timetable.service_factory import set_config, create_services

from glasir_timetable.api_client import (
    fetch_homework_for_lessons
)

from glasir_timetable.session import AuthSessionManager
from glasir_timetable.utils.param_utils import parse_dynamic_params

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
    parser.add_argument('--headless', action='store_false', dest='headless', default=True, help='Run in non-headless mode (default: headless=True)')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                        default='INFO', help='Set the logging level')
    parser.add_argument('--log-file', type=str, help='Log to a file instead of console')
    parser.add_argument('--collect-error-details', action='store_true', help='Collect detailed error information')
    parser.add_argument('--collect-tracebacks', action='store_true', help='Collect tracebacks for errors')
    parser.add_argument('--enable-screenshots', action='store_true', help='Enable screenshots on errors')
    parser.add_argument('--error-limit', type=int, default=100, help='Maximum number of errors to store per category')
    parser.add_argument('--use-cookies', action='store_true', default=True, help='Use cookie-based authentication when possible')
    parser.add_argument('--cookie-path', type=str, default='cookies.json', help='Path to save/load cookies')
    parser.add_argument('--no-cookie-refresh', action='store_false', dest='refresh_cookies', default=True, 
                      help='Do not refresh cookies even if they are expired')
    parser.add_argument('--teacherupdate', action='store_true', help='Update the teacher mapping cache at the start of the script')
    parser.add_argument('--skip-timetable', action='store_true', help='Skip timetable extraction, useful when only updating teachers')
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
    
    # Check cookie expiration at startup
    if args.use_cookies:
        cookie_data = load_cookies(args.cookie_path)
        if cookie_data:
            expiration_msg = estimate_cookie_expiration(cookie_data)
            logger.info(f"Cookie status: {expiration_msg}")
    
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
            "browser": lambda browser: browser.close()
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
            
            # Get service instances from service factory with cookie configuration
            set_config("use_cookie_auth", args.use_cookies)
            set_config("cookie_file", args.cookie_path)
            
            # Create all services
            services = create_services()
            
            # Get specific services
            auth_service = services["auth"]
            navigation_service = services["navigation"]
            extraction_service = services["extraction"] 
            api_client = services.get("api_client")
            
            # Log what services we're using
            logger.info(f"Using cookie authentication: {args.use_cookies}")
            
            async with error_screenshot_context(page, "main", "general_errors", take_screenshot=args.enable_screenshots):
                # Let the auth_service handle authentication (it will use cookies if configured)
                login_success = await auth_service.login(
                    credentials["username"], 
                    credentials["password"], 
                    page
                )
                
                if not login_success:
                    logger.error("Authentication failed. Please check your credentials.")
                    return
                
                # Get API cookies if needed for older API methods not using the ApiClient
                api_cookies = {}
                if hasattr(auth_service, "get_requests_session") and callable(getattr(auth_service, "get_requests_session")):
                    # We have a requests session with cookies
                    logger.info("Using cookies from cookie authentication service")
                    session = auth_service.get_requests_session()
                    if session:
                        api_cookies = dict(session.cookies)
                else:
                    # Fall back to extracting cookies from the browser
                    browser_cookies = await page.context.cookies()
                    api_cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
                
                logger.info(f"Using {len(api_cookies)} cookies for API requests")
                
                # Get basic info about the student and fetch key lname parameter
                student_id = await navigation_service.get_student_id(page)
                content = await page.content()
                lname_value, timer_value = parse_dynamic_params(content)
                logger.info(f"Student ID: {student_id}")
                logger.info(f"lname value: {lname_value}")
                logger.info(f"timer value: {timer_value}")
                
                # Extract dynamic teacher mapping using the extraction service
                teacher_map = await extraction_service.extract_teacher_map(
                    page, 
                    force_update=args.teacherupdate,
                    cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value
                )
                
                # If we're only updating the teacher cache, we can exit now
                if args.teacherupdate and args.skip_timetable:
                    logger.info("Teacher mapping updated. Skipping timetable extraction as requested.")
                    return
                
                # Process all weeks if requested
                if args.all_weeks:
                    logger.info("Processing range of weeks using --all-weeks (dynamically determined)...")
                    
                    try:
                        # Dynamically extract the available week range with API support
                        min_offset, max_offset = await extract_min_max_week_offsets(
                            page=page,
                            api_cookies=api_cookies,
                            student_id=student_id,
                            lname_value=lname_value,
                            timer_value=timer_value
                        )
                        
                        # The extracted min_offset is negative (like -65) and max_offset is positive (like 15)
                        # We need to set weekbackward to abs(min_offset) and weekforward to max_offset
                        if args.weekforward == 0:  # Only override if not explicitly set
                            args.weekforward = max_offset
                        if args.weekbackward == 0:  # Only override if not explicitly set
                            args.weekbackward = abs(min_offset)
                        
                        logger.info(f"Using dynamically determined range: {args.weekforward} weeks forward, {args.weekbackward} weeks backward")
                    except ValueError as e:
                        logger.error(f"{e} Cannot continue with --all-weeks option.")
                        return  # Exit the script
                
                # Process specific weeks
                if args.weekforward > 0 or args.weekbackward > 0:
                    # Extract current week's timetable data
                    logger.info("Extracting current week's timetable data...")
                    
                    # Extract current week's data with API approach
                    logger.info("Using API-based implementation for extraction")
                    
                    # Extract current week's data with API approach
                    timetable_data, week_info, _ = await navigate_and_extract_api(
                        page, 0, teacher_map, api_cookies,
                        lname_value=lname_value,
                        timer_value=timer_value
                    )
                    
                    # Check if we successfully retrieved the week info
                    if not week_info:
                        logger.error("Failed to retrieve week information. The page may need to be refreshed.")
                        # Try to refresh the page and try again
                        logger.info("Attempting to reload the page and retry...")
                        await page.reload(wait_until="networkidle")
                        await page.wait_for_timeout(2000)  # Wait an extra 2 seconds for stability
                        
                        # Try extraction once more
                        timetable_data, week_info, _ = await navigate_and_extract_api(
                            page, 0, teacher_map, api_cookies,
                            lname_value=lname_value,
                            timer_value=timer_value
                        )
                        
                        if not week_info:
                            logger.error("Still failed to retrieve week information after reload. Exiting.")
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
                    logger.info(f"Processing additional weeks: {args.weekforward} forward, {args.weekbackward} backward")
                    
                    # Get the week directions
                    directions = await get_week_directions(args)
                    
                    # Process all requested weeks using API-based approach
                    additional_results = await process_weeks(
                        page=page,
                        directions=directions,
                        teacher_map=teacher_map,
                        student_id=student_id,
                        output_dir=args.output_dir,
                        api_cookies=api_cookies,
                        processed_weeks={week_info['week_num']} if week_info else set(),
                        lname_value=lname_value,
                        timer_value=timer_value
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

            # Check and report cookie expiration at the end
            if args.use_cookies:
                if hasattr(auth_service, "cookie_data") and auth_service.cookie_data:
                    end_expiration_msg = estimate_cookie_expiration(auth_service.cookie_data)
                    logger.info(f"Final cookie status: {end_expiration_msg}")
                else:
                    # Try to load cookies from file again
                    end_cookie_data = load_cookies(args.cookie_path)
                    if end_cookie_data:
                        end_expiration_msg = estimate_cookie_expiration(end_cookie_data)
                        logger.info(f"Final cookie status: {end_expiration_msg}")

    # Execution completed
    update_stats("end_time", time.time(), increment=False)
    elapsed_time = stats.get("end_time", 0) - stats.get("start_time", 0)
    logger.info(f"Execution completed in {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())