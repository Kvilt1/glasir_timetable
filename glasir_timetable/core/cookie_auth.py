#!/usr/bin/env python3
"""
Cookie-based authentication module for the Glasir Timetable application.

This module provides functions for:
1. Logging in with Playwright and saving cookies
2. Loading saved cookies for use with requests
3. Checking cookie validity and refreshing when needed
"""
import os
import json
import time
import asyncio
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from playwright.async_api import Page
from glasir_timetable.shared import logger
from glasir_timetable.core.auth import login_to_glasir

# Default path for cookie storage - now inside the glasir_timetable directory
DEFAULT_COOKIE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    "cookies.json"
)

async def save_cookies_after_login(
    page: Page, 
    username: str, 
    password: str, 
    cookie_path: str = DEFAULT_COOKIE_PATH
) -> bool:
    """
    Log in to tg.glasir.fo using Playwright and save cookies for future use.
    
    Args:
        page: The Playwright page object
        username: The username for login (without @glasir.fo domain)
        password: The password for login
        cookie_path: Path to save cookies to (default: cookies.json in project root)
        
    Returns:
        bool: True if login and cookie saving was successful
    """
    try:
        # Login using the existing auth function
        await login_to_glasir(page, username, password)
        
        # Get cookies from the browser context
        cookies = await page.context.cookies()
        
        # Add expiration time (24 hours from now)
        cookie_data = {
            "cookies": cookies,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        
        # Save cookies to file
        with open(cookie_path, 'w') as f:
            json.dump(cookie_data, f, indent=2)
            
        logger.info(f"Saved {len(cookies)} cookies to {cookie_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save cookies after login: {e}")
        return False

def load_cookies(cookie_path: str = DEFAULT_COOKIE_PATH) -> Optional[Dict[str, Any]]:
    """
    Load saved cookies from file.
    
    Args:
        cookie_path: Path to the cookie file
        
    Returns:
        Dict containing cookie data or None if file doesn't exist or is invalid
    """
    try:
        if not os.path.exists(cookie_path):
            logger.info(f"Cookie file not found: {cookie_path}")
            return None
            
        with open(cookie_path, 'r') as f:
            cookie_data = json.load(f)
            
        # Quick validation of cookie data structure
        if not all(key in cookie_data for key in ['cookies', 'created_at', 'expires_at']):
            logger.warning(f"Cookie file {cookie_path} has invalid format")
            return None
            
        return cookie_data
        
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
        return None

def is_cookies_valid(cookie_data: Optional[Dict[str, Any]]) -> bool:
    """
    Check if the cookies are still valid (not expired).
    
    Args:
        cookie_data: Loaded cookie data dictionary
        
    Returns:
        bool: True if cookies are valid, False otherwise
    """
    if not cookie_data:
        return False
        
    try:
        expires_at = datetime.fromisoformat(cookie_data['expires_at'])
        now = datetime.now()
        return now < expires_at
    except Exception as e:
        logger.error(f"Error checking cookie validity: {e}")
        return False

def create_requests_session_with_cookies(cookie_data: Dict[str, Any]) -> requests.Session:
    """
    Create a requests session with the saved cookies.
    
    Args:
        cookie_data: The loaded cookie data
        
    Returns:
        requests.Session with cookies set
    """
    session = requests.Session()
    
    # Add cookies to the session
    for cookie in cookie_data['cookies']:
        session.cookies.set(
            name=cookie['name'], 
            value=cookie['value'],
            domain=cookie['domain'],
            path=cookie['path']
        )
    
    return session

async def check_and_refresh_cookies(
    page: Page, 
    username: str, 
    password: str, 
    cookie_path: str = DEFAULT_COOKIE_PATH
) -> Dict[str, Any]:
    """
    Check if cookies exist and are valid, refresh if needed.
    
    This function acts as the main entry point for cookie management:
    1. Checks if cookies exist and are valid
    2. If not, uses Playwright to login and generate new cookies
    3. Returns the cookie data for use
    
    Args:
        page: The Playwright page object
        username: The username for login
        password: The password for login
        cookie_path: Path to cookie file
        
    Returns:
        Dict containing cookie data
    """
    # Load existing cookies
    cookie_data = load_cookies(cookie_path)
    
    # Check if cookies are valid
    if not is_cookies_valid(cookie_data):
        logger.info("Cookies are expired or invalid, refreshing...")
        success = await save_cookies_after_login(page, username, password, cookie_path)
        
        if not success:
            raise Exception("Failed to refresh cookies")
            
        # Reload the cookies after saving
        cookie_data = load_cookies(cookie_path)
        
        if not cookie_data:
            raise Exception("Failed to load cookies after refresh")
    else:
        logger.info("Using existing valid cookies")
        
    return cookie_data

async def set_cookies_in_playwright_context(page: Page, cookie_data: Dict[str, Any]) -> None:
    """
    Set the loaded cookies in a Playwright browser context.
    
    Args:
        page: The Playwright page object
        cookie_data: The loaded cookie data
    """
    if not cookie_data or 'cookies' not in cookie_data:
        logger.warning("No valid cookies to set in Playwright context")
        return
        
    try:
        await page.context.add_cookies(cookie_data['cookies'])
        logger.info(f"Added {len(cookie_data['cookies'])} cookies to Playwright context")
    except Exception as e:
        logger.error(f"Failed to set cookies in Playwright context: {e}")

async def test_cookies_with_requests(cookie_data: Dict[str, Any]) -> bool:
    """
    Test if the cookies work with a requests session.
    
    Args:
        cookie_data: The loaded cookie data
        
    Returns:
        bool: True if the cookies can access the timetable page
    """
    session = create_requests_session_with_cookies(cookie_data)
    
    try:
        response = session.get("https://tg.glasir.fo/132n/")
        
        # Check if we're still on the login page or if we successfully accessed the timetable
        if response.status_code == 200 and "time_8_16" in response.text:
            logger.info("Cookies successfully verified with requests")
            return True
        else:
            logger.warning("Cookies failed verification with requests")
            return False
            
    except Exception as e:
        logger.error(f"Error testing cookies with requests: {e}")
        return False

def estimate_cookie_expiration(cookie_data: Optional[Dict[str, Any]]) -> str:
    """
    Estimate and format when cookies will expire.
    
    Args:
        cookie_data: Loaded cookie data dictionary
        
    Returns:
        str: A human-readable string describing when cookies will expire
    """
    if not cookie_data or 'expires_at' not in cookie_data:
        return "No valid cookies found"
        
    try:
        # Parse the expiration time
        expires_at = datetime.fromisoformat(cookie_data['expires_at'])
        now = datetime.now()
        
        # Check if already expired
        if now >= expires_at:
            return "Cookies have expired"
            
        # Calculate time until expiration
        time_left = expires_at - now
        hours_left = time_left.total_seconds() / 3600
        minutes_left = (time_left.total_seconds() % 3600) / 60
        
        if hours_left > 24:
            days_left = hours_left / 24
            return f"Cookies will expire in {days_left:.1f} days"
        elif hours_left >= 1:
            return f"Cookies will expire in {int(hours_left)} hours and {int(minutes_left)} minutes"
        else:
            return f"Cookies will expire in {int(minutes_left)} minutes"
            
    except Exception as e:
        logger.error(f"Error estimating cookie expiration: {e}")
        return "Unable to determine cookie expiration" 