from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.utils import secure_filename
import os, json, datetime, sqlite3

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
    "Completion", "Structure", "Cladding", "Service", "Repair", "Material"
]
LIFT_TYPES = ["Hydraulic", "MRL", "MR", "Dumbwaiter", "Goods"]
# -------------------------------------------------------------------------------


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)


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

    status = db.Column(db.String(40), default="Open")  # Open / In Progress / Closed
    due_date = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    template = db.relationship("FormSchema")
    creator = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


ALLOWED_PHOTO = {"png", "jpg", "jpeg", "webp"}
ALLOWED_VIDEO = {"mp4", "mov", "avi", "mkv"}

def allowed_file(filename, kind="photo"):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in (ALLOWED_PHOTO if kind == "photo" else ALLOWED_VIDEO)


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


def bootstrap_db():
    db.create_all()        # creates qc_work if missing
    ensure_qc_columns()    # adds missing columns safely

    default_users = [("user1", "pass"), ("user2", "pass"), ("admin", "admin")]
    for u, p in default_users:
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p))

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


@app.route("/dashboard")
@login_required
def dashboard():
    forms = FormSchema.query.all()
    subs = Submission.query.order_by(Submission.created_at.desc()).limit(10).all()
    return render_template("dashboard.html", forms=forms, submissions=subs, category_label=None)


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

        sub = Submission(
            form_id=fs.id,
            submitted_by=current_user.id,
            data_json=json.dumps(values, ensure_ascii=False),
            photos_json=json.dumps(saved_photos, ensure_ascii=False),
            videos_json=json.dumps(saved_videos, ensure_ascii=False),
            work_id=request.args.get("work_id")  # optional
        )
        db.session.add(sub)
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


# ---------------------- QC TABS ----------------------
@app.route("/qc")
@login_required
def qc_home():
    active_tab = request.args.get("tab", "work")
    templates = FormSchema.query.order_by(FormSchema.name.asc()).all()
    work_items = QCWork.query.order_by(QCWork.created_at.desc()).limit(25).all()
    return render_template("qc.html",
                           active_tab=active_tab,
                           templates=templates,
                           work_items=work_items,
                           STAGES=STAGES,
                           LIFT_TYPES=LIFT_TYPES)


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

    if not site_name or not template_id:
        flash("Site name and Template are required.", "error")
        return redirect(url_for("qc_home", tab="work"))

    due_dt = None
    if due:
        try:
            due_dt = datetime.datetime.strptime(due, "%Y-%m-%d")
        except Exception:
            flash("Invalid due date format.", "error")
            return redirect(url_for("qc_home", tab="work"))

    work = QCWork(
        site_name=site_name,
        client_name=client_name or None,
        address=address or None,
        template_id=template_id,
        stage=stage or None,
        lift_type=lift_type or None,
        due_date=due_dt,
        created_by=current_user.id
    )
    db.session.add(work)
    db.session.commit()
    flash("QC work created.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/qc/work/<int:work_id>")
@login_required
def qc_work_detail(work_id):
    work = QCWork.query.get_or_404(work_id)
    submissions = Submission.query.filter_by(work_id=work_id).order_by(Submission.created_at.desc()).all()
    return render_template("qc_work_detail.html", work=work, submissions=submissions)


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
    db.session.commit()
    flash(f"Work status changed to {new}.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))
# ----------------------------------------------------



@app.cli.command("initdb")
def initdb():
    """Initialize database and seed sample data"""
    bootstrap_db()
    print("Database initialized with default users and sample form.")


if __name__ == "__main__":
    with app.app_context():
        bootstrap_db()
    app.run(debug=True)
