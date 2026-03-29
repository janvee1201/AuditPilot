"""
main.py

AuditPilot — Master entry point.

Two modes:
  1. Interactive mode (default) — type task in plain English
  2. Demo mode (--demo flag)    — runs all hardcoded test cases

Usage:
  python main.py          → interactive mode
  python main.py --demo   → demo mode
"""

import re
import sys
import json
import uuid
import shutil
import types
from pathlib import Path

# ── mock httpx so w3 imports work without the package ────
httpx_mod = types.ModuleType("httpx")
class FakeTimeout(Exception): pass
httpx_mod.TimeoutException = FakeTimeout
sys.modules.setdefault("httpx", httpx_mod)

from shared.logger import log, log_section, log_step
from shared.error_map import get_error_hash

BASE = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────
# WORKFLOW RUNNERS
# ─────────────────────────────────────────────────────────

def run_w1(client: dict) -> dict:
    from w1.nodes.validation import validate_node
    from w1.nodes.duplicate  import duplicate_node
    from w1.nodes.kyc        import kyc_node
    from w1.nodes.execution  import create_account_node
    from w1.nodes.error      import error_node
    from w4.agent            import run_w4

    cid = client.get("client_id", f"C-{str(uuid.uuid4())[:4].upper()}")
    if "client_id" not in client:
        client["client_id"] = cid

    wid = f"WF-{cid}"
    state = {
        "workflow_id"  : wid,
        "input"        : client,
        "logs"         : [],
        "error"        : None,
        "retry_count"  : 0,
        "kyc_status"   : False,
        "hitl_enabled" : False,
        "skip_kyc"     : False,
        "w4_decision"  : None,
    }

    state = validate_node(state)
    if state["error"]:
        state = error_node(state)
        return state

    state = duplicate_node(state)
    if state["error"]:
        state = error_node(state)
        return state

    state = kyc_node(state)
    if state["error"]:
        state = error_node(state)
        if state.get("retry_count", 0) >= 1 and not state.get("error"):
            state = kyc_node(state)
            if not state["error"]:
                eh, et = get_error_hash("KYC_503")
                run_w4(wid, "W1", eh, et, retry_succeeded=True)

    if state["error"]:
        return state

    state = create_account_node(state)
    return state


def run_w2(po: dict) -> dict:
    from w2.nodes.intake       import intake_node
    from w2.nodes.validation   import validation_node
    from w2.nodes.vendor_check import vendor_check_node
    from w2.nodes.approval     import approval_node
    from w2.nodes.payment      import payment_node
    from w2.nodes.monitor      import monitor_node
    from w2.nodes.orchestrator import orchestrator_node
    from w2.nodes.audit        import audit_node
    from w4.agent              import run_w4

    wid = f"WF-{po.get('po_no', str(uuid.uuid4())[:6])}"
    state = {
        "workflow_id"  : wid,
        "input"        : po,
        "logs"         : [],
        "error"        : None,
        "approved"     : False,
        "retry_count"  : 0,
        "status"       : "running",
        "w4_decision"  : None,
        "hitl_enabled" : True,
    }

    state = intake_node(state)

    state = validation_node(state)
    if state.get("error"):
        state = orchestrator_node(state)
        state = audit_node(state)
        return state

    state = vendor_check_node(state)
    if state.get("error"):
        state = orchestrator_node(state)
        state = audit_node(state)
        return state

    state = approval_node(state)
    state = payment_node(state)
    state = monitor_node(state)
    state = orchestrator_node(state)

    if state.get("retry_count", 0) == 1 and state.get("status") == "running":
        state = payment_node(state)
        state = monitor_node(state)
        if not state.get("error"):
            eh, et = get_error_hash("API_TIMEOUT")
            run_w4(wid, "W2", eh, et, retry_succeeded=True)
        state = orchestrator_node(state)

    state = audit_node(state)
    return state


def run_w3(notes: str) -> dict:
    from w3.nodes.intake           import intake_node
    from w3.nodes.extraction       import extraction_node
    from w3.nodes.owner_resolution import owner_resolution_node
    from w3.nodes.task_writer      import task_writer_node
    from w3.nodes.error            import error_node

    wid = f"WF-MTG-{str(uuid.uuid4())[:6].upper()}"
    state = {
        "workflow_id"    : wid,
        "notes"          : notes,
        "logs"           : [],
        "error"          : None,
        "status"         : "running",
        "tasks"          : [],
        "assigned_tasks" : [],
        "escalated_tasks": [],
        "human_required" : [],
        "tasks_written"  : 0,
        "w4_decision"    : None,
    }

    state = intake_node(state)
    if state.get("error"):
        state = error_node(state)
        return state

    state = extraction_node(state)
    if state.get("error"):
        state = error_node(state)
        return state

    state = owner_resolution_node(state)
    state = task_writer_node(state)
    return state


