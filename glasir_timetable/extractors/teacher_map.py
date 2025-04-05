#!/usr/bin/env python3
"""
Module for extracting teacher mapping from the Glasir timetable.
"""

import os
import json
import re
import logging
from typing import Dict, Optional
from bs4 import BeautifulSoup, Tag

# Import fetch_teacher_mapping from api_client
from ..utils.error_utils import handle_errors, GlasirScrapingError
from ..constants import TEACHER_CACHE_FILE

logger = logging.getLogger(__name__)

# --- Caching logic ---
@handle_errors(default_return={}, error_category="loading_teacher_cache")
def load_teacher_cache(cache_file: str = TEACHER_CACHE_FILE) -> Dict[str, str]:
    """Loads the teacher map from the JSON cache file."""
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            if isinstance(cache_data, dict):
                logger.info(f"Loaded {len(cache_data)} teachers from cache: {cache_file}")
                return cache_data
            else:
                logger.warning(f"Invalid data format in teacher cache file: {cache_file}. Expected a dict.")
                return {}
    except FileNotFoundError:
        logger.info(f"Teacher cache file not found: {cache_file}")
        return {}
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from teacher cache file: {cache_file}")
        return {} # Return empty dict on decode error

@handle_errors(error_category="saving_teacher_cache")
def save_teacher_cache(teacher_map: Dict[str, str], cache_file: str = TEACHER_CACHE_FILE) -> None:
    """Saves the teacher map to the JSON cache file."""
    if not teacher_map:
        logger.warning("Attempted to save an empty teacher map to cache. Skipping.")
        return
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(teacher_map, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved {len(teacher_map)} teachers to cache: {cache_file}")
    except IOError as e:
        logger.error(f"Failed to write teacher cache file {cache_file}: {e}")
        # Decide if this should raise an error or just log
    except TypeError as e:
         logger.error(f"Data type error saving teacher cache {cache_file}: {e}")


# --- Function using Playwright Page (kept for potential Playwright-based extraction) ---
# This function might still be called by PlaywrightExtractionService if API fails or is not used.
@handle_errors(default_return={}, error_category="extracting_teacher_map_via_playwright")
async def extract_teacher_map_with_playwright(page) -> Dict[str, str]:
    """
    Extracts the teacher map by parsing options from a select element using Playwright.
    """
    logger.info("Extracting teacher map using Playwright page content...")
    try:
        # Ensure the relevant selector is present
        # Use a robust selector, wait if necessary
        select_selector = 'select[name="laerer"], select#laerer' # Example: try name or id
        await page.wait_for_selector(select_selector, timeout=5000)

        # Get the HTML content of the select element or the whole page
        # Getting the whole page content might be simpler if parsing logic handles it
        content = await page.content()
        teacher_map = parse_teacher_map_html_response(content) # Reuse parsing logic from api_client

        if not teacher_map:
            logger.warning("Extracted teacher map via Playwright, but no entries were found.")
        else:
            logger.info(f"Successfully extracted {len(teacher_map)} teachers via Playwright.")

        return teacher_map

    except Exception as e:
        logger.error(f"Playwright error extracting teacher map: {e}")
        # Consider if this should return {} or raise a specific error
        # Returning {} aligns with other error handling for this function
        return {}

async def extract_teacher_map(page, use_cache=False, cache_path=None, cookies=None, lname_value=None, timer_value=None):
    """
    Extract teacher map from the timetable page using API with fallback to Playwright methods.
    Returns a dictionary mapping teacher initials to full names with initials.
    
    Args:
        page: The Playwright page object.
        use_cache: Whether to use a cached version if available.
        cache_path: Path to the cache file (default is in the same directory as this module).
        cookies: Cookies dictionary to use with the API approach.
        lname_value: The lname value for API requests.
        timer_value: The timer value for API requests.
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
    # Import here to avoid circular import
    from glasir_timetable.api_client import fetch_teacher_mapping, parse_teacher_map_html_response

    # Set default cache path if not provided
    if cache_path is None:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(module_dir)  # Go up one level to the base package
        cache_path = os.path.join(base_dir, "teacher_cache.json")
    
    # Try to load from cache if use_cache is True
    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                logger.info(f"Loaded teacher mapping from cache with {len(cached_data)} entries.")
                return cached_data
        except Exception as e:
            logger.warning(f"Error loading teacher cache: {e}")
    
    logger.info("Extracting teacher mapping...")
    
    # Use API approach as the primary method
    if cookies is not None:
        logger.info("Using API approach to extract teacher mapping...")
        try:
            teacher_map = await fetch_teacher_mapping(
                cookies=cookies,
                lname_value=lname_value,
                timer_value=timer_value
            )
            
            if teacher_map and len(teacher_map) > 0:
                logger.info(f"Successfully extracted {len(teacher_map)} teachers via API")
                
                # Save to cache
                if cache_path:
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(teacher_map, f, ensure_ascii=False, indent=2)
                        logger.info(f"Saved teacher mapping to cache at {cache_path}")
                    except Exception as e:
                        logger.warning(f"Error saving teacher cache: {e}")
                
                return teacher_map
            else:
                logger.warning("API extraction returned empty teacher map. Falling back to Playwright method.")
        except Exception as e:
            logger.error(f"Error with API-based teacher mapping extraction: {e}")
            logger.warning("Falling back to Playwright method...")
    else:
        logger.warning("No cookies provided for API extraction. Falling back to Playwright method.")
    
    # Fallback to the Playwright method if API approach fails or returns empty
    original_url = await navigate_to_teachers_page(page)
    
    if original_url is None:
        logger.warning("Could not navigate to teachers page. Using alternative extraction method.")
        # Fall back to the old method if navigation fails
        return await extract_teacher_map_fallback(page)
    
    # Wait for the teacher table to load
    await page.wait_for_selector('table', state='visible', timeout=5000)
    
    # Use Playwright's locators to extract teacher information
    teacher_map = {}
    
    # Extract the entire HTML from the page, which contains the teacher information
    html_content = await page.content()
    
    # Parse out teacher information using regex
    # Format in HTML: Name (XXX) where XXX is the initials inside an <a> tag
    pattern = r'([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)'
    matches = re.findall(pattern, html_content)
    
    for match in matches:
        full_name = match[0].strip()
        initials = match[1].strip()
        teacher_map[initials] = full_name  # Store only the name without appending initials
    
    logger.info(f"Direct HTML extraction found {len(teacher_map)} teachers")
    
    # If we didn't extract enough teachers, try alternative methods
    if not teacher_map or len(teacher_map) < 20:  # If we found less than 20 teachers, try other methods
        logger.info(f"First extraction method yielded only {len(teacher_map)} results. Trying alternative selector.")
        
        # Try an alternative approach with more specific regex to match the teacher HTML structure
        pattern = r'([^<>]+?)\s*\(\s*<a [^>]*?onclick="[^"]*?teach([A-Z]{2,4})[^"]*?"[^>]*?>([A-Z]{2,4})</a>\s*\)'
        matches = re.findall(pattern, html_content)
        
        for match in matches:
            full_name = match[0].strip()
            initials = match[2].strip()  # Using the visible initials
            if initials not in teacher_map:
                teacher_map[initials] = full_name  # Store only the name without appending initials
        
        logger.info(f"Second extraction method found a total of {len(teacher_map)} teachers")
    
    # If still not enough, try extracting using JavaScript
    if len(teacher_map) < 50:
        logger.info("Previous methods yielded limited results. Trying JavaScript extraction.")
        
        js_result = await page.evaluate("""
        () => {
            const teacherMap = {};
            
            // Find all teacher links (they have onclick attributes containing 'teach')
            document.querySelectorAll('a[onclick*="teach"]').forEach(link => {
                const initials = link.textContent.trim();
                const parentNode = link.parentNode;
                const parentText = parentNode.textContent.trim();
                
                // Extract the name part (before the parenthesis)
                const fullNameMatch = parentText.match(/(.*?)\\s*\\(/);
                if (fullNameMatch && fullNameMatch[1]) {
                    const fullName = fullNameMatch[1].trim();
                    teacherMap[initials] = fullName;  // Store only the name without appending initials
                }
            });
            
            return teacherMap;
        }
        """)
        
        # Merge JavaScript results
        for initials, name in js_result.items():
            if initials not in teacher_map:
                teacher_map[initials] = name
        
        logger.info(f"JavaScript extraction found a total of {len(teacher_map)} teachers")
    
    # Store the URL we need to return to
    if original_url:
        logger.info(f"Navigating back to original page: {original_url}")
        
        try:
            # First store the current context and cookies
            cookies = await page.context.cookies()
            
            # Go back to the original page and wait for proper loading
            await page.goto(original_url, wait_until="domcontentloaded")
            
            # Extra wait to ensure the page is fully loaded
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Wait for a while to ensure stability
            await page.wait_for_timeout(1000)
            
            logger.info("Successfully returned to original page.")
        except Exception as e:
            logger.error(f"Error when returning to original page: {e}")
    
    if not teacher_map:
        logger.warning("Could not extract teacher mapping from the page. Using fallback mapping.")
        # Fall back to the old method if extraction fails
        return await extract_teacher_map_fallback(page)
    else:
        logger.info(f"Successfully extracted teacher mapping for {len(teacher_map)} teachers.")
        
        # Save to cache if extraction was successful
        if cache_path:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(teacher_map, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved teacher mapping to cache at {cache_path}")
            except Exception as e:
                logger.warning(f"Error saving teacher cache: {e}")
    
    return teacher_map 

async def extract_teacher_map_fallback(page):
    """
    Fallback method to extract teacher map from the timetable page.
    Uses a more general approach when the primary method fails.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
    logger.info("Using fallback method to extract teacher mapping...")
    
    teacher_map = {}
    
    try:
        # Try direct HTML extraction from the current page
        html_content = await page.content()
        
        # Check for teacher entries with pattern: Name (XXX) where XXX is 2-4 uppercase letters
        pattern = r'([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)'
        matches = re.findall(pattern, html_content)
        
        for match in matches:
            full_name = match[0].strip()
            initials = match[1].strip()
            teacher_map[initials] = full_name  # Store only the name without appending initials
        
        logger.info(f"Direct regex extraction found {len(teacher_map)} teachers")
    except Exception as e:
        logger.error(f"Error in regex-based extraction: {e}")
    
    # If first approach didn't yield many results, try with tables
    if len(teacher_map) < 10:
        try:
            rows = page.locator('table tr')
            count = await rows.count()
            
            for i in range(count):
                row = rows.nth(i)
                if await row.locator('td').count() > 0:
                    for j in range(await row.locator('td').count()):
                        cell = row.locator('td').nth(j)
                        cell_text = await cell.text_content()
                        
                        # Look for initials in parentheses pattern
                        match = re.search(r'(.*?)\s*\(([A-Z]{2,4})\)', cell_text)
                        if match:
                            full_name = match.group(1).strip()
                            initials = match.group(2).strip()
                            teacher_map[initials] = full_name  # Store only the name without appending initials
        except Exception as e:
            logger.error(f"Error in selector-based fallback: {e}")
    
    # If previous approaches didn't yield many results, try JavaScript approach
    if len(teacher_map) < 10:
        try:
            logger.info("Previous fallback methods yielded limited results. Trying JavaScript approach...")
            js_result = await page.evaluate("""
            () => {
                const teacherMap = {};
                
                // Method 1: Find all teacher links
                document.querySelectorAll('a[onclick*="teach"]').forEach(link => {
                    const initials = link.textContent.trim();
                    if (initials.match(/^[A-Z]{2,4}$/)) {
                        const parentText = link.parentNode.textContent.trim();
                        const fullNameMatch = parentText.match(/(.*?)\\s*\\(/);
                        
                        if (fullNameMatch && fullNameMatch[1]) {
                            const fullName = fullNameMatch[1].trim();
                            teacherMap[initials] = fullName;  // Store only the name without appending initials
                        }
                    }
                });
                
                // Method 2: Check table cells 
                document.querySelectorAll('td').forEach(cell => {
                    const text = cell.textContent.trim();
                    const match = text.match(/(.*?)\\s*\\(([A-Z]{2,4})\\)/);
                    if (match && match[1] && match[2]) {
                        const fullName = match[1].trim();
                        const initials = match[2].trim();
                        teacherMap[initials] = fullName;
                    }
                });
                
                return teacherMap;
            }
            """)
            
            # Merge JS results
            for initials, name in js_result.items():
                if initials not in teacher_map:
                    teacher_map[initials] = name
                    
            logger.info(f"JavaScript fallback found a total of {len(teacher_map)} teachers")
        except Exception as e:
            logger.error(f"Error in JavaScript fallback: {e}")
            
    return teacher_map

async def navigate_to_teachers_page(page):
    """
    Navigate to the teachers page to extract teacher mapping.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        str: The original URL to return to after extraction, or None if navigation failed.
    """
    try:
        # Store the current URL to return to later
        original_url = page.url
        
        # Try to navigate to the teachers page
        teacher_url = "https://tg.glasir.fo/132n/laerer.asp"
        logger.info(f"Navigating to teachers page: {teacher_url}")
        
        try:
            # Use a navigation approach that handles redirects appropriately
            response = await page.goto(teacher_url, wait_until="domcontentloaded")
            
            # Wait for the page to fully loaded
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Check if the navigation was successful
            if response and response.status == 200:
                logger.info("Successfully navigated to teachers page.")
                return original_url
            else:
                logger.warning(f"Navigation to teachers page returned status {response.status if response else 'unknown'}")
                return original_url  # Still return original URL for fallback
                
        except Exception as e:
            logger.error(f"Error navigating to teachers page: {e}")
            return original_url  # Still return original URL for fallback
            
    except Exception as e:
        logger.error(f"General error in teacher page navigation: {e}")
        return None
