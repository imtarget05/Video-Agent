"""
Cost Accounting Ledger for Video-Agent.
Tracks 'cost per finished minute' (CPFM), retry ratios, and gross-to-net efficiency.
"""
import sqlite3
import os
from typing import Dict, Any, List, Optional
from backend.app.agent.state import CostRecord


def _resolve_db_path(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # Accept sqlite:///path or plain path.
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        if url.startswith("sqlite://"):
            return url[len("sqlite://"):]
        return url
    return os.getenv("LEDGER_DB_PATH", "data/video_agent.db")


class CostLedger:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _resolve_db_path(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cost_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    cost_usd REAL NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Migration for DBs created before prompt_tokens column existed.
            cols = [r[1] for r in conn.execute("PRAGMA table_info(cost_records)").fetchall()]
            if "prompt_tokens" not in cols:
                conn.execute("ALTER TABLE cost_records ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0;")
            conn.commit()

    def record_cost(self, project_id: str, record: CostRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO cost_records (project_id, job_id, provider, duration_sec, cost_usd, attempt_number, status, prompt_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                project_id,
                record.job_id,
                record.provider,
                record.duration_sec,
                record.cost_usd,
                record.attempt_number,
                record.status,
                record.prompt_tokens or 0
            ))
            conn.commit()

    def get_project_metrics(self, project_id: str, approved_final_seconds: float) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT 
                    COUNT(*) as total_calls,
                    SUM(duration_sec) as gross_generated_seconds,
                    SUM(cost_usd) as total_spend_usd,
                    SUM(prompt_tokens) as total_prompt_tokens,
                    SUM(CASE WHEN attempt_number > 1 THEN 1 ELSE 0 END) as retries_count,
                    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count
                FROM cost_records
                WHERE project_id = ?;
            """, (project_id,))
            row = cur.fetchone()

        total_calls = row["total_calls"] or 0
        gross_seconds = row["gross_generated_seconds"] or 0.0
        total_spend = row["total_spend_usd"] or 0.0
        total_prompt_tokens = row["total_prompt_tokens"] or 0
        retries = row["retries_count"] or 0

        # Finished minutes of output
        final_minutes = (approved_final_seconds / 60.0) if approved_final_seconds > 0 else 0.0
        cpfm = round(total_spend / final_minutes, 2) if final_minutes > 0 else 0.0

        # Retry ratio
        retry_ratio = round(retries / total_calls, 3) if total_calls > 0 else 0.0

        # Gross to net seconds ratio (lower is more efficient, 1.0 is perfect)
        gross_to_net = round(gross_seconds / approved_final_seconds, 2) if approved_final_seconds > 0 else 0.0

        return {
            "project_id": project_id,
            "total_spend_usd": round(total_spend, 3),
            "gross_generated_seconds": round(gross_seconds, 2),
            "approved_final_seconds": round(approved_final_seconds, 2),
            "cost_per_finished_minute": cpfm,
            "retry_ratio": retry_ratio,
            "gross_to_net_ratio": gross_to_net,
            "total_prompt_tokens": int(total_prompt_tokens),
            "total_generation_calls": total_calls
        }