# ─────────────────────────────────────────────────────────
# INPUT HELPERS
# ─────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    else:
        val = input(f"  {prompt}: ").strip()
        return val


def _collect_w1_input(name_hint: str = "") -> dict:
    print("\n  I need a few details to onboard the client.\n")
    name  = ask("Client name", name_hint)
    email = ask("Email address")
    gstin = ask("GSTIN (15 characters)")
    phone = ask("Phone number", "9999999999")
    cid   = ask("Client ID", f"C-{str(uuid.uuid4())[:4].upper()}")
    return {
        "client_id"    : cid,
        "name"         : name,
        "email"        : email,
        "gstin"        : gstin,
        "phone"        : phone,
        "business_type": "",
    }


def _collect_w2_input(name_hint: str = "", amount_hint: str = "") -> dict:
    print("\n  I need a few details for the payment.\n")
    po_no   = ask("PO number", f"PO-{str(uuid.uuid4())[:6].upper()}")
    vendor  = ask("Vendor ID (e.g. V-1001)", name_hint)
    amount  = ask("PO amount (₹)", amount_hint)
    invoice = ask("Invoice amount (₹)", amount)
    return {
        "po_no"         : po_no,
        "vendor_id"     : vendor,
        "po_amount"     : float(amount)  if amount  else 0.0,
        "invoice_amount": float(invoice) if invoice else 0.0,
    }


def _collect_w3_input() -> str:
    print("\n  Paste your meeting notes below.")
    print("  Type END on a new line when done.\n")
    lines = []
    while True:
        line = input("  > ")
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# TASK CLASSIFIER
# ─────────────────────────────────────────────────────────

def _classify_task(user_task: str) -> dict:
    task_lower = user_task.lower()

    w1_keywords = [
        "onboard", "register", "add client", "new client",
        "sign up", "enroll", "create account", "kyc",
    ]
    w2_keywords = [
        "pay", "payment", "purchase order", "po", "invoice",
        "vendor", "procurement", "approve", "transaction",
        "pay to", "process payment", "settle",
    ]
    w3_keywords = [
        "meeting", "notes", "assign task", "action item",
        "task", "minute", "discussed", "follow up",
        "sprint", "standup", "sync",
    ]

    w1_score = sum(1 for k in w1_keywords if k in task_lower)
    w2_score = sum(1 for k in w2_keywords if k in task_lower)
    w3_score = sum(1 for k in w3_keywords if k in task_lower)
    total    = w1_score + w2_score + w3_score

    if total == 0:
        return {
            "route"     : "unclear",
            "confidence": 0.0,
            "extracted" : {},
            "is_multi"  : False,
            "routes"    : [],
            "reason"    : "No matching keywords found",
        }

    scores   = {"W1": w1_score, "W2": w2_score, "W3": w3_score}
    active   = sorted([k for k, v in scores.items() if v > 0])
    is_multi = len(active) >= 2
    best     = max(scores, key=scores.get)
    conf     = round(scores[best] / max(total, 1), 2)

    # extract name hint — words after trigger keywords
    extracted = {}
    words = user_task.split()
    for i, w in enumerate(words):
        if w.lower() in ("onboard", "register", "pay", "to") and i + 1 < len(words):
            extracted["name_hint"] = " ".join(words[i+1:i+3])

    # extract amount hint — any number in the sentence
    amounts = re.findall(r'\b\d[\d,]*\b', user_task)
    if amounts:
        extracted["amount_hint"] = amounts[-1].replace(",", "")

    reason = (
        f"Multi-task detected — will run {' then '.join(active)}"
        if is_multi else
        f"Matched {scores[best]} {best} keyword(s) in your task"
    )

    return {
        "route"     : best,
        "confidence": conf,
        "extracted" : extracted,
        "is_multi"  : is_multi,
        "routes"    : active,
        "reason"    : reason,
    }


# ─────────────────────────────────────────────────────────
# INTERACTIVE MODE
# ─────────────────────────────────────────────────────────

