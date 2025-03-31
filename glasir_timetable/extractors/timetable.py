#!/usr/bin/env python3
"""
Timetable extraction logic used to extract data from the Glasir timetable page.
"""

import re
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

from glasir_timetable.models import TimetableData, StudentInfo, WeekInfo, Event

async def extract_homework_content(page, lesson_id, subject_code="Unknown"):
    """
    Extract homework content for a specific lesson.
    Uses only JavaScript method without UI-based fallback.
    
    Args:
        page: The Playwright page object.
        lesson_id: The unique ID of the lesson from the speech bubble onclick attribute.
        subject_code: The subject code for better error reporting.
        
    Returns:
        dict: A dictionary with success status, content, and error if any.
    """
    try:
        # Check if the glasirTimetable JavaScript object exists
        js_available = await page.evaluate("typeof window.glasirTimetable === 'object' && typeof window.glasirTimetable.extractHomeworkContent === 'function'")
        
        if not js_available:
            logger.error(f"JavaScript method not available for homework extraction (lesson ID: {lesson_id})")
            from glasir_timetable import add_error, update_stats
            add_error("homework_errors", f"JavaScript method not available for {subject_code}", {
                "lesson_id": lesson_id
            })
            update_stats("homework_failed")
            return {
                "success": False,
                "error": "JavaScript method not available",
                "method": "javascript"
            }
            
        logger.debug(f"Using JavaScript method for homework extraction (lesson ID: {lesson_id})")
        # Call the JavaScript function directly
        homework_content = await page.evaluate(f"glasirTimetable.extractHomeworkContent('{lesson_id}')")
        
        # If content is a string, clean up any HTML tags
        if isinstance(homework_content, str):
            import re
            cleaned_content = re.sub(r'<[^>]*>', '', homework_content)
            cleaned_content = cleaned_content.strip()
            
            # Validate content isn't empty
            if cleaned_content:
                from glasir_timetable import update_stats
                update_stats("homework_success")
                return {
                    "success": True,
                    "content": cleaned_content,
                    "method": "javascript"
                }
            else:
                from glasir_timetable import add_error, update_stats
                add_error("homework_errors", f"Empty homework content for {subject_code}", {
                    "lesson_id": lesson_id,
                    "method": "javascript"
                })
                update_stats("homework_failed")
                return {
                    "success": False,
                    "error": "Empty content",
                    "method": "javascript"
                }
        
        # If we got non-string content, check if it's something we can use
        if homework_content:
            from glasir_timetable import update_stats
            update_stats("homework_success")
            return {
                "success": True,
                "content": str(homework_content),
                "method": "javascript"
            }
            
        # JavaScript method returned no content
        from glasir_timetable import add_error, update_stats
        add_error("homework_errors", f"JavaScript method returned no content for {subject_code}", {
            "lesson_id": lesson_id
        })
        update_stats("homework_failed")
        return {
            "success": False,
            "error": "No content from JavaScript method",
            "method": "javascript"
        }
            
    except Exception as e:
        from glasir_timetable import add_error, update_stats
        add_error("homework_errors", f"Error extracting homework for {subject_code}: {e}", {
            "lesson_id": lesson_id,
            "error": str(e)
        })
        update_stats("homework_failed")
        return {
            "success": False,
            "error": str(e),
            "method": "javascript"
        }

async def extract_student_info(page):
    """
    Extract student name and class from the page title or heading.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        dict: Student information with name and class
    """
    try:
        # Try to find student info in the page title
        title = await page.title()
        # Check for pattern like "Næmingatímatalva: Rókur Kvilt Meitilberg, 22y"
        title_match = re.search(r"Næmingatímatalva:\s*([^,]+),\s*([^\.]+)", title)
        if title_match:
            return {
                "student_name": title_match.group(1).strip(),
                "class": title_match.group(2).strip()
            }
        
        # Try to find it in a heading element
        student_info = await page.evaluate('''() => {
            // Check various headings
            for (const selector of ['h1', 'h2', 'h3', '.user-info', '.student-info']) {
                const element = document.querySelector(selector);
                if (element) {
                    const text = element.textContent;
                    const match = text.match(/Næmingatímatalva:\s*([^,]+),\s*([^\.]+)/);
                    if (match) {
                        return {
                            student_name: match[1].trim(),
                            class: match[2].trim()
                        };
                    }
                }
            }
            return null;
        }''')
        
        if student_info:
            return student_info
    except Exception as e:
        logger.error(f"Error extracting student info: {e}")
    
    # Default to constants as fallback
    logger.info("Using default student info from constants")
    return {
        "student_name": "Rókur Kvilt Meitilberg",
        "class": "22y"
    }

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