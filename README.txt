# Eleva ERP Starter (Flask + HTMX)

### What you get
- Python Flask app with auto-reload (`flask run --debug`)
- Simple login (user1/pass, user2/pass, admin/admin)
- Dynamic forms/checklist builder (edit schema in the UI, no code)
- QC form demo with photo/video upload rules
- TailwindCSS (CDN) + HTMX + Alpine for fast, animated UI
- SQLite database (file in `instance/eleva.db`)

### How to run (Windows + XAMPP or anywhere)
1) Install Python 3.10+
2) Open terminal in this folder and run:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
flask run --debug
```
3) Open http://127.0.0.1:5000

**Auto-reload**: Any change in `.py` or `templates/` will reload the server/browser.

### Deploying on GoDaddy (quick notes)
- If you're on shared hosting: prefer a GoDaddy Linux plan with Python/Passenger support. You can run Flask via WSGI.
- Or choose a GoDaddy VPS (recommended for Python). Install Python, set up `gunicorn` + `nginx` or use Passenger on cPanel.
- Use MySQL in production (already available on GoDaddy); change `SQLALCHEMY_DATABASE_URI` accordingly.

### Next steps (recommended)
- Add role-based permissions (admin vs inspector)
- Add Projects/NI modules and tie submissions to a Project
- Move media to object storage later (S3 compatible like Wasabi)
- Add audit trail and export to CSV/PDF
- Replace plaintext passwords with hashing before go-live

### Editing forms
- Go to Dashboard → Forms → Edit. Change the JSON to add your own fields.
- For dropdown checks, use `"type":"select","options":["Good","NG"]` and set `"photo_required_if_ng": true` where needed.
