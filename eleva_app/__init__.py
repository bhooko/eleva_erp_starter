import os
import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

try:
    from flask_wtf.csrf import CSRFProtect
except ImportError as exc:  # pragma: no cover - startup dependency guard
    raise ImportError(
        "Flask-WTF is required to run this application. Activate your virtual "
        "environment and install dependencies with `pip install -r requirements.txt` "
        "(or install Flask-WTF directly with `pip install Flask-WTF`) before "
        "launching the server."
    ) from exc


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    from app import (
        BASE_DIR,
        _get_max_upload_size_bytes,
        _load_admin_settings,
        _load_inventory_control,
        _save_inventory_control,
    )

    template_dir = os.path.join(BASE_DIR, "templates")
    static_dir = os.path.join(BASE_DIR, "static")

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=template_dir,
        static_folder=static_dir,
    )

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-eleva-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "SQLALCHEMY_DATABASE_URI",
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "eleva.db"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
    app.config["ADMIN_SETTINGS"] = _load_admin_settings()
    app.config["INVENTORY_CONTROL"] = _load_inventory_control()
    _save_inventory_control(app.config["INVENTORY_CONTROL"])
    app.config["MAX_CONTENT_LENGTH"] = _get_max_upload_size_bytes(
        app.config["ADMIN_SETTINGS"]
    )
    app.config["PURCHASE_ODOO_IMPORT_ENABLED"] = (
        str(os.environ.get("PURCHASE_ODOO_IMPORT_ENABLED", "true")).strip().lower()
        in {"1", "true", "yes", "y", "on"}
    )
    go_live_raw = os.environ.get("ERP_PO_GO_LIVE_DATE")
    try:
        app.config["ERP_PO_GO_LIVE_DATE"] = (
            datetime.date.fromisoformat(go_live_raw) if go_live_raw else None
        )
    except ValueError:
        app.config["ERP_PO_GO_LIVE_DATE"] = None

    app.config["SARV_RECORDING_BASE_URL"] = os.environ.get(
        "SARV_RECORDING_BASE_URL", "https://example.sarv.com"
    )
    app.config["SARV_RECORDING_TOKEN"] = os.environ.get("SARV_RECORDING_TOKEN", "")
    app.config["CALL_RECORDINGS_DIR"] = os.environ.get(
        "CALL_RECORDINGS_DIR", os.path.join("static", "call_recordings")
    )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["CALL_RECORDINGS_DIR"], exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

    with app.app_context():
        app.config["MAX_CONTENT_LENGTH"] = _get_max_upload_size_bytes(
            app.config.get("ADMIN_SETTINGS", _load_admin_settings())
        )

    from eleva_app import models  # noqa: F401

    return app
