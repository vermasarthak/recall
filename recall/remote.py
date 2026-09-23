import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import requests
import websockets


class RecallRemoteClient:
    """Synchronous Python client for interacting with the Recall FastAPI Server."""

    def __init__(self, base_url: str, tenant_id: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "x-tenant-id": self.tenant_id,
                "Content-Type": "application/json",
            }
        )

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        if not response.ok:
            raise RuntimeError(f"API Error {response.status_code}: {response.text}")
        return response.json()

    def ingest_turn(self, speaker: str, text: str, conversation_id: str) -> dict[str, Any]:
        """Send a conversational turn for the engine to extract and persist facts."""
        payload = {"speaker": speaker, "text": text, "conversation_id": conversation_id}
        res = self.session.post(f"{self.base_url}/api/v1/ingest", json=payload)
        return self._handle_response(res)

    def query(self, about_entity: str, context: str = "", limit: int = 10) -> list[dict[str, Any]]:
        """Query memory facts about an entity."""
        payload = {"about_entity": about_entity, "context": context, "limit": limit}
        res = self.session.post(f"{self.base_url}/api/v1/query", json=payload)
        return self._handle_response(res)

    def search(self, query: str, limit: int = 10, min_salience: float = 0.5) -> list[dict[str, Any]]:
        """Global semantic search across all memories using cosine similarity."""
        payload = {"query": query, "limit": limit, "min_salience": min_salience}
        res = self.session.post(f"{self.base_url}/api/v1/search", json=payload)
        return self._handle_response(res)

    def format_for_prompt(
        self, about_entity: str, context: str = "", limit: int = 10, max_tokens: int | None = None
    ) -> str:
        """Get pre-formatted XML context ready for LLM injection."""
        payload = {"about_entity": about_entity, "context": context, "limit": limit, "max_tokens": max_tokens}
        res = self.session.post(f"{self.base_url}/api/v1/query/prompt-context", json=payload)
        data = self._handle_response(res)
        return data.get("xml_context", "")

    def forget(self, about_entity: str) -> dict[str, Any]:
        """GDPR Right to be Forgotten. Permanently deletes an entity from the engine."""
        payload = {"about_entity": about_entity}
        res = self.session.post(f"{self.base_url}/api/v1/admin/forget", json=payload)
        return self._handle_response(res)

    def export_database(self, save_path: str) -> None:
        """Download the raw SQLite database for this tenant."""
        res = self.session.get(f"{self.base_url}/api/v1/admin/export", stream=True)
        if not res.ok:
            raise RuntimeError(f"Export Error {res.status_code}: {res.text}")

        with open(save_path, "wb") as f:
            f.writelines(res.iter_content(chunk_size=8192))


class AsyncRecallRemoteClient:
    """Asynchronous Python client for high-concurrency environments."""

    def __init__(self, base_url: str, tenant_id: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-tenant-id": self.tenant_id,
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(headers=self.headers, base_url=self.base_url)

    async def close(self):
        await self.client.aclose()

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise RuntimeError(f"API Error {response.status_code}: {response.text}")
        return response.json()

    async def ingest_turn(self, speaker: str, text: str, conversation_id: str) -> dict[str, Any]:
        payload = {"speaker": speaker, "text": text, "conversation_id": conversation_id}
        res = await self.client.post("/api/v1/ingest", json=payload)
        return self._handle_response(res)

    async def query(self, about_entity: str, context: str = "", limit: int = 10) -> list[dict[str, Any]]:
        payload = {"about_entity": about_entity, "context": context, "limit": limit}
        res = await self.client.post("/api/v1/query", json=payload)
        return self._handle_response(res)

    async def search(self, query: str, limit: int = 10, min_salience: float = 0.5) -> list[dict[str, Any]]:
        """Global semantic search across all memories using cosine similarity."""
        payload = {"query": query, "limit": limit, "min_salience": min_salience}
        res = await self.client.post("/api/v1/search", json=payload)
        return self._handle_response(res)

    async def format_for_prompt(
        self, about_entity: str, context: str = "", limit: int = 10, max_tokens: int | None = None
    ) -> str:
        payload = {"about_entity": about_entity, "context": context, "limit": limit, "max_tokens": max_tokens}
        res = await self.client.post("/api/v1/query/prompt-context", json=payload)
        data = self._handle_response(res)
        return data.get("xml_context", "")

    async def listen_for_events(self, callback_func: Callable[[dict[str, Any]], Any]):
        """Connects to the server's WebSocket to receive real-time memory updates."""
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_url}/api/v1/stream/{self.tenant_id}?token={self.api_key}"

        async with websockets.connect(uri) as ws:
            async for message in ws:
                data = json.loads(message)
                if asyncio.iscoroutinefunction(callback_func):
                    await callback_func(data)
                else:
                    callback_func(data)
