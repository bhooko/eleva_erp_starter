from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from werkzeug.utils import secure_filename
import os, json, datetime, sqlite3, threading, re, uuid, random, string, copy
from collections import OrderedDict

from sqlalchemy import case, inspect, func, or_, and_
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


def _random_digits(length=10):
    return "".join(random.choice(string.digits) for _ in range(length))


def generate_random_phone(country_code="+91"):
    return f"{country_code}-{_random_digits(10)}"


def generate_random_email(domains=None):
    domain_pool = domains or [
        "example.com",
        "maildrop.cc",
        "inbound.test",
        "demo.local",
    ]
    local_part = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return f"{local_part}@{random.choice(domain_pool)}"


# ---------------------- QC Profile choices (visible in UI) ----------------------
STAGES = [
    "Template QC", "Stage 1", "Stage 2", "Stage 3",
    "Completion", "Completion QC", "Structure", "Cladding", "Service", "Repair", "Material"
]
LIFT_TYPES = ["Hydraulic", "MRL", "MR", "Dumbwaiter", "Goods"]
DEFAULT_TASK_FORM_NAME = "Generic Task Tracker"
TASK_MILESTONES = [
    "Order Milestone",
    "Design Milestone",
    "Production Milestone",
    "Installation Stage 1",
    "Installation Stage 2",
    "Commissioning",
]

PROJECT_PRIORITIES = ["Immediate", "Urgent", "Normal"]
PROJECT_OPENING_TYPES = ["Single", "Adjacent", "Opposite Opening"]
PROJECT_LOCATIONS = ["Internal", "External"]
PROJECT_STRUCTURE_TYPES = ["NA", "RCC", "MS", "GI"]
PROJECT_CLADDING_TYPES = ["ACP", "Glass", "Hybrid", "Clients Scope", "Other"]
PROJECT_CABIN_FINISHES = ["SS", "MS", "Glass", "SS+Glass", "Designer", "Cage", "Half Cabin", "Other"]
PROJECT_DOOR_OPERATION_TYPES = ["Manual", "Auto"]
PROJECT_DOOR_FINISHES = ["SS", "MS", "Collapsible", "BiParting", "Gate"]
DEPARTMENT_BRANCHES = ["Goa", "Maharashtra"]


def slugify(value):
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or _random_digits(6)


SRT_SAMPLE_TASKS = [
    {
        "id": "SRT-1001",
        "site": "Panaji HQ",
        "summary": "Emergency brake inspection",
        "priority": "High",
        "status": "Pending",
        "due_date": datetime.date(2024, 6, 18),
        "owner": "Ravi Kumar",
        "age_days": 3,
    },
    {
        "id": "SRT-1002",
        "site": "Nova Residency",
        "summary": "Door alignment follow-up",
        "priority": "Medium",
        "status": "Pending",
        "due_date": datetime.date(2024, 6, 22),
        "owner": "Priya Nair",
        "age_days": 5,
    },
    {
        "id": "SRT-1003",
        "site": "Harbour View Tower",
        "summary": "Cabin levelling calibration",
        "priority": "High",
        "status": "In Progress",
        "due_date": datetime.date(2024, 6, 20),
        "owner": "Amol Patil",
        "age_days": 2,
    },
    {
        "id": "SRT-1004",
        "site": "Metro Heights",
        "summary": "Post-service vibration audit",
        "priority": "Low",
        "status": "Pending",
        "due_date": datetime.date(2024, 6, 30),
        "owner": "Sneha Kulkarni",
        "age_days": 1,
    },
]

def _default_srt_item():
    return {
        "label": "New Checklist Item",
        "type": "select",
        "options": ["Pass", "Fail", "N/A"],
        "required": True,
        "allow_photo": True,
        "allow_remark": True,
        "photo_required_if_ng": False,
        "display_image": "",
    }


def _default_srt_schema():
    return [
        {
            "section": "General",
            "display_image": "",
            "items": [_default_srt_item()],
        }
    ]


def _normalise_srt_schema(raw_schema):
    if not isinstance(raw_schema, list):
        return _default_srt_schema()

    normalised_sections = []
    for raw_section in raw_schema:
        if not isinstance(raw_section, dict):
            continue

        section_name = str(raw_section.get("section", "") or "")
        section_image = str(raw_section.get("display_image", "") or "")
        raw_items = raw_section.get("items")
        normalised_items = []

        if isinstance(raw_items, list):
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue

                item_type = str(raw_item.get("type", "select") or "select").lower()
                if item_type == "table":
                    rows = [
                        str(value).strip()
                        for value in raw_item.get("rows", [])
                        if str(value).strip()
                    ]
                    columns = [
                        str(value).strip()
                        for value in raw_item.get("columns", [])
                        if str(value).strip()
                    ]
                    normalised_items.append(
                        {
                            "label": str(raw_item.get("label", "") or ""),
                            "type": "table",
                            "required": bool(raw_item.get("required", False)),
                            "rows": rows or ["Row 1", "Row 2"],
                            "columns": columns or ["Column 1", "Column 2"],
                            "display_image": str(raw_item.get("display_image", "") or ""),
                        }
                    )
                    continue

                allowed_types = {"select", "text", "textarea"}
                if item_type not in allowed_types:
                    item_type = "select"

                if item_type == "select":
                    options = [
                        str(value).strip()
                        for value in raw_item.get("options", [])
                        if str(value).strip()
                    ] or ["Pass", "Fail", "N/A"]
                else:
                    options = []

                allow_photo = bool(raw_item.get("allow_photo", item_type == "select"))
                photo_required = bool(raw_item.get("photo_required_if_ng", False))
                if not allow_photo or item_type != "select":
                    photo_required = False

                normalised_items.append(
                    {
                        "label": str(raw_item.get("label", "") or ""),
                        "type": item_type,
                        "options": options,
                        "required": bool(raw_item.get("required", item_type == "select")),
                        "allow_photo": allow_photo,
                        "allow_remark": bool(raw_item.get("allow_remark", item_type != "text")),
                        "photo_required_if_ng": photo_required,
                        "display_image": str(raw_item.get("display_image", "") or ""),
                    }
                )

        if not normalised_items:
            normalised_items = [_default_srt_item()]

        normalised_sections.append(
            {
                "section": section_name,
                "display_image": section_image,
                "items": normalised_items,
            }
        )

    if not normalised_sections:
        return _default_srt_schema()

    return normalised_sections


SRT_FORM_TEMPLATES = [
    {
        "id": "srt-emergency-brake-audit",
        "name": "SRT - Emergency Brake Audit",
        "category": "Safety",
        "last_updated": datetime.date(2024, 4, 28),
        "usage_count": 14,
        "description": "Checklist capturing emergency brake checks, load test confirmation and evidence uploads.",
        "schema": [
            {
                "section": "Emergency Brake Assembly",
                "display_image": "/static/uploads/1761394043.501005_SAVE_20230822_183825.jpg",
                "items": [
                    {
                        "label": "Brake calipers inspected for wear",
                        "type": "select",
                        "options": ["Pass", "Fail", "Needs follow up"],
                        "required": True,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": True,
                        "display_image": "/static/uploads/1761394043.510924_SAVE_20230822_1837491.jpg",
                    },
                    {
                        "label": "Counterweight gap measurement (mm)",
                        "type": "text",
                        "options": [],
                        "required": True,
                        "allow_photo": False,
                        "allow_remark": False,
                        "photo_required_if_ng": False,
                        "display_image": "",
                    },
                    {
                        "label": "Load test observation notes",
                        "type": "textarea",
                        "options": [],
                        "required": False,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": False,
                        "display_image": "",
                    },
                ],
            },
            {
                "section": "Test Documentation",
                "display_image": "",
                "items": [
                    {
                        "label": "Brake torque verification table",
                        "type": "table",
                        "required": True,
                        "rows": ["Test 1", "Test 2", "Test 3"],
                        "columns": ["Recorded", "Expected", "Variance"],
                        "display_image": "/static/uploads/1761394043.506364_SAVE_20230822_183832.jpg",
                    }
                ],
            },
        ],
    },
    {
        "id": "srt-door-operation-review",
        "name": "SRT - Door Operation Review",
        "category": "Doors",
        "last_updated": datetime.date(2024, 5, 9),
        "usage_count": 9,
        "description": "Structured walk-through for door alignment, interlocks and threshold compliance.",
        "schema": [
            {
                "section": "Door Movement",
                "display_image": "",
                "items": [
                    {
                        "label": "Door closing speed within spec",
                        "type": "select",
                        "options": ["Pass", "Slow", "Fast"],
                        "required": True,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": True,
                        "display_image": "",
                    },
                    {
                        "label": "Sill alignment reference",
                        "type": "textarea",
                        "options": [],
                        "required": False,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": False,
                        "display_image": "/static/uploads/1761394043.501005_SAVE_20230822_183825.jpg",
                    },
                ],
            },
            {
                "section": "Interlock Compliance",
                "display_image": "",
                "items": [
                    {
                        "label": "Landing door interlocks",
                        "type": "select",
                        "options": ["Pass", "Fail", "Requires adjustment"],
                        "required": True,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": True,
                        "display_image": "",
                    },
                    {
                        "label": "Interlock wiring continuity",
                        "type": "text",
                        "options": [],
                        "required": False,
                        "allow_photo": False,
                        "allow_remark": False,
                        "photo_required_if_ng": False,
                        "display_image": "",
                    },
                ],
            },
        ],
    },
    {
        "id": "srt-post-service-summary",
        "name": "SRT - Post Service Summary",
        "category": "Reporting",
        "last_updated": datetime.date(2024, 3, 19),
        "usage_count": 22,
        "description": "Captures punch-list closure status, photos and pending parts for handover.",
        "schema": [
            {
                "section": "Punch List",
                "display_image": "",
                "items": [
                    {
                        "label": "Outstanding issues",
                        "type": "textarea",
                        "options": [],
                        "required": False,
                        "allow_photo": True,
                        "allow_remark": True,
                        "photo_required_if_ng": False,
                        "display_image": "",
                    },
                    {
                        "label": "Pending parts arrival date",
                        "type": "text",
                        "options": [],
                        "required": False,
                        "allow_photo": False,
                        "allow_remark": False,
                        "photo_required_if_ng": False,
                        "display_image": "",
                    },
                ],
            },
            {
                "section": "Hand-over Evidence",
                "display_image": "/static/uploads/1761394043.506364_SAVE_20230822_183832.jpg",
                "items": [
                    {
                        "label": "Client sign-off table",
                        "type": "table",
                        "required": True,
                        "rows": ["Client", "Technician", "Supervisor"],
                        "columns": ["Name", "Signature", "Date"],
                        "display_image": "",
                    }
                ],
            },
        ],
    },
]

SRT_TEAM_MEMBERS = [
    "Ravi Kumar",
    "Priya Nair",
    "Amol Patil",
    "Sneha Kulkarni",
    "Anita D'silva",
    "Rahul Menezes",
]


SRT_SITES = [
    {
        "key": "panaji-hq",
        "name": "Panaji HQ",
        "client": "Trident Holdings",
        "city": "Panaji",
        "address": "Trident Holdings HQ, 5th Floor, Patto Plaza, Panaji, Goa",
        "last_visit": datetime.date(2024, 6, 11),
        "status": "Technician visit scheduled",
        "client_contact": {
            "name": "Rohan Mascarhenas",
            "phone": generate_random_phone(),
            "email": generate_random_email(),
        },
        "interactions": [
            {"date": datetime.date(2024, 6, 13), "type": "Call", "summary": "Scheduled emergency brake inspection with facility manager."},
            {"date": datetime.date(2024, 6, 10), "type": "Email", "summary": "Shared safety advisories and pre-visit checklist."},
        ],
        "updates": [
            {"label": "Latest Update", "value": "Awaiting spare brake pads delivery (ETA 17 Jun)."},
            {"label": "Next Action", "value": "Confirm service window with client."},
        ],
        "additional_contacts": [
            {
                "name": "Meena Dsouza",
                "designation": "Contractor",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": True,
            },
            {
                "name": "Vikram Sawant",
                "designation": "Supervisor",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": False,
            },
        ],
        "form_update": {
            "form_name": "SRT - Emergency Brake Audit",
            "status": "Awaiting closure",
            "last_updated": datetime.date(2024, 6, 12),
            "summary": "Technician notes uploaded; pending brake pad replacement verification.",
        },
    },
    {
        "key": "nova-residency",
        "name": "Nova Residency",
        "client": "Silverline Developers",
        "city": "Mapusa",
        "address": "Nova Residency Block B, Mapusa Industrial Estate, Goa",
        "last_visit": datetime.date(2024, 6, 5),
        "status": "Client feedback pending",
        "client_contact": {
            "name": "Anita D'souza",
            "phone": generate_random_phone(),
            "email": generate_random_email(),
        },
        "interactions": [
            {"date": datetime.date(2024, 6, 12), "type": "Site Visit", "summary": "Performed door alignment checks on blocks A & B."},
            {"date": datetime.date(2024, 6, 7), "type": "Call", "summary": "Discussed vibration readings with maintenance lead."},
        ],
        "updates": [
            {"label": "Latest Update", "value": "Awaiting confirmation on revised door thresholds."},
            {"label": "Next Action", "value": "Share measurement sheet with QC for review."},
        ],
        "additional_contacts": [
            {
                "name": "Sahil Naik",
                "designation": "Labour Contractor",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": True,
            },
            {
                "name": "Priyanka Kenkre",
                "designation": "Client Coordinator",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": False,
            },
        ],
        "form_update": {
            "form_name": "SRT - Door Operation Review",
            "status": "Under review",
            "last_updated": datetime.date(2024, 6, 9),
            "summary": "Alignment readings submitted; awaiting QC comments on thresholds.",
        },
    },
    {
        "key": "harbour-view-tower",
        "name": "Harbour View Tower",
        "client": "Bluewater Properties",
        "city": "Vasco",
        "address": "Harbour View Tower, Port Road, Vasco, Goa",
        "last_visit": datetime.date(2024, 6, 2),
        "status": "Monitoring",
        "client_contact": {
            "name": "Ketan Prabhu",
            "phone": generate_random_phone(),
            "email": generate_random_email(),
        },
        "interactions": [
            {"date": datetime.date(2024, 6, 9), "type": "Email", "summary": "Sent levelling calibration results and next steps."},
            {"date": datetime.date(2024, 5, 30), "type": "Call", "summary": "Logged client concern about door closure speed."},
        ],
        "updates": [
            {"label": "Latest Update", "value": "Calibration within tolerance; monitoring for 48 hrs."},
            {"label": "Next Action", "value": "Revisit only if variance exceeds 3 mm."},
        ],
        "additional_contacts": [
            {
                "name": "Rima Fernandes",
                "designation": "Supervisor",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": True,
            },
            {
                "name": "Mahesh Lotlikar",
                "designation": "Electrician",
                "phone": generate_random_phone(),
                "email": generate_random_email(),
                "is_primary": False,
            },
        ],
        "form_update": {
            "form_name": "SRT - Post Service Summary",
            "status": "Monitoring",
            "last_updated": datetime.date(2024, 6, 8),
            "summary": "Calibration log uploaded; awaiting confirmation on vibration levels.",
        },
    },
]

SALES_PIPELINES = {
    "lift": {
        "label": "Lift",
        "stages": [
            "New Enquiry",
            "Site Visit",
            "Quote Submission",
            "Negotiation",
            "Closed Won",
            "Closed Lost",
        ],
    },
    "amc": {
        "label": "AMC",
        "stages": [
            "New AMC Enquiry",
            "Technician Visit",
            "Quote Submission",
            "Negotiation",
            "Closed Won",
            "Closed Lost",
        ],
    },
    "parking": {
        "label": "Parking System",
        "stages": [
            "New Parking Enquiry",
            "Site Assessment",
            "Proposal Shared",
            "Negotiation",
            "Closed Won",
            "Closed Lost",
        ],
    },
}

SALES_TEMPERATURES = [
    ("cold", "Cold"),
    ("warm", "Warm"),
    ("hot", "Hot"),
]

SALES_CLIENT_LIFECYCLE_STAGES = [
    "Prospect",
    "Qualification",
    "Negotiation",
    "Customer",
    "Post-Sales",
]

OPPORTUNITY_REMINDER_OPTIONS = [
    ("", "No reminder"),
    ("1h", "1 Hr before due"),
    ("2h", "2 Hr before due"),
    ("3h", "3 Hr before due"),
    ("1d", "1 Day before due"),
]

REMINDER_OPTION_LABELS = {value: label for value, label in OPPORTUNITY_REMINDER_OPTIONS}

OPPORTUNITY_ACTIVITY_LABELS = {
    "meeting": "Meeting",
    "call": "Call",
    "email": "Email",
}


def format_file_size(num_bytes):
    if num_bytes is None:
        return "0 B"

    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(num_bytes, 0))
    for unit in units:
        if size < step or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= step


def get_pipeline_config(pipeline_key):
    key = (pipeline_key or "lift").lower()
    return SALES_PIPELINES.get(key, SALES_PIPELINES["lift"])


def get_pipeline_stages(pipeline_key):
    return get_pipeline_config(pipeline_key)["stages"]


def format_currency(amount, currency="₹"):
    if amount is None:
        return "—"
    return f"{currency or '₹'}{amount:,.2f}"


def normalize_lifecycle_stage(value):
    value = (value or "").strip()
    if not value:
        return None
    if value not in SALES_CLIENT_LIFECYCLE_STAGES:
        return SALES_CLIENT_LIFECYCLE_STAGES[0]
    return value


def log_sales_activity(parent_type, parent_id, title, notes=None, actor=None):
    entry = SalesActivity(
        parent_type=parent_type,
        parent_id=parent_id,
        actor=actor or (current_user if current_user.is_authenticated else None),
        title=title,
        notes=notes,
    )
    db.session.add(entry)
    return entry


