"""
SQLite-backed project store (Slice A minimal).
"""
import json
import os
import sqlite3
from typing import Optional


class ProjectStore:
    def __init__(self, db_path: str = "data/projects.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def save(self, project_id: str, state_dict: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects (project_id, state_json) VALUES (?, ?);",
                (project_id, json.dumps(state_dict, default=str)),
            )
            conn.commit()

    def load(self, project_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT state_json FROM projects WHERE project_id = ?;", (project_id,)).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list_ids(self) -> list:
        with self._conn() as conn:
            return [r[0] for r in conn.execute("SELECT project_id FROM projects;").fetchall()]
