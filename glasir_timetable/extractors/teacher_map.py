#!/usr/bin/env python3
"""
Module for extracting teacher mapping from the Glasir timetable.
"""

import os
import json
import re
import logging

# Add import for the API-based approach
from glasir_timetable.api_client import fetch_teacher_mapping

logger = logging.getLogger(__name__)

async def extract_teacher_map(page, use_cache=False, cache_path=None, use_api=False, cookies=None, lname_value=None, timer_value=None):
    """
    Extract teacher map from the timetable page.
    Returns a dictionary mapping teacher initials to full names with initials.
    
    Args:
        page: The Playwright page object.
        use_cache: Whether to use a cached version if available.
        cache_path: Path to the cache file (default is in the same directory as this module).
        use_api: Whether to use the API approach instead of page navigation.
        cookies: Cookies dictionary to use with the API approach.
        lname_value: The lname value for API requests.
        timer_value: The timer value for API requests.
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
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
    
    logger.info("Extracting teacher mapping from page...")
    
    # If API approach is requested, use that instead of navigation
    if use_api and cookies is not None:
        logger.info("Using API approach to extract teacher mapping...")
        teacher_map = await fetch_teacher_mapping(cookies, lname_value, timer_value)
        
        if not teacher_map or len(teacher_map) < 20:  # If API approach failed or returned too few results
            logger.warning("API approach failed, falling back to page navigation")
        else:
            logger.info(f"Successfully extracted {len(teacher_map)} teachers using API approach")
            
            # Save to cache if extraction was successful
            if cache_path:
                try:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(teacher_map, f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved teacher mapping to cache at {cache_path}")
                except Exception as e:
                    logger.warning(f"Error saving teacher cache: {e}")
            
            return teacher_map
    
    # Otherwise continue with the original approach
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
                
                // Method 2: Look for text patterns like "Name (XXX)"
                if (Object.keys(teacherMap).length < 10) {
                    const textWalker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    
                    let textNode;
                    while (textNode = textWalker.nextNode()) {
                        const text = textNode.nodeValue.trim();
                        const match = text.match(/(.*?)\\s*\\(([A-Z]{2,4})\\)/);
                        if (match) {
                            const fullName = match[1].trim();
                            const initials = match[2].trim();
                            teacherMap[initials] = fullName;  // Store only the name without appending initials
                        }
                    }
                }
                
                return teacherMap;
            }
            """)
            
            # Merge JavaScript results with existing map
            for initials, name in js_result.items():
                if initials not in teacher_map:
                    teacher_map[initials] = name
                    
            logger.info(f"JavaScript approach extracted {len(js_result)} teachers")
        except Exception as e:
            logger.error(f"Error in JavaScript-based fallback: {e}")
    
    # As a last resort, include some fallback entries for common teachers 
    # (only add if not already present)
    if len(teacher_map) < 10:
        default_map = {
            "BIJ": "Brynjálvur I. Johansen",
            "DTH": "Durita Thomsen",
            "HSV": "Henriette Svenstrup",
            "JBJ": "Jan Berg Jørgensen",
            "JOH": "Jón Mikael Degn í Haraldstovu",
            "PEY": "Pætur Eysturskarð",
            "TJA": "Tina Kildegaard Jakobsen",
            "ESN": "Erla S. Nielsen",
            "GUR": "Guðrið Hansen",
            "HEJ": "Heidi Durhuus",
            "MRH": "Martin Hofmeister",
            "SAS": "Sámal Samuelsen"
        }
        
        for initials, name in default_map.items():
            if initials not in teacher_map:
                teacher_map[initials] = name
                
    logger.info(f"Total extracted: {len(teacher_map)} teachers using fallback methods")
    return teacher_map

async def navigate_to_teachers_page(page):
    """
    Navigate to the teachers page and return the original URL.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        str: The original URL if navigation was successful, None otherwise.
    """
    logger.info("Navigating to teachers page...")
    
    # Store current URL to return later
    current_url = page.url
    
    try:
        # Fixed approach - use individual selectors without invalid CSS
        success = await page.evaluate("""
        () => {
            // Try finding by title attribute
            let links = document.querySelectorAll('a.Knap[title="Lærarar"]');
            if (links.length > 0) {
                links[0].click();
                return true;
            }
            
            // Try finding by text content
            links = Array.from(document.querySelectorAll('a.Knap')).filter(a => 
                a.textContent.includes('Lærarar') || a.textContent.includes('Lærarar vm.')
            );
            if (links.length > 0) {
                links[0].click();
                return true;
            }
            
            // Try by onclick attribute
            links = document.querySelectorAll('a[onclick*="teachers.asp"]');
            if (links.length > 0) {
                links[0].click();
                return true;
            }
            
            return false;
        }
        """)
        
        if not success:
            logger.warning("Could not find the teachers link.")
            return None
        
        # Wait for navigation to complete
        await page.wait_for_load_state("networkidle", timeout=5000)
        
        # Check if we're on the teachers page
        has_teacher_links = await page.evaluate("""
        () => {
            return document.querySelectorAll('a[onclick*="teach"]').length > 0;
        }
        """)
        
        if has_teacher_links:
            logger.info("Successfully navigated to teachers page")
            return current_url
        else:
            logger.warning("Navigation may have occurred but teachers page not detected")
            return current_url
            
    except Exception as e:
        logger.error(f"Error navigating to teachers page: {e}")
        return None

async def extract_teachers_from_html(html_content):
    """
    Extract teacher information directly from HTML content.
    Useful when you have the teacher HTML directly without needing navigation.
    
    Args:
        html_content: The HTML content containing teacher information
        
    Returns:
        dict: A mapping of teacher initials to full names.
    """
    teacher_map = {}
    
    # Pattern 1: For links with onclick attributes: Name (<a...>XXX</a>)
    pattern1 = r'([^<>]+?)\s*\(\s*<a [^>]*?onclick="[^"]*?teach([A-Z]{2,4})[^"]*?"[^>]*?>([A-Z]{2,4})</a>\s*\)'
    matches = re.findall(pattern1, html_content)
    
    for match in matches:
        full_name = match[0].strip()
        initials = match[2].strip()  # Use the visible initials (within the <a> tag)
        teacher_map[initials] = full_name  # Store only the name without appending initials
    
    # Pattern 2: Simpler fallback pattern: Name (XXX)
    if len(teacher_map) < 10:
        pattern2 = r'([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)'
        matches = re.findall(pattern2, html_content)
        
        for match in matches:
            full_name = match[0].strip()
            initials = match[1].strip()
            if initials not in teacher_map:  # Only add if not already present
                teacher_map[initials] = full_name  # Store only the name without appending initials
    
    return teacher_map 