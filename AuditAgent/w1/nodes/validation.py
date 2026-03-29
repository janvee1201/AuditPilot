"""
w1/nodes/validation.py  —  T1

Validates incoming client data.
Checks name, email format, and GSTIN length.
Writes one trace row to SQLite on completion.
"""

import time
from shared.logger import log
from shared.db import write_trace
from w1.utils.hitl import ask_choice, ask_text


def validate_node(state: dict) -> dict:
    start = time.time()
    state["logs"].append(log("Validation Agent", "Running schema validation..."))

    data  = state.get("input", {})
    email = data.get("email", "")
    name  = data.get("name")
    gstin = data.get("gstin", "")
    wid   = state.get("workflow_id", "WF-UNKNOWN")

    # ── name check ──────────────────────────────────────
    if not isinstance(name, str) or not name.strip():
        state["error"] = "Missing Name"
        state["logs"].append(log("Validation Agent", "Missing name field [FAIL]"))
        write_trace(
            workflow_id = wid, workflow_type = "W1",
            step_id = "T1", agent = "validation_agent",
            status = "failed",
            input_data  = {"name": name, "email": email, "gstin": gstin},
            output_data = {"error": "Missing name"},
            error_hash  = "hash_gstin_val", error_type = "GSTIN_format_invalid",
            decision = "escalate", decision_reason = "Name missing — data problem",
            duration_ms = int((time.time() - start) * 1000),
        )
        return state

    # ── email check ─────────────────────────────────────
    if not isinstance(email, str) or not email.strip() or "@" not in email:
        state["error"] = "Missing Email"
        state["logs"].append(log("Validation Agent", "Missing or invalid email [FAIL]"))
        write_trace(
            workflow_id = wid, workflow_type = "W1",
            step_id = "T1", agent = "validation_agent",
            status = "failed",
            input_data  = {"email": email},
            output_data = {"error": "Invalid email"},
            duration_ms = int((time.time() - start) * 1000),
        )
        return state

    # ── GSTIN check ─────────────────────────────────────
    if not isinstance(gstin, str) or len(gstin.strip()) != 15:
        state["error"] = 'ValidationError: "GSTIN must be 15 characters"'
        state["logs"].append(
            log("Validation Agent", 'ValidationError: "GSTIN must be 15 characters" [FAIL]')
        )

        if state.get("hitl_enabled", False):
            state["logs"].append(
                log("Escalation Agent", "Human action required: Correct GSTIN or cancel")
            )
            choice = ask_choice(
                "Validation failed. Choose action",
                ["correct", "cancel"],
                "cancel",
            )
            if choice == "correct":
                new_gstin = ask_text("Enter corrected GSTIN (15 chars)", gstin).strip()
                if len(new_gstin) == 15:
                    state["input"]["gstin"] = new_gstin
                    state["error"] = None
                    state["logs"].append(
                        log("Validation Agent", "GSTIN corrected by human review [OK]")
                    )
                    write_trace(
                        workflow_id = wid, workflow_type = "W1",
                        step_id = "T1", agent = "validation_agent",
                        status = "success",
                        input_data  = {"gstin_original": gstin, "gstin_corrected": new_gstin},
                        output_data = {"validated": True},
                        duration_ms = int((time.time() - start) * 1000),
                    )
                    return state
                else:
                    state["logs"].append(
                        log("Validation Agent", "Corrected GSTIN still invalid [FAIL]")
                    )

        write_trace(
            workflow_id = wid, workflow_type = "W1",
            step_id = "T1", agent = "validation_agent",
            status = "failed",
            input_data  = {"gstin": gstin, "length": len(gstin)},
            output_data = {"error": "GSTIN must be 15 characters"},
            error_hash  = "hash_gstin_val",
            error_type  = "GSTIN_format_invalid",
            decision    = "escalate",
            decision_reason = "Format errors are data problems — retry never helps",
            duration_ms = int((time.time() - start) * 1000),
        )
        return state

    # ── all passed ──────────────────────────────────────
    state["logs"].append(log("Validation Agent", "All fields validated successfully [OK]"))
    write_trace(
        workflow_id = wid, workflow_type = "W1",
        step_id = "T1", agent = "validation_agent",
        status = "success",
        input_data  = {"name": name, "email": email, "gstin": gstin},
        output_data = {"validated": True},
        duration_ms = int((time.time() - start) * 1000),
    )
    return state