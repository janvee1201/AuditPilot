# from fastapi import FastAPI # type: ignore
# from fastapi.middleware.cors import CORSMiddleware # type: ignore
# from pydantic import BaseModel
# from agents.meeting_agent import run_meeting_agent

# app = FastAPI()

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"]
# )

# class MeetingInput(BaseModel):
#     notes: str

# @app.post("/workflow/meeting")
# def run_meeting(input: MeetingInput):
#     result = run_meeting_agent(input.notes)
#     return result

# @app.get("/health")
# def health():
#     return {"status": "running"}


from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.meeting_agent import run_meeting_agent
import uuid

# ── Module 6 imports ──────────────────────────────────────────
import sys
import os
module6_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "module6")
sys.path.insert(0, module6_path)

from scheduler import start_scheduler, stop_scheduler, run_briefing_job
from explainer import explain_decision

# ── Database imports ──────────────────────────────────────────
from database import (
    get_workflow_traces,
    get_workflow_tasks,
    get_pattern_memory,
    get_systemic_alerts,
    get_connection,
)
# ─────────────────────────────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Module 6 lifecycle ────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    start_scheduler()

@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()
# ─────────────────────────────────────────────────────────────


# ── Existing routes (unchanged) ───────────────────────────────
class MeetingInput(BaseModel):
    notes: str

@app.post("/workflow/meeting")
def run_meeting(input: MeetingInput):
    result = run_meeting_agent(input.notes)
    return result


@app.get("/health")
def health():
    return {"status": "running"}


# ── Module 6 routes ───────────────────────────────────────────
class ExplainInput(BaseModel):
    workflow_id: str
    question: str
    traces: list = []   # optional — fetched from DB automatically if not sent

@app.post("/explain")
def explain(input: ExplainInput):
    # passes traces if frontend sent them, otherwise explain_decision fetches from DB
    answer = explain_decision(input.workflow_id, input.question, input.traces or None)
    return {"explanation": answer}


@app.post("/briefing/generate")
def trigger_briefing():
    """Manual trigger — called by the demo button in frontend."""
    result = run_briefing_job()
    return result


# ── GET /logs ─────────────────────────────────────────────────
# Frontend polls this every 800ms for live log stream
@app.get("/logs")
def get_logs(workflow_id: str = Query(...)):
    """Returns last 50 trace entries for a workflow — used by live log panel."""
    traces = get_workflow_traces(workflow_id)
    logs = []
    for t in traces[-50:]:
        logs.append({
            "timestamp":  t.get("created_at", ""),
            "agent":      t.get("agent", ""),
            "action":     t.get("step_id") or t.get("action", ""),
            "outcome":    t.get("status") or t.get("outcome", ""),
            "decision":   t.get("decision", ""),
            "message":    t.get("decision_reason") or t.get("reason", ""),
        })
    return {"workflow_id": workflow_id, "logs": logs}


# ── GET /traces ───────────────────────────────────────────────
# Trace explorer page — full decision history
@app.get("/traces")
def get_traces(workflow_id: str = Query(...), outcome: str = Query(None)):
    """Returns all traces for a workflow with optional status filter."""
    traces = get_workflow_traces(workflow_id)
    if outcome:
        traces = [t for t in traces if t.get("status") == outcome or t.get("outcome") == outcome]
    return {"workflow_id": workflow_id, "traces": traces, "count": len(traces)}


# ── GET /memory ───────────────────────────────────────────────
# Pattern memory live panel
@app.get("/memory")
def get_memory():
    """Returns all pattern memory rows — used by memory panel."""
    return {"patterns": get_pattern_memory()}


# ── GET /workflow/status ──────────────────────────────────────
# Step progress bar on frontend
@app.get("/workflow/status")
def get_workflow_status(workflow_id: str = Query(...)):
    """Returns step counts per status for a workflow — used by progress bar."""
    traces = get_workflow_traces(workflow_id)
    status_counts = {"success": 0, "failed": 0, "escalated": 0, "running": 0}
    for t in traces:
        s = t.get("status") or t.get("outcome", "")
        if s in status_counts:
            status_counts[s] += 1
        elif s == "ambiguous" or t.get("decision") == "human_required":
            status_counts["escalated"] += 1

    overall = "completed"
    if status_counts["running"] > 0:
        overall = "running"
    elif status_counts["failed"] > 0 or status_counts["escalated"] > 0:
        overall = "needs_action"

    return {
        "workflow_id": workflow_id,
        "status": overall,
        "counts": status_counts,
        "total": len(traces)
    }


# ── GET /systemic-alerts ──────────────────────────────────────
# Red alert banner — W4 cross-workflow feature
@app.get("/systemic-alerts")
def get_alerts():
    """Returns unresolved systemic alerts — used by alert banner."""
    return {"alerts": get_systemic_alerts()}


# ── GET /workflow/tasks ───────────────────────────────────────
# Returns tasks for a workflow — used by task list panel
@app.get("/workflow/tasks")
def get_tasks(workflow_id: str = Query(...)):
    """Returns all tasks (assigned + escalated) for a workflow."""
    return {"workflow_id": workflow_id, "tasks": get_workflow_tasks(workflow_id)}