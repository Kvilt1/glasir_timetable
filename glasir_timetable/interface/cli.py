"""
CLI parsing and interactive prompts for Glasir Timetable.

- Defines parse_args() to handle command-line arguments.
- Defines select_account() for interactive account selection.
- Defines prompt_for_credentials() for username/password input.
"""

import argparse
import sys
import getpass
from glasir_timetable.storage.profile_manager import ProfileManager
from typing import Optional

def parse_args():
    print('DEBUG: sys.argv before parsing:', sys.argv)
    parser = argparse.ArgumentParser(description='Extract timetable data from Glasir')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--all-weeks', action='store_true', help='Extract all available weeks from all academic years')
    parser.add_argument('--forward', action='store_true', help='Extract only current and future weeks (positive offsets) dynamically')
    parser.add_argument('--output-dir', type=str, default='glasir_timetable/weeks', help='Directory to save output files')
    parser.add_argument('--headless', action='store_false', dest='headless', default=True, help='Run in non-headless mode (default: headless=True)')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='Set the logging level')
    parser.add_argument('--log-file', type=str, default='output/logs/glasir_timetable.log', help='Log to a file instead of console (default: output/logs/glasir_timetable.log)')
    parser.add_argument('--account', type=str, default=None, help='Specify the account profile username directly, skipping interactive selection')
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
    parser.add_argument('--raw-responses-dir', type=str, default='output/raw_responses/', help='Directory to save raw API responses (default: output/raw_responses/)')
    parser.add_argument('--force-max-concurrency', action='store_true', default=False, help='Force concurrency to predefined maximum limits for this run (does not save)')
    args = parser.parse_args()
    return args

from typing import Tuple # Add Tuple import

def select_account() -> Tuple[Optional[str], bool]:
    """
    Interactively prompts the user to select an account profile.

    Returns:
        A tuple containing:
        - The selected username (str) or None if cancelled/failed.
        - A boolean indicating if a new profile was created (True) or an existing one was selected (False).
    """
    profile_manager = ProfileManager.get_instance()
    profiles = profile_manager.list_profiles()

    if not profiles:
        print("No account profiles found.")
        create_new = input("Would you like to create a new profile now? (y/n): ").strip().lower()
        if create_new == 'y':
            credentials = prompt_for_credentials()
            username = credentials.get("username")
            password = credentials.get("password")
            if username and password:
                try:
                    # Pass the full credentials dictionary
                    profile_manager.create_profile(username, credentials=credentials)
                    print(f"Profile '{username}' created successfully.")
                    # Return the newly created username and True flag
                    return username, True
                except Exception as e:
                    print(f"Error creating profile: {e}")
                    return None, False # Indicate failure, profile not created
            else:
                print("Username or password not provided. Cannot create profile.")
                return None, False # Return None username, profile not created
        else:
            print("Profile creation skipped.")
            return None, False # Indicate failure, profile not created

    print("\nAvailable account profiles:")
    for idx, username in enumerate(profiles, 1):
        print(f"  {idx}. {username}")

    while True:
        try:
            choice = input(f"Select a profile by number (1-{len(profiles)}) or press Enter to cancel: ").strip()
            if not choice:
                print("Selection cancelled.")
                return None, False # Indicate skipped, profile not created
            if not choice.isdigit():
                print("Invalid input. Please enter a number.")
                continue
            index = int(choice)
            if 1 <= index <= len(profiles):
                selected_username = profiles[index - 1]
                print(f"Selected profile: {selected_username}")
                # Return selected username and False flag (existing profile)
                return selected_username, False
            else:
                print(f"Invalid number. Please enter a number between 1 and {len(profiles)}.")
        except KeyboardInterrupt:
            print("\nSelection cancelled.")
            return None, False # Indicate cancelled, profile not created

def prompt_for_credentials(username_hint=None):
    """
    Prompt user for username and password.
    Optionally pre-fill username prompt with a hint.
    Returns dict with 'username' and 'password'.
    """
    print("\nNo credentials found. Please enter your Glasir login details:")
    if username_hint:
        username = input(f"Username (without @glasir.fo) [{username_hint}]: ").strip()
        if not username:
            username = username_hint
    else:
        username = input("Username (without @glasir.fo): ").strip()
    password = getpass.getpass("Password: ")
    return {"username": username, "password": password}