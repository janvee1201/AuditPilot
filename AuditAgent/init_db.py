"""
init_db.py

AuditPilot — Database initialisation script.
Run this ONCE before starting the project.

What it does:
  1. Creates auditpilot.db in the project root
  2. Creates all 7 tables
  3. Seeds pattern_memory with 5 pre-seeded error patterns
  4. Seeds clients table with 3 existing clients
  5. Inserts test trace rows simulating W1, W2, W3 agents
     so W4 can be tested before real agents are connected

Usage:
  python init_db.py

Run from the project root folder (same folder as main.py).
Safe to re-run — drops and recreates the DB cleanly each time.
"""

import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "auditpilot.db"


# ─────────────────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────────────────
# CREATE TABLES
# Each table created as a separate execute() call.
# Avoids executescript() parsing issues on Windows.
# ─────────────────────────────────────────────────────────

def create_tables(conn: sqlite3.Connection) -> None:

    statements = [

        # pattern_memory — W4 reads and writes this
        """CREATE TABLE IF NOT EXISTS pattern_memory (
            error_hash          TEXT PRIMARY KEY,
            error_type          TEXT NOT NULL,
            agent               TEXT NOT NULL,
            recommended_action  TEXT NOT NULL,
            attempts            INTEGER NOT NULL DEFAULT 0,
            successes           INTEGER NOT NULL DEFAULT 0,
            success_rate        REAL NOT NULL DEFAULT 0.0,
            last_seen_at        TEXT NOT NULL,
            context             TEXT,
            systemic_flag       INTEGER NOT NULL DEFAULT 0,
            last_systemic_at    TEXT
        )""",

        # traces — every agent step writes here
        """CREATE TABLE IF NOT EXISTS traces (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     TEXT NOT NULL,
            workflow_type   TEXT NOT NULL,
            step_id         TEXT NOT NULL,
            agent           TEXT NOT NULL,
            input_data      TEXT,
            output_data     TEXT,
            status          TEXT NOT NULL,
            error_hash      TEXT,
            error_type      TEXT,
            decision        TEXT,
            decision_reason TEXT,
            duration_ms     INTEGER,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""",

        # clients — W1 writes here after successful onboarding
        """CREATE TABLE IF NOT EXISTS clients (
            client_id       TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            phone           TEXT,
            gstin           TEXT,
            business_type   TEXT,
            onboarded_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            status          TEXT NOT NULL DEFAULT 'active'
        )""",

        # purchase_orders — W2 writes here after payment
        """CREATE TABLE IF NOT EXISTS purchase_orders (
            po_number       TEXT PRIMARY KEY,
            vendor_id       TEXT NOT NULL,
            vendor_name     TEXT NOT NULL,
            amount          REAL NOT NULL,
            invoice_amount  REAL,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""",

        # tasks — W3 writes here after owner resolution
        """CREATE TABLE IF NOT EXISTS tasks (
            task_id         TEXT PRIMARY KEY,
            workflow_id     TEXT NOT NULL,
            owner_id        TEXT,
            owner_name      TEXT,
            title           TEXT NOT NULL,
            deadline        TEXT,
            priority        TEXT DEFAULT 'medium',
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""",

        # systemic_alerts — W4 writes here when count >= 3 workflows
        """CREATE TABLE IF NOT EXISTS systemic_alerts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            error_hash          TEXT NOT NULL,
            error_type          TEXT NOT NULL,
            affected_workflows  TEXT NOT NULL,
            occurrence_count    INTEGER NOT NULL,
            context             TEXT,
            resolved            INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""",

        # briefing_log — morning briefing module writes here
        """CREATE TABLE IF NOT EXISTS briefing_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            briefing_date   TEXT NOT NULL,
            items_count     INTEGER NOT NULL DEFAULT 0,
            email_sent      INTEGER NOT NULL DEFAULT 0,
            content         TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""",
    ]

    for stmt in statements:
        conn.execute(stmt)

    conn.commit()
    print("  7 tables created.")


# ─────────────────────────────────────────────────────────
# SEED PATTERN MEMORY
# 5 pre-seeded rows — makes the system look like it has
# been running for weeks before the demo starts.
# W4 reads these to decide retry vs escalate.
# ─────────────────────────────────────────────────────────

