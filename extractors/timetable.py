#!/usr/bin/env python3
"""
Module for extracting timetable data from the Glasir website.
"""
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from glasir_timetable.constants import DAY_NAME_MAPPING, DAYS_ORDER, CANCELLED_CLASS_INDICATORS
from glasir_timetable.utils.formatting import format_academic_year, get_timeslot_info

async def extract_homework_content(page, lesson_id):
    """
    Extract homework content for a specific lesson by clicking its speech bubble.
    
    Args:
        page: The Playwright page object.
        lesson_id: The unique ID of the lesson from the speech bubble onclick attribute.
        
    Returns:
        str: The extracted homework content, or None if no content was found.
    """
    try:
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
            
            # Debug output if no content was found
            if not homework_content:
                print(f"Could not extract homework content for lesson {lesson_id}")
            
            return homework_content
    except Exception as e:
        print(f"Error extracting homework for lesson {lesson_id}: {e}")
    
    return None

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
        print(f"Error extracting student info: {e}")
    
    # Default to constants as fallback
    print("Using default student info from constants")
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
    print("Extracting timetable data...")
    
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
        print("Error: Could not find tbody within the table.")
        return None

    # New structure: {"Week X: start to end": {"Day": [classes]}}
    timetable_data = {}
    day_classes = {}
    
    current_day_name_fo = None
    current_date_part = None
    first_date_obj = None

    rows = tbody.find_all('tr', recursive=False)

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

                    lesson_details = {
                        "name": subject_code,
                        "level": level,
                        "Year": academic_year,
                        "date": date_with_year,
                        "Teacher": teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full,
                        "Teacher short": teacher_initials,
                        "Location": location,
                        "Time slot": time_info["slot"],
                        "Time": time_info["time"],
                        "Cancelled": is_cancelled
                    }
                    
                    # Check for homework speech bubble
                    note_img = cell.find('input', {'type': 'image', 'src': re.compile(r'note\.gif')})
                    if note_img:
                        # Extract the lesson ID from the onclick attribute
                        onclick_attr = note_img.get('onclick', '')
                        lesson_id_match = re.search(r"'([A-F0-9-]+)&", onclick_attr)
                        
                        if lesson_id_match:
                            lesson_id = lesson_id_match.group(1)
                            
                            # Extract homework content by clicking the speech bubble
                            print(f"Extracting homework for {subject_code} (ID: {lesson_id}{'- cancelled' if is_cancelled else ''})")
                            homework_content = await extract_homework_content(page, lesson_id)
                            
                            if homework_content:
                                # Clean up the homework content (remove HTML tags if any)
                                if isinstance(homework_content, str):
                                    # Remove any HTML tags that might be in the content
                                    cleaned_content = re.sub(r'<[^>]*>', '', homework_content)
                                    lesson_details["Homework"] = cleaned_content.strip()
                                    print(f"Assigned homework for {subject_code}: {cleaned_content.strip()}")
                                else:
                                    lesson_details["Homework"] = homework_content
                                    print(f"Assigned homework for {subject_code}: {homework_content}")
                            else:
                                # If no homework was found, try one more time with a longer wait
                                await page.wait_for_timeout(500)  # Increased waiting time
                                homework_content = await extract_homework_content(page, lesson_id)
                                if homework_content:
                                    # Clean up the homework content (remove HTML tags if any)
                                    if isinstance(homework_content, str):
                                        # Remove any HTML tags that might be in the content
                                        cleaned_content = re.sub(r'<[^>]*>', '', homework_content)
                                        lesson_details["Homework"] = cleaned_content.strip()
                                        print(f"Assigned homework for {subject_code} (retry): {cleaned_content.strip()}")
                                    else:
                                        lesson_details["Homework"] = homework_content
                                        print(f"Assigned homework for {subject_code} (retry): {homework_content}")
                                else:
                                    print(f"No homework found for {subject_code} after retry")

                    # Add exam-specific details if this is an exam
                    if code_parts and code_parts[0] == "Várroynd" and len(code_parts) > 2:
                        lesson_details["exam_subject"] = code_parts[1]
                        lesson_details["exam_level"] = code_parts[2] if len(code_parts) > 2 else ""
                        lesson_details["exam_type"] = "Spring Exam"

                    # Special handling for making sure class entries are unique
                    if day_en in day_classes:
                        # Check if this exact class already exists in the list
                        duplicate_found = False
                        for existing_class in day_classes[day_en]:
                            if (existing_class["name"] == lesson_details["name"] and
                                existing_class["Time slot"] == lesson_details["Time slot"] and
                                existing_class["Teacher short"] == lesson_details["Teacher short"]):
                                
                                # If duplicate found, make sure homework is preserved
                                if "Homework" in lesson_details and "Homework" not in existing_class:
                                    existing_class["Homework"] = lesson_details["Homework"]
                                    print(f"Added homework to existing class: {subject_code}")
                                    duplicate_found = True
                                    break
                                # If duplicate already has homework, keep it
                                elif "Homework" in lesson_details and "Homework" in existing_class:
                                    duplicate_found = True
                                    break
                        
                        # Only add the class if it's not a duplicate or has unique information
                        if not duplicate_found:
                            day_classes[day_en].append(lesson_details)

            # Update column index for the next cell
            current_col_index += colspan

    # Sort classes for each day by time slot and prioritize uncancelled classes
    for day, classes in day_classes.items():
        # First, create a dictionary to group classes by time slot
        time_slot_groups = {}
        for class_info in classes:
            time_slot = class_info["Time slot"]
            if time_slot not in time_slot_groups:
                time_slot_groups[time_slot] = []
            time_slot_groups[time_slot].append(class_info)
        
        # Sort each time slot group, putting uncancelled classes first
        for time_slot, slot_classes in time_slot_groups.items():
            time_slot_groups[time_slot] = sorted(slot_classes, key=lambda x: x["Cancelled"])
        
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

    # Calculate week information
    week_info = {}
    if first_date_obj:
        # Calculate week number
        week_num = first_date_obj.isocalendar()[1]
        
        # Calculate start and end of week
        start_of_week = first_date_obj - timedelta(days=first_date_obj.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        week_key = f"Week {week_num}: {start_of_week.strftime('%Y-%m-%d')} to {end_of_week.strftime('%Y-%m-%d')}"
        
        week_info = {
            "year": first_date_obj.year,
            "week_num": week_num,
            "start_date": start_of_week.strftime("%Y-%m-%d"),
            "end_date": end_of_week.strftime("%Y-%m-%d"),
            "week_key": week_key
        }
    else:
        # Default week info if date parsing fails
        now = datetime.now()
        week_num = now.isocalendar()[1]
        week_key = f"Week {week_num}: Unknown Dates"
        
        week_info = {
            "year": now.year,
            "week_num": week_num,
            "start_date": "unknown",
            "end_date": "unknown",
            "week_key": week_key
        }
    
    # Ensure all days exist in the output
    for day in DAYS_ORDER:
        if day not in day_classes:
            day_classes[day] = []
    
    # Extract student information from the page
    student_info = await extract_student_info(page)
    
    # Create the final structure with the week key and student info
    timetable_data = {
        week_info["week_key"]: day_classes,
        "student_info": student_info
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
        print(f"Could not find week in H1: {e}")
    
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
        print(f"Could not find week with pattern: {e}")
    
    # Strategy 3: Extract from URL or page title
    try:
        title = await page.title()
        if title and " - " in title:
            return title.split(" - ")[0]
    except Exception as e:
        print(f"Could not extract week from title: {e}")
    
    # Fallback: Use current date and construct a week range
    now = datetime.now()
    start_of_week = now.strftime("%d.%m.%Y")
    return f"{start_of_week} (current week)" 