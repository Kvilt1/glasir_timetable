#!/usr/bin/env python3
"""
API client module for directly accessing Glasir's hidden homework API.

This module provides functions to fetch homework data using Glasir's note.asp endpoint.
"""

import time
import random
import logging
import httpx
import asyncio
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import re
import os
import json
from asyncio import Semaphore
import backoff # Using backoff decorator for retries

from playwright.async_api import Page

from glasir_timetable import logger
from glasir_timetable.extractors.homework_parser import clean_homework_text, parse_homework_html_response_structured
from glasir_timetable.extractors.teacher_map import parse_teacher_map_html_response
from .session import AuthSessionManager, get_dynamic_session_params
from .utils.error_utils import handle_errors, GlasirScrapingError
from .constants import (
    GLASIR_BASE_URL,
    DEFAULT_HEADERS,
    NOTE_ASP_URL,
    TEACHER_MAP_URL,
    TIMETABLE_INFO_URL,
)

logger = logging.getLogger(__name__)

async def extract_lname_from_page(page) -> Optional[str]:
    """
    Dynamically extract the lname value from the MyUpdate function on the page.
    
    Args:
        page: Playwright page object with access to the loaded timetable
        
    Returns:
        String containing the lname value in the format "Ford#####,##", or None if not found
        
    Note:
        This function is deprecated. Use get_dynamic_session_params from session module instead.
    """
    logger.warning("extract_lname_from_page is deprecated, use get_dynamic_session_params instead")
    try:
        lname, _ = await get_dynamic_session_params(page)
        return lname
    except Exception as e:
        logger.error(f"Error in extract_lname_from_page: {e}")
        return None

async def extract_timer_value_from_page(page) -> Optional[int]:
    """
    Extract the timer value used in the MyUpdate function.
    
    Args:
        page: Playwright page object with access to the loaded timetable
        
    Returns:
        Integer timer value or None if not found
        
    Note:
        This function is deprecated. Use get_dynamic_session_params from session module instead.
    """
    logger.warning("extract_timer_value_from_page is deprecated, use get_dynamic_session_params instead")
    try:
        _, timer = await get_dynamic_session_params(page)
        return timer
    except Exception as e:
        logger.error(f"Error in extract_timer_value_from_page: {e}")
        # Return a fallback value
        fallback = int(time.time() * 1000)
        logger.warning(f"Using fallback value due to error: {fallback}")
        return fallback

