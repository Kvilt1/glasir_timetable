#!/usr/bin/env python3
"""
Utilities for teacher API extraction from Glasir Timetable.

This module provides functions to extract teacher information from the Glasir teacher API
using cookies for authentication. Uses the extract_teachers_from_html method which has proven
to be the most reliable and fastest extraction method based on testing.
"""
import os
import json
import logging
import requests
from typing import Dict, Optional

from glasir_timetable.constants import TEACHER_MAP_URL, TEACHER_CACHE_FILE
from glasir_timetable.api_client import extract_teachers_from_html

logger = logging.getLogger(__name__)

def fetch_teacher_html(cookie_path: str = None) -> Optional[str]:
    """
    Fetch the teacher HTML from the API using the cookie auth module.
    
    Args:
        cookie_path: Path to the cookies.json file (defaults to project root)
        
    Returns:
        The HTML content or None if the request failed
    """
    # Define default cookie path in project root if not provided
    if cookie_path is None:
        cookie_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cookies.json")
    
    logger.info(f"Looking for cookies at: {cookie_path}")
    
    # Try to load cookies directly
    try:
        with open(cookie_path, 'r') as f:
            cookies_data = json.load(f)
        
        cookies_dict = {}
        
        # Handle the format where cookies are in a 'cookies' field
        if isinstance(cookies_data, dict) and 'cookies' in cookies_data and isinstance(cookies_data['cookies'], list):
            logger.info(f"Found {len(cookies_data['cookies'])} cookies in standard format")
            for cookie in cookies_data['cookies']:
                if 'name' in cookie and 'value' in cookie:
                    cookies_dict[cookie['name']] = cookie['value']
        # Handle the format where cookies are directly in a list
        elif isinstance(cookies_data, list):
            logger.info(f"Found {len(cookies_data)} cookies in list format")
            for cookie in cookies_data:
                if 'name' in cookie and 'value' in cookie:
                    cookies_dict[cookie['name']] = cookie['value']
        else:
            logger.warning(f"Unrecognized cookie format: {type(cookies_data)}")
            return None
        
        logger.info(f"Using {len(cookies_dict)} cookies for request")
        
        # Use the constant URL for teacher map
        url = TEACHER_MAP_URL
        logger.info(f"Fetching teacher HTML from {url}")
        
        response = requests.get(url, cookies=cookies_dict)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch teacher HTML. Status code: {response.status_code}")
            return None
        
        logger.info(f"Successfully retrieved HTML content from {url} ({len(response.text)} bytes)")
        return response.text
            
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading cookies file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching teacher HTML: {e}")
        return None

def update_teacher_cache(teacher_map: Dict[str, str], cache_file: str = TEACHER_CACHE_FILE) -> None:
    """
    Update the teacher cache with new entries.
    
    Args:
        teacher_map: Dictionary mapping teacher initials to full names
        cache_file: Path to the cache file
    """
    if not teacher_map:
        logger.warning("Cannot update cache with empty teacher map")
        return
        
    try:
        # Ensure the directory exists before saving
        cache_dir = os.path.dirname(cache_file)
        os.makedirs(cache_dir, exist_ok=True)

        # Load existing cache if it exists
        existing_map = {}
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                existing_map = json.load(f)
                
        # Add new entries, log any mismatches
        for initials, name in teacher_map.items():
            if initials in existing_map and existing_map[initials] != name:
                logger.info(f"Updating teacher: {initials} from '{existing_map[initials]}' to '{name}'")
            existing_map[initials] = name
            
        # Save updated cache
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(existing_map, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Updated teacher cache with {len(teacher_map)} entries. Total entries: {len(existing_map)}")
    except Exception as e:
        logger.error(f"Error updating teacher cache: {e}")

def fetch_and_extract_teachers(cookie_path: str = None, update_cache: bool = True) -> Dict[str, str]:
    """
    Fetch teacher HTML and extract teacher information using extract_teachers_from_html.
    
    Args:
        cookie_path: Path to the cookies.json file
        update_cache: Whether to update the teacher cache with extracted data
        
    Returns:
        Dictionary mapping teacher initials to full names
    """
    # Fetch the teacher HTML from the API
    logger.info("Starting teacher API extraction")
    html_content = fetch_teacher_html(cookie_path)
    
    if not html_content:
        logger.error("Failed to fetch teacher HTML")
        return {}
    
    # Extract teacher information using extract_teachers_from_html
    logger.info("Extracting teachers using extract_teachers_from_html")
    teacher_map = extract_teachers_from_html(html_content)
    
    if not teacher_map:
        logger.warning("No teachers extracted from HTML")
        return {}
        
    logger.info(f"Successfully extracted {len(teacher_map)} teachers")
    
    # Update the teacher cache with the extracted data if specified
    if update_cache:
        logger.info("Updating teacher cache with extracted data")
        update_teacher_cache(teacher_map)
    
    return teacher_map