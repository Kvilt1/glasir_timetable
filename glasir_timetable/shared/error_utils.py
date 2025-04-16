#!/usr/bin/env python3
"""
Error handling utilities for the Glasir Timetable application.
This module provides decorators, context managers, and wrapper functions
for consistent error handling throughout the application.
"""
import functools
import contextlib
import logging
import inspect
import traceback
import asyncio
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union, cast

from glasir_timetable import logger, add_error, error_config

# Type definitions for better type hinting
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

class GlasirError(Exception):
    """Base exception class for all Glasir application errors."""
    pass

class JavaScriptError(GlasirError):
    """Exception raised for JavaScript-related errors."""
    pass





# Global state management for console listener
_console_listener_registry = {
    'attached_pages': set(),
    'listeners': {}
}





@contextlib.asynccontextmanager
async def error_screenshot_context(page, screenshot_name: str, error_type: str = "general_errors", take_screenshot: bool = False):
    """
    Context manager that optionally takes a screenshot when an exception occurs.
    
    Args:
        page: The Playwright page object.
        screenshot_name: The base name for the screenshot file.
        error_type: The category of the error for reporting purposes.
        take_screenshot: Whether to take a screenshot or not (default: False).
        
    Yields:
        None
    """
    try:
        yield
    except Exception as e:
        logger.error(f"Error: {e}")
        
        screenshot_path = None
        if take_screenshot:
            # Take a screenshot for debugging
            screenshot_path = f"error_{screenshot_name}.png"
            logger.warning(f"Taking a screenshot for debugging: {screenshot_path}")
            
            try:
                await page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
            except Exception as screenshot_error:
                logger.error(f"Failed to take screenshot: {screenshot_error}")
        
        # Add to error collection - only include screenshot if taken
        error_data = {"traceback": traceback.format_exc()}
        if screenshot_path:
            error_data["screenshot"] = screenshot_path
            
        add_error(error_type, str(e), error_data)
        
        # Re-raise the original exception
        raise


def register_console_listener(page, listener=None):
    """
    Ensure a console listener is attached to the page.
    Maintains global registry to avoid duplicate listeners.
    
    Args:
        page: The Playwright page object.
        listener: Custom console listener function. If None, the default listener is used.
        
    Returns:
        None
    """
    global _console_listener_registry
    
    # Generate a unique ID for the page
    page_id = id(page)
    
    # Skip if already registered
    if page_id in _console_listener_registry['attached_pages']:
        logger.debug(f"Console listener already attached to page {page_id}")
        return
    
    # Use default listener if none provided
    if listener is None:
        listener = default_console_listener
    
    # Store the listener in registry
    _console_listener_registry['listeners'][page_id] = listener
    
    # Attach listener to page
    page.on("console", listener)
    
    # Mark as attached
    _console_listener_registry['attached_pages'].add(page_id)
    logger.debug(f"Console listener attached to page {page_id}")

def default_console_listener(msg):
    """
    Default console message listener that logs console messages.
    
    Args:
        msg: The console message object.
        
    Returns:
        None
    """
    message_type = msg.type
    text = msg.text
    
    if message_type == "error":
        logger.error(f"Console error: {text}")
        add_error("console_errors", text)
    elif message_type == "warning":
        logger.warning(f"Console warning: {text}")
    else:
        logger.debug(f"Console {message_type}: {text}")
