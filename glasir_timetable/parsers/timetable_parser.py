from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Any, Optional
import re
from glasir_timetable.shared import logger
from glasir_timetable.shared.constants import DAY_NAME_MAPPING, CANCELLED_CLASS_INDICATORS
from glasir_timetable.shared.date_utils import to_iso_date # Use date_utils for ISO conversion
from glasir_timetable.shared.formatting import (
    parse_time_range,
    format_academic_year,
    # format_iso_date # Removed, using to_iso_date from date_utils
)

# Compiled regex patterns for performance
_RE_STUDENT_INFO = re.compile(r"N[æ&aelig;]mingatímatalva:\s*([^,]+),\s*([^\s<]+)", re.IGNORECASE)
_RE_DATE_RANGE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})")
_RE_DAY_DATE = re.compile(r"(\w+)\s+(\d{1,2}/\d{1,2})")
_RE_NOTE_ONCLICK_ID = re.compile(r"'([A-F0-9-]+)&")
_RE_NOTE_IMG_SRC = re.compile(r'note\.gif') # Already compiled in usage, but good to have here
def get_timeslot_info(start_col_index):
    """
    Maps the starting column index of a lesson TD to its time slot.
    """
    # Column indices are 0-based in this calculation
    if 2 <= start_col_index <= 25:
        return {"slot": "1", "time": "08:10-09:40"}
    elif 26 <= start_col_index <= 50:
        return {"slot": "2", "time": "10:05-11:35"}
    elif 51 <= start_col_index <= 71:
        return {"slot": "3", "time": "12:10-13:40"}
    elif 72 <= start_col_index <= 90:
        return {"slot": "4", "time": "13:55-15:25"}
    elif 91 <= start_col_index <= 111:
        return {"slot": "5", "time": "15:30-17:00"}
    elif 112 <= start_col_index <= 131:
        return {"slot": "6", "time": "17:15-18:45"}
    else:
        return {"slot": "N/A", "time": "N/A"}  # Fallback