def normalize_floor_label(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None

    compact = re.sub(r"\s+", "", value.upper())
    if compact in {"G", "G+"}:
        return None

    # If the value is purely numeric, prefix it with G+ for consistency.
    if re.fullmatch(r"\d+", compact):
        return f"G+{compact}"

    # Normalize leading G without a plus sign (e.g., G10 -> G+10).
    if compact.startswith("G") and not compact.startswith("G+"):
        compact = f"G+{compact[1:]}"

    # Ensure there is only a single + immediately after G when present.
    if compact.startswith("G+"):
        suffix = compact[2:]
        suffix = suffix.lstrip("+")
        compact = f"G+{suffix}" if suffix else "G+"

    if compact in {"", "G+"}:
        return None

    return compact


def _extract_task_timing(form):
    start_mode = (form.get("start_mode") or "immediate").strip().lower()
    if start_mode not in {"immediate", "scheduled", "after_previous"}:
        start_mode = "immediate"

    start_date_value = None
    start_date_raw = (form.get("start_date") or "").strip()
    if start_mode == "scheduled":
        if not start_date_raw:
            return None, None, None, None, "Provide a start date for scheduled tasks."
        try:
            start_date_value = datetime.datetime.strptime(start_date_raw, "%Y-%m-%d").date()
        except ValueError:
            return None, None, None, None, "Start date must be a valid YYYY-MM-DD date."
    elif start_mode == "after_previous":
        # Ignore any manually provided start date when using sequential scheduling.
        start_date_value = None
    elif start_date_raw:
        # Allow optionally overriding the start date even if immediate was chosen.
        try:
            start_date_value = datetime.datetime.strptime(start_date_raw, "%Y-%m-%d").date()
        except ValueError:
            return None, None, None, None, "Start date must be a valid YYYY-MM-DD date."

    duration_raw = (form.get("duration_days") or "").strip()
    duration_value = None
    if duration_raw:
        try:
            duration_value = int(duration_raw)
        except ValueError:
            return None, None, None, None, "Duration must be a whole number of days."
        if duration_value < 0:
            return None, None, None, None, "Duration must be zero or a positive number of days."

    milestone_value = (form.get("milestone") or "").strip() or None

    # If mode is immediate we ignore scheduled date (unless user typed one to override).
    if start_mode == "immediate" and start_date_raw == "":
        start_date_value = None

    return start_mode, start_date_value, duration_value, milestone_value, None


def normalize_template_task_order(template_id):
    tasks = ProjectTemplateTask.query.filter_by(template_id=template_id).order_by(
        ProjectTemplateTask.order_index.asc(),
        ProjectTemplateTask.id.asc()
    ).all()
    for idx, task in enumerate(tasks, start=1):
        task.order_index = idx
    return tasks


def set_template_task_dependencies(task, dependency_ids):
    if not task:
        return
    cleaned = []
    for dep_id in dependency_ids or []:
        if not dep_id:
            continue
        if dep_id == task.id:
            continue
        if dep_id not in cleaned:
            cleaned.append(dep_id)
    task.depends_on_id = cleaned[0] if cleaned else None
    existing = {link.depends_on_id: link for link in getattr(task, "dependency_links", [])}
    for dep_id, link in list(existing.items()):
        if dep_id not in cleaned:
            db.session.delete(link)
    for dep_id in cleaned:
        if dep_id not in existing:
            db.session.add(ProjectTemplateTaskDependency(task_id=task.id, depends_on_id=dep_id))


def set_qc_work_dependencies(work, dependency_ids):
    if not work:
        return
    cleaned = []
    for dep_id in dependency_ids or []:
        if not dep_id:
            continue
        if dep_id == work.id:
            continue
        if dep_id not in cleaned:
            cleaned.append(dep_id)
    work.depends_on_id = cleaned[0] if cleaned else None
    existing = {link.depends_on_id: link for link in getattr(work, "dependency_links", [])}
    for dep_id, link in list(existing.items()):
        if dep_id not in cleaned:
            db.session.delete(link)
    for dep_id in cleaned:
        if dep_id not in existing:
            db.session.add(QCWorkDependency(task_id=work.id, depends_on_id=dep_id))


def synchronize_dependency_links():
    try:
        template_tasks = ProjectTemplateTask.query.filter(ProjectTemplateTask.depends_on_id.isnot(None)).all()
        for task in template_tasks:
            existing = {link.depends_on_id for link in getattr(task, "dependency_links", [])}
            if task.depends_on_id and task.depends_on_id not in existing:
                db.session.add(ProjectTemplateTaskDependency(task_id=task.id, depends_on_id=task.depends_on_id))

        qc_tasks = QCWork.query.filter(QCWork.depends_on_id.isnot(None)).all()
        for work in qc_tasks:
            existing = {link.depends_on_id for link in getattr(work, "dependency_links", [])}
            if work.depends_on_id and work.depends_on_id not in existing:
                db.session.add(QCWorkDependency(task_id=work.id, depends_on_id=work.depends_on_id))

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f"⚠️ Unable to synchronize dependency links automatically: {exc}")


def build_task_template_blueprint(template):
    tasks = sorted(template.tasks, key=lambda t: ((t.order_index or 0), t.id))
    id_to_index = {task.id: idx for idx, task in enumerate(tasks)}
    blueprint = []
    for idx, task in enumerate(tasks):
        dependency_indexes = []
        for dep in task.dependencies:
            dep_index = id_to_index.get(dep.id)
            if dep_index is not None:
                dependency_indexes.append(dep_index)
        blueprint.append({
            "name": task.name,
            "description": task.description,
            "order_index": task.order_index or (idx + 1),
            "default_assignee_id": task.default_assignee_id,
            "form_template_id": task.form_template_id,
            "start_mode": task.start_mode or "immediate",
            "planned_start_date": task.planned_start_date.isoformat() if task.planned_start_date else None,
            "duration_days": task.duration_days,
            "milestone": task.milestone,
            "dependency_indexes": dependency_indexes,
        })
    return blueprint


def apply_blueprint_to_template(template, blueprint):
    if not isinstance(blueprint, list):
        return []
    created = []
    for idx, entry in enumerate(blueprint):
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or f"Task {idx + 1}").strip()
        description = (entry.get("description") or None)
        order_index = entry.get("order_index") or (idx + 1)
        default_assignee_id = entry.get("default_assignee_id")
        form_template_id = entry.get("form_template_id")
        start_mode = (entry.get("start_mode") or "immediate").lower()
        if start_mode not in {"immediate", "scheduled", "after_previous"}:
            start_mode = "immediate"
        planned_start = entry.get("planned_start_date")
        planned_start_date = None
        if planned_start:
            try:
                planned_start_date = datetime.datetime.strptime(planned_start, "%Y-%m-%d").date()
            except ValueError:
                planned_start_date = None
        duration_days = entry.get("duration_days")
        if isinstance(duration_days, str) and duration_days.isdigit():
            duration_days = int(duration_days)
        elif not isinstance(duration_days, int):
            duration_days = None
        milestone = entry.get("milestone") or None

        task = ProjectTemplateTask(
            template_id=template.id,
            name=name,
            description=description,
            order_index=order_index,
            default_assignee_id=default_assignee_id,
            form_template_id=form_template_id,
            start_mode=start_mode,
            planned_start_date=planned_start_date,
            duration_days=duration_days,
            milestone=milestone
        )
        db.session.add(task)
        db.session.flush()
        created.append((task, entry))

    for task, entry in created:
        dependency_indexes = entry.get("dependency_indexes") or []
        dependency_ids = []
        for dep_idx in dependency_indexes:
            if isinstance(dep_idx, int) and 0 <= dep_idx < len(created):
                dependency_ids.append(created[dep_idx][0].id)
        set_template_task_dependencies(task, dependency_ids)

    normalize_template_task_order(template.id)
    return [task for task, _ in created]
# -------------------------------------------------------------------------------


def _normalize_form_schema(schema_raw):
    """Return (sections, is_sectioned) for a stored form schema."""
    if not isinstance(schema_raw, list):
        return [], False

    def _normalize_item(item, idx):
        if not isinstance(item, dict):
            item = {}
        normalized = dict(item)
        normalized["label"] = str(item.get("label") or f"Item {idx + 1}")
        ftype = (item.get("type") or "select").lower()
        if ftype not in {"text", "textarea", "select", "table"}:
            ftype = "select"
        normalized["type"] = ftype
        normalized["required"] = bool(item.get("required", False))
        if ftype == "select":
            opts = item.get("options") or ["Good", "NG"]
            normalized["options"] = [str(opt) for opt in opts if str(opt).strip()]
            normalized["photo_required_if_ng"] = bool(item.get("photo_required_if_ng", False))
            normalized["allow_photo"] = bool(item.get("allow_photo", normalized["photo_required_if_ng"]))
            normalized["allow_remark"] = bool(item.get("allow_remark", False))
            normalized["reference_image"] = None
            normalized["rows"] = []
            normalized["columns"] = []
        elif ftype in {"text", "textarea"}:
            normalized["options"] = []
            normalized["photo_required_if_ng"] = False
            normalized["allow_photo"] = bool(item.get("allow_photo", False))
            normalized["allow_remark"] = bool(item.get("allow_remark", False))
            normalized["reference_image"] = None
            normalized["rows"] = []
            normalized["columns"] = []
        else:  # table
            rows = item.get("rows") or []
            cols = item.get("columns") or []
            if not isinstance(rows, list):
                rows = []
            if not isinstance(cols, list):
                cols = []
            normalized["rows"] = [str(r) for r in rows if str(r).strip()]
            normalized["columns"] = [str(c) for c in cols if str(c).strip()]
            if not normalized["rows"]:
                normalized["rows"] = ["Row 1", "Row 2"]
            if not normalized["columns"]:
                normalized["columns"] = ["Column 1", "Column 2"]
            ref_img = item.get("reference_image")
            normalized["reference_image"] = str(ref_img) if ref_img is not None else ""
            normalized["options"] = []
            normalized["photo_required_if_ng"] = False
            normalized["allow_photo"] = False
            normalized["allow_remark"] = False
        return normalized

    if schema_raw and isinstance(schema_raw[0], dict) and "section" in schema_raw[0]:
        sections = []
        for s_idx, section in enumerate(schema_raw):
            if not isinstance(section, dict):
                continue
            items = section.get("items") or []
            normalized_items = [_normalize_item(it, idx) for idx, it in enumerate(items)]
            sections.append({
                "section": section.get("section") or f"Section {s_idx + 1}",
                "items": normalized_items
            })
        return sections, True

    normalized_items = [_normalize_item(it, idx) for idx, it in enumerate(schema_raw)]
    return [{"section": "", "items": normalized_items}], False


class Department(db.Model):
    __tablename__ = "department"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    branch = db.Column(db.String(50), nullable=False, default=DEPARTMENT_BRANCHES[0])
    description = db.Column(db.Text, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True)
    active = db.Column(db.Boolean, default=True)

    children = db.relationship(
        "Department",
        backref=db.backref("parent", remote_side=[id]),
    )
    positions = db.relationship(
        "Position",
        back_populates="department",
    )

    @property
    def full_name(self):
        parts = [self.name]
        parent = getattr(self, "parent", None)
        while parent:
            parts.append(parent.name)
            parent = getattr(parent, "parent", None)
        return " / ".join(reversed([p for p in parts if p]))