def run_interactive():
    print(log_section("AuditPilot — Natural Language Mode"))
    print("  Type your task in plain English.")
    print("  Examples:")
    print("    'I want to onboard Arjun Fintech Pvt Ltd'")
    print("    'Process payment to Mehta Enterprises'")
    print("    'Onboard Agarwal Steels and make a payment of 10000'")
    print("    'Assign tasks from today sprint meeting'")
    print("  Type 'exit' to quit.\n")

    while True:

        user_task = input("  You: ").strip()

        if not user_task:
            continue

        if user_task.lower() in ("exit", "quit", "q"):
            print("\n  Session ended.\n")
            _print_db_summary()
            break

        print()
        classification = _classify_task(user_task)
        route       = classification["route"]
        confidence  = classification["confidence"]
        reason      = classification["reason"]
        extracted   = classification["extracted"]
        routes      = classification.get("routes", [route])
        is_multi    = classification.get("is_multi", False)
        name_hint   = extracted.get("name_hint", "")
        amount_hint = extracted.get("amount_hint", "")

        if route == "unclear":
            print("  [Orchestrator] Could not understand the task.")
            print("  Please mention 'onboard', 'payment', or 'meeting tasks'.\n")
            continue

        route_labels = {
            "W1": "Client Onboarding",
            "W2": "Procurement to Payment",
            "W3": "Meeting to Task",
        }

        if is_multi:
            print(f"  [Orchestrator] Multi-task detected — {reason}")
            print(f"  [Orchestrator] Running: {' → '.join(routes)}\n")
        else:
            print(f"  [Orchestrator] Routing to {route} — {route_labels[route]}")
            print(f"  [Orchestrator] Reason: {reason}")
            print(f"  [Orchestrator] Confidence: {confidence}\n")

        should_stop = False

        for current_route in routes:

            if current_route == "W1":
                client = _collect_w1_input(name_hint)
                print(f"\n  Starting W1 for {client['name']}...\n")
                result = run_w1(client)
                print()
                if result.get("error"):
                    print(f"  W1 Status : ESCALATED")
                    print(f"  Reason    : {result['error']}")
                    if is_multi:
                        cont = input("\n  W1 failed. Continue to next task? (y/n): ").strip().lower()
                        if cont != "y":
                            print("  Stopping sequence.")
                            should_stop = True
                else:
                    print(f"  W1 Status : SUCCESS")
                    print(f"  Client ID : {client['client_id']}")
                    print(f"  KYC       : {result.get('kyc_status', False)}")

            elif current_route == "W2":
                po = _collect_w2_input(name_hint, amount_hint)
                print(f"\n  Starting W2 for {po['po_no']}...\n")
                result = run_w2(po)
                print()
                final = "SUCCESS" if result["status"] == "completed" else result["status"].upper()
                print(f"  W2 Status : {final}")
                print(f"  Retries   : {result.get('retry_count', 0)}")
                print(f"  W4        : {result.get('w4_decision', 'none')}")

            elif current_route == "W3":
                notes = _collect_w3_input()
                if notes.strip():
                    print(f"\n  Starting W3...\n")
                    result = run_w3(notes)
                    print()
                    total    = len(result.get("tasks", []))
                    assigned = len(result.get("assigned_tasks", []))
                    escalated= len(result.get("escalated_tasks", []))
                    print(f"  W3 Status : {result.get('status', 'completed').upper()}")
                    print(f"  Tasks     : {total} found, {assigned} assigned, {escalated} escalated")
                    print(f"  Written   : {result.get('tasks_written', 0)}")

            if should_stop:
                break

            if is_multi and current_route != routes[-1]:
                print(f"\n  {'─'*50}")
                print(f"  Moving to next task...\n")

        print()
        again = input("  Run another task? (y/n): ").strip().lower()
        if again != "y":
            print("\n  Session ended.\n")
            _print_db_summary()
            break
        print()


# ─────────────────────────────────────────────────────────
# DEMO MODE
# ─────────────────────────────────────────────────────────

