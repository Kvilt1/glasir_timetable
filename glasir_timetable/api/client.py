import httpx
import asyncio
import time
from typing import Optional, Dict, Any, Union
from glasir_timetable.shared import logger

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
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=True,
            cookies=self.cookies
        )

    async def close(self):
        await self.client.aclose()

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        **kwargs
    ) -> httpx.Response:
        attempt = 0
        last_exc = None
        full_url = url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
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
                    **kwargs
                )
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exc = e
                # Log sanitized endpoint (without query params)
                endpoint = full_url.split("?")[0]
                logger.warning(f"API {method} {endpoint} attempt {attempt+1} failed")
                attempt += 1
                if attempt >= self.max_retries:
                    break
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                await asyncio.sleep(sleep_time)
        endpoint = full_url.split("?")[0]
        logger.error(f"API {method} {endpoint} failed after {self.max_retries} attempts")
        raise last_exc

    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        **kwargs
    ) -> httpx.Response:
        return await self._request_with_retries(
            "GET", url, params=params, headers=headers, inject_params=inject_params, **kwargs
        )

    async def post(
        self,
        url: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        **kwargs
    ) -> httpx.Response:
        return await self._request_with_retries(
            "POST", url, data=data, headers=headers, inject_params=inject_params, **kwargs
        )