from database import get_connection

conn = get_connection()

traces = conn.execute('SELECT COUNT(*) FROM traces').fetchone()[0]
tasks = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]

print(f"Traces saved : {traces}")
print(f"Tasks saved  : {tasks}")

print("\n--- Sample traces ---")
rows = conn.execute('SELECT workflow_id, agent, status, decision FROM traces LIMIT 6').fetchall()
for r in rows:
    print(f"  {r[0]} | {r[1]} | {r[2]} | {r[3]}")

print("\n--- Sample tasks ---")
rows = conn.execute('SELECT workflow_id, owner_name, title, status FROM tasks LIMIT 6').fetchall()
for r in rows:
    print(f"  {r[0]} | {r[1]} | {r[3]} | {r[2][:40]}")

conn.close()