def seed_pattern_memory(conn: sqlite3.Connection) -> None:
    rows = [
        (
            "hash_404_vendor",
            "HTTP_404_vendor_not_found",
            "execution_agent",
            "escalate",
            20, 6, 0.30,
            "2024-03-14 09:23:00",
            "Vendor not found errors are almost always data problems — retry rarely helps",
            0, None,
        ),
        (
            "hash_503_kyc",
            "HTTP_503_kyc_unavailable",
            "execution_agent",
            "retry",
            15, 13, 0.87,
            "2024-03-14 11:45:00",
            "KYC API has intermittent outages — retry almost always succeeds within 2 attempts",
            0, None,
        ),
        (
            "hash_gstin_val",
            "GSTIN_format_invalid",
            "intake_agent",
            "escalate",
            8, 0, 0.00,
            "2024-03-13 14:12:00",
            "GSTIN format errors are always data problems — retry never helps",
            0, None,
        ),
        (
            "hash_403_vendor",
            "HTTP_403_vendor_inactive",
            "execution_agent",
            "escalate",
            12, 0, 0.00,
            "2024-03-14 10:30:00",
            "Inactive vendor status requires manual approval — cannot auto-resolve",
            0, None,
        ),
        (
            "hash_408_timeout",
            "HTTP_408_request_timeout",
            "execution_agent",
            "retry",
            22, 19, 0.86,
            "2024-03-14 08:15:00",
            "Timeout errors are transient — high retry success rate across all workflows",
            0, None,
        ),
    ]

    conn.executemany(
        """INSERT OR IGNORE INTO pattern_memory
           (error_hash, error_type, agent, recommended_action,
            attempts, successes, success_rate, last_seen_at,
            context, systemic_flag, last_systemic_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} pattern_memory rows seeded.")


# ─────────────────────────────────────────────────────────
# SEED EXISTING CLIENTS
# Already in the system before demo starts.
# C-001 email makes C-004 trigger duplicate detection.
# ─────────────────────────────────────────────────────────

def seed_existing_clients(conn: sqlite3.Connection) -> None:
    rows = [
        (
            "C-001", "Mehta Textiles Pvt Ltd",
            "accounts@mehtatex.in", "9876543210",
            "27AAPFM0939F1ZV", "Textiles",
            "2024-01-10 09:00:00", "active",
        ),
        (
            "C-EX1", "Reliance Vendors",
            "vendor@reliance.com", "9123456780",
            "27AAREL1234F1ZV", "Trading",
            "2024-01-05 10:30:00", "active",
        ),
        (
            "C-EX2", "Tata Supplies",
            "supply@tata.in", "9988776655",
            "27AAECT5678K1ZT", "Supply",
            "2023-12-20 14:00:00", "active",
        ),
    ]

    conn.executemany(
        """INSERT OR IGNORE INTO clients
           (client_id, name, email, phone, gstin,
            business_type, onboarded_at, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} existing client records seeded.")


# ─────────────────────────────────────────────────────────
# SEED TEST TRACES
# Simulates what W1, W2, W3 agents would write.
# Lets W4 run and detect patterns before real agents connect.
# workflow_id format exactly matches production agent output.
# ─────────────────────────────────────────────────────────

def seed_test_traces(conn: sqlite3.Connection) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = [

        # ── W1 C-001 Mehta Textiles — clean success ───────────────────
        ("WF-C001", "W1", "T1", "intake_agent",
         json.dumps({"client_id": "C-001", "name": "Mehta Textiles", "gstin": "27AAPFM0939F1ZV"}),
         json.dumps({"validated": True}),
         "success", None, None, None, None, 120, now),

        ("WF-C001", "W1", "T2", "intake_agent",
         json.dumps({"email": "accounts@mehtatex.in"}),
         json.dumps({"is_duplicate": False}),
         "success", None, None, None, None, 85, now),

        ("WF-C001", "W1", "T3", "execution_agent",
         json.dumps({"gstin": "27AAPFM0939F1ZV"}),
         json.dumps({"verified": True}),
         "success", None, None, None, None, 340, now),

        ("WF-C001", "W1", "T4", "execution_agent",
         json.dumps({"client_id": "C-001"}),
         json.dumps({"account_created": True, "email_sent": True}),
         "success", None, None, None, None, 210, now),

        # ── W1 C-003 Sharma Trading — GSTIN invalid ───────────────────
        ("WF-C003", "W1", "T1", "intake_agent",
         json.dumps({"client_id": "C-003", "gstin": "07AAECS1234F1Z", "length": 14}),
         json.dumps({"validated": False, "error": "GSTIN must be 15 characters, got 14"}),
         "failed",
         "hash_gstin_val", "GSTIN_format_invalid",
         "escalate", "Format errors are data problems — retry never helps",
         95, now),

        # ── W1 C-005 Gupta Pharma — KYC 503, retry success ───────────
        ("WF-C005", "W1", "T3", "execution_agent",
         json.dumps({"gstin": "06AABCG1234P1ZK", "attempt": 1}),
         json.dumps({"verified": False, "http_status": 503}),
         "failed",
         "hash_503_kyc", "HTTP_503_kyc_unavailable",
         "retry", "Historical rate 0.87 — above 0.70 threshold, auto-retry",
         1200, now),

        ("WF-C005", "W1", "T3", "execution_agent",
         json.dumps({"gstin": "06AABCG1234P1ZK", "attempt": 2}),
         json.dumps({"verified": True}),
         "retried",
         "hash_503_kyc", "HTTP_503_kyc_unavailable",
         "retry_succeeded", "Retry attempt 2 succeeded",
         980, now),

        # ── W2 PO-2024-001 — clean success ────────────────────────────
        ("WF-PO001", "W2", "T5", "intake_agent",
         json.dumps({"po_number": "PO-2024-001", "vendor_id": "V-1001", "amount": 45000}),
         json.dumps({"validated": True}),
         "success", None, None, None, None, 145, now),

        ("WF-PO001", "W2", "T6", "execution_agent",
         json.dumps({"po_amount": 45000, "invoice_amount": 45000}),
         json.dumps({"match": True}),
         "success", None, None, None, None, 190, now),

        ("WF-PO001", "W2", "T7", "execution_agent",
         json.dumps({"po_number": "PO-2024-001", "amount": 45000}),
         json.dumps({"approved": True}),
         "success", None, None, None, None, 230, now),

        ("WF-PO001", "W2", "T8", "execution_agent",
         json.dumps({"vendor_id": "V-1001", "amount": 45000}),
         json.dumps({"txn_ref": "TXN-1710404400", "vendor_notified": True}),
         "success", None, None, None, None, 560, now),

        # ── W2 PO-2024-002 — invoice mismatch ─────────────────────────
        ("WF-PO002", "W2", "T6", "execution_agent",
         json.dumps({"po_amount": 120000, "invoice_amount": 122200}),
         json.dumps({"match": False, "discrepancy": 2200}),
         "escalated",
         "hash_invoice_mismatch", "INVOICE_AMOUNT_MISMATCH",
         "escalate", "No prior resolution data — escalating with discrepancy detail",
         175, now),

        # ── W2 PO-2024-003 — vendor 404 ───────────────────────────────
        ("WF-PO003", "W2", "T5", "execution_agent",
         json.dumps({"vendor_id": "V-9999", "po_number": "PO-2024-003"}),
         json.dumps({"found": False, "http_status": 404}),
         "failed",
         "hash_404_vendor", "HTTP_404_vendor_not_found",
         "escalate", "Historical rate 0.30 — below threshold, escalating",
         310, now),

        # ── W3 WF-MTG001 — clean success ──────────────────────────────
        ("WF-MTG001", "W3", "T9", "intake_agent",
         json.dumps({"notes": "priya to finalize pricing, vikram to set up pipeline"}),
         json.dumps({"tasks_extracted": 2}),
         "success", None, None, None, None, 1850, now),

        ("WF-MTG001", "W3", "T10", "execution_agent",
         json.dumps({"owner_name": "Priya"}),
         json.dumps({"owner_id": "TM-001", "name": "Priya Sharma"}),
         "success", None, None, None, None, 210, now),

        ("WF-MTG001", "W3", "T11", "execution_agent",
         json.dumps({"task": "Finalize pricing", "owner_id": "TM-001"}),
         json.dumps({"task_id": "TASK-001", "status": "pending"}),
         "success", None, None, None, None, 130, now),

        # ── W3 WF-MTG002 — ambiguous owner (two Rahuls) ───────────────
        ("WF-MTG002", "W3", "T10", "execution_agent",
         json.dumps({"owner_name": "Rahul"}),
         json.dumps({
             "matches": [
                 {"id": "TM-002", "name": "Rahul Sharma", "dept": "Backend"},
                 {"id": "TM-003", "name": "Rahul Verma",  "dept": "Frontend"},
             ],
             "http_status": 300,
         }),
         "escalated",
         "hash_300_ambiguous", "HTTP_300_ambiguous_owner",
         "escalate", "Two team members match — manual selection required",
         280, now),
    ]

    conn.executemany(
        """INSERT INTO traces
           (workflow_id, workflow_type, step_id, agent,
            input_data, output_data, status,
            error_hash, error_type, decision, decision_reason,
            duration_ms, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    print(f"  {len(rows)} test trace rows inserted.")


# ─────────────────────────────────────────────────────────
# VERIFY
# ─────────────────────────────────────────────────────────

def verify(conn: sqlite3.Connection) -> None:
    tables = [
        "pattern_memory",
        "traces",
        "clients",
        "purchase_orders",
        "tasks",
        "systemic_alerts",
        "briefing_log",
    ]
    print("\n  Table row counts:")
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"    {t:<22} → {count} rows")


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main() -> None:
    print(f"\nAuditPilot — Database Init")
    print(f"Target : {DB_PATH}")
    print()

    if DB_PATH.exists():
        print("  Existing DB found — dropping and recreating cleanly.")
        DB_PATH.unlink()

    conn = get_connection()

    print("Creating tables...")
    create_tables(conn)

    print("Seeding pattern_memory...")
    seed_pattern_memory(conn)

    print("Seeding existing clients...")
    seed_existing_clients(conn)

    print("Inserting test traces...")
    seed_test_traces(conn)

    verify(conn)
    conn.close()

    print(f"\nDone. Run python main.py to start the demo.\n")


if __name__ == "__main__":
    main()