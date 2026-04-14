from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings

LOGGER = logging.getLogger(__name__)


class AllDebridError(RuntimeError):
    pass


class AllDebridClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = "https://api.alldebrid.com"
        self.session = requests.Session()
        retry = Retry(
            total=settings.retry_count,
            connect=settings.retry_count,
            read=settings.retry_count,
            backoff_factor=settings.retry_delay,
            allowed_methods=["GET", "POST", "HEAD"],
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.alldebrid_api_key}",
                "User-Agent": settings.alldebrid_agent,
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(1, self.settings.retry_count + 2):
            try:
                if method == "GET":
                    response = self.session.get(url, timeout=timeout or self.settings.request_timeout)
                else:
                    response = self.session.post(url, data=data or {}, timeout=timeout or self.settings.request_timeout)
                return self._handle_response(response)
            except (requests.RequestException, AllDebridError) as exc:
                if attempt > self.settings.retry_count:
                    raise AllDebridError(f"AllDebrid request failed for {path}: {exc}") from exc
                wait_seconds = self.settings.retry_delay * attempt
                LOGGER.warning("AllDebrid request failed on attempt %s/%s for %s: %s", attempt, self.settings.retry_count + 1, path, exc)
                time.sleep(wait_seconds)
        raise AllDebridError(f"Unreachable error path for {path}")

    def _handle_response(self, response: Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            error_code = payload.get("error", {}).get("code") if isinstance(payload.get("error"), dict) else payload.get("error")
            raise AllDebridError(f"API returned non-success response: {error_code or payload}")
        return payload.get("data", {})

    def test_auth(self) -> dict[str, Any]:
        return self._request("GET", "/v4/user")

    def add_magnet(self, magnet_uri: str) -> dict[str, Any]:
        return self._request("POST", "/v4.1/magnet/upload", data={"magnets[]": magnet_uri})

    def magnet_status(self, remote_id: int | None = None, status: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if remote_id is not None:
            data["id"] = remote_id
        if status:
            data["status"] = status
        return self._request("POST", "/v4.1/magnet/status", data=data)

    def magnet_files(self, remote_ids: list[int]) -> dict[str, Any]:
        payload: list[tuple[str, str]] = [("id[]", str(remote_id)) for remote_id in remote_ids]
        url = f"{self.base_url}/v4.1/magnet/files"
        response = self.session.post(url, data=payload, timeout=self.settings.request_timeout)
        return self._handle_response(response)

    def unlock_link(self, link: str) -> dict[str, Any]:
        return self._request("POST", "/v4/link/unlock", data={"link": link})

    def delayed_link(self, delayed_id: str | int) -> dict[str, Any]:
        return self._request("POST", "/v4/link/delayed", data={"id": str(delayed_id)})
