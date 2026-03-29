

"""
Module 6.1 — Ask-Why Engine
POST /explain  →  explains any agent decision in plain English
Uses the same OpenRouter setup as meeting_agent.py
"""

import json
import httpx
import os
import sys
from dotenv import load_dotenv   #type: ignore

load_dotenv()  # must be called before os.getenv

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = "arcee-ai/trinity-large-preview:free"

SYSTEM_PROMPT = """You are an audit assistant for AuditPilot, an AI workflow system.
Explain agent decisions in plain English to an operations manager.
- Name the specific agent and step
- Say what decision was made and WHY
- If retried, explain the retry logic
- If escalated, say exactly what the human needs to do
- End with one clear recommendation
Keep it under 150 words."""


def get_traces_for_workflow(workflow_id: str) -> list:
    """
    Fetches all traces for a workflow_id from DB.
    Used by /explain endpoint so frontend only needs to send workflow_id.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database import get_workflow_traces
        return get_workflow_traces(workflow_id)
    except Exception as e:
        print(f"[explainer] Could not fetch traces from DB: {e}")
        return []


def explain_decision(workflow_id: str, question: str, traces: list = None) -> str:
    """
    Takes workflow traces (list of dicts) and a question.
    If traces not provided, fetches from DB automatically.
    Returns a plain-English explanation string.
    """
    # Auto-fetch from DB if caller didn't pass traces
    if not traces:
        traces = get_traces_for_workflow(workflow_id)

    if not traces:
        return f"No traces found for workflow '{workflow_id}'. Run the workflow first."

    traces_json = json.dumps(traces, indent=2, default=str)

    prompt = f"""Here are the execution traces for workflow '{workflow_id}':

{traces_json}

The manager asks: {question}

Answer in plain English. Reference specific agents and steps from the traces.
End with a clear recommendation."""

    try:
        response = httpx.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )

        result = response.json()

        if "error" in result:
            return f"Explainer error: {result['error'].get('message', 'unknown error')}"

        return result["choices"][0]["message"]["content"].strip()

    except httpx.TimeoutException:
        return "Explanation timed out. Please try again."
    except Exception as e:
        return f"Explainer failed: {str(e)}"


# Quick test — run this file directly to verify it works
if __name__ == "__main__":

    # Test 1 — hardcoded traces
    print("── Test 1: hardcoded traces ─────────────────────────")
    sample_traces = [
        {
            "agent": "intake_agent",
            "status": "success",
            "decision": "continue",
            "decision_reason": "42 words — validation passed"
        },
        {
            "agent": "extraction_agent",
            "status": "success",
            "decision": "continue",
            "decision_reason": "3 tasks found"
        },
        {
            "agent": "owner_resolution",
            "status": "ambiguous",
            "decision": "human_required",
            "decision_reason": "Multiple matches: Rahul Sharma, Rahul Verma"
        }
    ]

    answer = explain_decision(
        workflow_id="wf_test_001",
        question="Why was the owner resolution escalated?",
        traces=sample_traces
    )
    print(answer)

    # Test 2 — pull from DB automatically
    print("\n── Test 2: live DB lookup ───────────────────────────")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_all_traces
    recent = get_all_traces()
    if recent:
        wid = recent[0]["workflow_id"]
        print(f"Testing with workflow: {wid}")
        answer2 = explain_decision(
            workflow_id=wid,
            question="What happened in this workflow and what needs human attention?"
        )
        print(answer2)
    else:
        print("No traces in DB — run test_meeting.py first")