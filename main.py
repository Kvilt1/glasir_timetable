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
from glasir_timetable.core.auth import login_to_glasir
from glasir_timetable.core.cookie_auth import (
    check_and_refresh_cookies,
    set_cookies_in_playwright_context,
    create_requests_session_with_cookies,
    test_cookies_with_requests,
    load_cookies,
    estimate_cookie_expiration
)
from glasir_timetable.data import (
    extract_teacher_map, 
    extract_timetable_data
)

# Import utility functions
from glasir_timetable.shared import (
    normalize_dates,
    normalize_week_number,
    generate_week_filename,
    convert_keys_to_camel_case,
    save_json_data
)

# Import error handling utilities
from glasir_timetable.shared.error_utils import (
    error_screenshot_context,
    register_console_listener,
    handle_errors,
    resource_cleanup_context,
    async_resource_cleanup_context,
    configure_error_handling
)

# Import navigation utilities
from glasir_timetable.core.navigation import (
    process_weeks,
    get_week_directions,
    navigate_and_extract_api,
    extract_min_max_week_offsets
)

from glasir_timetable.core.models import TimetableData
from glasir_timetable.shared.model_adapters import timetable_data_to_dict

# Import service factory for dependency injection
from glasir_timetable.core.service_factory import set_config, create_services

from glasir_timetable.core.api_client import (
    fetch_homework_for_lessons
)

from glasir_timetable.core.session import AuthSessionManager
from glasir_timetable.shared.param_utils import parse_dynamic_params

from glasir_timetable.core.cookie_auth import is_cookies_valid, load_cookies
from glasir_timetable.core.student_utils import load_student_info

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

    from glasir_timetable.interface.cli import parse_args
    args = parse_args()
    
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
    from glasir_timetable.accounts import manager as account_manager
    from glasir_timetable.shared import constants
    from glasir_timetable.interface.cli import select_account
    selected_username = select_account()

    from glasir_timetable.interface.config_manager import load_config
    config = load_config(args, selected_username)

    args = config["args"]
    credentials = config["credentials"]
    api_only_mode = config["api_only_mode"]
    cached_student_info = config["cached_student_info"]

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
    from glasir_timetable.interface.application import Application
    app = Application(config)

    from glasir_timetable.interface.orchestrator import run_extraction
    await run_extraction(app)

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