from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask import current_app as app
import sqlite3, os, datetime

qc_bp = Blueprint("qc", __name__, template_folder="templates")

DB_PATH = None

def _db_path():
    global DB_PATH
    if DB_PATH:
        return DB_PATH
    # Put SQLite inside instance/ if available, else project root
    inst = getattr(app, "instance_path", os.getcwd())
    os.makedirs(inst, exist_ok=True)
    DB_PATH = os.path.join(inst, "eleva_qc.db")
    return DB_PATH

def init_qc_db():
    """Create tables if not present."""
    path = _db_path()
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qc_form_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            form_name TEXT NOT NULL,
            stage TEXT NOT NULL,
            lift_type TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@qc_bp.before_app_request
def _ensure_db():
    init_qc_db()

@qc_bp.route("/forms/new", methods=["GET", "POST"])
def forms_new():
    """Create a new QC form profile. This does not conflict with your existing forms;
    it stores profile rows in qc_form_profiles (SQLite)."""
    if request.method == "POST":
        form_name = request.form.get("form_name", "").strip() or "QC - New form"
        stage = request.form.get("stage", "").strip()
        lift_type = request.form.get("lift_type", "").strip()
        created_by = getattr(getattr(request, "session", {}), "get", lambda k, d=None: d)("user") if hasattr(request, "session") else None
        created_at = datetime.datetime.utcnow().isoformat(timespec="seconds")

        if not stage or not lift_type:
            flash("Please select both Stage and Lift Type.", "error")
            return render_template("forms_new.html", stage=stage, lift_type=lift_type, form_name=form_name)

        conn = sqlite3.connect(_db_path())
        c = conn.cursor()
        c.execute("""
            INSERT INTO qc_form_profiles (form_name, stage, lift_type, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (form_name, stage, lift_type, created_by, created_at))
        conn.commit()
        conn.close()

        flash("QC form profile saved.", "success")
        # Redirect to a list page if you have one; otherwise go back to dashboard
        try:
            return redirect(url_for("qc_settings", tab="templates"))
        except Exception:
            return redirect(url_for("dashboard"))

    return render_template("forms_new.html")
