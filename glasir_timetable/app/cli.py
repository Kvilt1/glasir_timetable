"""
CLI parsing and interactive prompts for Glasir Timetable.

- Defines parse_args() to handle command-line arguments.
- Defines select_account() for interactive account selection.
- Defines prompt_for_credentials() for username/password input.
"""

import argparse
import sys
import getpass
from glasir_timetable import account_manager

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
    return args

def select_account():
    """
    Interactive account selection using account_manager.
    Returns the selected username.
    """
    return account_manager.interactive_account_selection()

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