def parse_timetable_html(html: str, teacher_map: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, Any], List[str]]:
    """
    Parse timetable HTML into structured dict and list of lesson IDs with homework.
    Returns:
        timetable_data: dict with student info, week info, events
        homework_lesson_ids: list of lesson IDs with homework icons
    """
    timetable_data = {
        "studentInfo": {},
        "weekInfo": {},
        "events": []
    }
    homework_ids = []
    if teacher_map is None:
        teacher_map = {}

    try:
        # Pre-filtering removed - lxml handles scripts/styles/comments efficiently.
        # html = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # # Remove style blocks
        # html = re.sub(r'<style.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # # Remove HTML comments
        # html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        # Now parse the potentially smaller HTML string
        soup = BeautifulSoup(html, "lxml")

        # Extract student info
        m = _RE_STUDENT_INFO.search(html)
        if m:
            timetable_data["studentInfo"] = {
                "studentName": m.group(1).strip(),
                "class": m.group(2).strip()
            }

        # Extract week number and date range
        week_link = soup.select_one('a.UgeKnapValgt') # Use select_one
        if week_link:
            week_text = week_link.get_text(strip=True)
            if week_text.startswith("Vika "):
                timetable_data["weekInfo"]["weekNumber"] = int(week_text.replace("Vika ", ""))

        # Relaxed day/month regex to handle single digits (e.g., 1.4.2024)
        date_range_match = _RE_DATE_RANGE.search(html)
        if date_range_match:
            start_date_str = date_range_match.group(1)
            end_date_str = date_range_match.group(2)
            # Convert dates to ISO format using the utility function
            timetable_data["weekInfo"]["startDate"] = to_iso_date(start_date_str)
            timetable_data["weekInfo"]["endDate"] = to_iso_date(end_date_str)

        # Parse lessons with day and time info
        table = soup.select_one('table.time_8_16') # Use select_one
        if not table:
            logger.warning("Timetable table not found")
            return timetable_data, homework_ids

        rows = table.select('tr') # Select descendant tr elements
        current_day_name_fo = None
        current_date_part = None
        current_year = None
        first_date_obj = None

        # Try to parse year from the already converted ISO startDate
        start_iso_date = timetable_data.get("weekInfo", {}).get("startDate")
        if start_iso_date:
            try:
                # ISO format is YYYY-MM-DD
                current_year = int(start_iso_date.split("-")[0])
                # Add the extracted year to weekInfo
                timetable_data["weekInfo"]["year"] = current_year
            except (ValueError, IndexError, TypeError):
                 logger.warning(f"Could not parse year from ISO startDate: {start_iso_date}")
                 current_year = None # Fallback if ISO date is somehow invalid
        else:
             current_year = None # No start date found yet

        for row in rows:
            cells = row.select('td') # Select descendant td elements
            if not cells:
                continue

            first_cell = cells[0]
            first_cell_text = first_cell.get_text(separator=' ').strip()
            day_match = _RE_DAY_DATE.match(first_cell_text)

            is_day_header = 'lektionslinje_1' in first_cell.get('class', []) or \
                            'lektionslinje_1_aktuel' in first_cell.get('class', [])

            if is_day_header and day_match:
                current_day_name_fo = day_match.group(1)
                current_date_part = day_match.group(2)
                # Year is determined earlier from weekInfo.startDate
                # No need to parse first_date_obj here anymore.
                pass # Keep current_day_name_fo and current_date_part (DD/MM)
            elif is_day_header:
                # Continuation row, keep previous day/date
                pass

            # Now parse lesson cells
            current_col_index = 0
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo)

            for cell in cells:
                colspan = 1
                try:
                    colspan = int(cell.get('colspan', 1))
                except:
                    pass

                classes = cell.get('class', [])
                is_lesson = any(cls.startswith('lektionslinje_lesson') for cls in classes)
                is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in classes)

                if is_lesson and current_day_name_fo:
                    a_tags = cell.select('a') # Use select
                    if len(a_tags) >= 3:
                        class_code_raw = a_tags[0].get_text(strip=True)
                        teacher_short = a_tags[1].get_text(strip=True)
                        room_raw = a_tags[2].get_text(strip=True)

                        # Parse class code parts
                        code_parts = class_code_raw.split('-')
                        if code_parts and code_parts[0] == "Várroynd":
                            subject_code = f"{code_parts[0]}-{code_parts[1]}" if len(code_parts) > 1 else code_parts[0]
                            level = code_parts[2] if len(code_parts) > 2 else ""
                            year_code = code_parts[4] if len(code_parts) > 4 else ""
                        else:
                            subject_code = code_parts[0] if len(code_parts) > 0 else ""
                            level = code_parts[1] if len(code_parts) > 1 else ""
                            year_code = code_parts[3] if len(code_parts) > 3 else ""

                        teacher_full = teacher_map.get(teacher_short, teacher_short)
                        location = room_raw.replace('st.', '').strip()

                        # Handle full-day events
                        if colspan >= 90:
                            time_info = {
                                "slot": "All day",
                                "time": "08:10-15:25"
                            }
                        else:
                            time_info = get_timeslot_info(current_col_index)

                        # Convert the DD/MM part to ISO date using the determined year
                        iso_date = None
                        if current_date_part and current_year:
                            iso_date = to_iso_date(current_date_part, current_year)
                        elif current_date_part:
                            logger.warning(f"Cannot determine ISO date for '{current_date_part}' - year is missing.")

                        start_time, end_time = parse_time_range(time_info["time"])

                        lesson = {
                            "title": subject_code,
                            "level": level,
                            "year": format_academic_year(year_code),
                            "date": iso_date, # Use the converted ISO date
                            "dayOfWeek": day_en,
                            "teacher": teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full,
                            "teacherShort": teacher_short,
                            "location": location,
                            "timeSlot": time_info["slot"],
                            "startTime": start_time,
                            "endTime": end_time,
                            "timeRange": time_info["time"],
                            "cancelled": is_cancelled
                        }

                        # Check for homework icon
                        # Use select_one with attribute selector (contains 'note.gif')
                        note_img = cell.select_one('input[type="image"][src*="note.gif"]')
                        if note_img:
                            onclick = note_img.get('onclick', '')
                            m = _RE_NOTE_ONCLICK_ID.search(onclick)
                            if m:
                                lesson_id = m.group(1)
                                lesson["lessonId"] = lesson_id
                                homework_ids.append(lesson_id)

                        timetable_data["events"].append(lesson)

                current_col_index += colspan

    except Exception as e:
        logger.error(f"Error parsing timetable HTML: {e}")

    return timetable_data, homework_ids