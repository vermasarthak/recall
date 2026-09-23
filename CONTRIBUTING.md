# Contributing to Recall

Recall is built as a bitemporal entity and fact store for long-horizon AI agents.

## Prerequisites
- Python 3.11+
- SQLite 3.35+ (with WAL support)

## Local Development Workflow

1. **Environment Setup**:
   ```bash
   git clone https://github.com/vermasarthak/recall.git
   cd recall
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev,server,client]"
   ```

2. **Linting & Code Style**:
   ```bash
   ruff check .
   ```

3. **Running Test Suite**:
   ```bash
   pytest -v
   ```

## Contribution Invariants
- **Bitemporal Invariants**: `valid_time` and `knowledge_time` must adhere strictly to half-open interval semantics `[from, to)`. Never mutate historical knowledge versions; close them with `tx_to = now()`.
- **Tenant Isolation**: Queries and vector embeddings must never cross tenant database boundaries.
- **Deterministic Time**: All time-dependent functions must use injectable `Clock` interfaces (`TestClock` / `SystemClock`).
