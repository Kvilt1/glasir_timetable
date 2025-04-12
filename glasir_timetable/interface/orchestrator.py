"""
Orchestration logic for Glasir Timetable.

- Coordinates authentication, teacher map extraction, timetable extraction.
- Provides high-level async functions like run_extraction(app).
- Calls into services and manages workflow based on config.
"""

import os
import time
import logging
import re
import httpx
from bs4 import BeautifulSoup
from glasir_timetable.auth.login import login as playwright_login
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.extractors.timetable_extractor import TimetableExtractor
from glasir_timetable.storage.exporter import save_timetable_export
from glasir_timetable import (
    logger, stats, update_stats, get_error_summary, configure_raw_responses
)
# Removed core.service_factory import
from glasir_timetable.auth.cookies import load_cookies_for_profile # Import correct function
# Removed import of non-existent extract_min_max_week_offsets
from glasir_timetable.auth.session_params import extract_session_params_from_html # Corrected import
# from glasir_timetable.core.student_utils import get_student_id # Removed import
from glasir_timetable.shared.constants import GLASIR_TIMETABLE_URL, DEFAULT_HEADERS # Assuming shared.constants is still valid
from glasir_timetable.storage.profile_manager import ProfileData # Import ProfileData

from playwright.async_api import async_playwright
from glasir_timetable.shared.error_utils import (
    error_screenshot_context, register_console_listener
)

