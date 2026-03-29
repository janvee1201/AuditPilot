"""
w2/nodes/orchestrator.py  —  W4 integration point for W2

Replaces all hardcoded retry/escalate logic with W4 calls.
Old behaviour: if error == X → do Y  (hardcoded)
New behaviour: call run_w4() → read decision → act on it
"""

import time
from shared.logger import log
from shared.db import write_trace
from shared.error_map import get_error_hash, is_retryable
from w4.agent import run_w4


# ── error descriptions shown to human in terminal ────────
ERROR_DESCRIPTIONS = {
    "VENDOR_403"        : "Vendor is inactive and not approved for payment.",
    "VENDOR_404"        : "Vendor ID not found in the system.",
    "THREE_WAY_MISMATCH": "Invoice amount does not match PO amount.",
    "API_TIMEOUT"       : "Payment API timed out.",
}


def _hitl_escalation(state: dict, error: str, error_hash: str) -> None:
    """
    Shows a human approval prompt in terminal when a payment is escalated.
    Human can approve manually, reject, or skip.
    Updates state in place based on human decision.
    """
    po_no       = state["input"].get("po_no", "unknown PO")
    vendor_id   = state["input"].get("vendor_id", "")
    po_amount   = state["input"].get("po_amount", 0)
    description = ERROR_DESCRIPTIONS.get(error, f"Error: {error}")

    print(f"\n  {'─'*50}")
    print(f"  [HITL] Payment escalated — human action required")
    print(f"  {'─'*50}")
    print(f"  PO Number  : {po_no}")
    print(f"  Vendor     : {vendor_id}")
    print(f"  Amount     : ₹{po_amount:,}")
    print(f"  Reason     : {description}")
    print(f"  {'─'*50}")
    print(f"  1. Approve payment manually (override)")
    print(f"  2. Reject and cancel this PO")
    print(f"  3. Skip — mark as pending review")
    print()

    try:
        choice = input("  Your choice (1 / 2 / 3): ").strip()
    except EOFError:
        choice = "2"

    if choice == "1":
        state["status"]      = "completed"
        state["w4_decision"] = "escalate"
        state["error"]       = None
        state["logs"].append(
            log("Escalation Agent",
                f"Human approved payment manually for {po_no} [OK]")
        )
        print(f"\n  Payment approved manually. PO {po_no} will be marked completed.\n")

    elif choice == "3":
        state["status"]      = "pending_review"
        state["w4_decision"] = "escalate"
        state["error"]       = None
        state["logs"].append(
            log("Escalation Agent",
                f"PO {po_no} marked as pending review — human will revisit [WARN]")
        )
        print(f"\n  PO {po_no} marked as pending review.\n")

    else:
        state["status"]      = "failed"
        state["w4_decision"] = "escalate"
        state["error"]       = None
        state["logs"].append(
            log("Escalation Agent",
                f"Human rejected payment — PO {po_no} cancelled [FAIL]")
        )
        print(f"\n  PO {po_no} rejected and cancelled.\n")


def orchestrator_node(state: dict) -> dict:
    start = time.time()
    wid   = state.get("workflow_id", "WF-UNKNOWN")
    error = state.get("error")

    # no error — payment succeeded cleanly
    if not error:
        state["logs"].append(log("Orchestrator", "No error — workflow completed [OK]"))
        return state

    state["logs"].append(log("Orchestrator", f"Error received: {error}"))

    # ── translate to W4 hash ─────────────────────────────
    error_hash, error_type = get_error_hash(error)

    # ── write orchestrator trace row ─────────────────────
    write_trace(
        workflow_id = wid, workflow_type = "W2",
        step_id = "orchestrator", agent = "orchestrator_agent",
        status = "escalated",
        input_data  = {"error": error, "retry_count": state.get("retry_count", 0)},
        output_data = {"calling_w4": True, "error_hash": error_hash},
        error_hash  = error_hash,
        error_type  = error_type,
        duration_ms = int((time.time() - start) * 1000),
    )

    # ── fast path: never-retry errors ────────────────────
    if not is_retryable(error_hash):
        state["logs"].append(
            log("Orchestrator", f"Non-retryable — escalating immediately [FAIL]")
        )

        if state.get("hitl_enabled", False):
            _hitl_escalation(state, error, error_hash)
        else:
            state["status"]      = "failed"
            state["w4_decision"] = "escalate"
            state["error"]       = None
        return state

    # ── call W4 ──────────────────────────────────────────
    state["logs"].append(
        log("Orchestrator", f"Calling W4 for decision on {error_hash}...")
    )

    w4_result  = run_w4(
        workflow_id    = wid,
        workflow_type  = "W2",
        error_hash     = error_hash,
        error_type     = error_type,
        retry_succeeded= False,
    )

    decision    = w4_result["decision"]["decision"]
    rate        = w4_result["decision"].get("success_rate")
    is_systemic = w4_result["pattern"]["is_systemic"]

    state["w4_decision"] = decision

    state["logs"].append(log(
        "Explainability Agent",
        f"W4 decision: {decision.upper()} "
        f"(rate={rate}, systemic={is_systemic})"
    ))

    if is_systemic:
        state["logs"].append(log(
            "Escalation Agent",
            f"SYSTEMIC PATTERN — same error across "
            f"{w4_result['pattern']['count']} workflows [ALERT]"
        ))

    # ── act on decision ───────────────────────────────────
    if decision == "retry" and state.get("retry_count", 0) < 1:
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["error"]       = None
        state["logs"].append(
            log("Orchestrator",
                f"Retrying based on W4 decision (rate={rate}) [RETRY]")
        )

    elif decision == "retry" and state.get("retry_count", 0) >= 1:
        state["logs"].append(
            log("Orchestrator", "Max retries reached — escalating [FAIL]")
        )
        state["status"]      = "failed"
        state["w4_decision"] = "escalate"
        state["error"]       = None

    else:
        state["logs"].append(
            log("Orchestrator",
                f"Escalating — W4 reason: {w4_result['decision']['reason']} [FAIL]")
        )
        if state.get("hitl_enabled", False):
            _hitl_escalation(state, error, error_hash)
        else:
            state["status"] = "failed"
            state["error"]  = None

    return state