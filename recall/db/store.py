"""Storage engine and SQLite persistence implementation for Recall."""

from datetime import datetime
import hashlib
import importlib.resources
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from recall.config import Clock, SystemClock, ensure_utc, parse_iso_utc, to_iso_utc
from recall.models.entity import EntityCreate, EntityRecord, EntityType
from recall.models.fact import FactRecord, RelationRecord, SourceType


def canonical_json_dumps(obj: Any) -> str:
    """Produces a deterministic, canonical JSON string representation of an object."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def calculate_fact_hash(subject_id: str, predicate: str, object_value: Any) -> str:
    """Calculates SHA-256 hash of (subject_id, predicate, canonical_json(object_value))."""
    c_json = canonical_json_dumps(object_value)
    raw_str = f"{subject_id}|{predicate}|{c_json}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


class StorageEngine:
    """Thread-safe SQLite storage engine with bitemporal transaction support."""

    def __init__(self, db_path: str = "recall.db", clock: Optional[Clock] = None):
        self.db_path = db_path
        self.clock = clock or SystemClock()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self.init_db()

    def _connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA busy_timeout = 5000;")
            if self.db_path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode = WAL;")
                except sqlite3.OperationalError:
                    pass

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._connect()
        return self._conn

    def init_db(self) -> None:
        """Initializes database schema from schema.sql."""
        conn = self.get_connection()
        try:
            schema_text = importlib.resources.files("recall.db").joinpath("schema.sql").read_text(encoding="utf-8")
        except Exception:
            # Fallback for local execution
            import os
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_text = f.read()

        with conn:
            conn.executescript(schema_text)
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?);", (to_iso_utc(self.clock.now()),))

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "StorageEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # --- ENTITY METHODS ---

    def create_entity(self, entity: EntityCreate, now: Optional[datetime] = None) -> EntityRecord:
        conn = self.get_connection()
        clock_now = ensure_utc(now or self.clock.now())
        entity_id = entity.id or f"ent_{uuid.uuid4().hex[:12]}"
        aliases_json = json.dumps(entity.aliases)
        metadata_json = json.dumps(entity.metadata)
        created_at_str = to_iso_utc(clock_now)

        with conn:
            conn.execute(
                """INSERT INTO entities (id, type, canonical_name, aliases, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?);""",
                (entity_id, entity.type.value, entity.canonical_name, aliases_json, metadata_json, created_at_str)
            )

        return EntityRecord(
            id=entity_id,
            type=entity.type,
            canonical_name=entity.canonical_name,
            aliases=entity.aliases,
            metadata=entity.metadata,
            created_at=clock_now
        )

    def get_entity_by_id(self, entity_id: str) -> Optional[EntityRecord]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM entities WHERE id = ?;", (entity_id,)).fetchone()
        if not row:
            return None
        return EntityRecord(
            id=row["id"],
            type=EntityType(row["type"]),
            canonical_name=row["canonical_name"],
            aliases=json.loads(row["aliases"]),
            metadata=json.loads(row["metadata"]),
            created_at=parse_iso_utc(row["created_at"])
        )

    def get_entity_by_canonical_name(self, name: str) -> Optional[EntityRecord]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM entities WHERE LOWER(canonical_name) = LOWER(?);", (name.strip(),)).fetchone()
        if not row:
            return None
        return EntityRecord(
            id=row["id"],
            type=EntityType(row["type"]),
            canonical_name=row["canonical_name"],
            aliases=json.loads(row["aliases"]),
            metadata=json.loads(row["metadata"]),
            created_at=parse_iso_utc(row["created_at"])
        )

    def get_all_entities(self) -> List[EntityRecord]:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM entities;").fetchall()
        return [
            EntityRecord(
                id=r["id"],
                type=EntityType(r["type"]),
                canonical_name=r["canonical_name"],
                aliases=json.loads(r["aliases"]),
                metadata=json.loads(r["metadata"]),
                created_at=parse_iso_utc(r["created_at"])
            )
            for r in rows
        ]

    # --- FACT BITEMPORAL METHODS ---

    def insert_fact_version(self, record: FactRecord, conn: Optional[sqlite3.Connection] = None) -> FactRecord:
        connection = conn or self.get_connection()
        obj_str = canonical_json_dumps(record.object_value)
        vf_str = to_iso_utc(record.valid_from)
        vt_str = to_iso_utc(record.valid_to) if record.valid_to else None
        tf_str = to_iso_utc(record.tx_from)
        tt_str = to_iso_utc(record.tx_to) if record.tx_to else None

        sql = """INSERT INTO facts (
                    version_id, logical_id, subject_id, predicate, object_value,
                    object_entity_id, confidence, source_type, source_ref,
                    valid_from, valid_to, tx_from, tx_to, fact_hash
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""
        params = (
            record.version_id, record.logical_id, record.subject_id, record.predicate,
            obj_str, record.object_entity_id, record.confidence, record.source_type.value,
            record.source_ref, vf_str, vt_str, tf_str, tt_str, record.fact_hash
        )

        if conn:
            connection.execute(sql, params)
        else:
            with connection:
                connection.execute(sql, params)

        return record

    def close_fact_tx_to(self, version_id: str, tx_to: datetime, conn: Optional[sqlite3.Connection] = None) -> None:
        """Closes tx_to of an existing version. This is the ONLY permitted mutation to historical versions."""
        connection = conn or self.get_connection()
        tx_to_str = to_iso_utc(ensure_utc(tx_to))
        
        # Verify not already closed
        row = connection.execute("SELECT tx_to FROM facts WHERE version_id = ?;", (version_id,)).fetchone()
        if not row:
            raise ValueError(f"Fact version_id '{version_id}' not found.")
        if row["tx_to"] is not None:
            raise ValueError(f"Repeated closure forbidden: version_id '{version_id}' already has tx_to={row['tx_to']}.")

        sql = "UPDATE facts SET tx_to = ? WHERE version_id = ?;"
        if conn:
            connection.execute(sql, (tx_to_str, version_id))
        else:
            with connection:
                connection.execute(sql, (tx_to_str, version_id))

    def close_fact_valid_to(self, version_id: str, valid_to: datetime, conn: Optional[sqlite3.Connection] = None) -> None:
        """Helper to close valid_to when building new versions (by writing a new version with tx_from=now)."""
        connection = conn or self.get_connection()
        vt_str = to_iso_utc(ensure_utc(valid_to))
        sql = "UPDATE facts SET valid_to = ? WHERE version_id = ?;"
        if conn:
            connection.execute(sql, (vt_str, version_id))
        else:
            with connection:
                connection.execute(sql, (vt_str, version_id))

    def insert_reinforcement(self, logical_fact_id: str, source_ref: str, reinforced_at: datetime, tx_time: datetime, conn: Optional[sqlite3.Connection] = None) -> str:
        connection = conn or self.get_connection()
        reinf_id = f"reinf_{uuid.uuid4().hex[:12]}"
        rf_str = to_iso_utc(ensure_utc(reinforced_at))
        tx_str = to_iso_utc(ensure_utc(tx_time))

        sql = """INSERT INTO reinforcements (id, logical_fact_id, source_ref, reinforced_at, tx_time)
                 VALUES (?, ?, ?, ?, ?);"""
        params = (reinf_id, logical_fact_id, source_ref, rf_str, tx_str)

        if conn:
            connection.execute(sql, params)
        else:
            with connection:
                connection.execute(sql, params)

        return reinf_id

    def get_reinforcements_count(self, logical_fact_id: str, max_reinforced_at: datetime, max_tx_time: datetime) -> int:
        conn = self.get_connection()
        rf_max = to_iso_utc(ensure_utc(max_reinforced_at))
        tx_max = to_iso_utc(ensure_utc(max_tx_time))

        sql = """SELECT COUNT(DISTINCT source_ref) as cnt FROM reinforcements
                 WHERE logical_fact_id = ?
                   AND reinforced_at <= ?
                   AND tx_time <= ?;"""
        row = conn.execute(sql, (logical_fact_id, rf_max, tx_max)).fetchone()
        return row["cnt"] if row else 0

    def query_facts(
        self,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        valid_at: Optional[datetime] = None,
        known_at: Optional[datetime] = None
    ) -> List[FactRecord]:
        """Queries facts using bitemporal eligibility:
        
            valid_from <= valid_at AND (valid_to IS NULL OR valid_at < valid_to)
            AND tx_from <= known_at AND (tx_to IS NULL OR known_at < tx_to)
        """
        conn = self.get_connection()
        v_at = to_iso_utc(ensure_utc(valid_at or self.clock.now()))
        k_at = to_iso_utc(ensure_utc(known_at or self.clock.now()))

        query = """SELECT * FROM facts
                   WHERE valid_from <= ? AND (valid_to IS NULL OR ? < valid_to)
                     AND tx_from <= ? AND (tx_to IS NULL OR ? < tx_to)"""
        params: List[Any] = [v_at, v_at, k_at, k_at]

        if subject_id:
            query += " AND subject_id = ?"
            params.append(subject_id)
        if predicate:
            query += " AND predicate = ?"
            params.append(predicate)

        query += " ORDER BY valid_from DESC;"

        rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def query_history(self, logical_id: str) -> List[FactRecord]:
        """Inspects all historical and active versions for a logical fact ID."""
        conn = self.get_connection()
        sql = "SELECT * FROM facts WHERE logical_id = ? ORDER BY tx_from ASC, version_id ASC;"
        rows = conn.execute(sql, (logical_id,)).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def _row_to_fact(self, row: sqlite3.Row) -> FactRecord:
        return FactRecord(
            version_id=row["version_id"],
            logical_id=row["logical_id"],
            subject_id=row["subject_id"],
            predicate=row["predicate"],
            object_value=json.loads(row["object_value"]),
            object_entity_id=row["object_entity_id"],
            confidence=row["confidence"],
            source_type=SourceType(row["source_type"]),
            source_ref=row["source_ref"],
            valid_from=parse_iso_utc(row["valid_from"]),
            valid_to=parse_iso_utc(row["valid_to"]) if row["valid_to"] else None,
            tx_from=parse_iso_utc(row["tx_from"]),
            tx_to=parse_iso_utc(row["tx_to"]) if row["tx_to"] else None,
            fact_hash=row["fact_hash"]
        )

    def get_string_embedding(self, text_hash: str) -> Optional[List[float]]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT embedding_json FROM string_embeddings WHERE text_hash = ?",
                (text_hash,)
            ).fetchone()
            if row:
                return json.loads(row["embedding_json"])
        return None

    def save_string_embedding(self, text_hash: str, embedding: List[float]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO string_embeddings (text_hash, embedding_json) VALUES (?, ?)",
                (text_hash, json.dumps(embedding))
            )

    def vacuum_history(self, retention_days: int) -> int:
        """Deletes historical records older than retention_days and reclaims disk space."""
        from datetime import timedelta
        threshold_time = self.clock.now() - timedelta(days=retention_days)
        threshold_str = threshold_time.isoformat()
        
        deleted_count = 0
        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM facts WHERE tx_to IS NOT NULL AND tx_to < ?",
                (threshold_str,)
            )
            deleted_count += cursor.rowcount
            
            cursor = conn.execute(
                "DELETE FROM relations WHERE tx_to IS NOT NULL AND tx_to < ?",
                (threshold_str,)
            )
            deleted_count += cursor.rowcount

        # Reclaim disk space (must run outside transaction)
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
            
        return deleted_count

    def forget_entity(self, entity_id: str) -> int:
        """GDPR Right to be Forgotten. Hard deletes an entity and all its history."""
        deleted_count = 0
        with self.get_connection() as conn:
            # Delete facts where entity is subject or object
            cursor = conn.execute("DELETE FROM facts WHERE subject_id = ? OR object_entity_id = ?", (entity_id, entity_id))
            deleted_count += cursor.rowcount
            
            # Delete relations
            cursor = conn.execute("DELETE FROM relations WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
            deleted_count += cursor.rowcount
            
            # Delete entity itself
            cursor = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            deleted_count += cursor.rowcount
            
        return deleted_count
