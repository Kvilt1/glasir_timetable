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
            return None
        
        # Extract lname value from the MyUpdate function
        lname_value = await page.evaluate("""() => {
            if (typeof MyUpdate !== 'function') {
                return null;
            }
            
            const myUpdateStr = MyUpdate.toString();
            const lnameMatch = myUpdateStr.match(/lname=([^&"]+)/);
            return lnameMatch ? lnameMatch[1] : null;
        }""")
        
        if lname_value:
            logger.info(f"Dynamically extracted lname value: {lname_value}")
            return lname_value
        else:
            logger.warning("Failed to extract lname value from MyUpdate function")
            return None
    except Exception as e:
        logger.error(f"Error extracting lname value: {e}")
        return None

async def fetch_homework_for_lesson(
    cookies: Dict[str, str],
    lesson_id: str,
    lname_value: str = None
) -> Optional[str]:
    """
    Fetch homework for a single lesson using the reliable individual lesson API function.
    This approach is guaranteed to work based on testing.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        lname_value: Optional dynamically extracted lname value
        
    Returns:
        HTML string containing the homework data, or None on error
    """
    try:
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/note.asp"
        
        # Use the exact parameter format from the working MyUpdate function
        params = {
            "fname": "Henry",
            "timex": int(time.time() * 1000),  # Similar to window.timer but we don't have access to it here
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
        
        logger.debug(f"Fetching homework for lesson {lesson_id}")
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            logger.debug(f"Lesson {lesson_id} homework response: {len(response.text)} bytes")
            return response.text
    except Exception as e:
        logger.error(f"Error fetching homework for lesson {lesson_id}: {e}")
        return None

async def _process_lesson(cookies: Dict[str, str], lesson_id: str, semaphore: asyncio.Semaphore, lname_value: str = None) -> tuple[str, Optional[str]]:
    """
    Process a single lesson with semaphore limiting for concurrency control.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_id: The ID of the lesson to fetch homework for
        semaphore: Semaphore to limit concurrent requests
        lname_value: Optional dynamically extracted lname value
        
    Returns:
        Tuple of (lesson_id, homework_text or None)
    """
    async with semaphore:
        try:
            html_content = await fetch_homework_for_lesson(cookies, lesson_id, lname_value)
            if html_content:
                homework_text = parse_individual_lesson_response(html_content)
                return lesson_id, homework_text
        except Exception as e:
            logger.error(f"Error processing homework for lesson {lesson_id}: {e}")
    
    return lesson_id, None

async def fetch_homework_for_lessons(
    cookies: Dict[str, str],
    lesson_ids: List[str],
    max_concurrent: int = 5,  # Limit concurrent requests to avoid overwhelming server
    lname_value: str = None
) -> Dict[str, str]:
    """
    Fetch homework for multiple lessons using parallel requests with limited concurrency.
    
    Args:
        cookies: Dictionary of cookies from the current browser session
        lesson_ids: List of lesson IDs to fetch homework for
        max_concurrent: Maximum number of concurrent requests (default: 5)
        lname_value: Optional dynamically extracted lname value
        
    Returns:
        Dictionary mapping lesson IDs to their homework content
    """
    if not lesson_ids:
        return {}
    
    results = {}
    
    # Use parallel individual requests with controlled concurrency
    logger.info(f"Fetching {len(lesson_ids)} lessons with max {max_concurrent} concurrent requests")
    
    # Create a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Process all lesson IDs in parallel with limited concurrency
    tasks = [_process_lesson(cookies, lesson_id, semaphore, lname_value) for lesson_id in lesson_ids]
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
            return homework_text
        
        # Fallback: try to find any paragraphs inside the response
        all_paragraphs = soup.find_all('p')
        if all_paragraphs:
            homework_text = "\n".join(p.get_text(strip=True) for p in all_paragraphs if p.get_text(strip=True))
            return homework_text
            
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
        # Get the timer value directly from the page - much simpler approach
        timer_value = await page.evaluate("window.timer")
        if timer_value is not None:
            logger.info(f"Extracted timer value: {timer_value}")
            return timer_value
        else:
            logger.warning("Timer variable not found on page")
            # Fallback to a timestamp similar to what the page would use
            return int(time.time() * 1000) % 1000
    except Exception as e:
        logger.error(f"Error extracting timer value: {e}")
        # Return a fallback value
        return int(time.time() * 1000) % 1000

async def fetch_timetable_for_week(
    cookies: Dict[str, str],
    student_id: str,
    week_offset: int = 0,
    lname_value: str = None,
    timer_value: int = None
) -> Optional[str]:
    """
    Fetches timetable data for a specific week using direct API call.
    
    Args:
        cookies: Dictionary of cookies from browser session
        student_id: Student ID (GUID format)
        week_offset: Week offset (positive=forward, negative=backward, 0=current)
        lname_value: Optional dynamically extracted lname value
        timer_value: Optional timer value extracted from the page
        
    Returns:
        HTML string containing the timetable data, or None on error
    """
    try:
        # Base URL
        base_url = "https://tg.glasir.fo"
        api_url = f"{base_url}/i/udvalg.asp"
        
        # Prepare parameters
        if timer_value is None:
            # If no timer value provided, use current timestamp (less accurate fallback)
            timer_value = int(time.time() * 1000)
        
        random_val = random.random()
        
        # Remove curly braces from student ID if present
        if student_id.startswith('{') and student_id.endswith('}'):
            student_id = student_id[1:-1]
        
        # Format the week query parameter similar to how it's done in the JS MyUpdate function
        q_value = f"stude&id={student_id}&v={week_offset}"
        
        # Set up parameters - using the exact format from the successful browser request
        params = {
            "fname": "Henry",
            "timex": timer_value,
            "rnd": random_val,
            "MyInsertAreaId": "MyWindowMain",
            "lname": lname_value if lname_value else "Ford62860,32",  # Use the latest dynamic value if available
            "q": q_value
        }
            
        # Set up headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{base_url}/132n/"
        }
        
        logger.info(f"Making timetable API request to {api_url} for week offset {week_offset}")
        logger.debug(f"Request params: {params}")
        
        # Make the request
        async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
            response = await client.post(api_url, data=params)
            response.raise_for_status()
            
            logger.info(f"Timetable API response received: {len(response.text)} bytes")
            if len(response.text) == 0:
                logger.warning(f"Empty response received for timetable request")
                return None
            
            return response.text
    except httpx.RequestError as exc:
        logger.error(f"Timetable API Request Error: {exc}")
    except httpx.HTTPStatusError as exc:
        logger.error(f"Timetable HTTP Status Error {exc.response.status_code}: {exc}")
    except Exception as e:
        logger.error(f"Unexpected error during timetable API call: {e}")
        
    return None 