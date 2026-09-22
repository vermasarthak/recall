import re

with open("recall/db/store.py", "r") as f:
    content = f.read()

# Replace the init and connect logic
new_init = """
    def __init__(self, db_path: str = "recall.db", clock: Optional[Clock] = None):
        import threading
        self.db_path = db_path
        self.clock = clock or SystemClock()
        self._local = threading.local()
        self._write_lock = threading.Lock()
        
        # Init schema immediately on a temp connection
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
                    conn.execute("PRAGMA synchronous = NORMAL;")
                except sqlite3.OperationalError:
                    pass
            self._local.conn = conn
        return self._local.conn

    def get_connection(self) -> sqlite3.Connection:
        return self._get_local_conn()
"""

# Apply the regex substitution for __init__ to get_connection
pattern = r'    def __init__\(self, db_path.*?def get_connection\(self\) -> sqlite3\.Connection:.*?return self\._conn'

content = re.sub(pattern, new_init.strip(), content, flags=re.DOTALL)

with open("recall/db/store.py", "w") as f:
    f.write(content)
