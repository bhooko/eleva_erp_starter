from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.utils import secure_filename
import os, json, datetime, sqlite3, threading

from sqlalchemy import case, inspect, func, or_
from sqlalchemy.exc import OperationalError

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = "dev-eleva-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "eleva.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB uploads

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------------- QC Profile choices (visible in UI) ----------------------
STAGES = [
    "Template QC", "Stage 1", "Stage 2", "Stage 3",
    "Completion", "Completion QC", "Structure", "Cladding", "Service", "Repair", "Material"
]
PROJECT_CORE_STAGES = ["Template QC", "Stage 1", "Stage 2", "Stage 3", "Completion QC"]
LIFT_TYPES = ["Hydraulic", "MRL", "MR", "Dumbwaiter", "Goods"]
# -------------------------------------------------------------------------------


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    department = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(120), nullable=True)
    mobile_number = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    display_picture = db.Column(db.String(255), nullable=True)

    @property
    def display_name(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.username

    @property
    def is_admin(self):
        role = (self.role or "").strip().lower()
        return role == "admin" or self.username.lower() == "admin"


class Project(db.Model):
    __tablename__ = "project"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    site_name = db.Column(db.String(200), nullable=True)
    site_address = db.Column(db.Text, nullable=True)
    customer_name = db.Column(db.String(200), nullable=True)
    lift_type = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class FormSchema(db.Model):
    __tablename__ = "form_schema"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    min_photos_if_all_good = db.Column(db.Integer, default=3)

    # NEW
    stage = db.Column(db.String(40), nullable=True)      # e.g., "Stage 1", "Completion", etc.
    lift_type = db.Column(db.String(40), nullable=True)  # e.g., "MRL", "Hydraulic", etc.


class Submission(db.Model):
    __tablename__ = "submission"
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("form_schema.id"), nullable=False)
    submitted_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    data_json = db.Column(db.Text, nullable=False, default="{}")
    photos_json = db.Column(db.Text, nullable=False, default="[]")
    videos_json = db.Column(db.Text, nullable=False, default="[]")

    # Optional link to a QC work item (created in /qc tab). Safe-migrated.
    work_id = db.Column(db.Integer, nullable=True)

    form = db.relationship("FormSchema")
    user = db.relationship("User")


# NEW: QC Work table (simple tracker for “create work for new site QC”)
class QCWork(db.Model):
    __tablename__ = "qc_work"
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(200), nullable=False)
    client_name = db.Column(db.String(200), nullable=True)
    address = db.Column(db.Text, nullable=True)

    template_id = db.Column(db.Integer, db.ForeignKey("form_schema.id"), nullable=False)
    stage = db.Column(db.String(40), nullable=True)
    lift_type = db.Column(db.String(40), nullable=True)

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)

    status = db.Column(db.String(40), default="Open")  # Open / In Progress / Closed
    due_date = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    template = db.relationship("FormSchema")
    creator = db.relationship("User", foreign_keys=[created_by])
    assignee = db.relationship("User", foreign_keys=[assigned_to])
    project = db.relationship("Project", backref=db.backref("tasks", lazy="dynamic"))