async def fetch_homework_for_lesson(
    cookies: Dict[str, str],
    lesson_id: str,
    lname_value: str = None,
    timer_value: int = None
) -> Optional[str]:
    """
    Fetch homework for a single lesson using the reliable individual lesson API function.
    This approach is guaranteed to work based on testing.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        HTML string containing the homework data, or None on error
    """
    try:
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/note.asp"
        
        # Get timer value if not provided
        if timer_value is None:
            timer_value = int(time.time() * 1000)
            
        # Use the exact parameter format from the working MyUpdate function
        params = {
            "fname": "Henry",
            "timex": timer_value,
            "rnd": random.random(),
            "MyInsertAreaId": "GlasirAPI",
            "lname": lname_value if lname_value else "Ford62860,32",  # Use the latest dynamic value if available
            "q": lesson_id,
            "MyFunktion": "ReadNotesToLessonWithLessonRID"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base_url}/132n/"
        }
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            if not response.text:
                logger.warning("Empty response received")
                
            return response.text
    except Exception as e:
        logger.error(f"Error fetching homework for lesson {lesson_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

async def _process_lesson(cookies: Dict[str, str], lesson_id: str, semaphore: asyncio.Semaphore, lname_value: str = None, timer_value: int = None) -> tuple[str, Optional[str]]:
    """
    Process a single lesson with semaphore limiting for concurrency control.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        semaphore: Semaphore to limit concurrent requests
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        Tuple of (lesson_id, homework_text or None)
    """
    async with semaphore:
        try:
            html_content = await fetch_homework_for_lesson(cookies, lesson_id, lname_value, timer_value)
            if html_content:
                homework_text = parse_individual_lesson_response(html_content)
                return lesson_id, homework_text
        except Exception as e:
            logger.error(f"Error processing homework for lesson {lesson_id}: {e}")
    
    return lesson_id, None

async def fetch_homework_for_lessons(
    cookies: Dict[str, str],
    lesson_ids: List[str],
    max_concurrent: int = 10,  # Limit concurrent requests to avoid overwhelming server
    lname_value: str = None,
    timer_value: int = None
) -> Dict[str, str]:
    """
    Fetch homework for multiple lessons using parallel requests with limited concurrency.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_ids: List of lesson IDs to fetch homework for
        max_concurrent: Maximum number of concurrent requests (default: 5)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        Dictionary mapping lesson IDs to their homework content
    """
    if not lesson_ids:
        return {}
    
    results = {}
    
    # Create a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Process all lesson IDs in parallel with limited concurrency
    tasks = [_process_lesson(cookies, lesson_id, semaphore, lname_value, timer_value) for lesson_id in lesson_ids]
    processed_results = await asyncio.gather(*tasks)
    
    # Filter out None values and add successful results to the result dictionary
    for lesson_id, homework_text in processed_results:
        if homework_text:
            results[lesson_id] = homework_text
    
    logger.info(f"Successfully fetched homework for {len(results)}/{len(lesson_ids)} lessons")
    return results

def parse_individual_lesson_response(html_content: str) -> Optional[str]:
    """
    Parse the HTML response from a single lesson homework request.
    
    Args:
        html_content: HTML string from the API response
        
    Returns:
        Extracted homework text or None if not found
    """
    if not html_content:
        return None
        
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Look for paragraphs with the white-space:pre-wrap style, which typically contains the homework
        paragraphs = soup.find_all('p', style=lambda s: s and 'white-space:pre-wrap' in s)
        
        if paragraphs:
            # Extract text from all relevant paragraphs
            homework_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
            return clean_homework_text(homework_text)
        
        # Fallback: try to find any paragraphs inside the response
        all_paragraphs = soup.find_all('p')
        if all_paragraphs:
            homework_text = "\n".join(p.get_text(strip=True) for p in all_paragraphs if p.get_text(strip=True))
            return clean_homework_text(homework_text)
            
    except Exception as e:
        logger.error(f"Error parsing individual lesson response: {e}")
        
    return None

def parse_homework_html_response(html_content: str) -> Dict[str, str]:
    """
    Parse the HTML response from the note.asp API to extract homework content.
    This function is kept for backward compatibility with any code that may use it.
    
    Args:
        html_content: HTML string from the API response
        
    Returns:
        Dictionary mapping lesson IDs to their corresponding homework text
    """
    homework_map = {}
    
    if not html_content:
        logger.warning("No HTML content to parse")
        return homework_map
        
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Look for hidden input fields containing lesson and note IDs
        lesson_inputs = soup.find_all('input', {'id': re.compile(r'^LektionsID')})
        
        # Process each lesson section
        for lesson_input in lesson_inputs:
            lesson_id = lesson_input.get('value')
            if not lesson_id:
                continue
                
            # Find the paragraph containing the homework text
            # This is based on the observed structure in our tests
            homework_paragraphs = soup.find_all('p', style=re.compile(r'white-space:pre-wrap'))
            
            for paragraph in homework_paragraphs:
                # Extract the text content
                homework_text = paragraph.get_text(strip=True)
                if homework_text:
                    homework_map[lesson_id] = homework_text
                    break
        
        logger.info(f"Extracted homework for {len(homework_map)} lessons")
        
    except Exception as e:
        logger.error(f"Error parsing homework HTML: {e}")
        
    return homework_map

async def analyze_lname_values(page) -> Dict[str, Any]:
    """
    Comprehensive analysis of all potential lname values on the page.
    
    Args:
        page: Playwright page object
        
    Returns:
        Dictionary with analysis results
    """
    results = {
        "myupdate_function_exists": False,
        "potential_lname_values": [],
        "page_url": page.url,
        "page_title": await page.title(),
        "html_snippet": ""
    }
    
    try:
        # Check if we're on a timetable page
        results["timetable_found"] = await page.locator("table.time_8_16").count() > 0
        
        # Check if MyUpdate function exists
        results["myupdate_function_exists"] = await page.evaluate("typeof MyUpdate === 'function'")
        
        # Get all potential lname values from various sources
        analysis_script = """() => {
            const results = {
                from_myupdate: null,
                from_source: [],
                from_scripts: [],
                from_window: null
            };
            
            // Try to extract from MyUpdate if it exists
            if (typeof MyUpdate === 'function') {
                const myUpdateStr = MyUpdate.toString();
                const lnameMatch = myUpdateStr.match(/lname=([^&"]+)/);
                results.from_myupdate = lnameMatch ? lnameMatch[1] : null;
                
                // Get all potential lname values from MyUpdate
                const allLnameMatches = myUpdateStr.match(/lname=([^&"]+)/g);
                if (allLnameMatches) {
                    results.from_source = allLnameMatches.map(m => m.replace('lname=', ''));
                }
            }
            
            // Look for lname in any script on the page
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const script of scripts) {
                if (script.textContent) {
                    const scriptLnameMatches = script.textContent.match(/lname=([^&"]+)/g);
                    if (scriptLnameMatches) {
                        const values = scriptLnameMatches.map(m => m.replace('lname=', ''));
                        results.from_scripts.push(...values);
                    }
                }
            }
            
            // Check if lname is available in any global variables
            if (typeof window.lname !== 'undefined') {
                results.from_window = window.lname;
            }
            
            return results;
        }"""
        
        lname_analysis = await page.evaluate(analysis_script)
        results["lname_analysis"] = lname_analysis
        
        # Get the list of unique values
        all_values = []
        if lname_analysis.get('from_myupdate'):
            all_values.append(lname_analysis['from_myupdate'])
        all_values.extend(lname_analysis.get('from_source', []))
        all_values.extend(lname_analysis.get('from_scripts', []))
        if lname_analysis.get('from_window'):
            all_values.append(lname_analysis['from_window'])
        
        # Remove duplicates
        unique_values = list(set(all_values))
        results["potential_lname_values"] = unique_values
        
        # Get HTML snippet that might contain relevant info
        html_snippet = await page.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const script of scripts) {
                if (script.textContent && script.textContent.includes('lname=')) {
                    return script.textContent.substring(0, 500) + '...';
                }
            }
            return '';
        }""")
        
        results["html_snippet"] = html_snippet
        
    except Exception as e:
        logger.error(f"Error analyzing lname values: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    return results 

async def fetch_homework_with_retry(
    cookies: Dict[str, str],
    lesson_id: str,
    page: Page = None,
    auth_service = None,
    username: str = None,
    password: str = None,
    lname_value: str = None,
    timer_value: int = None,
    max_retries: int = 2
) -> Optional[str]:
    """
    Fetch homework for a lesson with retry and re-authentication logic.
    
    This function will first attempt to fetch homework using the provided cookies.
    If that fails with a specific type of error (like DNS resolution), it will:
    1. Re-authenticate using auth_service
    2. Extract fresh lname_value and timer_value
    3. Retry the homework fetch with the new credentials
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        page: The Playwright page object (needed for re-authentication)
        auth_service: AuthenticationService instance for re-login
        username: Username for re-authentication
        password: Password for re-authentication
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        max_retries: Maximum number of retry attempts (default: 2)
        
    Returns:
        HTML string containing the homework data, or None on error
    """
    # First attempt with existing cookies
    try:
        result = await fetch_homework_for_lesson(
            cookies, lesson_id, lname_value, timer_value
        )
        if result:
            return result
    except Exception as e:
        # Check if it's a DNS resolution error or other connection-related issue
        is_dns_error = "[Errno 8] nodename nor servname provided, or not known" in str(e)
        is_connection_error = "ConnectionError" in str(e) or "Connection refused" in str(e)
        
        if not (is_dns_error or is_connection_error):
            # If it's some other error, just raise it
            logger.error(f"Non-connection error during homework fetch: {e}")
            return None
        
        logger.warning(f"Connection error during homework fetch: {e}")
        
        # If we don't have what we need for re-authentication, we can't retry
        if not all([page, auth_service, username, password]):
            logger.error("Cannot retry with re-authentication: missing required parameters")
            return None
        
        # Retry with re-authentication
        for retry in range(max_retries):
            try:
                logger.info(f"Retry attempt {retry+1}/{max_retries} with re-authentication")
                
                # Re-authenticate
                login_success = await auth_service.login(username, password, page)
                if not login_success:
                    logger.error("Re-authentication failed")
                    continue
                
                # Get fresh cookies from the page context
                fresh_cookies = await page.context.cookies()
                cookies_dict = {cookie['name']: cookie['value'] for cookie in fresh_cookies}
                
                # Extract fresh lname value and timer value
                fresh_lname = await extract_lname_from_page(page)
                fresh_timer = await extract_timer_value_from_page(page)
                
                # Retry the fetch with fresh values
                result = await fetch_homework_for_lesson(
                    cookies_dict, lesson_id, fresh_lname, fresh_timer
                )
                
                if result:
                    logger.info(f"Successfully fetched homework after re-authentication")
                    return result
                    
            except Exception as retry_e:
                logger.error(f"Error during retry {retry+1}: {retry_e}")
                
    return None

async def fetch_homework_for_lessons_with_retry(
    cookies: Dict[str, str],
    lesson_ids: List[str],
    page: Page = None,
    auth_service = None,
    username: str = None,
    password: str = None,
    max_concurrent: int = 10,
    lname_value: str = None,
    timer_value: int = None
) -> Dict[str, str]:
    """
    Fetch homework for multiple lessons with retry and re-authentication logic.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_ids: List of lesson IDs to fetch homework for
        page: The Playwright page object (needed for re-authentication)
        auth_service: AuthenticationService instance for re-login
        username: Username for re-authentication
        password: Password for re-authentication
        max_concurrent: Maximum number of concurrent requests
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        Dictionary mapping lesson IDs to their homework content
    """
    if not lesson_ids:
        return {}
    
    results = {}
    retry_needed = False
    retry_auth_performed = False
    
    try:
        # Try the normal parallel fetch first
        results = await fetch_homework_for_lessons(
            cookies, lesson_ids, max_concurrent, lname_value, timer_value
        )
        
        # If we got at least one result, consider it a partial success
        if results:
            # If we got all lessons, we're done
            if len(results) == len(lesson_ids):
                return results
            
            # Otherwise, we'll need to retry the missing ones
            retry_needed = True
            lesson_ids = [lesson_id for lesson_id in lesson_ids if lesson_id not in results]
    except Exception as e:
        # Check if it's a connection-related error
        is_dns_error = "[Errno 8] nodename nor servname provided, or not known" in str(e)
        is_connection_error = "ConnectionError" in str(e) or "Connection refused" in str(e)
        
        if is_dns_error or is_connection_error:
            logger.warning(f"Connection error during batch homework fetch: {e}")
            retry_needed = True
        else:
            logger.error(f"Error during batch homework fetch: {e}")
            return results  # Return whatever we might have gathered before the error
    
    # If we need to retry and have the means to re-authenticate
    if retry_needed and all([page, auth_service, username, password]):
        try:
            if not retry_auth_performed:
                logger.info("Re-authenticating before retrying failed lessons")
                
                # Re-authenticate
                login_success = await auth_service.login(username, password, page)
                if not login_success:
                    logger.error("Re-authentication failed")
                    return results
                
                # Get fresh cookies from the page context
                fresh_cookies = await page.context.cookies()
                cookies_dict = {cookie['name']: cookie['value'] for cookie in fresh_cookies}
                
                # Extract fresh lname value and timer value
                fresh_lname = await extract_lname_from_page(page)
                fresh_timer = await extract_timer_value_from_page(page)
                
                retry_auth_performed = True
                
                # Try again with fresh values
                retry_results = await fetch_homework_for_lessons(
                    cookies_dict, lesson_ids, max_concurrent, fresh_lname, fresh_timer
                )
                
                if retry_results:
                    # Merge the results
                    results.update(retry_results)
        except Exception as retry_e:
            logger.error(f"Error during retry with re-authentication: {retry_e}")
    
    return results 

async def fetch_teacher_mapping(
    cookies: Dict[str, str],
    lname_value: str = None,
    timer_value: int = None
) -> Dict[str, str]:
    """
    Fetch teacher mapping data directly using the teachers.asp endpoint without navigating the page.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        Dictionary mapping teacher initials to full names
    """
    try:
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/teachers.asp"
        
        # Get timer value if not provided
        if timer_value is None:
            timer_value = int(time.time() * 1000)
            
        # Use the parameter format observed in the HAR file
        params = {
            "fname": "Henry",
            "timex": timer_value,
            "rnd": random.random(),
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford28731,48",
            "q": "teach",
            "v": "0",
            "id": "a"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base_url}/132n/"
        }
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            if not response.text:
                logger.warning("Empty response received from teacher mapping request")
                return {}
                
            # Parse the HTML to extract teacher mapping
            return parse_teacher_map_html_response(response.text)
            
    except Exception as e:
        logger.error(f"Error fetching teacher mapping: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}

def parse_teacher_html_response(html_content: str) -> Dict[str, str]:
    """
    Parse the HTML response from the teachers.asp endpoint to extract teacher mapping.
    
    Args:
        html_content: HTML string from the API response
        
    Returns:
        Dictionary mapping teacher initials to full names
    """
    teacher_map = {}
    
    try:
        # Pattern to extract teacher name and initials
        pattern = r'([^<>]+?)\s*\(\s*<a [^>]*?onclick="[^"]*?teach([A-Z]{2,4})[^"]*?"[^>]*?>([A-Z]{2,4})</a>\s*\)'
        matches = re.findall(pattern, html_content)
        
        for match in matches:
            full_name = match[0].strip()
            initials = match[2].strip()  # Using the visible initials
            teacher_map[initials] = full_name
        
        # If we didn't get enough teachers, try a simpler pattern
        if len(teacher_map) < 10:
            pattern2 = r'([^<>]+?)\s*\(\s*<a [^>]*?>([A-Z]{2,4})</a>\s*\)'
            matches = re.findall(pattern2, html_content)
            
            for match in matches:
                full_name = match[0].strip()
                initials = match[1].strip()
                if initials not in teacher_map:
                    teacher_map[initials] = full_name
        
        logger.info(f"Extracted {len(teacher_map)} teachers from API response")
        
    except Exception as e:
        logger.error(f"Error parsing teacher HTML: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    return teacher_map

async def fetch_weeks_data(
    cookies: Dict[str, str],
    student_id: str,
    lname_value: str = None,
    timer_value: int = None,
    v_override: str = None
) -> Dict[str, Any]:
    """
    Fetch all available weeks data directly using the udvalg.asp endpoint without navigating the page.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        student_id: The student ID (GUID) for the current user
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        v_override: Override for the 'v' parameter to access different academic years
        
    Returns:
        Dictionary containing weeks data with week numbers, offsets, and dates
    """
    try:
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/udvalg.asp"
        
        # Get timer value if not provided
        if timer_value is None:
            timer_value = int(time.time() * 1000)
            
        # Use the parameter format observed in the HAR file
        params = {
            "fname": "Henry",
            "timex": timer_value,
            "rnd": random.random(),
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford28731,48",
            "q": "stude",
            "id": student_id,
            "v": v_override if v_override is not None else "-1"  # Use override value if provided
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base_url}/132n/"
        }
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            if not response.text:
                logger.warning("Empty response received from weeks data request")
                return {"weeks": [], "current_week": None}
                
            # Parse the HTML to extract weeks data
            return parse_weeks_html_response(response.text)
            
    except Exception as e:
        logger.error(f"Error fetching weeks data: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"weeks": [], "current_week": None}

def parse_weeks_html_response(html_content: str) -> Dict[str, Any]:
    """
    Parse the HTML response from the udvalg.asp endpoint to extract weeks data.
    
    Args:
        html_content: HTML string from the API response
        
    Returns:
        Dictionary containing:
        - weeks: List of dictionaries with week data (number, offset, date range)
        - current_week: Information about the currently selected week
    """
    result = {
        "weeks": [],
        "current_week": None
    }
    
    if not html_content:
        logger.warning("Empty HTML content provided to weeks parser")
        return result
        
    try:
        # Log a snippet of the HTML for debugging
        html_snippet = html_content[:500] + "..." if len(html_content) > 500 else html_content
        logger.debug(f"Parsing weeks data from HTML snippet: {html_snippet}")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract date range for the current week using multiple methods
        date_range_text = None
        
        # Method 1: Look for date patterns in text
        for text in soup.stripped_strings:
            if re.match(r'\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}', text):
                date_range_text = text
                logger.debug(f"Found date range using method 1: {date_range_text}")
                break
        
        # Method 2: Look for specific elements that often contain date ranges
        if not date_range_text:
            date_containers = soup.select('.UgeTekst, .CurrentWeekText, div.WeekDate')
            for container in date_containers:
                text = container.get_text(strip=True)
                if re.search(r'\d{2}\.\d{2}\.\d{4}', text):
                    date_range_text = text
                    logger.debug(f"Found date range using method 2: {date_range_text}")
                    break
                
        # Extract all week links with detailed error tracking
        css_selectors = [
            'a.UgeKnap', 'a.UgeKnapValgt', 'a.UgeKnapAktuel',  # Primary selectors
            'a[onclick*="v="]'                                  # Fallback selector
        ]
        
        week_links = soup.select(', '.join(css_selectors))
        logger.debug(f"Found {len(week_links)} week links using selectors: {css_selectors}")
        
        if not week_links:
            logger.warning("No week links found with primary selectors, attempting alternative approach")
            # Alternative approach: Find all links with 'onclick' containing 'v='
            week_links = soup.find_all('a', onclick=lambda v: v and 'v=' in v)
            logger.debug(f"Found {len(week_links)} week links using alternative approach")
            
            if not week_links:
                # Try another approach with broader matching
                all_links = soup.find_all('a')
                week_links = [link for link in all_links if link.get('onclick') and 'v=' in link.get('onclick')]
                logger.debug(f"Found {len(week_links)} week links using broadest approach")
                
        week_count = 0
        for link in week_links:
            try:
                week_data = {}
                
                # Extract week number
                week_number = link.text.strip()
                if week_number.startswith("Vika "):
                    week_number = week_number.replace("Vika ", "")
                week_data["week_number"] = week_number
                
                # Extract onclick attribute to get the week offset
                onclick = link.get('onclick', '')
                if not onclick:
                    logger.warning(f"Week link missing onclick attribute: {link}")
                    continue
                    
                offset_match = re.search(r'v=(-?\d+)', onclick)
                if offset_match:
                    week_data["offset"] = int(offset_match.group(1))
                else:
                    logger.warning(f"Cannot extract offset from onclick: {onclick}")
                    continue  # Skip if we can't get the offset
                
                # Determine if this is the current week
                css_classes = link.get('class', [])
                is_current = any(cls in css_classes for cls in ['UgeKnapValgt', 'UgeKnapAktuel'])
                week_data["is_current"] = is_current
                
                if is_current:
                    if date_range_text:
                        week_data["date_range"] = date_range_text
                    result["current_week"] = week_data.copy()  # Use copy to avoid reference issues
                
                result["weeks"].append(week_data)
                week_count += 1
            except Exception as e:
                logger.warning(f"Error processing week link {link}: {e}")
                continue  # Skip this link and continue with others
        
        # Check if we got at least some useful data
        if week_count == 0:
            logger.error("Failed to extract any valid week data")
            # Save HTML to debug file if we couldn't extract any data
            try:
                debug_path = "debug_weeks_html.html"
                with open(debug_path, "w") as f:
                    f.write(html_content)
                logger.info(f"Saved problematic HTML to {debug_path} for debugging")
            except Exception as save_err:
                logger.warning(f"Could not save debug HTML: {save_err}")
        else:
            logger.info(f"Successfully extracted {week_count} weeks from API response")
            
            # Sort weeks by offset for easier processing
            result["weeks"].sort(key=lambda w: w.get("offset", 0))
            
            # If we didn't find a current week, try to infer it
            if not result["current_week"] and result["weeks"]:
                # The current week typically has offset 0, or is the closest to 0
                closest_to_zero = min(result["weeks"], key=lambda w: abs(w.get("offset", 0)))
                logger.info(f"Inferred current week with offset {closest_to_zero.get('offset')} as no explicit current week was marked")
                result["current_week"] = closest_to_zero
        
    except Exception as e:
        logger.error(f"Error parsing weeks HTML: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Try to save HTML for debugging serious errors
        try:
            debug_path = "debug_weeks_html_error.html"
            with open(debug_path, "w") as f:
                f.write(html_content)
            logger.info(f"Saved HTML with parse error to {debug_path}")
        except Exception:
            pass
    
    return result

async def fetch_timetable_for_week(
    cookies: Dict[str, str],
    student_id: str,
    week_offset: int = 0,
    lname_value: str = None,
    timer_value: int = None
) -> Optional[str]:
    """
    Fetch the timetable HTML for a specific week using the udvalg.asp endpoint.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        student_id: The student ID (GUID) for the current user
        week_offset: Offset from the current week (-1 for previous week, etc.)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        HTML string containing the timetable, or None on error
    """
    try:
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/udvalg.asp"
        
        # Get timer value if not provided
        if timer_value is None:
            timer_value = int(time.time() * 1000)
            
        # Use the parameter format observed in the HAR file
        params = {
            "fname": "Henry",
            "timex": timer_value,
            "rnd": random.random(),
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford28731,48",
            "q": "stude",
            "id": student_id,
            "v": str(week_offset)  # Convert to string as seen in the HAR file
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base_url}/132n/"
        }
        
        logger.info(f"Fetching timetable for week offset {week_offset} with lname={lname_value}")
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            if not response.text:
                logger.warning("Empty response received from timetable request")
                return None
                
            return response.text
            
    except Exception as e:
        logger.error(f"Error fetching timetable for week {week_offset}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None 

async def _fetch_single_timetable_with_semaphore(
    semaphore: Semaphore,
    cookies: Dict[str, str],
    student_id: str,
    week_offset: int,
    lname_value: str = None,
    timer_value: int = None
) -> tuple[int, Optional[str]]:
    """Helper function to fetch a single week's timetable within a semaphore context."""
    async with semaphore:
        logger.debug(f"Acquired semaphore for fetching week offset {week_offset}")
        try:
            html_content = await fetch_timetable_for_week(
                cookies=cookies,
                student_id=student_id,
                week_offset=week_offset,
                lname_value=lname_value,
                timer_value=timer_value
            )
            return week_offset, html_content
        finally:
            logger.debug(f"Released semaphore for week offset {week_offset}")

