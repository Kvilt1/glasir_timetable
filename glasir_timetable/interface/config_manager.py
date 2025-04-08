"""
Configuration management for Glasir Timetable.

- Loads and merges CLI args, environment variables, and defaults.
- Validates configuration.
- Prepares config dictionary or object for the application.
"""

import os
import logging
from datetime import datetime
from glasir_timetable.shared import constants
from glasir_timetable import configure_raw_responses
from glasir_timetable.core.cookie_auth import load_cookies, estimate_cookie_expiration
from glasir_timetable import logger
from glasir_timetable.accounts.manager import AccountManager
from glasir_timetable.interface.cli import prompt_for_credentials
from glasir_timetable.shared.auth_utils import is_full_auth_data_valid

def load_config(args, selected_username):
    account_manager = AccountManager()
    """
    Prepare and validate configuration based on CLI args and username.
    Returns a config dict with derived paths and flags.
    """
    # Compute account-specific paths
    account_path = os.path.join("glasir_timetable", "accounts", selected_username)
    cookie_path = os.path.join(account_path, "cookies.json")
    output_dir = os.path.join(account_path, "weeks")
    student_id_path = os.path.join(account_path, "student-id.json")

    # Override args with account-specific paths
    args.cookie_path = cookie_path
    args.output_dir = output_dir

    # Override constants and module defaults
    constants.STUDENT_ID_FILE = student_id_path
    import glasir_timetable.core.student_utils as student_utils
    student_utils.set_student_id_path_for_user(selected_username)
    import glasir_timetable.core.cookie_auth as cookie_auth_module
    cookie_auth_module.DEFAULT_COOKIE_PATH = cookie_path

    # Update service factory config
    from glasir_timetable.core.service_factory import set_config as set_service_config
    set_service_config("cookie_file", cookie_path)
    set_service_config("storage_dir", output_dir)

    # Create output directory if needed
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        logger.debug(f"Created output directory: {output_dir}")

    # Configure raw response saving
    configure_raw_responses(
        args.save_raw_responses,
        args.raw_responses_dir,
        save_request_details=args.save_raw_responses
    )

    # Check cookie expiration
    if args.use_cookies:
        cookie_data = load_cookies(cookie_path)
        if cookie_data:
            expiration_msg = estimate_cookie_expiration(cookie_data)
            logger.info(f"Cookie status: {expiration_msg}")

    # Determine API-only mode
    api_only_mode = False
    auth_valid, cached_student_info = is_full_auth_data_valid(selected_username, cookie_path)
    if auth_valid:
        api_only_mode = True
        logger.info("All auth data valid, running in API-only mode, skipping Playwright.")
    else:
        logger.info("Auth data missing or expired, Playwright login required.")

    # Load credentials or prompt if missing
    profile = account_manager.load_profile(selected_username)
    credentials = profile.load_credentials()
    if not credentials or "username" not in credentials or "password" not in credentials:
        credentials = prompt_for_credentials(selected_username)
        profile.save_credentials(credentials)

    # Prepare config dict
    config = {
        "args": args,
        "username": selected_username,
        "account_path": account_path,
        "cookie_path": cookie_path,
        "output_dir": output_dir,
        "student_id_path": student_id_path,
        "credentials": credentials,
        "api_only_mode": api_only_mode,
        "cached_student_info": cached_student_info,
    }

    return config