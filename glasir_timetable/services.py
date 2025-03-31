#!/usr/bin/env python3
"""
Service interfaces for the Glasir Timetable application.

This module defines abstract base classes for the core services in the application,
establishing clear contracts and separation of concerns.
"""

import abc
import os
import json
from typing import Dict, List, Optional, Tuple, Union, Any
from pathlib import Path
import re
from datetime import datetime

from playwright.async_api import Page

from glasir_timetable import logger, add_error
from glasir_timetable.models import TimetableData, Event, WeekInfo
from glasir_timetable.domain import Teacher, Homework, Lesson, Timetable

class AuthenticationService(abc.ABC):
    """
    Service interface for handling authentication to the timetable system.
    """
    
    @abc.abstractmethod
    async def login(self, username: str, password: str, page: Page) -> bool:
        """
        Authenticate a user with the timetable system.
        
        Args:
            username: The username for login (without @glasir.fo domain)
            password: The password for login
            page: The Playwright page object
            
        Returns:
            bool: True if login successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def is_authenticated(self, page: Page) -> bool:
        """
        Check if the current session is authenticated.
        
        Args:
            page: The Playwright page object
            
        Returns:
            bool: True if authenticated, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def logout(self, page: Page) -> bool:
        """
        Log out the current user.
        
        Args:
            page: The Playwright page object
            
        Returns:
            bool: True if logout successful, False otherwise
        """
        pass