def run_demo():
    print(log_section("AuditPilot — Demo Mode"))

    # ── W1 ────────────────────────────────────────────────
    print(log_section("W1 — Client Onboarding"))

    seed   = BASE / "data" / "existing_clients.json"
    backup = BASE / "data" / "existing_clients.backup.json"
    shutil.copyfile(seed, backup)

    with open(BASE / "data" / "clients.json", "r", encoding="utf-8") as f:
        clients_raw = json.load(f)

    clients_data = []
    for c in clients_raw:
        client = dict(c)
        if "id" in client and "client_id" not in client:
            client["client_id"] = client["id"]
        clients_data.append(client)

    sequence      = ["C-001", "C-003", "C-005", "C-002", "C-004"]
    clients_by_id = {c["client_id"]: c for c in clients_data}

    for cid in sequence:
        client = clients_by_id.get(cid)
        if not client:
            continue

        print(f"\n{'─'*54}")
        print(f"  [{cid}] {client['name']}")
        print(f"{'─'*54}")

        result = run_w1(dict(client))
        if result.get("error"):
            print(f"\n  → ESCALATED: {result['error']}")
        else:
            print(f"\n  → SUCCESS — client onboarded")

    shutil.copyfile(backup, seed)
    backup.unlink()

    # ── W2 ────────────────────────────────────────────────
    print(log_section("W2 — Procurement to Payment"))

    with open(BASE / "data" / "purchase_orders.json", "r", encoding="utf-8") as f:
        pos = json.load(f)

    for po in pos:
        print(f"\n{'─'*54}")
        print(f"  [{po['po_no']}] vendor={po['vendor_id']} PO=₹{po['po_amount']:,}")
        print(f"{'─'*54}")

        result = run_w2(po)
        final  = "SUCCESS" if result["status"] == "completed" else result["status"].upper()
        print(f"\n  → {final} | retries={result['retry_count']} | W4={result['w4_decision']}")

    # ── W3 ────────────────────────────────────────────────
    print(log_section("W3 — Meeting to Task"))

    from w3.nodes import extraction as ext_mod

    def mock_llm(notes):
        tasks, words = [], notes.lower()
        mapping = {
            "priya" : ("Priya",  "Update marketing deck",       "this Friday",    "high"),
            "neha"  : ("Neha",   "Review finance report",       "end of month",   "medium"),
            "sneha" : ("Sneha",  "Finalize QA test plan",       "Wednesday",      "high"),
            "vikram": ("Vikram", "Set up deployment pipeline",  "before release", "high"),
            "rahul" : ("Rahul",  "Fix login bug and submit PR", "Wednesday",      "high"),
            "arjun" : ("Arjun",  "Update product roadmap",      "Friday",         "medium"),
        }
        for k, (o, t, d, p) in mapping.items():
            if k in words:
                tasks.append({"task": t, "owner_name": o,
                              "deadline": d, "priority": p, "source_quote": t})
        return {"status": "success", "content": json.dumps(tasks), "duration": 100}

    ext_mod._call_llm = mock_llm

    sample_notes = [
        (
            "WF-MTG-DEMO-1",
            "Team sync. Priya to update marketing deck for client by Friday. "
            "Neha will review the finance report and submit by month end. "
            "Vikram needs to set up the deployment pipeline before the next release. "
            "Sneha should finalize the QA test plan by Wednesday.",
        ),
        (
            "WF-MTG-DEMO-2",
            "Sprint planning. Rahul to fix the login bug and submit PR before Wednesday. "
            "Priya should prepare the demo deck for Thursday client visit. "
            "Arjun will update the product roadmap and share with stakeholders by Friday.",
        ),
    ]

    for wid, notes in sample_notes:
        print(f"\n{'─'*54}")
        print(f"  [{wid}]")
        print(f"{'─'*54}")

        result = run_w3(notes)
        total    = len(result.get("tasks", []))
        assigned = len(result.get("assigned_tasks", []))
        escalated= len(result.get("escalated_tasks", []))
        print(f"\n  → tasks={total} assigned={assigned} "
              f"escalated={escalated} written={result['tasks_written']}")

    print(log_section("Demo Complete"))
    _print_db_summary()


# ─────────────────────────────────────────────────────────
# DB SUMMARY
# ─────────────────────────────────────────────────────────

def _print_db_summary():
    from shared.db import get_connection
    conn = get_connection()

    traces = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    tasks  = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    alerts = conn.execute("SELECT COUNT(*) FROM systemic_alerts").fetchone()[0]
    pm     = conn.execute(
        "SELECT error_hash, attempts, success_rate, recommended_action "
        "FROM pattern_memory ORDER BY attempts DESC"
    ).fetchall()
    conn.close()

    print(f"\n  DB Summary:")
    print(f"    traces          : {traces} rows")
    print(f"    tasks           : {tasks} rows")
    print(f"    systemic_alerts : {alerts} rows")
    print(f"\n  Pattern memory:")
    for r in pm:
        print(f"    {r['error_hash']:<26} "
              f"attempts={r['attempts']:>3}  "
              f"rate={r['success_rate']:.2f}  "
              f"action={r['recommended_action']}")


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_interactive()