async def run_extraction(app):
    args = app.args
    credentials = app.credentials
    api_only_mode = app.api_only_mode
    cached_student_info = app.cached_student_info
    profile = app.profile # Get the selected profile object from the app instance

    if not api_only_mode:
        async with async_playwright() as p:
            async with error_screenshot_context(None, "main", "general_errors", take_screenshot=args.enable_screenshots):
                browser = await p.chromium.launch(headless=args.headless)
                context = await browser.new_context()
                page = await context.new_page()
                register_console_listener(page)

                # Perform login using new auth module
                try:
                    await playwright_login(page, credentials["username"], credentials["password"])
                except Exception as e:
                    logger.error(f"Login failed: {e}")
                    return

                # Extract cookies after login
                browser_cookies = await page.context.cookies()

                # Save cookies to active profile for reuse
                # We already have the 'profile' object from the app context (line 37)
                from datetime import datetime, timedelta
                # from glasir_timetable.storage.profile_manager import ProfileManager # No longer needed here
                from glasir_timetable.auth.cookies import save_cookies_for_profile

                # profile = ProfileManager.get_instance().get_active_profile() # REMOVED - Use profile from app
                if profile:
                    cookie_data = {
                        "cookies": browser_cookies,
                        "created_at": datetime.now().isoformat(),
                        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
                    }
                    save_cookies_for_profile(profile, cookie_data)
                    logger.info(f"Saved cookies for user {profile.username} after login")
                else:
                    logger.warning("No active profile found to save cookies")
                api_cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
                app.set_api_cookies(api_cookies)

                # Student info should have been ensured during login. Retrieve it from the profile object.
                # profile_manager = ProfileManager.get_instance() # No longer needed here
                student_info = profile.load_student_info() # Load from the specific profile object
                student_id = student_info.get("id") if student_info else None

                if not student_id:
                    # This indicates a problem, as login should have failed or info extracted.
                    logger.error("CRITICAL: Student ID not found in active profile after login/validation.")
                    # Depending on strictness, could raise an error or try a last-ditch extraction.
                    # For robustness, let's log and attempt to continue, but this needs review.
                    # raise ValueError("Student ID could not be determined after login.")

                # Extract session parameters regardless of student ID status for now
                content = await page.content()
                session_params = extract_session_params_from_html(content)
                lname_value = session_params.get("lname")
                timer_value = session_params.get("timer")

                # Initialize API client and extractor
                api_client = AsyncApiClient(
                    base_url="https://tg.glasir.fo",
                    cookies=api_cookies,
                    session_params={"lname": lname_value, "timer": timer_value}
                )
                extractor = TimetableExtractor(api_client)

                # Fetch teacher map
                try:
                    teacher_map = await extractor.fetch_teacher_map(api_cookies)
                except Exception as e:
                    logger.error(f"Failed to fetch teacher map: {e}")
                    teacher_map = {}

                # Week extraction logic - Pass the profile object
                await _extract_weeks_with_extractor(
                    args, extractor, student_id, teacher_map, profile, credentials["username"]
                )

                await api_client.close()

    else:
        # API-only mode
        # Load cookies using the profile object from the app context
        profile = app.profile # Assuming app object has profile attribute from config
        cookie_data = load_cookies_for_profile(profile)
        api_cookies = {cookie['name']: cookie['value'] for cookie in cookie_data['cookies']} if cookie_data else {}
        app.set_api_cookies(api_cookies)

        student_id = cached_student_info.get("id") if cached_student_info else None
        if not student_id:
            logger.error("Student ID missing in saved info, cannot proceed with API-only mode.")
            return

        # Fetch dynamic params
        extracted_lname = None
        extracted_timer = None
        try:
            async with httpx.AsyncClient(cookies=api_cookies, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
                response = await client.get(GLASIR_TIMETABLE_URL)
                response.raise_for_status()
                html_content = response.text
                logger.debug(f"API-only mode: Fetched HTML snippet: {html_content[:1000]}...")
                session_params = extract_session_params_from_html(html_content)
                extracted_lname = session_params.get("lname")
                # Timer should be generated dynamically for API calls, not extracted from potentially stale HTML
                generated_timer = str(int(time.time() * 1000))
                logger.info(f"API-only mode: Extracted lname={extracted_lname}, Generated timer={generated_timer}")
        except Exception as e:
            logger.warning(f"API-only mode: Failed to fetch/parse initial page for dynamic params: {e.__class__.__name__}: {e}")

        # Initialize API client and extractor
        api_client = AsyncApiClient(
            base_url="https://tg.glasir.fo",
            cookies=api_cookies,
            session_params={"lname": extracted_lname, "timer": generated_timer} # Use generated timer
        )
        extractor = TimetableExtractor(api_client)

        # Fetch teacher map
        try:
            teacher_map = await extractor.fetch_teacher_map(api_cookies)
        except Exception as e:
            logger.error(f"Failed to fetch teacher map: {e}")
            teacher_map = {}

        # Week extraction logic - Pass the profile object
        await _extract_weeks_with_extractor(
            args, extractor, student_id, teacher_map, profile, credentials["username"]
        )

        await api_client.close()

async def _extract_weeks_with_extractor(args, extractor, student_id, teacher_map, profile: ProfileData, user_id): # Add profile parameter
    lname_value = extractor.api.session_params.get("lname")
    timer_value = extractor.api.session_params.get("timer")
    processed_weeks = set()

    # Load student info from the specific profile passed via app context
    # The 'app' object isn't directly available here, so we need to pass the profile object
    # Let's modify the function signature and the call site later.
    # For now, assume 'profile' is available.
    try:
        # Load student info using the passed profile object
        student_info = profile.load_student_info()
        if not student_info:
             logger.warning(f"Loaded student info for profile '{profile.username}' is empty or invalid.")
             # Decide if we should default to None or raise an error
             student_info = None # Default to None if loading fails or returns empty
    except Exception as e:
        logger.error(f"Error loading student info for profile '{profile.username}': {e}")
        student_info = None # Ensure student_info is defined even on error
    # Determine week offsets
    if args.teacherupdate and args.skip_timetable:
        logger.info("Teacher mapping updated. Skipping timetable extraction as requested.")
        return

    # TODO: Reimplement dynamic week range detection for --all-weeks
    # The original 'extract_min_max_week_offsets' function is missing after refactoring.
    # This block is commented out until the functionality is restored.
    # if args.all_weeks:
    #     logger.info("Processing range of weeks using --all-weeks (dynamically determined)...")
    #     try:
    #         # min_offset, max_offset = await extractor.get_week_range() # Hypothetical future method
    #         # logger.info(f"Using full dynamic range: {min_offset} to {max_offset}")
    #         # directions = list(range(min_offset, max_offset + 1))
    #         logger.error("--all-weeks functionality is currently disabled due to missing week range detection.")
    #         directions = [0] # Default to current week only for now
    #     except Exception as e:
    #         logger.error(f"Error during --all-weeks extraction: {e}")
    #         return
    # else
    if args.all_weeks:
        logger.info("Processing all available weeks (--all-weeks)...")
        try:
            # Fetch HTML of the base week (offset 0) to find week links
            # Pass the required lname and timer values explicitly
            base_html = await extractor.fetch_week_html(
                week_offset=0,
                student_id=student_id, # Pass student_id too for consistency
                lname_value=lname_value,
                timer_value=timer_value
            )
            if not base_html:
                logger.critical("Could not fetch base week HTML (offset 0) to determine week range for --all-weeks.")
                raise RuntimeError("Failed to determine week range for --all-weeks.")
            else:
                soup = BeautifulSoup(base_html, 'html.parser')
                week_links = soup.find_all('a', onclick=lambda x: x and 'v=' in x)
                offsets = set()
                for link in week_links:
                    match = re.search(r"v=(-?\d+)", link['onclick'])
                    if match:
                        try:
                            offsets.add(int(match.group(1)))
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse week offset from onclick: {link['onclick']}")

                if not offsets:
                    logger.critical("No week offsets found in base week HTML. Cannot determine week range for --all-weeks.")
                    raise RuntimeError("Failed to determine week range for --all-weeks.")
                else:
                    min_offset = min(offsets)
                    max_offset = max(offsets)
                    logger.info(f"Determined week range from HTML: {min_offset} to {max_offset}")
                    directions = list(range(min_offset, max_offset + 1))

        except Exception as e:
            logger.critical(f"Error determining week range for --all-weeks: {e}.")
            raise RuntimeError(f"Failed to determine week range for --all-weeks: {e}") # Explicitly fail

    # TODO: Reimplement dynamic week range detection for --forward
    # The original 'extract_min_max_week_offsets' function is missing after refactoring.
    # This block is commented out until the functionality is restored.
    # elif args.forward:
    #     logger.info("Processing only current and future weeks (positive offsets) dynamically...")
    #     try:
    #         # min_offset, max_offset = await extractor.get_week_range() # Hypothetical future method
    #         # logger.info(f"Full dynamic range: {min_offset} to {max_offset}")
    #         # directions = [offset for offset in range(min_offset, max_offset + 1) if offset >= 0]
    #         logger.error("--forward functionality is currently disabled due to missing week range detection.")
    #         directions = [0] # Default to current week only for now
    #     except Exception as e:
    #         logger.error(f"Error during --forward extraction: {e}")
    #         return
    elif args.forward:
        logger.warning("--forward functionality is currently disabled. Processing current week only.")
        directions = [0] # Default to current week

    elif args.weekforward > 0 or args.weekbackward > 0:
        logger.info(f"Processing specified range: {args.weekbackward} weeks backward, {args.weekforward} weeks forward, always including current week (0)")
        directions = set()
        directions.add(0)
        for i in range(1, args.weekforward + 1):
            directions.add(i)
        for i in range(1, args.weekbackward + 1):
            directions.add(-i)
        directions = sorted(directions)

    else:
        logger.info("No week range specified, processing current week only")
        directions = [0]

    # Process each week offset
    for offset in directions:
        try:
            logger.info(f"Fetching timetable for week offset {offset}")
            timetable_data = await extractor.fetch_timetable_with_homework(
                offset,
                student_id=student_id,
                lname_value=lname_value,
                timer_value=timer_value,
                student_info=student_info
            )
            # Use the profile's weeks directory as the output directory
            output_dir_path = profile.weeks_dir
            save_path = save_timetable_export(
                timetable_data,
                output_dir=str(output_dir_path), # Pass the correct output dir
                user_id=user_id
            )
            logger.info(f"Saved week {offset} data to {save_path}")
        except Exception as e:
            logger.error(f"Failed to fetch/save week {offset}: {e}")