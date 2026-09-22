import os
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends
from starlette.concurrency import run_in_threadpool

from recall.client import Recall
from recall.models.fact import FactRecord

app = FastAPI(title="Recall Server", description="FastAPI Multi-Tenant Server for Recall Memory Engine")

# Multi-tenant state manager
class TenantManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.clients: Dict[str, Recall] = {}
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

    def get_client(self, tenant_id: str) -> Recall:
        if not tenant_id.isalnum():
            raise HTTPException(status_code=400, detail="Invalid Tenant ID format. Must be alphanumeric.")
            
        if tenant_id not in self.clients:
            db_path = os.path.join(self.data_dir, f"{tenant_id}.db")
            # In a real system, you might inject OpenAIEmbeddingProvider here
            self.clients[tenant_id] = Recall(db_path=db_path)
        return self.clients[tenant_id]

    def close_all(self):
        for client in self.clients.values():
            client.close()

tenant_manager = TenantManager()

# Dependency to extract tenant client
async def get_recall_client(x_tenant_id: str = Header(..., description="Tenant ID (e.g., user_123)")) -> Recall:
    return tenant_manager.get_client(x_tenant_id)

class IngestRequest(BaseModel):
    speaker: str
    text: str
    conversation_id: str
    message_id: Optional[str] = None
    timestamp: Optional[datetime] = None

class QueryRequest(BaseModel):
    about_entity: str
    context: str = ""
    min_salience: float = 0.2
    limit: int = 10

class PromptContextResponse(BaseModel):
    xml_context: str

@app.on_event("shutdown")
def shutdown_event():
    tenant_manager.close_all()

@app.post("/api/v1/ingest")
async def ingest_turn(req: IngestRequest, client: Recall = Depends(get_recall_client)):
    try:
        # Prevent event-loop blocking by running synchronous DB calls in a threadpool
        result = await run_in_threadpool(
            client.ingest_turn,
            speaker=req.speaker,
            text=req.text,
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            timestamp=req.timestamp
        )
        return {
            "inserted": len(result.inserted_facts),
            "reinforced": len(result.reinforced_facts),
            "unresolved": len(result.unresolved_conflicts)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/query")
async def query_memory(req: QueryRequest, client: Recall = Depends(get_recall_client)):
    try:
        results = await run_in_threadpool(
            client.query,
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit
        )
        return [
            {
                "fact": r.fact.model_dump(),
                "salience": r.salience.model_dump()
            } for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/query/prompt-context", response_model=PromptContextResponse)
async def get_prompt_context(req: QueryRequest, client: Recall = Depends(get_recall_client)):
    try:
        xml = await run_in_threadpool(
            client.format_for_prompt,
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit
        )
        return PromptContextResponse(xml_context=xml)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/history/{logical_id}")
async def get_history(logical_id: str, client: Recall = Depends(get_recall_client)):
    try:
        history = await run_in_threadpool(client.inspect_history, logical_id)
        return [h.model_dump() for h in history]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
