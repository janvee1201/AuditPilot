# from agents.meeting_agent import run_meeting_agent

# notes = """Product sync - 18 March 2024
# Attendees: Priya, Rahul, Neha, Arjun

# Priya needs to update the marketing deck with new pricing by this friday,
# client presentation depends on it.
# Rahul should fix the API timeout issue before end of next week.
# Neha to get budget approval for the Singapore office expansion.
# Arjun will coordinate timezone scheduling with Singapore before month end.
# Rahul to check on the CRM migration status and report back by wednesday."""

# result = run_meeting_agent(notes)

# print("\n========== ASSIGNED TASKS ==========")
# for t in result["assigned_tasks"]:
#     print(f"\nTask    : {t['task']}")
#     print(f"Owner   : {t['owner']['name']} ({t['owner']['role']})")
#     print(f"Email   : {t['owner']['email']}")
#     print(f"Deadline: {t['deadline']}")
#     print(f"Priority: {t['priority']}")

# print("\n========== ESCALATED TASKS ==========")
# for t in result["escalated_tasks"]:
#     print(f"\nTask    : {t['task']}")
#     print(f"Reason  : {t['decision_reason']}")
#     if t.get("options"):
#         print(f"Options :")
#         for o in t["options"]:
#             print(f"          - {o['name']} ({o['role']})")

# print("\n========== SUMMARY ==========")
# print(f"Total tasks : {result['summary']['total_tasks']}")
# print(f"Assigned    : {result['summary']['assigned']}")
# print(f"Escalated   : {result['summary']['escalated']}")
# print(f"Autonomy    : {result['summary']['autonomy_rate']}")

# from agents.meeting_agent import run_meeting_agent

# notes = """Product sync - 18 March 2024
# Attendees: Priya, Rahul, Neha, Arjun

# Priya needs to update the marketing deck with new pricing by this friday,
# client presentation depends on it.
# Rahul should fix the API timeout issue before end of next week.
# Neha to get budget approval for the Singapore office expansion.
# Arjun will coordinate timezone scheduling with Singapore before month end.
# Rahul to check on the CRM migration status and report back by wednesday."""

# result = run_meeting_agent(notes)

# print("\n========== ASSIGNED TASKS ==========")
# for t in result["assigned_tasks"]:
#     print(f"\nTask    : {t['task']}")
#     print(f"Owner   : {t['owner']['name']} ({t['owner']['role']})")
#     print(f"Email   : {t['owner']['email']}")
#     print(f"Deadline: {t['deadline']}")
#     print(f"Priority: {t['priority']}")

# print("\n========== ESCALATED TASKS ==========")
# for t in result["escalated_tasks"]:
#     print(f"\nTask    : {t['task']}")
#     print(f"Reason  : {t['decision_reason']}")
#     if t.get("options"):
#         print(f"Options :")
#         for o in t["options"]:
#             print(f"          - {o['name']} ({o['role']})")

# print("\n========== SUMMARY ==========")
# print(f"Total tasks : {result['summary']['total_tasks']}")
# print(f"Assigned    : {result['summary']['assigned']}")
# print(f"Escalated   : {result['summary']['escalated']}")
# print(f"Autonomy    : {result['summary']['autonomy_rate']}")


from database import init_db
from agents.meeting_agent import run_meeting_agent, pattern_memory

# Creates all tables if they dont exist yet — safe to run every time
init_db()

def print_separator(title):
    print("\n" + "="*50)
    print(f"  TEST: {title}")
    print("="*50)

def print_result(result):
    print(f"\nOutcome      : {result['summary']['outcome']}")
    print(f"Autonomy     : {result['summary'].get('autonomy_rate', '0%')}")
    print(f"Assigned     : {len(result['assigned_tasks'])}")
    print(f"Escalated    : {len(result['escalated_tasks'])}")
    print(f"Human needed : {len(result['human_required'])}")

    if result["assigned_tasks"]:
        print("\nASSIGNED:")
        for t in result["assigned_tasks"]:
            print(f"  - {t['task']}")
            print(f"    Owner: {t['owner']['name']}")
            print(f"    Deadline: {t['deadline']}")

    if result["escalated_tasks"]:
        print("\nESCALATED:")
        for t in result["escalated_tasks"]:
            print(f"  - {t['task']}")
            print(f"    Reason: {t['decision_reason']}")
            if t.get("options"):
                for o in t["options"]:
                    print(f"    Option: {o['name']} ({o['role']})")

    if result["human_required"]:
        print("\nHUMAN ACTION NEEDED:")
        for h in result["human_required"]:
            print(f"  - Step: {h['step']}")
            print(f"    Action: {h['action_needed']}")

    if result.get("pattern_memory_snapshot"):
        print("\nPATTERN MEMORY:")
        for k, v in result["pattern_memory_snapshot"].items():
            print(f"  - {k}: {v['attempts']} attempts, "
                  f"{v['success_rate']} success, "
                  f"will_retry={v['will_retry']}")

    if result.get("trace"):
        print("\nTRACE LOG:")
        for t in result["trace"]:
            print(f"  [{t['agent']}] {t['action']} "
                  f"→ {t['outcome']} | {t['decision']}")


