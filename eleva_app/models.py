import datetime
import json
import uuid
from datetime import date

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from eleva_app import db

from app import (
    DEPARTMENT_BRANCHES,
    OPPORTUNITY_ACTIVITY_LABELS,
    REMINDER_OPTION_LABELS,
    SALES_TASK_CATEGORY_LABELS,
    SERVICE_VISIT_STATUS_LABELS,
    _is_password_hashed,
    apply_actor_context,
    clean_str,
    format_file_size,
)


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
    is_service_manager = db.Column(db.Boolean, default=False)
    session_token = db.Column(
        db.String(36),
        nullable=True,
        default=lambda: str(uuid.uuid4()),
    )
    position_id = db.Column(db.Integer, db.ForeignKey("position.id"), nullable=True)
    module_permissions_json = db.Column(db.Text, nullable=False, default="{}")

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
        return role == "admin"

    def _module_permissions_cache(self):
        cache = getattr(self, "_module_permissions_data", None)
        if cache is None:
            raw = self.module_permissions_json or "{}"
            try:
                loaded = json.loads(raw)
            except (TypeError, ValueError):
                loaded = {}
            if not isinstance(loaded, dict):
                loaded = {}
            normalised = {}
            for key, value in loaded.items():
                if not isinstance(value, dict):
                    continue
                module_key = (key or "").strip().lower()
                if not module_key:
                    continue
                normalised[module_key] = {
                    "visibility": bool(value.get("visibility", False)),
                    "assignment": bool(value.get("assignment", False)),
                }
            self._module_permissions_data = normalised
            cache = normalised
        return cache

    def get_module_permission_settings(self, module_key):
        module_key = (module_key or "").strip().lower()
        data = self._module_permissions_cache().get(module_key, {})
        return {
            "visibility": bool(data.get("visibility", False)),
            "assignment": bool(data.get("assignment", False)),
        }

    def set_module_permissions(self, permissions):
        cleaned = {}
        for key, value in (permissions or {}).items():
            module_key = (key or "").strip().lower()
            if not module_key:
                continue
            visibility = bool(value.get("visibility", False)) if isinstance(value, dict) else bool(value)
            assignment = bool(value.get("assignment", False)) if isinstance(value, dict) else bool(value)
            cleaned[module_key] = {
                "visibility": visibility,
                "assignment": assignment,
            }
        self.module_permissions_json = json.dumps(cleaned)
        self._module_permissions_data = cleaned

    def set_password(self, raw_password: str):
        if raw_password is None:
            return
        self.password = generate_password_hash(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        if not raw_password:
            return False
        if _is_password_hashed(self.password):
            try:
                return check_password_hash(self.password, raw_password)
            except ValueError:
                return False
        return self.password == raw_password

    def can_view_module(self, module_key):
        if self.is_admin:
            return True
        module_key = (module_key or "").strip().lower()
        if not module_key:
            return True
        settings = self.get_module_permission_settings(module_key)
        return bool(settings.get("visibility", True))

    def can_be_assigned_module(self, module_key):
        if self.is_admin:
            return True
        module_key = (module_key or "").strip().lower()
        if not module_key:
            return True
        settings = self.get_module_permission_settings(module_key)
        return bool(settings.get("assignment", True))

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
    sales_won_at = db.Column(db.DateTime, nullable=True)
    sales_executive_name = db.Column(db.String(200), nullable=True)

    comments = db.relationship(
        "ProjectComment",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectComment(db.Model):
    __tablename__ = "project_comment"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    project = db.relationship("Project", back_populates="comments")
    author = db.relationship("User")


class FormSchema(db.Model):
    __tablename__ = "form_schema"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    schema_json = db.Column(db.Text, nullable=False, default="[]")
    min_photos_if_all_good = db.Column(db.Integer, default=0)

    # NEW
    stage = db.Column(db.String(40), nullable=True)      # e.g., "Stage 1", "Completion", etc.
    lift_type = db.Column(db.String(40), nullable=True)  # e.g., "MRL", "Hydraulic", etc.
    is_primary = db.Column(db.Boolean, default=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


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


class SalesCompany(db.Model):
    __tablename__ = "sales_company"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    projects_per_year = db.Column(db.Integer, nullable=True)
    contact_person_name = db.Column(db.String(150), nullable=True)
    contact_person_designation = db.Column(db.String(150), nullable=True)
    contact_person_number = db.Column(db.String(50), nullable=True)
    contact_person_email = db.Column(db.String(200), nullable=True)
    purchase_manager_name = db.Column(db.String(150), nullable=True)
    purchase_manager_number = db.Column(db.String(50), nullable=True)
    purchase_manager_email = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    blacklisted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    clients = db.relationship("SalesClient", back_populates="company")

    @property
    def display_label(self):
        return self.name or "Unnamed Company"


class SalesClient(db.Model):
    __tablename__ = "sales_client"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(150), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("sales_company.id"), nullable=True)
    company_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email_opt_out = db.Column(db.String(10), nullable=True)
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
    company = db.relationship("SalesCompany", back_populates="clients")
    opportunities = db.relationship(
        "SalesOpportunity",
        back_populates="client",
        cascade="all, delete-orphan",
    )

    @property
    def open_opportunity_count(self):
        return sum(1 for opp in self.opportunities if not opp.is_closed)

    @property
    def email_opt_out_label(self):
        value = (self.email_opt_out or "").strip().lower()
        if not value:
            return "Not set"
        return "Yes" if value in {"yes", "true", "1"} else "No"


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
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    owner = db.relationship("User")
    client = db.relationship("SalesClient", back_populates="opportunities")
    project = db.relationship("Project", backref="opportunities", lazy="joined")
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


sales_task_assignees = db.Table(
    "sales_task_assignee",
    db.Column("task_id", db.Integer, db.ForeignKey("sales_task.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
)


class SalesTask(db.Model):
    __tablename__ = "sales_task"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="task")
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(40), default="Pending")
    description = db.Column(db.Text, nullable=True)
    related_type = db.Column(db.String(30), default="general")
    opportunity_id = db.Column(db.Integer, db.ForeignKey("sales_opportunity.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("sales_client.id"), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", foreign_keys=[owner_id])
    assignee = db.relationship("User", foreign_keys=[assignee_id])
    assignees = db.relationship(
        "User",
        secondary=sales_task_assignees,
        backref="assigned_sales_tasks",
        lazy="joined",
    )
    creator = db.relationship("User", foreign_keys=[created_by_id])
    opportunity = db.relationship("SalesOpportunity")
    client = db.relationship("SalesClient")

    @property
    def category_label(self):
        return SALES_TASK_CATEGORY_LABELS.get(self.category, "Task")

    @property
    def is_completed(self):
        return (self.status or "").strip().lower() == "completed"

    @property
    def owner_display(self):
        if self.owner and self.owner.display_name:
            return self.owner.display_name
        if self.owner:
            return self.owner.username
        return "Unassigned"

    @property
    def assignee_display(self):
        users = self.assignees or ([])
        if not users and self.assignee:
            users = [self.assignee]

        display_names = []
        for user in users:
            if not user:
                continue
            if user.display_name:
                display_names.append(user.display_name)
            elif user.username:
                display_names.append(user.username)

        if display_names:
            return ", ".join(display_names)

        user = self.owner
        if user and user.display_name:
            return user.display_name
        if user:
            return user.username
        return "Unassigned"

    @property
    def assignee_display_list(self):
        users = self.assignees or ([])
        if not users and self.assignee:
            users = [self.assignee]

        names = []
        for user in users:
            if not user:
                continue
            if user.display_name:
                names.append(user.display_name)
            elif user.username:
                names.append(user.username)

        if names:
            return names

        if self.owner_display != "Unassigned":
            return [self.owner_display]
        return []

    @property
    def related_display(self):
        related_type = (self.related_type or "general").strip().lower()
        if related_type == "opportunity" and self.opportunity:
            name = self.opportunity.title
            if self.opportunity.client:
                name = f"{name} · {self.opportunity.client.display_name}"
            return name
        if related_type == "client" and self.client:
            return self.client.display_name
        return "General"


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


class ServiceRoute(db.Model):
    __tablename__ = "service_route"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(120), unique=True, nullable=False)
    branch = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @property
    def display_name(self):
        if self.branch:
            return f"{self.state} · {self.branch}"
        return self.state

    @property
    def route_name(self):
        return self.state


class Customer(db.Model):
    __tablename__ = "customer"

    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    external_customer_id = db.Column(
        db.String(100), unique=True, nullable=True, index=True
    )
    company_name = db.Column(db.String(255), nullable=False)
    contact_person = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    mobile = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    gst_no = db.Column(db.String(40), nullable=True)
    billing_address_line1 = db.Column(db.String(255), nullable=True)
    billing_address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state = db.Column(db.String(120), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(120), nullable=True)
    route = db.Column(db.String(120), nullable=True)
    sector = db.Column(db.String(60), nullable=True)
    branch = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    office_address_line1 = db.Column(db.String(255), nullable=True)
    office_address_line2 = db.Column(db.String(255), nullable=True)
    office_city = db.Column(db.String(120), nullable=True)
    office_state = db.Column(db.String(120), nullable=True)
    office_pincode = db.Column(db.String(20), nullable=True)
    office_country = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    lifts = db.relationship(
        "Lift",
        back_populates="customer",
        foreign_keys="Lift.customer_code",
        primaryjoin="Customer.customer_code==Lift.customer_code",
    )

    comments = db.relationship(
        "CustomerComment",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    def display_name(self):
        return f"{self.customer_code} – {self.company_name}" if self.company_name else self.customer_code


class CustomerComment(db.Model):
    __tablename__ = "customer_comment"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    customer = db.relationship("Customer", back_populates="comments")
    author = db.relationship("User")


class Lift(db.Model):
    __tablename__ = "lift"

    id = db.Column(db.Integer, primary_key=True)
    lift_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    external_lift_id = db.Column(db.String(100), nullable=True)
    customer_code = db.Column(db.String(32), db.ForeignKey("customer.customer_code"), nullable=True, index=True)
    site_address_line1 = db.Column(db.String(255), nullable=True)
    site_address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    state = db.Column(db.String(120), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    geo_location = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(120), nullable=True)
    building_villa_number = db.Column(db.String(120), nullable=True)
    route = db.Column(db.String(20), nullable=True)
    building_floors = db.Column(db.String(40), nullable=True)
    lift_type = db.Column(db.String(40), nullable=True)
    lift_brand = db.Column(db.String(120), nullable=True)
    capacity_persons = db.Column(db.Integer, nullable=True)
    capacity_kg = db.Column(db.Integer, nullable=True)
    speed_mps = db.Column(db.Float, nullable=True)
    machine_type = db.Column(db.String(40), nullable=True)
    machine_brand = db.Column(db.String(120), nullable=True)
    controller_brand = db.Column(db.String(120), nullable=True)
    door_type = db.Column(db.String(120), nullable=True)
    door_brand = db.Column(db.String(120), nullable=True)
    cabin_finish = db.Column(db.String(120), nullable=True)
    power_supply = db.Column(db.String(40), nullable=True)
    install_date = db.Column(db.Date, nullable=True)
    warranty_expiry = db.Column(db.Date, nullable=True)
    amc_status = db.Column(db.String(40), nullable=True)
    amc_start = db.Column(db.Date, nullable=True)
    amc_end = db.Column(db.Date, nullable=True)
    amc_duration_key = db.Column(db.String(40), nullable=True)
    amc_contract_id = db.Column(db.String(60), nullable=True)
    qr_code_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(40), nullable=True)
    last_service_date = db.Column(db.Date, nullable=True)
    next_service_due = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    preferred_service_day = db.Column(db.String(20), nullable=True)
    preferred_service_date = db.Column(db.Date, nullable=True)
    preferred_service_time = db.Column(db.Time, nullable=True)
    preferred_service_days_json = db.Column(db.Text, nullable=True)
    lifetime_metrics_json = db.Column(db.Text, nullable=True)
    amc_contacts_json = db.Column(db.Text, nullable=True)
    timeline_entries_json = db.Column(db.Text, nullable=True)
    service_schedule_json = db.Column(db.Text, nullable=True)
    last_updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    capacity_display = db.Column(db.String(120), nullable=True)

    customer = db.relationship(
        "Customer",
        back_populates="lifts",
        foreign_keys=[customer_code],
    )
    attachments = db.relationship(
        "LiftFile",
        back_populates="lift",
        cascade="all, delete-orphan",
    )
    comments = db.relationship(
        "LiftComment",
        back_populates="lift",
        cascade="all, delete-orphan",
    )

    def set_capacity_display(self):
        if self.capacity_persons and self.capacity_kg:
            self.capacity_display = f"{self.capacity_persons} persons / {self.capacity_kg} kg"
        elif self.capacity_persons:
            self.capacity_display = f"{self.capacity_persons} persons"
        elif self.capacity_kg:
            self.capacity_display = f"{self.capacity_kg} kg"
        else:
            self.capacity_display = None

    @property
    def door_finish(self):
        return self.door_brand

    @door_finish.setter
    def door_finish(self, value):
        self.door_brand = value

    @property
    def preferred_service_days(self):
        if not self.preferred_service_days_json:
            fallback = clean_str(self.preferred_service_day)
            return [fallback.lower()] if fallback else []
        try:
            data = json.loads(self.preferred_service_days_json)
        except (TypeError, ValueError):
            fallback = clean_str(self.preferred_service_day)
            return [fallback.lower()] if fallback else []
        if not isinstance(data, list):
            fallback = clean_str(self.preferred_service_day)
            return [fallback.lower()] if fallback else []
        cleaned = []
        for item in data:
            if not isinstance(item, str):
                continue
            cleaned_item = item.strip().lower()
            if cleaned_item:
                cleaned.append(cleaned_item)
        if not cleaned:
            fallback = clean_str(self.preferred_service_day)
            if fallback:
                return [fallback.lower()]
        return cleaned

    @preferred_service_days.setter
    def preferred_service_days(self, values):
        if not values:
            self.preferred_service_days_json = None
            self.preferred_service_day = None
            return
        unique_values = []
        for value in values:
            if not isinstance(value, str):
                continue
            cleaned = value.strip().lower()
            if cleaned and cleaned not in unique_values:
                unique_values.append(cleaned)
        if unique_values:
            self.preferred_service_day = unique_values[0]
            self.preferred_service_days_json = json.dumps(unique_values)
        else:
            self.preferred_service_day = None
            self.preferred_service_days_json = None

    @property
    def lifetime_metrics(self):
        if not self.lifetime_metrics_json:
            return []
        try:
            data = json.loads(self.lifetime_metrics_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        normalized = []
        for item in data:
            if not isinstance(item, dict):
                continue
            label = clean_str(item.get("label")) or "Metric"
            display = item.get("display")
            if display is None:
                display = clean_str(item.get("value")) or "—"
            normalized.append({"label": label, "display": display})
        return normalized

    @lifetime_metrics.setter
    def lifetime_metrics(self, values):
        if not values:
            self.lifetime_metrics_json = None
            return
        cleaned = []
        for item in values:
            if not isinstance(item, dict):
                continue
            label = clean_str(item.get("label"))
            display = item.get("display")
            if display is None:
                display = clean_str(item.get("value"))
            if not label and not display:
                continue
            cleaned.append(
                {
                    "label": label or "Metric",
                    "display": display or "—",
                }
            )
        self.lifetime_metrics_json = json.dumps(cleaned, ensure_ascii=False)

    @property
    def amc_contacts(self):
        if not self.amc_contacts_json:
            return []
        try:
            data = json.loads(self.amc_contacts_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        contacts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            contacts.append(
                {
                    "name": clean_str(item.get("name")) or "—",
                    "designation": clean_str(item.get("designation")) or "—",
                    "phone": clean_str(item.get("phone")) or "—",
                    "email": clean_str(item.get("email")) or "—",
                }
            )
        return contacts

    @amc_contacts.setter
    def amc_contacts(self, values):
        if not values:
            self.amc_contacts_json = None
            return
        cleaned = []
        for item in values:
            if not isinstance(item, dict):
                continue
            name = clean_str(item.get("name"))
            designation = clean_str(item.get("designation"))
            phone = clean_str(item.get("phone"))
            email = clean_str(item.get("email"))
            if not any([name, designation, phone, email]):
                continue
            cleaned.append(
                {
                    "name": name or "—",
                    "designation": designation or "—",
                    "phone": phone or "—",
                    "email": email or "—",
                }
            )
        self.amc_contacts_json = json.dumps(cleaned, ensure_ascii=False)

    @property
    def service_schedule(self):
        if not self.service_schedule_json:
            return []
        try:
            data = json.loads(self.service_schedule_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        schedule = []
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            visit_date = None
            if isinstance(raw_date, datetime.datetime):
                visit_date = raw_date.date()
            elif isinstance(raw_date, datetime.date):
                visit_date = raw_date
            elif isinstance(raw_date, str):
                try:
                    visit_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError:
                    visit_date = None
            technician = clean_str(item.get("technician"))
            status_value = clean_str(item.get("status"))
            status_key = (
                status_value.lower()
                if status_value and status_value.lower() in SERVICE_VISIT_STATUS_LABELS
                else None
            )
            slip_url = clean_str(item.get("slip_url") or item.get("slip"))
            slip_label = clean_str(item.get("slip_label") or item.get("label"))
            schedule.append(
                {
                    "date": visit_date,
                    "technician": technician,
                    "status": status_key,
                    "slip_url": slip_url,
                    "slip_label": slip_label,
                }
            )
        return schedule

    @service_schedule.setter
    def service_schedule(self, values):
        if not values:
            self.service_schedule_json = None
            return
        cleaned = []
        for item in values:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            iso_date = None
            if isinstance(raw_date, datetime.datetime):
                iso_date = raw_date.date().isoformat()
            elif isinstance(raw_date, datetime.date):
                iso_date = raw_date.isoformat()
            else:
                date_str = clean_str(raw_date)
                if date_str:
                    try:
                        iso_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
                    except ValueError:
                        continue
            if not iso_date:
                continue
            status_value = clean_str(item.get("status"))
            status_key = (
                status_value.lower()
                if status_value and status_value.lower() in SERVICE_VISIT_STATUS_LABELS
                else "scheduled"
            )
            technician = clean_str(item.get("technician"))
            slip_url = clean_str(item.get("slip_url"))
            slip_label = clean_str(item.get("slip_label"))
            cleaned.append(
                {
                    "date": iso_date,
                    "technician": technician,
                    "status": status_key,
                    "slip_url": slip_url,
                    "slip_label": slip_label,
                }
            )
        self.service_schedule_json = (
            json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        )

    @property
    def next_amc_date(self):
        """
        Returns the next preventive/AMC visit date for this lift.

        Priority:
        1) The earliest future 'service_schedule' entry that is not completed/cancelled.
        2) Fallback to `next_service_due` if set.
        3) Otherwise, None.
        """
        today = date.today()

        # Try from service_schedule entries
        try:
            schedule = self.service_schedule or []
        except Exception:
            schedule = []

        upcoming_dates = []
        for item in schedule:
            visit_date = item.get("date")
            if not isinstance(visit_date, date):
                continue
            status_key = (item.get("status") or "").strip().lower()
            # Treat anything not completed/cancelled as an open visit
            if status_key in {"completed", "cancelled"}:
                continue
            if visit_date >= today:
                upcoming_dates.append(visit_date)

        if upcoming_dates:
            return min(upcoming_dates)

        # Fallback to next_service_due column if available
        if isinstance(getattr(self, "next_service_due", None), date):
            return self.next_service_due

        return None

    @property
    def amc_due_status(self) -> str:
        """
        Returns a human-friendly AMC status key based on `next_amc_date`.

        Possible values:
        - "no_date"
        - "overdue"
        - "due_today"
        - "due_this_week"
        - "upcoming"
        """
        today = date.today()
        next_date = self.next_amc_date

        if not next_date:
            return "no_date"

        if next_date < today:
            return "overdue"
        if next_date == today:
            return "due_today"

        delta_days = (next_date - today).days
        if 0 < delta_days <= 7:
            return "due_this_week"
        return "upcoming"

    @property
    def timeline_entries(self):
        if not self.timeline_entries_json:
            return []
        try:
            data = json.loads(self.timeline_entries_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        entries = []
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            parsed_date = None
            if isinstance(raw_date, datetime.date):
                parsed_date = raw_date
            elif isinstance(raw_date, str) and raw_date:
                try:
                    parsed_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError:
                    parsed_date = None
            actor_info = apply_actor_context(item)
            entries.append(
                {
                    "date": parsed_date,
                    "title": item.get("title") or "—",
                    "detail": item.get("detail") or "",
                    "category": item.get("category") or "Update",
                    "actor": actor_info.get("actor"),
                    "actor_role": actor_info.get("actor_role"),
                    "actor_label": actor_info.get("actor_label"),
                }
            )
        return entries

    @timeline_entries.setter
    def timeline_entries(self, values):
        if not values:
            self.timeline_entries_json = None
            return
        cleaned = []
        for item in values:
            if not isinstance(item, dict):
                continue
            title = clean_str(item.get("title")) or "—"
            detail = clean_str(item.get("detail"))
            category = clean_str(item.get("category")) or "Update"
            raw_date = item.get("date")
            iso_date = None
            if isinstance(raw_date, datetime.date):
                iso_date = raw_date.isoformat()
            elif isinstance(raw_date, datetime.datetime):
                iso_date = raw_date.date().isoformat()
            else:
                date_str = clean_str(raw_date)
                if date_str:
                    try:
                        iso_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
                    except ValueError:
                        iso_date = None
            actor_info = apply_actor_context(item)
            cleaned.append(
                {
                    "date": iso_date,
                    "title": title,
                    "detail": detail or "",
                    "category": category,
                    "actor": actor_info.get("actor"),
                    "actor_role": actor_info.get("actor_role"),
                    "actor_label": actor_info.get("actor_label"),
                }
            )
        self.timeline_entries_json = json.dumps(cleaned, ensure_ascii=False)


class LiftFile(db.Model):
    __tablename__ = "lift_file"

    id = db.Column(db.Integer, primary_key=True)
    lift_id = db.Column(db.Integer, db.ForeignKey("lift.id"), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    label = db.Column(db.String(150), nullable=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(20), nullable=True, default="other")
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(400), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    lift = db.relationship("Lift", back_populates="attachments")
    uploaded_by = db.relationship("User")

    @property
    def display_label(self):
        return self.label or self.original_filename

    @property
    def display_size(self):
        return format_file_size(self.file_size or 0)

    @property
    def uploaded_display(self):
        if not self.created_at:
            return "—"
        return self.created_at.strftime("%d %b %Y, %I:%M %p")


class LiftComment(db.Model):
    __tablename__ = "lift_comment"

    id = db.Column(db.Integer, primary_key=True)
    lift_id = db.Column(db.Integer, db.ForeignKey("lift.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    lift = db.relationship("Lift", back_populates="comments")
    author = db.relationship("User")

    @property
    def author_name(self):
        if self.author:
            return self.author.display_name
        return "System"

    @property
    def created_display(self):
        if not self.created_at:
            return "—"
        return self.created_at.strftime("%d %b %Y, %I:%M %p")


class DropdownOption(db.Model):
    __tablename__ = "dropdown_option"

    id = db.Column(db.Integer, primary_key=True)
    field_key = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.String(120), nullable=True)
    label = db.Column(db.String(150), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("field_key", "label", name="uq_dropdown_option_field_label"),
    )

    def as_choice(self):
        option_value = self.value if self.value is not None else self.label
        return {"id": self.id, "value": option_value, "label": self.label}


# ----------------------------
# Design module models
# ----------------------------


class DesignTask(db.Model):
    __tablename__ = "design_task"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    project_name = db.Column(db.String(150), nullable=True)
    task_type = db.Column(db.String(50), nullable=False)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="new")
    priority = db.Column(db.String(50), nullable=False, default="medium")
    due_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, nullable=True)
    site_visit_date = db.Column(db.Date, nullable=True)
    site_visit_address = db.Column(db.String(255), nullable=True)
    site_visit_contact = db.Column(db.String(120), nullable=True)
    site_visit_phone = db.Column(db.String(50), nullable=True)
    site_visit_notes = db.Column(db.Text, nullable=True)
    site_visit_status = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    project = db.relationship("Project", backref="design_tasks")
    requested_by = db.relationship("User", foreign_keys=[requested_by_user_id])
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_user_id])

    @property
    def project_label(self):
        if self.project:
            return self.project.name
        return self.project_name or "Unlinked"


class DesignShaftSuggestion(db.Model):
    __tablename__ = "design_shaft_suggestion"

    id = db.Column(db.Integer, primary_key=True)
    design_task_id = db.Column(
        db.Integer, db.ForeignKey("design_task.id"), nullable=False, index=True
    )
    shaft_width_mm = db.Column(db.Integer, nullable=True)
    shaft_depth_mm = db.Column(db.Integer, nullable=True)
    pit_depth_mm = db.Column(db.Integer, nullable=True)
    headroom_mm = db.Column(db.Integer, nullable=True)
    machine_room_required = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    design_task = db.relationship("DesignTask", backref="shaft_suggestions")
    created_by = db.relationship("User")


class DesignTaskComment(db.Model):
    __tablename__ = "design_task_comment"

    id = db.Column(db.Integer, primary_key=True)
    design_task_id = db.Column(
        db.Integer, db.ForeignKey("design_task.id"), nullable=False, index=True
    )
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    design_task = db.relationship("DesignTask", backref="comments")
    author = db.relationship("User")


class DesignDrawing(db.Model):
    __tablename__ = "design_drawing"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    design_task_id = db.Column(
        db.Integer, db.ForeignKey("design_task.id"), nullable=True, index=True
    )
    name = db.Column(db.String(150), nullable=False)
    current_version_number = db.Column(db.Integer, default=1)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    project = db.relationship("Project")
    design_task = db.relationship("DesignTask", backref="drawings")
    created_by = db.relationship("User")


class DesignDrawingRevision(db.Model):
    __tablename__ = "design_drawing_revision"

    id = db.Column(db.Integer, primary_key=True)
    drawing_id = db.Column(
        db.Integer, db.ForeignKey("design_drawing.id"), nullable=False, index=True
    )
    version_number = db.Column(db.Integer, nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    change_reason = db.Column(db.Text, nullable=True)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    drawing = db.relationship("DesignDrawing", backref="revisions")
    changed_by = db.relationship("User")


class DrawingHistory(db.Model):
    __tablename__ = "drawing_history"

    id = db.Column(db.Integer, primary_key=True)
    project_no = db.Column(db.String(120), nullable=True, index=True)
    client_name = db.Column(db.String(150), nullable=True, index=True)
    site_location = db.Column(db.String(150), nullable=True)
    drg_number = db.Column(db.String(120), nullable=True, index=True)
    drg_by = db.Column(db.String(120), nullable=True)
    rev_no = db.Column(db.String(50), nullable=True)
    drg_approval = db.Column(db.String(120), nullable=True)
    lift_type = db.Column(db.String(120), nullable=True, index=True)
    shaft_inner_dims = db.Column(db.String(150), nullable=True)
    car_inner_dims = db.Column(db.String(150), nullable=True)
    num_pass_actual = db.Column(db.Integer, nullable=True)
    num_pass_quoted = db.Column(db.Integer, nullable=True)
    floor_level = db.Column(db.String(120), nullable=True)
    landing_door_opening = db.Column(db.String(150), nullable=True)
    num_sides_struct = db.Column(db.Integer, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "project_no", "drg_number", "rev_no", name="uq_drawing_history_revision"
        ),
    )


# ----------------------------
# Purchase module models
# ----------------------------


class BillOfMaterials(db.Model):
    __tablename__ = "bill_of_materials"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    design_task_id = db.Column(db.Integer, db.ForeignKey("design_task.id"), nullable=True)
    bom_name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="draft")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    project = db.relationship("Project")
    design_task = db.relationship("DesignTask", backref="boms")
    created_by = db.relationship("User")


class BOMItem(db.Model):
    __tablename__ = "bom_item"

    id = db.Column(db.Integer, primary_key=True)
    bom_id = db.Column(db.Integer, db.ForeignKey("bill_of_materials.id"), nullable=False)
    item_code = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(80), nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    quantity_required = db.Column(db.Float, nullable=False, default=1)
    remarks = db.Column(db.Text, nullable=True)

    bom = db.relationship("BillOfMaterials", backref="items")


class Vendor(db.Model):
    __tablename__ = "vendor"

    id = db.Column(db.Integer, primary_key=True)
    vendor_code = db.Column(db.String(80), unique=True, nullable=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    activities = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    country = db.Column(db.String(120), nullable=True)
    salesperson = db.Column(db.String(120), nullable=True)
    gstin = db.Column(db.String(80), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    pincode = db.Column(db.String(40), nullable=True)
    state = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_order"

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(80), unique=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="draft")
    order_date = db.Column(db.Date, nullable=True)
    expected_delivery_date = db.Column(db.Date, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    subtotal_amount = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    project = db.relationship("Project")
    vendor = db.relationship("Vendor")
    created_by = db.relationship("User")


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_line"

    id = db.Column(db.Integer, primary_key=True)
    order_ref = db.Column(db.String(255), nullable=False)
    vendor_name = db.Column(db.String(255), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    billing_status = db.Column(db.String(120), nullable=True)
    buyer = db.Column(db.String(120), nullable=True)
    confirmation_date = db.Column(db.DateTime, nullable=True)
    expected_arrival = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(120), nullable=True)
    source_document = db.Column(db.String(255), nullable=True)
    total_amount = db.Column(db.Numeric(precision=12, scale=2), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "order_ref",
            "vendor_name",
            "product_name",
            "confirmation_date",
            name="uq_purchase_order_line_ref_vendor_product_date",
        ),
    )


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_item"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer, db.ForeignKey("purchase_order.id"), nullable=False
    )
    bom_item_id = db.Column(db.Integer, db.ForeignKey("bom_item.id"), nullable=True)
    item_code = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    quantity_ordered = db.Column(db.Float, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(10), nullable=True, default="INR")
    total_amount = db.Column(db.Float, nullable=True)

    purchase_order = db.relationship("PurchaseOrder", backref="items")
    bom_item = db.relationship("BOMItem")


class BookInventory(db.Model):
    __tablename__ = "book_inventory"

    id = db.Column(db.Integer, primary_key=True)
    item_code = db.Column(db.String(120), nullable=False, unique=True)
    quantity_ordered_total = db.Column(db.Float, default=0)
    quantity_received_total = db.Column(db.Float, default=0)
    quantity_booked_for_projects = db.Column(db.Float, default=0)
    last_po_id = db.Column(db.Integer, db.ForeignKey("purchase_order.id"), nullable=True)

    last_po = db.relationship("PurchaseOrder")


class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    sale_price = db.Column(db.Float, nullable=True)
    cost = db.Column(db.Float, nullable=True)
    uom = db.Column(db.String(120), nullable=True)
    purchase_uom = db.Column(db.String(120), nullable=True)
    qty_on_hand = db.Column(db.Float, default=0)
    forecast_qty = db.Column(db.Float, default=0)
    is_favorite = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    primary_vendor = db.Column(db.String(255), nullable=True)
    linked_vendors = db.Column(db.Text, nullable=True)
    specifications = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )


# ----------------------------
# Store / Inventory module models
# ----------------------------


class InventoryItem(db.Model):
    __tablename__ = "inventory_item"

    id = db.Column(db.Integer, primary_key=True)
    item_code = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    current_stock = db.Column(db.Float, default=0)
    quarantined_stock = db.Column(db.Float, default=0)
    location = db.Column(db.String(120), nullable=True)


class InventoryStock(db.Model):
    __tablename__ = "inventory_stock"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    uom = db.Column(db.String(120), nullable=True)
    on_hand_value = db.Column(db.Float, nullable=True)
    company = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("product_name", "location", name="uq_inventory_stock_product_location"),
    )


class InventoryReceipt(db.Model):
    __tablename__ = "inventory_receipt"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer, db.ForeignKey("purchase_order.id"), nullable=True
    )
    receipt_number = db.Column(db.String(80), nullable=False)
    received_date = db.Column(db.Date, nullable=True)
    received_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    purchase_order = db.relationship("PurchaseOrder")
    received_by = db.relationship("User")


