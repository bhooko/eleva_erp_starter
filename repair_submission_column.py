import sqlite3, os

db_path = os.path.join("instance", "eleva.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

print(f"🔍 Checking database at: {db_path}")

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check columns in the submission table
cur.execute("PRAGMA table_info(submission)")
cols = [r[1] for r in cur.fetchall()]

if "work_id" not in cols:
    cur.execute("ALTER TABLE submission ADD COLUMN work_id INTEGER;")
    conn.commit()
    print("✅ Added column 'work_id' to 'submission' table.")
else:
    print("✔️ Column 'work_id' already exists.")

conn.close()
print("🎉 Done! You can now restart your Flask app.")
