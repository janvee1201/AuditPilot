"""
orchestrator/nodes/intent_classify.py

Calls OpenRouter API to classify the user's task.
Returns route, confidence, extracted params,
and whether multiple tasks were detected.

If clarification answer is present in state
(user replied to a previous question),
it is appended to the original task before classification.
"""

import json
import time
import os
import urllib.request
import urllib.error

from dotenv import load_dotenv
from shared.logger import log

load_dotenv()

OPENROUTER_API_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
MODEL                = "openrouter/auto"
OPENROUTER_URL       = "https://openrouter.ai/api/v1/chat/completions"
CONFIDENCE_THRESHOLD = 0.85

SYSTEM_PROMPT = """You are a workflow router for AuditPilot — a business process automation system.

You have exactly 3 workflows available:

W1 — Client onboarding
  Use when: user wants to onboard, register, add, or create a new client or company.
  Examples: "onboard Krishna Logistics", "add new client Mehta Textiles", "register a company"

W2 — Procurement to payment
  Use when: user wants to process a purchase order, make a payment, pay a vendor,
  approve an invoice, or handle any financial transaction with a supplier.
  Examples: "pay Tata Steels", "process PO-2024-001", "approve invoice from Sharma Industries"

W3 — Meeting to task
  Use when: user wants to convert meeting notes into tasks, assign action items
  from a meeting, or extract and assign tasks from any unstructured text.
  Examples: "assign tasks from today's meeting", "extract action items", "meeting notes: ..."

Return ONLY valid JSON. No explanation. No markdown. Just the JSON object.

Format:
{
  "route": "W1" | "W2" | "W3" | "unclear",
  "confidence": 0.0 to 1.0,
  "extracted_params": {
    for W1: {"client_name": "...", "email": "...", "gstin": "...", "phone": "..."},
    for W2: {"vendor_name": "...", "po_number": "...", "amount": 0, "vendor_id": "..."},
    for W3: {"notes": "..."}
  },
  "task_list": [
    {"route": "W1", "extracted_params": {...}},
    {"route": "W2", "extracted_params": {...}}
  ],
  "is_multi_task": false,
  "clarification_question": "only set this if route is unclear"
}

If the task mentions two separate workflows (e.g. "onboard X and pay Y"),
set is_multi_task=true and populate task_list with both tasks.
Set route to the first task's route in that case.

If you cannot determine the workflow with confidence >= 0.85,
set route="unclear" and provide a clarification_question."""


def _call_openrouter(prompt: str) -> dict:
    """
    Calls OpenRouter API using urllib (no requests/httpx dependency).
    Returns parsed JSON dict or raises on error.
    """
    payload = json.dumps({
        "model"   : MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data    = payload,
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type" : "application/json",
        },
        method = "POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    raw = body["choices"][0]["message"]["content"].strip()

    # strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def intent_classify_node(state: dict) -> dict:
    start = time.time()
    task  = state.get("user_task", "")

    # if user answered a clarification question — append their answer
    if state.get("clarification_answer"):
        task = f"{task}\nUser clarification: {state['clarification_answer']}"

    state["logs"].append(
        log("Master Orchestrator", f"Classifying task: '{task[:60]}...'")
    )

    try:
        result = _call_openrouter(task)

        route      = result.get("route", "unclear")
        confidence = float(result.get("confidence", 0.0))
        params     = result.get("extracted_params", {})
        task_list  = result.get("task_list", [])
        is_multi   = result.get("is_multi_task", False)
        clarq      = result.get("clarification_question", "")

        state["route"]            = route
        state["confidence"]       = confidence
        state["extracted_params"] = params
        state["task_list"]        = task_list if is_multi else [{"route": route, "extracted_params": params}]

        duration = int((time.time() - start) * 1000)

        if route == "unclear" or confidence < CONFIDENCE_THRESHOLD:
            state["needs_clarification"]    = True
            state["clarification_question"] = clarq or "Could you clarify — are you onboarding a client, processing a payment, or assigning meeting tasks?"
            state["logs"].append(log(
                "Master Orchestrator",
                f"Low confidence ({confidence}) — clarification needed [WARN]"
            ))
        else:
            state["needs_clarification"] = False
            multi_label = f" (multi-task: {len(task_list)} tasks)" if is_multi else ""
            state["logs"].append(log(
                "Master Orchestrator",
                f"Route={route} confidence={confidence}{multi_label} "
                f"params={list(params.keys())} [{duration}ms] [OK]"
            ))

    except urllib.error.URLError as e:
        state["logs"].append(log("Master Orchestrator", f"API call failed: {e} [FAIL]"))
        state["route"]      = "unclear"
        state["confidence"] = 0.0
        state["needs_clarification"]    = True
        state["clarification_question"] = "I could not reach the classification service. Please specify: onboard a client / process a payment / assign meeting tasks?"
        state["error"] = str(e)

    except (json.JSONDecodeError, KeyError) as e:
        state["logs"].append(log("Master Orchestrator", f"Parse error: {e} [FAIL]"))
        state["route"]      = "unclear"
        state["confidence"] = 0.0
        state["needs_clarification"]    = True
        state["clarification_question"] = "I could not understand the task. Please specify: onboard a client / process a payment / assign meeting tasks?"
        state["error"] = str(e)

    return state