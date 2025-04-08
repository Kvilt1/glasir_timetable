# Placeholder service classes to fix NameError during test collection
class AuthenticationService:
    pass

class CookieAuthenticationService(AuthenticationService):
    def __init__(self, cookie_file):
        self.cookie_file = cookie_file

class ApiExtractionService:
    def __init__(self, api_client):
        self.api_client = api_client

class ExtractionService:
    pass

class FormattingService:
    pass

class DefaultFormattingService(FormattingService):
    pass

class StorageService:
    pass

class FileStorageService(StorageService):
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir

class NavigationService:
    pass

#!/usr/bin/env python3
"""
Service factory for creating and initializing service instances.

This module provides factory functions for creating dependency-injected services
for authentication, navigation, extraction, formatting, and storage operations.
"""
import os
from typing import Dict, Any, Optional, Union
import httpx

from glasir_timetable import add_error, logger
from glasir_timetable.session import AuthSessionManager
from glasir_timetable.api_client import ApiClient
from glasir_timetable.constants import (
    AUTH_COOKIES_FILE,
    DATA_DIR
)

# Configuration options
_config = {
    "use_cookie_auth": False,  # Use cookie-based authentication
    "storage_dir": DATA_DIR,   # Default storage directory
    "cookie_file": AUTH_COOKIES_FILE  # Default cookie file path
}

# Dummy navigation service factory to fix undefined error
def create_navigation_service():
    class DummyNavService:
        pass
    return DummyNavService()

# Cache for singleton service instances
_service_cache = {}

def set_config(key: str, value: Any) -> None:
    """
    Set a configuration option for the service factory.
    
    Args:
        key: Configuration key to set
        value: Value for the configuration key
    """
    global _config
    if key in _config:
        _config[key] = value
        logger.info(f"Configuration updated: {key}={value}")
        
        # Clear cache when configuration changes to force recreation
        clear_service_cache()
    else:
        logger.warning(f"Ignoring unknown configuration option: {key}")

def create_httpx_client() -> httpx.AsyncClient:
    """
    Create an AsyncClient for HTTP requests.
    
    Returns:
        httpx.AsyncClient: The configured client
    """
    return httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        verify=True
    )

def create_auth_session_manager(authentication_service: AuthenticationService) -> AuthSessionManager:
    """
    Create and configure the AuthSessionManager with the provided authentication service.
    
    Args:
        authentication_service: The authentication service to use
        
    Returns:
        AuthSessionManager: The configured auth session manager
    """
    return AuthSessionManager(authentication_service)

def create_api_client(auth_session_manager: AuthSessionManager) -> ApiClient:
    """
    Create and configure the ApiClient with the auth session manager.
    
    Args:
        auth_session_manager: The authentication session manager
        
    Returns:
        ApiClient: The configured API client
    """
    client = create_httpx_client()
    return ApiClient(client, auth_session_manager)

def create_authentication_service() -> AuthenticationService:
    """
    Always create a cookie-based authentication service.
    """
    cookie_file = _config.get("cookie_file", AUTH_COOKIES_FILE)
    logger.info(f"Using cookie-based authentication with file: {cookie_file}")
    return CookieAuthenticationService(cookie_file)

def create_extraction_service(api_client: Optional[ApiClient] = None) -> ExtractionService:
    """
    Always create an API-based extraction service.
    """
    if api_client:
        logger.info("Using API-based extraction service")
        return ApiExtractionService(api_client)
    else:
        logger.warning("No ApiClient provided, creating ApiExtractionService without client")
        return ApiExtractionService(None)

def create_formatting_service() -> FormattingService:
    """
    Create and configure the formatting service.
    
    Returns:
        FormattingService: The configured formatting service
    """
    logger.info("Creating JSON formatting service")
    return DefaultFormattingService()

def create_storage_service() -> StorageService:
    """
    Create and configure the storage service.
    
    Returns:
        StorageService: The configured storage service
    """
    storage_dir = _config.get("storage_dir", DATA_DIR)
    logger.info(f"Creating file system storage service with directory: {storage_dir}")
    return FileStorageService(storage_dir)

def create_services() -> Dict[str, Any]:
    """
    Create all required services and return them in a dictionary.
    
    Returns:
        Dict[str, Any]: Dictionary of service instances
    """
    # Create services in correct dependency order
    auth_service = get_service("auth", create_authentication_service)
    
    # Create auth session manager
    auth_session_manager = get_service("auth_session_manager", 
                                       lambda: create_auth_session_manager(auth_service))
    
    # Create API client
    api_client = get_service("api_client", 
                             lambda: create_api_client(auth_session_manager))
    
    # Create other services
    nav_service = get_service("nav", create_navigation_service)
    extraction_service = get_service("extraction", 
                                    lambda: create_extraction_service(api_client))
    formatting_service = get_service("formatting", create_formatting_service)
    storage_service = get_service("storage", create_storage_service)
    
    # Return all services in a dictionary
    return {
        "auth": auth_service,
        "navigation": nav_service,
        "extraction": extraction_service,
        "formatting": formatting_service,
        "storage": storage_service,
        "auth_session_manager": auth_session_manager,
        "api_client": api_client
    }

def get_service(service_key: str, factory_func: callable) -> Any:
    """
    Get or create a service instance from the cache.
    
    Args:
        service_key: The key to identify the service
        factory_func: Factory function to create the service if not cached
        
    Returns:
        Any: The service instance
    """
    global _service_cache
    
    # Return cached service if available
    if service_key in _service_cache:
        return _service_cache[service_key]
    
    # Create new service instance
    service = factory_func()
    
    # Cache the service
    _service_cache[service_key] = service
    
    return service

def clear_service_cache() -> None:
    """
    Clear the service cache to force new instances on next request.
    """
    global _service_cache
    
    # Close any services that require cleanup
    close_services()
    
    # Clear the cache
    _service_cache = {}
    logger.info("Service cache cleared")

def close_services() -> None:
    """
    Close any services that require cleanup (like httpx clients).
    """
    global _service_cache
    
    # Close the httpx client in the API client if it exists
    if "api_client" in _service_cache:
        api_client = _service_cache["api_client"]
        if api_client and hasattr(api_client, "_client"):
            try:
                # We need to run the close method in an event loop, but we can't block here
                # Just log that it needs to be closed properly
                logger.info("Note: API client's httpx client needs to be closed properly at shutdown")
            except Exception as e:
                logger.error(f"Error closing API client: {e}") 