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
import asyncio
from asyncio import Queue, Semaphore
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm as tqdm_asyncio
import tqdm # Import the main tqdm module
# Compiled regex patterns
_RE_WEEK_OFFSET = re.compile(r"v=(-?\d+)")
from glasir_timetable.auth.login import login as playwright_login
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.extractors.timetable_extractor import TimetableExtractor
from glasir_timetable.storage.exporter import save_timetable_export # Used by consumer
from glasir_timetable.parsers.timetable_parser import parse_timetable_html # Used by consumer
from glasir_timetable import (
    logger, stats, update_stats, get_error_summary, configure_raw_responses
)
# Removed core.service_factory import
from glasir_timetable.auth.cookies import load_cookies_for_profile # Import correct function
# Removed import of non-existent extract_min_max_week_offsets
from glasir_timetable.auth.session_params import extract_session_params_from_html # Corrected import
# from glasir_timetable.core.student_utils import get_student_id # Removed import
from glasir_timetable.shared.constants import (
    GLASIR_TIMETABLE_URL, DEFAULT_HEADERS,
    DEFAULT_WEEK_FETCH_CONCURRENCY, DEFAULT_HOMEWORK_FETCH_CONCURRENCY,
    DEFAULT_WEEK_PROCESS_CONCURRENCY, # Default consumer count
    FORCE_MAX_WEEK_FETCH_CONCURRENCY, FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY # Import new max constants
)
from glasir_timetable.storage.profile_manager import ProfileData # Import ProfileData
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager

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
    concurrency_config = app.concurrency_config # Get loaded concurrency settings

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
                    await save_cookies_for_profile(profile, cookie_data)
                    logger.info(f"Saved cookies for user {profile.username} after login")
                else:
                    logger.warning("No active profile found to save cookies")
                api_cookies = {cookie['name']: cookie['value'] for cookie in browser_cookies}
                app.set_api_cookies(api_cookies)

                # Student info should have been ensured during login. Retrieve it from the profile object.
                # profile_manager = ProfileManager.get_instance() # No longer needed here
                student_info = await profile.load_student_info() # Load from the specific profile object
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
                # timer_value = session_params.get("timer") # Removed: Timer is generated dynamically

                # Initialize API client and extractor
                api_client = AsyncApiClient(
                    base_url="https://tg.glasir.fo",
                    cookies=api_cookies,
                    # Always use a dynamically generated timer for consistency
                    session_params={"lname": lname_value, "timer": str(int(time.time() * 1000))}
                )
                extractor = TimetableExtractor(api_client)

                # Fetch teacher map
                try:
                    teacher_map = await extractor.fetch_teacher_map() # fetch_teacher_map doesn't take cookies arg
                except Exception as e:
                    logger.error(f"Failed to fetch teacher map: {e}")
                    teacher_map = {}

                # Week extraction logic - Pass the app object
                await _extract_weeks_with_extractor(
                    app, extractor, student_id, teacher_map, profile, credentials["username"], concurrency_config
                )

                await api_client.close()

    else:
        # API-only mode
        # Load cookies using the profile object from the app context
        profile = app.profile # Assuming app object has profile attribute from config
        cookie_data = await load_cookies_for_profile(profile)
        api_cookies = {cookie['name']: cookie['value'] for cookie in cookie_data['cookies']} if cookie_data else {}
        app.set_api_cookies(api_cookies)

        student_id = cached_student_info.get("id") if cached_student_info else None
        if not student_id:
            logger.error("Student ID missing in saved info, cannot proceed with API-only mode.")
            return

        # Fetch dynamic params
        extracted_lname = None
        # extracted_timer = None # Removed: Timer is generated dynamically later
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
            teacher_map = await extractor.fetch_teacher_map() # fetch_teacher_map doesn't take cookies arg
        except Exception as e:
            logger.error(f"Failed to fetch teacher map: {e}")
            teacher_map = {}

        # Week extraction logic - Pass the app object
        await _extract_weeks_with_extractor(
            app, extractor, student_id, teacher_map, profile, credentials["username"], concurrency_config
        )

        await api_client.close()

