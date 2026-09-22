import re

with open("recall/db/store.py", "r") as f:
    content = f.read()

# 1. Add threading.local and Lock to __init__
new_init = """    def __init__(self, db_path: str = "recall.db", clock: Optional[Clock] = None):
        import threading
        self.db_path = db_path
        self.clock = clock or SystemClock()
        self._local = threading.local()
        self._write_lock = threading.RLock()
        
        self.init_db()

    def _get_local_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            if self.db_path != ":memory:":
                try:
                    conn.execute("PRAGMA journal_mode = WAL;")
                except sqlite3.OperationalError:
                    pass
            self._local.conn = conn
        return self._local.conn

    def get_connection(self) -> sqlite3.Connection:
        return self._get_local_conn()"""

pattern_init = r'    def __init__\(self, db_path.*?def get_connection\(self\) -> sqlite3\.Connection:.*?return self\._conn'
content = re.sub(pattern_init, new_init.strip(), content, flags=re.DOTALL)

# 2. Fix the Repeated closure race condition
old_close = """        # Verify not already closed
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
                connection.execute(sql, (tx_to_str, version_id))"""

new_close = """        sql = "UPDATE facts SET tx_to = ? WHERE version_id = ? AND tx_to IS NULL;"
        
        def execute_update(c):
            cursor = c.execute(sql, (tx_to_str, version_id))
            if cursor.rowcount == 0:
                row = c.execute("SELECT tx_to FROM facts WHERE version_id = ?;", (version_id,)).fetchone()
                if not row:
                    raise ValueError(f"Fact version_id '{version_id}' not found.")
                raise ValueError(f"Repeated closure forbidden: version_id '{version_id}' already has tx_to={row['tx_to']}.")

        if conn:
            execute_update(connection)
        else:
            with self._write_lock:
                with connection:
                    execute_update(connection)"""
content = content.replace(old_close, new_close)

# 3. Add `with self._write_lock:` to the core mutating transactions.
# create_entity
content = content.replace("with conn:\n            conn.execute(\n                \"\"\"INSERT INTO entities", "with self._write_lock, conn:\n            conn.execute(\n                \"\"\"INSERT INTO entities")

# insert_fact_version
content = content.replace("with connection:\n                connection.execute(sql, params)", "with self._write_lock, connection:\n                connection.execute(sql, params)")

# insert_reinforcement
content = content.replace("with connection:\n                connection.execute(sql, params)", "with self._write_lock, connection:\n                connection.execute(sql, params)")

with open("recall/db/store.py", "w") as f:
    f.write(content)