class QCWorkComment(db.Model):
    __tablename__ = "qc_work_comment"
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("qc_work.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    attachments_json = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    work = db.relationship("QCWork", backref=db.backref("comments", cascade="all, delete-orphan"))
    author = db.relationship("User")


class QCWorkLog(db.Model):
    __tablename__ = "qc_work_log"
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("qc_work.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    from_status = db.Column(db.String(40), nullable=True)
    to_status = db.Column(db.String(40), nullable=True)
    details_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    work = db.relationship("QCWork", backref=db.backref("logs", cascade="all, delete-orphan"))
    actor = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


ALLOWED_PHOTO = {"png", "jpg", "jpeg", "webp"}
ALLOWED_VIDEO = {"mp4", "mov", "avi", "mkv"}
ALLOWED_ATTACHMENTS = ALLOWED_PHOTO.union(ALLOWED_VIDEO).union({"pdf", "doc", "docx", "xls", "xlsx"})

def allowed_file(filename, kind="photo"):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    if kind == "photo":
        return ext in ALLOWED_PHOTO
    if kind == "video":
        return ext in ALLOWED_VIDEO
    return ext in ALLOWED_ATTACHMENTS


def log_work_event(work_id, action, actor_id=None, from_status=None, to_status=None, details=None):
    entry = QCWorkLog(
        work_id=work_id,
        actor_id=actor_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        details_json=json.dumps(details or {}, ensure_ascii=False)
    )
    db.session.add(entry)


# ---------------------- SAFE DB REPAIR / MIGRATIONS ----------------------
def ensure_qc_columns():
    """Check and auto-add 'stage' and 'lift_type' in form_schema, and 'work_id' in submission."""
    db_path = os.path.join("instance", "eleva.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # form_schema
    cur.execute("PRAGMA table_info(form_schema)")
    fs_cols = [r[1] for r in cur.fetchall()]
    added_fs = []
    if "stage" not in fs_cols:
        cur.execute("ALTER TABLE form_schema ADD COLUMN stage TEXT;")
        added_fs.append("stage")
    if "lift_type" not in fs_cols:
        cur.execute("ALTER TABLE form_schema ADD COLUMN lift_type TEXT;")
        added_fs.append("lift_type")

    # submission
    cur.execute("PRAGMA table_info(submission)")
    sub_cols = [r[1] for r in cur.fetchall()]
    added_sub = []
    if "work_id" not in sub_cols:
        cur.execute("ALTER TABLE submission ADD COLUMN work_id INTEGER;")
        added_sub.append("work_id")

    # user profile additions
    cur.execute("PRAGMA table_info(user)")
    user_cols = [r[1] for r in cur.fetchall()]
    added_user = []
    user_column_defs = {
        "first_name": "TEXT",
        "last_name": "TEXT",
        "department": "TEXT",
        "role": "TEXT",
        "mobile_number": "TEXT",
        "email": "TEXT",
        "display_picture": "TEXT"
    }
    for col, col_type in user_column_defs.items():
        if col not in user_cols:
            cur.execute(f"ALTER TABLE user ADD COLUMN {col} {col_type};")
            added_user.append(col)

    # qc_work (only attempt to alter when table exists)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='qc_work'")
    qc_exists = cur.fetchone() is not None
    added_qc = []
    if qc_exists:
        cur.execute("PRAGMA table_info(qc_work)")
        qc_cols = [r[1] for r in cur.fetchall()]
        if "assigned_to" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN assigned_to INTEGER;")
            added_qc.append("assigned_to")
        if "project_id" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN project_id INTEGER;")
            added_qc.append("project_id")

    conn.commit()
    conn.close()

    if added_fs:
        print(f"✅ Auto-added in form_schema: {', '.join(added_fs)}")
    else:
        print("✔️ form_schema OK")

    if added_sub:
        print(f"✅ Auto-added in submission: {', '.join(added_sub)}")
    else:
        print("✔️ submission OK")

    if added_user:
        print(f"✅ Auto-added in user: {', '.join(added_user)}")
    else:
        print("✔️ user OK")

    if qc_exists:
        if added_qc:
            print(f"✅ Auto-added in qc_work: {', '.join(added_qc)}")
        else:
            print("✔️ qc_work OK")
    else:
        print("ℹ️ qc_work table did not exist prior to ensure_qc_columns")


def ensure_tables():
    """Ensure all known tables exist. Creates them if missing."""
    created_tables = []
    inspector = inspect(db.engine)
    try:
        existing_tables = set(inspector.get_table_names())
    except OperationalError:
        # Database file might be missing – create all tables fresh.
        db.create_all()
        existing_tables = set(inspect(db.engine).get_table_names())

    models = [
        User.__table__,
        Project.__table__,
        FormSchema.__table__,
        Submission.__table__,
        QCWork.__table__,
        QCWorkComment.__table__,
        QCWorkLog.__table__,
    ]

    for table in models:
        if table.name not in existing_tables:
            table.create(bind=db.engine, checkfirst=True)
            created_tables.append(table.name)

    if created_tables:
        print(f"✅ Created missing tables: {', '.join(created_tables)}")


def bootstrap_db():
    ensure_tables()
    ensure_qc_columns()    # adds missing columns safely

    default_users = [("user1", "pass"), ("user2", "pass"), ("admin", "admin")]
    for u, p in default_users:
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p))

    admin_user = User.query.filter_by(username="admin").first()
    if admin_user and not admin_user.role:
        admin_user.role = "Admin"

    if not FormSchema.query.filter_by(name="QC - New Installation").first():
        sample_schema = [
            {"label": "Lift Cabin Condition", "type": "select", "required": True, "options": ["Good", "NG"], "photo_required_if_ng": True},
            {"label": "Machine Room Cleanliness", "type": "select", "required": True, "options": ["Good", "NG"], "photo_required_if_ng": True},
            {"label": "Lift Shaft Obstruction", "type": "select", "required": True, "options": ["Good", "NG"], "photo_required_if_ng": True},
            {"label": "General Remarks", "type": "textarea", "required": False},
        ]
        fs = FormSchema(
            name="QC - New Installation",
            schema_json=json.dumps(sample_schema, ensure_ascii=False),
            min_photos_if_all_good=3,
            stage="Template QC",
            lift_type="MRL"
        )
        db.session.add(fs)

    db.session.commit()
# -----------------------------------------------------------------------


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html", category_label=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")
    return render_template("login.html", category_label=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        remove_avatar = request.form.get("remove_avatar") == "1"

        current_user.first_name = first_name or None
        current_user.last_name = last_name or None

        file = request.files.get("display_picture")
        if remove_avatar:
            current_user.display_picture = None
        elif file and file.filename:
            if not allowed_file(file.filename, kind="photo"):
                flash("Please upload a PNG, JPG, JPEG or WEBP image for the display picture.", "error")
                return redirect(url_for("profile"))
            fname = secure_filename(file.filename)
            dest_name = f"avatar_{current_user.id}_{int(datetime.datetime.utcnow().timestamp())}_{fname}"
            dest_path = os.path.join(app.config["UPLOAD_FOLDER"], dest_name)
            file.save(dest_path)
            rel_path = os.path.relpath(dest_path, "static") if dest_path.startswith("static") else os.path.join("uploads", dest_name)
            current_user.display_picture = rel_path.replace("\\", "/")

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html")


@app.route("/dashboard")
@login_required
def dashboard():
    viewing_user = current_user
    selected_user_id = request.args.get("user_id", type=int)
    if selected_user_id and current_user.is_admin:
        candidate = db.session.get(User, selected_user_id)
        if candidate:
            viewing_user = candidate

    status_order = case(
        (QCWork.status == "Open", 0),
        (QCWork.status == "In Progress", 1),
        (QCWork.status == "Closed", 2),
        else_=3
    )
    tasks = (
        QCWork.query
        .filter(QCWork.assigned_to == viewing_user.id)
        .order_by(status_order, QCWork.due_date.asc().nullslast(), QCWork.created_at.desc())
        .all()
    )
    counts = (
        db.session.query(
            func.coalesce(func.sum(case((QCWork.status == "Open", 1), else_=0)), 0),
            func.coalesce(func.sum(case((QCWork.status == "In Progress", 1), else_=0)), 0)
        )
        .filter(QCWork.assigned_to == viewing_user.id)
        .one()
    )
    open_count, in_progress_count = [int(c or 0) for c in counts]

    team_load = []
    if current_user.is_admin:
        rows = (
            db.session.query(
                User,
                func.coalesce(func.count(QCWork.id), 0).label("total"),
                func.coalesce(func.sum(case((QCWork.status == "Open", 1), else_=0)), 0).label("open"),
                func.coalesce(func.sum(case((QCWork.status == "In Progress", 1), else_=0)), 0).label("in_progress")
            )
            .outerjoin(QCWork, QCWork.assigned_to == User.id)
            .group_by(User.id)
            .order_by(User.username.asc())
            .all()
        )
        team_load = [
            {
                "user": member,
                "total": int(total or 0),
                "open": int(open_tasks or 0),
                "in_progress": int(progress or 0)
            }
            for member, total, open_tasks, progress in rows
        ]

    return render_template(
        "dashboard.html",
        tasks=tasks,
        open_count=open_count,
        in_progress_count=in_progress_count,
        viewing_user=viewing_user,
        team_load=team_load,
        category_label=None
    )


# ---------------------- FORMS (TEMPLATES) ----------------------
@app.route("/forms")
@login_required
def forms_list():
    forms = FormSchema.query.order_by(FormSchema.name.asc()).all()
    return render_template("forms_list.html", forms=forms, category_label="Forms", category_url=url_for('forms_list'))


@app.route("/forms/new", methods=["GET", "POST"])
@login_required
def forms_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        stage = (request.form.get("stage") or "").strip()
        lift_type = (request.form.get("lift_type") or "").strip()
        min_photos = int(request.form.get("min_photos", 3))
        try:
            schema = json.loads(request.form.get("schema_json", "[]"))
        except Exception:
            flash("Invalid JSON schema", "error")
            return render_template("forms_edit.html", item=None, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))

        if not name:
            flash("Name is required", "error")
            return render_template("forms_edit.html", item=None, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))

        if stage and stage not in STAGES:
            flash("Select a valid Stage.", "error")
            return render_template("forms_edit.html", item=None, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))
        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid Lift Type.", "error")
            return render_template("forms_edit.html", item=None, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))

        item = FormSchema(
            name=name,
            schema_json=json.dumps(schema, ensure_ascii=False),
            min_photos_if_all_good=min_photos,
            stage=stage or None,
            lift_type=lift_type or None
        )
        db.session.add(item)
        db.session.commit()
        flash("Form created", "success")
        return redirect(url_for("forms_list"))

    return render_template("forms_edit.html", item=None, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                           category_label="Forms", category_url=url_for('forms_list'))


