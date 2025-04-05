#!/usr/bin/env python3
"""
API client for Glasir Timetable.

This module provides utilities for interacting with the Glasir Timetable API.
"""

import time
import random
import logging
import httpx
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode
from bs4 import BeautifulSoup, Tag
import re
import os
import json
from asyncio import Semaphore
import backoff # Using backoff decorator for retries

from playwright.async_api import Page

from glasir_timetable import logger, raw_response_config
from glasir_timetable.extractors.homework_parser import clean_homework_text, parse_homework_html_response_structured
from glasir_timetable.utils.file_utils import save_raw_response
from .session import AuthSessionManager
from .utils.error_utils import handle_errors, GlasirScrapingError
from .utils.param_utils import parse_dynamic_params
from .constants import (
    GLASIR_BASE_URL,
    DEFAULT_HEADERS,
    NOTE_ASP_URL,
    TEACHER_MAP_URL,
    TIMETABLE_INFO_URL,
    TEACHER_CACHE_FILE,
)
from glasir_timetable.student_utils import get_student_id

# Use the package-level logger for consistency

@handle_errors(default_return={}, error_category="parsing_teacher_map_html")
def parse_teacher_map_html_response(html_content: str) -> Dict[str, str]:
    """
    Parses the HTML response from the laerer.asp endpoint to extract the teacher map.

    Args:
        html_content: The HTML content string from the teacher map endpoint.

    Returns:
        A dictionary mapping teacher initials to full names. Returns {} on failure or if no teachers found.
    """
    if not html_content:
        logger.warning("Received empty content for teacher map parsing.")
        return {}

    soup = BeautifulSoup(html_content, "lxml")
    teacher_map = {}

    try:
        # First try the traditional select element approach
        # Find the select element containing teacher options
        select_element = soup.find("select")  # Assuming there's only one relevant select
        if not select_element:
            # Try finding by a known name attribute if ID is unreliable
            select_element = soup.find("select", {"name": "laerer"})  # Example name
            if not select_element:
                logger.warning("Could not find the select element containing teacher options in HTML. Trying alternative extraction method.")
                # Instead of raising an error, try the alternative approach
                raise ValueError("Select element not found")

        options = select_element.find_all("option")
        if not options:
            logger.warning("No teacher <option> tags found within the select element. Trying alternative extraction method.")
            raise ValueError("No options found in select element")

        for option in options:
            if isinstance(option, Tag):
                initials = option.get("value")
                full_name = option.get_text(strip=True)

                # Basic validation and cleanup
                if initials and full_name and initials != "-1":  # Skip placeholder values
                    # Sometimes the name might contain the initials e.g., "ABC - Anders B. Christensen"
                    # Attempt to clean this up
                    if f"{initials} -" in full_name:
                        cleaned_name = full_name.split(f"{initials} -", 1)[-1].strip()
                        if cleaned_name:  # Use cleaned name only if it's not empty
                            full_name = cleaned_name
                        else:  # If cleaning results in empty, keep original (edge case)
                            logger.debug(f"Cleaning resulted in empty name for initials {initials}, keeping original: {full_name}")

                    # Further cleanup: Remove potential "(initials)" suffix if present
                    if full_name.endswith(f"({initials})"):
                        full_name = full_name[:-len(f"({initials})")].strip()

                    if initials in teacher_map and teacher_map[initials] != full_name:
                        logger.warning(f"Duplicate teacher initials '{initials}' found with different names: '{teacher_map[initials]}' vs '{full_name}'. Keeping the latter.")
                    teacher_map[initials] = full_name

        if not teacher_map:
            logger.warning("Parsed teacher map HTML but extracted no valid teacher entries. Trying alternative extraction method.")
            raise ValueError("No teachers extracted from select element")
        else:
            logger.info(f"Successfully parsed {len(teacher_map)} teachers from HTML select element.")

    except (ValueError, GlasirScrapingError):
        # If the select element approach fails, try the alternative regex-based approach
        logger.info("Trying alternative teacher extraction method using regex patterns.")
        teacher_map = extract_teachers_from_html(html_content)
        
        if not teacher_map:
            logger.warning("Alternative extraction method also failed to extract teacher information.")
        else:
            logger.info(f"Successfully extracted {len(teacher_map)} teachers using alternative method.")

    return teacher_map

