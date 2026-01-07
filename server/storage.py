"""
Storage layer for FailWatch
SQLite-based persistence for analysis records
"""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List


class AnalysisStorage:
    def __init__(self, db_path: str = "failwatch.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                output_hash TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence REAL NOT NULL,
                failure_types TEXT,
                recommended_action TEXT NOT NULL,
                explanation TEXT
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON analyses(timestamp DESC)
        """)

        conn.commit()
        conn.close()

    def save_analysis(
        self,
        task_type: str,
        input_hash: str,
        output_hash: str,
        verdict: str,
        confidence: float,
        failure_types: List[str],
        recommended_action: str,
        explanation: List[str],
    ) -> int:
        """
        Save an analysis record to the database
        Returns the record ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat()
        failure_types_str = ",".join(failure_types) if failure_types else ""
        explanation_str = " | ".join(explanation) if explanation else ""

        cursor.execute(
            """
            INSERT INTO analyses
            (timestamp, task_type, input_hash, output_hash, verdict, confidence,
             failure_types, recommended_action, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                timestamp,
                task_type,
                input_hash,
                output_hash,
                verdict,
                confidence,
                failure_types_str,
                recommended_action,
                explanation_str,
            ),
        )

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return record_id

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get the most recent analysis records
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, timestamp, task_type, input_hash, output_hash,
                   verdict, confidence, failure_types, recommended_action
            FROM analyses
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_by_hash(self, input_hash: str, output_hash: str) -> List[Dict[str, Any]]:
        """
        Find analyses by input/output hash (for inconsistency detection)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM analyses
            WHERE input_hash = ? OR output_hash = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """,
            (input_hash, output_hash),
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM analyses")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM analyses WHERE verdict = 'RISKY'")
        risky = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(confidence) FROM analyses")
        avg_confidence = cursor.fetchone()[0] or 0.0

        conn.close()

        return {
            "total_analyses": total,
            "risky_count": risky,
            "ok_count": total - risky,
            "average_confidence": round(avg_confidence, 2),
        }

    def clear_all(self):
        """
        Clear all records (for testing)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM analyses")
        conn.commit()
        conn.close()