# --- Producer-Consumer Implementation ---

async def _week_fetch_producer( # Add force_max_concurrency flag
    fetch_queue: Queue,
    process_queue: Queue,
    extractor: TimetableExtractor,
    student_id: str,
    lname_value: str,
    timer_value: str,
    fetch_semaphore: asyncio.Semaphore,
    week_fetch_manager: ConcurrencyManager,
    force_max_concurrency: bool
):
    """Producer task: Fetches week HTML and puts it on the process_queue."""
    while True:
        try:
            offset = await fetch_queue.get()
            if offset is None: # Sentinel value indicates completion
                # logger.debug("Producer received sentinel, exiting.")
                fetch_queue.task_done()
                break

            async with fetch_semaphore: # Limit concurrent fetches
                tqdm.tqdm.write(f"[Producer] Fetching HTML for week offset {offset}")
                try:
                    html_content = await extractor.fetch_week_html(
                        week_offset=offset,
                        student_id=student_id,
                        lname_value=lname_value,
                        timer_value=timer_value,
                        week_concurrency_manager=week_fetch_manager, # Pass manager
                        force_max_concurrency=force_max_concurrency # Pass flag
                    )
                    if html_content:
                        await process_queue.put((offset, html_content))
                        tqdm.tqdm.write(f"[Producer] Queued week {offset} for processing.") # Changed from debug to info for visibility with tqdm
                    else:
                        tqdm.tqdm.write(f"[Producer] WARNING: Received empty HTML for week {offset}, skipping.")
                        # Success/failure reporting is now handled by the API client via the manager
                except Exception as e:
                    # Failure reporting is now handled by the API client
                    tqdm.tqdm.write(f"[Producer] ERROR fetching week {offset}: {e}")
                    # Optionally put an error marker or skip: await process_queue.put((offset, None, e))
                finally:
                    fetch_queue.task_done() # Signal task completion for this offset

        except asyncio.CancelledError:
            tqdm.tqdm.write("Producer task cancelled.")
            break
        except Exception as e:
            tqdm.tqdm.write(f"Unexpected ERROR in producer: {e}")
            # Ensure task_done is called even on unexpected errors if an item was retrieved
            if 'offset' in locals() and offset is not None:
                 try:
                     fetch_queue.task_done()
                 except ValueError: # May happen if task_done called twice
                     pass
            break # Exit loop on unexpected error

