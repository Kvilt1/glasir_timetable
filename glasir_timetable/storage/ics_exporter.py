"""
ICS Exporter Module for Glasir Timetable

This module provides functionality to export timetable data to a valid .ics (iCalendar) file.
"""

from typing import Union
from pathlib import Path
from datetime import datetime, timedelta
from glasir_timetable.models import TimetableData, Event

def _format_datetime(date_str: str, time_str: str) -> str:
    """
    Format date and time strings to iCalendar datetime format (YYYYMMDDTHHMMSS).
    Assumes local time (floating time).
    """
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return dt.strftime("%Y%m%dT%H%M%S")

def _generate_uid(event: Event) -> str:
    """
    Generate a unique identifier for an event.
    """
    # Use lesson_id if available, else fallback to a hash of key fields
    if event.lesson_id:
        return f"{event.lesson_id}@glasir"
    base = f"{event.date}-{event.start_time}-{event.title}-{event.teacher_short}-{event.location}"
    return f"{abs(hash(base))}@glasir"

def _escape_ics_text(text: str) -> str:
    """
    Escape text for ICS format (commas, semicolons, backslashes, newlines).
    """
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )

def export_to_ics(
    timetable_data: Union[TimetableData, dict],
    output_path: Union[str, Path]
) -> None:
    """
    Export timetable data to a valid .ics (iCalendar) file.

    Args:
        timetable_data (TimetableData | dict): The timetable data to export.
        output_path (str | Path): The file path where the .ics file will be written.

    Raises:
        ValueError: If timetable_data is not a valid TimetableData or dict.
        IOError: If writing to the output file fails.
    """
    if isinstance(timetable_data, dict):
        timetable = TimetableData.model_validate(timetable_data)
    elif isinstance(timetable_data, TimetableData):
        timetable = timetable_data
    else:
        raise ValueError("timetable_data must be a TimetableData instance or a dict.")

    events = timetable.sort_events_by_time()
    student = timetable.student_info

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Glasir Timetable//ICS Exporter//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape_ics_text(student.student_name)} - {student.class_} Timetable",
        "X-WR-TIMEZONE:Europe/Copenhagen",
    ]

    for event in events:
        if event.cancelled:
            continue  # Skip cancelled events

        dtstart = _format_datetime(event.date, event.start_time)
        dtend = _format_datetime(event.date, event.end_time)
        summary = _escape_ics_text(event.title)
        description = _escape_ics_text(
            f"Teacher: {event.teacher} ({event.teacher_short})"
            + (f"\nDescription: {event.description}" if event.description else "")
        )
        location = _escape_ics_text(event.location)
        uid = _generate_uid(event)
        dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            f"CATEGORIES:Lesson",
            "STATUS:CONFIRMED",
            "SEQUENCE:0",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")

    output_path = Path(output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\r\n")
    except Exception as e:
        raise IOError(f"Failed to write ICS file: {e}")