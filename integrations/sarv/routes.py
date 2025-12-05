from datetime import datetime

from flask import Blueprint, request

from eleva_app import db, csrf
from eleva_app.models import CallLog, CallRecording
from integrations.sarv.utils import download_call_recording

sarv_bp = Blueprint("sarv", __name__)


@sarv_bp.route("/sarv/webhook", methods=["POST"])
def sarv_webhook():
    data = request.get_json(silent=True) or {}

    call_id = data.get("callId")
    if not call_id:
        return "GODBLESSYOU", 200

    call = CallLog.query.filter_by(sarv_call_id=call_id).first()
    if not call:
        call = CallLog(sarv_call_id=call_id)

    call.ctype = data.get("cType")
    call.did = data.get("did")
    call.customer_number = data.get("cNumber")

    call.agent_user_id = data.get("userId")
    call.agent_number = data.get("masterAgentNumber")
    call.agent_name = data.get("masterAgent")
    call.group_id = data.get("masterGroupId")

    call.call_status = data.get("callStatus")
    call.ivr_flow = data.get("ivrExecuteFlow")
    call.ivr_id_arr = data.get("ivrIdArr")

    def parse_dt(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def parse_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    call.ivr_start_time = parse_dt(data.get("ivrSTime"))
    call.ivr_end_time = parse_dt(data.get("ivrETime"))
    call.first_answer_time = parse_dt(data.get("firstAnswerTime"))
    call.last_hangup_time = parse_dt(data.get("lastHangupTime"))
    call.cust_answer_start = parse_dt(data.get("custAnswerSTime"))
    call.cust_answer_end = parse_dt(data.get("custAnswerETime"))

    call.ivr_duration = parse_int(data.get("ivrDuration"))
    call.talk_duration = parse_int(data.get("talkDuration"))
    call.total_duration = parse_int(data.get("lastFirstDuration"))
    call.hold_duration = parse_int(data.get("totalHoldDuration"))

    call.raw_payload = data

    db.session.add(call)
    db.session.commit()

    recordings = data.get("recordings") or []
    for rec in recordings:
        sarv_path = rec.get("file")
        if not sarv_path:
            continue

        existing = (
            CallRecording.query.filter_by(call_log_id=call.id, sarv_file_path=sarv_path).first()
        )
        if existing:
            continue

        cr = CallRecording(
            call_log_id=call.id,
            sarv_file_path=sarv_path,
            sarv_node_id=rec.get("nodeid"),
            sarv_visit_id=rec.get("visitId"),
        )

        rtime = rec.get("time")
        cr.sarv_time = parse_dt(rtime) if rtime else None

        db.session.add(cr)
        db.session.commit()

        download_call_recording(cr)

    return "GODBLESSYOU", 200


csrf.exempt(sarv_bp)

