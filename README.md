# Recall: Temporal Entity Memory Engine

`Recall` is a production-grade, bitemporal entity memory engine built for long-horizon AI agents, relationship companions, and social applications.

Unlike traditional flat vector databases (which lack temporal awareness) or simple conversation scrolls (which hallucinate stale facts), Recall models memory as a **Bitemporal Knowledge Graph** with **Ebbinghaus retention decay**, **semantic conflict resolution**, and **contextual salience retrieval**.

## 🚀 Features

- **Bitemporal Fact Storage:** Every fact has independent valid-time (when it was true) and transaction-time (when the system knew it) intervals.
- **Deterministic Conflict Resolution:** Predicate policies handle multi-valued coexistence and single-valued conflict resolution with source precedence.
- **Ebbinghaus Memory Decay:** Facts naturally decay using the Ebbinghaus retention function $R(t) = \exp(-t/S)$ unless reinforced by conversation.
- **Proactive Contextual Salience:** Queries return scored facts evaluating lexical similarity, confidence, and retention.
- **Entity Resolution:** Jaro-Winkler fuzzy matching with ambiguity boundaries.
- **Offline & Local-First:** Pure Python + standard library SQLite3 (`sqlite3`). No cloud dependencies.

## 📦 Installation & Minimal Example

```bash
# Clone the repository
git clone https://github.com/vermasarthak/recall.git
cd recall

# Install package
pip install .
```

### Minimal Usage Example
```python
from datetime import datetime, timezone
from recall import Recall

# 1. Initialize offline client
client = Recall(db_path="recall.db")

# 2. Ingest structured turns (or use an LLM provider adapter)
res = client.ingest_turn(
    speaker="User",
    text="John works at Google",
    conversation_id="conv_1"
)

# 3. Time passes. Ingest a conflicting fact (John changes jobs)
client.ingest_turn(
    speaker="User",
    text="John started working at Amazon",
    conversation_id="conv_2",
)

# 4. Query current active memory
q = client.query("John", context="Where does he work?")
print(q[0].fact.object_value) # "Amazon"

client.close()
```

## 🧠 Core Concepts

### Valid Time vs Transaction Time
Recall implements a true **bitemporal** model using half-open intervals:
- **Valid Time (`valid_from`, `valid_to`)**: When the fact is true in the real world.
- **Transaction Time (`tx_from`, `tx_to`)**: When the system knew the fact.

If you learn today that someone changed jobs 2 months ago, Recall correctly branches historical knowledge without mutating past audit traces. You can query "What did we *believe* about John last month?" and get the historically accurate response.

### Predicate Cardinality & Conflict Policies
Not all facts conflict.
- **Single-Valued Predicates** (e.g., `primary_employer`, `residence`): A new high-confidence fact cleanly invalidates the old fact's `valid_to` interval.
- **Multi-Valued Predicates** (e.g., `speaks_language`, `likes`): Distinct facts cleanly coexist concurrently.
- **Retraction / Correction**: Explicit user edits override inference and hearsay via strict source precedence.

### Ebbinghaus Retention Scoring
Facts you don't reinforce naturally decay in relevance. 
The Ebbinghaus retention is given by: $R(t) = \exp(-t/S)$
Where $S = S_{\text{base}} \times (1 + \alpha \cdot N)$.
- $S_{\text{base}}$ = Base stability (default 10 days)
- $N$ = Number of independent conversational reinforcements.

## 🧪 Running the Demo and Tests

### Run the Offline WhatsApp Timeline Demo
Run the provided simulated 6-month offline WhatsApp timeline demo which showcases all core mechanics (fact transitions, reinforcements, history rewrites, and proactive relationship cues):
```bash
python examples/demo_whatsapp_timeline.py
```

### Run the Test Suite
The package includes a rigorous offline test suite verifying interval bounding, decay mathematics, provider serialization, and entity resolution constraints.
```bash
pytest -v
```

## ⚠️ Known Limitations
- **Concurrency:** Uses standard SQLite `WAL` mode. Designed for single-tenant or low-concurrency environments (one DB per memory owner). Do not use this as a distributed multi-tenant datastore.
- **Lexical Salience:** Default salience uses Jaccard lexical overlap. Semantic embedding endpoints (e.g., OpenAI embeddings) can be injected but are omitted by default to ensure the engine runs completely offline.
- **Timezone Safety:** Recall enforces strict timezone-aware (UTC) `datetime` objects. Naive datetimes will raise strict validation errors.

---
Built for the next generation of social AI agents.
