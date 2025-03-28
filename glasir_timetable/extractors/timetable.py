#!/usr/bin/env python3
"""
Timetable data extraction module.
"""
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta
from glasir_timetable import logger
from bs4 import BeautifulSoup

from glasir_timetable.constants import (
    BLOCK_TIMES, 
    DAY_NAME_MAPPING, 
    SUBJECT_CODE_MAPPING,
    ROOM_FORMAT_MAPPING,
    DAYS_ORDER,
    CANCELLED_CLASS_INDICATORS
)
from glasir_timetable.utils.formatting import (
    format_academic_year, 
    get_timeslot_info, 
    convert_keys_to_camel_case,
    format_iso_date,
    parse_time_range
)

async def extract_homework_content(page, lesson_id, subject_code="Unknown"):
    """
    Extract homework content for a specific lesson.
    Prioritizes using JavaScript method over UI-based clicking.
    
    Args:
        page: The Playwright page object.
        lesson_id: The unique ID of the lesson from the speech bubble onclick attribute.
        subject_code: The subject code for better error reporting.
        
    Returns:
        dict: A dictionary with success status, content, and error if any.
    """
    try:
        # Always try JavaScript method first
        try:
            # Check if the glasirTimetable JavaScript object exists
            js_available = await page.evaluate("typeof window.glasirTimetable === 'object' && typeof window.glasirTimetable.extractHomeworkContent === 'function'")
            
            if js_available:
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
                
                # If JS method returned null, only fall back to UI method if explicitly instructed
                # Check if we should use UI fallback (only if JavaScript is not enforced)
                use_ui_fallback = await page.evaluate("window.glasirTimetable.useUIFallback !== false")
                if not use_ui_fallback:
                    from glasir_timetable import add_error, update_stats
                    add_error("homework_errors", f"JavaScript method returned no content for {subject_code}", {
                        "lesson_id": lesson_id
                    })
                    update_stats("homework_failed")
                    return {
                        "success": False,
                        "error": "No content from JavaScript method, UI fallback disabled",
                        "method": "javascript"
                    }
            
        except Exception as js_error:
            # Check if we should use UI fallback
            try:
                use_ui_fallback = await page.evaluate("window.glasirTimetable.useUIFallback !== false")
                if not use_ui_fallback:
                    from glasir_timetable import add_error, update_stats
                    add_error("homework_errors", f"JavaScript homework extraction failed for {subject_code}: {js_error}", {
                        "lesson_id": lesson_id,
                        "error": str(js_error)
                    })
                    update_stats("homework_failed")
                    return {
                        "success": False,
                        "error": f"JavaScript extraction error: {js_error}",
                        "method": "javascript"
                    }
            except:
                pass
        
        # Fall back to UI method
        # Find the speech bubble by its specific window ID
        selector = f'input[type="image"][src*="note.gif"][onclick*="{lesson_id}"]'
        
        # Check if the speech bubble exists
        if await page.query_selector(selector):
            # First, clear any previous homework popup by clicking elsewhere 
            await page.click('body', position={"x": 1, "y": 1})
            await page.wait_for_timeout(300)
            
            # Now click the speech bubble for this specific class
            await page.click(selector)
            
            # Wait for the content to load - increased timeout
            await page.wait_for_timeout(1000)

            # Use the window ID to specifically target this popup's content
            homework_content = await page.evaluate(f'''(lessonId) => {{
                // Look for the specific window containing this lesson's homework
                const windowId = `MyWindow${{lessonId}}Main`;
                const specificWindow = document.getElementById(windowId);
                
                if (specificWindow) {{
                    // Method 1: Parse the paragraph with HTML structure
                    const paragraphs = specificWindow.querySelectorAll('p');
                    for (const para of paragraphs) {{
                        if (para.innerHTML && para.innerHTML.includes('<b>Heimaarbeiði</b>')) {{
                            // Extract content after the <br> tag
                            const parts = para.innerHTML.split('<br>');
                            if (parts.length > 1) {{
                                // Get everything after the first <br>
                                return parts.slice(1).join('<br>').trim();
                            }}
                        }}
                    }}
                    
                    // Method 2: Direct text extraction
                    const allText = [];
                    const walk = document.createTreeWalker(
                        specificWindow, 
                        NodeFilter.SHOW_TEXT, 
                        null, 
                        false
                    );
                    
                    let foundHeimalabel = false;
                    
                    while(walk.nextNode()) {{
                        const text = walk.currentNode.textContent.trim();
                        if (text) {{
                            allText.push(text);
                            
                            // Case 1: Text node is exactly "Heimaarbeiði"
                            if (text === "Heimaarbeiði") {{
                                foundHeimalabel = true;
                            }} 
                            // Case 2: We previously found the label, this is the content
                            else if (foundHeimalabel) {{
                                return text;
                            }}
                            // Case 3: Text contains "Heimaarbeiði" and more content
                            else if (text.includes('Heimaarbeiði')) {{
                                return text.substring(text.indexOf('Heimaarbeiði') + 'Heimaarbeiði'.length).trim();
                            }}
                        }}
                    }}
                    
                    // If we get here and have collected text, check if we missed anything
                    if (allText.length > 1 && allText[0] === "Heimaarbeiði") {{
                        return allText[1];
                    }}
                    
                    // Method 3: Try getting the innerHTML of the entire window as last resort
                    if (allText.length === 0) {{
                        const html = specificWindow.innerHTML;
                        if (html.includes('<b>Heimaarbeiði</b><br>')) {{
                            const content = html.split('<b>Heimaarbeiði</b><br>')[1];
                            if (content) {{
                                // Extract up to the next tag
                                const endMatch = content.match(/<\\/(p|div|span)>/);
                                if (endMatch) {{
                                    return content.substring(0, endMatch.index).trim();
                                }}
                                return content.split('<')[0].trim();
                            }}
                        }}
                    }}
                }}
                
                return null;
            }}''', lesson_id)
            
            # Close the popup by clicking elsewhere
            await page.click('body', position={"x": 1, "y": 1})
            
            # Check if we got valid content
            if homework_content and isinstance(homework_content, str) and homework_content.strip():
                from glasir_timetable import update_stats
                update_stats("homework_success")
                return {
                    "success": True,
                    "content": homework_content.strip(),
                    "method": "ui"
                }
            else:
                from glasir_timetable import add_error, update_stats
                add_error("homework_errors", f"UI method returned empty content for {subject_code}", {
                    "lesson_id": lesson_id
                })
                update_stats("homework_failed")
                return {
                    "success": False,
                    "error": "Empty content from UI method",
                    "method": "ui"
                }
        else:
            from glasir_timetable import add_error, update_stats
            add_error("homework_errors", f"No speech bubble found for {subject_code}", {
                "lesson_id": lesson_id
            })
            update_stats("homework_failed")
            return {
                "success": False,
                "error": "Speech bubble not found",
                "method": "ui"
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
            "method": "unknown"
        }
    
    # This should never be reached, but just in case
    from glasir_timetable import add_error, update_stats
    add_error("homework_errors", f"Unknown error in homework extraction for {subject_code}", {
        "lesson_id": lesson_id
    })
    update_stats("homework_failed")
    return {
        "success": False,
        "error": "Unknown extraction error",
        "method": "unknown"
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

async def extract_timetable_data(page, teacher_map):
    """
    Extract timetable data from the page using BeautifulSoup parsing.
    
    Args:
        page: The Playwright page object.
        teacher_map: A dictionary mapping teacher initials to full names.
        
    Returns:
        tuple: A tuple containing timetable data and week information.
    """
    logger.info("Extracting timetable data...")
    
    # Get HTML content from the page
    html_content = await page.content()
    
    # Use BeautifulSoup to parse the HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Get the current year
    current_year = datetime.now().year
    
    # Find the timetable table
    table = soup.find('table', class_='time_8_16')
    if not table:
        raise Exception("Timetable table not found")

    tbody = table.find('tbody')
    if not tbody:
        logger.info("Error: Could not find tbody within the table.")
        return None

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
    day_classes = {}
    all_events = []
    
    current_day_name_fo = None
    current_date_part = None
    first_date_obj = None

    # If we successfully parsed the date range, use the start date for first_date_obj
    if parsed_start_date:
        first_date_obj = parsed_start_date
        logger.info(f"Using extracted start date for week calculation: {first_date_obj}")

    rows = tbody.find_all('tr', recursive=False)
    
    # New: collect all lesson IDs with notes for parallel extraction
    all_note_lessons = []
    lesson_id_to_details = {}  # Map to find lesson details by ID
    lesson_id_to_classes = {}  # Map to know which day and class index to update

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
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo)
            
            if day_en not in day_classes:
                day_classes[day_en] = []

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
                            
                            # Store for parallel processing instead of extracting now
                            all_note_lessons.append((lesson_id, subject_code))
                            logger.debug(f"Found homework note for {subject_code} (ID: {lesson_id}{'- cancelled' if is_cancelled else ''})")
                    
                    # Add exam-specific details if this is an exam
                    if code_parts and code_parts[0] == "Várroynd" and len(code_parts) > 2:
                        lesson_details["examSubject"] = code_parts[1]
                        lesson_details["examLevel"] = code_parts[2] if len(code_parts) > 2 else ""
                        lesson_details["examType"] = "Spring Exam"

                    # Store event in both old structure (day_classes) and new flattened structure (all_events)
                    # Special handling for making sure class entries are unique
                    if day_en in day_classes:
                        # Check if this exact class already exists in the list
                        duplicate_found = False
                        for i, existing_class in enumerate(day_classes[day_en]):
                            if (existing_class["title"] == lesson_details["title"] and
                                existing_class["timeSlot"] == lesson_details["timeSlot"] and
                                existing_class["teacherShort"] == lesson_details["teacherShort"]):
                                
                                # If it has a note, store the mapping for later
                                if note_img and lesson_id_match:
                                    # For parallel homework processing
                                    lesson_id = lesson_id_match.group(1)
                                    lesson_id_to_details[lesson_id] = existing_class
                                    lesson_id_to_classes[lesson_id] = (day_en, i)
                                
                                duplicate_found = True
                                break
                        
                        # Only add the class if it's not a duplicate
                        if not duplicate_found:
                            class_index = len(day_classes[day_en])
                            day_classes[day_en].append(lesson_details)
                            all_events.append(lesson_details)  # Add to flattened structure
                            
                            # If it has a note, store the mapping for later
                            if note_img and lesson_id_match:
                                # For parallel homework processing
                                lesson_id = lesson_id_match.group(1)
                                lesson_id_to_details[lesson_id] = lesson_details
                                lesson_id_to_classes[lesson_id] = (day_en, class_index)
                    else:
                        # First class for this day
                        day_classes[day_en] = [lesson_details]
                        all_events.append(lesson_details)  # Add to flattened structure
                        
                        # If it has a note, store the mapping for later
                        if note_img and lesson_id_match:
                            # For parallel homework processing
                            lesson_id = lesson_id_match.group(1)
                            lesson_id_to_details[lesson_id] = lesson_details
                            lesson_id_to_classes[lesson_id] = (day_en, 0)

            # Update column index for the next cell
            current_col_index += colspan
            
    # Now process all note lessons in parallel if JavaScript is available
    if all_note_lessons:
        from tqdm import tqdm
        import time
        from glasir_timetable import update_stats

        logger.info(f"Processing {len(all_note_lessons)} homework assignments")
        
        # MODIFIED: Skip the JavaScript-based extraction and go straight to sequential
        logger.info("Using sequential homework extraction")
        homework_count = 0
        
        # Create a progress bar for homework extraction
        with tqdm(total=len(all_note_lessons), desc="Extracting homework", unit="notes",
                 bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                 dynamic_ncols=True, position=1, leave=False) as pbar:
            start_time = time.time()
            
            for lesson_id, subject_code in all_note_lessons:
                lesson_details = lesson_id_to_details.get(lesson_id)
                if lesson_details:
                    # Extract homework content by clicking the speech bubble
                    result = await extract_homework_content(page, lesson_id, subject_code)
                    
                    if result["success"]:
                        lesson_details["description"] = result["content"]  # Use description instead of Homework
                        homework_count += 1
                        pbar.set_description(f"Homework: {subject_code} (success)")
                    else:
                        pbar.set_description(f"Homework: {subject_code} (failed)")
                    
                    # Update progress
                    pbar.update(1)
                    
                    # Calculate and display statistics
                    elapsed = time.time() - start_time
                    items_per_min = 60 * pbar.n / elapsed if elapsed > 0 else 0
                    pbar.set_postfix({"success": homework_count, "rate": f"{items_per_min:.1f}/min"})
        
        logger.info(f"Successfully assigned {homework_count} homework entries using sequential extraction")

    # Sort classes for each day by time slot and prioritize uncancelled classes
    for day, classes in day_classes.items():
        # First, create a dictionary to group classes by time slot
        time_slot_groups = {}
        for class_info in classes:
            time_slot = class_info["timeSlot"]
            if time_slot not in time_slot_groups:
                time_slot_groups[time_slot] = []
            time_slot_groups[time_slot].append(class_info)
        
        # Sort each time slot group, putting uncancelled classes first
        for time_slot, slot_classes in time_slot_groups.items():
            time_slot_groups[time_slot] = sorted(slot_classes, key=lambda x: x["cancelled"])
        
        # Special handling for sorting - put "All day" events first
        sorted_time_slots = sorted(time_slot_groups.keys(), 
                                   key=lambda x: (0 if x == "All day" else 
                                                  1 if x.endswith(".") else 2, x))
        
        # Flatten the list with the new sorting
        sorted_classes = []
        for time_slot in sorted_time_slots:
            sorted_classes.extend(time_slot_groups[time_slot])
        
        # Update the day's classes with the sorted list
        day_classes[day] = sorted_classes
    
    # Also sort the all_events list by date and time
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
        # Fallback to the previous method if direct extraction fails
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
        # Default week info if date parsing fails
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

    # Ensure all days exist in the output
    for day in DAYS_ORDER:
        if day not in day_classes:
            day_classes[day] = []
    
    # Extract student information from the page
    student_info = await extract_student_info(page)
    
    # Convert student_info keys to camelCase
    student_info = {
        "studentName": student_info.get("student_name"),
        "class": student_info.get("class")
    }
    
    # Create the event-centric format only (removing traditional format)
    timetable_data = {
        "studentInfo": student_info,
        "events": all_events,
        "weekInfo": week_info,
        # Add a flag to indicate this is the new format
        "formatVersion": 2
    }
    
    return timetable_data, week_info

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