import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Security, WebSocket, WebSocketDisconnect, responses
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from recall.client import Recall
from recall.engine.extractor import OpenAIProviderAdapter
from recall.engine.similarity import OpenAIEmbeddingProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    tenant_manager.close_all()


app = FastAPI(
    title="Recall Server", description="FastAPI Multi-Tenant Server for Recall Memory Engine", lifespan=lifespan
)

# Security
security = HTTPBearer(auto_error=False)


def get_configured_api_keys() -> dict[str, str | None]:
    """
    Parses RECALL_API_KEYS (e.g. 'key1:tenant_1,key2:tenant_2' or single 'RECALL_API_KEY').
    Returns a dict mapping api_key -> bound_tenant_id (or None if key has access to all tenants).
    """
    keys_map: dict[str, str | None] = {}

    # 1. Multi-key binding format: RECALL_API_KEYS="sk-key1:tenant1,sk-key2:user_123"
    multi_keys = os.environ.get("RECALL_API_KEYS", "").strip()
    if multi_keys:
        for entry in multi_keys.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry:
                k, t = entry.split(":", 1)
                keys_map[k.strip()] = t.strip()
            else:
                keys_map[entry] = None

    # 2. Single master or dev key
    single_key = os.environ.get("RECALL_API_KEY", "").strip()
    if single_key:
        keys_map[single_key] = None

    # In test/dev environment, fallback only if RECALL_ALLOW_DEV_KEY is explicitly enabled
    if not keys_map and os.environ.get("RECALL_ALLOW_DEV_KEY", "").lower() in ("1", "true"):
        keys_map["sk-recall-dev-key"] = None

    return keys_map


def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    x_tenant_id: str | None = Header(None, alias="x-tenant-id"),
) -> str:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    keys_map = get_configured_api_keys()
    if not keys_map:
        raise HTTPException(
            status_code=500, detail="Server authentication is unconfigured. Set RECALL_API_KEY or RECALL_API_KEYS."
        )

    token = credentials.credentials
    if token not in keys_map:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    bound_tenant = keys_map[token]
    if bound_tenant is not None and x_tenant_id is not None:
        if bound_tenant != x_tenant_id:
            raise HTTPException(status_code=403, detail=f"API Key is not authorized for tenant '{x_tenant_id}'")

    return token


# Multi-tenant state manager
class TenantManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.clients: dict[str, Recall] = {}
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

    def validate_tenant_id(self, tenant_id: str) -> bool:
        """Validates tenant identifier allowing standard alphanumeric, underscores, and hyphens."""
        if not tenant_id or len(tenant_id) > 64:
            return False
        return all(c.isalnum() or c in ("_", "-") for c in tenant_id)

    def get_client(self, tenant_id: str) -> Recall:
        if not self.validate_tenant_id(tenant_id):
            raise HTTPException(
                status_code=400, detail="Invalid Tenant ID format. Must be alphanumeric with optional '_' or '-'."
            )

        if tenant_id not in self.clients:
            db_path = os.path.join(self.data_dir, f"{tenant_id}.db")

            extractor = None
            similarity = None
            openai_key = os.environ.get("OPENAI_API_KEY")

            if openai_key:
                extractor = OpenAIProviderAdapter(api_key=openai_key)
                # Note: To enable persistent vector caching, pass the store here once initialized
                similarity = OpenAIEmbeddingProvider(api_key=openai_key)

            client = Recall(db_path=db_path, extractor=extractor, similarity_provider=similarity)

            # Post-initialization inject cache for similarity provider
            if openai_key and isinstance(similarity, OpenAIEmbeddingProvider):
                similarity.cache = client.store

            self.clients[tenant_id] = client

        return self.clients[tenant_id]

    def close_all(self):
        for client in self.clients.values():
            client.close()


tenant_manager = TenantManager()


