import pytest
import os
from fastapi.testclient import TestClient
from recall.server.app import app, tenant_manager

# Override the tenant manager data directory for testing
os.environ["RECALL_API_KEY"] = "sk-test"

@pytest.fixture
def client(tmp_path):
    # Set the global tenant manager to use a temp dir during tests
    tenant_manager.data_dir = str(tmp_path)
    tenant_manager.clients.clear()
    
    with TestClient(app) as c:
        yield c
        
    tenant_manager.close_all()

def test_unauthenticated_request_rejected(client):
    response = client.post("/api/v1/query", json={"about_entity": "John"})
    assert response.status_code in [401, 403] # Depending on FastAPI version, missing auth is 401 or 403

def test_invalid_api_key_rejected(client):
    headers = {"Authorization": "Bearer sk-wrong"}
    response = client.post("/api/v1/query", headers=headers, json={"about_entity": "John"})
    assert response.status_code == 401
    
def test_missing_tenant_id_rejected(client):
    headers = {"Authorization": "Bearer sk-test"}
    response = client.post("/api/v1/query", headers=headers, json={"about_entity": "John"})
    assert response.status_code == 422 # FastAPI missing header

def test_successful_ingest_and_query(client):
    headers = {"Authorization": "Bearer sk-test", "x-tenant-id": "user123"}
    
    # 1. Ingest
    ingest_payload = {
        "speaker": "John",
        "text": "John works at Google",
        "conversation_id": "c1"
    }
    response = client.post("/api/v1/ingest", headers=headers, json=ingest_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["inserted"] > 0
    
    # 2. Query
    query_payload = {
        "about_entity": "John",
        "context": "Where does John work?"
    }
    response = client.post("/api/v1/query", headers=headers, json=query_payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "Google" in data[0]["fact"]["object_value"]
    
def test_prompt_context_endpoint(client):
    headers = {"Authorization": "Bearer sk-test", "x-tenant-id": "user123"}
    # The DB is shared across tests in the same module if the fixture allows, but since it's same tenant, it should work.
    
    query_payload = {
        "about_entity": "John",
        "context": "Where does John work?"
    }
    response = client.post("/api/v1/query/prompt-context", headers=headers, json=query_payload)
    assert response.status_code == 200
    data = response.json()
    assert "<memory entity=" in data["xml_context"]

def test_vacuum_endpoint(client):
    headers = {"Authorization": "Bearer sk-test", "x-tenant-id": "user123"}
    response = client.post("/api/v1/admin/vacuum", headers=headers, json={"retention_days": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

def test_multi_tenant_isolation(client):
    headers_a = {"Authorization": "Bearer sk-test", "x-tenant-id": "tenantA"}
    headers_b = {"Authorization": "Bearer sk-test", "x-tenant-id": "tenantB"}
    
    # Write to A
    client.post("/api/v1/ingest", headers=headers_a, json={"speaker": "Alice", "text": "Alice likes apples", "conversation_id": "c1"})
    
    # Query A -> should see apples
    res_a = client.post("/api/v1/query", headers=headers_a, json={"about_entity": "Alice"})
    assert len(res_a.json()) > 0
    
    # Query B -> shouldn't see apples
    res_b = client.post("/api/v1/query", headers=headers_b, json={"about_entity": "Alice"})
    assert len(res_b.json()) == 0

def test_search_endpoint(client):
    headers = {"Authorization": "Bearer sk-test", "x-tenant-id": "user123"}
    # Ingest dummy data
    client.post("/api/v1/ingest", headers=headers, json={"speaker": "John", "text": "John likes StarWars", "conversation_id": "c1"})
    
    # Global Search
    search_payload = {
        "query": "watching movies",
        "min_salience": 0.0,
        "limit": 5
    }
    response = client.post("/api/v1/search", headers=headers, json=search_payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "Starwars" in data[0]["fact"]["object_value"]