@app.route("/forms/<int:form_id>/edit", methods=["GET", "POST"])
@login_required
def forms_edit(form_id):
    item = db.session.get(FormSchema, form_id)
    if not item:
        flash("Form not found", "error")
        return redirect(url_for("forms_list"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        stage = (request.form.get("stage") or "").strip()
        lift_type = (request.form.get("lift_type") or "").strip()
        min_photos = int(request.form.get("min_photos", 3))
        try:
            schema = json.loads(request.form.get("schema_json", "[]"))
        except Exception:
            flash("Invalid JSON schema", "error")
            return render_template("forms_edit.html", item=item, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))

        if name:
            item.name = name
        item.min_photos_if_all_good = min_photos
        item.schema_json = json.dumps(schema, ensure_ascii=False)

        if stage and stage not in STAGES:
            flash("Select a valid Stage.", "error")
            return render_template("forms_edit.html", item=item, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))
        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid Lift Type.", "error")
            return render_template("forms_edit.html", item=item, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                                   category_label="Forms", category_url=url_for('forms_list'))

        item.stage = stage or None
        item.lift_type = lift_type or None

        db.session.commit()
        flash("Form updated", "success")
        return redirect(url_for("forms_list"))

    return render_template("forms_edit.html", item=item, STAGES=STAGES, LIFT_TYPES=LIFT_TYPES,
                           category_label="Forms", category_url=url_for('forms_list'))


