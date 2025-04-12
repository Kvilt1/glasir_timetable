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
    # Get the absolute path of the directory containing main.py (project root)
    project_root = os.path.abspath(os.path.dirname(__file__))
    # Add the project root to the beginning of sys.path if it's not already there
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Now the imports will work both when run as a script and when imported as a module
# Keep necessary high-level imports
from glasir_timetable import logger, setup_logging, stats, update_stats, clear_errors # Removed unused imports

# Imports moved to specific modules (auth, api, extractors, interface, etc.)
# Removed imports from core.*, data.*, and unused shared.*

# Imports for the current main structure
from glasir_timetable.interface.cli import parse_args, select_account
from glasir_timetable.interface.config_manager import load_config
from glasir_timetable.interface.application import Application
from glasir_timetable.interface.orchestrator import run_extraction
from glasir_timetable.storage.profile_manager import ProfileManager # Use ProfileManager for account/profile handling

# Removed local duplicate function is_full_auth_data_valid (logic now in config_manager)
# Removed local duplicate function generate_credentials_file (handled by profile/manager)
# Removed local duplicate function prompt_for_credentials (handled by interface.cli)

async def main():
    """
    Main entry point for the Glasir Timetable application.
    """
    # Initialize statistics
    clear_errors()  # Clear any errors from previous runs
    update_stats("start_time", time.time(), increment=False)

    args = parse_args() # Use imported function
    
    # If no log file provided, use default output/logs/glasir_timetable.log
    if not args.log_file:
        log_dir = os.path.join("output", "logs")
        os.makedirs(log_dir, exist_ok=True)
        args.log_file = os.path.join(log_dir, "glasir_timetable.log")
    # Ensure directory for log file exists (handles custom paths)
    log_dir = os.path.dirname(args.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Generate date string for log filename
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Create dated log filename
    base_log_file = args.log_file
    if base_log_file.endswith('.log'):
        dated_log_file = base_log_file[:-4] + f"_{date_str}.log"
    else:
        dated_log_file = base_log_file + f"_{date_str}.log"

    # Create latest log filename in same directory
    latest_log_file = os.path.join(log_dir, "latest.log")


    # Configure logging based on command-line arguments
    log_level = getattr(logging, args.log_level)
    if args.log_file:
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # Handler for dated log file (append mode)
        dated_handler = logging.FileHandler(dated_log_file, mode='a')
        dated_handler.setFormatter(formatter)
        logger.addHandler(dated_handler)

        # Handler for latest.log (overwrite mode)
        latest_handler = logging.FileHandler(latest_log_file, mode='w')
        latest_handler.setFormatter(formatter)
        logger.addHandler(latest_handler)

    # Set the log level
    logger.setLevel(log_level)
    for handler in logger.handlers:
        handler.setLevel(log_level)

    # ---- ACCOUNT SELECTION ----
    # Use imported function
    # AccountManager might be needed implicitly by select_account or load_config
    # Keep AccountManager import at top level
    selected_username, profile_created = select_account() # Capture the tuple

    if selected_username is None:
        logger.error("No accounts found. Please create an account before running the timetable extraction.")
        return

    # Use imported function
    # Pass the profile_created flag to load_config
    config = load_config(args, selected_username, profile_created=profile_created)

    # Removed outdated Playwright setup and service factory logic.
    # This is now handled within the Application/Orchestrator structure.
    from glasir_timetable.interface.application import Application
    # Instantiate Application with the loaded config
    app = Application(config)

    # Run the main extraction process via the orchestrator
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

    # Ensure project root is in sys.path (redundant if first block ran, but safe)
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Check for --profile argument *without* consuming other arguments
    profile_enabled = "--profile" in sys.argv
    if profile_enabled:
        # Remove --profile so it doesn't interfere with the main parser
        sys.argv.remove("--profile")
        # The main() function will now receive the original args minus --profile
    
    # No need to reassign sys.argv here, main() will use the modified sys.argv

    if profile_enabled:
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