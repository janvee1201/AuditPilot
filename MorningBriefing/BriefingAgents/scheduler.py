




"""
Module 6.4 — Scheduler
Runs the full briefing pipeline (generate + email) on a daily cron.
Also exposes a manual trigger function for the demo button.
No billing. APScheduler is completely free.
"""

import sys
import os

# So Python finds briefing_generator and email_sender in the same folder
sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.background import BackgroundScheduler   #type: ignore
from apscheduler.triggers.cron import CronTrigger #type: ignore
from briefing_generator import generate_briefing, get_traces_from_db
from email_sender import send_briefing_email
from datetime import datetime
import time

# ── Single shared scheduler instance ─────────────────────────
_scheduler = BackgroundScheduler()


# ── The core job ──────────────────────────────────────────────
def run_briefing_job(traces: list = None) -> dict:
    """
    Generates briefing and sends email.
    If traces not passed, pulls last 8 hours from DB automatically.
    Pass traces explicitly only for testing.
    """
    print(f"\n[scheduler] Briefing job started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Pull from DB if no traces passed — this is what runs every morning
    if traces is None:
        traces = get_traces_from_db(hours=8)
        print(f"[scheduler] Pulled {len(traces)} traces from DB")

        # If DB is empty (e.g. demo day, no overnight runs) use a
        # clear message instead of confusing empty briefing
        if not traces:
            print("[scheduler] No overnight traces found — sending standby briefing")

    # Step 1 — Generate briefing
    briefing = generate_briefing(traces)
    print(f"[scheduler] Briefing generated — {briefing['workflow_count']} workflows, "
          f"{briefing['needs_action_count']} need action")

    # Step 2 — Send email
    email_result = send_briefing_email(briefing)
    print(f"[scheduler] Email — status={email_result['status']}")

    return {
        "briefing_text":      briefing["briefing_text"],
        "workflow_count":     briefing["workflow_count"],
        "needs_action_count": briefing["needs_action_count"],
        "generated_at":       briefing["generated_at"],
        "email_status":       email_result["status"],
        "email_to":           email_result.get("to", ""),
        "email_reason":       email_result.get("reason", "")
    }


# ── Scheduler lifecycle ───────────────────────────────────────
def start_scheduler():
    if _scheduler.running:
        print("[scheduler] Already running")
        return

    _scheduler.add_job(
        run_briefing_job,
        trigger=CronTrigger(hour=8, minute=45),
        id="morning_briefing",
        name="AuditPilot morning briefing",
        replace_existing=True
    )

    _scheduler.start()
    print("[scheduler] ✓ Started — briefing runs daily at 08:45")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped")


# ── Quick test — run directly ─────────────────────────────────
if __name__ == "__main__":
    print("── Manual trigger test (pulls from DB) ──────────────")
    result = run_briefing_job()  # no traces = pulls from DB automatically

    print(f"\n── Result ───────────────────────────────────────────")
    print(f"Workflows     : {result['workflow_count']}")
    print(f"Needs action  : {result['needs_action_count']}")
    print(f"Generated at  : {result['generated_at']}")
    print(f"Email status  : {result['email_status']}")
    if result["email_reason"]:
        print(f"Email reason  : {result['email_reason']}")
    print(f"\n── Briefing text ────────────────────────────────────")
    print(result["briefing_text"])

    # Test the scheduler starts without crashing
    print(f"\n── Scheduler start test ─────────────────────────────")
    start_scheduler()
    print("[test] Scheduler is running:", _scheduler.running)
    time.sleep(2)
    stop_scheduler()
    print("[test] Scheduler stopped cleanly")