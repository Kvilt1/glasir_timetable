import asyncio
import os
import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

import httpx
from httpx import Limits

# Import the global config and logger
from glasir_timetable import raw_response_config, logger
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager


class AsyncApiClient:
    """
    Async HTTP API client with retries, cookie and param injection.
    """

    def __init__(
        self,
        base_url: str,
        cookies: Optional[Dict[str, str]] = None,
        session_params: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.cookies = cookies or {}
        self.session_params = session_params or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        # Configure connection limits
        limits = Limits(max_keepalive_connections=20, max_connections=100)
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=True,
            cookies=self.cookies,
            limits=limits,
            http2=True,  # Enable HTTP/2 negotiation
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self.client.aclose()

    async def _request_with_retries(  # Add force_max_concurrency flag
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,  # New flag
        **kwargs,
    ) -> httpx.Response:
        attempt = 0
        last_exc = None
        full_url = (
            url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
        )
        merged_data = data.copy() if data else {}

        # Inject session params if needed
        if inject_params and self.session_params:
            merged_data.update(self.session_params)

        while attempt < self.max_retries:
            try:
                response = await self.client.request(
                    method,
                    full_url,
                    params=params,
                    data=merged_data,
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                # Save raw response if enabled
                await self._save_raw_response(response, method, full_url)
                # Only report success if manager exists AND force flag is OFF
                if concurrency_manager and not force_max_concurrency:
                    concurrency_manager.report_success()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exc = e

                # Check for specific failure conditions and report
                report_failure = False
                if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
                    report_failure = True
                elif isinstance(
                    e, httpx.HTTPStatusError
                ) and e.response.status_code in [429, 500, 503]:
                    report_failure = True

                # Only report failure if conditions met AND manager exists AND force flag is OFF
                if report_failure and concurrency_manager and not force_max_concurrency:
                    concurrency_manager.report_failure()

                # Log sanitized endpoint (without query params)
                endpoint = full_url.split("?")[0]
                logger.warning(
                    f"API {method} {endpoint} attempt {attempt+1} failed: {type(e).__name__}"
                )
                attempt += 1
                if attempt >= self.max_retries:
                    break
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                await asyncio.sleep(sleep_time)
        endpoint = full_url.split("?")[0]
        logger.error(
            f"API {method} {endpoint} failed after {self.max_retries} attempts"
        )
        raise last_exc

    async def _save_raw_response(
        self, response: httpx.Response, method: str, url: str
    ):
        """Saves the raw response content if configured."""
        if not raw_response_config["save_enabled"]:
            return

        try:
            # Ensure directory exists
            save_dir = raw_response_config["directory"]
            os.makedirs(save_dir, exist_ok=True)

            # Create a somewhat unique filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            parsed_url = urlparse(url)
            # Sanitize path for filename
            path_part = parsed_url.path.strip('/').replace('/', '_')
            if not path_part:
                path_part = "index"
            # Include relevant query params if they exist
            query_part = ""
            if parsed_url.query:
                params = parse_qs(parsed_url.query)
                # Example: include 'week' if present
                if 'week' in params:
                    query_part = f"_week{params['week'][0]}"
                elif 'id' in params: # Or ID if relevant
                    query_part = f"_id{params['id'][0]}"

            filename = f"{timestamp}_{method}_{path_part}{query_part}.raw"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, "wb") as f:
                f.write(response.content)

            logger.debug(f"Saved raw response to: {filepath}")

            # Optionally save request details
            if raw_response_config["save_request_details"]:
                details_filepath = filepath.replace(".raw", ".request.txt")
                with open(details_filepath, "w") as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"Method: {method}\n")
                    f.write(f"Status Code: {response.status_code}\n")
                    f.write("Headers:\n")
                    for k, v in response.request.headers.items():
                        f.write(f"  {k}: {v}\n")
                    # Add more details if needed (e.g., request body for POST)

        except Exception as e:
            logger.error(f"Failed to save raw response for {url}: {e}")

    async def get(  # Add force_max_concurrency flag
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,  # New flag
        **kwargs,
    ) -> httpx.Response:
        return await self._request_with_retries(
            "GET",
            url,
            params=params,
            headers=headers,
            inject_params=inject_params,
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,  # Pass flag
        )

    async def post(  # Add force_max_concurrency flag
        self,
        url: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,  # New flag
        **kwargs,
    ) -> httpx.Response:
        return await self._request_with_retries(
            "POST",
            url,
            data=data,
            headers=headers,
            inject_params=inject_params,
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,  # Pass flag
        )
