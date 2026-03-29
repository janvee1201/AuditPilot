from database import get_connection

conn = get_connection()

columns_to_add = [
    ("workflow_type", "TEXT"),
    ("step_id", "TEXT"),
    ("input_data", "TEXT"),
    ("output_data", "TEXT"),
    ("error_hash", "TEXT"),
    ("error_type", "TEXT"),
]

for col_name, col_type in columns_to_add:
    try:
        conn.execute(f"ALTER TABLE traces ADD COLUMN {col_name} {col_type}")
        conn.commit()
        print(f"[fix_db] Added column: {col_name}")
    except Exception as e:
        print(f"[fix_db] Skipped {col_name} — {e}")

conn.close()
print("[fix_db] Done — run test_meeting.py now")