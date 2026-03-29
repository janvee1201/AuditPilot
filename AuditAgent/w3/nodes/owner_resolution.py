"""
w3/nodes/owner_resolution.py  —  T10

Resolves owner names from tasks to actual team members.

Three outcomes per name:
  resolved  — exactly one match → auto assigned
  ambiguous — two or more match → HITL picks one
  not_found — zero matches      → HITL: add to JSON / reassign / skip

W4 called once per error for pattern tracking.
New members added to team_members.json permanently.
"""

import json
import time
from pathlib import Path

from shared.logger import log
from shared.db import write_trace
from shared.error_map import get_error_hash
from w4.agent import run_w4

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "team_members.json"

# names that look like owner names but are not real people
INVALID_NAMES = {
    "not specified", "none", "n/a", "tbd", "unknown",
    "not mentioned", "team", "everyone", "all",
}


def _load_team() -> list:
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_team(team: list) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(team, f, indent=2)


def _resolve_one(owner_name: str, team: list) -> dict:
    name_lower = owner_name.lower().strip()
    matches = [
        m for m in team
        if name_lower in m.get("full_name", "").lower()
    ]
    if len(matches) == 1:
        return {"status": "resolved", "member": matches[0]}
    elif len(matches) > 1:
        return {
            "status" : "ambiguous",
            "matches": matches,
            "reason" : f"Found {len(matches)} people named '{owner_name}'",
        }
    else:
        return {
            "status": "not_found",
            "reason": f"No team member named '{owner_name}'",
        }


