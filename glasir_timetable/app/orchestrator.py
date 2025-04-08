"""
Orchestration logic for Glasir Timetable.

- Coordinates authentication, teacher map extraction, timetable extraction.
- Provides high-level async functions like run_extraction(app).
- Calls into services and manages workflow based on config.
"""

import os
import time
import logging
from glasir_timetable import (
    logger, stats, update_stats, get_error_summary, configure_raw_responses
)
from glasir_timetable.service_factory import create_services, set_config, CookieAuthenticationService
from glasir_timetable.cookie_auth import load_cookies, estimate_cookie_expiration, is_cookies_valid, check_and_refresh_cookies
from glasir_timetable.navigation import process_weeks, extract_min_max_week_offsets
from glasir_timetable.utils.param_utils import parse_dynamic_params
from glasir_timetable.student_utils import get_student_id

from playwright.async_api import async_playwright
from glasir_timetable.utils.error_utils import (
    error_screenshot_context, register_console_listener
)

async def run_extraction(app):
    args = app.args
    credentials = app.credentials
    api_only_mode = app.api_only_mode
    cached_student_info = app.cached_student_info

    if not api_only_mode:
        async with async_playwright() as p:
            resources = {"browser": None, "context": None, "page": None}
            cleanup_funcs = {"browser": lambda browser: browser.close()}

            async with error_screenshot_context(None, "main", "general_errors", take_screenshot=args.enable_screenshots):
                browser = await p.chromium.launch(headless=args.headless)
                context = await browser.new_context()
                page = await context.new_page()
                register_console_listener(page)

                # Create services
                set_config("use_cookie_auth", args.use_cookies)
                set_config("cookie_file", args.cookie_path)
                services = create_services()
                app.set_services(services)

                auth_service = services["auth"]
                extraction_service = services["extraction"]
                api_client = services.get("api_client")

                # Authenticate
                if isinstance(auth_service, CookieAuthenticationService):
                    try:
                        # Attempt to load and refresh cookies if needed
                        cookie_data = await check_and_refresh_cookies(
                            page,
                            credentials["username"],
                            credentials["password"],
                            args.cookie_path
                        )
                    except Exception as e:
                        logger.error(f"Failed to refresh cookies via Playwright: {e}")
                        return
                else:
                    login_success = await auth_service.login(
                        credentials["username"],
                        credentials["password"],
                        page
                    )
                    if not login_success:
                        logger.error("Authentication failed. Please check your credentials.")
                        return

                # Get API cookies
                api_cookies = {}
                if hasattr(auth_service, "get_requests_session") and callable(getattr(auth_service, "get_requests_session")):
                    session = auth_service.get_requests_session()
                    if session:
                        api_cookies = dict(session.cookies)
                else:
                    browser_cookies = await page.context.cookies()
                    api_cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
                app.set_api_cookies(api_cookies)

                # Extract student info and params
                student_id = await get_student_id(page)
                content = await page.content()
                lname_value, timer_value = parse_dynamic_params(content)

                # Extract teacher map
                teacher_map = await extraction_service.extract_teacher_map(
                    page,
                    force_update=args.teacherupdate,
                    cookies=api_cookies,
                    lname_value=lname_value,
                    timer_value=timer_value
                )

                # Week extraction logic
                await _extract_weeks(
                    args, api_cookies, student_id, lname_value, timer_value, teacher_map
                )

    else:
        # API-only mode
        set_config("use_cookie_auth", True)
        set_config("cookie_file", args.cookie_path)
        services = create_services()
        app.set_services(services)

        extraction_service = services["extraction"]
        api_client = services.get("api_client")

        cookie_data = load_cookies(args.cookie_path)
        api_cookies = {cookie['name']: cookie['value'] for cookie in cookie_data['cookies']} if cookie_data else {}
        app.set_api_cookies(api_cookies)

        student_id = cached_student_info.get("id") if cached_student_info else None
        if not student_id:
            logger.error("Student ID missing in saved info, cannot proceed with API-only mode.")
            return

        try:
            teacher_map = await api_client.fetch_teacher_map(student_id, update_cache=args.teacherupdate)
        except Exception as e:
            logger.error(f"Failed to fetch teacher map via API: {e}")
            teacher_map = {}

        await _extract_weeks(
            args, api_cookies, student_id, None, None, teacher_map
        )

async def _extract_weeks(args, api_cookies, student_id, lname_value, timer_value, teacher_map):
    processed_weeks = set()

    if args.teacherupdate and args.skip_timetable:
        logger.info("Teacher mapping updated. Skipping timetable extraction as requested.")
        return

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