async def fetch_timetables_for_weeks(
    cookies: Dict[str, str],
    student_id: str,
    week_offsets: List[int],
    max_concurrent: int = 5,  # Limit concurrent requests for timetables
    lname_value: str = None,
    timer_value: int = None
) -> Dict[int, Optional[str]]:
    """
    Fetch timetable HTML for multiple weeks concurrently.

    Args:
        cookies: Dictionary of cookies from the current browser session.
        student_id: The student ID (GUID) for the current user.
        week_offsets: A list of week offsets to fetch timetables for.
        max_concurrent: Maximum number of concurrent requests.
        lname_value: Optional dynamically extracted lname value.
        timer_value: Optional timer value extracted from the page.

    Returns:
        A dictionary mapping each week_offset to its corresponding HTML timetable string,
        or None if an error occurred for that specific week.
    """
    if not week_offsets:
        return {}

    semaphore = Semaphore(max_concurrent)
    tasks = []
    
    # Reuse timer_value if provided, otherwise get a new one (consistent across requests)
    current_timer_value = timer_value if timer_value is not None else int(time.time() * 1000)

    for offset in week_offsets:
        task = asyncio.create_task(
            _fetch_single_timetable_with_semaphore(
                semaphore=semaphore,
                cookies=cookies,
                student_id=student_id,
                week_offset=offset,
                lname_value=lname_value,
                timer_value=current_timer_value # Use consistent timer value
            )
        )
        tasks.append(task)

    logger.info(f"Fetching timetables for {len(week_offsets)} weeks with max concurrency {max_concurrent}")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Finished fetching all specified weeks.")

    timetable_data = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error fetching timetable during concurrent fetch: {result}")
            # Cannot easily map back to week_offset if an exception occurred *before* calling the helper
            # Consider adding offset to exception context if needed later
        elif result is not None:
            offset, html_content = result
            timetable_data[offset] = html_content
        # Handle cases where the helper might return None or unexpected format (though it shouldn't)
        
    # Ensure all requested offsets are keys in the result, even if fetching failed
    for offset in week_offsets:
        if offset not in timetable_data:
             timetable_data[offset] = None # Mark as failed/not found

    return timetable_data 

