import pytest
from unittest.mock import patch, MagicMock, call
from glasir_timetable.core.api_client import ApiClient
from glasir_timetable.core.session import GlasirScrapingError

import time

@pytest.fixture
def api_client():
    mock_client = MagicMock(name="MockHttpClient")
    mock_session_manager = MagicMock(name="MockSessionManager")
    client = ApiClient(client=mock_client, session_manager=mock_session_manager)
    # Set dummy valid params
    client.lname = "12345"
    client.timer = int(time.time() * 1000)
    return client

def test_retry_logic_on_network_error(api_client):
    with patch.object(api_client, "_make_request", side_effect=[Exception("Network error"), {"success": True}]) as mock_request, \
         patch("time.sleep") as mock_sleep:
        response = api_client.request_with_retry("GET", "/some-endpoint")
        assert response == {"success": True}
        assert mock_request.call_count == 2
        mock_sleep.assert_called()
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(sleep_calls[i] <= sleep_calls[i+1] for i in range(len(sleep_calls)-1))

def test_retry_logic_on_http_5xx(api_client):
    mock_response_500 = MagicMock()
    mock_response_500.status_code = 500
    mock_response_500.json.return_value = {}
    with patch.object(api_client, "_make_request", side_effect=[mock_response_500, {"success": True}]) as mock_request, \
         patch("time.sleep") as mock_sleep:
        response = api_client.request_with_retry("GET", "/some-endpoint")
        assert response == {"success": True}
        assert mock_request.call_count == 2
        mock_sleep.assert_called()

def test_reauthentication_on_401_then_success(api_client):
    mock_response_401 = MagicMock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {}

    with patch.object(api_client, "_make_request", side_effect=[mock_response_401, {"success": True}]) as mock_request, \
         patch.object(api_client, "refresh_session", return_value=True) as mock_refresh:
        response = api_client.request_with_retry("GET", "/some-endpoint")
        assert response == {"success": True}
        assert mock_request.call_count == 2
        mock_refresh.assert_called_once()

def test_reauthentication_fails_aborts(api_client):
    mock_response_401 = MagicMock()
    mock_response_401.status_code = 401
    mock_response_401.json.return_value = {}

    with patch.object(api_client, "_make_request", side_effect=[mock_response_401]) as mock_request, \
         patch.object(api_client, "refresh_session", return_value=False) as mock_refresh:
        with pytest.raises(GlasirScrapingError):
            api_client.request_with_retry("GET", "/some-endpoint")
        assert mock_request.call_count == 1
        mock_refresh.assert_called_once()

def test_missing_parameters_raise_error():
    mock_client = MagicMock()
    mock_session_manager = MagicMock()
    client = ApiClient(client=mock_client, session_manager=mock_session_manager)
    client.lname = None
    client.timer = None
    with pytest.raises(GlasirScrapingError):
        client.request_with_retry("GET", "/some-endpoint")
