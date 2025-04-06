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
from glasir_timetable import logger, setup_logging, stats, update_stats, error_collection, get_error_summary, clear_errors, add_error, configure_raw_responses
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

from glasir_timetable.cookie_auth import is_cookies_valid, load_cookies
from glasir_timetable.student_utils import load_student_info

def is_full_auth_data_valid(username, cookie_path):
    """
    Check if both cookies and student ID are valid for the given user.
    Returns (is_valid: bool, student_info_dict: dict or None)
    """
    try:
        cookie_data = load_cookies(cookie_path)
        cookies_ok = is_cookies_valid(cookie_data)
    except Exception:
        cookies_ok = False

    # Check student-id.json file directly
    try:
        student_id_path = os.path.join("glasir_timetable", "accounts", username, "student-id.json")
        info = None
        if os.path.exists(student_id_path):
            import json
            with open(student_id_path, "r") as f:
                info = json.load(f)
        id_ok = info is not None and "id" in info and info["id"]
    except Exception:
        info = None
        id_ok = False

    logger.info(f"[DEBUG] is_full_auth_data_valid: cookies_ok={cookies_ok}")
    logger.info(f"[DEBUG] is_full_auth_data_valid: student_id_info={info}")
    logger.info(f"[DEBUG] is_full_auth_data_valid: id_ok={id_ok}")

    return (cookies_ok and id_ok), info

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
    auth_service = None  # Initialize to avoid UnboundLocalError
    """
    Main entry point for the Glasir Timetable application.
    """
    # Initialize statistics
    from glasir_timetable import stats, update_stats, clear_errors
    clear_errors()  # Clear any errors from previous runs
    update_stats("start_time", time.time(), increment=False)

    print('DEBUG: sys.argv before parsing:', sys.argv)
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Extract timetable data from Glasir')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--all-weeks', action='store_true', help='Extract all available weeks from all academic years')
    parser.add_argument('--forward', action='store_true', help='Extract only current and future weeks (positive offsets) dynamically')
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
    parser.add_argument('--save-raw-responses', action='store_true', help='Save raw API responses before parsing')
    parser.add_argument('--raw-responses-dir', type=str, help='Directory to save raw API responses (default: glasir_timetable/raw_responses/)')
    args = parser.parse_args()
    
    # If no log file provided, generate timestamped log file inside glasir_timetable/logs/
    if not args.log_file:
        log_dir = os.path.join("glasir_timetable", "logs")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        args.log_file = os.path.join(log_dir, f"glasir_timetable_{timestamp}.log")

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

    # ---- ACCOUNT SELECTION ----
    from glasir_timetable import account_manager, constants
    import glasir_timetable.student_utils as student_utils

    selected_username = account_manager.interactive_account_selection()
    # Force account path inside the glasir_timetable package directory
    account_path = os.path.join("glasir_timetable", "accounts", selected_username)

    # Override cookie path to be per-account
    args.cookie_path = os.path.join(account_path, "cookies.json")

    # Override student ID file to be per-account (legacy code)
    constants.STUDENT_ID_FILE = os.path.join(account_path, "student-id.json")
    
    # Set student_utils to use per-account student-id.json via helper
    student_utils.set_student_id_path_for_user(selected_username)
    
    # Override output directory to be per-account weeks folder
    args.output_dir = os.path.join(account_path, "weeks")
    
    # Also override the default cookie path in cookie_auth module
    import glasir_timetable.cookie_auth as cookie_auth_module
    cookie_auth_module.DEFAULT_COOKIE_PATH = args.cookie_path
    
    # Update service factory config to use per-account cookie file and storage dir
    from glasir_timetable.service_factory import set_config
    set_config("cookie_file", args.cookie_path)
    set_config("storage_dir", args.output_dir)

    # Load credentials for this account
    credentials = account_manager.load_account_data(selected_username, "credentials")
    if not credentials or "username" not in credentials or "password" not in credentials:
        print(f"No credentials found for account '{selected_username}'. Please enter them now.")
        uname = input("Username (without @glasir.fo): ").strip()
        import getpass
        pwd = getpass.getpass("Password: ")
        credentials = {"username": uname, "password": pwd}
        account_manager.save_account_data(selected_username, "credentials", credentials)

    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir, exist_ok=True)
        logger.debug(f"Created output directory: {args.output_dir}")

    # Configure raw response saving based on command-line arguments
    configure_raw_responses(
        args.save_raw_responses,
        args.raw_responses_dir,
        save_request_details=args.save_raw_responses  # Enable saving request details by default when saving raw responses
    )
    
    # Check cookie expiration at startup
    if args.use_cookies:
        cookie_data = load_cookies(args.cookie_path)
        if cookie_data:
            expiration_msg = estimate_cookie_expiration(cookie_data)
            logger.info(f"Cookie status: {expiration_msg}")
    
    # Determine if we can skip Playwright entirely
    api_only_mode = False
    auth_valid, cached_student_info = is_full_auth_data_valid(selected_username, args.cookie_path)
    if auth_valid:
        api_only_mode = True
        logger.info("All auth data valid, running in API-only mode, skipping Playwright.")
    else:
        logger.info("Auth data missing or expired, Playwright login required.")

    if not api_only_mode:
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
                    processed_weeks = set()
                    # Determine week offsets to process

            logger.info("DEBUG: Extraction call POINT A")
            # Run API-only extraction for all weeks
            # (Removed initial extraction to avoid double work)

            logger.info(f"Finished processing {len(processed_weeks)} weeks")
            
            # If we're only updating the teacher cache, we can exit now
            if args.teacherupdate and args.skip_timetable:
                logger.info("Teacher mapping updated. Skipping timetable extraction as requested.")
                return
            
            # Process all weeks if requested
            logger.info("DEBUG: Extraction call POINT B - before dynamic range extraction")
            
            if args.all_weeks:
                logger.info("Processing range of weeks using --all-weeks (dynamically determined)...")
                try:
                    min_offset, max_offset = await extract_min_max_week_offsets(
                        api_cookies=api_cookies,
                        student_id=student_id,
                        lname_value=lname_value,
                        timer_value=timer_value
                    )
                    logger.info(f"Using full dynamic range: {min_offset} to {max_offset}")
                    directions = list(range(min_offset, max_offset + 1))
                    processed_weeks = await process_weeks(
                        directions=directions,
                        teacher_map=teacher_map,
                        student_id=student_id,
                        output_dir=args.output_dir,
                        api_cookies=api_cookies,
                        lname_value=lname_value,
                        timer_value=timer_value,
                        dynamic_range=True
                    )
                    logger.info(f"Finished processing {len(processed_weeks)} weeks")
                except Exception as e:
                    logger.error(f"Error during --all-weeks extraction: {e}")
                    return

            elif args.forward:
                logger.info("Processing only current and future weeks (positive offsets) dynamically...")
                try:
                    min_offset, max_offset = await extract_min_max_week_offsets(
                        api_cookies=api_cookies,
                        student_id=student_id,
                        lname_value=lname_value,
                        timer_value=timer_value
                    )
                    logger.info(f"Full dynamic range: {min_offset} to {max_offset}")
                    directions = [offset for offset in range(min_offset, max_offset + 1) if offset >= 0]
                    logger.info(f"Filtered to {len(directions)} current and future weeks: {directions}")
                    processed_weeks = await process_weeks(
                        directions=directions,
                        teacher_map=teacher_map,
                        student_id=student_id,
                        output_dir=args.output_dir,
                        api_cookies=api_cookies,
                        lname_value=lname_value,
                        timer_value=timer_value,
                        dynamic_range=False
                    )
                    logger.info(f"Finished processing {len(processed_weeks)} weeks")
                except Exception as e:
                    logger.error(f"Error during --forward extraction: {e}")
                    return

            elif args.weekforward > 0 or args.weekbackward > 0:
                logger.info(f"Processing specified range: {args.weekbackward} weeks backward, {args.weekforward} weeks forward, always including current week (0)")
                directions = set()
                directions.add(0)
                for i in range(1, args.weekforward + 1):
                    directions.add(i)
                for i in range(1, args.weekbackward + 1):
                    directions.add(-i)
                directions = sorted(directions)
                logger.info(f"Week offsets to process: {directions}")
                processed_weeks = await process_weeks(
                    directions=directions,
                    teacher_map=teacher_map,
                    student_id=student_id,
                    output_dir=args.output_dir,
                    api_cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value,
                    dynamic_range=False
                )
                logger.info(f"Finished processing {len(processed_weeks)} weeks")

            else:
                logger.info("No week range specified, processing current week only")
                directions = [0]
                processed_weeks = await process_weeks(
                    directions=directions,
                    teacher_map=teacher_map,
                    student_id=student_id,
                    output_dir=args.output_dir,
                    api_cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value,
                    dynamic_range=False
                )
                logger.info(f"Finished processing {len(processed_weeks)} weeks")
    else:
        # API-only mode branch
        set_config("use_cookie_auth", True)
        set_config("cookie_file", args.cookie_path)
        services = create_services()
        extraction_service = services["extraction"]
        api_client = services.get("api_client")

        # Load cookies dict for API calls
        cookie_data = load_cookies(args.cookie_path)
        api_cookies = {cookie['name']: cookie['value'] for cookie in cookie_data['cookies']} if cookie_data else {}

        # Load student info
        student_id = cached_student_info.get("id") if cached_student_info else None
        if not student_id:
            logger.error("Student ID missing in saved info, cannot proceed with API-only mode.")
            return

        # Extract teacher map via API
        try:
            teacher_map = await api_client.fetch_teacher_map(student_id, update_cache=args.teacherupdate)
        except Exception as e:
            logger.error(f"Failed to fetch teacher map via API: {e}")
            teacher_map = {}

        # Extract min/max week offsets dynamically if requested
        processed_weeks = set()
        if args.all_weeks:
            logger.info("Processing range of weeks using --all-weeks (dynamically determined)...")
            try:
                min_offset, max_offset = await extract_min_max_week_offsets(
                    api_cookies=api_cookies,
                    student_id=student_id,
                    lname_value=None,
                    timer_value=None
                )
                logger.info(f"Using full dynamic range: {min_offset} to {max_offset}")
                directions = list(range(min_offset, max_offset + 1))
                processed_weeks = await process_weeks(
                    directions=directions,
                    teacher_map=teacher_map,
                    student_id=student_id,
                    output_dir=args.output_dir,
                    api_cookies=api_cookies,
                    lname_value=None,
                    timer_value=None,
                    dynamic_range=True
                )
                logger.info(f"Finished processing {len(processed_weeks)} weeks")
            except Exception as e:
                logger.error(f"Error during --all-weeks extraction: {e}")
                return

        elif args.forward:
            logger.info("Processing only current and future weeks (positive offsets) dynamically...")
            try:
                min_offset, max_offset = await extract_min_max_week_offsets(
                    api_cookies=api_cookies,
                    student_id=student_id,
                    lname_value=None,
                    timer_value=None
                )
                logger.info(f"Full dynamic range: {min_offset} to {max_offset}")
                directions = [offset for offset in range(min_offset, max_offset + 1) if offset >= 0]
                logger.info(f"Filtered to {len(directions)} current and future weeks: {directions}")
                processed_weeks = await process_weeks(
                    directions=directions,
                    teacher_map=teacher_map,
                    student_id=student_id,
                    output_dir=args.output_dir,
                    api_cookies=api_cookies,
                    lname_value=None,
                    timer_value=None,
                    dynamic_range=False
                )
                logger.info(f"Finished processing {len(processed_weeks)} weeks")
            except Exception as e:
                logger.error(f"Error during --forward extraction: {e}")
                return

        elif args.weekforward > 0 or args.weekbackward > 0:
            logger.info(f"Processing specified range: {args.weekbackward} weeks backward, {args.weekforward} weeks forward, always including current week (0)")
            directions = set()
            directions.add(0)
            for i in range(1, args.weekforward + 1):
                directions.add(i)
            for i in range(1, args.weekbackward + 1):
                directions.add(-i)
            directions = sorted(directions)
            logger.info(f"Week offsets to process: {directions}")
            processed_weeks = await process_weeks(
                directions=directions,
                teacher_map=teacher_map,
                student_id=student_id,
                output_dir=args.output_dir,
                api_cookies=api_cookies,
                lname_value=None,
                timer_value=None,
                dynamic_range=False
            )
            logger.info(f"Finished processing {len(processed_weeks)} weeks")

        else:
            logger.info("No week range specified, processing current week only")
            directions = [0]
            processed_weeks = await process_weeks(
                directions=directions,
                teacher_map=teacher_map,
                student_id=student_id,
                output_dir=args.output_dir,
                api_cookies=api_cookies,
                lname_value=None,
                timer_value=None,
                dynamic_range=False
            )
            logger.info(f"Finished processing {len(processed_weeks)} weeks")

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
        if auth_service and hasattr(auth_service, "cookie_data") and auth_service.cookie_data:
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
start_time = stats.get("start_time")
end_time = stats.get("end_time")
if start_time is None or end_time is None:
    elapsed_time = 0.0
else:
    elapsed_time = end_time - start_time
logger.info(f"Execution completed in {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    import argparse
    import sys
    import asyncio
    import cProfile
    import pstats
    import io
    from pathlib import Path

    # Existing sys.path setup
    parent_dir = Path(__file__).resolve().parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="store_true", help="Enable profiling")
    args, unknown = parser.parse_known_args()

    sys.argv = [sys.argv[0]] + unknown  # Pass remaining args to main()

    if args.profile:
        profile_output = "profile_output.prof"
        pr = cProfile.Profile()
        pr.enable()

        try:
            asyncio.run(main())
        finally:
            pr.disable()
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)
            print("Profiling results (top 30 by cumulative time):")
            print(s.getvalue())
            ps.dump_stats(profile_output)
            print(f"Full profile data saved to {profile_output}")
    else:
        asyncio.run(main())