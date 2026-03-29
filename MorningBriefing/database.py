import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv  # type: ignore

load_dotenv()

# Reads DB_PATH from .env — add this line to your .env:  DB_PATH=auditpilot.db
_default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auditpilot.db")
DB_PATH = os.getenv("DB_PATH", _default)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates all tables if they don't exist.
    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS.
    Schema matches the shared auditpilot.db exactly.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ── traces — every agent decision ──────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     TEXT,
            workflow_type   TEXT,
            step_id         TEXT,
            agent           TEXT,
            input_data      TEXT,
            output_data     TEXT,
            status          TEXT,
            error_hash      TEXT,
            error_type      TEXT,
            decision        TEXT,
            decision_reason TEXT,
            duration_ms     INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── tasks — extracted + assigned/escalated tasks ───────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id     TEXT PRIMARY KEY,
            workflow_id TEXT,
            owner_id    TEXT,
            owner_name  TEXT,
            title       TEXT,
            deadline    TEXT,
            priority    TEXT,
            status      TEXT DEFAULT 'assigned',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── pattern_memory — cross-workflow error learning ─────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_memory (
            error_hash          TEXT PRIMARY KEY,
            error_type          TEXT,
            agent               TEXT,
            recommended_action  TEXT,
            attempts            INTEGER DEFAULT 0,
            successes           INTEGER DEFAULT 0,
            success_rate        REAL DEFAULT 0.0,
            last_seen_at        TEXT DEFAULT CURRENT_TIMESTAMP,
            context             TEXT,
            systemic_flag       INTEGER DEFAULT 0,
            last_systemic_at    TEXT
        )
    """)

    # ── systemic_alerts — W4 cross-workflow alerts ─────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS systemic_alerts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            error_hash          TEXT,
            error_type          TEXT,
            affected_workflows  TEXT,
            occurrence_count    INTEGER DEFAULT 0,
            context             TEXT,
            resolved            INTEGER DEFAULT 0,
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── briefing_log — module 6 email log ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS briefing_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            briefing_date   TEXT,
            items_count     INTEGER DEFAULT 0,
            email_sent      INTEGER DEFAULT 0,
            content         TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── clients — W1 onboarding ────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id       TEXT PRIMARY KEY,
            name            TEXT,
            email           TEXT,
            phone           TEXT,
            gstin           TEXT,
            business_type   TEXT,
            onboarded_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            status          TEXT DEFAULT 'active'
        )
    """)

    # ── purchase_orders — W2 procurement ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number       TEXT PRIMARY KEY,
            vendor_id       TEXT,
            vendor_name     TEXT,
            amount          REAL,
            invoice_amount  REAL,
            status          TEXT DEFAULT 'pending',
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("[database] All tables ready")


# ─────────────────────────────────────────
# SAVE FUNCTIONS — used by meeting_agent.py
# ─────────────────────────────────────────

def save_trace(workflow_id: str, agent: str, action: str,
               outcome: str, decision: str, reason: str,
               duration_ms: int = 0) -> None:
    """Saves one agent decision to traces table."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO traces
            (workflow_id, agent, status,
             decision, decision_reason, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (workflow_id, agent, outcome, decision, reason, duration_ms))
    conn.commit()
    conn.close()


def save_task(workflow_id: str, task: dict) -> None:
    """Saves one task (assigned or escalated) to tasks table."""
    import uuid
    task_id = f"TASK-{uuid.uuid4().hex[:6].upper()}"

    if task.get("decision") == "assigned":
        owner = task.get("owner", {})
        conn = get_connection()
        conn.execute("""
            INSERT OR IGNORE INTO tasks
                (task_id, workflow_id, owner_id, owner_name,
                 title, deadline, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'assigned')
        """, (
            task_id,
            workflow_id,
            owner.get("id"),
            owner.get("name"),
            task.get("task"),
            task.get("deadline"),
            task.get("priority"),
        ))
        conn.commit()
        conn.close()
    else:
        conn = get_connection()
        conn.execute("""
            INSERT OR IGNORE INTO tasks
                (task_id, workflow_id, owner_name,
                 title, deadline, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, 'escalated')
        """, (
            task_id,
            workflow_id,
            task.get("owner_searched"),
            task.get("task"),
            task.get("deadline"),
            task.get("priority"),
        ))
        conn.commit()
        conn.close()


def save_human_action(workflow_id: str, step: str,
                      task_text: str, reason: str,
                      action_needed: str) -> None:
    """
    Team DB has no human_actions table.
    We log these as escalated traces so W4 can detect them.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO traces
            (workflow_id, agent, status, decision, decision_reason)
        VALUES (?, ?, 'escalated', 'human_required', ?)
    """, (workflow_id, step, f"{reason} | action: {action_needed}"))
    conn.commit()
    conn.close()


def save_workflow(workflow_id: str, workflow_type: str,
                  input_text: str) -> None:
    """
    Team DB has no workflows table.
    We log workflow start as a trace entry so it's visible in DB.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO traces
            (workflow_id, agent, status, decision, decision_reason)
        VALUES (?, 'orchestrator', 'running', 'started', ?)
    """, (workflow_id, f"workflow started: {workflow_type}"))
    conn.commit()
    conn.close()


def update_workflow_summary(workflow_id: str, summary: dict) -> None:
    """
    Team DB has no workflows table.
    We log workflow completion as a trace entry.
    """
    conn = get_connection()
    outcome = summary.get("outcome", "completed")
    autonomy = summary.get("autonomy_rate", "0%")
    assigned = summary.get("assigned", 0)
    escalated = summary.get("escalated", 0)
    conn.execute("""
        INSERT INTO traces
            (workflow_id, agent, status, decision, decision_reason)
        VALUES (?, 'orchestrator', ?, 'completed', ?)
    """, (
        workflow_id,
        outcome,
        f"autonomy={autonomy} assigned={assigned} escalated={escalated}"
    ))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# READ FUNCTIONS — for API endpoints
# ─────────────────────────────────────────

def get_workflow_traces(workflow_id: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM traces
        WHERE workflow_id = ?
        ORDER BY created_at ASC
    """, (workflow_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_workflow_tasks(workflow_id: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM tasks
        WHERE workflow_id = ?
        ORDER BY created_at ASC
    """, (workflow_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pattern_memory() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM pattern_memory
        ORDER BY attempts DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_traces() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM traces
        ORDER BY created_at DESC
        LIMIT 100
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_systemic_alerts() -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM systemic_alerts
        WHERE resolved = 0
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]