# ─────────────────────────────────────────
# TEST 1 — Normal working case
# Everything should work perfectly
# 3 assigned, 2 escalated (both Rahuls)
# ─────────────────────────────────────────
print_separator("NORMAL CASE — everything works")

notes1 = """Product sync 18 March 2024.
Priya needs to update the marketing deck with new pricing by this friday.
Rahul should fix the API timeout issue before end of next week.
Neha to get budget approval for Singapore office.
Arjun will coordinate timezone scheduling before month end.
Rahul to check CRM migration status by wednesday."""

result1 = run_meeting_agent(notes1)
print_result(result1)


# ─────────────────────────────────────────
# TEST 2 — Empty notes
# Intake agent should catch this immediately
# No AI called, no cost, instant error
# ─────────────────────────────────────────
print_separator("EMPTY NOTES — intake should catch")

result2 = run_meeting_agent("")
print_result(result2)


# ─────────────────────────────────────────
# TEST 3 — Too short notes
# Only 5 words — below minimum of 15
# ─────────────────────────────────────────
print_separator("TOO SHORT — only 5 words")

result3 = run_meeting_agent("Rahul fix the bug")
print_result(result3)


# ─────────────────────────────────────────
# TEST 4 — Nobody in notes matches team
# All owners will be not_found
# All tasks escalate, 0% autonomy
# ─────────────────────────────────────────
print_separator("UNKNOWN PEOPLE — no matches in team")

notes4 = """Team meeting 18 March 2024.
John needs to prepare the quarterly report by next monday.
Sarah should contact the client about the delay before friday.
Michael to review the contract and send feedback by wednesday.
Jessica will handle the social media campaign starting next week.
Robert to organize the team building event before month end."""

result4 = run_meeting_agent(notes4)
print_result(result4)


# ─────────────────────────────────────────
# TEST 5 — All tasks to one person
# Arjun gets everything
# Should all be assigned — 100% autonomy
# ─────────────────────────────────────────
print_separator("ALL TASKS TO ONE PERSON — 100% autonomy")

notes5 = """Quick sync 18 March 2024.
Arjun needs to write the product roadmap by friday.
Arjun should review all pull requests before end of week.
Arjun to present the demo to the client next monday.
Arjun will set up the new staging environment this week."""

result5 = run_meeting_agent(notes5)
print_result(result5)


# ─────────────────────────────────────────
# TEST 6 — Mixed known and unknown people
# Some resolve, some do not
# Partial autonomy
# ─────────────────────────────────────────
print_separator("MIXED — some known, some unknown")

notes6 = """Sprint planning 18 March 2024.
Priya to finalize the design mockups by thursday.
James should set up the CI CD pipeline before friday.
Neha to process all pending invoices by end of week.
David will coordinate with the external vendor next week.
Arjun to write unit tests for the new feature by wednesday."""

result6 = run_meeting_agent(notes6)
print_result(result6)


# ─────────────────────────────────────────
# TEST 7 — Pattern memory check
# Run test 1 again and check if pattern
# memory has updated from all previous runs
# ─────────────────────────────────────────
print_separator("PATTERN MEMORY — check after all tests")

print("\nCurrent pattern memory state:")
for error_type, data in pattern_memory.items():
    if data["attempts"] > 0:
        rate = data["successes"] / data["attempts"] * 100
        print(f"  {error_type}:")
        print(f"    attempts  = {data['attempts']}")
        print(f"    successes = {data['successes']}")
        print(f"    rate      = {round(rate)}%")


# ─────────────────────────────────────────
# TEST 8 — No deadlines mentioned
# Agent should handle "not specified" cleanly
# ─────────────────────────────────────────
print_separator("NO DEADLINES — all open ended")

notes8 = """Casual team catch up.
Priya should look into the new marketing tools available.
Neha to review the budget spreadsheet when she gets a chance.
Arjun will think about the product roadmap for next quarter.
Rahul to explore options for improving the API performance."""

result8 = run_meeting_agent(notes8)
print_result(result8)


# ─────────────────────────────────────────
# TEST 9 — High priority emergency meeting
# Multiple urgent tasks, tight deadlines
# ─────────────────────────────────────────
print_separator("EMERGENCY MEETING — all urgent")

notes9 = """Emergency sync 18 March 2024. Production is down.
Rahul must fix the database connection issue immediately.
Priya needs to send a status update to all clients right now.
Arjun should roll back the last deployment within the hour.
Neha to contact AWS support urgently about the outage."""

result9 = run_meeting_agent(notes9)
print_result(result9)


print("\n" + "="*50)
print("  ALL TESTS COMPLETE")
print("="*50)