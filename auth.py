#!/usr/bin/env python3
"""
Authentication module for the Glasir Timetable application.
"""

async def login_to_glasir(page, email, password):
    """
    Log in to tg.glasir.fo using Microsoft authentication.
    
    Args:
        page: The Playwright page object.
        email: The email address for login.
        password: The password for login.
    """
    print("Navigating to tg.glasir.fo...")
    await page.goto("https://tg.glasir.fo")
    
    # Enter email
    print("Entering email...")
    await page.fill("#i0116", email)
    await page.click("#idSIButton9")
    
    # Wait for password field
    print("Entering password...")
    await page.wait_for_selector("#passwordInput", state="visible")
    await page.fill("#passwordInput", password)
    
    # Click Sign In button
    await page.click("#submitButton")
    
    # Wait for "Stay signed in?" prompt and click "Yes"
    try:
        await page.wait_for_selector("#idSIButton9", state="visible", timeout=10000)
        await page.click("#idSIButton9")
    except:
        print("No 'Stay signed in' prompt detected, continuing...")
    
    # Wait for redirection to timetable page
    await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=30000)
    print("Successfully logged in!")
    
    # Give the page a moment to fully load
    await page.wait_for_load_state("networkidle") 