def extract_teachers_from_html(html_content: str) -> Dict[str, str]:
    """
    Extract teacher mapping from HTML content using regex patterns.
    This is an alternative method when the select element approach fails.
    
    Args:
        html_content: The HTML content string to extract from.
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
    teacher_map = {}
    
    try:
        # Several regex patterns to try extracting teacher information
        patterns = [
            # Pattern 1: Name (XXX) where XXX is 2-4 uppercase letters with an <a> tag
            r'([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)',
            
            # Pattern 2: Name (XXX) with onclick attribute
            r'([^<>]+?)\s*\(\s*<a [^>]*?onclick="[^"]*?teach([A-Z]{2,4})[^"]*?"[^>]*?>([A-Z]{2,4})</a>\s*\)',
            
            # Pattern 3: Simple Name (XXX) pattern without HTML tags
            r'([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)',
            
            # Pattern 4: Teacher listing with separator
            r'([^<>:]+?)\s*:\s*([A-Z]{2,4})'
        ]
        
        # Try patterns in sequence, stopping if we find enough teachers
        for pattern_index, pattern in enumerate(patterns):
            matches = re.findall(pattern, html_content)
            
            # Process matches based on the pattern format
            if pattern_index == 0:  # Pattern 1
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    teacher_map[initials] = full_name
            elif pattern_index == 1:  # Pattern 2
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[2].strip()  # Using the visible initials
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name
            elif pattern_index == 2:  # Pattern 3
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name
            elif pattern_index == 3:  # Pattern 4
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name
            
            # If we found a reasonable number of teachers, stop trying other patterns
            if len(teacher_map) >= 20:
                logger.info(f"Found {len(teacher_map)} teachers using pattern {pattern_index+1}")
                break
        
        logger.info(f"Extracted a total of {len(teacher_map)} teachers from HTML using regex patterns")
        return teacher_map
        
    except Exception as e:
        logger.error(f"Error extracting teachers from HTML: {e}")
        return {}

async def fetch_homework_for_lesson(
    cookies: Dict[str, str],
    lesson_id: str,
    lname_value: str = None,
    timer_value: int = None,
    client: httpx.AsyncClient = None
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
        # Use constants instead of hardcoded URLs
        api_url = NOTE_ASP_URL
        
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
            "Referer": f"{GLASIR_BASE_URL}/132n/"
        }
        
        # Use provided client if available
        if client is not None:
            try:
                # Add DNS resolution check
                try:
                    domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
                    import socket
                    socket.gethostbyname(domain)
                except socket.gaierror:
                    logger.error(f"DNS resolution failed for {domain}. Please check your network connection or DNS configuration.")
                    return None

                response = await client.post(api_url, data=params, headers=headers, cookies=cookies, follow_redirects=True, timeout=30.0)
                response.raise_for_status()

                if not response.text:
                    logger.warning("Empty response received")
                    return None

                if raw_response_config["save_enabled"]:
                    timestamp = int(time.time())
                    filename = f"raw_homework_lesson{lesson_id}_{timestamp}.html"
                    save_raw_response(
                        response.text,
                        raw_response_config["directory"],
                        filename,
                        request_url=api_url,
                        request_method="POST",
                        request_headers=headers,
                        request_payload=params
                    )

                return response.text
            except httpx.ConnectError as e:
                logger.error(f"Connection error for {api_url}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} for {api_url}: {e}")
                return None
        else:
            # Create a temporary client if none provided
            async with httpx.AsyncClient(
                cookies=cookies,
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
                verify=True
            ) as temp_client:
                try:
                    domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
                    import socket
                    socket.gethostbyname(domain)
                except socket.gaierror:
                    logger.error(f"DNS resolution failed for {domain}. Please check your network connection or DNS configuration.")
                    return None

                try:
                    response = await temp_client.post(api_url, data=params)
                    response.raise_for_status()

                    if not response.text:
                        logger.warning("Empty response received")
                        return None

                    if raw_response_config["save_enabled"]:
                        timestamp = int(time.time())
                        filename = f"raw_homework_lesson{lesson_id}_{timestamp}.html"
                        save_raw_response(
                            response.text,
                            raw_response_config["directory"],
                            filename,
                            request_url=api_url,
                            request_method="POST",
                            request_headers=headers,
                            request_payload=params
                        )

                    return response.text
                except httpx.ConnectError as e:
                    logger.error(f"Connection error for {api_url}: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return None
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error {e.response.status_code} for {api_url}: {e}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching homework for lesson {lesson_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

async def _process_lesson(
    cookies: Dict[str, str],
    lesson_id: str,
    semaphore: asyncio.Semaphore,
    lname_value: str = None,
    timer_value: int = None,
    client: httpx.AsyncClient = None
) -> tuple[str, Optional[str]]:
    """
    Process a single lesson with semaphore limiting for concurrency control.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        semaphore: Semaphore to limit concurrent requests
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        client: Optional shared httpx.AsyncClient
        
    Returns:
        Tuple of (lesson_id, homework_text or None)
    """
    async with semaphore:
        try:
            html_content = await fetch_homework_for_lesson(
                cookies, lesson_id, lname_value, timer_value, client=client
            )
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
    timer_value: int = None,
    client: httpx.AsyncClient = None
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
    tasks = [_process_lesson(cookies, lesson_id, semaphore, lname_value, timer_value, client) for lesson_id in lesson_ids]
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
    Fetch homework with automatic retry and re-authentication on failure.
    
    Args:
        cookies: Dictionary of cookies from the browser session
        lesson_id: The ID of the lesson to fetch homework for
        page: Playwright page object for re-authentication (optional)
        auth_service: Authentication service for refreshing cookies (optional)
        username: Username for re-authentication (optional)
        password: Password for re-authentication (optional)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        max_retries: Maximum number of retry attempts (default: 2)
        
    Returns:
        HTML string containing the homework data, or None on error
    """
    retry_count = 0
    retry_needed = True
    result = None
    
    # First attempt with existing cookies
    try:
        # Verify DNS resolution first
        try:
            domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
            import socket
            socket.gethostbyname(domain)
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for {domain}: {e}")
            # If DNS resolution fails, we should signal that retry isn't going to help
            # because it's likely a network configuration issue
            return None
            
        result = await fetch_homework_for_lesson(
            cookies, lesson_id, lname_value, timer_value
        )
        if result:
            return result
    except Exception as e:
        # Check if it's a DNS resolution error or other connection-related issue
        is_dns_error = "[Errno 8] nodename nor servname provided, or not known" in str(e)
        is_connection_error = isinstance(e, httpx.ConnectError) or "ConnectionError" in str(e) or "Connection refused" in str(e)
        
        if not (is_dns_error or is_connection_error):
            # If it's some other error, just raise it
            logger.error(f"Non-connection error during homework fetch: {e}")
            return None
        
        logger.warning(f"Connection error during homework fetch: {e}")
        
        # If we don't have what we need for re-authentication, we can't retry
        if not all([page, auth_service, username, password]):
            logger.error("Cannot retry with re-authentication: missing required parameters")
            return None
    
    # If we didn't get a successful result, try re-authenticating and retrying
    while retry_needed and retry_count < max_retries:
        retry_count += 1
        
        try:
            logger.info(f"Retry attempt {retry_count}/{max_retries} with re-authentication")
            
            # Re-authenticate using the provided authentication service
            await auth_service.authenticate(username, password, page)
            
            # Get fresh cookies after re-authentication
            new_cookies = await auth_service.get_cookies()
            
            # Get fresh lname and timer values from page content
            content = await page.content()
            new_lname, new_timer = parse_dynamic_params(content)
            logger.info(f"Re-fetched dynamic parameters: lname={new_lname}, timer={new_timer}")
            
            # Try again with the fresh cookies and parameters
            result = await fetch_homework_for_lesson(
                new_cookies, lesson_id, new_lname, new_timer
            )
            
            if result:
                logger.info(f"Successfully fetched homework for lesson {lesson_id} after {retry_count} retries")
                retry_needed = False
                return result
            else:
                logger.warning(f"Retry {retry_count}/{max_retries} failed: Empty or invalid response")
        except Exception as retry_e:
            logger.error(f"Error during retry {retry_count}/{max_retries}: {retry_e}")
    
    if retry_count >= max_retries:
        logger.error(f"Failed to fetch homework after {max_retries} retry attempts")
        
    return result