@app.route("/forms/<int:form_id>/delete", methods=["POST"])
@login_required
def forms_delete(form_id):
    item = db.session.get(FormSchema, form_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Form deleted", "info")
    return redirect(url_for("forms_list"))


@app.route("/forms/<int:form_id>/fill", methods=["GET", "POST"])
@login_required
def forms_fill(form_id):
    fs = db.session.get(FormSchema, form_id)
    if not fs:
        flash("Form not found", "error")
        return redirect(url_for("forms_list"))

    schema = json.loads(fs.schema_json)
    if request.method == "POST":
        values = {}
        any_ng = False
        for field in schema:
            label = field.get("label")
            ftype = field.get("type")
            required = field.get("required", False)
            if ftype in ["text", "textarea"]:
                val = request.form.get(label, "").strip()
                if required and not val:
                    flash(f"'{label}' is required", "error")
                    return render_template("form_render.html", fs=fs, schema=schema, category_label="Forms", category_url=url_for('forms_list'), subcategory_label=fs.name)
                values[label] = val
            elif ftype == "select":
                val = request.form.get(label, "")
                if required and not val:
                    flash(f"'{label}' is required", "error")
                    return render_template("form_render.html", fs=fs, schema=schema, category_label="Forms", category_url=url_for('forms_list'), subcategory_label=fs.name)
                values[label] = val
                if val == "NG":
                    any_ng = True

        photo_files = request.files.getlist("photos")
        video_files = request.files.getlist("videos")
        saved_photos, saved_videos = [], []

        if any_ng:
            has_valid_photo = any((p and p.filename and "." in p.filename and p.filename.rsplit(".",1)[1].lower() in {"png","jpg","jpeg","webp"}) for p in photo_files)
            if not has_valid_photo:
                flash("At least one photo is required when any item is marked NG.", "error")
                return render_template("form_render.html", fs=fs, schema=schema, category_label="Forms", category_url=url_for('forms_list'), subcategory_label=fs.name)
        else:
            valid_photos = [p for p in photo_files if p and p.filename and "." in p.filename and p.filename.rsplit(".",1)[1].lower() in {"png","jpg","jpeg","webp"}]
            if len(valid_photos) < fs.min_photos_if_all_good:
                flash(f"At least {fs.min_photos_if_all_good} photos are required (cabin, machine room, shaft).", "error")
                return render_template("form_render.html", fs=fs, schema=schema, category_label="Forms", category_url=url_for('forms_list'), subcategory_label=fs.name)

        for f in photo_files:
            if f and f.filename:
                ext = f.filename.rsplit(".",1)[1].lower() if "." in f.filename else ""
                if ext in {"png","jpg","jpeg","webp"}:
                    fname = secure_filename(f.filename)
                    dest = os.path.join(app.config["UPLOAD_FOLDER"], f"{datetime.datetime.utcnow().timestamp()}_{fname}")
                    f.save(dest)
                    saved_photos.append(dest)

        for f in video_files:
            if f and f.filename:
                ext = f.filename.rsplit(".",1)[1].lower() if "." in f.filename else ""
                if ext in {"mp4","mov","avi","mkv"}:
                    fname = secure_filename(f.filename)
                    dest = os.path.join(app.config["UPLOAD_FOLDER"], f"{datetime.datetime.utcnow().timestamp()}_{fname}")
                    f.save(dest)
                    saved_videos.append(dest)

        linked_work_id = request.args.get("work_id", type=int)
        sub = Submission(
            form_id=fs.id,
            submitted_by=current_user.id,
            data_json=json.dumps(values, ensure_ascii=False),
            photos_json=json.dumps(saved_photos, ensure_ascii=False),
            videos_json=json.dumps(saved_videos, ensure_ascii=False),
            work_id=linked_work_id
        )
        db.session.add(sub)
        db.session.commit()
        if linked_work_id:
            log_work_event(
                linked_work_id,
                "submission_created",
                actor_id=current_user.id,
                details={"submission_id": sub.id}
            )
            db.session.commit()
        flash("Submitted successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("form_render.html", fs=fs, schema=schema,
                           category_label="Forms", category_url=url_for('forms_list'), subcategory_label=fs.name)


@app.route("/submissions/<int:sub_id>")
@login_required
def submission_view(sub_id):
    sub = db.session.get(Submission, sub_id)
    if not sub:
        flash("Submission not found", "error")
        return redirect(url_for("dashboard"))
    data = json.loads(sub.data_json or "{}")
    photos = json.loads(sub.photos_json or "[]")
    videos = json.loads(sub.videos_json or "[]")
    return render_template("submission_view.html", sub=sub, data=data, photos=photos, videos=videos,
                           category_label="Dashboard", category_url=url_for('dashboard'),
                           subcategory_label=f"Submission #{sub.id}", subcategory_url=None)


# ---------------------- PROJECTS ----------------------
@app.route("/projects", methods=["GET", "POST"])
@login_required
def projects_list():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        site_name = (request.form.get("site_name") or "").strip()
        site_address = (request.form.get("site_address") or "").strip()
        customer_name = (request.form.get("customer_name") or "").strip()
        lift_type = (request.form.get("lift_type") or "").strip()

        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("projects_list"))

        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid lift type.", "error")
            return redirect(url_for("projects_list"))

        project = Project(
            name=name,
            site_name=site_name or None,
            site_address=site_address or None,
            customer_name=customer_name or None,
            lift_type=lift_type or None
        )
        db.session.add(project)
        db.session.commit()
        flash("Project created.", "success")
        return redirect(url_for("project_detail", project_id=project.id))

    projects = Project.query.order_by(Project.created_at.desc()).all()
    stats_rows = (
        db.session.query(
            QCWork.project_id,
            func.count(QCWork.id).label("total"),
            func.coalesce(func.sum(case((QCWork.status == "Open", 1), else_=0)), 0).label("open"),
            func.coalesce(func.sum(case((QCWork.status == "In Progress", 1), else_=0)), 0).label("in_progress"),
            func.coalesce(func.sum(case((QCWork.status == "Closed", 1), else_=0)), 0).label("closed")
        )
        .filter(QCWork.project_id.isnot(None))
        .group_by(QCWork.project_id)
        .all()
    )
    stats_map = {
        row.project_id: {
            "total": int(row.total or 0),
            "open": int(row.open or 0),
            "in_progress": int(row.in_progress or 0),
            "closed": int(row.closed or 0)
        }
        for row in stats_rows
    }
    return render_template(
        "projects.html",
        projects=projects,
        stats_map=stats_map,
        LIFT_TYPES=LIFT_TYPES
    )