async def get_student_id(page) -> Optional[str]:
    """
    Extract the student ID (GUID) from the current page.
    
    Args:
        page: Playwright page object with access to the loaded timetable
        
    Returns:
        String containing the student ID, or None if not found
    """
    try:
        # Try extracting from MyUpdate function if it exists
        has_my_update = await page.evaluate("typeof MyUpdate === 'function'")
        
        if has_my_update:
            student_id = await page.evaluate("""() => {
                if (typeof MyUpdate !== 'function') {
                    return null;
                }
                
                // Extract from MyUpdate function
                const myUpdateStr = MyUpdate.toString();
                const idMatch = myUpdateStr.match(/[&?]id=([0-9a-fA-F-]{36})/);
                return idMatch ? idMatch[1] : null;
            }""")
            
            if student_id:
                logger.info(f"Extracted student ID from MyUpdate function: {student_id[:5]}...")
                return student_id
        
        # Try extracting from the URL if present
        url = page.url
        id_match = re.search(r'[?&]id=([0-9a-fA-F-]{36})', url)
        if id_match:
            student_id = id_match.group(1)
            logger.info(f"Extracted student ID from URL: {student_id[:5]}...")
            return student_id
            
        # Try looking in the page source
        student_id = await page.evaluate("""() => {
            // Search for GUID pattern in any script
            const guidPattern = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;
            
            // Check scripts first
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const script of scripts) {
                if (script.textContent) {
                    const match = script.textContent.match(guidPattern);
                    if (match) {
                        return match[0];
                    }
                }
            }
            
            // Check for any links containing id parameter with GUID
            const links = Array.from(document.querySelectorAll('a[href*="id="]'));
            for (const link of links) {
                const match = link.href.match(/[?&]id=([0-9a-fA-F-]{36})/);
                if (match) {
                    return match[1];
                }
            }
            
            // Look in page source as last resort
            const pageSource = document.documentElement.outerHTML;
            const sourceMatch = pageSource.match(guidPattern);
            return sourceMatch ? sourceMatch[0] : null;
        }""")
        
        if student_id:
            logger.info(f"Extracted student ID from page source: {student_id[:5]}...")
            return student_id
            
        logger.warning("Could not extract student ID from the page")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting student ID: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None 