async def _week_process_consumer(
    process_queue: Queue,
    extractor: TimetableExtractor,
    teacher_map: dict,
    student_info: dict,
    profile: ProfileData,
    user_id: str,
    results_counter: dict,
    homework_fetch_manager: ConcurrencyManager,
    force_max_concurrency: bool,
    progress_bar: tqdm_asyncio, # Added progress bar
    week_fetch_manager: ConcurrencyManager, # Added week manager for postfix
    update_postfix_func: callable # Added postfix update function
):
    """Consumer task: Processes HTML, fetches homework, saves data."""
    while True:
        try:
            item = await process_queue.get()
            if item is None: # Sentinel value indicates completion
                # logger.debug("Consumer received sentinel, exiting.")
                process_queue.task_done()
                break

            offset, html_content = item
            # Optional: async with process_semaphore:
            # tqdm.tqdm.write(f"[Consumer] Processing week offset {offset}") # Less verbose with progress bar
            try:
                # 1. Parse main timetable HTML
                timetable_data, homework_ids = parse_timetable_html(html_content, teacher_map=teacher_map)
                html_content = None # Dereference large HTML string after parsing

                # 2. Fetch associated homework
                homework_map = await extractor.fetch_homework_for_lessons(
                    homework_ids,
                    concurrency_manager=homework_fetch_manager, # Pass manager
                    force_max_concurrency=force_max_concurrency # Pass flag
                )

                # 3. Merge homework into events
                for event in timetable_data.get("events", []):
                    lesson_id = event.get("lessonId")
                    if lesson_id and lesson_id in homework_map:
                        event["description"] = homework_map[lesson_id]

                # 4. Overwrite studentInfo with profile data if provided
                if student_info:
                    timetable_data["studentInfo"] = student_info

                # 5. Save the result
                output_dir_path = profile.weeks_dir
                save_path = await save_timetable_export(
                    timetable_data,
                    output_dir=str(output_dir_path),
                    user_id=user_id # Note: user_id is not actually used by save_timetable_export anymore
                )
                # tqdm.tqdm.write(f"[Consumer] Saved week {offset} data to {save_path}") # Less verbose with progress bar
                results_counter["success"] += 1
                progress_bar.update(1) # Update progress bar
                await update_postfix_func() # Update postfix after successful processing

            except Exception as e:
                tqdm.tqdm.write(f"[Consumer] ERROR processing week {offset}: {e}")
                results_counter["failure"] += 1
            finally:
                process_queue.task_done() # Signal task completion for this item

        except asyncio.CancelledError:
            tqdm.tqdm.write("Consumer task cancelled.")
            break
        except Exception as e:
            tqdm.tqdm.write(f"Unexpected ERROR in consumer: {e}")
            # Ensure task_done is called even on unexpected errors if an item was retrieved
            if 'item' in locals() and item is not None:
                 try:
                     process_queue.task_done()
                 except ValueError:
                     pass
            break # Exit loop on unexpected error

