"""
orchestrator/nodes/state_builder.py

Builds the initial state dict for each workflow
from the params extracted by the LLM classifier.

For W1 — builds W1State-compatible dict
For W2 — builds W2State-compatible dict
For W3 — builds W3State-compatible dict

For multi-task — builds a list of state dicts,
one per task, stored in state["built_states"].
"""

import uuid
import time
from shared.logger import log


def _build_w1_state(params: dict, workflow_id: str) -> dict:
    """
    Builds initial W1 state from extracted params.
    Merges any params the LLM extracted into the input dict.
    The user or test data fills in missing fields.
    """
    return {
        "workflow_id"  : workflow_id,
        "input"        : {
            "client_id"    : params.get("client_id", f"C-{str(uuid.uuid4())[:4].upper()}"),
            "name"         : params.get("client_name", params.get("name", "")),
            "email"        : params.get("email", ""),
            "phone"        : params.get("phone", ""),
            "gstin"        : params.get("gstin", ""),
            "business_type": params.get("business_type", ""),
        },
        "logs"         : [],
        "error"        : None,
        "retry_count"  : 0,
        "kyc_status"   : False,
        "hitl_enabled" : True,
        "skip_kyc"     : False,
        "w4_decision"  : None,
    }


def _build_w2_state(params: dict, workflow_id: str) -> dict:
    """
    Builds initial W2 state from extracted params.
    """
    return {
        "workflow_id"  : workflow_id,
        "input"        : {
            "po_no"         : params.get("po_number", params.get("po_no", "")),
            "vendor_id"     : params.get("vendor_id", ""),
            "vendor_name"   : params.get("vendor_name", ""),
            "po_amount"     : float(params.get("amount", 0)),
            "invoice_amount": float(params.get("invoice_amount", params.get("amount", 0))),
        },
        "logs"         : [],
        "error"        : None,
        "approved"     : False,
        "retry_count"  : 0,
        "status"       : "running",
        "w4_decision"  : None,
    }


def _build_w3_state(params: dict, workflow_id: str) -> dict:
    """
    Builds initial W3 state from extracted params.
    The 'notes' field is the raw meeting text.
    """
    return {
        "workflow_id"    : workflow_id,
        "notes"          : params.get("notes", params.get("meeting_notes", "")),
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


BUILDERS = {
    "W1": _build_w1_state,
    "W2": _build_w2_state,
    "W3": _build_w3_state,
}


def state_builder_node(state: dict) -> dict:
    start     = time.time()
    task_list = state.get("task_list", [])

    if not task_list:
        # single task — use top-level route and params
        task_list = [{
            "route"           : state.get("route", "unclear"),
            "extracted_params": state.get("extracted_params", {}),
        }]

    built_states = []

    for task in task_list:
        route  = task.get("route", "unclear")
        params = task.get("extracted_params", {})

        if route not in BUILDERS:
            state["logs"].append(
                log("Master Orchestrator", f"Unknown route '{route}' — skipping [WARN]")
            )
            continue

        wid = f"WF-{route}-{str(uuid.uuid4())[:6].upper()}"
        built = BUILDERS[route](params, wid)

        built_states.append({
            "route"       : route,
            "workflow_id" : wid,
            "state"       : built,
        })

        state["logs"].append(log(
            "Master Orchestrator",
            f"Built {route} state — workflow_id={wid} "
            f"params={list(params.keys())} [OK]"
        ))

    state["built_states"] = built_states
    duration = int((time.time() - start) * 1000)
    state["logs"].append(log(
        "Master Orchestrator",
        f"State builder done — {len(built_states)} workflow(s) ready [{duration}ms]"
    ))

    return state