class Position(db.Model):
    __tablename__ = "position"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True)
    reports_to_id = db.Column(db.Integer, db.ForeignKey("position.id"), nullable=True)
    active = db.Column(db.Boolean, default=True)

    department = db.relationship("Department", back_populates="positions")
    reports_to = db.relationship(
        "Position",
        remote_side=[id],
        backref=db.backref("direct_reports"),
    )
    users = db.relationship("User", back_populates="position")

    @property
    def hierarchy_label(self):
        parts = [self.title]
        parent = getattr(self, "reports_to", None)
        visited = {self.id}
        while parent and getattr(parent, "id", None) not in visited:
            parts.append(parent.title)
            visited.add(parent.id)
            parent = getattr(parent, "reports_to", None)
        return " / ".join(reversed([p for p in parts if p]))

    @property
    def display_label(self):
        dept_label = self.department.full_name if self.department else None
        hierarchy = self.hierarchy_label
        if dept_label:
            return f"{dept_label} · {hierarchy}"
        return hierarchy


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
    active = db.Column(db.Boolean, default=True)
    session_token = db.Column(
        db.String(36),
        nullable=True,
        default=lambda: str(uuid.uuid4()),
    )
    position_id = db.Column(db.Integer, db.ForeignKey("position.id"), nullable=True)

    position = db.relationship("Position", back_populates="users")

    @property
    def display_name(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.username

    @property
    def is_active(self):
        return bool(self.active)

    @property
    def is_admin(self):
        role = (self.role or "").strip().lower()
        return role == "admin" or self.username.lower() == "admin"

    def issue_session_token(self):
        self.session_token = str(uuid.uuid4())
        return self.session_token


class Project(db.Model):
    __tablename__ = "project"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    site_name = db.Column(db.String(200), nullable=True)
    site_address = db.Column(db.Text, nullable=True)
    customer_name = db.Column(db.String(200), nullable=True)
    lift_type = db.Column(db.String(40), nullable=True)
    floors = db.Column(db.String(40), nullable=True)
    stops = db.Column(db.Integer, nullable=True)
    opening_type = db.Column(db.String(40), nullable=True)
    location = db.Column(db.String(40), nullable=True)
    structure_type = db.Column(db.String(40), nullable=True)
    cladding_type = db.Column(db.String(40), nullable=True)
    cabin_finish = db.Column(db.String(40), nullable=True)
    door_operation_type = db.Column(db.String(40), nullable=True)
    door_finish = db.Column(db.String(40), nullable=True)
    handover_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class FormSchema(db.Model):
    __tablename__ = "form_schema"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    min_photos_if_all_good = db.Column(db.Integer, default=0)

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


class ProjectTemplate(db.Model):
    __tablename__ = "project_template"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    creator = db.relationship("User")


class ProjectTemplateTask(db.Model):
    __tablename__ = "project_template_task"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("project_template.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order_index = db.Column(db.Integer, default=0)
    depends_on_id = db.Column(db.Integer, db.ForeignKey("project_template_task.id"), nullable=True)
    default_assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    form_template_id = db.Column(db.Integer, db.ForeignKey("form_schema.id"), nullable=True)
    start_mode = db.Column(db.String(20), default="immediate")
    planned_start_date = db.Column(db.Date, nullable=True)
    duration_days = db.Column(db.Integer, nullable=True)
    milestone = db.Column(db.String(120), nullable=True)

    template = db.relationship("ProjectTemplate", backref=db.backref("tasks", cascade="all, delete-orphan", order_by="ProjectTemplateTask.order_index"))
    depends_on = db.relationship("ProjectTemplateTask", remote_side=[id], backref=db.backref("primary_dependents", cascade="all"))
    default_assignee = db.relationship("User", foreign_keys=[default_assignee_id])
    form_template = db.relationship("FormSchema")
    dependency_links = db.relationship(
        "ProjectTemplateTaskDependency",
        foreign_keys="ProjectTemplateTaskDependency.task_id",
        cascade="all, delete-orphan",
        back_populates="task"
    )

    @property
    def planned_due_date(self):
        if self.planned_start_date and self.duration_days:
            return self.planned_start_date + datetime.timedelta(days=self.duration_days)
        return None

    @property
    def dependency_ids(self):
        ids = []
        if self.depends_on_id:
            ids.append(self.depends_on_id)
        for link in getattr(self, "dependency_links", []):
            if link.depends_on_id and link.depends_on_id not in ids:
                ids.append(link.depends_on_id)
        return ids

    @property
    def dependencies(self):
        seen = set()
        ordered = []
        if self.depends_on and self.depends_on.id not in seen:
            ordered.append(self.depends_on)
            seen.add(self.depends_on.id)
        for link in getattr(self, "dependency_links", []):
            if link.dependency and link.dependency.id not in seen:
                ordered.append(link.dependency)
                seen.add(link.dependency.id)
        return ordered


class ProjectTemplateTaskDependency(db.Model):
    __tablename__ = "project_template_task_dependency"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("project_template_task.id"), nullable=False)
    depends_on_id = db.Column(db.Integer, db.ForeignKey("project_template_task.id"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("task_id", "depends_on_id", name="uq_template_task_dependency"),
    )

    task = db.relationship(
        "ProjectTemplateTask",
        foreign_keys=[task_id],
        back_populates="dependency_links"
    )
    dependency = db.relationship(
        "ProjectTemplateTask",
        foreign_keys=[depends_on_id],
        backref=db.backref("dependent_links", cascade="all, delete-orphan")
    )


class TaskTemplate(db.Model):
    __tablename__ = "task_template"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    blueprint_json = db.Column(db.Text, nullable=False)
    created_from_template_id = db.Column(db.Integer, db.ForeignKey("project_template.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    creator = db.relationship("User")
    source_template = db.relationship("ProjectTemplate")

    @property
    def task_count(self):
        try:
            data = json.loads(self.blueprint_json or "[]")
        except json.JSONDecodeError:
            return 0
        if isinstance(data, list):
            return len(data)
        return 0


class SalesClient(db.Model):
    __tablename__ = "sales_client"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(150), nullable=False)
    company_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    tag = db.Column(db.String(60), nullable=True)
    category = db.Column(db.String(60), default="Individual")
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    lifecycle_stage = db.Column(db.String(120), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    owner = db.relationship("User")
    opportunities = db.relationship(
        "SalesOpportunity",
        back_populates="client",
        cascade="all, delete-orphan",
    )

    @property
    def open_opportunity_count(self):
        return sum(1 for opp in self.opportunities if not opp.is_closed)


class SalesOpportunity(db.Model):
    __tablename__ = "sales_opportunity"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    pipeline = db.Column(db.String(40), nullable=False, default="lift")
    stage = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(40), default="Open")
    temperature = db.Column(db.String(20), nullable=True)
    amount = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(8), default="₹")
    expected_close_date = db.Column(db.Date, nullable=True)
    probability = db.Column(db.Integer, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("sales_client.id"), nullable=True)
    related_project = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    owner = db.relationship("User")
    client = db.relationship("SalesClient", back_populates="opportunities")
    comments = db.relationship(
        "SalesOpportunityComment",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    files = db.relationship(
        "SalesOpportunityFile",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    engagements = db.relationship(
        "SalesOpportunityEngagement",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    items = db.relationship(
        "SalesOpportunityItem",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )

    @property
    def display_amount(self):
        if self.amount is None:
            return "—"
        return f"{self.currency or '₹'}{self.amount:,.2f}"

    @property
    def is_closed(self):
        status = (self.status or "").strip().lower()
        if status == "closed":
            return True

        stage = (self.stage or "").strip().lower()
        return stage.startswith("closed") if stage else False

    @property
    def badge_variant(self):
        mapping = {
            "hot": ("Hot", "bg-rose-500/20 text-rose-300 border border-rose-500/40"),
            "warm": ("Warm", "bg-amber-500/20 text-amber-200 border border-amber-500/40"),
            "cold": ("Cold", "bg-sky-500/20 text-sky-200 border border-sky-500/40"),
        }
        key = (self.temperature or "").strip().lower()
        return mapping.get(key, (None, "bg-slate-800/60 text-slate-300 border border-slate-700/60"))


class SalesActivity(db.Model):
    __tablename__ = "sales_activity"

    id = db.Column(db.Integer, primary_key=True)
    parent_type = db.Column(db.String(30), nullable=False)
    parent_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    actor = db.relationship("User")


class SalesOpportunityComment(db.Model):
    __tablename__ = "sales_opportunity_comment"

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("sales_opportunity.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    opportunity = db.relationship("SalesOpportunity", back_populates="comments")
    author = db.relationship("User")


class SalesOpportunityFile(db.Model):
    __tablename__ = "sales_opportunity_file"

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("sales_opportunity.id"), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(400), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    opportunity = db.relationship("SalesOpportunity", back_populates="files")
    uploaded_by = db.relationship("User")

    @property
    def display_size(self):
        return format_file_size(self.file_size or 0)


class SalesOpportunityEngagement(db.Model):
    __tablename__ = "sales_opportunity_engagement"

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("sales_opportunity.id"), nullable=False)
    activity_type = db.Column(db.String(40), default="meeting")
    subject = db.Column(db.String(200), nullable=True)
    scheduled_for = db.Column(db.DateTime, nullable=True)
    reminder_option = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    opportunity = db.relationship("SalesOpportunity", back_populates="engagements")
    created_by = db.relationship("User")

    @property
    def display_activity_type(self):
        return OPPORTUNITY_ACTIVITY_LABELS.get(self.activity_type, (self.activity_type or "").title() or "Activity")

    @property
    def display_schedule(self):
        if not self.scheduled_for:
            return "Date not set"
        return self.scheduled_for.strftime("%d %b %Y, %I:%M %p")

    @property
    def display_reminder(self):
        key = (self.reminder_option or "").strip()
        return REMINDER_OPTION_LABELS.get(key, "No reminder")


class SalesOpportunityItem(db.Model):
    __tablename__ = "sales_opportunity_item"

    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("sales_opportunity.id"), nullable=False)
    details = db.Column(db.Text, nullable=True)
    lift_type = db.Column(db.String(80), nullable=True)
    quantity = db.Column(db.Integer, nullable=True)
    floors = db.Column(db.String(80), nullable=True)
    cabin_finish = db.Column(db.String(120), nullable=True)
    door_type = db.Column(db.String(120), nullable=True)
    structure_required = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    opportunity = db.relationship("SalesOpportunity", back_populates="items")

    @property
    def structure_label(self):
        return "Yes" if self.structure_required else "No"


# NEW: QC Work table (simple tracker for “create work for new site QC”)
class QCWork(db.Model):
    __tablename__ = "qc_work"
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(200), nullable=False)
    client_name = db.Column(db.String(200), nullable=True)
    address = db.Column(db.Text, nullable=True)

    name = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)

    template_id = db.Column(db.Integer, db.ForeignKey("form_schema.id"), nullable=False)
    stage = db.Column(db.String(40), nullable=True)
    lift_type = db.Column(db.String(40), nullable=True)

    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)

    template_task_id = db.Column(db.Integer, db.ForeignKey("project_template_task.id"), nullable=True)
    depends_on_id = db.Column(db.Integer, db.ForeignKey("qc_work.id"), nullable=True)

    status = db.Column(db.String(40), default="Open")  # Open / In Progress / Closed
    due_date = db.Column(db.DateTime, nullable=True)
    planned_start_date = db.Column(db.Date, nullable=True)
    planned_duration_days = db.Column(db.Integer, nullable=True)
    milestone = db.Column(db.String(120), nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    template = db.relationship("FormSchema")
    creator = db.relationship("User", foreign_keys=[created_by])
    assignee = db.relationship("User", foreign_keys=[assigned_to])
    project = db.relationship("Project", backref=db.backref("tasks", lazy="dynamic"))
    template_task = db.relationship("ProjectTemplateTask", backref=db.backref("project_tasks", lazy="dynamic"))
    primary_dependency = db.relationship(
        "QCWork",
        remote_side=[id],
        backref=db.backref("primary_dependents", cascade="all"),
        foreign_keys=[depends_on_id]
    )
    dependency_links = db.relationship(
        "QCWorkDependency",
        foreign_keys="QCWorkDependency.task_id",
        cascade="all, delete-orphan",
        back_populates="task"
    )

    @property
    def display_title(self):
        if self.name:
            return self.name
        if self.site_name:
            return self.site_name
        return f"Task #{self.id}"

    @property
    def dependency_satisfied(self):
        for dependency in self.dependencies:
            if (dependency.status or "").lower() != "closed":
                return False
        return True

    @property
    def is_blocked(self):
        return not self.dependency_satisfied

    @property
    def dependencies(self):
        seen = set()
        ordered = []
        if self.primary_dependency and self.primary_dependency.id not in seen:
            ordered.append(self.primary_dependency)
            seen.add(self.primary_dependency.id)
        for link in getattr(self, "dependency_links", []):
            if link.dependency and link.dependency.id not in seen:
                ordered.append(link.dependency)
                seen.add(link.dependency.id)
        return ordered

    @property
    def dependency(self):
        deps = self.dependencies
        return deps[0] if deps else None

    @property
    def dependency_ids(self):
        return [dep.id for dep in self.dependencies]

    @property
    def all_dependents(self):
        dependents = []
        seen = set()
        for dependent in getattr(self, "primary_dependents", []):
            if dependent.id not in seen:
                dependents.append(dependent)
                seen.add(dependent.id)
        for link in getattr(self, "dependent_links", []):
            if link.task and link.task.id not in seen:
                dependents.append(link.task)
                seen.add(link.task.id)
        return dependents

    @property
    def planned_due_date(self):
        if self.planned_start_date and self.planned_duration_days:
            return self.planned_start_date + datetime.timedelta(days=self.planned_duration_days)
        return None


class QCWorkDependency(db.Model):
    __tablename__ = "qc_work_dependency"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("qc_work.id"), nullable=False)
    depends_on_id = db.Column(db.Integer, db.ForeignKey("qc_work.id"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("task_id", "depends_on_id", name="uq_qc_work_dependency"),
    )

    task = db.relationship(
        "QCWork",
        foreign_keys=[task_id],
        back_populates="dependency_links"
    )
    dependency = db.relationship(
        "QCWork",
        foreign_keys=[depends_on_id],
        backref=db.backref("dependent_links", cascade="all, delete-orphan")
    )


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
    # Ensure that any pending bootstrap/migration tasks run before we try to
    # query the database. When the application starts for the very first time
    # Flask-Login may attempt to load the user (via `current_user`) before our
    # `@app.before_request` hook that calls `ensure_bootstrap()` executes. In
    # that scenario the legacy SQLite schema might still be missing newer
    # columns such as `user.active`, resulting in an OperationalError during the
    # initial SELECT. Proactively invoking `ensure_bootstrap()` here guarantees
    # the schema has been patched before any queries are issued.
    ensure_bootstrap()
    try:
        user_obj = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user_obj and not user_obj.is_active:
        return None
    return user_obj


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


@app.before_request
def enforce_user_session():
    if not current_user.is_authenticated:
        return

    if not current_user.is_active:
        session.pop("session_token", None)
        logout_user()
        flash("Your account has been deactivated.", "error")
        return

    if not current_user.session_token:
        current_user.issue_session_token()
        db.session.commit()

    token = session.get("session_token")
    if token and token == current_user.session_token:
        return

    session.pop("session_token", None)
    logout_user()
    flash("You have been signed out. Please log in again.", "info")


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


def get_or_create_default_task_form():
    form = FormSchema.query.filter_by(name=DEFAULT_TASK_FORM_NAME).first()
    if form:
        return form
    fallback_schema = [
        {"label": "Summary", "type": "textarea", "required": False, "allow_remark": False},
        {"label": "Status", "type": "select", "required": True, "options": ["Not Started", "In Progress", "Completed"]}
    ]
    form = FormSchema(
        name=DEFAULT_TASK_FORM_NAME,
        schema_json=json.dumps(fallback_schema, ensure_ascii=False),
        min_photos_if_all_good=0
    )
    db.session.add(form)
    db.session.flush()
    return form


def release_dependent_tasks(work, actor_id=None):
    for dependent in work.all_dependents:
        if dependent.status == "Blocked" and dependent.dependency_satisfied:
            dependent.status = "Open"
            db.session.flush()
            log_work_event(
                dependent.id,
                "dependency_released",
                actor_id=actor_id,
                details={"dependency": work.id}
            )


def block_child_tasks(work, actor_id=None):
    for dependent in work.all_dependents:
        if dependent.status != "Closed" and work.id in dependent.dependency_ids:
            dependent.status = "Blocked"
            db.session.flush()
            log_work_event(
                dependent.id,
                "dependency_reinstated",
                actor_id=actor_id,
                details={"dependency": work.id}
            )


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
        "display_picture": "TEXT",
        "active": "INTEGER DEFAULT 1",
        "session_token": "TEXT",
        "position_id": "INTEGER"
    }
    for col, col_type in user_column_defs.items():
        if col not in user_cols:
            cur.execute(f"ALTER TABLE user ADD COLUMN {col} {col_type};")
            added_user.append(col)

    # department additions
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='department'")
    department_exists = cur.fetchone() is not None
    added_department_cols = []
    if department_exists:
        cur.execute("PRAGMA table_info(department)")
        department_cols = [r[1] for r in cur.fetchall()]
        if "branch" not in department_cols:
            cur.execute("ALTER TABLE department ADD COLUMN branch TEXT DEFAULT 'Goa';")
            cur.execute("UPDATE department SET branch = COALESCE(branch, 'Goa');")
            added_department_cols.append("branch")

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
        if "name" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN name TEXT;")
            added_qc.append("name")
        if "description" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN description TEXT;")
            added_qc.append("description")
        if "template_task_id" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN template_task_id INTEGER;")
            added_qc.append("template_task_id")
        if "depends_on_id" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN depends_on_id INTEGER;")
            added_qc.append("depends_on_id")
        if "planned_start_date" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN planned_start_date TEXT;")
            added_qc.append("planned_start_date")
        if "planned_duration_days" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN planned_duration_days INTEGER;")
            added_qc.append("planned_duration_days")
        if "milestone" not in qc_cols:
            cur.execute("ALTER TABLE qc_work ADD COLUMN milestone TEXT;")
            added_qc.append("milestone")

    # project_template_task additions
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_template_task'")
    template_task_exists = cur.fetchone() is not None
    added_template_cols = []
    if template_task_exists:
        cur.execute("PRAGMA table_info(project_template_task)")
        template_cols = [r[1] for r in cur.fetchall()]
        if "start_mode" not in template_cols:
            cur.execute("ALTER TABLE project_template_task ADD COLUMN start_mode TEXT DEFAULT 'immediate';")
            added_template_cols.append("start_mode")
        if "planned_start_date" not in template_cols:
            cur.execute("ALTER TABLE project_template_task ADD COLUMN planned_start_date TEXT;")
            added_template_cols.append("planned_start_date")
        if "duration_days" not in template_cols:
            cur.execute("ALTER TABLE project_template_task ADD COLUMN duration_days INTEGER;")
            added_template_cols.append("duration_days")
        if "milestone" not in template_cols:
            cur.execute("ALTER TABLE project_template_task ADD COLUMN milestone TEXT;")
            added_template_cols.append("milestone")

    # project additions
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project'")
    project_exists = cur.fetchone() is not None
    added_project_cols = []
    if project_exists:
        cur.execute("PRAGMA table_info(project)")
        project_cols = {row[1]: (row[2] or "").upper() for row in cur.execute("PRAGMA table_info(project)")}

        if "floors" in project_cols and project_cols["floors"] not in {"TEXT", "VARCHAR", "NVARCHAR"}:
            cur.execute("ALTER TABLE project RENAME COLUMN floors TO floors_numeric;")
            project_cols = {row[1]: (row[2] or "").upper() for row in cur.execute("PRAGMA table_info(project)")}

        project_column_defs = {
            "floors": "TEXT",
            "stops": "INTEGER",
            "opening_type": "TEXT",
            "location": "TEXT",
            "handover_date": "TEXT",
            "priority": "TEXT",
            "structure_type": "TEXT",
            "cladding_type": "TEXT",
            "cabin_finish": "TEXT",
            "door_operation_type": "TEXT",
            "door_finish": "TEXT",
        }
        for col, col_type in project_column_defs.items():
            if col not in project_cols:
                cur.execute(f"ALTER TABLE project ADD COLUMN {col} {col_type};")
                added_project_cols.append(col)

        if "floors_numeric" in project_cols and "floors" in project_column_defs:
            cur.execute(
                "UPDATE project SET floors = CASE WHEN floors IS NULL OR floors = '' THEN CAST(floors_numeric AS TEXT) ELSE floors END WHERE floors_numeric IS NOT NULL;"
            )

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

    if department_exists:
        if added_department_cols:
            print(f"✅ Auto-added in department: {', '.join(added_department_cols)}")
        else:
            print("✔️ department OK")

    if template_task_exists:
        if added_template_cols:
            print(f"✅ Auto-added in project_template_task: {', '.join(added_template_cols)}")
        else:
            print("✔️ project_template_task OK")

    if added_project_cols:
        print(f"✅ Auto-added in project: {', '.join(added_project_cols)}")
    else:
        print("✔️ project OK")


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
        Department.__table__,
        Position.__table__,
        User.__table__,
        Project.__table__,
        FormSchema.__table__,
        Submission.__table__,
        ProjectTemplate.__table__,
        ProjectTemplateTask.__table__,
        ProjectTemplateTaskDependency.__table__,
        TaskTemplate.__table__,
        SalesClient.__table__,
        SalesOpportunity.__table__,
        SalesActivity.__table__,
        SalesOpportunityComment.__table__,
        SalesOpportunityFile.__table__,
        SalesOpportunityEngagement.__table__,
        SalesOpportunityItem.__table__,
        QCWork.__table__,
        QCWorkDependency.__table__,
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
            new_user = User(username=u, password=p)
            new_user.issue_session_token()
            db.session.add(new_user)

    admin_user = User.query.filter_by(username="admin").first()
    if admin_user and not admin_user.role:
        admin_user.role = "Admin"

    # Ensure legacy accounts have activation flag and session tokens
    for user in User.query.filter(or_(User.session_token.is_(None), User.session_token == "")).all():
        user.issue_session_token()
    for user in User.query.filter(User.active.is_(None)).all():
        user.active = True

    get_or_create_default_task_form()

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
            min_photos_if_all_good=0,
            stage="Template QC",
            lift_type="MRL"
        )
        db.session.add(fs)

    if not ProjectTemplate.query.filter_by(name="NI Project").first():
        ni_template = ProjectTemplate(
            name="NI Project",
            description="Baseline new installation delivery with sequential QC checks.",
            created_by=admin_user.id if admin_user else None
        )
        db.session.add(ni_template)
        db.session.flush()

        sample_form = FormSchema.query.filter_by(name="QC - New Installation").first()

        stage_task = ProjectTemplateTask(
            template_id=ni_template.id,
            name="Initial Site Handover",
            description="Confirm site readiness and collect base documentation.",
            order_index=1,
            form_template_id=sample_form.id if sample_form else None,
            default_assignee_id=admin_user.id if admin_user else None,
            start_mode="immediate",
            duration_days=3,
            milestone="Order Milestone"
        )
        db.session.add(stage_task)
        db.session.flush()

        follow_up = ProjectTemplateTask(
            template_id=ni_template.id,
            name="Final Commissioning QC",
            description="Run through final QC checklist before handover.",
            order_index=2,
            form_template_id=sample_form.id if sample_form else None,
            default_assignee_id=admin_user.id if admin_user else None,
            start_mode="scheduled",
            planned_start_date=datetime.date.today() + datetime.timedelta(days=7),
            duration_days=2,
            milestone="Commissioning"
        )
        db.session.add(follow_up)
        db.session.flush()
        set_template_task_dependencies(follow_up, [stage_task.id])

    if SalesClient.query.count() == 0:
        owner = admin_user or User.query.first()
        client_entries = [
            SalesClient(
                display_name="Ted Watson",
                company_name="Watson Professional Services",
                email=generate_random_email(),
                phone=generate_random_phone(),
                tag="Priority",
                category="Company",
                owner=owner,
                lifecycle_stage="Prospect",
                description="Key account for premium installations.",
            ),
            SalesClient(
                display_name="Mrs. Vanmsee Krishna Naidu",
                company_name="Individual",
                email=generate_random_email(),
                phone=generate_random_phone(),
                tag="HOT",
                category="Individual",
                owner=owner,
                lifecycle_stage="Negotiation",
            ),
            SalesClient(
                display_name="Fortuna Building",
                company_name="Fortuna Holdings",
                email=generate_random_email(),
                phone=generate_random_phone(),
                tag="",
                category="Company",
                owner=owner,
                lifecycle_stage="Customer",
            ),
        ]
        db.session.add_all(client_entries)
        db.session.flush()

        lift_stages = get_pipeline_stages("lift")
        amc_stages = get_pipeline_stages("amc")
        parking_stages = get_pipeline_stages("parking")

        opportunity_entries = [
            SalesOpportunity(
                title="Lotus Avenue Site - 2 Cars",
                pipeline="lift",
                stage=lift_stages[0],
                temperature="cold",
                amount=1250000,
                owner=owner,
                client=client_entries[0],
                description="New enquiry for twin passenger lifts.",
            ),
            SalesOpportunity(
                title="Greenridge Heights Modernization",
                pipeline="lift",
                stage=lift_stages[2],
                temperature="warm",
                amount=980000,
                owner=owner,
                client=client_entries[1],
                description="Quote shared for modernization package.",
            ),
            SalesOpportunity(
                title="Metro Arcade AMC Renewal",
                pipeline="amc",
                stage=amc_stages[1],
                temperature="warm",
                amount=185000,
                owner=owner,
                client=client_entries[2],
            ),
            SalesOpportunity(
                title="Skyline Parking System Phase 2",
                pipeline="parking",
                stage=parking_stages[0],
                temperature="hot",
                amount=2250000,
                owner=owner,
                client=client_entries[0],
            ),
        ]
        db.session.add_all(opportunity_entries)
        db.session.flush()

        for entity in client_entries + opportunity_entries:
            db.session.add(SalesActivity(
                parent_type="client" if isinstance(entity, SalesClient) else "opportunity",
                parent_id=entity.id,
                actor=owner,
                title="Record created",
                notes="Automatically generated sample record to showcase the Sales workspace.",
            ))
            db.session.add(SalesActivity(
                parent_type="client" if isinstance(entity, SalesClient) else "opportunity",
                parent_id=entity.id,
                actor=owner,
                title="Intro note",
                notes="Add your updates here to keep the timeline current.",
            ))

    db.session.commit()
    synchronize_dependency_links()
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
            if not user.is_active:
                flash("Your account is deactivated. Please contact an administrator.", "error")
            else:
                user.issue_session_token()
                db.session.commit()
                login_user(user)
                session["session_token"] = user.session_token
                flash("Welcome back!", "success")
                return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")
    return render_template("login.html", category_label=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("session_token", None)
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


@app.route("/settings")
@login_required
def settings():
    tab = (request.args.get("tab") or "admin").lower()
    allowed_tabs = {"admin", "account"}
    active_tab = tab if tab in allowed_tabs else "admin"

    users = []
    departments = []
    positions = []
    department_options = []
    position_options = []

    if current_user.is_admin:
        departments = sorted(
            Department.query.order_by(Department.name.asc()).all(),
            key=lambda d: (d.full_name or "").lower(),
        )
        positions = sorted(
            Position.query.order_by(Position.title.asc()).all(),
            key=lambda p: (p.display_label or "").lower(),
        )
        department_options = departments
        position_options = positions
        users = User.query.order_by(User.username.asc()).all()

    return render_template(
        "settings.html",
        active_tab=active_tab,
        allowed_tabs=sorted(allowed_tabs),
        users=users,
        departments=departments,
        department_options=department_options,
        department_branches=DEPARTMENT_BRANCHES,
        positions=positions,
        position_options=position_options
    )


@app.route("/sales")
@login_required
def sales_home():
    today = datetime.date.today()
    month_start = today.replace(day=1)
    next_month_start = (month_start + datetime.timedelta(days=32)).replace(day=1)

    duration = request.args.get("duration", "month")
    period_label = {
        "month": "This Month",
        "quarter": "This Quarter",
        "ytd": "Year to Date",
    }.get(duration, "This Month")
    period_descriptions = {
        "month": "Current month snapshot",
        "quarter": "Performance for the current quarter",
        "ytd": "Year-to-date performance overview",
    }

    if duration == "quarter":
        quarter_index = (today.month - 1) // 3
        start_month = quarter_index * 3 + 1
        period_start = today.replace(month=start_month, day=1)
        next_quarter_month = start_month + 3
        if next_quarter_month > 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            period_end = today.replace(month=next_quarter_month, day=1)
    elif duration == "ytd":
        period_start = today.replace(month=1, day=1)
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        duration = "month"
        period_start = month_start
        period_end = next_month_start
    period_description = period_descriptions.get(duration, period_descriptions["month"])

    closed_won_clause = func.lower(SalesOpportunity.stage).like("closed won%")
    period_filters = [
        closed_won_clause,
        SalesOpportunity.updated_at >= period_start,
        SalesOpportunity.updated_at < period_end,
    ]

    won_count = SalesOpportunity.query.filter(*period_filters).count()
    won_value = (
        db.session.query(func.coalesce(func.sum(SalesOpportunity.amount), 0.0))
        .filter(*period_filters)
        .scalar()
        or 0.0
    )

    closed_lost_clause = func.lower(SalesOpportunity.stage).like("closed lost%")
    period_closed_total = (
        SalesOpportunity.query
        .filter(
            or_(closed_won_clause, closed_lost_clause),
            SalesOpportunity.updated_at >= period_start,
            SalesOpportunity.updated_at < period_end,
        )
        .count()
    )
    win_rate = (won_count / period_closed_total * 100) if period_closed_total else 0.0
    average_deal_value = (won_value / won_count) if won_count else 0.0

    open_pipeline_clause = ~func.lower(SalesOpportunity.stage).like("closed%")
    open_deals_count = SalesOpportunity.query.filter(open_pipeline_clause).count()
    open_pipeline_value = (
        db.session.query(func.coalesce(func.sum(SalesOpportunity.amount), 0.0))
        .filter(open_pipeline_clause)
        .scalar()
        or 0.0
    )

    stage_rows = (
        db.session.query(
            SalesOpportunity.stage,
            func.count(SalesOpportunity.id),
            func.coalesce(func.sum(SalesOpportunity.amount), 0.0),
        )
        .group_by(SalesOpportunity.stage)
        .order_by(func.count(SalesOpportunity.id).desc())
        .all()
    )
    stage_distribution = [
        {
            "stage": stage or "(No Stage)",
            "count": count,
            "value": float(total or 0.0),
        }
        for stage, count, total in stage_rows
    ]

    previous_months = []
    cursor = month_start
    for _ in range(3):
        cursor = (cursor - datetime.timedelta(days=1)).replace(day=1)
        next_cursor = (cursor + datetime.timedelta(days=32)).replace(day=1)
        total_value = (
            db.session.query(func.coalesce(func.sum(SalesOpportunity.amount), 0.0))
            .filter(
                closed_won_clause,
                SalesOpportunity.updated_at >= cursor,
                SalesOpportunity.updated_at < next_cursor,
            )
            .scalar()
            or 0.0
        )
        previous_months.append(
            {
                "label": cursor.strftime("%b %Y"),
                "total": float(total_value or 0.0),
            }
        )
    previous_months.reverse()

    team_rows = (
        db.session.query(
            SalesOpportunity.owner_id,
            func.count(SalesOpportunity.id),
            func.coalesce(func.sum(SalesOpportunity.amount), 0.0),
        )
        .filter(*period_filters)
        .group_by(SalesOpportunity.owner_id)
        .all()
    )

    team_breakdown = []
    owner_cache = {}
    for owner_id, deal_count, total_value in team_rows:
        if owner_id:
            owner = owner_cache.get(owner_id)
            if owner is None:
                owner = db.session.get(User, owner_id)
                owner_cache[owner_id] = owner
            owner_name = owner.display_name if owner else "Unknown"
        else:
            owner_name = "Unassigned"
        team_breakdown.append(
            {
                "owner": owner_name,
                "deals": deal_count,
                "value": float(total_value or 0.0),
            }
        )
    team_breakdown.sort(key=lambda row: row["value"], reverse=True)

    now = datetime.datetime.utcnow()
    due_activities = (
        SalesOpportunityEngagement.query
        .filter(
            SalesOpportunityEngagement.scheduled_for.isnot(None),
            SalesOpportunityEngagement.scheduled_for <= now,
        )
        .order_by(SalesOpportunityEngagement.scheduled_for.asc())
        .limit(10)
        .all()
    )

    return render_template(
        "sales/dashboard.html",
        won_count=won_count,
        won_value=won_value,
        win_rate=win_rate,
        average_deal_value=average_deal_value,
        open_deals_count=open_deals_count,
        open_pipeline_value=open_pipeline_value,
        stage_distribution=stage_distribution,
        previous_months=previous_months,
        team_breakdown=team_breakdown,
        due_activities=due_activities,
        format_currency=format_currency,
        selected_duration=duration,
        period_label=period_label,
        period_description=period_description,
    )


@app.route("/sales/clients")
@login_required
def sales_clients():
    clients = (
        SalesClient.query
        .order_by(SalesClient.display_name.asc())
        .all()
    )
    return render_template(
        "sales/clients_list.html",
        clients=clients,
        pipeline_map=SALES_PIPELINES,
        temperature_choices=SALES_TEMPERATURES,
        lifecycle_options=SALES_CLIENT_LIFECYCLE_STAGES,
    )


@app.route("/sales/clients/create", methods=["POST"])
@login_required
def sales_clients_create():
    name = (request.form.get("display_name") or "").strip()
    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("sales_clients"))

    lifecycle_value = normalize_lifecycle_stage(request.form.get("lifecycle_stage"))
    if lifecycle_value is None and SALES_CLIENT_LIFECYCLE_STAGES:
        lifecycle_value = SALES_CLIENT_LIFECYCLE_STAGES[0]

    client = SalesClient(
        display_name=name,
        company_name=(request.form.get("company_name") or "").strip() or None,
        email=(request.form.get("email") or "").strip() or None,
        phone=(request.form.get("phone") or "").strip() or None,
        category=(request.form.get("category") or "Individual").strip() or "Individual",
        description=(request.form.get("description") or "").strip() or None,
    )

    client.lifecycle_stage = lifecycle_value
    client.owner = current_user

    db.session.add(client)
    db.session.flush()
    log_sales_activity("client", client.id, "Client created")
    db.session.commit()
    flash(f"Client '{client.display_name}' created.", "success")
    return redirect(url_for("sales_client_detail", client_id=client.id))