# --- End Producer-Consumer ---
async def _extract_weeks_with_extractor(
    app,
    extractor: TimetableExtractor,
    student_id: str,
    teacher_map: dict,
    profile: ProfileData,
    user_id: str,
    concurrency_config: dict
):
    """Orchestrates week data extraction using a producer-consumer pattern with tqdm progress."""
    args = app.args # Get args from app
    force_max_concurrency = app.force_max_concurrency # Get the flag from the app object
    lname_value = extractor.api.session_params.get("lname")
    # Retrieve lname and dynamically generated timer from the initialized API client
    lname_value = extractor.api.session_params.get("lname")
    timer_value = extractor.api.session_params.get("timer") # This should now be the dynamically generated one

    # Load student info (used by consumer)
    try:
        student_info = await profile.load_student_info()
        if not student_info:
             logger.warning(f"Loaded student info for profile '{profile.username}' is empty or invalid.")
             student_info = None
    except Exception as e:
        logger.error(f"Error loading student info for profile '{profile.username}': {e}")
        student_info = None

    # --- Initialize Concurrency Managers ---
    # Moved up to be available for --all-weeks base fetch
    # Determine initial limits based on the flag
    if force_max_concurrency:
        logger.warning("Using --force-max-concurrency: Overriding dynamic limits with predefined maximums.")
        initial_week_limit = FORCE_MAX_WEEK_FETCH_CONCURRENCY
        initial_homework_limit = FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY
    else:
        initial_week_limit = concurrency_config.get("week_fetch_limit", DEFAULT_WEEK_FETCH_CONCURRENCY)
        initial_homework_limit = concurrency_config.get("homework_fetch_limit", DEFAULT_HOMEWORK_FETCH_CONCURRENCY)

    week_fetch_manager = ConcurrencyManager(
        initial_limit=initial_week_limit,
        min_limit=1,
        max_limit=50, # Max for dynamic adjustment, not the forced max
        name="WeekFetch",
        disabled=force_max_concurrency # Disable dynamic adjustments if forced
    )
    homework_fetch_manager = ConcurrencyManager(
        initial_limit=initial_homework_limit,
        min_limit=1,
        max_limit=100, # Max for dynamic adjustment, not the forced max
        name="HomeworkFetch",
        disabled=force_max_concurrency # Disable dynamic adjustments if forced
    )

    # Determine week offsets to process
    if args.teacherupdate and args.skip_timetable:
        logger.info("Teacher mapping updated. Skipping timetable extraction as requested.")
        return

    directions = []
    try:
        if args.all_weeks:
            logger.info("Processing all available weeks (--all-weeks)...")
            # Fetch base week HTML to find week links
            # Pass the week_fetch_manager here as well
            base_html = await extractor.fetch_week_html(
                week_offset=0, student_id=student_id, lname_value=lname_value, timer_value=timer_value,
                week_concurrency_manager=week_fetch_manager
            )
            if not base_html:
                raise RuntimeError("Could not fetch base week HTML (offset 0) to determine week range.")

            soup = BeautifulSoup(base_html, 'html.parser')
            week_links = soup.select('a[onclick*="v="]')
            offsets = set()
            for link in week_links:
                match = _RE_WEEK_OFFSET.search(link['onclick'])
                if match:
                    try: offsets.add(int(match.group(1)))
                    except (ValueError, TypeError): logger.warning(f"Could not parse week offset from onclick: {link['onclick']}")

            if not offsets:
                raise RuntimeError("No week offsets found in base week HTML.")

            min_offset, max_offset = min(offsets), max(offsets)
            logger.info(f"Determined week range from HTML: {min_offset} to {max_offset}")
            directions = list(range(min_offset, max_offset + 1))

        elif args.forward:
            logger.warning("--forward functionality is currently disabled. Processing current week only.")
            directions = [0] # Default to current week

        elif args.weekforward > 0 or args.weekbackward > 0:
            logger.info(f"Processing specified range: {args.weekbackward} backward, {args.weekforward} forward, including current (0)")
            directions_set = {0}
            for i in range(1, args.weekforward + 1): directions_set.add(i)
            for i in range(1, args.weekbackward + 1): directions_set.add(-i)
            directions = sorted(list(directions_set))

        else:
            logger.info("No week range specified, processing current week only")
            directions = [0]

    except Exception as e:
        logger.critical(f"Failed to determine week range: {e}. Aborting week extraction.")
        return # Stop if we can't determine the weeks

    if not directions:
        logger.info("No week offsets determined to process.")
        return

    total_weeks = len(directions)
    progress_bar = None # Initialize progress_bar to None

    # --- Helper for Postfix Update ---
    async def _update_progress_bar_postfix():
        if progress_bar:
            week_limit = week_fetch_manager.get_current_limit()
            homework_limit = homework_fetch_manager.get_current_limit()
            postfix_str = f"W Fetch: {week_limit}, H Fetch: {homework_limit}"
            progress_bar.set_postfix_str(postfix_str, refresh=False) # Let update handle refresh

    try:
        # --- Setup Producer-Consumer ---
        fetch_queue = Queue()
        process_queue = Queue(maxsize=DEFAULT_WEEK_PROCESS_CONCURRENCY * 2) # Buffer processed items slightly

        # --- Concurrency Managers Initialized Above ---
        
        fetch_semaphore = asyncio.Semaphore(week_fetch_manager.get_limit()) # Use initial limit from manager
        # process_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WEEK_PROCESSES) # Optional processing semaphore
        results_counter = {"success": 0, "failure": 0}

        # Populate fetch queue
        for offset in directions:
            await fetch_queue.put(offset)

        # Initialize Progress Bar
        progress_bar = tqdm_asyncio(
            total=total_weeks,
            desc="Processing Weeks",
            unit="week",
            smoothing=0.1, # Standard smoothing for ETA
            leave=True # Keep the bar after completion
        )
        await _update_progress_bar_postfix() # Initial postfix update

        tqdm.tqdm.write(f"Starting extraction for {total_weeks} weeks. "
                   f"Initial Limits - Week Fetch: {week_fetch_manager.get_limit()}, Homework Fetch: {homework_fetch_manager.get_limit()}, Processors: {concurrency_config.get('week_process_limit', DEFAULT_WEEK_PROCESS_CONCURRENCY)}")

        # Create and start producer tasks
        producer_tasks = []
        # Use the manager's initial limit to determine the number of producer tasks
        num_producers = week_fetch_manager.get_limit()
        # tqdm_write(f"Creating {num_producers} producer tasks based on initial week_fetch_limit.") # Less verbose
        for _ in range(num_producers):
            task = asyncio.create_task(
                _week_fetch_producer(
                    fetch_queue, process_queue, extractor, student_id, lname_value, timer_value, fetch_semaphore, week_fetch_manager, force_max_concurrency # Pass flag
                )
            )
            producer_tasks.append(task)

        # Create and start consumer tasks
        consumer_tasks = []
        # Use a fixed number of consumers for processing, homework concurrency is handled within the consumer
        # Use the configured or default number of consumers
        num_consumers = concurrency_config.get("week_process_limit", DEFAULT_WEEK_PROCESS_CONCURRENCY)
        # tqdm_write(f"Creating {num_consumers} consumer tasks.") # Less verbose
        for _ in range(num_consumers):
            task = asyncio.create_task(
                _week_process_consumer(
                    process_queue, extractor, teacher_map, student_info, profile, user_id, results_counter, homework_fetch_manager, force_max_concurrency,
                    progress_bar, week_fetch_manager, _update_progress_bar_postfix # Pass tqdm bar, managers, and helper
                )
            )
            consumer_tasks.append(task)

        # --- Wait for completion ---
        # 1. Wait for all fetch tasks to be picked up and processed by producers
        await fetch_queue.join()
        tqdm.tqdm.write("Fetch queue empty. Signaling producers to stop.")

        # 2. Signal producers to stop by sending sentinel values
        for _ in producer_tasks:
            await fetch_queue.put(None)

        # 3. Wait for producers to finish cleanly
        await asyncio.gather(*producer_tasks, return_exceptions=True) # Allow capturing producer errors
        tqdm.tqdm.write("All producer tasks finished.")

        # 4. Wait for all processing tasks to be picked up and processed by consumers
        await process_queue.join()
        tqdm.tqdm.write("Process queue empty. Signaling consumers to stop.")

        # 5. Signal consumers to stop
        for _ in consumer_tasks:
            await process_queue.put(None)

        # 6. Wait for consumers to finish cleanly
        await asyncio.gather(*consumer_tasks, return_exceptions=True) # Allow capturing consumer errors
        tqdm.tqdm.write("All consumer tasks finished.")

        # Final summary outside tqdm context might be cleaner
        # logger.info(f"Week processing complete. Success: {results_counter['success']}, Failures: {results_counter['failure']}")

    finally:
        if progress_bar:
            progress_bar.close()
            # Print final summary after closing the bar
            logger.info(f"Week processing complete. Success: {results_counter['success']}, Failures: {results_counter['failure']}")

        # --- Save Final Concurrency Limits ---
        final_week_limit = week_fetch_manager.get_limit()
        final_homework_limit = homework_fetch_manager.get_limit()
        logger.info(f"Final Week Fetch Limit: {final_week_limit}")
        logger.info(f"Final Homework Fetch Limit: {final_homework_limit}")

        # Prepare data to save
        final_config_data = {
            "week_fetch_limit": final_week_limit,
            "homework_fetch_limit": final_homework_limit,
            "week_process_limit": num_consumers, # Save the potentially adjusted process limit too
        }

        if not force_max_concurrency:
            try:
                await profile.save_concurrency_config(final_config_data)
                logger.info(f"Saved final concurrency limits to {profile.concurrency_config_path}")
            except Exception as e:
                logger.error(f"Failed to save final concurrency limits: {e}")
        else:
            logger.warning("Skipping save of concurrency limits due to --force-max-concurrency flag.")