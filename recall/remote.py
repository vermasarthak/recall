import requests
from typing import List, Dict, Any, Optional

class RecallRemoteClient:
    """Synchronous Python client for interacting with the Recall FastAPI Server."""
    
    def __init__(self, base_url: str, tenant_id: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "x-tenant-id": self.tenant_id,
            "Content-Type": "application/json"
        })
        
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if not response.ok:
            raise RuntimeError(f"API Error {response.status_code}: {response.text}")
        return response.json()

    def ingest_turn(self, speaker: str, text: str, conversation_id: str) -> Dict[str, Any]:
        """Send a conversational turn for the engine to extract and persist facts."""
        payload = {
            "speaker": speaker,
            "text": text,
            "conversation_id": conversation_id
        }
        res = self.session.post(f"{self.base_url}/api/v1/ingest", json=payload)
        return self._handle_response(res)

    def query(self, about_entity: str, context: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Query memory facts about an entity."""
        payload = {
            "about_entity": about_entity,
            "context": context,
            "limit": limit
        }
        res = self.session.post(f"{self.base_url}/api/v1/query", json=payload)
        return self._handle_response(res)

    def format_for_prompt(self, about_entity: str, context: str = "", limit: int = 10, max_tokens: Optional[int] = None) -> str:
        """Get pre-formatted XML context ready for LLM injection."""
        payload = {
            "about_entity": about_entity,
            "context": context,
            "limit": limit,
            "max_tokens": max_tokens
        }
        res = self.session.post(f"{self.base_url}/api/v1/query/prompt-context", json=payload)
        data = self._handle_response(res)
        return data.get("xml_context", "")

    def forget(self, about_entity: str) -> Dict[str, Any]:
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
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
