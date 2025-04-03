#!/usr/bin/env python3
"""
Timetable extraction logic used to extract data from the Glasir timetable page.
"""

import re
import os
import json
import time
import logging
import asyncio
from typing import Dict, List, Tuple, Any, Union, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from tqdm.auto import tqdm

from glasir_timetable.constants import (
    BLOCK_TIMES,
    DAY_NAME_MAPPING,
    DAYS_ORDER,
    CANCELLED_CLASS_INDICATORS
)
from glasir_timetable.utils.formatting import (
    normalize_week_number,
    convert_keys_to_camel_case,
    format_iso_date,
    parse_time_range,
    format_academic_year,
    get_timeslot_info
)
from glasir_timetable.utils.date_utils import normalize_dates, parse_date
from glasir_timetable.utils.model_adapters import dict_to_timetable_data
from glasir_timetable.utils import logger
from glasir_timetable import add_error, update_stats
# Import get_student_id from student_utils instead of navigation
from glasir_timetable.student_utils import get_student_id
from glasir_timetable.constants import STUDENT_ID_FILE # Use the constant for the file path

from glasir_timetable.models import TimetableData, StudentInfo, WeekInfo, Event

async def extract_student_info(page):
    """
    Extract student name and class from the page title or heading.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        dict: Student information with name and class
    """
    student_info = None
    student_id = None

    # --- Step 1: Try reading from student-id.json ---
    try:
        if os.path.exists(STUDENT_ID_FILE):
            with open(STUDENT_ID_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Check for the required structure and non-empty values
                if isinstance(data, dict) and \
                   data.get("name") and data.get("class") and data.get("id"):
                    student_info = {
                        "student_name": data["name"],
                        "class": data["class"]
                    }
                    student_id = data["id"] # Store the ID as well
                    logger.info(f"Loaded student info from {STUDENT_ID_FILE}: Name='{student_info['student_name']}', Class='{student_info['class']}', ID='{student_id}'")
                    return student_info # Return immediately if found
                else:
                    logger.warning(f"{STUDENT_ID_FILE} found but content is invalid or incomplete. Attempting extraction.")
        else:
            logger.info(f"{STUDENT_ID_FILE} not found. Attempting extraction.")
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error reading or parsing {STUDENT_ID_FILE}: {e}. Attempting extraction.")
    except Exception as e:
         logger.error(f"Unexpected error reading {STUDENT_ID_FILE}: {e}. Attempting extraction.")

    # --- Step 2: Attempt extraction only if not found in JSON ---
    if not student_info:
        logger.info("Attempting to extract student info from page...")
        try:
            # Try to find student info in the page title
            title = await page.title()
            # Check for pattern like "Næmingatímatalva: Rókur Kvilt Meitilberg, 22y"
            title_match = re.search(r"(?:Næmingatímatalva:|Naemingatimatalva:)\s*([^,]+),\s*([^\s\.<]+)", title, re.IGNORECASE)
            if title_match:
                student_info = {
                    "student_name": title_match.group(1).strip(),
                    "class": title_match.group(2).strip()
                }
                logger.info(f"Found student info in page title: {student_info['student_name']}, {student_info['class']}")
                # --- Step 3: Save extracted data to JSON ---
                if not student_id: # Fetch ID if we didn't get it from the file
                    student_id = await get_student_id(page)

                if student_id:
                    save_data = {
                        "id": student_id,
                        "name": student_info["student_name"],
                        "class": student_info["class"]
                    }
                    try:
                        with open(STUDENT_ID_FILE, 'w', encoding='utf-8') as f:
                            json.dump(save_data, f, indent=4)
                        logger.info(f"Successfully extracted and saved student info to {STUDENT_ID_FILE}")
                    except IOError as e:
                        logger.error(f"Failed to save extracted student info to {STUDENT_ID_FILE}: {e}")
                else:
                    logger.warning("Extracted student name/class but could not get student ID to save.")

                return student_info
            
            # Try to extract from the page content directly
            content = await page.content()
            
            # Check for pattern in the content (including HTML entities like &aelig;)
            content_match = re.search(r"N&aelig;mingatímatalva:\s*([^,]+),\s*([^\s<]+)", content, re.IGNORECASE)
            if content_match:
                student_info = {
                    "student_name": content_match.group(1).strip(),
                    "class": content_match.group(2).strip()
                }
                logger.info(f"Found student info in page content: {student_info['student_name']}, {student_info['class']}")
                # --- Step 3: Save extracted data to JSON ---
                if not student_id: # Fetch ID if we didn't get it from the file
                    student_id = await get_student_id(page)

                if student_id:
                    save_data = {
                        "id": student_id,
                        "name": student_info["student_name"],
                        "class": student_info["class"]
                    }
                    try:
                        with open(STUDENT_ID_FILE, 'w', encoding='utf-8') as f:
                            json.dump(save_data, f, indent=4)
                        logger.info(f"Successfully extracted and saved student info to {STUDENT_ID_FILE}")
                    except IOError as e:
                        logger.error(f"Failed to save extracted student info to {STUDENT_ID_FILE}: {e}")
                else:
                    logger.warning("Extracted student name/class but could not get student ID to save.")

                return student_info
            
            # Try to find it in a heading element
            student_info = await page.evaluate('''() => {
                // Check various headings
                for (const selector of ['h1', 'h2', 'h3', '.user-info', '.student-info', 'td']) {
                    const elements = document.querySelectorAll(selector);
                    for (const element of elements) {
                        if (element) {
                            const text = element.textContent || '';
                            // Match various patterns of the student info
                            const patterns = [
                                /Næmingatímatalva:\s*([^,]+),\s*([^\s\.]+)/i,
                                /Naemingatimatalva:\s*([^,]+),\s*([^\s\.]+)/i,
                                /N[æae]mingat[ií]matalva:\s*([^,]+),\s*([^\s\.]+)/i
                            ];
                            
                            for (const pattern of patterns) {
                                const match = text.match(pattern);
                                if (match) {
                                    return {
                                        student_name: match[1].trim(),
                                        class: match[2].trim()
                                    };
                                }
                            }
                        }
                    }
                }
                return null;
            }''')
            
            if student_info:
                logger.info(f"Found student info in page element: {student_info['student_name']}, {student_info['class']}")
                # --- Step 3: Save extracted data to JSON ---
                if not student_id: # Fetch ID if we didn't get it from the file
                    student_id = await get_student_id(page)

                if student_id:
                    save_data = {
                        "id": student_id,
                        "name": student_info["student_name"],
                        "class": student_info["class"]
                    }
                    try:
                        with open(STUDENT_ID_FILE, 'w', encoding='utf-8') as f:
                            json.dump(save_data, f, indent=4)
                        logger.info(f"Successfully extracted and saved student info to {STUDENT_ID_FILE}")
                    except IOError as e:
                        logger.error(f"Failed to save extracted student info to {STUDENT_ID_FILE}: {e}")
                else:
                    logger.warning("Extracted student name/class but could not get student ID to save.")

                return student_info
        except Exception as e:
            logger.error(f"Error during extraction attempt: {e}")

    # --- Step 4: Fail hard if both methods failed ---
    logger.critical("Fatal: Could not determine student name and class from student-id.json or page extraction. Exiting.")
    raise ValueError("Missing critical student information (name/class).")

async def extract_timetable_data(page, teacher_map, use_models=True):
    """
    Extract timetable data from the page using BeautifulSoup parsing.
    
    Args:
        page: The Playwright page object.
        teacher_map: A dictionary mapping teacher initials to full names.
        use_models: Whether to return Pydantic models (default: True)
        
    Returns:
        tuple: A tuple containing (timetable_data_dict, week_info, homework_lesson_ids)
               where homework_lesson_ids is a list of lesson IDs that have homework icons
    """
    logger.info("Extracting timetable data...")
    
    # Get HTML content from the page
    html_content = await page.content()
    
    # Use BeautifulSoup to parse the HTML with lxml for better performance
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Get the current year
    current_year = datetime.now().year
    
    # Find the timetable table
    table = soup.find('table', class_='time_8_16')
    if not table:
        raise Exception("Timetable table not found")

    tbody = table.find('tbody')
    if not tbody:
        logger.info("Error: Could not find tbody within the table.")
        return None, None, []

    # Extract date range directly from the HTML
    # Look for the date range pattern like "24.03.2025 - 30.03.2025"
    date_range_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})')
    date_range_text = None
    
    # First try to find it near the table
    table_parent = table.parent
    if table_parent:
        parent_text = table_parent.get_text()
        date_range_match = date_range_pattern.search(parent_text)
        if date_range_match:
            date_range_text = date_range_match.group(0)
            logger.info(f"Found date range in table parent: {date_range_text}")

    # If not found, search in the whole document
    if not date_range_text:
        # Try to find it in any element preceding the timetable
        for element in soup.find_all(['p', 'div', 'span', 'br']):
            if element.get_text():
                date_range_match = date_range_pattern.search(element.get_text())
                if date_range_match:
                    date_range_text = date_range_match.group(0)
                    logger.info(f"Found date range in document: {date_range_text}")
                    break
    
    # Extract start and end dates if we found the range
    parsed_start_date = None
    parsed_end_date = None
    if date_range_text:
        date_parts = date_range_text.split('-')
        if len(date_parts) == 2:
            start_date_str = date_parts[0].strip()
            end_date_str = date_parts[1].strip()
            
            # Parse these dates into datetime objects
            try:
                parsed_start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
                parsed_end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
                logger.info(f"Parsed dates: start={parsed_start_date}, end={parsed_end_date}")
            except ValueError as e:
                logger.error(f"Failed to parse date range: {e}")
    
    # New structure: {"studentInfo": {...}, "events": [...]}
    timetable_data = {}
    all_events = []

    current_day_name_fo = None
    current_date_part = None
    first_date_obj = None

    # If we successfully parsed the date range, use the start date for first_date_obj
    if parsed_start_date:
        first_date_obj = parsed_start_date
        logger.info(f"Using extracted start date for week calculation: {first_date_obj}")

    rows = tbody.find_all('tr', recursive=False)

    # Collection for lesson IDs with homework notes
    homework_lesson_ids = []
    lesson_id_to_details = {}  # Map to find lesson details by ID

    for row in rows:
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue # Skip header rows or unexpected rows

        first_cell = cells[0]
        first_cell_text = first_cell.get_text(separator=' ').strip()
        day_match = re.match(r"(\w+)\s+(\d+/\d+)", first_cell_text) # Match "DayName DD/MM"

        is_day_header = 'lektionslinje_1' in first_cell.get('class', []) or \
                        'lektionslinje_1_aktuel' in first_cell.get('class', [])

        if is_day_header and day_match:
            current_day_name_fo = day_match.group(1)
            current_date_part = day_match.group(2)
            
            # Try to capture the first date for week calculation
            if first_date_obj is None:
                try:
                    day, month = map(int, current_date_part.split('/'))
                    first_date_obj = datetime(current_year, month, day)
                except ValueError:
                    pass # Ignore if date format is wrong

        elif is_day_header and not first_cell_text:
            # Handle continuation rows (like second row for Friday)
            # Keep using the previous day name and date
            if current_day_name_fo is None:
                continue # Skip if we haven't identified a day yet

        elif not is_day_header:
             # Skip rows that are not day headers/continuations or lesson rows (e.g., 'mellem')
             if not any('lektionslinje_lesson' in c.get('class', '') for c in cells):
                 continue

        # Process cells in the current row for lessons
        current_col_index = 0
        day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo) # Get English name again

        for cell in cells:
            colspan = 1
            try:
                colspan = int(cell.get('colspan', 1))
            except ValueError:
                pass # Keep colspan = 1 if invalid

            cell_classes = cell.get('class', [])

            # Check if it's a lesson cell
            is_lesson = any(cls.startswith('lektionslinje_lesson') for cls in cell_classes)
            
            # Check if lesson is cancelled
            is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in cell_classes)

            if is_lesson and current_day_name_fo: # Ensure we have context of the day
                a_tags = cell.find_all('a')
                if len(a_tags) >= 3: # Expecting 3 links: class, teacher, room
                    class_code_raw = a_tags[0].get_text(strip=True)
                    teacher_initials = a_tags[1].get_text(strip=True)
                    room_raw = a_tags[2].get_text(strip=True)

                    # Parse class code (e.g., evf-A-33-2425-22y)
                    code_parts = class_code_raw.split('-')
                    
                    # Special handling for exam schedules (Várroynd)
                    if code_parts and code_parts[0] == "Várroynd":
                        # For exam schedule format: Várroynd-før-A-33-2425
                        subject_code = f"{code_parts[0]}-{code_parts[1]}" if len(code_parts) > 1 else code_parts[0]
                        level = code_parts[2] if len(code_parts) > 2 else ""
                        year_code = code_parts[4] if len(code_parts) > 4 else ""
                    else:
                        # Regular class format: evf-A-33-2425-22y
                        subject_code = code_parts[0] if len(code_parts) > 0 else "N/A"
                        level = code_parts[1] if len(code_parts) > 1 else ""
                        year_code = code_parts[3] if len(code_parts) > 3 else ""
                    
                    # Get full teacher name from the dynamically extracted teacher map
                    teacher_full = teacher_map.get(teacher_initials, teacher_initials)
                    
                    # Extract just the room number/location
                    location = room_raw.replace('st.', '').strip()
                    
                    # Handle full-day classes (large colspan values)
                    if colspan >= 90:  # If spanning most of the day (e.g., 96 columns)
                        # Create a special entry indicating it's a full-day event
                        time_info = {
                            "slot": "All day",
                            "time": "08:10-15:25"  # Span from first to last slot
                        }
                    else:
                        # Get time slot info for regular classes
                        time_info = get_timeslot_info(current_col_index)
                    
                    # Format academic year
                    academic_year = format_academic_year(year_code)

                    # Include the year in the date format, using year from first_date_obj
                    date_with_year = f"{current_date_part}-{first_date_obj.year if first_date_obj else datetime.now().year}"
                    
                    # Format as ISO 8601
                    iso_date = format_iso_date(date_with_year, first_date_obj.year if first_date_obj else datetime.now().year)
                    
                    # Parse time range into start and end times
                    start_time, end_time = parse_time_range(time_info["time"])

                    # Create event object with camelCase keys
                    lesson_details = {
                        "title": subject_code,
                        "level": level,
                        "year": academic_year,
                        "date": iso_date,
                        "day": day_en,
                        "teacher": teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full,
                        "teacherShort": teacher_initials,
                        "location": location,
                        "timeSlot": time_info["slot"],
                        "startTime": start_time,
                        "endTime": end_time,
                        "timeRange": time_info["time"],
                        "cancelled": is_cancelled
                    }
                    
                    # Check for homework speech bubble
                    note_img = cell.find('input', {'type': 'image', 'src': re.compile(r'note\.gif')})
                    if note_img:
                        # Extract the lesson ID from the onclick attribute
                        onclick_attr = note_img.get('onclick', '')
                        lesson_id_match = re.search(r"'([A-F0-9-]+)&", onclick_attr)
                        
                        if lesson_id_match:
                            lesson_id = lesson_id_match.group(1)
                            
                            # Store the lesson ID for later API-based homework fetching
                            homework_lesson_ids.append(lesson_id)
                            lesson_details["lessonId"] = lesson_id
                            logger.debug(f"Found homework note for {subject_code} (ID: {lesson_id}{'- cancelled' if is_cancelled else ''})")
                            
                            # Store mapping for later homework assignment
                            lesson_id_to_details[lesson_id] = lesson_details
                    
                    # Add exam-specific details if this is an exam
                    if code_parts and code_parts[0] == "Várroynd" and len(code_parts) > 2:
                        lesson_details["examSubject"] = code_parts[1]
                        lesson_details["examLevel"] = code_parts[2] if len(code_parts) > 2 else ""
                        lesson_details["examType"] = "Spring Exam"

                    # Add event to the flattened structure
                    all_events.append(lesson_details)

            # Update column index for the next cell
            current_col_index += colspan
    
    # Sort the all_events list by date and time
    all_events.sort(key=lambda x: (x["date"], x.get("timeSlot", ""), x.get("startTime", "")))

    # Calculate week information
    week_info = {}
    if parsed_start_date and parsed_end_date:
        # Use the extracted dates directly
        # Calculate week number from the start date
        week_num = parsed_start_date.isocalendar()[1]
        
        # Format dates for the output
        start_date_str = f"{parsed_start_date.year}.{parsed_start_date.month:02d}.{parsed_start_date.day:02d}"
        end_date_str = f"{parsed_end_date.year}.{parsed_end_date.month:02d}.{parsed_end_date.day:02d}"
        
        # Create week key in the correct format for the JSON
        week_key = f"Week {week_num}: {parsed_start_date.year}.{parsed_start_date.month:02d}.{parsed_start_date.day:02d} to {parsed_end_date.year}.{parsed_end_date.month:02d}.{parsed_end_date.day:02d}"
        
        week_info = {
            "year": parsed_start_date.year,
            "week_num": week_num,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "week_key": week_key
        }
        logger.info(f"Using extracted week info: {week_info}")
    elif first_date_obj:
        # Use calculated date information
        # Calculate week number
        week_num = first_date_obj.isocalendar()[1]
        
        # Calculate start and end of week
        start_of_week = first_date_obj - timedelta(days=first_date_obj.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        # Format start and end dates in the same way as the filename
        # Use MM.DD format instead of DD/MM to avoid issues with path separators
        start_date_str = f"{start_of_week.year}.{start_of_week.month:02d}.{start_of_week.day:02d}"
        end_date_str = f"{end_of_week.year}.{end_of_week.month:02d}.{end_of_week.day:02d}"
        
        # Create week key using the consistent format that matches filenames
        week_key = f"Week {week_num}: {start_of_week.year}.{start_of_week.month:02d}.{start_of_week.day:02d} to {end_of_week.year}.{end_of_week.month:02d}.{end_of_week.day:02d}"
        
        week_info = {
            "year": first_date_obj.year,
            "week_num": week_num,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "week_key": week_key
        }
        logger.info(f"Using calculated week info: {week_info}")
    else:
        # Use current date when no date information is available
        now = datetime.now()
        week_num = now.isocalendar()[1]
        
        # Calculate start and end of week
        start_of_week = now - timedelta(days=now.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        # Create consistent week key format with correct formatting
        week_key = f"Week {week_num}: {start_of_week.year}.{start_of_week.month:02d}.{start_of_week.day:02d} to {end_of_week.year}.{end_of_week.month:02d}.{end_of_week.day:02d}"
        
        # Format dates for the output
        start_date_str = f"{start_of_week.year}.{start_of_week.month:02d}.{start_of_week.day:02d}"
        end_date_str = f"{end_of_week.year}.{end_of_week.month:02d}.{end_of_week.day:02d}"
        
        week_info = {
            "year": now.year,
            "week_num": week_num,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "week_key": week_key
        }
        logger.warning(f"Using default week info (no dates found): {week_info}")

    # Extract student information from the page
    student_info = await extract_student_info(page)
    
    # Convert student_info keys to camelCase
    student_info = {
        "studentName": student_info.get("student_name"),
        "class": student_info.get("class")
    }
    
    # Create the final timetable data structure
    timetable_data_dict = {
        "studentInfo": student_info,
        "events": all_events,
        "weekInfo": {
            "weekNumber": week_info.get("week_num"),
            "year": week_info.get("year"),
            "startDate": week_info.get("start_date"),
            "endDate": week_info.get("end_date"),
            "weekKey": week_info.get("week_key")
        },
        "formatVersion": 2
    }
    
    # Log summary of extraction
    logger.info(f"Extracted {len(all_events)} events and found {len(homework_lesson_ids)} events with homework")
    
    # Return the timetable dictionary, week info, and the list of lesson IDs with homework
    return timetable_data_dict, week_info, homework_lesson_ids

async def get_week_info(page):
    """
    Try multiple strategies to get the week information from the page.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        str: The week information.
    """
    
    # Strategy 1: Try to find an H1 element
    try:
        week = await page.evaluate('() => { const h1 = document.querySelector("h1"); return h1 ? h1.textContent.trim() : null; }')
        if week and " - " in week:
            return week.split(" - ")[0]
    except Exception as e:
        logger.info(f"Could not find week in H1: {e}")
    
    # Strategy 2: Look for any element that might contain the week dates
    try:
        week_pattern = r'\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}'
        week_element = await page.evaluate(f'''() => {{
            const nodeIterator = document.createNodeIterator(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while (node = nodeIterator.nextNode()) {{
                const match = node.textContent.match(/{week_pattern}/);
                if (match) return match[0];
            }}
            return null;
        }}''')
        
        if week_element:
            return week_element
    except Exception as e:
        logger.info(f"Could not find week with pattern: {e}")
    
    # Strategy 3: Extract from URL or page title
    try:
        title = await page.title()
        if title and " - " in title:
            return title.split(" - ")[0]
    except Exception as e:
        logger.info(f"Could not extract week from title: {e}")
    
    # Fallback: Use current date and construct a week range
    now = datetime.now()
    start_of_week = now.strftime("%d.%m.%Y")
    return f"{start_of_week} (current week)" 