class NavigationService(abc.ABC):
    """
    Service interface for navigating between timetable weeks and pages.
    """
    
    @abc.abstractmethod
    async def navigate_to_week(self, page: Page, week_offset: int, student_id: str) -> Dict[str, Any]:
        """
        Navigate to a specific week in the timetable.
        
        Args:
            page: The Playwright page object
            week_offset: Offset from current week (0=current, 1=next, -1=previous)
            student_id: The student ID GUID
            
        Returns:
            dict: Information about the week that was navigated to
        """
        pass
    
    @abc.abstractmethod
    async def return_to_baseline(self, page: Page, student_id: str) -> bool:
        """
        Return to the baseline week (typically current week).
        
        Args:
            page: The Playwright page object
            student_id: The student ID GUID
            
        Returns:
            bool: True if navigation successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def get_available_weeks(self, page: Page, student_id: str) -> List[Dict[str, Any]]:
        """
        Get a list of all available weeks in the timetable.
        
        Args:
            page: The Playwright page object
            student_id: The student ID GUID
            
        Returns:
            list: List of week information dictionaries
        """
        pass
    
    @abc.abstractmethod
    async def get_student_id(self, page: Page) -> str:
        """
        Extract the student ID from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            str: Student ID GUID
        """
        pass

class ExtractionService(abc.ABC):
    """
    Service interface for extracting data from the timetable pages.
    """
    
    @abc.abstractmethod
    async def extract_timetable(self, page: Page, teacher_map: Dict[str, str] = None) -> Union[TimetableData, Dict[str, Any]]:
        """
        Extract timetable data from the current page.
        
        Args:
            page: The Playwright page object
            teacher_map: Optional dictionary mapping teacher initials to full names
            
        Returns:
            Union[TimetableData, dict]: Extracted timetable data as model or dictionary
        """
        pass
    
    @abc.abstractmethod
    async def extract_teacher_map(self, page: Page) -> Dict[str, str]:
        """
        Extract the teacher mapping (initials to full names) from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            dict: Mapping of teacher initials to full names
        """
        pass
    
    @abc.abstractmethod
    async def extract_homework(self, page: Page, lesson_id: str, subject_code: str = "Unknown") -> Optional[Homework]:
        """
        Extract homework content for a specific lesson.
        
        Args:
            page: The Playwright page object
            lesson_id: The unique ID of the lesson
            subject_code: The subject code for better error reporting
            
        Returns:
            Optional[Homework]: Homework data if successful, None otherwise
        """
        pass
    
    @abc.abstractmethod
    async def extract_multiple_homework(self, 
                                      page: Page, 
                                      lesson_ids: List[str], 
                                      batch_size: int = 3) -> Dict[str, Optional[Homework]]:
        """
        Extract homework content for multiple lessons in parallel.
        
        Args:
            page: The Playwright page object
            lesson_ids: List of lesson IDs
            batch_size: Number of homework items to process in parallel
            
        Returns:
            dict: Mapping of lesson IDs to homework data
        """
        pass
    
    @abc.abstractmethod
    async def extract_student_info(self, page: Page) -> Dict[str, str]:
        """
        Extract student information from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            dict: Student information (name, class)
        """
        pass

class FormattingService(abc.ABC):
    """
    Service interface for formatting and transforming timetable data.
    """
    
    @abc.abstractmethod
    def normalize_dates(self, start_date: str, end_date: str, year: int) -> Tuple[str, str]:
        """
        Normalize date formats to ISO 8601.
        
        Args:
            start_date: Start date string
            end_date: End date string
            year: Year number for context
            
        Returns:
            tuple: Normalized (start_date, end_date)
        """
        pass
    
    @abc.abstractmethod
    def normalize_week_number(self, week_num: int) -> int:
        """
        Normalize week number to valid range (1-53).
        
        Args:
            week_num: Week number to normalize
            
        Returns:
            int: Normalized week number
        """
        pass
    
    @abc.abstractmethod
    def generate_filename(self, year: int, week_num: int, start_date: str, end_date: str) -> str:
        """
        Generate a standardized filename for timetable data.
        
        Args:
            year: Year number
            week_num: Week number
            start_date: Start date in ISO format
            end_date: End date in ISO format
            
        Returns:
            str: Standardized filename
        """
        pass

class StorageService(abc.ABC):
    """
    Service interface for persisting and retrieving timetable data.
    """
    
    @abc.abstractmethod
    def save_timetable(self, data: Union[TimetableData, Dict[str, Any]], output_path: str) -> bool:
        """
        Save timetable data to a file.
        
        Args:
            data: Timetable data to save
            output_path: Path to save the data to
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def load_timetable(self, file_path: str) -> Optional[TimetableData]:
        """
        Load timetable data from a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Optional[TimetableData]: Loaded timetable data if successful, None otherwise
        """
        pass
    
    @abc.abstractmethod
    def get_available_timetables(self, directory: str) -> List[Path]:
        """
        Get a list of available timetable files.
        
        Args:
            directory: Directory to search in
            
        Returns:
            list: List of file paths
        """
        pass
    
    @abc.abstractmethod
    def save_credentials(self, username: str, password: str, file_path: str) -> bool:
        """
        Save credentials to a file.
        
        Args:
            username: Username
            password: Password
            file_path: Path to save the credentials to
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    def load_credentials(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Load credentials from a file.
        
        Args:
            file_path: Path to the credentials file
            
        Returns:
            tuple: (username, password) if successful, (None, None) otherwise
        """
        pass

# Concrete Implementations

