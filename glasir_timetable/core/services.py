

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
import asyncio

from playwright.async_api import Page

from glasir_timetable import logger, add_error
from glasir_timetable.core.models import TimetableData, Event, WeekInfo
from glasir_timetable.core.domain import Teacher, Homework, Lesson, Timetable
from glasir_timetable.core.cookie_auth import (
    check_and_refresh_cookies,
    set_cookies_in_playwright_context,
    create_requests_session_with_cookies,
    test_cookies_with_requests
)
from glasir_timetable.shared.param_utils import parse_dynamic_params

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
    async def extract_teacher_map(self, page: Page, force_update: bool = False,
                             cookies: Dict[str, str] = None, lname_value: str = None, timer_value: int = None) -> Dict[str, str]:
        """
        Extract teacher mapping from the timetable page.
        
        Args:
            page: The Playwright page object.
            force_update: Whether to force an update of the teacher mapping cache.
            cookies: Cookies dictionary to use with the API approach.
            lname_value: The lname value for API requests.
            timer_value: The timer value for API requests.
            
        Returns:
            dict: A mapping of teacher initials to full names.
        """
        pass
    
    @abc.abstractmethod
    async def extract_homework(self, page: Page, lesson_id: str, subject_code: str = "Unknown") -> Optional[Homework]:
        """
        Extract homework content for a specific lesson.
        
        Args:
            page: The Playwright page object
            lesson_id: The ID of the lesson
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

# Removed PlaywrightAuthenticationService, PlaywrightNavigationService, PlaywrightExtractionService per refactor specification.

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
            from glasir_timetable.shared import normalize_dates
            
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
            from glasir_timetable.shared import normalize_week_number
            
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
            from glasir_timetable.shared import generate_week_filename
            
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
    
    def __init__(self, storage_dir: str = "glasir_timetable/weeks"):
        """
        Initialize with a storage directory.
        
        Args:
            storage_dir: Directory to store timetable files (default: "glasir_timetable/weeks")
        """
        self.storage_dir = storage_dir
        # Create the storage directory if it doesn't exist
        os.makedirs(storage_dir, exist_ok=True)
    
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
            from glasir_timetable.shared.file_utils import save_json_data
            
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
            from glasir_timetable.shared.model_adapters import dict_to_timetable_data
            
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

class ApiExtractionService(ExtractionService):
    """
    Service that extracts data using the ApiClient rather than Playwright.
    This offers better performance by directly accessing the Glasir API endpoints.
    """
    
    def __init__(self, api_client):
        """
        Initialize with an ApiClient.
        
        Args:
            api_client: The ApiClient instance for accessing Glasir's API
        """
        self._api_client = api_client
        self._teacher_cache = {}  # Local cache for teacher mapping


    async def extract_teacher_map(self, page: Page, force_update: bool = False,
                             cookies: Dict[str, str] = None, lname_value: str = None, timer_value: int = None) -> Dict[str, str]:
        """
        Extract teacher mapping using the API client for teacher map extraction.
        
        Args:
            page: The Playwright page object
            force_update: Whether to force an update of the teacher mapping cache
            cookies: Cookies for API requests
            lname_value: Optional lname value for API requests
            timer_value: Optional timer value for API requests
            
        Returns:
            dict: Mapping of teacher initials to full names
        """
        # If we have a cached result and aren't forcing an update, return it
        if self._teacher_cache and not force_update:
            return self._teacher_cache
        
        # Try to use the API client for extraction
        try:
            # Get student ID from page
            student_id = await self.get_student_id(page)
            if not student_id:
                logger.warning("Could not extract student ID, using fallback method")
                # Fall back to Playwright extraction if we can't get student ID
                return await self._fallback_extract_teacher_map(page, force_update)
            
            # Use the API client to fetch teacher map
            # Pass the force_update parameter as update_cache
            teacher_map = await self._api_client.fetch_teacher_map(student_id, update_cache=force_update)
            
            if teacher_map:
                # Cache the result
                self._teacher_cache = teacher_map
                return teacher_map
            else:
                # Fall back to Playwright extraction if API returns empty
                logger.warning("API extraction returned empty teacher map, using fallback method")
                return await self._fallback_extract_teacher_map(page, force_update)
                
        except Exception as e:
            logger.error(f"Error using API client for teacher map extraction: {e}")
            logger.info("Falling back to Playwright extraction")
            return await self._fallback_extract_teacher_map(page, force_update)

    async def _fallback_extract_teacher_map(self, page: Page, force_update: bool = False) -> Dict[str, str]:
        """
        Fallback method using Playwright for teacher map extraction.
        
        Args:
            page: The Playwright page object
            force_update: Whether to force an update of the teacher mapping cache
            
        Returns:
            dict: Mapping of teacher initials to full names
        """
        # Use the teacher_map extractor directly
        from glasir_timetable.data.teacher_map import extract_teacher_map
        
        # Use appropriate cache file path
        from glasir_timetable.shared.constants import TEACHER_CACHE_FILE
        
        teacher_map = await extract_teacher_map(
            page, 
            use_cache=not force_update,
            cache_path=TEACHER_CACHE_FILE,
            cookies=None,
            lname_value=None,
            timer_value=None
        )
        
        # Cache the result
        if teacher_map:
            self._teacher_cache = teacher_map
        
        return teacher_map

    async def extract_homework(self, page: Page, lesson_id: str, subject_code: str = "Unknown") -> Optional[Homework]:
        """
        Extract homework content for a specific lesson using the API client.
        
        Args:
            page: The Playwright page object (needed for student ID extraction)
            lesson_id: The ID of the lesson
            subject_code: The subject code for better error reporting
            
        Returns:
            Optional[Homework]: Homework data if successful, None otherwise
        """
        try:
            # Get student ID
            student_id = await self.get_student_id(page)
            if not student_id:
                logger.warning(f"Could not extract student ID for homework extraction, lesson {lesson_id}")
                # No fallback available
                return None
            
            # Use the API client to fetch homework data
            homework_data = await self._api_client.fetch_homework_details(lesson_id, student_id)
            
            if homework_data is None:
                logger.warning(f"No homework data found for lesson {lesson_id}")
                return None
                
            if not homework_data:  # Empty dict - means homework exists but is empty
                return Homework(
                    lesson_id=lesson_id,
                    subject_code=subject_code,
                    content="",
                    is_empty=True
                )
                
            # Create Homework object
            return Homework(
                lesson_id=lesson_id,
                subject_code=subject_code,
                content=homework_data.get("description", ""),
                is_empty=not homework_data.get("description", "")
            )
                
        except Exception as e:
            logger.error(f"Error using API client for homework extraction (lesson {lesson_id}): {e}")
            logger.info("No fallback available for homework extraction")
            return None


    async def extract_multiple_homework(self, 
                                      page: Page, 
                                      lesson_ids: List[str], 
                                      batch_size: int = 10) -> Dict[str, Optional[Homework]]:
        """
        Extract homework content for multiple lessons in parallel using the API client.
        This is much more efficient than the Playwright approach.
        
        Args:
            page: The Playwright page object (needed for student ID extraction)
            lesson_ids: List of lesson IDs
            batch_size: Number of homework items to process in parallel
            
        Returns:
            Dict[str, Optional[Homework]]: Dictionary mapping lesson IDs to homework data
        """
        if not lesson_ids:
            return {}
            
        result = {}
        
        try:
            # Get student ID
            student_id = await self.get_student_id(page)
            if not student_id:
                logger.warning("Could not extract student ID for batch homework extraction")
                # Fall back to Playwright extraction
                return await self._fallback_extract_multiple_homework(page, lesson_ids, batch_size)
            
            # Process in batches to avoid overwhelming the server
            total_lessons = len(lesson_ids)
            processed = 0
            failed = 0
            
            # Create batches
            batches = [lesson_ids[i:i + batch_size] for i in range(0, len(lesson_ids), batch_size)]
            
            for batch in batches:
                # Process each batch in parallel using tasks
                tasks = [self._api_client.fetch_homework_details(lesson_id, student_id) for lesson_id in batch]
                homework_data_list = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for lesson_id, homework_data in zip(batch, homework_data_list):
                    # Handle exceptions
                    if isinstance(homework_data, Exception):
                        logger.error(f"Error fetching homework for lesson {lesson_id}: {homework_data}")
                        failed += 1
                        continue
                        
                    if homework_data is None:
                        # No homework data found
                        result[lesson_id] = None
                    elif not homework_data:  # Empty dict
                        # Empty homework
                        result[lesson_id] = Homework(
                            lesson_id=lesson_id,
                            subject_code="Unknown",  # We don't have subject code in batch mode
                            content="",
                            is_empty=True
                        )
                    else:
                        # Valid homework
                        result[lesson_id] = Homework(
                            lesson_id=lesson_id,
                            subject_code="Unknown",  # We don't have subject code in batch mode
                            content=homework_data.get("description", ""),
                            is_empty=not homework_data.get("description", "")
                        )
                    
                    processed += 1
                
                # Log progress
                logger.info(f"Processed {processed}/{total_lessons} lessons, {failed} failed")
                
            return result
                
        except Exception as e:
            logger.error(f"Error in batch homework extraction: {e}")
            logger.info("Falling back to Playwright extraction")
            return await self._fallback_extract_multiple_homework(page, lesson_ids, batch_size)


    async def extract_student_info(self, page: Page) -> Dict[str, str]:
        """
        Extract student information from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            dict: Student information (name, class)
        """
        # First check if we have student info stored in a file
        student_info_file = os.path.join("glasir_timetable", "student_info.json")
        
        if os.path.exists(student_info_file):
            try:
                with open(student_info_file, 'r', encoding='utf-8') as f:
                    stored_info = json.load(f)
                if stored_info and "studentName" in stored_info and "class" in stored_info:
                    logger.info(f"Using cached student info: {stored_info}")
                    return stored_info
            except Exception as e:
                logger.error(f"Error reading student info from file: {e}")
                # Continue with extraction
        
        try:
            # Try to extract using DOM selectors
            from glasir_timetable.shared.error_utils import evaluate_js_safely
            
            # Extract student info using JavaScript selectors
            try:
                student_name = await evaluate_js_safely(
                    page,
                    "document.querySelector('.main-content h1')?.textContent.trim() || 'Unknown'",
                    error_message="Failed to extract student name"
                )
                
                class_name = await evaluate_js_safely(
                    page,
                    "document.querySelector('.main-content p')?.textContent.match(/Class: ([^,]+)/)?.[1] || 'Unknown'",
                    error_message="Failed to extract class name"
                )
                
                student_info = {
                    "studentName": student_name if student_name != "" else "Unknown",
                    "class": class_name if class_name != "" else "Unknown"
                }
                
                # Save the successfully extracted info to file for future use
                if student_info["studentName"] != "Unknown" or student_info["class"] != "Unknown":
                    try:
                        os.makedirs(os.path.dirname(student_info_file), exist_ok=True)
                        with open(student_info_file, 'w', encoding='utf-8') as f:
                            json.dump(student_info, f)
                        logger.info(f"Saved student info to file: {student_info}")
                    except Exception as e:
                        logger.error(f"Error saving student info to file: {e}")
                
                return student_info
            except Exception as js_e:
                logger.warning(f"Error extracting student info using JavaScript: {js_e}")
                
            # If JavaScript extraction failed, try using regex on HTML content
            try:
                html_content = await page.content()
                
                # Attempt to find student name and class in HTML
                name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content)
                class_match = re.search(r'Class:\s*([^,<]+)', html_content)
                
                student_name = name_match.group(1).strip() if name_match else "Unknown"
                class_name = class_match.group(1).strip() if class_match else "Unknown"
                
                student_info = {
                    "studentName": student_name,
                    "class": class_name
                }
                
                # Save the successfully extracted info to file for future use
                if student_info["studentName"] != "Unknown" or student_info["class"] != "Unknown":
                    try:
                        os.makedirs(os.path.dirname(student_info_file), exist_ok=True)
                        with open(student_info_file, 'w', encoding='utf-8') as f:
                            json.dump(student_info, f)
                        logger.info(f"Saved student info to file: {student_info}")
                    except Exception as e:
                        logger.error(f"Error saving student info to file: {e}")
                
                return student_info
            except Exception as regex_e:
                logger.warning(f"Error extracting student info using regex: {regex_e}")
            
            # Try the specific timetable format extraction
            try:
                html_content = await page.content()
                
                # Specific pattern for Glasir timetable format with tab character and HTML entity
                timetable_match = re.search(r'<td[^>]*valign=top[^>]*>\t?N&aelig;mingatímatalva:\s*([^,]+),\s*([^<\s]+)', html_content)
                
                if timetable_match:
                    student_name = timetable_match.group(1).strip()
                    class_name = timetable_match.group(2).strip()
                    
                    student_info = {
                        "studentName": student_name,
                        "class": class_name
                    }
                    
                    # Save the successfully extracted info to file for future use
                    try:
                        os.makedirs(os.path.dirname(student_info_file), exist_ok=True)
                        with open(student_info_file, 'w', encoding='utf-8') as f:
                            json.dump(student_info, f)
                        logger.info(f"Saved student info from timetable format: {student_info}")
                    except Exception as e:
                        logger.error(f"Error saving student info to file: {e}")
                    
                    return student_info
            except Exception as timetable_regex_e:
                logger.warning(f"Error extracting student info using timetable regex: {timetable_regex_e}")
            
            # If everything fails, return default values
            logger.warning("Could not extract student info, using default values")
            return {
                "studentName": "Unknown",
                "class": "Unknown"
            }
        except Exception as e:
            logger.error(f"Error extracting student info: {e}")
            return {
                "studentName": "Unknown",
                "class": "Unknown"
            }
        
    async def get_student_id(self, page: Page) -> Optional[str]:
        """
        Extract the student ID from the page.
        
        Args:
            page: The Playwright page object
            
        Returns:
            Optional[str]: The student ID or None if not found
        """
        # Import here to avoid circular imports
        from glasir_timetable.core.student_utils import get_student_id
        
        # Reuse the existing implementation
        return await get_student_id(page) 