async def fetch_homework_for_lessons_with_retry(
    cookies: Dict[str, str],
    lesson_ids: List[str],
    page: Page = None,
    auth_service = None,
    username: str = None,
    password: str = None,
    max_concurrent: int = 10,
    lname_value: str = None,
    timer_value: int = None,
    max_retries: int = 2
) -> Dict[str, str]:
    """
    Fetch homework for multiple lessons with retry and re-authentication.
    
    Args:
        cookies: Dictionary of cookies from the browser session
        lesson_ids: List of lesson IDs to fetch homework for
        page: Playwright page object for re-authentication (optional)
        auth_service: Authentication service for refreshing cookies (optional)
        username: Username for re-authentication (optional)
        password: Password for re-authentication (optional)
        max_concurrent: Maximum number of concurrent requests (default: 10)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        max_retries: Maximum number of retry attempts (default: 2)
        
    Returns:
        Dictionary mapping lesson IDs to their homework content
    """
    if not lesson_ids:
        return {}
        
    results = {}
    retry_count = 0
    retry_needed = False
    
    # Verify DNS resolution first
    try:
        domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
        import socket
        socket.gethostbyname(domain)
    except socket.gaierror as e:
        logger.error(f"DNS resolution failed for {domain}: {e}")
        # If DNS resolution fails, we should return empty results
        # because it's likely a network configuration issue
        return results
    
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
        is_connection_error = isinstance(e, httpx.ConnectError) or "ConnectionError" in str(e) or "Connection refused" in str(e)
        
        if is_dns_error or is_connection_error:
            logger.warning(f"Connection error during batch homework fetch: {e}")
            retry_needed = True
        else:
            logger.error(f"Error during batch homework fetch: {e}")
            return results  # Return whatever we might have gathered before the error
            
    # If we don't have all results and can retry (and have what we need for re-auth)
    if retry_needed and all([page, auth_service, username, password]):
        while retry_needed and retry_count < max_retries:
            retry_count += 1
            
            try:
                logger.info(f"Batch retry attempt {retry_count}/{max_retries} with re-authentication")
                
                # Re-authenticate using the provided authentication service
                await auth_service.authenticate(username, password, page)
                
                # Get fresh cookies after re-authentication
                new_cookies = await auth_service.get_cookies()
                
                # Get fresh lname and timer values from page content
                content = await page.content()
                new_lname, new_timer = parse_dynamic_params(content)
                logger.info(f"Re-fetched dynamic parameters: lname={new_lname}, timer={new_timer}")
                
                # Try again with the fresh cookies and parameters (only for missing lesson_ids)
                retry_results = await fetch_homework_for_lessons(
                    new_cookies, lesson_ids, max_concurrent, new_lname, new_timer
                )
                
                # Merge the new results with the existing ones
                results.update(retry_results)
                
                # Update the list of missing lessons for the next retry if needed
                if retry_results and len(retry_results) > 0:
                    lesson_ids = [lesson_id for lesson_id in lesson_ids if lesson_id not in retry_results]
                    
                # If we got all lessons, we're done
                if not lesson_ids:
                    logger.info(f"Successfully fetched all remaining homework after {retry_count} retries")
                    retry_needed = False
                    break
                else:
                    logger.warning(f"Retry {retry_count}/{max_retries} fetched {len(retry_results)} lessons, {len(lesson_ids)} remaining")
            except Exception as retry_e:
                logger.error(f"Error during batch retry {retry_count}/{max_retries}: {retry_e}")
        
        if retry_count >= max_retries and lesson_ids:
            logger.error(f"Failed to fetch all homework after {max_retries} retry attempts. Missing {len(lesson_ids)} lessons.")
            
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
        # Use constants instead of hardcoded URLs
        api_url = TEACHER_MAP_URL
        
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
            "Referer": f"{GLASIR_BASE_URL}/132n/"
        }
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            if not response.text:
                logger.warning("Empty response received from teacher mapping request")
                return {}
            
            # Save raw response if enabled
            if raw_response_config["save_enabled"]:
                # Construct filename using the agreed pattern
                timestamp = int(time.time())
                filename = f"raw_teachers_{timestamp}.html"
                save_raw_response(
                    response.text,
                    raw_response_config["directory"],
                    filename,
                    request_url=api_url,
                    request_method="POST",
                    request_headers=headers,
                    request_payload=params
                )
                
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
            "timex": str(timer_value),
            "rnd": str(random.random()),
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford28731,48",
            "q": "stude",
            "id": student_id,
            "v": v_override if v_override is not None else "0"  # Use v_override if provided, otherwise default to 0
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
            
            # Save raw response if enabled
            if raw_response_config["save_enabled"]:
                # Construct filename using the agreed pattern
                timestamp = int(time.time())
                v_param = v_override if v_override is not None else "0"
                filename = f"raw_weeks_student{student_id}_v{v_param}_{timestamp}.html"
                save_raw_response(
                    response.text,
                    raw_response_config["directory"],
                    filename,
                    request_url=api_url,
                    request_method="POST",
                    request_headers=headers,
                    request_payload=params
                )
                
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
    Fetch the timetable HTML for a specific week offset using the direct API.
    
    Args:
        cookies: Dictionary of cookies from the browser session
        student_id: The student ID to fetch the timetable for
        week_offset: The week offset (0 = current week, 1 = next week, etc.)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        The HTML content of the timetable response, or None if the request fails
    """
    try:
        # Use the correct URL from constants
        api_url = TIMETABLE_INFO_URL
        
        if timer_value is None:
            timer_value = int(time.time() * 1000)
            
        # Important: Must use MyUpdate-compatible parameters
        logger.info(f"Fetching timetable for week offset {week_offset} with lname={lname_value}")
        
        # Format parameters according to the MyUpdate function we observed
        params = {
            "fname": "Henry",
            "timex": str(timer_value),
            "rnd": str(random.random()),
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford62860,32",
            "q": "stude",
            "id": student_id,
            "v": str(week_offset)  # Format v and id as separate parameters as observed in the actual request
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{GLASIR_BASE_URL}/132n/"
        }
        
        # Create a more robust HTTP client with appropriate settings
        async with httpx.AsyncClient(
            cookies=cookies, 
            headers=headers, 
            follow_redirects=True, 
            timeout=30.0,
            verify=True      # Verify SSL certificates
        ) as client:
            # Add DNS resolution check
            try:
                # Attempt to resolve the hostname manually first
                domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
                import socket
                socket.gethostbyname(domain)
            except socket.gaierror:
                logger.error(f"DNS resolution failed for {domain}. Please check your network connection or DNS configuration.")
                return None
                
            try:
                response = await client.post(api_url, data=params)
                response.raise_for_status()
                
                if not response.text:
                    logger.warning("Empty response received from timetable request")
                    return None
                
                # Save raw response if enabled
                if raw_response_config["save_enabled"]:
                    # Construct filename using the agreed pattern
                    timestamp = int(time.time())
                    filename = f"raw_timetable_week{week_offset}_student{student_id}_{timestamp}.html"
                    save_raw_response(
                        response.text,
                        raw_response_config["directory"],
                        filename,
                        request_url=api_url,
                        request_method="POST",
                        request_headers=headers,
                        request_payload=params
                    )
                    
                return response.text
            except httpx.ConnectError as e:
                logger.error(f"Connection error for {api_url}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} for {api_url}: {e}")
                return None
            
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
    lname_value: str = None,
    timer_value: int = None,
    max_parallel: int = 5
) -> Dict[int, Optional[str]]:
    """
    Fetch timetable HTML for multiple weeks in parallel using a connection pool.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        student_id: The student ID (GUID) for the current user
        week_offsets: List of week offsets to fetch (0 = current week, 1 = next week, etc.)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        max_parallel: Maximum number of parallel requests
        
    Returns:
        Dictionary mapping week offsets to HTML content
    """
    # Ensure unique week offsets
    unique_offsets = list(set(week_offsets))
    
    if len(unique_offsets) != len(week_offsets):
        logger.info(f"Removed {len(week_offsets) - len(unique_offsets)} duplicate week offsets from request")
    
    # Create a semaphore to limit concurrent requests
    semaphore = Semaphore(max_parallel)
    timetable_data = {}
    
    logger.info(f"Fetching timetables for {len(unique_offsets)} weeks with max concurrency {max_parallel}")
    
    # Define an async helper function for fetching a single week
    async def fetch_week(week_offset):
        async with semaphore:
            html_content = await fetch_timetable_for_week(
                cookies=cookies,
                student_id=student_id,
                week_offset=week_offset,
                lname_value=lname_value,
                timer_value=timer_value
            )
            return week_offset, html_content
    
    # Create tasks for all week offsets
    tasks = [fetch_week(offset) for offset in unique_offsets]
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error in parallel fetch: {result}")
            continue
        if isinstance(result, tuple) and len(result) == 2:
            offset, html_content = result
            timetable_data[offset] = html_content
        # Handle cases where the helper might return None or unexpected format (though it shouldn't)
        
    # Ensure all requested offsets are keys in the result, even if fetching failed
    for offset in unique_offsets:
        if offset not in timetable_data:
             timetable_data[offset] = None # Mark as failed/not found

    return timetable_data

async def extract_week_range(
    cookies: Dict[str, str],
    student_id: str,
    lname_value: str = None,
    timer_value: int = None,
    v_override: str = None
) -> Tuple[int, int]:
    """
    Extract the minimum and maximum week offsets available in the timetable using API.
    This function uses the dedicated week selector endpoint (fetch_weeks_data) instead of
    parsing the timetable HTML.
    
    Args:
        cookies: Dictionary of cookies from current browser session
        student_id: The student ID (GUID) for the current user
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        v_override: Optional override for the 'v' parameter to access different academic years
        
    Returns:
        tuple: (min_offset, max_offset) - the earliest and latest available week offsets
        
    Raises:
        ValueError: If no week offset values can be found in the API response
    """
    try:
        # Fetch the weeks data directly using the dedicated endpoint
        weeks_data_response = await fetch_weeks_data(
            cookies=cookies,
            student_id=student_id,
            lname_value=lname_value,
            timer_value=timer_value,
            v_override=v_override
        )
        
        if not weeks_data_response:
            logger.error("Failed to fetch weeks data from API")
            raise ValueError("Failed to extract week offset range. Cannot fetch weeks data.")
        
        # Extract offsets from the weeks data
        if "weeks" not in weeks_data_response or not weeks_data_response["weeks"]:
            logger.error("No valid weeks data found in API response")
            raise ValueError("Failed to extract week offset range. No weeks data found.")
        
        # Get all offsets and find min/max
        offsets = [week.get("offset", 0) for week in weeks_data_response["weeks"] if "offset" in week]
        
        if not offsets:
            logger.error("No week offset values found in API response")
            raise ValueError("Failed to extract week offset range. No offset values found.")
        
        min_offset = min(offsets)
        max_offset = max(offsets)
        
        logger.info(f"API-extracted week offset range: {min_offset} to {max_offset}")
        return min_offset, max_offset
        
    except Exception as e:
        logger.error(f"Error extracting week range using API: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise ValueError(f"Failed to extract week offset range from timetable using API: {e}")

class ApiClient:
    """Client for interacting with Glasir's API endpoints."""
    
    def __init__(self, client: httpx.AsyncClient, session_manager: AuthSessionManager):
        """Initialize the API client with an HTTP client and session manager."""
        self._client = client
        self._session_manager = session_manager
        
    async def initialize_session_params(self, page: Optional[Page] = None) -> None:
        """Initialize session parameters using the provided page or a fresh request."""
        await self._session_manager.fetch_and_cache_params(page)

    # Custom backoff handler to refresh auth and parameters
    def _on_backoff_handler(self, details):
        exception = details.get('exception')
        wait_time = details.get('wait', 0)
        tries = details.get('tries', 0)
        
        # Log the backoff event
        logger.warning(f"Retrying request in {wait_time:.1f}s after {tries} tries. Error: {exception}")
        
        # Check if it's a connection or auth-related error
        is_connection_error = isinstance(exception, httpx.ConnectError)
        is_auth_error = hasattr(exception, 'response') and exception.response and exception.response.status_code in (401, 403)
        
        # For connection or auth errors, trigger re-authentication
        if is_connection_error or is_auth_error:
            logger.warning("Connection or authentication error detected, will refresh session parameters before retry")
            # Clear cached parameters to force refresh on next attempt
            self._session_manager.clear_cache()

    @handle_errors(default_return=None, error_category="fetching_homework_details")
    @backoff.on_exception(backoff.expo,
                          (httpx.RequestError, httpx.HTTPStatusError, httpx.ConnectError, GlasirScrapingError),
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
            # Create a more robust client configuration
            client_kwargs = {
                "timeout": 30.0
            }
            
            # Verify DNS resolution first
            try:
                domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
                import socket
                socket.gethostbyname(domain)
            except socket.gaierror as e:
                logger.error(f"DNS resolution failed for {domain}: {e}")
                raise httpx.ConnectError(f"DNS resolution failed: {e}")

            response = await self._client.post(
                NOTE_ASP_URL, data=payload, headers=DEFAULT_HEADERS, **client_kwargs
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
                          (httpx.RequestError, httpx.HTTPStatusError, httpx.ConnectError, GlasirScrapingError),
                          max_tries=3,
                          logger=logger,
                          on_backoff=lambda details: logger.warning(f"Retrying teacher map fetch in {details['wait']:.1f}s after {details['tries']} tries. Error: {details['exception']}"))
    async def fetch_teacher_map(self, student_id: str, update_cache: bool = False) -> Dict[str, str]:
        """
        Fetches the teacher initials to full name mapping.
        When update_cache is True, fetches from the API and updates the cache.
        When update_cache is False, loads directly from the cache file.

        Args:
            student_id: The ID of the student (unused in direct extraction method).
            update_cache: Whether to update the teacher cache (based on --teacherupdate flag).

        Returns:
            A dictionary mapping teacher initials to full names, or {} on failure.
        """
        try:
            cache_exists = os.path.exists(TEACHER_CACHE_FILE)
            teacher_map = {}

            if not update_cache and cache_exists:
                with open(TEACHER_CACHE_FILE, 'r', encoding='utf-8') as f:
                    teacher_map = json.load(f)
                logger.info(f"Loaded {len(teacher_map)} teachers from cache file")

                # If cache is empty, force update
                if len(teacher_map) == 0:
                    logger.info("Teacher cache is empty, forcing update from API")
                    update_cache = True
                else:
                    return teacher_map

            if update_cache or not cache_exists:
                from glasir_timetable.utils.teacher_api import fetch_and_extract_teachers
                teacher_map = fetch_and_extract_teachers(update_cache=True)

                if teacher_map:
                    logger.info(f"Successfully extracted {len(teacher_map)} teachers, saving to cache")
                    with open(TEACHER_CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(teacher_map, f, indent=2, ensure_ascii=False)
                    return teacher_map
                else:
                    logger.error("Teacher data extraction failed")
                    return {}
        except Exception as e:
            logger.error(f"Error during teacher map extraction: {e}")
            return {}

    @handle_errors(default_return=None, error_category="fetching_timetable_info")
    @backoff.on_exception(backoff.expo,
                          (httpx.RequestError, httpx.HTTPStatusError, httpx.ConnectError, GlasirScrapingError),
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
        
        # Calculate week offset based on current week/year
        # For simplicity, we'll use a direct week offset of 0 for now
        week_offset = 0
        
        payload = {
            "fname": "Henry",
            "timex": params["timer"],
            "rnd": str(random.random()),
            "MyInsertAreaId": "MyWindowMain",
            "lname": params["lname"],
            "q": "stude",
            "id": student_id,
            "v": str(week_offset)
        }
        
        logger.debug(f"Fetching timetable info for week {week_number}/{year} with payload: {payload}")
        try:
            # Create a more robust client configuration
            client_kwargs = {
                "timeout": 30.0
            }
            
            # Verify DNS resolution first
            try:
                domain = GLASIR_BASE_URL.split("//")[1].split("/")[0]
                import socket
                socket.gethostbyname(domain)
            except socket.gaierror as e:
                logger.error(f"DNS resolution failed for {domain}: {e}")
                raise httpx.ConnectError(f"DNS resolution failed: {e}")
                
            response = await self._client.post(
                TIMETABLE_INFO_URL, data=payload, headers=DEFAULT_HEADERS, **client_kwargs
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
