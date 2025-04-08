#!/usr/bin/env python3
"""
Domain models for the Glasir Timetable application.

This module defines additional domain entities that extend the existing Pydantic models
to create a more comprehensive domain model.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator

from glasir_timetable.core.models import Event, StudentInfo, WeekInfo, TimetableData

class Teacher(BaseModel):
    """Teacher domain entity."""
    initials: str
    full_name: str
    subjects: Optional[List[str]] = None
    email: Optional[str] = None
    
    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "initials": "BIJ",
                "full_name": "Brynjálvur I. Johansen",
                "subjects": ["evf"],
                "email": "bij@glasir.fo"
            }
        }
    
    @property
    def display_name(self) -> str:
        """Return a formatted display name for the teacher."""
        return f"{self.full_name} ({self.initials})"

class Homework(BaseModel):
    """Homework domain entity."""
    lesson_id: str = Field(..., alias="lessonId")
    subject: str
    content: str
    date: str
    teacher_initials: Optional[str] = Field(None, alias="teacherInitials")
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    @validator("date")
    def validate_date_format(cls, v):
        """Validate date is in ISO format (YYYY-MM-DD)."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")
    
    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {
            "example": {
                "lessonId": "12345678-1234-1234-1234-123456789012",
                "subject": "evf",
                "content": "Read chapter 5 for next class",
                "date": "2023-03-24",
                "teacherInitials": "BIJ",
                "extracted_at": "2023-03-22T14:30:45"
            }
        }

class Lesson(BaseModel):
    """Enhanced lesson domain entity that extends Event."""
    event: Event
    homework: Optional[Homework] = None
    
    class Config:
        populate_by_name = True
        frozen = True
    
    @property
    def has_homework(self) -> bool:
        """Check if the lesson has homework."""
        return self.homework is not None
    
    @property
    def formatted_time(self) -> str:
        """Return a nicely formatted time string."""
        return f"{self.event.day} {self.event.date}: {self.event.time_range}"

class Timetable(BaseModel):
    """
    Enhanced timetable domain entity that extends TimetableData.
    
    This adds additional functionality beyond the basic TimetableData model.
    """
    base: TimetableData
    lessons: List[Lesson] = []
    teachers: Dict[str, Teacher] = {}
    
    class Config:
        populate_by_name = True
        
    def __init__(self, **data):
        """Initialize the Timetable with TimetableData and convert events to lessons."""
        super().__init__(**data)
        
        # Convert events to lessons if not provided
        if not self.lessons and hasattr(self.base, 'events'):
            self.lessons = [Lesson(event=event) for event in self.base.events]
    
    @property
    def student_info(self) -> StudentInfo:
        """Get student information."""
        return self.base.student_info
    
    @property
    def week_info(self) -> WeekInfo:
        """Get week information."""
        return self.base.week_info
    
    @property
    def events(self) -> List[Event]:
        """Get original events from base timetable data."""
        return self.base.events
    
    def get_lessons_by_teacher(self, teacher_initials: str) -> List[Lesson]:
        """Get all lessons taught by a specific teacher."""
        return [lesson for lesson in self.lessons 
                if lesson.event.teacher_short == teacher_initials]
    
    def get_lessons_by_subject(self, subject: str) -> List[Lesson]:
        """Get all lessons for a specific subject."""
        return [lesson for lesson in self.lessons 
                if lesson.event.title == subject]
    
    def get_lessons_with_homework(self) -> List[Lesson]:
        """Get all lessons that have homework."""
        return [lesson for lesson in self.lessons 
                if lesson.has_homework]
    
    def add_homework(self, lesson_id: str, homework: Homework) -> bool:
        """Add homework to the corresponding lesson."""
        for lesson in self.lessons:
            if lesson.event.lesson_id == lesson_id:
                lesson.homework = homework
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Timetable to dictionary with all enhancements."""
        base_dict = self.base.to_dict()
        
        # Add teachers dictionary
        base_dict["teachers"] = {
            initials: teacher.model_dump(by_alias=True)
            for initials, teacher in self.teachers.items()
        }
        
        # Add homework content to events
        for event in base_dict["events"]:
            lesson_id = event.get("lessonId")
            if lesson_id:
                for lesson in self.lessons:
                    if lesson.event.lesson_id == lesson_id and lesson.homework:
                        event["homework"] = lesson.homework.model_dump(by_alias=True)
        
        return base_dict 