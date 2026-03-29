"""
Module 6.3 — Email Sender
Sends the morning briefing via Gmail SMTP.
No billing. Uses Gmail App Password — completely free.

Setup (one time):
  1. Go to myaccount.google.com → Security → 2-Step Verification → turn ON
  2. Then go to → App passwords → create one called "auditpilot"
  3. Copy the 16-char password into your .env file
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv   #type: ignore

load_dotenv()

# ── DB import ─────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection

# ── Config — reads from .env ──────────────────────────────────
GMAIL_SENDER       = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
BRIEFING_RECIPIENT = os.getenv("BRIEFING_RECIPIENT", "")


def send_briefing_email(briefing_result: dict) -> dict:
    """
    Takes the dict returned by briefing_generator.generate_briefing()
    Sends it as a plain-text email via Gmail SMTP.

    Returns:
    { "status": "sent" | "failed", "to": "...", "reason": "..." }
    """

    # ── Validate config ───────────────────────────────────────
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        return {
            "status": "failed",
            "reason": "GMAIL_SENDER or GMAIL_APP_PASSWORD not set in .env"
        }

    recipient = BRIEFING_RECIPIENT or GMAIL_SENDER  # send to self if not set

    # ── Build subject ─────────────────────────────────────────
    n = briefing_result.get("needs_action_count", 0)
    date_str = datetime.now().strftime("%d %b %Y")

    if n == 0:
        subject = f"AuditPilot morning briefing — {date_str} — all clear ✓"
    else:
        subject = f"AuditPilot morning briefing — {date_str} — {n} item{'s' if n > 1 else ''} need your attention"

    # ── Build body ────────────────────────────────────────────
    body = briefing_result.get("briefing_text", "No briefing generated.")
    body += f"\n\n{'─' * 50}"
    body += f"\nGenerated : {briefing_result.get('generated_at', '')}"
    body += f"\nWorkflows : {briefing_result.get('workflow_count', 0)}"
    body += f"\n\n— AuditPilot  |  http://localhost:8000"

    # ── Build email ───────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # ── Send ──────────────────────────────────────────────────
    print(f"[email_sender] Connecting to Gmail SMTP...")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, [recipient], msg.as_string())

        print(f"[email_sender] ✓ Sent to {recipient}")
        print(f"[email_sender] Subject: {subject}")

        # ── Log to briefing_log table ─────────────────────────
        try:
            conn = get_connection()
            conn.execute("""
                INSERT INTO briefing_log
                    (briefing_date, items_count, email_sent, content)
                VALUES (?, ?, 1, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d"),
                briefing_result.get("needs_action_count", 0),
                briefing_result.get("briefing_text", "")
            ))
            conn.commit()
            conn.close()
            print(f"[email_sender] Logged to briefing_log")
        except Exception as e:
            print(f"[email_sender] Warning: could not log to briefing_log — {e}")

        return {
            "status":  "sent",
            "to":      recipient,
            "subject": subject
        }

    except smtplib.SMTPAuthenticationError:
        reason = "Gmail auth failed. Check GMAIL_SENDER and GMAIL_APP_PASSWORD in .env"
        print(f"[email_sender] ✗ {reason}")
        return {"status": "failed", "reason": reason}

    except smtplib.SMTPException as e:
        reason = f"SMTP error: {str(e)}"
        print(f"[email_sender] ✗ {reason}")
        return {"status": "failed", "reason": reason}

    except Exception as e:
        reason = f"Unexpected error: {str(e)}"
        print(f"[email_sender] ✗ {reason}")
        return {"status": "failed", "reason": reason}


# Quick test — run directly
if __name__ == "__main__":
    from briefing_generator import generate_briefing

    sample_traces = [
        {
            "workflow_id": "wf_meeting_001",
            "agent": "intake_agent",
            "action": "validate_input",
            "outcome": "success",
            "decision": "continue",
            "reason": "42 words — validation passed"
        },
        {
            "workflow_id": "wf_meeting_001",
            "agent": "owner_resolution",
            "action": "resolve_Rahul",
            "outcome": "ambiguous",
            "decision": "human_required",
            "reason": "Multiple matches: Rahul Sharma, Rahul Verma"
        }
    ]

    briefing = generate_briefing(sample_traces)
    result   = send_briefing_email(briefing)

    print(f"\n── Email Result ─────────────────────────────")
    print(f"Status  : {result['status']}")
    print(f"To      : {result.get('to', '-')}")
    print(f"Subject : {result.get('subject', '-')}")
    if result.get("reason"):
        print(f"Reason  : {result['reason']}")