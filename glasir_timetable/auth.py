#!/usr/bin/env python3
"""
Authentication module for the Glasir Timetable application.
"""
import logging
from glasir_timetable import logger

async def login_to_glasir(page, username, password):
    """
    Log in to tg.glasir.fo using Microsoft authentication.
    
    Args:
        page: The Playwright page object.
        username: The username for login (without @glasir.fo domain).
        password: The password for login.
    """
    # Append domain to username
    email = f"{username}@glasir.fo"
    
    logger.info("Navigating to tg.glasir.fo...")
    await page.goto("https://tg.glasir.fo")
    
    # Enter email
    logger.info("Entering username...")
    await page.wait_for_selector("#i0116", state="visible")
    await page.fill("#i0116", email)
    await page.click("#idSIButton9")
    
    # Wait for password field
    logger.info("Entering password...")
    await page.wait_for_selector("#passwordInput", state="visible")
    await page.fill("#passwordInput", password)
    
    # Check "Keep me signed in" checkbox to avoid the "Stay signed in?" prompt later
    logger.info("Checking 'Keep me signed in' checkbox...")
    await page.check("#kmsiInput")
    
    # Click Sign In button
    await page.click("#submitButton")
    
    # Wait for redirection to timetable page
    await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=30000)
    logger.info("Successfully logged in!")
    
    # Wait for the timetable to be visible instead of networkidle
    await page.wait_for_selector("table.time_8_16", state="visible", timeout=10000) 