from fastapi.testclient import TestClient
from recall.server.app import app

client = TestClient(app)
headers = {"Authorization": "Bearer sk-test", "x-tenant-id": "user123"}
ingest_payload = {
    "speaker": "John",
    "text": "John works at Google",
    "conversation_id": "c1"
}
response = client.post("/api/v1/ingest", headers=headers, json=ingest_payload)
print(response.status_code)
print(response.text)