@app.route("/sales/clients/<int:client_id>", methods=["GET", "POST"])
@login_required
def sales_client_detail(client_id):
    client = db.session.get(SalesClient, client_id)
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("sales_clients"))

    if request.method == "POST":
        action = request.form.get("form_action") or "update"
        if action == "update":
            client.display_name = (request.form.get("display_name") or "").strip() or client.display_name
            client.company_name = (request.form.get("company_name") or "").strip() or None
            client.email = (request.form.get("email") or "").strip() or None
            client.phone = (request.form.get("phone") or "").strip() or None
            client.category = (request.form.get("category") or "").strip() or "Individual"
            lifecycle_value = normalize_lifecycle_stage(request.form.get("lifecycle_stage"))
            client.lifecycle_stage = lifecycle_value
            client.description = (request.form.get("description") or "").strip() or None

            owner_id_raw = request.form.get("owner_id")
            if owner_id_raw:
                try:
                    client.owner = db.session.get(User, int(owner_id_raw))
                except (TypeError, ValueError):
                    client.owner = None
            else:
                client.owner = None

            log_sales_activity("client", client.id, "Client updated", actor=current_user)
            db.session.commit()
            flash("Client details updated.", "success")
            return redirect(url_for("sales_client_detail", client_id=client.id))

        elif action == "add_note":
            note_title = (request.form.get("note_title") or "").strip() or "Timeline update"
            note_body = (request.form.get("note_body") or "").strip() or None
            log_sales_activity("client", client.id, note_title, notes=note_body)
            db.session.commit()
            flash("Timeline note added.", "success")
            return redirect(url_for("sales_client_detail", client_id=client.id))

    activities = (
        SalesActivity.query
        .filter_by(parent_type="client", parent_id=client.id)
        .order_by(SalesActivity.created_at.desc())
        .all()
    )
    owners = User.query.order_by(User.first_name.asc(), User.last_name.asc()).all()
    open_opportunities = [opp for opp in client.opportunities if not opp.is_closed]
    all_clients = SalesClient.query.order_by(SalesClient.display_name.asc()).all()
    return render_template(
        "sales/client_detail.html",
        client=client,
        owners=owners,
        activities=activities,
        open_opportunities=open_opportunities,
        pipeline_map=SALES_PIPELINES,
        opportunity_clients=all_clients,
        temperature_choices=SALES_TEMPERATURES,
        lifecycle_options=SALES_CLIENT_LIFECYCLE_STAGES,
    )


@app.route("/sales/opportunities/<pipeline_key>")
@login_required
def sales_opportunities_pipeline(pipeline_key):
    pipeline_key = (pipeline_key or "lift").lower()
    config = get_pipeline_config(pipeline_key)
    stages = list(config["stages"])
    opportunities = (
        SalesOpportunity.query
        .filter(SalesOpportunity.pipeline == pipeline_key)
        .order_by(SalesOpportunity.stage.asc(), SalesOpportunity.updated_at.desc())
        .all()
    )

    grouped = {stage: [] for stage in stages}
    for opp in opportunities:
        grouped.setdefault(opp.stage, []).append(opp)

    for stage_list in grouped.values():
        stage_list.sort(key=lambda o: o.updated_at or o.created_at, reverse=True)

    owners = User.query.order_by(User.first_name.asc(), User.last_name.asc()).all()
    clients = SalesClient.query.order_by(SalesClient.display_name.asc()).all()
    temperature_choices = SALES_TEMPERATURES
    total_opportunities = sum(len(items) for items in grouped.values())

    stage_totals_raw = {}
    stage_currencies = {}
    stage_totals_display = {}
    for stage in stages:
        opportunities_in_stage = grouped.get(stage, [])
        total_amount = sum(opp.amount for opp in opportunities_in_stage if opp.amount is not None)
        currency = next((opp.currency for opp in opportunities_in_stage if opp.currency), "₹")
        stage_totals_raw[stage] = total_amount
        stage_currencies[stage] = currency
        stage_totals_display[stage] = format_currency(total_amount if opportunities_in_stage else 0, currency)

    return render_template(
        "sales/opportunity_board.html",
        pipeline_key=pipeline_key,
        pipeline_config=config,
        stages=stages,
        grouped=grouped,
        owners=owners,
        clients=clients,
        temperature_choices=temperature_choices,
        pipeline_map=SALES_PIPELINES,
        total_opportunities=total_opportunities,
        stage_totals=stage_totals_display,
        stage_totals_raw=stage_totals_raw,
        stage_currencies=stage_currencies,
    )


@app.route("/sales/opportunities/create", methods=["POST"])
@login_required
def sales_opportunities_create():
    title = (request.form.get("title") or "").strip()
    pipeline_key = (request.form.get("pipeline") or "lift").lower()
    config = get_pipeline_config(pipeline_key)

    if not title:
        flash("Opportunity title is required.", "error")
        return redirect(url_for("sales_opportunities_pipeline", pipeline_key=pipeline_key))

    stage_value = (request.form.get("stage") or config["stages"][0]).strip()
    if stage_value not in config["stages"]:
        stage_value = config["stages"][0]

    amount_raw = (request.form.get("amount") or "").strip()
    amount_value = None
    if amount_raw:
        try:
            amount_value = float(amount_raw)
        except ValueError:
            flash("Amount must be a valid number.", "error")
            return redirect(url_for("sales_opportunities_pipeline", pipeline_key=pipeline_key))

    opportunity = SalesOpportunity(
        title=title,
        pipeline=pipeline_key,
        stage=stage_value,
        temperature=(request.form.get("temperature") or "").strip() or None,
        amount=amount_value,
        description=(request.form.get("description") or "").strip() or None,
    )

    opportunity.owner = current_user

    client_id_raw = request.form.get("client_id")
    if client_id_raw:
        try:
            opportunity.client = db.session.get(SalesClient, int(client_id_raw))
        except (TypeError, ValueError):
            opportunity.client = None

    db.session.add(opportunity)
    db.session.flush()
    log_sales_activity("opportunity", opportunity.id, "Opportunity created")
    db.session.commit()
    flash("Opportunity created.", "success")
    return redirect(url_for("sales_opportunities_pipeline", pipeline_key=pipeline_key))


