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
from glasir_timetable.cookie_auth import (
    check_and_refresh_cookies,
    set_cookies_in_playwright_context,
    create_requests_session_with_cookies,
    test_cookies_with_requests
)

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
    async def extract_teacher_map(self, page: Page, force_update: bool = False) -> Dict[str, str]:
        """
        Extract the teacher mapping (initials to full names) from the page.
        
        Args:
            page: The Playwright page object
            force_update: Whether to force an update of the teacher mapping cache
            
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

class CookieAuthenticationService(AuthenticationService):
    """
    Authentication service implementation that uses cookie-based authentication
    with fallback to regular Playwright authentication.
    """
    
    def __init__(self, cookie_path: str = "cookies.json", auto_refresh: bool = True):
        """
        Initialize the cookie-based authentication service.
        
        Args:
            cookie_path: Path to save/load cookies
            auto_refresh: Whether to automatically refresh expired cookies
        """
        self.cookie_path = cookie_path
        self.auto_refresh = auto_refresh
        # Create a regular authentication service as fallback
        self.regular_auth_service = PlaywrightAuthenticationService()
        # Keep track of the requests session when created
        self.requests_session = None
        # Store cookie data
        self.cookie_data = None
    
    async def login(self, username: str, password: str, page: Page) -> bool:
        """
        Authenticate using cookies if possible, falling back to regular login.
        
        Args:
            username: Username for login
            password: Password for login
            page: Playwright page object
            
        Returns:
            bool: True if authentication successful
        """
        try:
            # Try cookie-based authentication first
            logger.info("Attempting cookie-based authentication...")
            
            if self.auto_refresh:
                # This will check if cookies exist/valid and refresh them if needed
                self.cookie_data = await check_and_refresh_cookies(
                    page=page,
                    username=username,
                    password=password,
                    cookie_path=self.cookie_path
                )
                
                if self.cookie_data:
                    # Set cookies in browser context
                    await set_cookies_in_playwright_context(page, self.cookie_data)
                    
                    # Navigate to timetable page to verify
                    await page.goto("https://tg.glasir.fo/132n/")
                    
                    # Check if we're logged in by looking for the timetable
                    try:
                        await page.wait_for_selector("table.time_8_16", state="visible", timeout=10000)
                        logger.info("Successfully authenticated using cookies!")
                        
                        # Create requests session
                        self.requests_session = create_requests_session_with_cookies(self.cookie_data)
                        
                        return True
                    except Exception as e:
                        logger.warning(f"Cookie authentication failed: {e}")
                        # Fall back to regular login
            
            # If we get here, cookie authentication failed or was disabled
            logger.info("Using regular authentication...")
            return await self.regular_auth_service.login(username, password, page)
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            add_error("authentication", str(e))
            return False
    
    async def is_authenticated(self, page: Page) -> bool:
        """
        Check if the current session is authenticated.
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if authenticated
        """
        # First try checking with the requests session if available
        if self.requests_session and self.cookie_data:
            try:
                # Quick test with requests
                return await test_cookies_with_requests(self.cookie_data)
            except Exception as e:
                logger.warning(f"Error checking cookies with requests: {e}")
        
        # Fall back to regular check
        return await self.regular_auth_service.is_authenticated(page)
    
    async def logout(self, page: Page) -> bool:
        """
        Log out the current user and invalidate cookies.
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if logout successful
        """
        # Clear requests session
        self.requests_session = None
        self.cookie_data = None
        
        # Delete cookie file if it exists
        if os.path.exists(self.cookie_path):
            try:
                os.remove(self.cookie_path)
                logger.info(f"Removed cookie file: {self.cookie_path}")
            except Exception as e:
                logger.warning(f"Failed to remove cookie file: {e}")
        
        # Use regular logout
        return await self.regular_auth_service.logout(page)
    
    def get_requests_session(self):
        """
        Get the requests session with cookies set.
        
        Returns:
            requests.Session: Session with cookies
        """
        return self.requests_session

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
    """Extracts timetable, teacher and homework data using Playwright."""
    
    async def extract_timetable(self, page: Page, teacher_map: Dict[str, str] = None) -> Union[TimetableData, Dict[str, Any]]:
        """
        Extract timetable data from the current page.
        
        Args:
            page: The Playwright page object
            teacher_map: Optional dictionary mapping teacher initials to full names
            
        Returns:
            Union[TimetableData, dict]: Extracted timetable data as model or dictionary
        """
        from glasir_timetable.extractors.timetable import extract_timetable_data
        
        try:
            timetable_data, week_info, lesson_ids = await extract_timetable_data(page)
            
            # Add teacher names if available
            if teacher_map and timetable_data:
                for event in timetable_data.get('events', []):
                    if event.get('teacher') in teacher_map:
                        event['teacherFullName'] = teacher_map[event['teacher']]
            
            return timetable_data
        except Exception as e:
            add_error("timetable_extraction", f"Failed to extract timetable: {e}")
            return {}
    
    async def extract_teacher_map(self, page: Page, force_update: bool = False) -> Dict[str, str]:
        """
        Extract the teacher mapping (initials to full names) from the page.
        
        Args:
            page: The Playwright page object
            force_update: Whether to force an update of the teacher mapping cache
            
        Returns:
            dict: Mapping of teacher initials to full names
        """
        from glasir_timetable.extractors.teacher_map import extract_teacher_map
        
        try:
            teacher_map = await extract_teacher_map(page, force_update=force_update)
            return teacher_map
        except Exception as e:
            add_error("teacher_map_extraction", f"Failed to extract teacher map: {e}")
            return {}
    
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
        from glasir_timetable.api_client import fetch_homework_for_lesson, extract_lname_from_page, extract_timer_value_from_page, fetch_homework_with_retry
        
        try:
            # Get cookies for API requests
            cookies = {}
            try:
                all_cookies = await page.context.cookies()
                cookies = {cookie['name']: cookie['value'] for cookie in all_cookies}
            except Exception as cookie_e:
                add_error("homework_extraction", f"Failed to get cookies: {cookie_e}, subject: {subject_code}")
                return None
            
            # Extract the lname value for the API request
            lname_value = await extract_lname_from_page(page)
            timer_value = await extract_timer_value_from_page(page)
            
            # Attempt to fetch the homework using our new retry function
            # First try to get auth service for potential retry
            auth_service = None
            username = None
            password = None
            
            try:
                # Try to access service_factory and get credentials from the context
                from glasir_timetable.service_factory import get_service
                auth_service = get_service("authentication")
                
                # Try to get credentials from the environment or a credentials file
                credentials_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
                if os.path.exists(credentials_path):
                    with open(credentials_path, 'r') as f:
                        creds = json.load(f)
                        username = creds.get('username')
                        password = creds.get('password')
            except Exception as auth_e:
                logger.warning(f"Could not get authentication service or credentials: {auth_e}")
                # We'll still try the normal fetch even without retry capability
            
            # Use the retry function if we have auth capabilities, otherwise use regular function
            if auth_service and username and password:
                html_content = await fetch_homework_with_retry(
                    cookies, 
                    lesson_id, 
                    page=page,
                    auth_service=auth_service,
                    username=username,
                    password=password,
                    lname_value=lname_value, 
                    timer_value=timer_value
                )
            else:
                html_content = await fetch_homework_for_lesson(cookies, lesson_id, lname_value, timer_value)
            
            if not html_content:
                logger.warning(f"No homework content returned for lesson {lesson_id} ({subject_code})")
                return None
            
            from glasir_timetable.api_client import parse_individual_lesson_response
            homework_text = parse_individual_lesson_response(html_content)
            
            if not homework_text:
                logger.info(f"No homework text found for lesson {lesson_id} ({subject_code})")
                return None
            
            # Create homework object
            homework = Homework(
                lesson_id=lesson_id,
                subject=subject_code,
                content=homework_text,
                date=datetime.now().strftime("%Y-%m-%d"),
                extracted_at=datetime.now().isoformat()
            )
            
            return homework
            
        except Exception as e:
            add_error("homework_extraction", f"Failed to extract homework for {subject_code} (lesson {lesson_id}): {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
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
        from glasir_timetable.api_client import (
            fetch_homework_for_lessons, 
            extract_lname_from_page, 
            extract_timer_value_from_page,
            parse_individual_lesson_response,
            fetch_homework_for_lessons_with_retry
        )
        
        results = {}
        
        if not lesson_ids:
            return results
        
        try:
            # Get cookies for API requests
            cookies = {}
            try:
                all_cookies = await page.context.cookies()
                cookies = {cookie['name']: cookie['value'] for cookie in all_cookies}
            except Exception as cookie_e:
                add_error("homework_extraction", f"Failed to get cookies for batch extraction: {cookie_e}")
                return results
            
            # Extract the lname value for the API request
            lname_value = await extract_lname_from_page(page)
            timer_value = await extract_timer_value_from_page(page)
            
            # Attempt to fetch the homework content for all lesson IDs in parallel
            # Try to get auth service for potential retry
            auth_service = None
            username = None
            password = None
            
            try:
                # Try to access service_factory and get credentials from the context
                from glasir_timetable.service_factory import get_service
                auth_service = get_service("authentication")
                
                # Try to get credentials from the environment or a credentials file
                credentials_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
                if os.path.exists(credentials_path):
                    with open(credentials_path, 'r') as f:
                        creds = json.load(f)
                        username = creds.get('username')
                        password = creds.get('password')
            except Exception as auth_e:
                logger.warning(f"Could not get authentication service or credentials: {auth_e}")
                # We'll still try the normal fetch even without retry capability
            
            # Use the retry function if we have auth capabilities, otherwise use regular function
            if auth_service and username and password:
                homework_map = await fetch_homework_for_lessons_with_retry(
                    cookies, 
                    lesson_ids, 
                    page=page,
                    auth_service=auth_service,
                    username=username,
                    password=password,
                    max_concurrent=batch_size,
                    lname_value=lname_value, 
                    timer_value=timer_value
                )
            else:
                homework_map = await fetch_homework_for_lessons(
                    cookies, lesson_ids, batch_size, lname_value, timer_value
                )
            
            if not homework_map:
                logger.warning(f"No homework content returned for any of the {len(lesson_ids)} lessons")
                return results
            
            # Convert the HTML responses to Homework objects
            lesson_to_subject = {}  # We'll try to collect this from nearby elements, but it's optional
            
            for lesson_id, html_content in homework_map.items():
                subject_code = lesson_to_subject.get(lesson_id, "Unknown")
                
                homework_text = parse_individual_lesson_response(html_content)
                
                if homework_text:
                    results[lesson_id] = Homework(
                        lesson_id=lesson_id,
                        subject=subject_code,
                        content=homework_text,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        extracted_at=datetime.now().isoformat()
                    )
            
            logger.info(f"Successfully extracted {len(results)}/{len(lesson_ids)} homework items")
            return results
            
        except Exception as e:
            add_error("homework_extraction_batch", f"Failed to extract homework batch: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return results
    
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