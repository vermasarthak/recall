from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from fastapi import FastAPI, HTTPException

from recall.client import Recall
from recall.models.fact import FactRecord

app = FastAPI(title="Recall Server", description="FastAPI Server for Recall Memory Engine")

# Dependency / Global State
# Note: In a production app, we would use a more robust lifecycle manager,
# but this global initialization works for the MVP.
recall_client = Recall(db_path="server.db")

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
    recall_client.close()

@app.post("/api/v1/ingest")
def ingest_turn(req: IngestRequest):
    try:
        result = recall_client.ingest_turn(
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
def query_memory(req: QueryRequest):
    try:
        results = recall_client.query(
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit
        )
        # Expose facts as dictionaries for JSON serialization
        return [
            {
                "fact": r.fact.model_dump(),
                "salience": r.salience.model_dump()
            } for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/query/prompt-context", response_model=PromptContextResponse)
def get_prompt_context(req: QueryRequest):
    try:
        xml = recall_client.format_for_prompt(
            about_entity=req.about_entity,
            context=req.context,
            min_salience=req.min_salience,
            limit=req.limit
        )
        return PromptContextResponse(xml_context=xml)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/history/{logical_id}")
def get_history(logical_id: str):
    try:
        history = recall_client.inspect_history(logical_id)
        return [h.model_dump() for h in history]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
