import os
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

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

    base_url = current_app.config.get(
        "SARV_RECORDING_BASE_URL", "https://ctv1.sarv.com"
    )
    token = current_app.config.get("SARV_RECORDING_TOKEN", "")
    target_dir = current_app.config.get("CALL_RECORDINGS_DIR", "static/call_recordings")
    target_dir = _resolve_target_dir(target_dir)

    os.makedirs(target_dir, exist_ok=True)

    full_url = urljoin(
        base_url.rstrip("/") + "/", call_recording.sarv_file_path.lstrip("/")
    )

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        request = Request(full_url, headers=headers)
        with urlopen(request, timeout=60) as resp:
            if resp.status >= 400:
                raise HTTPError(full_url, resp.status, resp.reason, resp.headers, None)

            filename = os.path.basename(call_recording.sarv_file_path)
            local_name = f"{call_recording.call_log.sarv_call_id}_{filename}"
            local_path = os.path.join(target_dir, local_name)

            with open(local_path, "wb") as f:
                f.write(resp.read())

        rel_path = os.path.relpath(local_path, start="static")

        call_recording.local_file_path = rel_path.replace("\\", "/")
        call_recording.download_status = "success"
        call_recording.download_error = None
        db.session.commit()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network and IO side effects
        call_recording.download_status = "failed"
        call_recording.download_error = str(exc)[:250]
        db.session.commit()

