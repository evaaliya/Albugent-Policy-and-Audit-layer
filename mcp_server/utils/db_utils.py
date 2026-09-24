"""
Almost unchanged from Albugent's db_utils.py — same idea (thin sqlite helpers),
just pointed at actions_log.db instead of a business dataset.
"""
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "actions_log.db"
SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "schema.sql"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_agent_trust(agent_id: str) -> float:
    conn = get_connection()
    row = conn.execute(
        "SELECT trust_score FROM agent_trust WHERE agent_id = ?;", (agent_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return 0.5  # unknown agent: neutral starting trust, same spirit as Albugent's is_orphan default
    return float(row["trust_score"])


def bump_agent_trust(agent_id: str, approved: bool) -> None:
    """Called only from the Tier 2 resolution path — never reachable from an MCP tool."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM agent_trust WHERE agent_id = ?;", (agent_id,)).fetchone()
    if row is None:
        trust = 0.5
        approved_count = 0
        denied_count = 0
    else:
        trust = row["trust_score"]
        approved_count = row["approved_count"]
        denied_count = row["denied_count"]

    if approved:
        approved_count += 1
        trust = min(1.0, trust + 0.03)
    else:
        denied_count += 1
        trust = max(0.0, trust - 0.15)  # denials cost more than approvals earn — asymmetric on purpose

    conn.execute(
        """INSERT INTO agent_trust (agent_id, trust_score, approved_count, denied_count, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(agent_id) DO UPDATE SET
               trust_score = excluded.trust_score,
               approved_count = excluded.approved_count,
               denied_count = excluded.denied_count,
               updated_at = excluded.updated_at;""",
        (agent_id, trust, approved_count, denied_count, now_iso()),
    )
    conn.commit()
    conn.close()


def get_session_actions(session_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM actions WHERE session_id = ? ORDER BY created_at ASC;", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_history(agent_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if category:
        rows = conn.execute(
            "SELECT * FROM actions WHERE agent_id = ? AND category = ? ORDER BY created_at ASC;",
            (agent_id, category),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM actions WHERE agent_id = ? ORDER BY created_at ASC;", (agent_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_action(action_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM actions WHERE action_id = ?;", (action_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_action(record: Dict[str, Any]) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO actions
           (action_id, session_id, agent_id, item, category, merchant, amount, created_at,
            risk_score, category_severity, anomaly_flags, status, reason,
            resolution, resolved_at, resolved_by)
           VALUES (:action_id, :session_id, :agent_id, :item, :category, :merchant, :amount, :created_at,
                   :risk_score, :category_severity, :anomaly_flags, :status, :reason,
                   :resolution, :resolved_at, :resolved_by);""",
        record,
    )
    conn.commit()
    conn.close()


def update_action_resolution(action_id: str, resolution: str, resolved_by: str) -> None:
    """Only called from the Tier 2 web_api service, never from an MCP tool."""
    conn = get_connection()
    conn.execute(
        "UPDATE actions SET resolution = ?, resolved_at = ?, resolved_by = ? WHERE action_id = ?;",
        (resolution, now_iso(), resolved_by, action_id),
    )
    conn.commit()
    conn.close()
