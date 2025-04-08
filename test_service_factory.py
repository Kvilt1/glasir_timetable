import pytest
from unittest.mock import MagicMock
import glasir_timetable.core.service_factory as sf

def test_service_factory_caches_instances():
    mock_service = MagicMock(name="MockCookieAuthService")
    factory_func = lambda: mock_service

    # First call creates and caches
    service1 = sf.get_service("cookie_auth", factory_func)
    # Second call returns cached
    service2 = sf.get_service("cookie_auth", factory_func)

    assert service1 is service2
    assert service1 == mock_service

def test_service_factory_different_keys():
    # Clear cache to avoid interference from other tests
    sf.clear_service_cache()

    mock_auth = MagicMock(name="MockCookieAuthService")
    mock_api = MagicMock(name="MockApiExtractionService")

    auth_service = sf.get_service("cookie_auth", lambda: mock_auth)
    api_service = sf.get_service("api_extraction", lambda: mock_api)

    assert auth_service == mock_auth
    assert api_service == mock_api
    assert auth_service is not api_service

def test_service_factory_clear_cache():
    mock_service = MagicMock(name="MockCookieAuthService")
    factory_func = lambda: mock_service

    service1 = sf.get_service("cookie_auth", factory_func)
    sf.clear_service_cache()
    mock_service2 = MagicMock(name="MockCookieAuthService2")
    service2 = sf.get_service("cookie_auth", lambda: mock_service2)

    assert service1 is not service2
    assert service2 == mock_service2

def test_removed_constants_raise_error():
    import glasir_timetable.constants as constants
    with pytest.raises(AttributeError):
        _ = constants.DEFAULT_LNAME_FALLBACK
    with pytest.raises(AttributeError):
        _ = constants.DEFAULT_TIMER_FALLBACK