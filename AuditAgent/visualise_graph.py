"""
visualize_full_architecture.py

Builds one single LangGraph StateGraph that represents
the entire AuditPilot architecture — master orchestrator,
W1, W2, W3, W4 — all connected as they actually run.

Run from project root:
    python visualize_full_architecture.py

Saves: graphs/auditpilot_full_architecture.png
"""

import sys
import types
from pathlib import Path
from typing import TypedDict, Optional

# ── mock httpx so w3 imports don't fail ──────────────────
httpx_mod = types.ModuleType("httpx")
class FakeTimeout(Exception): pass
httpx_mod.TimeoutException = FakeTimeout
sys.modules.setdefault("httpx", httpx_mod)

from langgraph.graph import StateGraph, END


# ─────────────────────────────────────────────────────────
# COMBINED STATE
# Single flat state that covers all agents
# ─────────────────────────────────────────────────────────

class FullArchState(TypedDict):
    user_task               : str
    route                   : str
    confidence              : float
    needs_clarification     : bool
    extracted_params        : dict
    task_list               : list
    # W1 fields
    w1_input                : dict
    w1_error                : Optional[str]
    w1_retry_count          : int
    w1_kyc_status           : bool
    # W2 fields
    w2_input                : dict
    w2_error                : Optional[str]
    w2_retry_count          : int
    w2_status               : str
    # W3 fields
    w3_notes                : str
    w3_error                : Optional[str]
    w3_tasks                : list
    w3_assigned             : list
    w3_escalated            : list
    # W4 fields
    w4_error_hash           : Optional[str]
    w4_decision             : Optional[str]
    w4_is_systemic          : bool
    # result
    final_reply             : str
    logs                    : list


# ─────────────────────────────────────────────────────────
# NODE STUBS
# These are display-only nodes — they show the architecture
# without running the actual agent logic
# ─────────────────────────────────────────────────────────

def intent_classify(state):   return state
def clarification(state):     return state
def state_builder(state):     return state

def w1_validate(state):       return state
def w1_duplicate(state):      return state
def w1_kyc(state):            return state
def w1_create_account(state): return state
def w1_error(state):          return state

def w2_intake(state):         return state
def w2_validation(state):     return state
def w2_vendor_check(state):   return state
def w2_approval(state):       return state
def w2_payment(state):        return state
def w2_monitor(state):        return state
def w2_orchestrator(state):   return state
def w2_audit(state):          return state

def w3_intake(state):              return state
def w3_extraction(state):          return state
def w3_owner_resolution(state):    return state
def w3_task_writer(state):         return state
def w3_error(state):               return state

def w4_t13_detect(state):          return state
def w4_t14_decide(state):          return state
def w4_t15_systemic_alert(state):  return state
def w4_t16_update(state):          return state

def result_builder(state):    return state


# ─────────────────────────────────────────────────────────
# ROUTING STUBS
# ─────────────────────────────────────────────────────────

def route_classify(state):
    if state.get("needs_clarification"):
        return "clarification"
    return "state_builder"

def route_state_builder(state):
    r = state.get("route", "W1")
    if r == "W2": return "w2_intake"
    if r == "W3": return "w3_intake"
    return "w1_validate"

def route_w1_error(state):
    return "w1_kyc" if state.get("w1_retry_count", 0) >= 1 else "result_builder"

def route_w1_on_error(state):
    return "w1_error" if state.get("w1_error") else "continue"

def route_w2_orchestrator(state):
    return "w2_payment" if state.get("w2_retry_count", 0) == 1 else "w2_audit"

def route_w3_on_error(state):
    return "w3_error" if state.get("w3_error") else "continue"

def route_w4_systemic(state):
    return "w4_t15_systemic_alert" if state.get("w4_is_systemic") else "w4_t16_update"


# ─────────────────────────────────────────────────────────
# BUILD THE COMBINED GRAPH
# ─────────────────────────────────────────────────────────

