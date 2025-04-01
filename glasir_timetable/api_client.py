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

from playwright.async_api import Page

from glasir_timetable import logger
from glasir_timetable.extractors.homework_parser import clean_homework_text

logger = logging.getLogger(__name__)

async def extract_lname_from_page(page) -> Optional[str]:
    """
    Dynamically extract the lname value from the MyUpdate function on the page.
    
    Args:
        page: Playwright page object with access to the loaded timetable
        
    Returns:
        String containing the lname value in the format "Ford#####,##", or None if not found
    """
    try:
        # Check if MyUpdate function exists on the page
        has_my_update = await page.evaluate("typeof MyUpdate === 'function'")
        
        if not has_my_update:
            logger.warning("MyUpdate function not found on page, cannot extract lname")
            analysis_results = await analyze_lname_values(page)
            
            # Try to find a usable lname value from the analysis
            if analysis_results["potential_lname_values"]:
                # Find values that match the expected format (Ford#####,##)
                ford_values = [v for v in analysis_results["potential_lname_values"] 
                              if v.startswith("Ford") and "," in v]
                
                if ford_values:
                    lname_value = ford_values[0]
                    return lname_value
                else:
                    # Just use the first value as a best guess
                    lname_value = analysis_results["potential_lname_values"][0]
                    return lname_value
            
            return None
        
        # Extract lname value from the MyUpdate function
        my_update_str = await page.evaluate("MyUpdate.toString()")
        
        lname_value = await page.evaluate("""() => {
            if (typeof MyUpdate !== 'function') {
                return null;
            }
            
            const myUpdateStr = MyUpdate.toString();
            const lnameMatch = myUpdateStr.match(/lname=([^&"]+)/);
            return lnameMatch ? lnameMatch[1] : null;
        }""")
        
        if lname_value:
            return lname_value
        else:
            logger.warning("Failed to extract lname value from MyUpdate function")
            
            # Look for lname in any form on the page
            alt_lname = await page.evaluate("""() => {
                // Look for any "lname" references in page source
                const pageSource = document.documentElement.outerHTML;
                const lnameMatches = pageSource.match(/lname=([^&"]+)/g);
                return lnameMatches ? JSON.stringify(lnameMatches) : null;
            }""")
            
            if alt_lname:
                # Try to extract a usable value from these references
                try:
                    matches = json.loads(alt_lname)
                    if matches:
                        # Extract the first value
                        first_match = matches[0].replace("lname=", "")
                        return first_match
                except:
                    pass
            
            # Try the comprehensive analysis as a last resort
            analysis_results = await analyze_lname_values(page)
            
            # Try to find a usable lname value from the analysis
            if analysis_results["potential_lname_values"]:
                # Find values that match the expected format (Ford#####,##)
                ford_values = [v for v in analysis_results["potential_lname_values"] 
                              if v.startswith("Ford") and "," in v]
                
                if ford_values:
                    lname_value = ford_values[0]
                    return lname_value
                else:
                    # Just use the first value as a best guess
                    lname_value = analysis_results["potential_lname_values"][0]
                    return lname_value
                
            return None
    except Exception as e:
        logger.error(f"Error extracting lname value: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

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

async def extract_timer_value_from_page(page) -> Optional[int]:
    """
    Extract the timer value used in the MyUpdate function.
    
    Args:
        page: Playwright page object with access to the loaded timetable
        
    Returns:
        Integer timer value or None if not found
    """
    try:
        # Check if we're on a timetable page
        timetable_found = await page.locator("table.time_8_16").count() > 0
        
        # First try direct approach - get timer from window object
        has_timer = await page.evaluate("typeof window.timer !== 'undefined'")
        
        if has_timer:
            timer_value = await page.evaluate("window.timer")
            if timer_value is not None:
                return timer_value
            else:
                logger.warning("Timer variable exists but is null or undefined")
        else:
            logger.warning("Timer variable not found on page")
            
        # Try to find timer in scripts
        alt_timer = await page.evaluate("""() => {
            // Check for timer in any script
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const script of scripts) {
                if (script.textContent) {
                    const timerMatch = script.textContent.match(/timer\\s*=\\s*(\\d+)/);
                    if (timerMatch) {
                        return parseInt(timerMatch[1], 10);
                    }
                }
            }
            return null;
        }""")
        
        if alt_timer:
            return alt_timer
        
        # Fallback to a timestamp similar to what the page would use
        fallback = int(time.time() * 1000) 
        logger.warning(f"No timer found, using fallback value: {fallback}")
        return fallback
    except Exception as e:
        logger.error(f"Error extracting timer value: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Return a fallback value
        fallback = int(time.time() * 1000)
        logger.warning(f"Using fallback value due to error: {fallback}")
        return fallback

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
            return parse_teacher_html_response(response.text)
            
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
    timer_value: int = None
) -> Dict[str, Any]:
    """
    Fetch all available weeks data directly using the udvalg.asp endpoint without navigating the page.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        student_id: The student ID (GUID) for the current user
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
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
            "v": "-1"  # Can be any week offset
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
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract date range for the current week
        date_range_text = None
        for text in soup.stripped_strings:
            if re.match(r'\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}', text):
                date_range_text = text
                break
        
        # Extract all week links
        week_links = soup.select('a.UgeKnap, a.UgeKnapValgt, a.UgeKnapAktuel')
        
        for link in week_links:
            week_data = {}
            
            # Extract week number
            week_number = link.text.strip()
            if week_number.startswith("Vika "):
                week_number = week_number.replace("Vika ", "")
            
            week_data["week_number"] = week_number
            
            # Extract onclick attribute to get the week offset
            onclick = link.get('onclick', '')
            offset_match = re.search(r'v=(-?\d+)', onclick)
            if offset_match:
                week_data["offset"] = int(offset_match.group(1))
            else:
                continue  # Skip if we can't get the offset
            
            # Determine if this is the current week
            if 'UgeKnapValgt' in link.get('class', []) or 'UgeKnapAktuel' in link.get('class', []):
                week_data["is_current"] = True
                if date_range_text:
                    week_data["date_range"] = date_range_text
                result["current_week"] = week_data
            else:
                week_data["is_current"] = False
            
            result["weeks"].append(week_data)
        
        logger.info(f"Extracted {len(result['weeks'])} weeks from API response")
        
    except Exception as e:
        logger.error(f"Error parsing weeks HTML: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
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