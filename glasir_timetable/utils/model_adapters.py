#!/usr/bin/env python3
"""
Adapter functions for converting between dictionary data structures
and Pydantic models for the Glasir Timetable application.
"""

from typing import Dict, Any, Optional, Union, List, Tuple, Type, TypeVar
from pydantic import ValidationError

from glasir_timetable import logger, add_error
from glasir_timetable.models import StudentInfo, WeekInfo, Event, TimetableData

# Type variable for generic model functions
T = TypeVar('T')

def safe_model_conversion(data_dict: Dict[str, Any], model_class: Type[T]) -> Tuple[Optional[T], bool]:
    """
    Safely convert a dictionary to a Pydantic model, handling validation errors.
    
    Args:
        data_dict: Dictionary data to convert
        model_class: Pydantic model class to convert to
        
    Returns:
        tuple: (model_instance, success_flag)
    """
    if not data_dict:
        return None, False
        
    try:
        model_instance = model_class.model_validate(data_dict)
        return model_instance, True
    except ValidationError as e:
        error_details = str(e).replace('\n', ' ')
        logger.error(f"Validation error converting to {model_class.__name__}: {error_details}")
        add_error("general_errors", f"Model validation error: {model_class.__name__}", 
                 {"details": error_details, "data": str(data_dict)[:200] + "..."})
        return None, False

def convert_date_format(date_str: Optional[str]) -> Optional[str]:
    """
    Convert date string to ISO format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to convert
    
    Returns:
        str: Date in ISO format or None if conversion fails
    """
    if not date_str:
        return None
    
    # Convert from "YYYY.MM.DD" to "YYYY-MM-DD"
    if '.' in date_str:
        return date_str.replace('.', '-')
    
    # Already in ISO format
    return date_str

def dict_to_timetable_data(data_dict: Dict[str, Any]) -> Tuple[Optional[TimetableData], bool]:
    """
    Convert a dictionary to a TimetableData model.
    
    Args:
        data_dict: Dictionary containing timetable data
        
    Returns:
        tuple: (timetable_data, success_flag)
    """
    if not data_dict:
        return None, False
        
    try:
        # Process nested structures first if needed
        student_info_dict = data_dict.get("studentInfo", {})
        week_info_dict = data_dict.get("weekInfo", {})
        events_list = data_dict.get("events", [])
        
        # Transform week_info_dict to match model expectations
        transformed_week_info = {
            # Handle different field names (week_num vs weekNumber)
            "weekNumber": week_info_dict.get("weekNumber", week_info_dict.get("week_num")),
            "year": week_info_dict.get("year"),
            # Convert date formats from YYYY.MM.DD to YYYY-MM-DD
            "startDate": convert_date_format(week_info_dict.get("startDate", week_info_dict.get("start_date"))),
            "endDate": convert_date_format(week_info_dict.get("endDate", week_info_dict.get("end_date"))),
            "weekKey": week_info_dict.get("weekKey", week_info_dict.get("week_key"))
        }

        # Handle possible transformation of events if needed
        transformed_events = []
        for event in events_list:
            # Ensure date is in ISO format
            if "date" in event and event["date"]:
                event["date"] = convert_date_format(event["date"])
            transformed_events.append(event)
        
        # Create the model instance
        timetable_data = TimetableData(
            student_info=StudentInfo.model_validate(student_info_dict),
            week_info=WeekInfo.model_validate(transformed_week_info),
            events=[Event.model_validate(event) for event in transformed_events],
            format_version=data_dict.get("formatVersion", 2)
        )
        return timetable_data, True
    except ValidationError as e:
        error_details = str(e).replace('\n', ' ')
        logger.error(f"Validation error converting to TimetableData: {error_details}")
        add_error("general_errors", "Model validation error: TimetableData", 
                 {"details": error_details})
        return None, False
    except Exception as e:
        logger.error(f"Error converting to TimetableData: {e}")
        add_error("general_errors", "Model conversion error", {"details": str(e)})
        return None, False

def timetable_data_to_dict(timetable_data: TimetableData) -> Dict[str, Any]:
    """
    Convert a TimetableData model to a dictionary.
    
    Args:
        timetable_data: TimetableData model instance
        
    Returns:
        dict: Dictionary representation of the timetable data
    """
    if timetable_data is None:
        return {}
        
    return timetable_data.model_dump(by_alias=True) 