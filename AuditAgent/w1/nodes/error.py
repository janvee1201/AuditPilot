"""
w1/nodes/error.py

W1 error node — the W4 integration point.

Every failure in W1 routes here.
This node calls run_w4() and uses the returned
decision to determine next action.

Old behaviour — hardcoded PATTERN_MEMORY dict → REMOVED
New behaviour — calls W4, reads decision from SQLite
"""

import time
from shared.logger import log
from shared.db import write_trace
from shared.error_map import get_error_hash, is_retryable
from w4.agent import run_w4
from w1.utils.hitl import ask_choice


def error_node(state: dict) -> dict:
    start       = time.time()
    error_str   = state.get("error", "")
    wid         = state.get("workflow_id", "WF-UNKNOWN")
    client_id   = state["input"].get("client_id", "unknown")

    state["logs"].append(log("Monitor Agent", f"Error detected: {error_str}"))

    # ── translate agent error string to W4 hash ──────────
    error_hash, error_type = get_error_hash(error_str)

    # ── write the failure trace row for this workflow ─────
    # (the node that failed wrote its own trace already,
    #  this row records that W4 is being called)
    write_trace(
        workflow_id = wid, workflow_type = "W1",
        step_id = "error_node", agent = "monitor_agent",
        status = "escalated",
        input_data  = {"error": error_str, "retry_count": state.get("retry_count", 0)},
        output_data = {"calling_w4": True, "error_hash": error_hash},
        error_hash  = error_hash,
        error_type  = error_type,
        duration_ms = int((time.time() - start) * 1000),
    )

    # ── fast path: never-retry errors ────────────────────
    # GSTIN format errors and duplicates are always data
    # problems — skip W4 decision, escalate immediately
    if not is_retryable(error_hash):
        state["logs"].append(
            log("Monitor Agent", f"Non-retryable error — escalating immediately [FAIL]")
        )

        # HITL for duplicate — ask merge / create new / cancel
        if error_hash == "hash_duplicate":
            state["logs"].append(
                log("Escalation Agent", "Asking human: Merge / Create new / Cancel?")
            )
            if state.get("hitl_enabled", False):
                action = ask_choice(
                    "Duplicate detected. Choose action",
                    ["merge", "create_new", "cancel"],
                    "cancel",
                )
                if action == "merge":
                    state["logs"].append(
                        log("Escalation Agent", "Human selected MERGE with existing client [OK]")
                    )
                elif action == "create_new":
                    state["logs"].append(
                        log("Escalation Agent", "Human selected CREATE NEW — blocked by policy [FAIL]")
                    )
                else:
                    state["logs"].append(
                        log("Escalation Agent", "Human selected CANCEL onboarding [OK]")
                    )

        state["w4_decision"] = "escalate"
        return state

    # ── call W4 for retryable errors ─────────────────────
    state["logs"].append(
        log("Monitor Agent", f"Calling W4 pattern memory for {error_hash}...")
    )

    w4_result = run_w4(
        workflow_id    = wid,
        workflow_type  = "W1",
        error_hash     = error_hash,
        error_type     = error_type,
        retry_succeeded= False,   # not yet — retry happens in kyc_node
    )

    decision   = w4_result["decision"]["decision"]
    rate       = w4_result["decision"].get("success_rate")
    is_systemic= w4_result["pattern"]["is_systemic"]

    state["w4_decision"] = decision

    state["logs"].append(log(
        "Explainability Agent",
        f"W4 decision: {decision.upper()} "
        f"(rate={rate}, systemic={is_systemic})"
    ))

    # ── systemic alert message ────────────────────────────
    if is_systemic:
        state["logs"].append(log(
            "Escalation Agent",
            f"SYSTEMIC PATTERN — same error across "
            f"{w4_result['pattern']['count']} workflows [ALERT]"
        ))

    # ── act on W4 decision ────────────────────────────────
    if decision == "retry" and state.get("retry_count", 0) < 1:
        # KYC_503 — W4 says retry, we have not retried yet
        if state.get("error") == "KYC_503" and state.get("hitl_enabled", False):
            state["logs"].append(
                log("Escalation Agent", "Human approval required: Retry / Manual docs / Override KYC")
            )
            action = ask_choice(
                "KYC failed. Choose action",
                ["retry", "manual_docs", "override"],
                "retry",
            )
            if action == "manual_docs":
                state["error"] = "KYC manual document verification required"
                state["logs"].append(
                    log("Escalation Agent", "Human selected manual document flow [FAIL]")
                )
                state["w4_decision"] = "escalate"
                return state

            if action == "override":
                state["skip_kyc"]   = True
                state["kyc_status"] = True
                state["error"]      = None
                state["logs"].append(
                    log("Escalation Agent", "Human approved KYC override [OK]")
                )
                state["w4_decision"] = "override"
                return state

        # auto retry — increment count, clear error
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["error"]       = None
        state["logs"].append(
            log("Escalation Agent",
                f"Retrying based on W4 decision (rate={rate}) [RETRY]")
        )

    elif decision == "retry" and state.get("retry_count", 0) >= 1:
        # already retried once — now escalate regardless of W4
        state["logs"].append(
            log("Monitor Agent", "Max retries reached — escalating [FAIL]")
        )
        state["w4_decision"] = "escalate"

    else:
        # W4 said escalate
        state["logs"].append(
            log("Escalation Agent",
                f"Escalating — W4 reason: {w4_result['decision']['reason']} [FAIL]")
        )

    return state