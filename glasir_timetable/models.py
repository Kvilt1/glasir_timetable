#!/usr/bin/env python3
"""
Data models for the Glasir Timetable application.

This module defines Pydantic models for student information, week information,
events (classes/lessons), and the overall timetable data structure.
"""

from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field, model_validator, validator


class StudentInfo(BaseModel):
    """Student information model."""

    student_name: str = Field(..., alias="studentName")
    class_: str = Field(..., alias="class")

    class Config:  # noqa: F811 - Pydantic Config class
        populate_by_name = True
        frozen = True
        json_schema_extra = {"example": {"studentName": "John Doe", "class": "22y"}}


class WeekInfo(BaseModel):
    """Week information model."""

    week_number: int = Field(..., alias="weekNumber")
    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")
    year: int
    week_key: Optional[str] = Field(None, alias="weekKey")

    @validator("start_date", "end_date")
    def validate_date_format(cls, v):  # noqa: F811 - Pydantic validator
        """Validate date is in ISO format (YYYY-MM-DD)."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")

    @validator("week_number")
    def validate_week_number(cls, v):  # noqa: F811 - Pydantic validator
        """Validate week number is within range 1-53."""
        if not 1 <= v <= 53:
            raise ValueError("Week number must be between 1 and 53")
        return v

    @model_validator(mode="after")
    def generate_week_key(self):  # noqa: F811 - Pydantic model validator
        """Generate week_key if not provided."""
        if not self.week_key:
            self.week_key = f"{self.year}-W{self.week_number:02d}"
        return self

    class Config:  # noqa: F811 - Pydantic Config class
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "weekNumber": 13,
                "startDate": "2025-03-24",
                "endDate": "2025-03-30",
                "year": 2025,
                "weekKey": "2025-W13",
            }
        }


class Event(BaseModel):
    """Event (class/lesson) model."""

    title: str
    level: str
    year: str
    date: str
    day: str
    teacher: str
    teacher_short: str = Field(..., alias="teacherShort")
    location: str
    time_slot: Union[int, str] = Field(..., alias="timeSlot")
    start_time: str = Field(..., alias="startTime")
    end_time: str = Field(..., alias="endTime")
    time_range: str = Field(..., alias="timeRange")
    cancelled: bool = False
    lesson_id: Optional[str] = Field(None, alias="lessonId")
    description: Optional[str] = None

    @validator("date")
    def validate_date_format(cls, v):  # noqa: F811 - Pydantic validator
        """Validate date is in ISO format (YYYY-MM-DD)."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")

    @validator("start_time", "end_time")
    def validate_time_format(cls, v):  # noqa: F811 - Pydantic validator
        """Validate time is in HH:MM format."""
        if not v or not isinstance(v, str):
            return v

        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM format")

    class Config:  # noqa: F811 - Pydantic Config class
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "title": "evf",
                "level": "A",
                "year": "2024-2025",
                "date": "2025-03-24",
                "day": "Monday",
                "teacher": "Brynjálvur I. Johansen",
                "teacherShort": "BIJ",
                "location": "608",
                "timeSlot": 2,
                "startTime": "10:05",
                "endTime": "11:35",
                "timeRange": "10:05-11:35",
                "cancelled": False,
                "lessonId": "12345678-1234-1234-1234-123456789012",
                "description": "Homework text goes here.",
            }
        }


class TimetableData(BaseModel):
    """Complete timetable data model."""

    student_info: StudentInfo = Field(..., alias="studentInfo")
    events: List[Event]
    week_info: WeekInfo = Field(..., alias="weekInfo")
    format_version: int = Field(2, alias="formatVersion")

    @validator("format_version")
    def validate_format_version(cls, v):  # noqa: F811 - Pydantic validator
        """Validate format version is 2."""
        if v != 2:
            raise ValueError("Format version must be 2")
        return v

    class Config:  # noqa: F811 - Pydantic Config class
        populate_by_name = True
        frozen = True

    # Methods previously defined here (filter_events_*, get_events_*, sort_events_*,
    # get_unique_*, from_dict, to_dict, to_json) were removed on 2025-04-19
    # as they were identified as unused by Vulture and confirmed via search.
    # They were marked with '# noqa: F811 - Part of TimetableData API' but
    # are not currently called anywhere in the project.
    pass  # Add pass to avoid empty class body issues if no other methods exist
