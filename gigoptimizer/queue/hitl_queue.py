from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..models import ApprovalRecord, ValidationIssue


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HITLQueue:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_queue (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    current_value TEXT NOT NULL,
                    proposed_value TEXT NOT NULL,
                    confidence_score INTEGER NOT NULL,
                    validator_issues TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_notes TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.commit()

    def enqueue(
        self,
        *,
        agent_name: str,
        action_type: str,
        current_value: str,
        proposed_value: str,
        confidence_score: int,
        validator_issues: list[ValidationIssue] | None = None,
        status: str = "pending",
    ) -> ApprovalRecord:
        record = ApprovalRecord(
            id=str(uuid.uuid4()),
            agent_name=agent_name,
            action_type=action_type,
            current_value=current_value,
            proposed_value=proposed_value,
            confidence_score=confidence_score,
            validator_issues=validator_issues or [],
            status=status,
            created_at=utc_now_iso(),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                INSERT INTO approval_queue (
                    id, agent_name, action_type, current_value, proposed_value,
                    confidence_score, validator_issues, status, created_at, reviewed_at, reviewer_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.agent_name,
                    record.action_type,
                    record.current_value,
                    record.proposed_value,
                    record.confidence_score,
                    json.dumps([asdict(issue) for issue in record.validator_issues]),
                    record.status,
                    record.created_at,
                    record.reviewed_at,
                    record.reviewer_notes,
                ),
            )
            connection.commit()
        return record

    def list_records(self, *, status: str | None = None) -> list[ApprovalRecord]:
        query = """
            SELECT id, agent_name, action_type, current_value, proposed_value,
                   confidence_score, validator_issues, status, created_at, reviewed_at, reviewer_notes
            FROM approval_queue
        """
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"

        with closing(sqlite3.connect(self.db_path)) as connection:
            with closing(connection.execute(query, params)) as cursor:
                rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_status(
        self,
        record_id: str,
        *,
        status: str,
        reviewer_notes: str = "",
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            cursor = connection.execute(
                """
                UPDATE approval_queue
                SET status = ?, reviewed_at = ?, reviewer_notes = ?
                WHERE id = ?
                """,
                (status, utc_now_iso(), reviewer_notes, record_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise KeyError(record_id)

    def _row_to_record(self, row) -> ApprovalRecord:
        issues_raw = json.loads(row[6] or "[]")
        issues = [ValidationIssue(**item) for item in issues_raw]
        return ApprovalRecord(
            id=row[0],
            agent_name=row[1],
            action_type=row[2],
            current_value=row[3],
            proposed_value=row[4],
            confidence_score=row[5],
            validator_issues=issues,
            status=row[7],
            created_at=row[8],
            reviewed_at=row[9],
            reviewer_notes=row[10],
        )