# WebSocket Manager for Real-Time Hooks
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = []
        self.active_connections[tenant_id].append(websocket)

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].remove(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


ws_manager = ConnectionManager()


# Dependency to extract tenant client
async def get_recall_client(x_tenant_id: str = Header(..., description="Tenant ID (e.g., user_123)")) -> Recall:
    return tenant_manager.get_client(x_tenant_id)


class IngestRequest(BaseModel):
    speaker: str = Field(..., max_length=100)
    text: str = Field(..., max_length=10000)
    conversation_id: str = Field(..., max_length=100)
    message_id: str | None = Field(None, max_length=100)
    timestamp: datetime | None = None


class QueryRequest(BaseModel):
    about_entity: str = Field(..., max_length=200)
    context: str = Field("", max_length=2000)
    min_salience: float = Field(0.2, ge=0.0, le=1.0)
    limit: int = Field(10, ge=1, le=100)
    max_tokens: int | None = Field(None, ge=10, le=32000)


class VacuumRequest(BaseModel):
    retention_days: int = Field(30, ge=0, le=3650)


class PromptContextResponse(BaseModel):
    xml_context: str


@app.websocket("/api/v1/stream/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: str, token: str):
    # Authenticate websocket
    keys_map = get_configured_api_keys()
    if not keys_map or token not in keys_map:
        await websocket.close(code=1008)
        return

    bound_tenant = keys_map[token]
    if bound_tenant is not None and bound_tenant != tenant_id:
        await websocket.close(code=1008)
        return

    if not tenant_manager.validate_tenant_id(tenant_id):
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket, tenant_id)
    try:
        while True:
            _ = await websocket.receive_text()
            # We only expect them to listen, but keep connection alive
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, tenant_id)


@app.post("/api/v1/ingest", dependencies=[Depends(verify_api_key)])
async def ingest_turn(req: IngestRequest, x_tenant_id: str = Header(...), client: Recall = Depends(get_recall_client)):
    try:
        result = await run_in_threadpool(
            client.ingest_turn,
            speaker=req.speaker,
            text=req.text,
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            timestamp=req.timestamp,
        )

        # Real-Time Broadcast if memory changed
        if result.inserted_facts or result.reinforced_facts:
            await ws_manager.broadcast_to_tenant(
                x_tenant_id,
                {
                    "event": "memory_updated",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "inserted": len(result.inserted_facts),
                    "reinforced": len(result.reinforced_facts),
                },
            )

        return {
            "inserted": len(result.inserted_facts),
            "reinforced": len(result.reinforced_facts),
            "unresolved": len(result.unresolved_conflicts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/query", dependencies=[Depends(verify_api_key)])
async def query_memory(req: QueryRequest, client: Recall = Depends(get_recall_client)):
    try:
        results = await run_in_threadpool(
            client.query,
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit,
        )
        return [{"fact": r.fact.model_dump(), "salience": r.salience.model_dump()} for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/query/prompt-context", response_model=PromptContextResponse, dependencies=[Depends(verify_api_key)])
async def get_prompt_context(req: QueryRequest, client: Recall = Depends(get_recall_client)):
    try:
        xml = await run_in_threadpool(
            client.format_for_prompt,
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit,
            max_tokens=req.max_tokens,
        )
        return PromptContextResponse(xml_context=xml)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/vacuum", dependencies=[Depends(verify_api_key)])
async def vacuum_database(req: VacuumRequest, client: Recall = Depends(get_recall_client)):
    try:
        deleted = await run_in_threadpool(client.vacuum_history, req.retention_days)
        return {"deleted_records": deleted, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/history/{logical_id}", dependencies=[Depends(verify_api_key)])
async def get_history(logical_id: str, client: Recall = Depends(get_recall_client)):
    try:
        history = await run_in_threadpool(client.inspect_history, logical_id)
        return [h.model_dump() for h in history]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ForgetEntityRequest(BaseModel):
    about_entity: str


@app.post("/api/v1/admin/forget", dependencies=[Depends(verify_api_key)])
async def forget_entity(req: ForgetEntityRequest, client: Recall = Depends(get_recall_client)):
    try:
        deleted = await run_in_threadpool(client.forget, req.about_entity)
        return {"deleted_records": deleted, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/export", dependencies=[Depends(verify_api_key)])
async def export_database(client: Recall = Depends(get_recall_client)):
    try:
        db_path = client.store.db_path
        if not os.path.exists(db_path):
            raise HTTPException(status_code=404, detail="Database file not found")
        return responses.FileResponse(
            path=db_path, filename=os.path.basename(db_path), media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    min_salience: float = Field(0.5, ge=0.0, le=1.0)
    limit: int = Field(10, ge=1, le=100)


@app.post("/api/v1/search", dependencies=[Depends(verify_api_key)])
async def search_memory(req: SearchRequest, client: Recall = Depends(get_recall_client)):
    try:
        results = await run_in_threadpool(client.search, query=req.query, min_score=req.min_salience, limit=req.limit)
        return [
            {"fact": r.fact.model_dump(), "salience": r.salience.model_dump(), "subject": r.subject_entity.model_dump()}
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
