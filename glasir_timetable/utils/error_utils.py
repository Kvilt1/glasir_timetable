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

class ExtractionError(GlasirError):
    """Exception raised for data extraction errors."""
    pass

class NavigationError(GlasirError):
    """Exception raised for navigation errors."""
    pass

class AuthenticationError(GlasirError):
    """Exception raised for authentication errors."""
    pass

class GlasirScrapingError(ExtractionError):
    """Exception raised for scraping and data extraction errors."""
    pass

# Global state management for console listener
_console_listener_registry = {
    'attached_pages': set(),
    'listeners': {}
}

def configure_error_handling(collect_details=False, collect_tracebacks=False, error_limit=100):
    """Configure error handling behavior"""
    error_config["collect_details"] = collect_details
    error_config["collect_tracebacks"] = collect_tracebacks
    error_config["error_limit"] = error_limit

def handle_errors(
    error_category: str = "general_errors",
    error_class: Type[Exception] = Exception,
    reraise: bool = True,
    default_return: Any = None,
    error_message: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator for handling errors in a consistent way.
    
    Args:
        error_category: The category of the error for reporting purposes.
        error_class: The exception class to catch and convert.
        reraise: Whether to reraise the exception after handling.
        default_return: The value to return if an exception occurs and reraise is False.
        error_message: A message template that will be formatted with the exception.
        
    Returns:
        The decorated function.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Get function information for better error messages
                module = inspect.getmodule(func)
                function_name = f"{module.__name__ if module else 'unknown'}.{func.__name__}"
                
                # Format error message
                msg = error_message or f"Error in {function_name}: {str(e)}"
                formatted_msg = msg.format(error=str(e), function=function_name)
                
                # Log the error
                logger.error(formatted_msg)
                
                # Add to error collection
                add_error(error_category, formatted_msg, {
                    "traceback": traceback.format_exc(),
                    "function": function_name,
                    "args": str(args),
                    "kwargs": str(kwargs)
                })
                
                # Reraise the error if requested
                if reraise:
                    if isinstance(e, error_class):
                        raise
                    else:
                        raise error_class(formatted_msg) from e
                        
                # Return default value
                return default_return
        return cast(F, wrapper)
    return decorator

@contextlib.contextmanager
def resource_cleanup_context(
    resources: Dict[str, Any],
    cleanup_funcs: Dict[str, Callable[[Any], None]]
):
    """
    Context manager for resource cleanup.
    
    Args:
        resources: Dictionary of resources to be managed.
        cleanup_funcs: Dictionary of cleanup functions for each resource.
        
    Yields:
        The resources dictionary.
    """
    try:
        yield resources
    finally:
        # Clean up resources in reverse order of creation
        for name, resource in reversed(list(resources.items())):
            if name in cleanup_funcs and resource is not None:
                try:
                    cleanup_funcs[name](resource)
                except Exception as e:
                    logger.error(f"Error cleaning up resource {name}: {e}")

@contextlib.asynccontextmanager
async def async_resource_cleanup_context(
    resources: Dict[str, Any],
    cleanup_funcs: Dict[str, Callable[[Any], None]]
):
    """
    Async context manager for resource cleanup.
    
    Args:
        resources: Dictionary of resources to be managed.
        cleanup_funcs: Dictionary of cleanup functions for each resource.
        
    Yields:
        The resources dictionary.
    """
    try:
        yield resources
    finally:
        # Clean up resources in reverse order of creation
        for name, resource in reversed(list(resources.items())):
            if name in cleanup_funcs and resource is not None:
                try:
                    if asyncio.iscoroutinefunction(cleanup_funcs[name]):
                        await cleanup_funcs[name](resource)
                    else:
                        cleanup_funcs[name](resource)
                except Exception as e:
                    logger.error(f"Error cleaning up resource {name}: {e}")

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

async def evaluate_js_safely(
    page,
    js_code: str,
    error_message: Optional[str] = None,
    error_category: str = "javascript_errors",
    reraise: bool = True
) -> Any:
    """
    Evaluate JavaScript code safely with proper error handling.
    
    Args:
        page: The Playwright page object.
        js_code: The JavaScript code to evaluate.
        error_message: Custom error message.
        error_category: The category of the error for reporting purposes.
        reraise: Whether to reraise the exception.
        
    Returns:
        The result of the JavaScript evaluation.
        
    Raises:
        JavaScriptError: If the JavaScript evaluation fails and reraise is True.
    """
    try:
        return await page.evaluate(js_code)
    except Exception as e:
        msg = error_message or f"JavaScript evaluation failed: {str(e)}"
        logger.error(msg)
        
        # Add to error collection
        add_error(error_category, msg, {
            "js_code": js_code,
            "traceback": traceback.format_exc()
        })
        
        if reraise:
            raise JavaScriptError(msg) from e
        return None

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

def unregister_console_listener(page):
    """
    Remove console listener from a page.
    
    Args:
        page: The Playwright page object.
        
    Returns:
        None
    """
    global _console_listener_registry
    
    page_id = id(page)
    
    # Skip if not registered
    if page_id not in _console_listener_registry['attached_pages']:
        return
    
    # Get the listener
    listener = _console_listener_registry['listeners'].get(page_id)
    if listener:
        # Remove listener from page
        page.remove_listener("console", listener)
        
        # Remove from registry
        _console_listener_registry['attached_pages'].remove(page_id)
        del _console_listener_registry['listeners'][page_id]
        logger.debug(f"Console listener removed from page {page_id}") 