import sqlite3, os

# Path to your database
db_path = os.path.join("instance", "eleva.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

print(f"🔍 Checking database at: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("PRAGMA table_info(form_schema)")
cols = [r[1] for r in cur.fetchall()]

added = []
if "stage" not in cols:
    cur.execute("ALTER TABLE form_schema ADD COLUMN stage TEXT;")
    added.append("stage")
if "lift_type" not in cols:
    cur.execute("ALTER TABLE form_schema ADD COLUMN lift_type TEXT;")
    added.append("lift_type")

conn.commit()
conn.close()

if added:
    print(f"✅ Added missing columns: {', '.join(added)}")
else:
    print("✔️ All columns already exist. No action needed.")

print("🎉 Done! Now run: python app.py")