@app.route("/sales/opportunities/<int:opportunity_id>", methods=["GET", "POST"])
@login_required
def sales_opportunity_detail(opportunity_id):
    opportunity = db.session.get(SalesOpportunity, opportunity_id)
    if not opportunity:
        flash("Opportunity not found.", "error")
        return redirect(url_for("sales_opportunities_pipeline", pipeline_key="lift"))

    pipeline_key = opportunity.pipeline
    stages = get_pipeline_stages(pipeline_key)
    pipeline_config = get_pipeline_config(pipeline_key)
    current_stage_index = stages.index(opportunity.stage) if opportunity.stage in stages else 0

    if request.method == "POST":
        action = request.form.get("form_action") or "update"
        if action == "update":
            opportunity.title = (request.form.get("title") or "").strip() or opportunity.title
            stage_value = (request.form.get("stage") or stages[0]).strip()
            if stage_value not in stages:
                stage_value = stages[0]
            opportunity.stage = stage_value
            opportunity.temperature = (request.form.get("temperature") or "").strip() or None
            amount_raw = (request.form.get("amount") or "").strip()
            if amount_raw:
                try:
                    opportunity.amount = float(amount_raw)
                except ValueError:
                    flash("Amount must be a valid number.", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))
            else:
                opportunity.amount = None
            probability_raw = (request.form.get("probability") or "").strip()
            if probability_raw:
                try:
                    opportunity.probability = int(probability_raw)
                except ValueError:
                    flash("Probability must be a whole number.", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))
            else:
                opportunity.probability = None
            expected_close_raw = (request.form.get("expected_close_date") or "").strip()
            if expected_close_raw:
                try:
                    opportunity.expected_close_date = datetime.datetime.strptime(expected_close_raw, "%Y-%m-%d").date()
                except ValueError:
                    flash("Expected close date must be YYYY-MM-DD.", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))
            else:
                opportunity.expected_close_date = None
            opportunity.related_project = (request.form.get("related_project") or "").strip() or None
            opportunity.description = (request.form.get("description") or "").strip() or None

            client_id_raw = request.form.get("client_id")
            if client_id_raw:
                try:
                    opportunity.client = db.session.get(SalesClient, int(client_id_raw))
                except (TypeError, ValueError):
                    opportunity.client = None
            else:
                opportunity.client = None

            owner_id_raw = request.form.get("owner_id")
            if owner_id_raw:
                try:
                    opportunity.owner = db.session.get(User, int(owner_id_raw))
                except (TypeError, ValueError):
                    opportunity.owner = None
            else:
                opportunity.owner = None

            log_sales_activity("opportunity", opportunity.id, "Opportunity updated", actor=current_user)
            db.session.commit()
            flash("Opportunity updated.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

        elif action == "add_note":
            note_title = (request.form.get("note_title") or "").strip() or "Timeline update"
            note_body = (request.form.get("note_body") or "").strip() or None
            log_sales_activity("opportunity", opportunity.id, note_title, notes=note_body)
            db.session.commit()
            flash("Timeline note added.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

        elif action == "add_comment":
            body = (request.form.get("comment_body") or "").strip()
            if not body:
                flash("Comment cannot be empty.", "error")
                return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

            comment = SalesOpportunityComment(
                opportunity=opportunity,
                body=body,
                author=current_user if current_user.is_authenticated else None,
            )
            db.session.add(comment)

            snippet = body if len(body) <= 120 else f"{body[:117]}..."
            log_sales_activity(
                "opportunity",
                opportunity.id,
                "Comment added",
                notes=snippet,
                actor=current_user,
            )
            db.session.commit()
            flash("Comment saved.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

        elif action == "upload_file":
            uploaded_file = request.files.get("attachment")
            if not uploaded_file or not uploaded_file.filename:
                flash("Select a file to upload.", "error")
                return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

            safe_name = secure_filename(uploaded_file.filename)
            if not safe_name:
                flash("The selected file name is not valid.", "error")
                return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

            upload_root = os.path.join(app.config["UPLOAD_FOLDER"], "opportunities", str(opportunity.id))
            os.makedirs(upload_root, exist_ok=True)

            unique_name = f"{uuid.uuid4().hex}_{safe_name}"
            destination_path = os.path.join(upload_root, unique_name)
            uploaded_file.save(destination_path)

            static_root = os.path.join(BASE_DIR, "static")
            stored_relative = os.path.relpath(destination_path, static_root).replace(os.sep, "/")

            record = SalesOpportunityFile(
                opportunity=opportunity,
                original_filename=uploaded_file.filename,
                stored_path=stored_relative,
                content_type=uploaded_file.mimetype,
                file_size=os.path.getsize(destination_path),
                uploaded_by=current_user if current_user.is_authenticated else None,
            )
            db.session.add(record)

            log_sales_activity(
                "opportunity",
                opportunity.id,
                "File uploaded",
                notes=uploaded_file.filename,
                actor=current_user,
            )
            db.session.commit()
            flash("File uploaded.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

        elif action == "add_item":
            details = (request.form.get("item_details") or "").strip()
            lift_type = (request.form.get("item_lift_type") or "").strip()
            if lift_type and lift_type not in LIFT_TYPES:
                lift_type = None

            quantity_raw = (request.form.get("item_quantity") or "").strip()
            quantity_value = None
            if quantity_raw:
                try:
                    quantity_value = int(quantity_raw)
                    if quantity_value < 0:
                        raise ValueError
                except ValueError:
                    flash("Quantity must be a positive whole number.", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

            floors_value = (request.form.get("item_floors") or "").strip() or None
            cabin_finish = (request.form.get("item_cabin_finish") or "").strip() or None
            door_type = (request.form.get("item_door_type") or "").strip() or None
            structure_value = (request.form.get("item_structure") or "no").strip().lower()
            structure_required = structure_value in {"yes", "true", "1", "on"}

            if not any([details, lift_type, quantity_value, floors_value, cabin_finish, door_type]):
                flash("Provide at least one detail for the opportunity item.", "error")
                return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

            item = SalesOpportunityItem(
                opportunity=opportunity,
                details=details or None,
                lift_type=lift_type or None,
                quantity=quantity_value,
                floors=floors_value,
                cabin_finish=cabin_finish,
                door_type=door_type,
                structure_required=structure_required,
            )
            db.session.add(item)

            summary_bits = []
            if lift_type:
                summary_bits.append(f"Lift type: {lift_type}")
            if quantity_value is not None:
                summary_bits.append(f"Qty: {quantity_value}")
            if floors_value:
                summary_bits.append(f"Floors: {floors_value}")

            log_sales_activity(
                "opportunity",
                opportunity.id,
                "Item added",
                notes="; ".join(summary_bits) or None,
                actor=current_user,
            )
            db.session.commit()
            flash("Opportunity item added.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

        elif action == "schedule_activity":
            activity_type = (request.form.get("activity_type") or "meeting").strip().lower()
            if activity_type not in {"meeting", "call", "email"}:
                activity_type = "meeting"

            subject = (request.form.get("activity_subject") or "").strip()
            activity_date_raw = (request.form.get("activity_date") or "").strip()
            activity_time_raw = (request.form.get("activity_time") or "").strip()
            reminder_option = (request.form.get("reminder_option") or "").strip()
            if reminder_option not in {value for value, _ in OPPORTUNITY_REMINDER_OPTIONS}:
                reminder_option = ""
            additional_notes = (request.form.get("activity_notes") or "").strip()

            scheduled_parts = []
            if activity_date_raw:
                try:
                    scheduled_date = datetime.datetime.strptime(activity_date_raw, "%Y-%m-%d").date()
                    scheduled_parts.append(scheduled_date.strftime("%d %b %Y"))
                except ValueError:
                    flash("Provide a valid date for the activity (YYYY-MM-DD).", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))
            else:
                scheduled_date = None

            if activity_time_raw:
                try:
                    scheduled_time = datetime.datetime.strptime(activity_time_raw, "%H:%M").time()
                    scheduled_parts.append(scheduled_time.strftime("%I:%M %p"))
                except ValueError:
                    flash("Provide a valid time for the activity (HH:MM).", "error")
                    return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))
            else:
                scheduled_time = None

            scheduled_for = None
            if scheduled_date and scheduled_time:
                scheduled_for = datetime.datetime.combine(scheduled_date, scheduled_time)
            elif scheduled_date:
                scheduled_for = datetime.datetime.combine(scheduled_date, datetime.time())
            elif scheduled_time:
                scheduled_for = datetime.datetime.combine(datetime.date.today(), scheduled_time)

            engagement = SalesOpportunityEngagement(
                opportunity=opportunity,
                activity_type=activity_type,
                subject=subject or None,
                scheduled_for=scheduled_for,
                reminder_option=reminder_option or None,
                notes=additional_notes or None,
                created_by=current_user if current_user.is_authenticated else None,
            )
            db.session.add(engagement)

            details = []
            if scheduled_parts:
                details.append(f"Scheduled for {' '.join(scheduled_parts)}.")
            elif not subject:
                details.append("Scheduled without a specific date. Update when confirmed.")

            reminder_label = REMINDER_OPTION_LABELS.get(reminder_option or "", "No reminder")
            if reminder_option:
                details.append(f"Reminder set: {reminder_label}.")

            if additional_notes:
                details.append(additional_notes)

            activity_label = OPPORTUNITY_ACTIVITY_LABELS.get(activity_type, activity_type.title())
            title = subject or f"Scheduled {activity_label}"
            log_sales_activity(
                "opportunity",
                opportunity.id,
                title,
                notes="\n\n".join(details) if details else None,
                actor=current_user,
            )
            db.session.commit()
            flash("Activity scheduled.", "success")
            return redirect(url_for("sales_opportunity_detail", opportunity_id=opportunity.id))

    activities = (
        SalesActivity.query
        .filter_by(parent_type="opportunity", parent_id=opportunity.id)
        .order_by(SalesActivity.created_at.desc())
        .all()
    )
    comments = (
        SalesOpportunityComment.query
        .filter_by(opportunity_id=opportunity.id)
        .order_by(SalesOpportunityComment.created_at.desc())
        .all()
    )
    files = (
        SalesOpportunityFile.query
        .filter_by(opportunity_id=opportunity.id)
        .order_by(SalesOpportunityFile.created_at.desc())
        .all()
    )
    scheduled_activities = (
        SalesOpportunityEngagement.query
        .filter_by(opportunity_id=opportunity.id)
        .order_by(SalesOpportunityEngagement.created_at.desc())
        .all()
    )
    items = (
        SalesOpportunityItem.query
        .filter_by(opportunity_id=opportunity.id)
        .order_by(SalesOpportunityItem.created_at.desc())
        .all()
    )
    owners = User.query.order_by(User.first_name.asc(), User.last_name.asc()).all()
    clients = SalesClient.query.order_by(SalesClient.display_name.asc()).all()

    return render_template(
        "sales/opportunity_detail.html",
        opportunity=opportunity,
        pipeline_key=pipeline_key,
        pipeline_config=pipeline_config,
        stages=stages,
        current_stage_index=current_stage_index,
        owners=owners,
        clients=clients,
        activities=activities,
        comments=comments,
        files=files,
        scheduled_activities=scheduled_activities,
        items=items,
        reminder_options=OPPORTUNITY_REMINDER_OPTIONS,
        lift_types=LIFT_TYPES,
        temperature_choices=SALES_TEMPERATURES,
        pipeline_map=SALES_PIPELINES,
    )


@app.route("/sales/opportunities/<int:opportunity_id>/stage", methods=["POST"])
@login_required
def sales_opportunity_stage(opportunity_id):
    opportunity = db.session.get(SalesOpportunity, opportunity_id)
    accepts = request.accept_mimetypes.best
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or accepts == "application/json"
    if not opportunity:
        if wants_json:
            return jsonify({"success": False, "message": "Opportunity not found."}), 404
        flash("Opportunity not found.", "error")
        return redirect(url_for("sales_opportunities_pipeline", pipeline_key="lift"))

    pipeline_key = opportunity.pipeline
    stage = (request.form.get("stage") or "").strip()
    stages = get_pipeline_stages(pipeline_key)
    if stage not in stages:
        if wants_json:
            return jsonify({"success": False, "message": "Invalid stage selected."}), 400
        flash("Invalid stage selected.", "error")
        return redirect(url_for("sales_opportunities_pipeline", pipeline_key=pipeline_key))

    opportunity.stage = stage
    log_sales_activity("opportunity", opportunity.id, f"Stage moved to {stage}", actor=current_user)
    db.session.commit()

    if wants_json:
        return jsonify({"success": True, "stage": stage, "pipeline": pipeline_key})

    flash("Opportunity stage updated.", "success")
    return redirect(url_for("sales_opportunities_pipeline", pipeline_key=pipeline_key))

def _require_admin():
    if not current_user.is_admin:
        abort(403)


def _form_truthy(value):
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _department_cycle(department, candidate_parent):
    current = candidate_parent
    while current is not None:
        if current.id == department.id:
            return True
        current = current.parent
    return False


def _position_cycle(position, candidate_manager):
    current = candidate_manager
    while current is not None:
        if current.id == position.id:
            return True
        current = current.reports_to
    return False


# ---------------------- ADMINISTRATION ----------------------
@app.route("/admin/users")
@login_required
def admin_users():
    _require_admin()

    departments = sorted(
        Department.query.order_by(Department.name.asc()).all(),
        key=lambda d: (d.full_name or "").lower(),
    )
    positions = sorted(
        Position.query.order_by(Position.title.asc()).all(),
        key=lambda p: (p.display_label or "").lower(),
    )
    department_options = departments
    position_options = positions
    users = User.query.order_by(User.username.asc()).all()

    return render_template(
        "admin_users.html",
        users=users,
        departments=departments,
        department_options=department_options,
        department_branches=DEPARTMENT_BRANCHES,
        positions=positions,
        position_options=position_options,
        category_label="Admin",
        category_url=url_for("admin_users"),
    )


@app.route("/admin/users/create", methods=["POST"])
@login_required
def admin_users_create():
    _require_admin()

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    mobile_number = (request.form.get("mobile_number") or "").strip()
    role = (request.form.get("role") or "").strip()
    department_id_raw = request.form.get("department_id")
    position_id_raw = request.form.get("position_id")
    active_flag = _form_truthy(request.form.get("active", "1"))

    if not username or not password:
        flash("Username and password are required to create a user.", "error")
        return redirect(url_for("admin_users"))

    existing = (
        User.query.filter(func.lower(User.username) == username.lower()).first()
        if username
        else None
    )
    if existing:
        flash("A user with that username already exists.", "error")
        return redirect(url_for("admin_users"))

    department = None
    if department_id_raw:
        try:
            department = db.session.get(Department, int(department_id_raw))
        except (TypeError, ValueError):
            department = None

    position = None
    if position_id_raw:
        try:
            position = db.session.get(Position, int(position_id_raw))
        except (TypeError, ValueError):
            position = None

    user = User(
        username=username,
        password=password,
        first_name=first_name or None,
        last_name=last_name or None,
        email=email or None,
        mobile_number=mobile_number or None,
        role=role or None,
        department=department.name if department else None,
        active=active_flag,
    )
    if position:
        user.position = position
        if not user.department and position.department:
            user.department = position.department.name

    user.issue_session_token()
    db.session.add(user)
    db.session.commit()

    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("admin_users") + f"#user-{user.id}")


@app.route("/admin/users/<int:user_id>/update", methods=["POST"])
@login_required
def admin_users_update(user_id):
    _require_admin()

    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin_users"))

    action = request.form.get("action") or "update"
    if action == "reset_sessions":
        user.issue_session_token()
        db.session.commit()
        flash(f"All active sessions for '{user.username}' have been revoked.", "success")
        if user.id == current_user.id:
            session.pop("session_token", None)
            logout_user()
            flash("You signed yourself out of all sessions.", "info")
            return redirect(url_for("login"))
        return redirect(url_for("admin_users") + f"#user-{user.id}")

    username = (request.form.get("username") or "").strip()
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    mobile_number = (request.form.get("mobile_number") or "").strip()
    role = (request.form.get("role") or "").strip()
    department_id_raw = request.form.get("department_id")
    position_id_raw = request.form.get("position_id")
    active_flag = _form_truthy(request.form.get("active"))
    password = (request.form.get("password") or "").strip()

    if not username:
        flash("Username is required.", "error")
        return redirect(url_for("admin_users") + f"#user-{user.id}")

    if username.lower() != user.username.lower():
        existing = (
            User.query.filter(func.lower(User.username) == username.lower(), User.id != user.id).first()
        )
        if existing:
            flash("Another user already uses that username.", "error")
            return redirect(url_for("admin_users") + f"#user-{user.id}")

    department = None
    if department_id_raw:
        try:
            department = db.session.get(Department, int(department_id_raw))
        except (TypeError, ValueError):
            department = None

    position = None
    if position_id_raw:
        try:
            position = db.session.get(Position, int(position_id_raw))
        except (TypeError, ValueError):
            position = None

    if user.id == current_user.id and not active_flag:
        flash("You cannot deactivate your own account while logged in.", "error")
        return redirect(url_for("admin_users") + f"#user-{user.id}")

    user.username = username
    user.first_name = first_name or None
    user.last_name = last_name or None
    user.email = email or None
    user.mobile_number = mobile_number or None
    user.role = role or None
    user.department = department.name if department else None
    user.active = active_flag
    user.position = position
    if not user.department and position and position.department:
        user.department = position.department.name

    if password:
        user.password = password

    db.session.commit()
    flash(f"User '{user.username}' updated.", "success")
    return redirect(url_for("admin_users") + f"#user-{user.id}")


@app.route("/admin/departments/create", methods=["POST"])
@login_required
def admin_departments_create():
    _require_admin()

    name = (request.form.get("name") or "").strip()
    branch = (request.form.get("branch") or "").strip()
    description = (request.form.get("description") or "").strip()
    parent_id_raw = request.form.get("parent_id")
    active_flag = _form_truthy(request.form.get("active", "1"))

    if not name:
        flash("Department name is required.", "error")
        return redirect(url_for("admin_users") + "#departments")

    if branch not in DEPARTMENT_BRANCHES:
        branch = DEPARTMENT_BRANCHES[0]

    existing = Department.query.filter(func.lower(Department.name) == name.lower()).first()
    if existing:
        flash("A department with that name already exists.", "error")
        return redirect(url_for("admin_users") + "#departments")

    parent = None
    if parent_id_raw:
        try:
            parent = db.session.get(Department, int(parent_id_raw))
        except (TypeError, ValueError):
            parent = None

    department = Department(
        name=name,
        branch=branch,
        description=description or None,
        active=active_flag,
    )
    if parent:
        department.parent = parent

    db.session.add(department)
    db.session.commit()

    flash(f"Department '{department.full_name}' created.", "success")
    return redirect(url_for("admin_users") + f"#department-{department.id}")


@app.route("/admin/departments/<int:department_id>/update", methods=["POST"])
@login_required
def admin_departments_update(department_id):
    _require_admin()

    department = db.session.get(Department, department_id)
    if not department:
        flash("Department not found.", "error")
        return redirect(url_for("admin_users") + "#departments")

    name = (request.form.get("name") or "").strip()
    branch = (request.form.get("branch") or "").strip()
    description = (request.form.get("description") or "").strip()
    parent_id_raw = request.form.get("parent_id")
    active_flag = _form_truthy(request.form.get("active"))

    if not name:
        flash("Department name is required.", "error")
        return redirect(url_for("admin_users") + f"#department-{department.id}")

    if branch not in DEPARTMENT_BRANCHES:
        branch = DEPARTMENT_BRANCHES[0]

    if name.lower() != department.name.lower():
        existing = Department.query.filter(
            func.lower(Department.name) == name.lower(),
            Department.id != department.id,
        ).first()
        if existing:
            flash("Another department already uses that name.", "error")
            return redirect(url_for("admin_users") + f"#department-{department.id}")

    parent = None
    if parent_id_raw:
        try:
            parent = db.session.get(Department, int(parent_id_raw))
        except (TypeError, ValueError):
            parent = None
    if parent and _department_cycle(department, parent):
        flash("Cannot assign a department to one of its descendants.", "error")
        return redirect(url_for("admin_users") + f"#department-{department.id}")

    department.name = name
    department.branch = branch
    department.description = description or None
    department.active = active_flag
    department.parent = parent

    db.session.commit()
    flash(f"Department '{department.full_name}' updated.", "success")
    return redirect(url_for("admin_users") + f"#department-{department.id}")


@app.route("/admin/departments/<int:department_id>/delete", methods=["POST"])
@login_required
def admin_departments_delete(department_id):
    _require_admin()

    department = db.session.get(Department, department_id)
    if not department:
        flash("Department not found.", "error")
        return redirect(url_for("admin_users") + "#departments")

    for child in list(department.children or []):
        child.parent = None
    for position in list(department.positions or []):
        position.department = None

    db.session.delete(department)
    db.session.commit()

    flash(f"Department '{department.name}' deleted.", "success")
    return redirect(url_for("admin_users") + "#departments")


@app.route("/admin/positions/create", methods=["POST"])
@login_required
def admin_positions_create():
    _require_admin()

    title = (request.form.get("title") or "").strip()
    department_id_raw = request.form.get("department_id")
    reports_to_id_raw = request.form.get("reports_to_id")
    active_flag = _form_truthy(request.form.get("active", "1"))

    if not title:
        flash("Position title is required.", "error")
        return redirect(url_for("admin_users") + "#positions")

    department = None
    if department_id_raw:
        try:
            department = db.session.get(Department, int(department_id_raw))
        except (TypeError, ValueError):
            department = None

    manager = None
    if reports_to_id_raw:
        try:
            manager = db.session.get(Position, int(reports_to_id_raw))
        except (TypeError, ValueError):
            manager = None

    position = Position(
        title=title,
        department=department,
        reports_to=manager,
        active=active_flag,
    )
    db.session.add(position)
    db.session.commit()

    flash(f"Position '{position.display_label}' created.", "success")
    return redirect(url_for("admin_users") + f"#position-{position.id}")


@app.route("/admin/positions/<int:position_id>/update", methods=["POST"])
@login_required
def admin_positions_update(position_id):
    _require_admin()

    position = db.session.get(Position, position_id)
    if not position:
        flash("Position not found.", "error")
        return redirect(url_for("admin_users") + "#positions")

    title = (request.form.get("title") or "").strip()
    department_id_raw = request.form.get("department_id")
    reports_to_id_raw = request.form.get("reports_to_id")
    active_flag = _form_truthy(request.form.get("active"))

    if not title:
        flash("Position title is required.", "error")
        return redirect(url_for("admin_users") + f"#position-{position.id}")

    department = None
    if department_id_raw:
        try:
            department = db.session.get(Department, int(department_id_raw))
        except (TypeError, ValueError):
            department = None

    manager = None
    if reports_to_id_raw:
        try:
            manager = db.session.get(Position, int(reports_to_id_raw))
        except (TypeError, ValueError):
            manager = None

    if manager and _position_cycle(position, manager):
        flash("Cannot assign a position to report to itself or its descendants.", "error")
        return redirect(url_for("admin_users") + f"#position-{position.id}")

    position.title = title
    position.department = department
    position.reports_to = manager
    position.active = active_flag

    db.session.commit()
    flash(f"Position '{position.display_label}' updated.", "success")
    return redirect(url_for("admin_users") + f"#position-{position.id}")


@app.route("/admin/positions/<int:position_id>/delete", methods=["POST"])
@login_required
def admin_positions_delete(position_id):
    _require_admin()

    position = db.session.get(Position, position_id)
    if not position:
        flash("Position not found.", "error")
        return redirect(url_for("admin_users") + "#positions")

    for report in list(position.direct_reports or []):
        report.reports_to = None

    db.session.delete(position)
    db.session.commit()

    flash(f"Position '{position.title}' deleted.", "success")
    return redirect(url_for("admin_users") + "#positions")


def _build_task_overview(viewing_user: "User"):
    def _describe_due_date(target_date, now):
        if not target_date:
            return None, None, "none"
        if isinstance(target_date, datetime.date) and not isinstance(target_date, datetime.datetime):
            target_dt = datetime.datetime.combine(target_date, datetime.time.min)
        else:
            target_dt = target_date
        delta_days = (target_dt.date() - now.date()).days
        display = target_dt.strftime("%d %b %Y")
        if delta_days < 0:
            days = abs(delta_days)
            label = f"Overdue by {days} day{'s' if days != 1 else ''}"
            variant = "overdue"
        elif delta_days == 0:
            label = "Due today"
            variant = "today"
        elif delta_days == 1:
            label = "Due tomorrow"
            variant = "upcoming"
        else:
            label = f"Due in {delta_days} days"
            variant = "upcoming"
        return label, display, variant

    def _status_badge_class(key):
        mapping = {
            "open": "bg-amber-500/20 text-amber-100 border border-amber-500/40",
            "in_progress": "bg-sky-500/20 text-sky-100 border border-sky-500/40",
            "blocked": "bg-rose-500/20 text-rose-100 border border-rose-500/40",
            "scheduled": "bg-sky-500/20 text-sky-100 border border-sky-500/40",
            "overdue": "bg-rose-500/20 text-rose-100 border border-rose-500/40",
        }
        return mapping.get(key, "bg-slate-800/60 text-slate-200 border border-slate-700/60")

    def _due_badge_class(variant):
        mapping = {
            "overdue": "bg-rose-500/20 text-rose-100 border border-rose-500/40",
            "today": "bg-amber-500/20 text-amber-100 border border-amber-500/40",
            "upcoming": "bg-slate-800/60 text-slate-200 border border-slate-700/60",
        }
        return mapping.get(variant, "bg-slate-800/60 text-slate-200 border border-slate-700/60")

    def _ensure_module(modules_map, order, label, empty_message, description=None):
        module = modules_map.get(label)
        if module is None:
            module = {
                "module": label,
                "items": [],
                "empty_message": empty_message,
                "description": description,
            }
            modules_map[label] = module
            order.append(label)
        else:
            if description and not module.get("description"):
                module["description"] = description
        return module

    def _status_key(status):
        key = (status or "").strip().lower()
        if key == "in progress":
            return "in_progress"
        if key == "blocked":
            return "blocked"
        if key == "closed":
            return "closed"
        if key == "overdue":
            return "overdue"
        if key == "scheduled":
            return "scheduled"
        return "open"

    def _build_pending_modules(viewing_user, open_tasks, now):
        modules_map = OrderedDict()
        module_order = []

        _ensure_module(
            modules_map,
            module_order,
            "Projects",
            "No pending project tasks.",
            "Tasks from active projects assigned to you.",
        )
        _ensure_module(
            modules_map,
            module_order,
            "Sales",
            "No pending sales activities.",
            "Upcoming and overdue sales engagements on your opportunities.",
        )

        for task in open_tasks:
            module_label = "Projects" if task.project else "Quality Control"
            module_description = (
                "Project execution tasks awaiting your action."
                if module_label == "Projects"
                else "Quality inspections and tasks that still need attention."
            )
            module = _ensure_module(
                modules_map,
                module_order,
                module_label,
                "No pending QC tasks." if module_label == "Quality Control" else "No pending project tasks.",
                module_description,
            )

            due_label, due_display, due_variant = _describe_due_date(task.due_date, now)
            metadata = []
            if task.stage:
                metadata.append(task.stage)
            if task.lift_type:
                metadata.append(task.lift_type)
            if task.template and task.template.name:
                metadata.append(f"Form: {task.template.name}")
            if task.project and task.project.name:
                metadata.append(f"Project: {task.project.name}")

            module["items"].append(
                {
                    "title": task.display_title,
                    "subtitle": task.client_name or task.site_name,
                    "description": task.description,
                    "identifier": f"#{task.id}",
                    "status": task.status or "Open",
                    "status_class": _status_badge_class(_status_key(task.status)),
                    "due_description": due_label,
                    "due_display": due_display,
                    "due_class": _due_badge_class(due_variant),
                    "url": url_for("qc_work_detail", work_id=task.id),
                    "secondary_url": url_for("forms_fill", form_id=task.template_id, work_id=task.id)
                    if task.template_id
                    else None,
                    "secondary_label": "New Submission" if task.template_id else None,
                    "metadata": metadata,
                }
            )

        sales_module = modules_map.get("Sales")
        if sales_module is None:
            sales_module = _ensure_module(
                modules_map,
                module_order,
                "Sales",
                "No pending sales activities.",
                "Upcoming and overdue sales engagements on your opportunities.",
            )
        sales_items = (
            SalesOpportunityEngagement.query
            .join(SalesOpportunity, SalesOpportunity.id == SalesOpportunityEngagement.opportunity_id)
            .filter(SalesOpportunityEngagement.scheduled_for.isnot(None))
            .filter(
                or_(
                    SalesOpportunity.owner_id == viewing_user.id,
                    SalesOpportunityEngagement.created_by_id == viewing_user.id,
                )
            )
            .filter(func.lower(SalesOpportunity.status) != "closed")
            .order_by(SalesOpportunityEngagement.scheduled_for.asc(), SalesOpportunityEngagement.id.asc())
            .limit(50)
            .all()
        )

        for activity in sales_items:
            opportunity = activity.opportunity
            due_label, due_display, due_variant = _describe_due_date(activity.scheduled_for, now)
            status_key = "overdue" if due_variant == "overdue" else "scheduled"
            metadata = [activity.display_activity_type]
            subtitle = None
            if opportunity:
                subtitle = opportunity.title
                if opportunity.stage:
                    metadata.append(opportunity.stage)
                if opportunity.client and opportunity.client.display_name:
                    metadata.append(f"Client: {opportunity.client.display_name}")

            sales_module["items"].append(
                {
                    "title": activity.subject or activity.display_activity_type,
                    "subtitle": subtitle,
                    "description": activity.notes,
                    "identifier": f"Activity #{activity.id}",
                    "status": "Overdue" if status_key == "overdue" else "Scheduled",
                    "status_class": _status_badge_class(status_key),
                    "due_description": due_label,
                    "due_display": due_display,
                    "due_class": _due_badge_class(due_variant),
                    "url": url_for("sales_opportunity_detail", opportunity_id=opportunity.id)
                    if opportunity
                    else None,
                    "secondary_url": None,
                    "secondary_label": None,
                    "metadata": metadata,
                }
            )

        pending_modules = [modules_map[label] for label in module_order]
        pending_total = sum(len(module["items"]) for module in pending_modules)
        return pending_modules, pending_total

    status_order = case(
        (QCWork.status == "In Progress", 0),
        (QCWork.status == "Open", 1),
        (QCWork.status == "Blocked", 2),
        (QCWork.status == "Closed", 3),
        else_=4
    )
    now = datetime.datetime.utcnow()
    tasks = (
        QCWork.query
        .filter(QCWork.assigned_to == viewing_user.id)
        .order_by(status_order, QCWork.due_date.asc().nullslast(), QCWork.created_at.desc())
        .all()
    )
    actionable_tasks = [task for task in tasks if task.dependency_satisfied]
    blocked_tasks = [task for task in tasks if not task.dependency_satisfied and task.status != "Closed"]
    open_tasks = [task for task in actionable_tasks if task.status != "Closed"]
    closed_tasks = [task for task in tasks if task.status == "Closed"]

    open_count = sum(1 for task in open_tasks if (task.status or "").lower() in {"open", "blocked"})
    in_progress_count = sum(1 for task in open_tasks if (task.status or "").lower() == "in progress")
    overdue_count = sum(
        1
        for task in open_tasks
        if task.due_date and task.due_date < now and (task.status or "").lower() != "closed"
    )

    team_load = []
    if current_user.is_admin:
        users = User.query.order_by(User.username.asc()).all()
        assignments = {user.id: [] for user in users}
        for task in QCWork.query.filter(QCWork.assigned_to.isnot(None)).all():
            assignments.setdefault(task.assigned_to, []).append(task)

        for member in users:
            member_tasks = assignments.get(member.id, [])
            actionable = [task for task in member_tasks if task.dependency_satisfied]
            open_items = [task for task in actionable if task.status != "Closed"]
            team_load.append({
                "user": member,
                "total": len(actionable),
                "open": sum(1 for task in open_items if (task.status or "").lower() in {"open", "blocked"}),
                "in_progress": sum(1 for task in open_items if (task.status or "").lower() == "in progress"),
                "overdue": sum(
                    1 for task in open_items if task.due_date and task.due_date < now
                )
            })

    pending_modules, pending_total = _build_pending_modules(viewing_user, open_tasks, now)

    return {
        "open_tasks": open_tasks,
        "closed_tasks": closed_tasks,
        "open_count": open_count,
        "in_progress_count": in_progress_count,
        "overdue_count": overdue_count,
        "blocked_tasks": blocked_tasks,
        "team_load": team_load,
        "pending_modules": pending_modules,
        "pending_total": pending_total,
    }


@app.route("/dashboard")
@login_required
def dashboard():
    viewing_user = current_user
    selected_user_id = request.args.get("user_id", type=int)
    if selected_user_id and current_user.is_admin:
        candidate = db.session.get(User, selected_user_id)
        if candidate:
            viewing_user = candidate

    context = _build_task_overview(viewing_user)
    context.update({
        "viewing_user": viewing_user,
        "category_label": None,
        "page_mode": "dashboard",
        "switch_user_endpoint": "dashboard",
    })

    return render_template("dashboard.html", **context)


@app.route("/projects/pending")
@login_required
def projects_pending():
    viewing_user = current_user
    selected_user_id = request.args.get("user_id", type=int)
    if selected_user_id and current_user.is_admin:
        candidate = db.session.get(User, selected_user_id)
        if candidate:
            viewing_user = candidate

    context = _build_task_overview(viewing_user)
    context.update({
        "viewing_user": viewing_user,
        "category_label": "Projects",
        "category_url": url_for("projects_pending"),
        "page_mode": "projects",
        "switch_user_endpoint": "projects_pending",
    })

    project_modules = [
        module
        for module in context.get("pending_modules", [])
        if module.get("module") in {"Projects", "Quality Control"}
    ]
    context["pending_modules"] = project_modules
    context["pending_total"] = sum(len(module.get("items", [])) for module in project_modules)

    return render_template("dashboard.html", **context)


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
        try:
            schema = json.loads(request.form.get("schema_json", "[]"))
        except Exception:
            flash("Invalid JSON schema", "error")
            return render_template(
                "forms_edit.html",
                item=None,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=[],
                category_label="Forms",
                category_url=url_for('forms_list')
            )

        if not name:
            flash("Name is required", "error")
            return render_template(
                "forms_edit.html",
                item=None,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=schema,
                category_label="Forms",
                category_url=url_for('forms_list')
            )

        if stage and stage not in STAGES:
            flash("Select a valid Stage.", "error")
            return render_template(
                "forms_edit.html",
                item=None,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=schema,
                category_label="Forms",
                category_url=url_for('forms_list')
            )
        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid Lift Type.", "error")
            return render_template(
                "forms_edit.html",
                item=None,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=schema,
                category_label="Forms",
                category_url=url_for('forms_list')
            )

        item = FormSchema(
            name=name,
            schema_json=json.dumps(schema, ensure_ascii=False),
            min_photos_if_all_good=0,
            stage=stage or None,
            lift_type=lift_type or None
        )
        db.session.add(item)
        db.session.commit()
        flash("Form created", "success")
        return redirect(url_for("forms_list"))

    return render_template(
        "forms_edit.html",
        item=None,
        STAGES=STAGES,
        LIFT_TYPES=LIFT_TYPES,
        initial_schema=[],
        category_label="Forms",
        category_url=url_for('forms_list')
    )


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
        try:
            schema = json.loads(request.form.get("schema_json", "[]"))
        except Exception:
            flash("Invalid JSON schema", "error")
            return render_template(
                "forms_edit.html",
                item=item,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=[],
                category_label="Forms",
                category_url=url_for('forms_list')
            )

        if name:
            item.name = name
        item.schema_json = json.dumps(schema, ensure_ascii=False)

        if stage and stage not in STAGES:
            flash("Select a valid Stage.", "error")
            return render_template(
                "forms_edit.html",
                item=item,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=schema,
                category_label="Forms",
                category_url=url_for('forms_list')
            )
        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid Lift Type.", "error")
            return render_template(
                "forms_edit.html",
                item=item,
                STAGES=STAGES,
                LIFT_TYPES=LIFT_TYPES,
                initial_schema=schema,
                category_label="Forms",
                category_url=url_for('forms_list')
            )

        item.stage = stage or None
        item.lift_type = lift_type or None

        db.session.commit()
        flash("Form updated", "success")
        return redirect(url_for("forms_list"))

    return render_template(
        "forms_edit.html",
        item=item,
        STAGES=STAGES,
        LIFT_TYPES=LIFT_TYPES,
        initial_schema=json.loads(item.schema_json or "[]"),
        category_label="Forms",
        category_url=url_for('forms_list')
    )


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

    schema_raw = json.loads(fs.schema_json)
    sections, is_sectioned = _normalize_form_schema(schema_raw)
    if request.method == "POST":
        values = {} if is_sectioned else {}
        any_ng = False
        saved_photos = []
        per_item_photo_count = 0
        for s_idx, section in enumerate(sections):
            section_label = section.get("section") or f"Section {s_idx + 1}"
            section_items = section.get("items") or []
            section_entries = []
            if is_sectioned:
                values[section_label] = section_entries
            for f_idx, field in enumerate(section_items):
                label = field.get("label") or f"Item {f_idx + 1}"
                ftype = field.get("type")
                required = field.get("required", False)
                field_name = f"field__{s_idx}__{f_idx}"
                remark_name = f"remark__{s_idx}__{f_idx}"
                photo_name = f"photo__{s_idx}__{f_idx}"
                options = field.get("options") or []

                if ftype == "table":
                    rows = field.get("rows") or []
                    columns = field.get("columns") or []
                    table_values = []
                    missing_required = False
                    for r_idx, _ in enumerate(rows):
                        row_entries = []
                        for c_idx, _ in enumerate(columns):
                            cell_name = f"table__{s_idx}__{f_idx}__{r_idx}__{c_idx}"
                            cell_val = request.form.get(cell_name, "").strip()
                            if required and not cell_val:
                                missing_required = True
                            row_entries.append(cell_val)
                        table_values.append(row_entries)
                    if required and missing_required:
                        flash(f"'{label}' requires a value in every cell.", "error")
                        return render_template(
                            "form_render.html",
                            fs=fs,
                            sections=sections,
                            is_sectioned=is_sectioned,
                            category_label="Forms",
                            category_url=url_for('forms_list'),
                            subcategory_label=fs.name
                        )
                    table_payload = {
                        "type": "table",
                        "rows": rows,
                        "columns": columns,
                        "values": table_values,
                        "reference_image": field.get("reference_image") or ""
                    }
                    if is_sectioned:
                        section_entries.append({
                            "label": label,
                            "type": "table",
                            "table": table_payload
                        })
                    else:
                        values[label] = table_payload
                    continue

                if ftype in ["text", "textarea"]:
                    val = request.form.get(field_name, "").strip()
                    if required and not val:
                        flash(f"'{label}' is required", "error")
                        return render_template(
                            "form_render.html",
                            fs=fs,
                            sections=sections,
                            is_sectioned=is_sectioned,
                            category_label="Forms",
                            category_url=url_for('forms_list'),
                            subcategory_label=fs.name
                        )
                elif ftype == "select":
                    val = request.form.get(field_name, "")
                    if required and not val:
                        flash(f"'{label}' is required", "error")
                        return render_template(
                            "form_render.html",
                            fs=fs,
                            sections=sections,
                            is_sectioned=is_sectioned,
                            category_label="Forms",
                            category_url=url_for('forms_list'),
                            subcategory_label=fs.name
                        )
                    if options and val and val not in options:
                        flash(f"'{label}' has an invalid selection", "error")
                        return render_template(
                            "form_render.html",
                            fs=fs,
                            sections=sections,
                            is_sectioned=is_sectioned,
                            category_label="Forms",
                            category_url=url_for('forms_list'),
                            subcategory_label=fs.name
                        )
                    if isinstance(val, str) and val.strip().lower() == "ng":
                        any_ng = True
                else:
                    val = request.form.get(field_name, "").strip()

                remark_val = ""
                if field.get("allow_remark"):
                    remark_val = request.form.get(remark_name, "").strip()

                item_saved_photos = []
                valid_item_files = []
                if field.get("allow_photo"):
                    upload_list = request.files.getlist(photo_name)
                    for f in upload_list:
                        if f and f.filename:
                            ext = f.filename.rsplit(".", 1)[1].lower() if "." in f.filename else ""
                            if ext in {"png", "jpg", "jpeg", "webp"}:
                                valid_item_files.append(f)
                    if field.get("photo_required_if_ng") and isinstance(val, str) and val.strip().lower() == "ng" and not valid_item_files:
                        flash(f"Photo evidence is required for '{label}' when marked NG.", "error")
                        return render_template(
                            "form_render.html",
                            fs=fs,
                            sections=sections,
                            is_sectioned=is_sectioned,
                            category_label="Forms",
                            category_url=url_for('forms_list'),
                            subcategory_label=fs.name
                        )
                    for f in valid_item_files:
                        fname = secure_filename(f.filename)
                        dest = os.path.join(app.config["UPLOAD_FOLDER"], f"{datetime.datetime.utcnow().timestamp()}_{fname}")
                        f.save(dest)
                        saved_path = dest
                        item_saved_photos.append(saved_path)
                        saved_photos.append(saved_path)
                        per_item_photo_count += 1

                if is_sectioned:
                    section_entries.append({
                        "label": label,
                        "type": ftype,
                        "value": val,
                        "remark": remark_val or None,
                        "photos": item_saved_photos
                    })
                else:
                    values[label] = val
                    if field.get("allow_remark") and remark_val:
                        values[f"{label} - Remark"] = remark_val

        photo_files = request.files.getlist("photos")
        video_files = request.files.getlist("videos")
        saved_videos = []

        valid_photo_files = [
            p for p in photo_files
            if p and p.filename and "." in p.filename and p.filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "webp"}
        ]

        if any_ng and per_item_photo_count + len(valid_photo_files) == 0:
            flash("At least one photo is required when any item is marked NG.", "error")
            return render_template(
                "form_render.html",
                fs=fs,
                sections=sections,
                is_sectioned=is_sectioned,
                category_label="Forms",
                category_url=url_for('forms_list'),
                subcategory_label=fs.name
            )

        for f in valid_photo_files:
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

    return render_template(
        "form_render.html",
        fs=fs,
        sections=sections,
        is_sectioned=is_sectioned,
        category_label="Forms",
        category_url=url_for('forms_list'),
        subcategory_label=fs.name
    )


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
    data_sectioned = any(
        isinstance(entries, list) and entries and isinstance(entries[0], dict) and "label" in entries[0]
        for entries in (data.values() if isinstance(data, dict) else [])
    )
    return render_template("submission_view.html", sub=sub, data=data, photos=photos, videos=videos,
                           data_sectioned=data_sectioned,
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
        floors_raw = (request.form.get("floors") or "").strip()
        stops_raw = (request.form.get("stops") or "").strip()
        opening_type = (request.form.get("opening_type") or "").strip()
        location = (request.form.get("location") or "").strip()
        handover_raw = (request.form.get("handover_date") or "").strip()
        priority = (request.form.get("priority") or "").strip()
        structure_type = (request.form.get("structure_type") or "").strip()
        cladding_type = (request.form.get("cladding_type") or "").strip()
        cabin_finish = (request.form.get("cabin_finish") or "").strip()
        door_operation_type = (request.form.get("door_operation_type") or "").strip()
        door_finish = (request.form.get("door_finish") or "").strip()

        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("projects_list"))

        if lift_type and lift_type not in LIFT_TYPES:
            flash("Select a valid lift type.", "error")
            return redirect(url_for("projects_list"))

        floors = normalize_floor_label(floors_raw)

        stops = None
        if stops_raw:
            try:
                stops = int(stops_raw)
                if stops < 0:
                    raise ValueError
            except ValueError:
                flash("Number of stops must be a positive whole number.", "error")
                return redirect(url_for("projects_list"))

        if opening_type and opening_type not in PROJECT_OPENING_TYPES:
            flash("Choose a valid opening type.", "error")
            return redirect(url_for("projects_list"))

        if location and location not in PROJECT_LOCATIONS:
            flash("Choose a valid location.", "error")
            return redirect(url_for("projects_list"))

        if structure_type and structure_type not in PROJECT_STRUCTURE_TYPES:
            flash("Choose a valid structure type.", "error")
            return redirect(url_for("projects_list"))

        if cladding_type and cladding_type not in PROJECT_CLADDING_TYPES:
            flash("Choose a valid cladding type.", "error")
            return redirect(url_for("projects_list"))

        if cabin_finish and cabin_finish not in PROJECT_CABIN_FINISHES:
            flash("Choose a valid cabin finish.", "error")
            return redirect(url_for("projects_list"))

        if door_operation_type and door_operation_type not in PROJECT_DOOR_OPERATION_TYPES:
            flash("Choose a valid door operation type.", "error")
            return redirect(url_for("projects_list"))

        if door_finish and door_finish not in PROJECT_DOOR_FINISHES:
            flash("Choose a valid door finish.", "error")
            return redirect(url_for("projects_list"))

        if priority and priority not in PROJECT_PRIORITIES:
            flash("Choose a valid project priority.", "error")
            return redirect(url_for("projects_list"))

        handover_date = None
        if handover_raw:
            try:
                handover_date = datetime.datetime.strptime(handover_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("Provide a valid handover date (YYYY-MM-DD).", "error")
                return redirect(url_for("projects_list"))

        project = Project(
            name=name,
            site_name=site_name or None,
            site_address=site_address or None,
            customer_name=customer_name or None,
            lift_type=lift_type or None,
            floors=floors,
            stops=stops,
            opening_type=opening_type or None,
            location=location or None,
            handover_date=handover_date,
            priority=priority or None,
            structure_type=structure_type or None,
            cladding_type=cladding_type or None,
            cabin_finish=cabin_finish or None,
            door_operation_type=door_operation_type or None,
            door_finish=door_finish or None,
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
        LIFT_TYPES=LIFT_TYPES,
        PROJECT_PRIORITIES=PROJECT_PRIORITIES,
        PROJECT_OPENING_TYPES=PROJECT_OPENING_TYPES,
        PROJECT_LOCATIONS=PROJECT_LOCATIONS,
        PROJECT_STRUCTURE_TYPES=PROJECT_STRUCTURE_TYPES,
        PROJECT_CLADDING_TYPES=PROJECT_CLADDING_TYPES,
        PROJECT_CABIN_FINISHES=PROJECT_CABIN_FINISHES,
        PROJECT_DOOR_OPERATION_TYPES=PROJECT_DOOR_OPERATION_TYPES,
        PROJECT_DOOR_FINISHES=PROJECT_DOOR_FINISHES,
    )


@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    project_tasks = (
        QCWork.query
        .filter(QCWork.project_id == project.id)
        .order_by(QCWork.created_at.asc())
        .all()
    )
    active_tasks = [task for task in project_tasks if task.status != "Closed" and task.dependency_satisfied]
    waiting_tasks = [task for task in project_tasks if task.status != "Closed" and not task.dependency_satisfied]
    closed_tasks = [task for task in project_tasks if task.status == "Closed"]

    templates = ProjectTemplate.query.order_by(ProjectTemplate.name.asc()).all()
    form_templates = FormSchema.query.order_by(FormSchema.name.asc()).all()
    users = User.query.order_by(User.username.asc()).all()
    return render_template(
        "project_detail.html",
        project=project,
        active_tasks=active_tasks,
        waiting_tasks=waiting_tasks,
        closed_tasks=closed_tasks,
        all_tasks=project_tasks,
        templates=templates,
        form_templates=form_templates,
        users=users,
        LIFT_TYPES=LIFT_TYPES,
        DEFAULT_TASK_FORM_NAME=DEFAULT_TASK_FORM_NAME,
        STAGES=STAGES,
        TASK_MILESTONES=TASK_MILESTONES,
        PROJECT_PRIORITIES=PROJECT_PRIORITIES,
        PROJECT_OPENING_TYPES=PROJECT_OPENING_TYPES,
        PROJECT_LOCATIONS=PROJECT_LOCATIONS,
        PROJECT_STRUCTURE_TYPES=PROJECT_STRUCTURE_TYPES,
        PROJECT_CLADDING_TYPES=PROJECT_CLADDING_TYPES,
        PROJECT_CABIN_FINISHES=PROJECT_CABIN_FINISHES,
        PROJECT_DOOR_OPERATION_TYPES=PROJECT_DOOR_OPERATION_TYPES,
        PROJECT_DOOR_FINISHES=PROJECT_DOOR_FINISHES,
    )


@app.route("/projects/<int:project_id>/edit", methods=["POST"])
@login_required
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)

    name = (request.form.get("name") or "").strip()
    site_name = (request.form.get("site_name") or "").strip()
    site_address = (request.form.get("site_address") or "").strip()
    customer_name = (request.form.get("customer_name") or "").strip()
    lift_type = (request.form.get("lift_type") or "").strip()
    floors_raw = (request.form.get("floors") or "").strip()
    stops_raw = (request.form.get("stops") or "").strip()
    opening_type = (request.form.get("opening_type") or "").strip()
    location = (request.form.get("location") or "").strip()
    handover_raw = (request.form.get("handover_date") or "").strip()
    priority = (request.form.get("priority") or "").strip()
    structure_type = (request.form.get("structure_type") or "").strip()
    cladding_type = (request.form.get("cladding_type") or "").strip()
    cabin_finish = (request.form.get("cabin_finish") or "").strip()
    door_operation_type = (request.form.get("door_operation_type") or "").strip()
    door_finish = (request.form.get("door_finish") or "").strip()

    if not name:
        flash("Project name is required.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if lift_type and lift_type not in LIFT_TYPES:
        flash("Select a valid lift type.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    floors = normalize_floor_label(floors_raw)

    stops = None
    if stops_raw:
        try:
            stops = int(stops_raw)
            if stops < 0:
                raise ValueError
        except ValueError:
            flash("Number of stops must be a positive whole number.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    if opening_type and opening_type not in PROJECT_OPENING_TYPES:
        flash("Choose a valid opening type.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if location and location not in PROJECT_LOCATIONS:
        flash("Choose a valid location.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if structure_type and structure_type not in PROJECT_STRUCTURE_TYPES:
        flash("Choose a valid structure type.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if cladding_type and cladding_type not in PROJECT_CLADDING_TYPES:
        flash("Choose a valid cladding type.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if cabin_finish and cabin_finish not in PROJECT_CABIN_FINISHES:
        flash("Choose a valid cabin finish.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if door_operation_type and door_operation_type not in PROJECT_DOOR_OPERATION_TYPES:
        flash("Choose a valid door operation type.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if door_finish and door_finish not in PROJECT_DOOR_FINISHES:
        flash("Choose a valid door finish.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    if priority and priority not in PROJECT_PRIORITIES:
        flash("Choose a valid project priority.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    handover_date = None
    if handover_raw:
        try:
            handover_date = datetime.datetime.strptime(handover_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Provide a valid handover date (YYYY-MM-DD).", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    project.name = name
    project.site_name = site_name or None
    project.site_address = site_address or None
    project.customer_name = customer_name or None
    project.lift_type = lift_type or None
    project.floors = floors
    project.stops = stops
    project.opening_type = opening_type or None
    project.location = location or None
    project.handover_date = handover_date
    project.priority = priority or None
    project.structure_type = structure_type or None
    project.cladding_type = cladding_type or None
    project.cabin_finish = cabin_finish or None
    project.door_operation_type = door_operation_type or None
    project.door_finish = door_finish or None

    db.session.commit()
    flash("Project updated.", "success")
    return redirect(url_for("project_detail", project_id=project.id))


@app.route("/projects/<int:project_id>/apply-template", methods=["POST"])
@login_required
def project_apply_template(project_id):
    project = Project.query.get_or_404(project_id)
    template_id = request.form.get("template_id", type=int)
    if not template_id:
        flash("Select a template to apply.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    template = ProjectTemplate.query.get(template_id)
    if not template:
        flash("Template not found.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    fallback_form = get_or_create_default_task_form()
    existing_template_task_ids = {
        task.template_task_id
        for task in QCWork.query.filter(
            QCWork.project_id == project.id,
            QCWork.template_task_id.isnot(None)
        ).all()
        if task.template_task_id is not None
    }

    created = []
    task_lookup = {}
    ordered_template_tasks = sorted(template.tasks, key=lambda t: ((t.order_index or 0), t.id))

    for template_task in ordered_template_tasks:
        if template_task.id in existing_template_task_ids:
            continue

        dependency_tasks = []
        for dep_id in template_task.dependency_ids:
            dependency = task_lookup.get(dep_id)
            if not dependency:
                dependency = QCWork.query.filter_by(
                    project_id=project.id,
                    template_task_id=dep_id
                ).first()
            if dependency:
                dependency_tasks.append(dependency)

        form_template = template_task.form_template or fallback_form
        if not form_template:
            continue

        status = "Open"
        if any((dep.status or "").lower() != "closed" for dep in dependency_tasks):
            status = "Blocked"

        planned_start = template_task.planned_start_date
        planned_duration = template_task.duration_days
        due_date = None
        if planned_start and planned_duration:
            due_date = datetime.datetime.combine(planned_start, datetime.time.min) + datetime.timedelta(days=planned_duration)
        elif planned_duration and (template_task.start_mode or "immediate") != "after_previous":
            due_date = datetime.datetime.utcnow() + datetime.timedelta(days=planned_duration)
        elif template_task.planned_due_date:
            due_date = datetime.datetime.combine(template_task.planned_due_date, datetime.time.min)

        milestone_value = template_task.milestone or None

        new_task = QCWork(
            site_name=project.site_name or project.name,
            client_name=project.customer_name,
            address=project.site_address,
            template_id=form_template.id,
            stage=template_task.template.name,
            lift_type=project.lift_type or form_template.lift_type,
            project_id=project.id,
            created_by=current_user.id,
            assigned_to=template_task.default_assignee_id,
            name=template_task.name,
            description=template_task.description,
            template_task_id=template_task.id,
            status=status,
            due_date=due_date,
            planned_start_date=planned_start,
            planned_duration_days=planned_duration,
            milestone=milestone_value
        )
        db.session.add(new_task)
        db.session.flush()
        set_qc_work_dependencies(new_task, [dep.id for dep in dependency_tasks])

        task_lookup[template_task.id] = new_task
        created.append(new_task)

        log_work_event(
            new_task.id,
            "created_from_project_template",
            actor_id=current_user.id,
            details={
                "project_id": project.id,
                "template": template.name,
                "template_task": template_task.name,
                "planned_start_date": planned_start.strftime("%Y-%m-%d") if planned_start else None,
                "planned_duration_days": planned_duration,
                "milestone": milestone_value,
                "due_date": due_date.strftime("%Y-%m-%d") if due_date else None
            }
        )
        if template_task.default_assignee_id:
            log_work_event(
                new_task.id,
                "assigned",
                actor_id=current_user.id,
                details={"assigned_to": template_task.default_assignee_id}
            )
        if status == "Blocked" and dependency_tasks:
            log_work_event(
                new_task.id,
                "waiting_on_dependency",
                actor_id=current_user.id,
                details={"depends_on": [dep.id for dep in dependency_tasks]}
            )

    if not created:
        flash("No new tasks were created – they may already exist for this project.", "info")
        return redirect(url_for("project_detail", project_id=project.id))

    db.session.commit()
    flash(f"Added {len(created)} tasks from template {template.name}.", "success")
    return redirect(url_for("project_detail", project_id=project.id))


@app.route("/projects/<int:project_id>/tasks/create", methods=["POST"])
@login_required
def project_task_create(project_id):
    project = Project.query.get_or_404(project_id)
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    form_template_id = request.form.get("form_template_id", type=int)
    assigned_to = request.form.get("assigned_to", type=int)
    due = (request.form.get("due_date") or "").strip()
    depends_on_ids = []
    for raw in request.form.getlist("depends_on_ids"):
        try:
            dep_id = int(raw)
        except (TypeError, ValueError):
            continue
        if dep_id not in depends_on_ids:
            depends_on_ids.append(dep_id)
    stage = (request.form.get("stage") or "").strip()
    planned_start = (request.form.get("planned_start_date") or "").strip()
    duration_raw = (request.form.get("planned_duration_days") or "").strip()
    milestone_value = (request.form.get("milestone") or "").strip()

    if not name:
        flash("Provide a task name.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    form_template = db.session.get(FormSchema, form_template_id) if form_template_id else None
    if not form_template:
        form_template = get_or_create_default_task_form()
    if not form_template:
        flash("Set up a form template before creating tasks.", "error")
        return redirect(url_for("project_detail", project_id=project.id))

    due_dt = None
    if due:
        try:
            due_dt = datetime.datetime.strptime(due, "%Y-%m-%d")
        except Exception:
            flash("Invalid due date format.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    planned_start_date = None
    if planned_start:
        try:
            planned_start_date = datetime.datetime.strptime(planned_start, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid planned start date format.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    duration_days = None
    if duration_raw:
        try:
            duration_days = int(duration_raw)
        except ValueError:
            flash("Duration must be a whole number of days.", "error")
            return redirect(url_for("project_detail", project_id=project.id))
        if duration_days < 0:
            flash("Duration must be zero or positive.", "error")
            return redirect(url_for("project_detail", project_id=project.id))

    if due_dt is None:
        if planned_start_date and duration_days is not None:
            due_dt = datetime.datetime.combine(planned_start_date, datetime.time.min) + datetime.timedelta(days=duration_days)
        elif duration_days is not None:
            due_dt = datetime.datetime.utcnow() + datetime.timedelta(days=duration_days)

    dependency_tasks = []
    if depends_on_ids:
        dependencies = (
            QCWork.query
            .filter(QCWork.project_id == project.id, QCWork.id.in_(depends_on_ids))
            .all()
        )
        found_ids = {dep.id for dep in dependencies}
        missing = [dep_id for dep_id in depends_on_ids if dep_id not in found_ids]
        if missing:
            flash("Choose dependencies from the same project.", "error")
            return redirect(url_for("project_detail", project_id=project.id))
        id_map = {dep.id: dep for dep in dependencies}
        dependency_tasks = [id_map[dep_id] for dep_id in depends_on_ids if dep_id in id_map]

    status = "Open"
    if any((dep.status or "").lower() != "closed" for dep in dependency_tasks):
        status = "Blocked"

    work = QCWork(
        site_name=project.site_name or project.name,
        client_name=project.customer_name,
        address=project.site_address,
        template_id=form_template.id,
        stage=stage or None,
        lift_type=project.lift_type or form_template.lift_type,
        project_id=project.id,
        due_date=due_dt,
        created_by=current_user.id,
        assigned_to=assigned_to,
        name=name,
        description=description or None,
        status=status,
        planned_start_date=planned_start_date,
        planned_duration_days=duration_days,
        milestone=milestone_value or None
    )
    db.session.add(work)
    db.session.flush()
    set_qc_work_dependencies(work, [dep.id for dep in dependency_tasks])
    log_work_event(
        work.id,
        "created_from_project",
        actor_id=current_user.id,
        details={
            "project_id": project.id,
            "stage": stage or None,
            "assigned_to": assigned_to,
            "due_date": work.due_date.strftime("%Y-%m-%d") if work.due_date else None,
            "dependencies": [dep.id for dep in dependency_tasks],
            "planned_start_date": planned_start_date.strftime("%Y-%m-%d") if planned_start_date else None,
            "planned_duration_days": duration_days,
            "milestone": work.milestone
        }
    )
    if assigned_to:
        log_work_event(
            work.id,
            "assigned",
            actor_id=current_user.id,
            details={"assigned_to": assigned_to}
        )
    if status == "Blocked" and dependency_tasks:
        log_work_event(
            work.id,
            "waiting_on_dependency",
            actor_id=current_user.id,
            details={"depends_on": [dep.id for dep in dependency_tasks]}
        )
    db.session.commit()
    flash("Project task created.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/project-templates", methods=["GET", "POST"])
@login_required
def project_templates():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Template name is required.", "error")
        else:
            template = ProjectTemplate(
                name=name,
                description=description or None,
                created_by=current_user.id
            )
            db.session.add(template)
            db.session.commit()
            flash("Project template created.", "success")
            return redirect(url_for("project_template_detail", template_id=template.id))

    templates = ProjectTemplate.query.order_by(ProjectTemplate.name.asc()).all()
    template_counts = {
        tpl.id: len(tpl.tasks)
        for tpl in templates
    }
    task_templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()
    return render_template(
        "project_templates.html",
        templates=templates,
        template_counts=template_counts,
        task_templates=task_templates,
        DEFAULT_TASK_FORM_NAME=DEFAULT_TASK_FORM_NAME
    )


@app.route("/project-templates/<int:template_id>", methods=["GET", "POST"])
@login_required
def project_template_detail(template_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    users = User.query.order_by(User.username.asc()).all()
    forms = FormSchema.query.order_by(FormSchema.name.asc()).all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        requested_order = request.form.get("order_index", type=int)
        depends_on_ids = []
        for raw in request.form.getlist("depends_on_ids"):
            try:
                dep_id = int(raw)
            except (TypeError, ValueError):
                continue
            if dep_id not in depends_on_ids:
                depends_on_ids.append(dep_id)
        default_assignee_id = request.form.get("default_assignee_id", type=int)
        form_template_id = request.form.get("form_template_id", type=int)

        if not name:
            flash("Task name is required.", "error")
            return redirect(url_for("project_template_detail", template_id=template.id))

        if depends_on_ids:
            dependencies = ProjectTemplateTask.query.filter(
                ProjectTemplateTask.template_id == template.id,
                ProjectTemplateTask.id.in_(depends_on_ids)
            ).all()
            if len(dependencies) != len(depends_on_ids):
                flash("Select dependencies from the same template.", "error")
                return redirect(url_for("project_template_detail", template_id=template.id))

        if default_assignee_id and not db.session.get(User, default_assignee_id):
            flash("Choose a valid default assignee.", "error")
            return redirect(url_for("project_template_detail", template_id=template.id))

        if form_template_id and not db.session.get(FormSchema, form_template_id):
            flash("Choose a valid form template.", "error")
            return redirect(url_for("project_template_detail", template_id=template.id))

        start_mode, planned_start_date, duration_value, milestone_value, timing_error = _extract_task_timing(request.form)
        if timing_error:
            flash(timing_error, "error")
            return redirect(url_for("project_template_detail", template_id=template.id))

        existing_tasks = ProjectTemplateTask.query.filter_by(template_id=template.id).order_by(
            ProjectTemplateTask.order_index.asc(),
            ProjectTemplateTask.id.asc()
        ).all()
        max_position = len(existing_tasks) + 1
        if not requested_order or requested_order < 1:
            requested_order = max_position
        else:
            requested_order = min(requested_order, max_position)

        shifts = False
        for idx, existing in enumerate(existing_tasks, start=1):
            new_index = idx if idx < requested_order else idx + 1
            if existing.order_index != new_index:
                shifts = True
            existing.order_index = new_index

        task = ProjectTemplateTask(
            template_id=template.id,
            name=name,
            description=description or None,
            order_index=requested_order,
            default_assignee_id=default_assignee_id,
            form_template_id=form_template_id,
            start_mode=start_mode,
            planned_start_date=planned_start_date,
            duration_days=duration_value,
            milestone=milestone_value
        )
        db.session.add(task)
        db.session.flush()
        set_template_task_dependencies(task, depends_on_ids)
        normalize_template_task_order(template.id)
        db.session.commit()
        message = "Template task added."
        if shifts:
            message = "Template task added. Existing tasks were re-ordered automatically."
        flash(message, "success")
        return redirect(url_for("project_template_detail", template_id=template.id))

    tasks = ProjectTemplateTask.query.filter_by(template_id=template.id).order_by(
        ProjectTemplateTask.order_index.asc(),
        ProjectTemplateTask.id.asc()
    ).all()
    return render_template(
        "project_template_detail.html",
        template=template,
        tasks=tasks,
        users=users,
        forms=forms,
        DEFAULT_TASK_FORM_NAME=DEFAULT_TASK_FORM_NAME,
        TASK_MILESTONES=TASK_MILESTONES
    )


@app.route("/project-templates/<int:template_id>/update", methods=["POST"])
@login_required
def project_template_update(template_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    name = (request.form.get("template_name") or request.form.get("name") or "").strip()
    description = (request.form.get("template_description") or request.form.get("description") or "").strip()
    if not name:
        flash("Template name is required.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    template.name = name
    template.description = description or None
    db.session.commit()
    flash("Template details saved.", "success")
    return redirect(url_for("project_template_detail", template_id=template.id))


@app.route("/project-templates/<int:template_id>/save-as-task-template", methods=["POST"])
@login_required
def project_template_save_as_task_template(template_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    name = (request.form.get("task_template_name") or "").strip()
    description = (request.form.get("task_template_description") or "").strip()
    if not name:
        flash("Provide a name for the task template.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    existing = TaskTemplate.query.filter(func.lower(TaskTemplate.name) == name.lower()).first()
    if existing:
        flash("A task template with that name already exists.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    blueprint = build_task_template_blueprint(template)
    task_template = TaskTemplate(
        name=name,
        description=description or None,
        blueprint_json=json.dumps(blueprint, ensure_ascii=False),
        created_from_template_id=template.id,
        created_by=current_user.id
    )
    db.session.add(task_template)
    db.session.commit()
    flash("Task template saved for future reuse.", "success")
    return redirect(url_for("project_template_detail", template_id=template.id))


@app.route("/task-templates/<int:task_template_id>/create-project-template", methods=["POST"])
@login_required
def create_project_template_from_task_template(task_template_id):
    task_template = TaskTemplate.query.get_or_404(task_template_id)
    name = (request.form.get("name") or task_template.name or "").strip()
    description = (request.form.get("description") or task_template.description or "").strip()
    if not name:
        flash("Template name is required.", "error")
        return redirect(url_for("project_templates"))

    new_template = ProjectTemplate(
        name=name,
        description=description or None,
        created_by=current_user.id
    )
    db.session.add(new_template)
    db.session.flush()

    try:
        blueprint = json.loads(task_template.blueprint_json or "[]")
    except json.JSONDecodeError:
        blueprint = []

    apply_blueprint_to_template(new_template, blueprint)
    db.session.commit()
    flash(f"Project template '{name}' created from task template.", "success")
    return redirect(url_for("project_template_detail", template_id=new_template.id))


@app.route("/project-templates/<int:template_id>/delete", methods=["POST"])
@login_required
def project_template_delete(template_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    if not (current_user.is_admin or template.created_by == current_user.id):
        flash("You do not have permission to delete this template.", "error")
        return redirect(url_for("project_templates"))

    name = template.name or f'Template {template.id}'
    db.session.delete(template)
    db.session.commit()
    flash(f"Project template '{name}' deleted.", "success")
    return redirect(url_for("project_templates"))



# ---- Template task management helpers ----
@app.route("/project-templates/<int:template_id>/tasks/<int:task_id>/edit", methods=["POST"])
@login_required
def project_template_task_edit(template_id, task_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    task = ProjectTemplateTask.query.filter_by(id=task_id, template_id=template.id).first()
    if not task:
        flash("Task not found for this template.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    requested_order = request.form.get("order_index", type=int)
    depends_on_ids = []
    for raw in request.form.getlist("depends_on_ids"):
        try:
            dep_id = int(raw)
        except (TypeError, ValueError):
            continue
        if dep_id not in depends_on_ids:
            depends_on_ids.append(dep_id)
    default_assignee_id = request.form.get("default_assignee_id", type=int)
    form_template_id = request.form.get("form_template_id", type=int)

    if not name:
        flash("Task name is required.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    if depends_on_ids:
        if task.id in depends_on_ids:
            flash("A task cannot depend on itself.", "error")
            return redirect(url_for("project_template_detail", template_id=template.id))
        dependencies = ProjectTemplateTask.query.filter(
            ProjectTemplateTask.template_id == template.id,
            ProjectTemplateTask.id.in_(depends_on_ids)
        ).all()
        if len(dependencies) != len(depends_on_ids):
            flash("Select dependencies from the same template.", "error")
            return redirect(url_for("project_template_detail", template_id=template.id))

    if default_assignee_id and not db.session.get(User, default_assignee_id):
        flash("Choose a valid default assignee.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    if form_template_id and not db.session.get(FormSchema, form_template_id):
        flash("Choose a valid form template.", "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    start_mode, planned_start_date, duration_value, milestone_value, timing_error = _extract_task_timing(request.form)
    if timing_error:
        flash(timing_error, "error")
        return redirect(url_for("project_template_detail", template_id=template.id))

    existing_tasks = ProjectTemplateTask.query.filter_by(template_id=template.id).order_by(
        ProjectTemplateTask.order_index.asc(),
        ProjectTemplateTask.id.asc()
    ).all()
    others = [t for t in existing_tasks if t.id != task.id]
    max_position = len(others) + 1
    if not requested_order or requested_order < 1:
        requested_order = max_position if task.order_index is None else min(task.order_index, max_position)
    else:
        requested_order = min(requested_order, max_position)

    for idx, existing in enumerate(others, start=1):
        new_index = idx if idx < requested_order else idx + 1
        existing.order_index = new_index

    task.name = name
    task.description = description or None
    task.order_index = requested_order
    task.default_assignee_id = default_assignee_id
    task.form_template_id = form_template_id
    task.start_mode = start_mode
    task.planned_start_date = planned_start_date
    task.duration_days = duration_value
    task.milestone = milestone_value

    set_template_task_dependencies(task, depends_on_ids)

    normalize_template_task_order(template.id)
    db.session.commit()
    flash("Template task updated.", "success")
    return redirect(url_for("project_template_detail", template_id=template.id))


@app.route("/project-templates/<int:template_id>/tasks/reorder", methods=["POST"])
@login_required
def project_template_task_reorder(template_id):
    template = ProjectTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True) or {}
    ordered_ids = payload.get("ordered_ids")
    if not isinstance(ordered_ids, list) or not ordered_ids:
        return jsonify({"ok": False, "message": "No ordering received."}), 400

    try:
        ordered_ids = [int(task_id) for task_id in ordered_ids]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Invalid task identifiers."}), 400

    template_task_ids = {task.id for task in template.tasks}
    if set(ordered_ids) != template_task_ids:
        return jsonify({"ok": False, "message": "Ordering must include all template tasks."}), 400

    tasks = {
        task.id: task for task in ProjectTemplateTask.query.filter(
            ProjectTemplateTask.template_id == template.id,
            ProjectTemplateTask.id.in_(ordered_ids)
        ).all()
    }

    if len(tasks) != len(ordered_ids):
        return jsonify({"ok": False, "message": "One or more tasks were not found."}), 400

    for idx, task_id in enumerate(ordered_ids, start=1):
        tasks[task_id].order_index = idx

    db.session.commit()
    return jsonify({"ok": True})


# ---------------------- SRT MODULE ----------------------
@app.route("/srt")
@login_required
def srt_overview():
    status_filter = request.args.get("status", "all").lower()
    today = datetime.date.today()

    tasks = []
    for task in SRT_SAMPLE_TASKS:
        due_in = (task["due_date"] - today).days if task.get("due_date") else None
        tasks.append({**task, "due_in": due_in})

    if status_filter in {"pending", "open"}:
        filtered_tasks = [task for task in tasks if task["status"].lower() != "closed"]
    elif status_filter in {"in-progress", "in_progress"}:
        filtered_tasks = [task for task in tasks if task["status"].lower() == "in progress"]
    elif status_filter in {"closed", "completed"}:
        filtered_tasks = [task for task in tasks if task["status"].lower() == "closed"]
    else:
        filtered_tasks = list(tasks)

    summary = {
        "total_pending": sum(1 for task in tasks if task["status"].lower() != "closed"),
        "high_priority": sum(1 for task in tasks if task["priority"].lower() == "high" and task["status"].lower() != "closed"),
        "due_this_week": sum(
            1
            for task in tasks
            if task["status"].lower() != "closed"
            and task.get("due_in") is not None
            and 0 <= task["due_in"] <= 7
        ),
        "oldest_age": max((task["age_days"] for task in tasks), default=0),
    }

    return render_template(
        "srt_overview.html",
        tasks=filtered_tasks,
        status_filter=status_filter,
        summary=summary,
    )


@app.route("/srt/form-templates", methods=["GET", "POST"])
@login_required
def srt_form_templates():
    global SRT_FORM_TEMPLATES

    if request.method == "POST":
        action = request.form.get("action", "").lower()
        name = (request.form.get("name") or "").strip()
        category = (request.form.get("category") or "General").strip() or "General"
        description = (request.form.get("description") or "").strip()
        usage_count_raw = request.form.get("usage_count")
        last_updated_raw = request.form.get("last_updated")
        schema_json = (request.form.get("schema_json") or "").strip()

        usage_count = 0
        try:
            if usage_count_raw is not None and usage_count_raw != "":
                usage_count = max(0, int(usage_count_raw))
        except ValueError:
            usage_count = 0

        last_updated = datetime.date.today()
        if last_updated_raw:
            try:
                last_updated = datetime.datetime.strptime(last_updated_raw, "%Y-%m-%d").date()
            except ValueError:
                last_updated = datetime.date.today()

        schema_payload = _default_srt_schema()
        if schema_json:
            try:
                loaded = json.loads(schema_json)
            except json.JSONDecodeError:
                loaded = _default_srt_schema()
            schema_payload = loaded

        schema = copy.deepcopy(_normalise_srt_schema(schema_payload))

        if action == "create":
            if not name:
                flash("Template name is required.", "error")
            else:
                template_id = slugify(name)
                if any(template["id"] == template_id for template in SRT_FORM_TEMPLATES):
                    template_id = f"{template_id}-{_random_digits(4)}"

                SRT_FORM_TEMPLATES.append(
                    {
                        "id": template_id,
                        "name": name,
                        "category": category or "General",
                        "description": description,
                        "usage_count": usage_count,
                        "last_updated": last_updated,
                        "schema": schema,
                    }
                )
                flash("SRT form template added.", "success")

        elif action == "delete":
            template_id = request.form.get("template_id")
            if not template_id:
                flash("Template not found.", "error")
            else:
                updated_templates = [
                    item for item in SRT_FORM_TEMPLATES if item["id"] != template_id
                ]
                if len(updated_templates) == len(SRT_FORM_TEMPLATES):
                    flash("Template not found.", "error")
                else:
                    SRT_FORM_TEMPLATES = updated_templates
                    flash("Template deleted.", "success")

        elif action == "update":
            template_id = request.form.get("template_id")
            template = next((item for item in SRT_FORM_TEMPLATES if item["id"] == template_id), None)
            if not template:
                flash("Template not found.", "error")
            elif not name:
                flash("Template name is required.", "error")
            else:
                template.update(
                    {
                        "name": name,
                        "category": category or "General",
                        "description": description,
                        "usage_count": usage_count,
                        "last_updated": last_updated,
                        "schema": schema,
                    }
                )
                flash("Template updated.", "success")

        return redirect(url_for("srt_form_templates"))

    templates_normalised = []
    for template in SRT_FORM_TEMPLATES:
        template.setdefault("schema", _default_srt_schema())
        normalised_schema = copy.deepcopy(_normalise_srt_schema(template["schema"]))
        template["schema"] = normalised_schema
        templates_normalised.append(
            {
                **template,
                "schema": copy.deepcopy(normalised_schema),
            }
        )

    templates_normalised.sort(key=lambda item: item["name"].lower())

    return render_template("srt_form_templates.html", templates=templates_normalised)


@app.route("/srt/sites")
@login_required
def srt_sites():
    selected_key = request.args.get("site")

    sites = []
    site_map = {}
    for site in sorted(SRT_SITES, key=lambda item: item["name"].lower()):
        site_copy = {key: value for key, value in site.items() if key != "additional_contacts"}
        contacts = [dict(contact) for contact in site.get("additional_contacts", [])]
        site_copy["additional_contacts"] = contacts
        site_copy["tasks"] = [
            dict(task)
            for task in SRT_SAMPLE_TASKS
            if task.get("site") == site["name"]
        ]
        site_copy.setdefault("client_contact", {})
        site_copy.setdefault("form_update", {})
        site_copy.setdefault("updates", [])
        site_copy.setdefault("interactions", [])
        site_map[site["key"]] = site_copy
        sites.append(site_copy)

    if not sites:
        selected_site = None
    else:
        if selected_key and selected_key in site_map:
            selected_site = site_map[selected_key]
        else:
            selected_site = sites[0]
            selected_key = selected_site["key"]

    return render_template(
        "srt_sites.html",
        sites=sites,
        selected_site_key=selected_key,
        team_members=SRT_TEAM_MEMBERS,
    )


@app.route("/srt/task", methods=["POST"])
@login_required
def srt_task_create():
    site_name = (request.form.get("site_name") or "").strip()
    summary = (request.form.get("summary") or "").strip()
    priority = (request.form.get("priority") or "Medium").strip().title() or "Medium"
    owner = (request.form.get("owner") or "Unassigned").strip() or "Unassigned"
    due_date_raw = request.form.get("due_date")

    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            due_date = None

    if not site_name or not summary:
        flash("Site and summary are required to create a task.", "error")
        return redirect(url_for("srt_sites"))

    existing_ids = {task["id"] for task in SRT_SAMPLE_TASKS}
    task_id = f"SRT-{_random_digits(4)}"
    while task_id in existing_ids:
        task_id = f"SRT-{_random_digits(4)}"

    SRT_SAMPLE_TASKS.insert(
        0,
        {
            "id": task_id,
            "site": site_name,
            "summary": summary,
            "priority": priority,
            "status": "Pending",
            "due_date": due_date,
            "owner": owner or "Unassigned",
            "age_days": 0,
        },
    )

    flash("SRT task added to the board.", "success")
    return redirect(url_for("srt_sites", site=slugify(site_name)))


# ---------------------- QC TABS ----------------------
@app.route("/qc")
@login_required
def qc_home():
    status = request.args.get("status", "all")
    status_order = case(
        (QCWork.status == "In Progress", 0),
        (QCWork.status == "Open", 1),
        (QCWork.status == "Blocked", 2),
        (QCWork.status == "Closed", 3),
        else_=4
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
        status_filter=status,
        TASK_MILESTONES=TASK_MILESTONES
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
    planned_start = (request.form.get("planned_start_date") or "").strip()
    duration_raw = (request.form.get("planned_duration_days") or "").strip()
    milestone_value = (request.form.get("milestone") or "").strip()

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

    planned_start_date = None
    if planned_start:
        try:
            planned_start_date = datetime.datetime.strptime(planned_start, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid planned start date format.", "error")
            return redirect(url_for("qc_home"))

    duration_days = None
    if duration_raw:
        try:
            duration_days = int(duration_raw)
        except ValueError:
            flash("Duration must be a whole number of days.", "error")
            return redirect(url_for("qc_home"))
        if duration_days < 0:
            flash("Duration must be zero or positive.", "error")
            return redirect(url_for("qc_home"))

    if due_dt is None:
        if planned_start_date and duration_days is not None:
            due_dt = datetime.datetime.combine(planned_start_date, datetime.time.min) + datetime.timedelta(days=duration_days)
        elif duration_days is not None:
            due_dt = datetime.datetime.utcnow() + datetime.timedelta(days=duration_days)

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
        assigned_to=assigned_to,
        name=site_name,
        planned_start_date=planned_start_date,
        planned_duration_days=duration_days,
        milestone=milestone_value or None
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
            "project_id": work.project_id,
            "planned_start_date": planned_start_date.strftime("%Y-%m-%d") if planned_start_date else None,
            "planned_duration_days": duration_days,
            "milestone": work.milestone
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
    comments = (
        QCWorkComment.query
        .filter_by(work_id=work_id)
        .order_by(QCWorkComment.created_at.desc())
        .all()
    )
    for comment in comments:
        try:
            comment.attachments = json.loads(comment.attachments_json or "[]")
        except Exception:
            comment.attachments = []
        comment.has_attachments = bool(comment.attachments)
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
    attachment_entries = []
    for comment in comments:
        for item in getattr(comment, "attachments", []) or []:
            web_path = item.get("web_path") or (
                item.get("path", "").split("static/", 1)[1]
                if "path" in item and "static/" in item.get("path", "")
                else item.get("path")
            )
            attachment_entries.append({
                "name": item.get("name") or "Attachment",
                "web_path": web_path,
                "comment_id": comment.id,
                "author": comment.author.username if comment.author else "Unknown",
                "created_at": comment.created_at,
                "body": (comment.body[:160] + ("…" if len(comment.body) > 160 else "")) if comment.body else None,
            })

    attachment_entries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return render_template(
        "qc_work_detail.html",
        work=work,
        submissions=submissions,
        users=users,
        comments=comments,
        logs=logs,
        attachments=attachment_entries
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
    log_details = {"comment_id": comment.id}
    if body:
        snippet = body if len(body) <= 160 else body[:157] + "…"
        log_details["body"] = snippet
    if attachments:
        log_details["attachments"] = [item.get("name") for item in attachments if item.get("name")]
    log_work_event(
        work.id,
        "comment_added",
        actor_id=current_user.id,
        details=log_details
    )
    db.session.commit()
    flash("Comment added.", "success")
    return redirect(url_for("qc_work_detail", work_id=work.id))


@app.route("/qc/work/<int:work_id>/status/<string:action>", methods=["POST"])
@login_required
def qc_work_status(work_id, action):
    """Progress status for work: open -> in_progress -> closed."""
    work = QCWork.query.get_or_404(work_id)
    if action not in {"start", "close", "reopen"}:
        flash("Invalid action.", "error")
        return redirect(url_for("qc_work_detail", work_id=work.id))

    from_status = work.status or "Open"
    if action == "start":
        if from_status == "Blocked" and not work.dependency_satisfied:
            flash("This task is waiting for its dependency to complete.", "error")
            return redirect(url_for("qc_work_detail", work_id=work.id))
        if from_status == "Blocked" and work.dependency_satisfied:
            work.status = "Open"
            db.session.flush()
            log_work_event(
                work.id,
                "dependency_released",
                actor_id=current_user.id,
                details={"dependency": work.depends_on_id}
            )
            from_status = work.status
        if from_status != "Open":
            flash(f"Cannot start: current status is {work.status}.", "error")
            return redirect(url_for("qc_work_detail", work_id=work.id))
        new_status = "In Progress"
    elif action == "close":
        if from_status != "In Progress":
            flash(f"Cannot close: current status is {work.status}.", "error")
            return redirect(url_for("qc_work_detail", work_id=work.id))
        new_status = "Closed"
    else:  # reopen
        if from_status != "Closed":
            flash(f"Cannot reopen: current status is {work.status}.", "error")
            return redirect(url_for("qc_work_detail", work_id=work.id))
        new_status = "In Progress"

    work.status = new_status
    db.session.flush()
    log_work_event(
        work.id,
        "status_changed",
        actor_id=current_user.id,
        from_status=from_status,
        to_status=new_status
    )
    if new_status == "Closed":
        release_dependent_tasks(work, actor_id=current_user.id)
    elif action == "reopen":
        block_child_tasks(work, actor_id=current_user.id)
    db.session.commit()
    flash(f"Work status changed to {new_status}.", "success")
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
