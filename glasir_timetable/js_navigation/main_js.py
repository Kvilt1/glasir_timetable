#!/usr/bin/env python3
"""
Modified main entry point for the Glasir Timetable application.
Uses JavaScript-based navigation instead of UI-based navigation.
"""
import os
import json
import asyncio
import sys
import argparse
import re
from pathlib import Path

# Add parent directory to path if running as script
if __name__ == "__main__" or True:  # Always add parent dir to path
    # Get the parent directory of this file
    parent_dir = Path(__file__).resolve().parent.parent
    # Add to sys.path if not already there
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

# Try different import paths
try:
    from playwright.async_api import async_playwright
    from glasir_timetable.auth import login_to_glasir
    from glasir_timetable.extractors import extract_teacher_map
except ModuleNotFoundError:
    # Try relative imports instead
    try:
        sys.path.insert(0, str(parent_dir))
        from playwright.async_api import async_playwright
        from auth import login_to_glasir
        from extractors.teacher_map import extract_teacher_map
    except ModuleNotFoundError:
        print("ERROR: Could not import required modules.")
        print("Make sure you're in the correct directory or that the Python module is installed.")
        print("Current sys.path:", sys.path)
        raise

# Import JavaScript integration functions
from scripts.js_integration import (
    inject_timetable_script,
    get_student_id,
    navigate_to_week_js,
    extract_timetable_data_js,
    return_to_baseline_js,
    test_javascript_integration,
    JavaScriptIntegrationError
)