def build_full_graph():
    builder = StateGraph(FullArchState)

    # ── Master Orchestrator nodes ─────────────────────────
    builder.add_node("intent_classify",  intent_classify)
    builder.add_node("clarification",    clarification)
    builder.add_node("state_builder",    state_builder)
    builder.add_node("result_builder",   result_builder)

    # ── W1 nodes ──────────────────────────────────────────
    builder.add_node("w1_validate",       w1_validate)
    builder.add_node("w1_duplicate",      w1_duplicate)
    builder.add_node("w1_kyc",            w1_kyc)
    builder.add_node("w1_create_account", w1_create_account)
    builder.add_node("w1_error",          w1_error)

    # ── W2 nodes ──────────────────────────────────────────
    builder.add_node("w2_intake",       w2_intake)
    builder.add_node("w2_validation",   w2_validation)
    builder.add_node("w2_vendor_check", w2_vendor_check)
    builder.add_node("w2_approval",     w2_approval)
    builder.add_node("w2_payment",      w2_payment)
    builder.add_node("w2_monitor",      w2_monitor)
    builder.add_node("w2_orchestrator", w2_orchestrator)
    builder.add_node("w2_audit",        w2_audit)

    # ── W3 nodes ──────────────────────────────────────────
    builder.add_node("w3_intake",            w3_intake)
    builder.add_node("w3_extraction",        w3_extraction)
    builder.add_node("w3_owner_resolution",  w3_owner_resolution)
    builder.add_node("w3_task_writer",       w3_task_writer)
    builder.add_node("w3_error",             w3_error)

    # ── W4 nodes ──────────────────────────────────────────
    builder.add_node("w4_t13_detect",         w4_t13_detect)
    builder.add_node("w4_t14_decide",         w4_t14_decide)
    builder.add_node("w4_t15_systemic_alert", w4_t15_systemic_alert)
    builder.add_node("w4_t16_update",         w4_t16_update)

    # ── Entry point ───────────────────────────────────────
    builder.set_entry_point("intent_classify")

    # ── Orchestrator edges ────────────────────────────────
    builder.add_conditional_edges(
        "intent_classify", route_classify,
        {"clarification": "clarification", "state_builder": "state_builder"},
    )
    builder.add_edge("clarification", "intent_classify")
    builder.add_conditional_edges(
        "state_builder", route_state_builder,
        {
            "w1_validate": "w1_validate",
            "w2_intake"  : "w2_intake",
            "w3_intake"  : "w3_intake",
        },
    )

    # ── W1 edges ──────────────────────────────────────────
    builder.add_conditional_edges(
        "w1_validate", route_w1_on_error,
        {"w1_error": "w1_error", "continue": "w1_duplicate"},
    )
    builder.add_conditional_edges(
        "w1_duplicate", route_w1_on_error,
        {"w1_error": "w1_error", "continue": "w1_kyc"},
    )
    builder.add_conditional_edges(
        "w1_kyc", route_w1_on_error,
        {"w1_error": "w1_error", "continue": "w1_create_account"},
    )
    builder.add_edge("w1_create_account", "result_builder")
    builder.add_conditional_edges(
        "w1_error", route_w1_error,
        {"w1_kyc": "w1_kyc", "result_builder": "result_builder"},
    )

    # w1_error → calls W4
    builder.add_edge("w1_error",    "w4_t13_detect")

    # ── W2 edges ──────────────────────────────────────────
    builder.add_edge("w2_intake",       "w2_validation")
    builder.add_edge("w2_validation",   "w2_vendor_check")
    builder.add_edge("w2_vendor_check", "w2_approval")
    builder.add_edge("w2_approval",     "w2_payment")
    builder.add_edge("w2_payment",      "w2_monitor")
    builder.add_edge("w2_monitor",      "w2_orchestrator")
    builder.add_conditional_edges(
        "w2_orchestrator", route_w2_orchestrator,
        {"w2_payment": "w2_payment", "w2_audit": "w2_audit"},
    )
    builder.add_edge("w2_audit", "result_builder")

    # w2_orchestrator → calls W4
    builder.add_edge("w2_orchestrator", "w4_t13_detect")

    # ── W3 edges ──────────────────────────────────────────
    builder.add_conditional_edges(
        "w3_intake", route_w3_on_error,
        {"w3_error": "w3_error", "continue": "w3_extraction"},
    )
    builder.add_conditional_edges(
        "w3_extraction", route_w3_on_error,
        {"w3_error": "w3_error", "continue": "w3_owner_resolution"},
    )
    builder.add_edge("w3_owner_resolution", "w3_task_writer")
    builder.add_edge("w3_task_writer",      "result_builder")
    builder.add_edge("w3_error",            "result_builder")

    # w3_owner_resolution → calls W4
    builder.add_edge("w3_owner_resolution", "w4_t13_detect")

    # ── W4 internal edges ─────────────────────────────────
    builder.add_edge("w4_t13_detect", "w4_t14_decide")
    builder.add_conditional_edges(
        "w4_t14_decide", route_w4_systemic,
        {
            "w4_t15_systemic_alert": "w4_t15_systemic_alert",
            "w4_t16_update"        : "w4_t16_update",
        },
    )
    builder.add_edge("w4_t15_systemic_alert", "w4_t16_update")
    builder.add_edge("w4_t16_update",         "result_builder")

    # ── Final edge ────────────────────────────────────────
    builder.add_edge("result_builder", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    print("\nBuilding full AuditPilot architecture graph...")

    graph = build_full_graph()

    OUTPUT_DIR = Path(__file__).resolve().parent / "graphs"
    OUTPUT_DIR.mkdir(exist_ok=True)

    path = OUTPUT_DIR / "auditpilot_full_architecture.png"

    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
        with open(path, "wb") as f:
            f.write(png_bytes)
        print(f"  Saved → graphs/auditpilot_full_architecture.png")
        print(f"  Full path: {path}")
        print("\n  Open graphs/auditpilot_full_architecture.png to see the full architecture.\n")

    except Exception as e:
        print(f"\n  PNG export failed: {e}")
        print("  Trying Mermaid source instead...\n")

        # fallback — print mermaid source so you can paste into mermaid.live
        try:
            mermaid_src = graph.get_graph().draw_mermaid()
            mermaid_path = OUTPUT_DIR / "auditpilot_full_architecture.md"
            with open(mermaid_path, "w") as f:
                f.write("```mermaid\n")
                f.write(mermaid_src)
                f.write("\n```\n")
            print(f"  Mermaid source saved → graphs/auditpilot_full_architecture.md")
            print("  Paste the content at https://mermaid.live to view the diagram.\n")
        except Exception as e2:
            print(f"  Mermaid export also failed: {e2}")


if __name__ == "__main__":
    main()