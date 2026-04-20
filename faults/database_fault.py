"""
Real Database Fault Handler
- Fault:    Closes connection and deletes the SQLite DB file
- Recovery: Recreates the DB file, restores schema, verifies a real query works
"""

import gc
import os
import sqlite3
import tempfile
import time

# One DB file per process so Flask debug reloader (parent + child) does not
# share the same path and lock each other on Windows.
DB_PATH = os.path.join(tempfile.gettempdir(), f"cs527_system_{os.getpid()}.db")


class DatabaseFaultHandler:
    def __init__(self):
        self.db_path = DB_PATH
        self._conn = None
        self._setup_db()  # start healthy

    # ── DB Setup ────────────────────────────────────────────

    def _setup_db(self):
        """Create DB and schema from scratch."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Avoid WAL sidecar files (-wal/-shm); deleting the main file is simpler on Windows.
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS system_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event     TEXT,
                status    TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._conn.execute(
            "INSERT OR REPLACE INTO system_config VALUES (?,?)",
            ("initialized_at", str(time.time()))
        )
        self._conn.commit()

    # ── Fault & Recovery ────────────────────────────────────

    def _unlink_db_files(self):
        """Remove main DB and any SQLite sidecars; retry on Windows transient locks."""
        gc.collect()
        paths = [
            self.db_path,
            self.db_path + "-wal",
            self.db_path + "-shm",
            self.db_path + "-journal",
        ]
        for path in paths:
            if not os.path.isfile(path):
                continue
            for attempt in range(8):
                try:
                    os.remove(path)
                    break
                except PermissionError:
                    time.sleep(0.05 * (attempt + 1))
                except OSError:
                    break

    def trigger_fault(self):
        """
        Actually break the DB: close connection and delete the file.
        Any subsequent query will raise an error.
        """
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

        self._unlink_db_files()

    def try_recover(self):
        """
        Actually fix it: recreate the DB file, restore schema,
        then verify a real query executes successfully.
        """
        try:
            self._setup_db()
            return self._verify_db()
        except Exception as e:
            return False, f"DB rebuild failed: {e}"

    def _verify_db(self):
        """Run a real query to confirm DB is functional."""
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM system_config")
            count = cursor.fetchone()[0]
            # Write a test record to confirm writes work too
            self._conn.execute(
                "INSERT INTO system_log (timestamp, event, status) VALUES (?,?,?)",
                (str(time.time()), "recovery_check", "ok")
            )
            self._conn.commit()
            return True, f"DB verified — {count} config rows, write test passed"
        except Exception as e:
            return False, f"DB verification failed: {e}"

    def is_healthy(self):
        if self._conn is None:
            return False
        ok, _ = self._verify_db()
        return ok

    def log_event(self, event, status):
        """Used by the main system to write real events to the DB."""
        if self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO system_log (timestamp, event, status) VALUES (?,?,?)",
                    (str(time.time()), event, status)
                )
                self._conn.commit()
            except Exception:
                pass
