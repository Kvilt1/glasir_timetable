#!/usr/bin/env python3
"""
Service factory for the Glasir Timetable application.

This module provides functions to create and initialize service instances,
facilitating dependency injection and service management.
"""

from typing import Dict, Any

from glasir_timetable.services import (
    AuthenticationService,
    NavigationService,
    ExtractionService,
    FormattingService,
    StorageService,
    PlaywrightAuthenticationService,
    CookieAuthenticationService,
    PlaywrightNavigationService,
    PlaywrightExtractionService,
    DefaultFormattingService,
    FileStorageService
)

# Cache for singleton service instances
_services_cache = {}

# Default configuration options
_config = {
    "use_cookie_auth": True,
    "cookie_path": "cookies.json",
    "auto_refresh_cookies": True
}

def set_config(config_dict):
    """
    Set configuration options for the service factory.
    
    Args:
        config_dict: Dictionary of configuration options
    """
    global _config
    _config.update(config_dict)

def create_authentication_service() -> AuthenticationService:
    """
    Create and return an authentication service instance.
    
    Returns:
        AuthenticationService: The authentication service
    """
    if "auth_service" not in _services_cache:
        if _config.get("use_cookie_auth", True):
            _services_cache["auth_service"] = CookieAuthenticationService(
                cookie_path=_config.get("cookie_path", "cookies.json"),
                auto_refresh=_config.get("auto_refresh_cookies", True)
            )
        else:
            _services_cache["auth_service"] = PlaywrightAuthenticationService()
    return _services_cache["auth_service"]

def create_navigation_service() -> NavigationService:
    """
    Create and return a navigation service instance.
    
    Returns:
        NavigationService: The navigation service
    """
    if "navigation_service" not in _services_cache:
        _services_cache["navigation_service"] = PlaywrightNavigationService()
    return _services_cache["navigation_service"]

def create_extraction_service() -> ExtractionService:
    """
    Create and return an extraction service instance.
    
    Returns:
        ExtractionService: The extraction service
    """
    if "extraction_service" not in _services_cache:
        _services_cache["extraction_service"] = PlaywrightExtractionService()
    return _services_cache["extraction_service"]

def create_formatting_service() -> FormattingService:
    """
    Create and return a formatting service instance.
    
    Returns:
        FormattingService: The formatting service
    """
    if "formatting_service" not in _services_cache:
        _services_cache["formatting_service"] = DefaultFormattingService()
    return _services_cache["formatting_service"]

def create_storage_service() -> StorageService:
    """
    Create and return a storage service instance.
    
    Returns:
        StorageService: The storage service
    """
    if "storage_service" not in _services_cache:
        _services_cache["storage_service"] = FileStorageService()
    return _services_cache["storage_service"]

def create_services(config=None) -> Dict[str, Any]:
    """
    Create and return all application services.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        dict: Dictionary of all service instances
    """
    # Update config if provided
    if config:
        set_config(config)
    
    return {
        "auth_service": create_authentication_service(),
        "navigation_service": create_navigation_service(),
        "extraction_service": create_extraction_service(),
        "formatting_service": create_formatting_service(),
        "storage_service": create_storage_service()
    }

def get_service(service_name: str) -> Any:
    """
    Get a service instance by name.
    
    Args:
        service_name: Name of the service to get
        
    Returns:
        Any: The requested service instance
        
    Raises:
        ValueError: If the service name is invalid
    """
    # Create services if not already created
    if not _services_cache:
        create_services()
        
    if service_name == "auth_service":
        return create_authentication_service()
    elif service_name == "navigation_service":
        return create_navigation_service()
    elif service_name == "extraction_service":
        return create_extraction_service()
    elif service_name == "formatting_service":
        return create_formatting_service()
    elif service_name == "storage_service":
        return create_storage_service()
    else:
        raise ValueError(f"Invalid service name: {service_name}")

def clear_service_cache() -> None:
    """
    Clear the service cache.
    This is useful for testing or when services need to be re-initialized.
    """
    global _services_cache
    _services_cache = {} 