@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    tasks_by_stage = {}
    for stage in PROJECT_CORE_STAGES:
        tasks_by_stage[stage] = (
            QCWork.query
            .filter(QCWork.project_id == project.id, QCWork.stage == stage)
            .order_by(QCWork.created_at.desc())
            .all()
        )

    stage_cards = []
    for stage in PROJECT_CORE_STAGES:
        stage_tasks = tasks_by_stage.get(stage, [])
        if not stage_tasks:
            status = "empty"
        else:
            unfinished = [t for t in stage_tasks if t.status != "Closed"]
            status = "completed" if not unfinished else "active"
        stage_cards.append({
            "name": stage,
            "tasks": stage_tasks,
            "status": status
        })

    other_tasks = (
        QCWork.query
        .filter(QCWork.project_id == project.id)
        .filter(or_(QCWork.stage.is_(None), ~QCWork.stage.in_(PROJECT_CORE_STAGES)))
        .order_by(QCWork.created_at.desc())
        .all()
    )
    templates = FormSchema.query.order_by(FormSchema.name.asc()).all()
    templates_by_stage = {
        stage: [t for t in templates if t.stage == stage]
        for stage in PROJECT_CORE_STAGES
    }
    users = User.query.order_by(User.username.asc()).all()
    return render_template(
        "project_detail.html",
        project=project,
        tasks_by_stage=tasks_by_stage,
        stage_cards=stage_cards,
        other_tasks=other_tasks,
        templates=templates,
        templates_by_stage=templates_by_stage,
        users=users,
        PROJECT_CORE_STAGES=PROJECT_CORE_STAGES,
        STAGES=STAGES,
        LIFT_TYPES=LIFT_TYPES
    )