async def main():
    """
    Main entry point for the Glasir Timetable application.
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Extract timetable data from Glasir')
    parser.add_argument('--email', type=str, help='Email for login')
    parser.add_argument('--password', type=str, help='Password for login')
    parser.add_argument('--credentials-file', type=str, default='credentials.json', help='JSON file with email and password')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--output-dir', type=str, default='weeks', help='Directory to save output files')
    parser.add_argument('--test-js', action='store_true', help='Test the JavaScript integration before extracting data')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (default: False)')
    args = parser.parse_args()
    
    # Load credentials
    credentials = {}
    if os.path.exists(args.credentials_file):
        try:
            with open(args.credentials_file, 'r') as f:
                credentials = json.load(f)
        except FileNotFoundError:
            print(f"{args.credentials_file} not found. Please create a credentials.json file with 'email' and 'password' fields.")
            return
        except json.JSONDecodeError:
            print(f"Error: {args.credentials_file} is not valid JSON. Please check the file format.")
            return
    
    # Command line arguments override credentials file
    if args.email:
        credentials["email"] = args.email
    if args.password:
        credentials["password"] = args.password
    
    # Check for required credentials
    if "email" not in credentials or "password" not in credentials:
        print("Error: Email and password must be provided either in credentials file or as command line arguments")
        return
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize Playwright
    async with async_playwright() as p:
        # Launch browser with headless mode controlled by arguments
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Login to Glasir
            await login_to_glasir(page, credentials["email"], credentials["password"])
            
            # Inject the JavaScript navigation script
            await inject_timetable_script(page)
            
            # Test the JavaScript integration if requested
            if args.test_js:
                print("Testing JavaScript integration...")
                try:
                    await test_javascript_integration(page)
                    print("JavaScript integration test passed!")
                except JavaScriptIntegrationError as e:
                    print(f"JavaScript integration test failed: {e}")
                    print("Please fix the issues before continuing.")
                    return
            
            # Extract dynamic teacher mapping from the page
            teacher_map = await extract_teacher_map(page)
            
            # Get student ID (needed for navigation)
            try:
                student_id = await get_student_id(page)
            except JavaScriptIntegrationError as e:
                print(f"Error getting student ID: {e}")
                print("Taking a screenshot for debugging...")
                await page.screenshot(path="error_student_id.png")
                return
            
            # Extract and save current week data using JavaScript
            print("Processing current week...")
            try:
                timetable_data, week_info = await extract_timetable_data_js(page, teacher_map)
                
                # Format filename
                filename = f"{week_info['year']} Vika {week_info['week_num']} - {week_info['start_date'].replace('-', '.')}-{week_info['end_date'].replace('-', '.')}.json"
                output_path = os.path.join(args.output_dir, filename)
                
                # Save data to JSON file
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                    
                print(f"Timetable data saved to {output_path}")
                
                # Store processed weeks to avoid duplicates
                processed_weeks = {week_info['week_num']}
            except JavaScriptIntegrationError as e:
                print(f"Error extracting current week data: {e}")
                print("Taking a screenshot for debugging...")
                await page.screenshot(path="error_current_week.png")
                return
            
            # Process backward weeks if requested
            for i in range(1, args.weekbackward + 1):
                print(f"Processing week backward {i}...")
                
                try:
                    # Use JavaScript navigation
                    week_info = await navigate_to_week_js(page, -i, student_id)
                    
                    # Skip if navigation failed or we've already processed this week
                    if not week_info or week_info.get('weekNumber') in processed_weeks:
                        print(f"Week navigation failed or already processed, skipping.")
                        # Return to baseline (current week)
                        await return_to_baseline_js(page, 0, student_id)
                        continue
                    
                    # Mark as processed
                    processed_weeks.add(week_info.get('weekNumber'))
                    
                    # Extract timetable data using JavaScript
                    timetable_data, detailed_week_info = await extract_timetable_data_js(page, teacher_map)
                    
                    # Format filename - convert navigation field names to timetable field names
                    week_num = week_info.get('weekNumber')
                    year = week_info.get('year')
                    start_date = week_info.get('startDate')
                    end_date = week_info.get('endDate')
                    
                    filename = f"{year} Vika {week_num} - {start_date.replace('-', '.')}-{end_date.replace('-', '.')}.json"
                    output_path = os.path.join(args.output_dir, filename)
                    
                    # Save data to JSON file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"Timetable data for Week {week_num} saved to {output_path}")
                except JavaScriptIntegrationError as e:
                    print(f"Error processing week backward {i}: {e}")
                    print("Taking a screenshot for debugging...")
                    await page.screenshot(path=f"error_backward_week_{i}.png")
                finally:
                    # Always try to return to baseline, even if there was an error
                    try:
                        await return_to_baseline_js(page, 0, student_id)
                    except JavaScriptIntegrationError:
                        print("Error returning to baseline week, attempting to continue...")
                    
                    # Wait a bit between requests
                    await asyncio.sleep(2)
            
            # Process forward weeks if requested
            for i in range(1, args.weekforward + 1):
                print(f"Processing week forward {i}...")
                
                try:
                    # Use JavaScript navigation
                    week_info = await navigate_to_week_js(page, i, student_id)
                    
                    # Skip if navigation failed or we've already processed this week
                    if not week_info or week_info.get('weekNumber') in processed_weeks:
                        print(f"Week navigation failed or already processed, skipping.")
                        # Return to baseline (current week)
                        await return_to_baseline_js(page, 0, student_id)
                        continue
                    
                    # Mark as processed
                    processed_weeks.add(week_info.get('weekNumber'))
                    
                    # Extract timetable data using JavaScript
                    timetable_data, detailed_week_info = await extract_timetable_data_js(page, teacher_map)
                    
                    # Format filename - convert navigation field names to timetable field names
                    week_num = week_info.get('weekNumber')
                    year = week_info.get('year')
                    start_date = week_info.get('startDate')
                    end_date = week_info.get('endDate')
                    
                    filename = f"{year} Vika {week_num} - {start_date.replace('-', '.')}-{end_date.replace('-', '.')}.json"
                    output_path = os.path.join(args.output_dir, filename)
                    
                    # Save data to JSON file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"Timetable data for Week {week_num} saved to {output_path}")
                except JavaScriptIntegrationError as e:
                    print(f"Error processing week forward {i}: {e}")
                    print("Taking a screenshot for debugging...")
                    await page.screenshot(path=f"error_forward_week_{i}.png")
                finally:
                    # Always try to return to baseline, even if there was an error
                    try:
                        await return_to_baseline_js(page, 0, student_id)
                    except JavaScriptIntegrationError:
                        print("Error returning to baseline week, attempting to continue...")
                    
                    # Wait a bit between requests
                    await asyncio.sleep(2)
            
            print("All requested weeks processed successfully")
            
        except Exception as e:
            print(f"Error: {e}")
            # Save a screenshot on error to help with debugging
            await page.screenshot(path="error_screenshot.png", full_page=True)
            print("Error screenshot saved to error_screenshot.png")

if __name__ == "__main__":
    asyncio.run(main()) 