class InventoryReceiptItem(db.Model):
    __tablename__ = "inventory_receipt_item"

    id = db.Column(db.Integer, primary_key=True)
    inventory_receipt_id = db.Column(
        db.Integer, db.ForeignKey("inventory_receipt.id"), nullable=False
    )
    purchase_order_item_id = db.Column(
        db.Integer, db.ForeignKey("purchase_order_item.id"), nullable=True
    )
    item_code = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    quantity_received = db.Column(db.Float, nullable=False, default=0)
    qc_status = db.Column(db.String(20), nullable=True)
    qc_notes = db.Column(db.Text, nullable=True)

    receipt = db.relationship("InventoryReceipt", backref="items")
    purchase_order_item = db.relationship("PurchaseOrderItem")


class Dispatch(db.Model):
    __tablename__ = "dispatch"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    dispatch_number = db.Column(db.String(80), nullable=False)
    dispatch_date = db.Column(db.Date, nullable=True)
    dispatched_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    vehicle_details = db.Column(db.String(150), nullable=True)
    driver_name = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project")
    dispatched_by = db.relationship("User")


class DispatchItem(db.Model):
    __tablename__ = "dispatch_item"

    id = db.Column(db.Integer, primary_key=True)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch.id"), nullable=False)
    item_code = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    quantity_dispatched = db.Column(db.Float, nullable=False, default=0)

    dispatch = db.relationship("Dispatch", backref="items")


class DeliveryOrder(db.Model):
    __tablename__ = "delivery_order"

    id = db.Column(db.Integer, primary_key=True)
    do_number = db.Column(db.String(120), nullable=False, unique=True)
    date_created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    project_or_site = db.Column(db.String(255), nullable=False)
    receiver_name = db.Column(db.String(255), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="Created")
    dispatched_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    dispatched_by = db.relationship("User", foreign_keys=[dispatched_by_user_id])


class DeliveryOrderItem(db.Model):
    __tablename__ = "delivery_order_item"

    id = db.Column(db.Integer, primary_key=True)
    delivery_order_id = db.Column(
        db.Integer, db.ForeignKey("delivery_order.id"), nullable=False
    )
    product_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    uom = db.Column(db.String(80), nullable=True)
    remarks = db.Column(db.Text, nullable=True)

    delivery_order = db.relationship(
        "DeliveryOrder", backref=db.backref("items", cascade="all, delete-orphan")
    )