class ApiClient:
    """Client for interacting with Glasir's API endpoints."""
    
    def __init__(self, client: httpx.AsyncClient, session_manager: AuthSessionManager):
        """Initialize the API client with an HTTP client and session manager."""
        self._client = client
        self._session_manager = session_manager
        
    async def initialize_session_params(self, page: Optional[Page] = None) -> None:
        """
        Initialize session parameters (lname and timer) using the new minimized approach.
        
        Args:
            page: Authenticated Playwright page object
        """
        if page:
            # Use the minimized extraction approach
            lname, timer = await get_dynamic_session_params(page)
            
            # Update session manager with these values
            if lname:
                self._session_manager._lname = lname
                self._session_manager._cached_params["lname"] = lname
            if timer:
                self._session_manager._timer = str(timer)  # Convert to string as expected by session manager
                self._session_manager._cached_params["timer"] = str(timer)
        else:
            # Fall back to the standard fetching mechanism
            await self._session_manager.fetch_and_cache_params()

    @handle_errors(default_return=None, error_category="fetching_homework_details")
    @backoff.on_exception(backoff.expo,
                          (httpx.RequestError, httpx.HTTPStatusError, GlasirScrapingError),
                          max_tries=3,
                          logger=logger,
                          on_backoff=lambda details: logger.warning(f"Retrying homework fetch in {details['wait']:.1f}s after {details['tries']} tries. Error: {details['exception']}"))
    async def fetch_homework_details(self, lesson_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch homework details for a specific lesson.
        
        Args:
            lesson_id: ID of the lesson to fetch homework for.
            student_id: ID of the student.
            
        Returns:
            Dict with structured homework data or None if request failed.
        """
        # Get dynamic parameters from session manager
        params = await self._session_manager.get_params()
        
        payload = {
            "id": lesson_id,
            "elev": student_id, # Assuming 'elev' is the correct param for student ID here
            "lname": params["lname"],
            "timer": params["timer"],
        }
        logger.debug(f"Fetching homework for lesson {lesson_id} with payload: {payload}")

        try:
            response = await self._client.post(
                NOTE_ASP_URL, data=payload, headers=DEFAULT_HEADERS
            )
            response.raise_for_status() # Check for HTTP errors

            # Delegate parsing to the extractor
            homework_data = parse_homework_html_response_structured(response.text)
            logger.debug(f"Successfully fetched and parsed homework for lesson {lesson_id}.")
            return homework_data

        except httpx.RequestError as e:
            logger.error(f"Request failed for lesson {lesson_id}: {e}")
            raise GlasirScrapingError(f"Network error fetching homework for lesson {lesson_id}") from e
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP error {e.response.status_code} for lesson {lesson_id}: {e.response.text[:200]}")
             if e.response.status_code >= 500:
                 raise GlasirScrapingError(f"Server error ({e.response.status_code}) fetching homework for lesson {lesson_id}") from e
             else: # Treat 4xx as potentially recoverable/ignorable depending on caller
                 logger.warning(f"Client error ({e.response.status_code}) fetching homework for lesson {lesson_id}.")
                 return None # Or raise specific error? Returning None for now.
        except Exception as e:
            logger.exception(f"Unexpected error parsing homework for lesson {lesson_id}: {e}")
            # Reraise unexpected errors if not handled by @handle_errors
            raise GlasirScrapingError(f"Parsing error for homework lesson {lesson_id}") from e

    @handle_errors(default_return={}, error_category="fetching_teacher_map")
    @backoff.on_exception(backoff.expo,
                          (httpx.RequestError, httpx.HTTPStatusError, GlasirScrapingError),
                          max_tries=3,
                          logger=logger,
                          on_backoff=lambda details: logger.warning(f"Retrying teacher map fetch in {details['wait']:.1f}s after {details['tries']} tries. Error: {details['exception']}"))
    async def fetch_teacher_map(self, student_id: str) -> Dict[str, str]:
        """
        Fetches the teacher initials to full name mapping using the laerer.asp endpoint.

        Args:
            student_id: The ID of the student.

        Returns:
            A dictionary mapping teacher initials to full names, or {} on failure.
        """
        params = await self._session_manager.get_params()
        payload = {
            "elev": student_id, # Assuming 'elev' is the correct param
            "lname": params["lname"],
            "timer": params["timer"],
        }
        logger.debug("Fetching teacher map with payload: %s", payload)
        try:
            response = await self._client.post(
                TEACHER_MAP_URL, data=payload, headers=DEFAULT_HEADERS
            )
            response.raise_for_status()

            # Delegate parsing to the extractor
            teacher_map = parse_teacher_map_html_response(response.text)
            logger.info(f"Successfully fetched and parsed teacher map ({len(teacher_map)} entries).")
            return teacher_map

        except httpx.RequestError as e:
            logger.error(f"Request failed for teacher map: {e}")
            raise GlasirScrapingError("Network error fetching teacher map") from e
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP error {e.response.status_code} for teacher map: {e.response.text[:200]}")
             raise GlasirScrapingError(f"HTTP error ({e.response.status_code}) fetching teacher map") from e
        except Exception as e:
            logger.exception(f"Unexpected error parsing teacher map: {e}")
            raise GlasirScrapingError("Parsing error for teacher map") from e

    @handle_errors(default_return=None, error_category="fetching_timetable_info")
    @backoff.on_exception(backoff.expo,
                          (httpx.RequestError, httpx.HTTPStatusError, GlasirScrapingError),
                          max_tries=3,
                          logger=logger,
                          on_backoff=lambda details: logger.warning(f"Retrying timetable info fetch in {details['wait']:.1f}s after {details['tries']} tries. Error: {details['exception']}"))
    async def fetch_timetable_info_for_week(self, student_id: str, week_number: int, year: int) -> Optional[Dict[str, Any]]:
        """
        Fetches timetable structure and week info using the skema_data.asp endpoint.

        Args:
            student_id: The ID of the student.
            week_number: The week number.
            year: The year.

        Returns:
            A dictionary containing parsed timetable and week info, or None on failure.
        """
        params = await self._session_manager.get_params()
        payload = {
            "elev": student_id, # Assuming 'elev' is correct
            "uge": f"{week_number:02d}{str(year)[-2:]}", # Format: WWYY
            "lname": params["lname"],
            "timer": params["timer"],
        }
        logger.debug(f"Fetching timetable info for week {week_number}/{year} with payload: {payload}")
        try:
            response = await self._client.post(
                TIMETABLE_INFO_URL, data=payload, headers=DEFAULT_HEADERS
            )
            response.raise_for_status()

            # For now, we'll just return the raw HTML until we adapt the timetable parser
            # In the future, we'll use a proper parser from extractors/timetable.py
            logger.debug(f"Successfully fetched timetable info for week {week_number}/{year}.")
            return {"html_content": response.text, "needs_parsing": True}

        except httpx.RequestError as e:
            logger.error(f"Request failed for timetable info week {week_number}/{year}: {e}")
            raise GlasirScrapingError(f"Network error fetching timetable info for week {week_number}/{year}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for timetable info week {week_number}/{year}: {e.response.text[:200]}")
            raise GlasirScrapingError(f"HTTP error ({e.response.status_code}) fetching timetable info week {week_number}/{year}") from e
        except Exception as e:
            logger.exception(f"Unexpected error for timetable info week {week_number}/{year}: {e}")
            raise GlasirScrapingError(f"Error processing timetable info week {week_number}/{year}") from e 