def _hitl_ambiguous(owner_name: str, matches: list, task: str) -> dict | None:
    """HITL when two or more members match. Human picks one or skips."""
    print(f"\n  {'─'*52}")
    print(f"  [HITL] Ambiguous owner — human selection required")
    print(f"  {'─'*52}")
    print(f"  Task : {task[:60]}")
    print(f"  Name : '{owner_name}' matched {len(matches)} people\n")
    for i, m in enumerate(matches, 1):
        print(f"  {i}. {m['full_name']:<20} ({m['role']})")
    print(f"  {len(matches)+1}. Skip this task")
    print()

    try:
        choice = input("  Your choice: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            chosen = matches[idx]
            print(f"\n  Assigned to {chosen['full_name']} [OK]\n")
            return chosen
        else:
            print(f"\n  Task skipped.\n")
            return None
    except (ValueError, EOFError):
        print(f"\n  Invalid — task skipped.\n")
        return None


def _hitl_not_found(owner_name: str, task: str) -> dict | None:
    """
    HITL when name not in team_members.json.
    Option 1 adds the person permanently to team_members.json.
    """
    print(f"\n  {'─'*52}")
    print(f"  [HITL] Unknown person — human action required")
    print(f"  {'─'*52}")
    print(f"  Task : {task[:60]}")
    print(f"  Name : '{owner_name}' is not in team members\n")
    print(f"  1. Add as new member and assign task")
    print(f"  2. Reassign to an existing team member")
    print(f"  3. Skip this task")
    print()

    try:
        choice = input("  Your choice (1 / 2 / 3): ").strip()
    except EOFError:
        choice = "3"

    if choice == "1":
        email = input(f"  Email for {owner_name} (Enter to auto-generate): ").strip()
        role  = input(f"  Role for {owner_name} (Enter for default): ").strip()

        team         = _load_team()
        existing_ids = {m.get("id", "") for m in team}
        new_id       = f"TM-{owner_name[:3].upper()}-{str(len(team)+1).zfill(3)}"
        while new_id in existing_ids:
            new_id += "X"

        new_member = {
            "id"           : new_id,
            "full_name"    : owner_name.title(),
            "email"        : email if email else f"{owner_name.lower().replace(' ','.')}@company.in",
            "role"         : role  if role  else "Team Member",
            "current_tasks": 1,
        }

        team.append(new_member)
        _save_team(team)

        print(f"\n  {new_member['full_name']} (ID: {new_id}) added to team_members.json [OK]")
        print(f"  Task assigned to {new_member['full_name']} [OK]\n")
        return new_member

    elif choice == "2":
        team = _load_team()
        print(f"\n  Existing team members:")
        for i, m in enumerate(team, 1):
            print(f"  {i}. {m['full_name']:<20} ({m['role']})")
        print()
        try:
            pick = int(input("  Assign to member number: ").strip()) - 1
            if 0 <= pick < len(team):
                chosen = team[pick]
                print(f"\n  Reassigned to {chosen['full_name']} [OK]\n")
                return chosen
        except (ValueError, EOFError):
            pass
        print("\n  Invalid — task skipped.\n")
        return None

    else:
        print(f"\n  Task skipped.\n")
        return None


def owner_resolution_node(state: dict) -> dict:
    start = time.time()
    wid   = state.get("workflow_id", "WF-UNKNOWN")
    tasks = state.get("tasks", [])

    state["logs"].append(
        log("Owner Resolution Agent", f"Resolving owners for {len(tasks)} tasks...")
    )

    # reload team fresh at start of each run
    team            = _load_team()
    assigned_tasks  = []
    escalated_tasks = []
    human_required  = []

    for task in tasks:
        owner_name = task.get("owner_name", "").strip()
        t_start    = time.time()

        # ── skip invalid owner names from LLM ────────────
        if not owner_name or owner_name.lower() in INVALID_NAMES:
            state["logs"].append(
                log("Owner Resolution Agent",
                    f"Skipping invalid owner name: '{owner_name}' [OK]")
            )
            continue

        # reload team after each HITL in case new member was added
        team       = _load_team()
        resolution = _resolve_one(owner_name, team)

        # ── clean match ───────────────────────────────────
        if resolution["status"] == "resolved":
            member = resolution["member"]
            assigned_tasks.append({
                "task"           : task["task"],
                "owner"          : member,
                "deadline"       : task.get("deadline"),
                "priority"       : task.get("priority"),
                "source_quote"   : task.get("source_quote"),
                "decision"       : "assigned",
                "decision_reason": f"Exact match for '{owner_name}'",
            })
            state["logs"].append(
                log("Owner Resolution Agent",
                    f"'{owner_name}' → {member['full_name']} ({member['role']}) [OK]")
            )
            write_trace(
                workflow_id = wid, workflow_type = "W3",
                step_id = "T10_owner_resolution", agent = "owner_resolution_agent",
                status = "success",
                input_data  = {"owner_name": owner_name},
                output_data = {"member_id": member["id"], "member_name": member["full_name"]},
                duration_ms = int((time.time() - t_start) * 1000),
            )

        # ── ambiguous — HITL picks one ────────────────────
        elif resolution["status"] == "ambiguous":
            error_hash, error_type = get_error_hash("ambiguous")
            options_str = ", ".join(m["full_name"] for m in resolution["matches"])

            state["logs"].append(
                log("Owner Resolution Agent",
                    f"'{owner_name}' is ambiguous — {options_str} — HITL required [WARN]")
            )

            # W4 called once for pattern tracking
            run_w4(
                workflow_id    = wid,
                workflow_type  = "W3",
                error_hash     = error_hash,
                error_type     = error_type,
                retry_succeeded= False,
            )

            chosen = _hitl_ambiguous(owner_name, resolution["matches"], task["task"])

            if chosen:
                assigned_tasks.append({
                    "task"           : task["task"],
                    "owner"          : chosen,
                    "deadline"       : task.get("deadline"),
                    "priority"       : task.get("priority"),
                    "source_quote"   : task.get("source_quote"),
                    "decision"       : "assigned_via_hitl",
                    "decision_reason": f"Human selected {chosen['full_name']} from ambiguous match",
                })
                state["logs"].append(
                    log("Owner Resolution Agent",
                        f"'{owner_name}' → {chosen['full_name']} (human selected) [OK]")
                )
            else:
                escalated_tasks.append({
                    "task"           : task["task"],
                    "owner_searched" : owner_name,
                    "deadline"       : task.get("deadline"),
                    "priority"       : task.get("priority"),
                    "decision"       : "skipped",
                    "decision_reason": "Human skipped ambiguous owner",
                    "human_action"   : f"Choose between: {options_str}",
                })
                human_required.append({
                    "step"         : "owner_resolution",
                    "task"         : task["task"],
                    "reason"       : resolution["reason"],
                    "action_needed": f"Choose between: {options_str}",
                })

            write_trace(
                workflow_id = wid, workflow_type = "W3",
                step_id = "T10_owner_resolution", agent = "owner_resolution_agent",
                status = "success" if chosen else "escalated",
                input_data  = {"owner_name": owner_name},
                output_data = {
                    "status"  : "ambiguous",
                    "resolved": chosen["full_name"] if chosen else None,
                    "options" : [m["full_name"] for m in resolution["matches"]],
                },
                error_hash  = error_hash,
                error_type  = error_type,
                decision    = "assigned_via_hitl" if chosen else "skipped",
                duration_ms = int((time.time() - t_start) * 1000),
            )

        # ── not found — HITL decides ──────────────────────
        else:
            error_hash, error_type = get_error_hash("not_found")

            state["logs"].append(
                log("Owner Resolution Agent",
                    f"'{owner_name}' not found in team — HITL required [WARN]")
            )

            # W4 called once for pattern tracking
            run_w4(
                workflow_id    = wid,
                workflow_type  = "W3",
                error_hash     = error_hash,
                error_type     = error_type,
                retry_succeeded= False,
            )

            chosen = _hitl_not_found(owner_name, task["task"])

            if chosen:
                assigned_tasks.append({
                    "task"           : task["task"],
                    "owner"          : chosen,
                    "deadline"       : task.get("deadline"),
                    "priority"       : task.get("priority"),
                    "source_quote"   : task.get("source_quote"),
                    "decision"       : "assigned_via_hitl",
                    "decision_reason": f"Human resolved unknown name '{owner_name}'",
                })
                state["logs"].append(
                    log("Owner Resolution Agent",
                        f"'{owner_name}' → {chosen['full_name']} (human resolved) [OK]")
                )
            else:
                escalated_tasks.append({
                    "task"           : task["task"],
                    "owner_searched" : owner_name,
                    "deadline"       : task.get("deadline"),
                    "priority"       : task.get("priority"),
                    "decision"       : "skipped",
                    "decision_reason": f"Human skipped unknown name '{owner_name}'",
                    "human_action"   : f"Add '{owner_name}' to team or reassign",
                })
                human_required.append({
                    "step"         : "owner_resolution",
                    "task"         : task["task"],
                    "reason"       : resolution["reason"],
                    "action_needed": f"Add '{owner_name}' to team or reassign",
                })

            write_trace(
                workflow_id = wid, workflow_type = "W3",
                step_id = "T10_owner_resolution", agent = "owner_resolution_agent",
                status = "success" if chosen else "escalated",
                input_data  = {"owner_name": owner_name},
                output_data = {
                    "status"  : "not_found",
                    "resolved": chosen["full_name"] if chosen else None,
                },
                error_hash  = error_hash,
                error_type  = error_type,
                decision    = "assigned_via_hitl" if chosen else "skipped",
                duration_ms = int((time.time() - t_start) * 1000),
            )

    # ── store results ─────────────────────────────────────
    state["assigned_tasks"]  = assigned_tasks
    state["escalated_tasks"] = escalated_tasks
    state["human_required"]  = human_required

    total    = len(tasks)
    assigned = len(assigned_tasks)
    state["logs"].append(
        log("Owner Resolution Agent",
            f"Done — assigned={assigned} escalated={len(escalated_tasks)} "
            f"of {total} tasks [OK]")
    )
    return state