class PlaywrightAuthenticationService(AuthenticationService):
    """
    Playwright-based implementation of the AuthenticationService interface.
    """
    
    async def login(self, username: str, password: str, page: Page) -> bool:
        """
        Authenticate a user with the timetable system using Playwright.
        
        Args:
            username: The username for login (without @glasir.fo domain)
            password: The password for login
            page: The Playwright page object
            
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            from glasir_timetable.auth import login_to_glasir
            await login_to_glasir(page, username, password)
            return await self.is_authenticated(page)
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def is_authenticated(self, page: Page) -> bool:
        """
        Check if the current session is authenticated by looking for timetable elements.
        
        Args:
            page: The Playwright page object
            
        Returns:
            bool: True if authenticated, False otherwise
        """
        try:
            # Check if we're on the timetable page
            current_url = page.url
            if "tg.glasir.fo/132n" not in current_url:
                return False
            
            # Check for the presence of the timetable table
            table_selector = "table.time_8_16"
            table = await page.query_selector(table_selector)
            return table is not None
        except Exception as e:
            logger.error(f"Error checking authentication status: {e}")
            return False
    
    async def logout(self, page: Page) -> bool:
        """
        Log out the current user by navigating to the logout page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            bool: True if logout successful, False otherwise
        """
        try:
            # Navigate to the logout page
            await page.goto("https://tg.glasir.fo/logout.asp")
            
            # Check if we're logged out
            return not await self.is_authenticated(page)
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            return False

class PlaywrightNavigationService(NavigationService):
    """
    Playwright-based implementation of the NavigationService interface.
    """
    
    async def navigate_to_week(self, page: Page, week_offset: int, student_id: str) -> Dict[str, Any]:
        """
        Navigate to a specific week using JavaScript navigation.
        
        Args:
            page: The Playwright page object
            week_offset: Offset from current week (0=current, 1=next, -1=previous)
            student_id: The student ID GUID
            
        Returns:
            dict: Information about the week that was navigated to
        """
        try:
            from glasir_timetable.js_navigation.js_integration import navigate_to_week_js
            
            # Check if student_id is provided, or get it
            if not student_id:
                student_id = await self.get_student_id(page)
            
            # Navigate to the week
            week_info = await navigate_to_week_js(page, week_offset, student_id)
            return week_info
        except Exception as e:
            logger.error(f"Error navigating to week {week_offset}: {e}")
            return {}
    
    async def return_to_baseline(self, page: Page, student_id: str) -> bool:
        """
        Return to the baseline week (typically current week).
        
        Args:
            page: The Playwright page object
            student_id: The student ID GUID
            
        Returns:
            bool: True if navigation successful, False otherwise
        """
        try:
            from glasir_timetable.js_navigation.js_integration import return_to_baseline_js
            
            # Navigate to baseline (week 0)
            await return_to_baseline_js(page, 0, student_id)
            return True
        except Exception as e:
            logger.error(f"Error returning to baseline: {e}")
            return False
    
    async def get_available_weeks(self, page: Page, student_id: str) -> List[Dict[str, Any]]:
        """
        Get a list of all available weeks in the timetable.
        
        Args:
            page: The Playwright page object
            student_id: The student ID GUID
            
        Returns:
            list: List of week information dictionaries
        """
        try:
            from glasir_timetable.utils.error_utils import evaluate_js_safely
            
            # Get all available weeks using the JavaScript function
            weeks = await evaluate_js_safely(
                page,
                "glasirTimetable.getAllWeeks()",
                error_message="Failed to get available weeks"
            )
            
            if not weeks:
                return []
            
            return weeks
        except Exception as e:
            logger.error(f"Error getting available weeks: {e}")
            return []
    
    async def get_student_id(self, page: Page) -> str:
        """
        Extract the student ID from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            str: Student ID GUID
        """
        try:
            from glasir_timetable.js_navigation.js_integration import get_student_id
            
            # Get student ID 
            student_id = await get_student_id(page)
            return student_id
        except Exception as e:
            logger.error(f"Error getting student ID: {e}")
            return ""

class PlaywrightExtractionService(ExtractionService):
    """
    Playwright-based implementation of the ExtractionService interface.
    """
    
    async def extract_timetable(self, page: Page, teacher_map: Dict[str, str] = None) -> Union[TimetableData, Dict[str, Any]]:
        """
        Extract timetable data from the page.
        
        Args:
            page: The Playwright page object
            teacher_map: Optional dictionary mapping teacher initials to full names
            
        Returns:
            Union[TimetableData, dict]: Extracted timetable data
        """
        try:
            from glasir_timetable.extractors.timetable import extract_timetable_data
            
            # Extract timetable data (returns a tuple with data and week_info)
            timetable_data, _ = await extract_timetable_data(
                page, 
                teacher_map=teacher_map, 
                use_models=True
            )
            
            return timetable_data
        except Exception as e:
            logger.error(f"Error extracting timetable data: {e}")
            return None
    
    async def extract_teacher_map(self, page: Page) -> Dict[str, str]:
        """
        Extract the teacher mapping from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            dict: Mapping of teacher initials to full names
        """
        try:
            from glasir_timetable.extractors.teacher_map import extract_teacher_map
            
            # Extract teacher map
            teacher_map = await extract_teacher_map(page)
            return teacher_map
        except Exception as e:
            logger.error(f"Error extracting teacher map: {e}")
            return {}
    
    async def extract_homework(self, page: Page, lesson_id: str, subject_code: str = "Unknown") -> Optional[Homework]:
        """
        Extract homework content for a specific lesson.
        
        Args:
            page: The Playwright page object
            lesson_id: The unique ID of the lesson
            subject_code: The subject code for better error reporting
            
        Returns:
            Optional[Homework]: Homework data if successful, None otherwise
        """
        try:
            from glasir_timetable.extractors.timetable import extract_homework_content
            
            # Extract homework content
            result = await extract_homework_content(page, lesson_id, subject_code)
            
            if result and result.get("success") and result.get("content"):
                # Create Homework object with the extracted content
                homework = Homework(
                    lessonId=lesson_id,
                    subject=subject_code,
                    content=result["content"],
                    date=datetime.now().strftime("%Y-%m-%d")
                )
                return homework
                
            return None
        except Exception as e:
            logger.error(f"Error extracting homework for {subject_code} (ID: {lesson_id}): {e}")
            return None
    
    async def extract_multiple_homework(self, 
                                      page: Page, 
                                      lesson_ids: List[str], 
                                      batch_size: int = 3) -> Dict[str, Optional[Homework]]:
        """
        Extract homework content for multiple lessons in parallel.
        
        Args:
            page: The Playwright page object
            lesson_ids: List of lesson IDs
            batch_size: Number of homework items to process in parallel
            
        Returns:
            dict: Mapping of lesson IDs to homework data
        """
        try:
            from glasir_timetable.js_navigation.js_integration import extract_all_homework_content_js
            
            # Extract all homework content in parallel
            content_dict = await extract_all_homework_content_js(page, lesson_ids, batch_size)
            
            # Convert to Homework objects
            result = {}
            for lesson_id, content in content_dict.items():
                if content:
                    # Create Homework object
                    homework = Homework(
                        lessonId=lesson_id,
                        subject="Unknown",  # We don't know the subject here
                        content=content,
                        date=datetime.now().strftime("%Y-%m-%d")
                    )
                    result[lesson_id] = homework
                else:
                    result[lesson_id] = None
                    
            return result
        except Exception as e:
            logger.error(f"Error extracting multiple homework: {e}")
            return {lesson_id: None for lesson_id in lesson_ids}
    
    async def extract_student_info(self, page: Page) -> Dict[str, str]:
        """
        Extract student information from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            dict: Student information (name, class)
        """
        try:
            from glasir_timetable.js_navigation.js_integration import extract_student_info_js
            
            # Extract student info using JavaScript
            student_info = await extract_student_info_js(page)
            return student_info
        except Exception as e:
            logger.error(f"Error extracting student info: {e}")
            return {"studentName": "Unknown", "class": "Unknown"}

class DefaultFormattingService(FormattingService):
    """
    Default implementation of the FormattingService interface.
    """
    
    def normalize_dates(self, start_date: str, end_date: str, year: int) -> Tuple[str, str]:
        """
        Normalize date formats to ISO 8601.
        
        Args:
            start_date: Start date string
            end_date: End date string
            year: Year number for context
            
        Returns:
            tuple: Normalized (start_date, end_date)
        """
        try:
            from glasir_timetable.utils import normalize_dates
            
            # Use the utility function
            normalized_start, normalized_end = normalize_dates(start_date, end_date, year)
            return normalized_start, normalized_end
        except Exception as e:
            logger.error(f"Error normalizing dates: {e}")
            return start_date, end_date
    
    def normalize_week_number(self, week_num: int) -> int:
        """
        Normalize week number to valid range (1-53).
        
        Args:
            week_num: Week number to normalize
            
        Returns:
            int: Normalized week number
        """
        try:
            from glasir_timetable.utils import normalize_week_number
            
            # Use the utility function
            return normalize_week_number(week_num)
        except Exception as e:
            logger.error(f"Error normalizing week number: {e}")
            # Basic fallback
            if week_num < 1:
                return 1
            elif week_num > 53:
                return 53
            return week_num
    
    def generate_filename(self, year: int, week_num: int, start_date: str, end_date: str) -> str:
        """
        Generate a standardized filename for timetable data.
        
        Args:
            year: Year number
            week_num: Week number
            start_date: Start date in ISO format
            end_date: End date in ISO format
            
        Returns:
            str: Standardized filename
        """
        try:
            from glasir_timetable.utils import generate_week_filename
            
            # Generate filename
            filename = generate_week_filename(year, week_num, start_date, end_date)
            return filename
        except Exception as e:
            logger.error(f"Error generating filename: {e}")
            # Simple fallback
            return f"{year}_Week_{week_num}_{start_date}_to_{end_date}.json"

class FileStorageService(StorageService):
    """
    File-based implementation of the StorageService interface.
    """
    
    def save_timetable(self, data: Union[TimetableData, Dict[str, Any]], output_path: str) -> bool:
        """
        Save timetable data to a JSON file.
        
        Args:
            data: Timetable data to save
            output_path: Path to save the data to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from glasir_timetable.utils.file_utils import save_json_data
            
            # Save data to file
            result = save_json_data(data, output_path)
            return result
        except Exception as e:
            logger.error(f"Error saving timetable data: {e}")
            return False
    
    def load_timetable(self, file_path: str) -> Optional[TimetableData]:
        """
        Load timetable data from a JSON file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Optional[TimetableData]: Loaded timetable data if successful, None otherwise
        """
        try:
            from glasir_timetable.utils.model_adapters import dict_to_timetable_data
            
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            # Load JSON data
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Convert to TimetableData model
            model, success = dict_to_timetable_data(json_data)
            if success and model:
                return model
                
            # If conversion to model fails, return None
            return None
        except Exception as e:
            logger.error(f"Error loading timetable data: {e}")
            return None
    
    def get_available_timetables(self, directory: str) -> List[Path]:
        """
        Get a list of available timetable files in a directory.
        
        Args:
            directory: Directory to search in
            
        Returns:
            list: List of file paths
        """
        try:
            # Check if directory exists
            if not os.path.exists(directory) or not os.path.isdir(directory):
                logger.error(f"Directory not found or not a directory: {directory}")
                return []
            
            # Find all JSON files in the directory
            path = Path(directory)
            json_files = list(path.glob("*.json"))
            
            # Filter for timetable files (based on filename pattern)
            timetable_files = [
                file for file in json_files 
                if re.match(r"\d{4}_Week_\d+_.*\.json", file.name) or 
                   re.match(r"\d{4} Vika \d+.*\.json", file.name)
            ]
            
            return timetable_files
        except Exception as e:
            logger.error(f"Error getting available timetables: {e}")
            return []
    
    def save_credentials(self, username: str, password: str, file_path: str) -> bool:
        """
        Save credentials to a JSON file.
        
        Args:
            username: Username
            password: Password
            file_path: Path to save the credentials to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create the parent directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Create credentials dictionary
            credentials = {
                "username": username,
                "password": password
            }
            
            # Save to JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, ensure_ascii=False, indent=2)
                
            return True
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")
            return False
    
    def load_credentials(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Load credentials from a JSON file.
        
        Args:
            file_path: Path to the credentials file
            
        Returns:
            tuple: (username, password) if successful, (None, None) otherwise
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"Credentials file not found: {file_path}")
                return None, None
            
            # Load JSON data
            with open(file_path, 'r', encoding='utf-8') as f:
                credentials = json.load(f)
                
            # Extract username and password
            username = credentials.get("username")
            password = credentials.get("password")
            
            return username, password
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return None, None 