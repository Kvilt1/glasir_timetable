#!/usr/bin/env python3
"""
Data models for the Glasir Timetable application.

This module defines Pydantic models for student information, week information,
events (classes/lessons), and the overall timetable data structure.
"""

from typing import List, Optional, Union, Dict, Any, Set
from datetime import datetime
from pydantic import BaseModel, Field, validator, model_validator

class StudentInfo(BaseModel):
    """Student information model."""
    student_name: str = Field(..., alias="studentName")
    class_: str = Field(..., alias="class")
    
    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "studentName": "John Doe",
                "class": "22y"
            }
        }

class WeekInfo(BaseModel):
    """Week information model."""
    week_number: int = Field(..., alias="weekNumber")
    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")
    year: int
    week_key: Optional[str] = Field(None, alias="weekKey")
    
    @validator("start_date", "end_date")
    def validate_date_format(cls, v):
        """Validate date is in ISO format (YYYY-MM-DD)."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")
    
    @validator("week_number")
    def validate_week_number(cls, v):
        """Validate week number is within range 1-53."""
        if not 1 <= v <= 53:
            raise ValueError("Week number must be between 1 and 53")
        return v
    
    @model_validator(mode='after')
    def generate_week_key(self):
        """Generate week_key if not provided."""
        if not self.week_key:
            self.week_key = f"{self.year}_Week_{self.week_number}"
        return self
    
    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "weekNumber": 13,
                "startDate": "2025-03-24",
                "endDate": "2025-03-30",
                "year": 2025,
                "weekKey": "2025_Week_13"
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
    def validate_date_format(cls, v):
        """Validate date is in ISO format (YYYY-MM-DD)."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")
    
    @validator("start_time", "end_time")
    def validate_time_format(cls, v):
        """Validate time is in HH:MM format."""
        if not v or not isinstance(v, str):
            return v
        
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
    
    class Config:
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
                "description": "Homework text goes here."
            }
        }

class TimetableData(BaseModel):
    """Complete timetable data model."""
    student_info: StudentInfo = Field(..., alias="studentInfo")
    events: List[Event]
    week_info: WeekInfo = Field(..., alias="weekInfo")
    format_version: int = Field(2, alias="formatVersion")
    
    @validator("format_version")
    def validate_format_version(cls, v):
        """Validate format version is 2."""
        if v != 2:
            raise ValueError("Format version must be 2")
        return v
    
    class Config:
        populate_by_name = True
        frozen = True

    def filter_events_by_day(self, day: str) -> List[Event]:
        """Filter events by day of the week."""
        return [event for event in self.events if event.day == day]
    
    def filter_events_by_subject(self, subject: str) -> List[Event]:
        """Filter events by subject/title."""
        return [event for event in self.events if event.title == subject]
    
    def filter_events_by_teacher(self, teacher_short: str) -> List[Event]:
        """Filter events by teacher initials."""
        return [event for event in self.events if event.teacher_short == teacher_short]
    
    def get_events_for_date(self, date: str) -> List[Event]:
        """Get events for a specific date."""
        return [event for event in self.events if event.date == date]
    
    def sort_events_by_time(self) -> List[Event]:
        """Sort events by date and time."""
        return sorted(
            self.events, 
            key=lambda x: (x.date, x.start_time if x.start_time else "")
        )
    
    def get_unique_subjects(self) -> Set[str]:
        """Get all unique subjects in the timetable."""
        return {event.title for event in self.events}
    
    def get_unique_teachers(self) -> Set[str]:
        """Get all unique teachers in the timetable."""
        return {event.teacher_short for event in self.events}
    
    def get_events_count_by_day(self) -> Dict[str, int]:
        """Get count of events by day."""
        count = {}
        for event in self.events:
            count[event.day] = count.get(event.day, 0) + 1
        return count
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimetableData":
        """Create TimetableData instance from a dictionary."""
        return cls.model_validate(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TimetableData to a dictionary with camelCase keys."""
        return self.model_dump(by_alias=True)
    
    def to_json(self) -> str:
        """Convert TimetableData to a JSON string with camelCase keys."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) 