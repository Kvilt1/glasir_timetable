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
from pathlib import Path

# Add parent directory to path if running as script
if __name__ == "__main__":
    # Get the parent directory of this file
    parent_dir = Path(__file__).resolve().parent
    # Add to sys.path if not already there
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

# Now the imports will work both when run as a script and when imported as a module
from playwright.async_api import async_playwright
from glasir_timetable.auth import login_to_glasir
from glasir_timetable.extractors import (
    extract_teacher_map, 
    extract_timetable_data,
    analyze_week_structure,
    find_week_v_value,
    navigate_to_week,
    get_current_week_info,
    return_to_baseline
)

# Import JavaScript navigation functions
try:
    from glasir_timetable.js_navigation.js_integration import (
        inject_timetable_script,
        get_student_id,
        navigate_to_week_js,
        extract_timetable_data_js,
        return_to_baseline_js,
        test_javascript_integration,
        extract_homework_content_js,
        extract_all_homework_content_js,
        JavaScriptIntegrationError
    )
    JS_NAVIGATION_AVAILABLE = True
except ImportError:
    JS_NAVIGATION_AVAILABLE = False
    print("WARNING: JavaScript navigation module not found. --use-js option will be disabled.")

async def main():
    """
    Main entry point for the Glasir Timetable application.
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Extract timetable data from Glasir')
    parser.add_argument('--email', type=str, help='Email for login')
    parser.add_argument('--password', type=str, help='Password for login')
    parser.add_argument('--credentials-file', type=str, default='glasir_timetable/credentials.json', help='JSON file with email and password')
    parser.add_argument('--weekforward', type=int, default=0, help='Number of weeks forward to extract')
    parser.add_argument('--weekbackward', type=int, default=0, help='Number of weeks backward to extract')
    parser.add_argument('--output-dir', type=str, default='glasir_timetable/weeks', help='Directory to save output files')
    parser.add_argument('--academic-year', type=str, choices=['first', 'second', 'auto'], default='auto', 
                        help='Which academic year to use (first, second, or auto for automatic detection)')
    parser.add_argument('--use-js', action='store_true', help='Use JavaScript-based navigation instead of UI-based navigation')
    parser.add_argument('--test-js', action='store_true', help='Test the JavaScript integration before extracting data')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (default: True)')
    args = parser.parse_args()
    
    # Check if JavaScript navigation is available when requested
    if args.use_js and not JS_NAVIGATION_AVAILABLE:
        print("ERROR: JavaScript navigation was requested but the module is not available.")
        print("Please make sure the scripts directory is properly set up.")
        return
    
    # Load credentials
    credentials = {}
    if os.path.exists(args.credentials_file):
        try:
            with open(args.credentials_file, 'r') as f:
                credentials = json.load(f)
        except FileNotFoundError:
            print(f"{args.credentials_file} not found. Please create a credentials.json file with 'email' and 'password' fields.")
            return
    
    # Command line arguments override credentials file
    if args.email:
        credentials["email"] = args.email
    if args.password:
        credentials["password"] = args.password
    
    # Check for required credentials
    if "email" not in credentials or "password" not in credentials:
        print("Email and password must be provided either in credentials file or as command line arguments")
        return
    
    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Login to Glasir
            await login_to_glasir(page, credentials["email"], credentials["password"])
            
            # Initialize student_id for JavaScript navigation if requested
            student_id = None
            if args.use_js:
                try:
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
                        
                    # Get student ID (needed for navigation)
                    student_id = await get_student_id(page)
                except JavaScriptIntegrationError as e:
                    print(f"Error initializing JavaScript navigation: {e}")
                    print("Taking a screenshot for debugging...")
                    await page.screenshot(path="error_js_init.png")
                    return
            
            # Variables for UI-based navigation
            original_week_v_value = None
            week_to_v_map = {}
            
            # If using UI-based navigation and we're doing week navigation, analyze the week structure
            if not args.use_js and (args.weekforward > 0 or args.weekbackward > 0):
                # Analyze the week structure to identify academic year sections and v-values
                all_weeks, academic_year_sections, current_section_key = await analyze_week_structure(page)
                
                # Allow manual override of academic year selection
                if args.academic_year != 'auto' and len(academic_year_sections) > 1:
                    if args.academic_year == 'first':
                        # Use the first academic year
                        current_section_key = list(academic_year_sections.keys())[0]
                        print(f"Manually selected first academic year section: {current_section_key}")
                    elif args.academic_year == 'second':
                        # Use the second academic year
                        if len(academic_year_sections) >= 2:
                            current_section_key = list(academic_year_sections.keys())[1]
                            print(f"Manually selected second academic year section: {current_section_key}")
                        else:
                            print("Warning: Second academic year requested but only one year available.")
                
                if not current_section_key:
                    print("Warning: Could not determine current academic year section, will use default navigation.")
                    # Create a flat mapping of week numbers to v-values from all weeks
                    week_to_v_map = {}
                    for week in all_weeks:
                        week_num = week['weekNum']
                        if week_num not in week_to_v_map or week.get('isCurrentWeek', False):
                            week_to_v_map[week_num] = week['v']
                    
                    current_section_weeks = all_weeks
                else:
                    # Use only weeks from the selected academic year section
                    section_data = academic_year_sections[current_section_key]
                    current_section_weeks = section_data['weeks']
                    week_to_v_map = section_data['v_mapping']
                    print(f"Using weeks from section: {current_section_key}")
                    print(f"V-value mapping for this section: {json.dumps(week_to_v_map)}")
                    
                # Store original week v-value for accurate baseline return
                original_week_button = next((w for w in all_weeks if w.get('isCurrentWeek', False)), None)
                if original_week_button:
                    original_week_v_value = original_week_button['v']
                    print(f"Original week has v-value: {original_week_v_value}")
            
            # Extract dynamic teacher mapping from the page
            teacher_map = await extract_teacher_map(page)
            
            # Extract and save current week data
            print("Processing current week...")
            # Always use the standard data extraction, even when using JS navigation
            if args.use_js:
                # First navigate using JS to ensure we're on the right week
                await inject_timetable_script(page)
                await get_student_id(page)
                # But still use the original extraction method
                timetable_data, week_info = await extract_timetable_data(page, teacher_map)
            else:
                timetable_data, week_info = await extract_timetable_data(page, teacher_map)
                
                # If we didn't get the v-value from the button and we're doing week navigation, try to get it from the page URL
                if (args.weekforward > 0 or args.weekbackward > 0) and original_week_v_value is None:
                    current_url = page.url
                    v_match = re.search(r'v=(-?\d+)', current_url)
                    if v_match:
                        original_week_v_value = int(v_match.group(1))
                        print(f"Original week has v-value (from URL): {original_week_v_value}")
                    else:
                        # Default to 0 as a last resort
                        original_week_v_value = 0
                        print("Using default v-value (0) for original week")
            
            # Format filename with standardized format (YYYY Vika XX - YYYY.MM.DD-YYYY.MM.DD.json)
            # Ensure dates have year prefix
            start_date = week_info['start_date']
            end_date = week_info['end_date']
            
            # Add year prefix if not already present
            if not start_date.startswith(str(week_info['year'])):
                start_date = f"{week_info['year']}.{start_date}"
            if not end_date.startswith(str(week_info['year'])):
                end_date = f"{week_info['year']}.{end_date}"
            
            # Replace any hyphens with periods for consistency
            start_date = start_date.replace('-', '.')
            end_date = end_date.replace('-', '.')
            
            filename = f"{week_info['year']} Vika {week_info['week_num']} - {start_date}-{end_date}.json"
            output_path = os.path.join(args.output_dir, filename)
            
            # Save data to JSON file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                
            print(f"Timetable data saved to {output_path}")
            
            # Store processed weeks to avoid duplicates
            processed_weeks = {week_info['week_num']}
            
            # Process backward weeks if requested
            for i in range(1, args.weekbackward + 1):
                print(f"Processing week backward {i}...")
                
                try:
                    # Use the appropriate navigation method
                    if args.use_js:
                        # Navigate using JavaScript
                        week_info = await navigate_to_week_js(page, -i, student_id)
                        
                        # Skip if navigation failed or we've already processed this week
                        if not week_info or week_info.get('weekNumber') in processed_weeks:
                            print(f"Week navigation failed or already processed, skipping.")
                            # Return to baseline using appropriate method
                            await return_to_baseline_js(page, 0, student_id)
                            continue
                            
                        # But use the original extraction method for data
                        timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                        
                        # Convert JavaScript week_info format to standard format
                        week_num = week_info.get('weekNumber')
                        year = week_info.get('year')
                        start_date = week_info.get('startDate')
                        end_date = week_info.get('endDate')
                    else:
                        week_info = await navigate_to_week(page, -i)  # Negative offset for backward
                        
                        # Skip if navigation failed or we've already processed this week
                        if not week_info or week_info.get('weekNumber') in processed_weeks:
                            print(f"Week navigation failed or already processed, skipping.")
                            # Return to baseline using appropriate method
                            await return_to_baseline(page, original_week_v_value)
                            continue
                            
                        # Mark as processed
                        processed_weeks.add(week_info.get('weekNumber'))
                        
                        # Extract timetable data
                        timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                        
                        # Get values in standard format
                        week_num = week_info.get('weekNumber')
                        year = week_info.get('year')
                        start_date = week_info.get('startDate')
                        end_date = week_info.get('endDate')
                    
                    # Mark as processed
                    processed_weeks.add(week_num)
                    
                    # Ensure dates have year prefix
                    if not start_date.startswith(str(year)):
                        start_date = f"{year}.{start_date}"
                    if not end_date.startswith(str(year)):
                        end_date = f"{year}.{end_date}"
                    
                    # Replace any hyphens with periods for consistency
                    start_date = start_date.replace('-', '.')
                    end_date = end_date.replace('-', '.')
                    
                    # Use standardized filename format
                    filename = f"{year} Vika {week_num} - {start_date}-{end_date}.json"
                    output_path = os.path.join(args.output_dir, filename)
                    
                    # Save data to JSON file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"Timetable data for Week {week_num} saved to {output_path}")
                except Exception as e:
                    print(f"Error processing week backward {i}: {e}")
                    print("Taking a screenshot for debugging...")
                    await page.screenshot(path=f"error_backward_week_{i}.png")
                finally:
                    # Always try to return to baseline, even if there was an error
                    try:
                        if args.use_js:
                            await return_to_baseline_js(page, 0, student_id)
                        else:
                            await return_to_baseline(page, original_week_v_value)
                    except Exception as e:
                        print(f"Error returning to baseline week: {e}")
                        print("Attempting to continue...")
                    
                    # Wait a bit between requests - reduced for JS navigation
                    if args.use_js:
                        # JavaScript navigation already has a built-in 500ms delay, so we need minimal additional delay
                        await asyncio.sleep(0.2)  # Just 200ms to avoid overwhelming the server
                    else:
                        # Keep the original delay for UI-based navigation
                        await asyncio.sleep(2)
            
            # Process forward weeks if requested
            for i in range(1, args.weekforward + 1):
                print(f"Processing week forward {i}...")
                
                try:
                    # Use the appropriate navigation method
                    if args.use_js:
                        # Navigate using JavaScript
                        week_info = await navigate_to_week_js(page, i, student_id)
                        
                        # Skip if navigation failed or we've already processed this week
                        if not week_info or week_info.get('weekNumber') in processed_weeks:
                            print(f"Week navigation failed or already processed, skipping.")
                            # Return to baseline using appropriate method
                            await return_to_baseline_js(page, 0, student_id)
                            continue
                            
                        # But use the original extraction method for data
                        timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                        
                        # Convert JavaScript week_info format to standard format
                        week_num = week_info.get('weekNumber')
                        year = week_info.get('year')
                        start_date = week_info.get('startDate')
                        end_date = week_info.get('endDate')
                    else:
                        week_info = await navigate_to_week(page, i)  # Positive offset for forward
                        
                        # Skip if navigation failed or we've already processed this week
                        if not week_info or week_info.get('weekNumber') in processed_weeks:
                            print(f"Week navigation failed or already processed, skipping.")
                            # Return to baseline using appropriate method
                            await return_to_baseline(page, original_week_v_value)
                            continue
                            
                        # Mark as processed
                        processed_weeks.add(week_info.get('weekNumber'))
                        
                        # Extract timetable data
                        timetable_data, week_details = await extract_timetable_data(page, teacher_map)
                        
                        # Get values in standard format
                        week_num = week_info.get('weekNumber')
                        year = week_info.get('year')
                        start_date = week_info.get('startDate')
                        end_date = week_info.get('endDate')
                    
                    # Mark as processed
                    processed_weeks.add(week_num)
                    
                    # Ensure dates have year prefix
                    if not start_date.startswith(str(year)):
                        start_date = f"{year}.{start_date}"
                    if not end_date.startswith(str(year)):
                        end_date = f"{year}.{end_date}"
                    
                    # Replace any hyphens with periods for consistency
                    start_date = start_date.replace('-', '.')
                    end_date = end_date.replace('-', '.')
                    
                    # Use standardized filename format
                    filename = f"{year} Vika {week_num} - {start_date}-{end_date}.json"
                    output_path = os.path.join(args.output_dir, filename)
                    
                    # Save data to JSON file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(timetable_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"Timetable data for Week {week_num} saved to {output_path}")
                except Exception as e:
                    print(f"Error processing week forward {i}: {e}")
                    print("Taking a screenshot for debugging...")
                    await page.screenshot(path=f"error_forward_week_{i}.png")
                finally:
                    # Always try to return to baseline, even if there was an error
                    try:
                        if args.use_js:
                            await return_to_baseline_js(page, 0, student_id)
                        else:
                            await return_to_baseline(page, original_week_v_value)
                    except Exception as e:
                        print(f"Error returning to baseline week: {e}")
                        print("Attempting to continue...")
                    
                    # Wait a bit between requests - reduced for JS navigation
                    if args.use_js:
                        # JavaScript navigation already has a built-in 500ms delay, so we need minimal additional delay
                        await asyncio.sleep(0.2)  # Just 200ms to avoid overwhelming the server
                    else:
                        # Keep the original delay for UI-based navigation
                        await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error: {e}")
            # Save a screenshot on error to help with debugging
            await page.screenshot(path="error_screenshot.png", full_page=True)
            print("Error screenshot saved to error_screenshot.png")

if __name__ == "__main__":
    asyncio.run(main()) 