@app.route("/projects/<int:project_id>/tasks/create", methods=["POST"])
@login_required
def project_task_create(project_id):
    project = Project.query.get_or_404(project_id)
    stage = (request.form.get("stage") or "").strip()
    template_id = request.form.get("template_id", type=int)
    assigned_to = request.form.get("assigned_to", type=int)
    due = (request.form.get("due_date") or "").strip()

    if stage not in PROJECT_CORE_STAGES:
        flash("Select one of the core project stages.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    template = db.session.get(FormSchema, template_id) if template_id else None
    if not template:
        template = (
            FormSchema.query
            .filter_by(stage=stage)
            .order_by(FormSchema.name.asc())
            .first()
        )
    if not template:
        flash("Choose a template for this stage.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    due_dt = None
    if due:
        try:
            due_dt = datetime.datetime.strptime(due, "%Y-%m-%d")
        except Exception:
            flash("Invalid due date format.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    work = QCWork(
        site_name=project.site_name or project.name,
        client_name=project.customer_name,
        address=project.site_address,
        template_id=template.id,
        stage=stage,
        lift_type=project.lift_type or template.lift_type,
        project_id=project.id,
        due_date=due_dt,
        created_by=current_user.id,
        assigned_to=assigned_to
    )
    db.session.add(work)
    db.session.flush()
    log_work_event(
        work.id,
        "created_from_project",
        actor_id=current_user.id,
        details={
            "project_id": project.id,
            "stage": stage,
            "assigned_to": assigned_to,
            "due_date": work.due_date.strftime("%Y-%m-%d") if work.due_date else None
        }
    )
    if assigned_to:
        log_work_event(
            work.id,
            "assigned",
            actor_id=current_user.id,
            details={"assigned_to": assigned_to}
        )
    db.session.commit()
    flash("QC task created for the project.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


# ---------------------- QC TABS ----------------------
@app.route("/qc")
@login_required
def qc_home():
    status = request.args.get("status", "all")
    status_order = case(
        (QCWork.status == "Open", 0),
        (QCWork.status == "In Progress", 1),
        (QCWork.status == "Closed", 2),
        else_=3
    )
    query = QCWork.query.order_by(
        status_order,
        QCWork.due_date.asc().nullslast(),
        QCWork.created_at.desc()
    )
    if status == "open":
        query = query.filter(QCWork.status != "Closed")
    elif status == "closed":
        query = query.filter(QCWork.status == "Closed")

    work_items = query.all()
    templates = FormSchema.query.order_by(FormSchema.name.asc()).all()
    users = User.query.order_by(User.username.asc()).all()
    projects = Project.query.order_by(Project.name.asc()).all()
    return render_template(
        "qc.html",
        work_items=work_items,
        templates=templates,
        users=users,
        projects=projects,
        STAGES=STAGES,
        LIFT_TYPES=LIFT_TYPES,
        status_filter=status
    )


@app.route("/qc/work/new", methods=["POST"])
@login_required
def qc_work_new():
    site_name = (request.form.get("site_name") or "").strip()
    client_name = (request.form.get("client_name") or "").strip()
    address = (request.form.get("address") or "").strip()
    template_id = request.form.get("template_id", type=int)
    stage = (request.form.get("stage") or "").strip()
    lift_type = (request.form.get("lift_type") or "").strip()
    due = (request.form.get("due_date") or "").strip()
    assigned_to = request.form.get("assigned_to", type=int)
    project_id = request.form.get("project_id", type=int)

    project = db.session.get(Project, project_id) if project_id else None
    if project:
        site_name = site_name or project.site_name or project.name
        client_name = client_name or (project.customer_name or "")
        address = address or (project.site_address or "")
        lift_type = lift_type or (project.lift_type or "")

    if not site_name or not template_id:
        flash("Site name and Template are required.", "error")
        return redirect(url_for("qc_home"))

    due_dt = None
    if due:
        try:
            due_dt = datetime.datetime.strptime(due, "%Y-%m-%d")
        except Exception:
            flash("Invalid due date format.", "error")
            return redirect(url_for("qc_home"))

    template = db.session.get(FormSchema, template_id)

    work = QCWork(
        site_name=site_name,
        client_name=client_name or None,
        address=address or None,
        template_id=template_id,
        stage=stage or (template.stage if template else None),
        lift_type=lift_type or (template.lift_type if template else None),
        project_id=project.id if project else None,
        due_date=due_dt,
        created_by=current_user.id,
        assigned_to=assigned_to
    )
    db.session.add(work)
    db.session.flush()
    log_work_event(
        work.id,
        "created",
        actor_id=current_user.id,
        details={
            "site_name": work.site_name,
            "assigned_to": assigned_to,
            "due_date": work.due_date.strftime("%Y-%m-%d") if work.due_date else None,
            "project_id": work.project_id
        }
    )
    if assigned_to:
        log_work_event(
            work.id,
            "assigned",
            actor_id=current_user.id,
            details={"assigned_to": assigned_to}
        )
    db.session.commit()
    flash("QC work created.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/qc/work/<int:work_id>")
@login_required
def qc_work_detail(work_id):
    work = QCWork.query.get_or_404(work_id)
    submissions = Submission.query.filter_by(work_id=work_id).order_by(Submission.created_at.desc()).all()
    for submission in submissions:
        try:
            submission.photo_count = len(json.loads(submission.photos_json or "[]"))
        except Exception:
            submission.photo_count = 0
        try:
            submission.video_count = len(json.loads(submission.videos_json or "[]"))
        except Exception:
            submission.video_count = 0
    users = User.query.order_by(User.username.asc()).all()
    comments = QCWorkComment.query.filter_by(work_id=work_id).order_by(QCWorkComment.created_at.asc()).all()
    for comment in comments:
        try:
            comment.attachments = json.loads(comment.attachments_json or "[]")
        except Exception:
            comment.attachments = []
    logs = QCWorkLog.query.filter_by(work_id=work_id).order_by(QCWorkLog.created_at.desc()).all()
    for log in logs:
        try:
            log.details = json.loads(log.details_json or "{}")
        except Exception:
            log.details = {}
        if isinstance(log.details, dict):
            if "assigned_to" in log.details:
                user_id = log.details.get("assigned_to")
                if user_id:
                    user_obj = db.session.get(User, user_id)
                    log.details["assigned_to"] = user_obj.username if user_obj else user_id
                else:
                    log.details["assigned_to"] = "Unassigned"
            if "from" in log.details:
                prev_id = log.details.get("from")
                if prev_id:
                    user_obj = db.session.get(User, prev_id)
                    log.details["from"] = user_obj.username if user_obj else prev_id
                elif prev_id is None:
                    log.details["from"] = "Unassigned"
            if "to" in log.details:
                next_id = log.details.get("to")
                if next_id:
                    user_obj = db.session.get(User, next_id)
                    log.details["to"] = user_obj.username if user_obj else next_id
                elif next_id is None:
                    log.details["to"] = "Unassigned"
    return render_template(
        "qc_work_detail.html",
        work=work,
        submissions=submissions,
        users=users,
        comments=comments,
        logs=logs
    )


@app.route("/qc/work/<int:work_id>/assign", methods=["POST"])
@login_required
def qc_work_assign(work_id):
    work = QCWork.query.get_or_404(work_id)
    assigned_to = request.form.get("assigned_to", type=int)
    previous = work.assigned_to
    work.assigned_to = assigned_to or None
    if previous != work.assigned_to:
        db.session.flush()
        log_work_event(
            work.id,
            "assignment_updated",
            actor_id=current_user.id,
            details={"from": previous, "to": work.assigned_to}
        )
        db.session.commit()
        flash("Assignment updated.", "success")
    else:
        db.session.rollback()
        flash("Assignment unchanged.", "info")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/qc/work/<int:work_id>/comment", methods=["POST"])
@login_required
def qc_work_comment(work_id):
    work = QCWork.query.get_or_404(work_id)
    body = (request.form.get("body") or "").strip()
    if not body and not request.files.getlist("attachments"):
        flash("Add a comment or attachment.", "error")
        return redirect(url_for("qc_work_detail", work_id=work.id))

    attachments = []
    for f in request.files.getlist("attachments"):
        if f and f.filename:
            if not allowed_file(f.filename, kind="attachment"):
                flash(f"Unsupported file type for {f.filename}.", "error")
                return redirect(url_for("qc_work_detail", work_id=work.id))
            fname = secure_filename(f.filename)
            dest_name = f"{datetime.datetime.utcnow().timestamp()}_{fname}"
            dest = os.path.join(app.config["UPLOAD_FOLDER"], dest_name)
            f.save(dest)
            rel_path = dest.split("static/", 1)[1] if "static/" in dest else dest
            attachments.append({"path": dest, "name": fname, "web_path": rel_path})

    comment = QCWorkComment(
        work_id=work.id,
        author_id=current_user.id,
        body=body,
        attachments_json=json.dumps(attachments, ensure_ascii=False)
    )
    db.session.add(comment)
    db.session.flush()
    log_work_event(
        work.id,
        "comment_added",
        actor_id=current_user.id,
        details={"comment_id": comment.id}
    )
    db.session.commit()
    flash("Comment added.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/qc/work/<int:work_id>/status/<string:action>", methods=["POST"])
@login_required
def qc_work_status(work_id, action):
    """Progress status for work: open -> in_progress -> closed."""
    work = QCWork.query.get_or_404(work_id)
    valid_transitions = {
        "start": ("Open", "In Progress"),
        "close": ("In Progress", "Closed"),
        "reopen": ("Closed", "In Progress")
    }

    if action not in valid_transitions:
        flash("Invalid action.", "error")
        return redirect(url_for("qc_work_detail", work_id=work.id))

    current, new = valid_transitions[action]
    if work.status != current:
        flash(f"Cannot {action}: current status is {work.status}.", "error")
        return redirect(url_for("qc_work_detail", work_id=work.id))

    work.status = new
    db.session.flush()
    log_work_event(
        work.id,
        "status_changed",
        actor_id=current_user.id,
        from_status=current,
        to_status=new
    )
    db.session.commit()
    flash(f"Work status changed to {new}.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))
# ----------------------------------------------------


@app.route("/qc/recent-submissions")
@login_required
def qc_recent_submissions():
    submissions = (
        Submission.query
        .order_by(Submission.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "qc_recent_submissions.html",
        submissions=submissions
    )


@app.cli.command("initdb")
def initdb():
    """Initialize database and seed sample data"""
    bootstrap_db()
    print("Database initialized with default users and sample form.")


_bootstrap_lock = threading.Lock()
_bootstrapped = False


def ensure_bootstrap():
    global _bootstrapped
    if _bootstrapped:
        return
    with _bootstrap_lock:
        if _bootstrapped:
            return
        try:
            bootstrap_db()
            _bootstrapped = True
        except Exception as exc:
            app.logger.exception("Database bootstrap failed: %s", exc)


@app.before_request
def _ensure_db_ready():
    ensure_bootstrap()


if __name__ == "__main__":
    with app.app_context():
        bootstrap_db()
    app.run(debug=True)
