
"""
Configuration management for Glasir Timetable.

- Loads and merges CLI args, environment variables, and defaults.
- Validates configuration.
- Prepares config dictionary or object for the application.
"""

# Unused import 'constants' removed based on Vulture report and analysis.
from glasir_timetable import configure_raw_responses
from glasir_timetable.auth.cookies import is_cookies_valid # Removed estimate_cookie_expiration
from glasir_timetable import logger
from glasir_timetable.storage.profile_manager import ProfileManager, ProfileData # Import ProfileData too
from glasir_timetable.interface.cli import prompt_for_credentials
# (No direct import for is_full_auth_data_valid needed; logic uses profile methods)
async def load_config(args, selected_username, profile_created: bool = False): # noqa: F811 - Used externally (e.g., in main.py)
    profile_manager = ProfileManager.get_instance()
    """
    Prepare and validate configuration based on CLI args and selected username.
    Loads the profile, handles credentials, checks auth status, and returns a config dict.

    Args:
        args: Parsed command-line arguments.
        selected_username: The username of the profile to load/use.
        profile_created: Boolean flag indicating if the profile was just created in this run.
    """
    # --- 1. Load Profile ---
    try:
        profile: ProfileData = profile_manager.load_profile(selected_username)
        logger.info(f"Loaded profile for '{selected_username}' from {profile.base_dir}")
    except FileNotFoundError:
        logger.error(f"Profile '{selected_username}' not found. Please ensure the profile exists.")
        # Optionally, prompt to create one or exit
        # For now, let's exit as config is crucial
        # TODO: Consider prompting for creation via ProfileManager.create_profile
        exit(f"Error: Profile '{selected_username}' does not exist.")
    except Exception as e:
        logger.error(f"Failed to load profile '{selected_username}': {e}")
        exit(f"Error loading profile: {e}")

    # --- 1.5 Load Concurrency Config ---
    concurrency_config = await profile.load_concurrency_config()
    logger.info(f"Loaded concurrency config: {concurrency_config}")

    # --- 2. Update Args/Defaults with Profile Paths ---
    # Args might still be used elsewhere, update them if necessary,
    # but prefer using profile paths directly from the config dict later.
    # args.cookie_path assignment removed; value is unused as config dict uses profile.cookies_path directly.
    args.output_dir = str(profile.weeks_dir)    # Use profile's weeks_dir for output

    # Ensure the output directory (weeks dir) exists
    profile.weeks_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured output directory exists: {profile.weeks_dir}")

    # Remove overrides of constants - paths should be accessed via profile object
    # constants.STUDENT_ID_FILE = str(profile.student_info_path) # No longer needed
    # import glasir_timetable.auth.cookies as cookie_auth_module # Import still needed for is_cookies_valid
    # cookie_auth_module.DEFAULT_COOKIE_PATH = str(profile.cookies_path) # No longer needed

    # Removed service_factory import and config calls, assuming handled differently now

    # (Output directory creation moved above)
    # Configure raw response saving
    configure_raw_responses(
        args.save_raw_responses,
        args.raw_responses_dir,
        save_request_details=args.save_raw_responses
    )

    # --- 3. Handle Credentials ---
    # Profile loading already handled above
    credentials = await profile.load_credentials()
    # Only prompt for credentials if the profile wasn't *just* created AND they are missing/invalid
    if not profile_created and (not credentials or "username" not in credentials or "password" not in credentials):
        logger.warning("Credentials file missing or incomplete. Prompting user.")
        credentials = prompt_for_credentials(selected_username)
        await profile.save_credentials(credentials)
    elif not credentials:
        # This case should ideally not happen if profile_created is True,
        # as cli.py should have saved them. Log a warning if it does.
        logger.error("Profile was just created, but credentials could not be loaded. This indicates an issue.")
        # Attempt to prompt anyway as a fallback, though this might indicate a deeper problem.
        credentials = prompt_for_credentials(selected_username)
        await profile.save_credentials(credentials)
    # --- 4. Determine API-only Mode (Automatically based on auth data) ---
    api_only_mode = False
    cached_student_info = None
    auth_valid = False
    try:
        cookie_data = await profile.load_cookies()
        student_info = await profile.load_student_info()
        cookies_are_valid = is_cookies_valid(cookie_data)
        student_info_is_valid = student_info is not None and "id" in student_info

        if cookies_are_valid and student_info_is_valid:
            auth_valid = True
            cached_student_info = student_info # Store loaded info
            api_only_mode = True
            logger.info("Valid cookies and student info found. Automatically enabling API-only mode (skipping Playwright).")
        elif not cookies_are_valid:
             logger.info("Cookies missing or expired.")
        elif not student_info_is_valid:
             logger.info("Student info missing or invalid.")

        if not auth_valid:
             logger.info("Full auth data not available or valid. API-only mode disabled. Playwright login may be required.")

    except Exception as e:
        logger.error(f"Error checking auth data validity: {e}")
        # Decide how to handle error, e.g., default to non-API mode
        logger.warning("Proceeding with API-only mode disabled due to error checking auth data.")

    # --- 5. Prepare Config Dict ---
    config = {
        "args": args, # Pass original args for reference if needed elsewhere
        "username": selected_username,
        "profile": profile, # Pass the loaded ProfileData object
        "account_path": str(profile.base_dir), # Use profile path
        "cookie_path": str(profile.cookies_path), # Use profile path
        "output_dir": str(profile.weeks_dir), # Use profile path (weeks dir)
        "student_id_path": str(profile.student_info_path), # Use profile path
        "credentials": credentials,
        "api_only_mode": api_only_mode,
        "cached_student_info": cached_student_info,
        "concurrency_config": concurrency_config, # Add loaded concurrency settings
        "force_max_concurrency": args.force_max_concurrency, # Add the new flag
        # Add other relevant config derived from args or profile as needed
    }

    return config
