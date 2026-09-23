# Recall Limitations & Operational Boundaries

Recall is a bitemporal entity and fact store designed for long-horizon AI agent memory.

## Storage & Concurrency Model
- **SQLite Per-Tenant Storage**: Each tenant is isolated in a separate SQLite database file with WAL mode enabled.
- **Concurrency Boundaries**: SQLite WAL allows multiple concurrent readers and a serialized single writer per tenant database. It is intended for embedded agent memory and single-node service deployments, not distributed multi-region OLTP clusters.
- **Bitemporal Semantics**:
  - `valid_time`: The real-world half-open interval `[valid_from, valid_to)` during which the fact was or is true.
  - `knowledge_time`: The half-open interval `[knowledge_from, knowledge_to)` during which the system knew about the fact.
  - Historical facts are never deleted upon update; previous knowledge versions are closed with `knowledge_to = now()`.

## Semantic Retrieval & Tenant Isolation
- **Strict Tenant Scoping**: All vector similarity calculations and fact lookups are executed strictly within the caller's tenant database. Cross-tenant retrieval is architecturally prevented.
- **Provider Adapters**: Extraction and embedding adapters (e.g. OpenAI) require external API keys. Unit and regression tests use deterministic fakes and mocks.

## Unsupported Scenarios
- High-throughput multi-master distributed clustering.
- Arbitrary graph query languages (Cypher/SPARQL); query access is structured via bitemporal SQL assertions and point-in-time point/interval lookups.
