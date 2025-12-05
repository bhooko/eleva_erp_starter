import os
from urllib.parse import urljoin

import requests
from flask import current_app

from eleva_app import db
from eleva_app.models import CallRecording


def _resolve_target_dir(target_dir: str) -> str:
    if os.path.isabs(target_dir):
        return target_dir
    return os.path.join(current_app.root_path, target_dir)


def download_call_recording(call_recording: CallRecording):
    """
    Download one SARV recording and save locally under CALL_RECORDINGS_DIR.
    Updates CallRecording.local_file_path and download_status.
    """

    base_url = current_app.config.get("SARV_RECORDING_BASE_URL")
    token = current_app.config.get("SARV_RECORDING_TOKEN", "")
    target_dir = current_app.config.get("CALL_RECORDINGS_DIR", "static/call_recordings")
    target_dir = _resolve_target_dir(target_dir)

    os.makedirs(target_dir, exist_ok=True)

    full_url = urljoin(base_url.rstrip("/") + "/", call_recording.sarv_file_path.lstrip("/"))

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(full_url, headers=headers, timeout=60)
        resp.raise_for_status()

        filename = os.path.basename(call_recording.sarv_file_path)
        local_name = f"{call_recording.call_log.sarv_call_id}_{filename}"
        local_path = os.path.join(target_dir, local_name)

        with open(local_path, "wb") as f:
            f.write(resp.content)

        rel_path = os.path.relpath(local_path, start=current_app.static_folder)

        call_recording.local_file_path = rel_path.replace("\\", "/")
        call_recording.download_status = "success"
        call_recording.download_error = None
        db.session.commit()
    except Exception as exc:  # pragma: no cover - network and IO side effects
        call_recording.download_status = "failed"
        call_recording.download_error = str(exc)[:250]
        db.session.commit()

