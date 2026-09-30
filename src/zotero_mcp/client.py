"""Thin async client for the Zotero Web API and the Zotero 7 local API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

WEB_API_URL = "https://api.zotero.org"
LOCAL_API_URL = "http://localhost:23119/api"


class ZoteroError(Exception):
    pass


@dataclass
class ZoteroConfig:
    base_url: str
    library_prefix: str
    api_key: str | None
    local: bool

    @classmethod
    def from_env(cls) -> ZoteroConfig:
        local = os.environ.get("ZOTERO_LOCAL", "").lower() in ("1", "true", "yes")
        library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user").lower()
        if library_type not in ("user", "group"):
            raise ZoteroError("ZOTERO_LIBRARY_TYPE must be 'user' or 'group'")

        if local:
            # The local API always exposes the signed-in user's library as user 0.
            library_id = os.environ.get("ZOTERO_LIBRARY_ID", "0")
            return cls(LOCAL_API_URL, f"/{library_type}s/{library_id}", None, True)

        api_key = os.environ.get("ZOTERO_API_KEY")
        library_id = os.environ.get("ZOTERO_LIBRARY_ID")
        if not api_key or not library_id:
            raise ZoteroError(
                "Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID, or set ZOTERO_LOCAL=true "
                "to use the Zotero desktop app's local API."
            )
        return cls(WEB_API_URL, f"/{library_type}s/{library_id}", api_key, False)


class ZoteroClient:
    def __init__(self, config: ZoteroConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        headers = {"Zotero-API-Version": "3"}
        if config.api_key:
            headers["Zotero-API-Key"] = config.api_key
        self._http = httpx.AsyncClient(
            base_url=config.base_url + config.library_prefix,
            headers=headers,
            timeout=30.0,
            transport=transport,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            if self.config.local:
                raise ZoteroError(
                    "Could not reach Zotero on localhost:23119. Make sure Zotero 7 is running "
                    "and 'Allow other applications on this computer to communicate with Zotero' "
                    "is enabled in Settings > Advanced."
                ) from e
            raise ZoteroError(f"Could not reach the Zotero API: {e}") from e
        if resp.status_code == 403:
            raise ZoteroError("Zotero returned 403 Forbidden. Check the API key and its permissions.")
        if resp.status_code == 404:
            raise ZoteroError(f"Not found: {path}")
        if resp.status_code >= 400:
            raise ZoteroError(f"Zotero API error {resp.status_code}: {resp.text[:300]}")
        return resp

    async def get(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def post(self, path: str, body: Any) -> Any:
        if self.config.local:
            raise ZoteroError("The Zotero local API is read-only. Use the Web API to make changes.")
        resp = await self._request("POST", path, json=body)
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
