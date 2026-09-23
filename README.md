<h1 align="center">
  <img src="https://raw.githubusercontent.com/vermasarthak/recall/main/docs/logo.png" width="120" alt="Recall Logo" onerror="this.src='https://via.placeholder.com/120?text=🧠'"><br>
  Recall
</h1>

<p align="center">
  <strong>The Bitemporal Memory Engine for Long-Horizon AI Agents</strong>
</p>

<p align="center">
  <a href="https://github.com/vermasarthak/recall/actions"><img src="https://img.shields.io/github/actions/workflow/status/vermasarthak/recall/test.yml?style=flat-square" alt="Build Status"></a>
  <a href="https://pypi.org/project/recall/"><img src="https://img.shields.io/pypi/v/recall?style=flat-square" alt="PyPI version"></a>
  <a href="https://github.com/vermasarthak/recall/blob/main/LICENSE"><img src="https://img.shields.io/github/license/vermasarthak/recall?style=flat-square" alt="License"></a>
</p>

## The Problem
Standard RAG relies on vector databases that append new facts endlessly. If a user tells an agent "I live in New York", and 6 months later says "I just moved to London", a standard RAG system will embed both. When the agent asks "Where does the user live?", the vector database returns both. The LLM hallucinates or gets confused. 

Furthermore, memories decay. A minor detail mentioned 3 years ago shouldn't have the same context weight as a major life event mentioned yesterday.

## The Solution: Recall
**Recall** is a thread-safe, bitemporal entity-graph memory engine designed specifically for long-horizon AI companions and agents. 

It solves stateful memory through:
1. **Bitemporal Fact Tracking**: Memories are tracked by when they were true (`valid_time`) and when the agent learned them (`knowledge_time`). When facts change, the old fact is gracefully closed, not deleted.
2. **Ebbinghaus Salience Decay**: Memories automatically decay in relevance over time unless they are reinforced.
3. **Global Semantic Vector Search**: Under the hood, facts are cached as vector embeddings, allowing $O(N)$ semantic RAG searches globally across the SQLite graph.
4. **Deterministic Conflict Resolution**: New conflicting facts overwrite old ones deterministically, ensuring the LLM always gets a clean, conflict-free XML context block.

## Features
- 🚀 **Multi-Tenant FastAPI Server**: Built-in HTTP server with Bearer auth and Multi-tenant SQLite isolation (O(1) routing).
- 🧠 **Vector RAG Fallback**: Perform semantic queries against memory nodes when you don't know the exact Entity ID.
- 🧵 **Extreme Concurrency**: Hand-optimized Python SQLite drivers using thread-local pooling and WAL mode `RLock` mutexes for massive scale.
- 🗑️ **Garbage Collection & GDPR**: Delete isolated graphs or vacuum retracted historical data to save disk space.
- ⚡ **Async Python SDK**: Drop-in Python client (`RecallRemoteClient`) for seamless integration into your Agent loops.

---

## Quickstart

### 1. Installation
```bash
pip install recall
```

### 2. Start the Recall Server
Run the production server via Docker, or locally with required authentication:
```bash
export OPENAI_API_KEY="sk-..."
# Master key or tenant-bound keys (e.g. "key_user123:user_123,key_user456:user_456")
export RECALL_API_KEY="your-secret-key"
uvicorn recall.server.app:app --port 8000
```

### 3. Use the Python SDK in your Agent
```python
import asyncio
from recall.remote import AsyncRecallRemoteClient

async def main():
    async with AsyncRecallRemoteClient("http://localhost:8000", "your-secret-key") as client:
        
        # 1. Ingest a user's chat message
        await client.ingest_turn(
            tenant_id="user_123",
            speaker="User",
            text="I just got a new job at OpenAI! Moving to SF tomorrow.",
            conversation_id="conv_001"
        )
        
        # 2. Query memory semantically later
        results = await client.search(tenant_id="user_123", query="where do they work?")
        
        # 3. Format as a compressed XML block for your LLM Prompt
        xml_context = await client.format_for_prompt(tenant_id="user_123", about_entity="User")
        print(xml_context)
        # <memory entity='User'>
        #   <fact confidence='0.95'>works_at OpenAI</fact>
        #   <fact confidence='0.95'>lives_in San Francisco</fact>
        # </memory>

asyncio.run(main())
```

### 4. Command Line Interface
Recall ships with a built-in CLI for quick memory introspection:
```bash
recall --tenant user_123 search "OpenAI"
```

---

## How It Works

### The Ebbinghaus Salience Scorer
Recall uses a custom scoring algorithm to determine which facts are injected into your LLM's context window. The `Composite Score` combines:
1. **Semantic Similarity (40%)**: Cosine similarity between the agent's current query and the memory embedding.
2. **Retention (40%)**: An Ebbinghaus forgetting curve based on `elapsed_days` since the memory was last reinforced.
3. **Confidence (20%)**: The extraction confidence of the LLM pipeline.

### Try the Showcase AI Companion!
See the engine in action. We've included a terminal-based Chat Companion that uses the embedded `Recall` engine to talk to you.
```bash
export OPENAI_API_KEY="sk-..."
python examples/chat_companion.py
```

---
*Built for the future of Stateful AI.*
