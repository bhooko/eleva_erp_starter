import datetime
import unittest

import app
from eleva_app import db
from eleva_app.models import CallLog, CallRecording


class SarvCallListingTests(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app.app_context()
        self.app_context.push()
        app.ensure_bootstrap()
        self.client = app.app.test_client()
        app.CUSTOMER_SUPPORT_CALL_LOGS.clear()
        app.CUSTOMER_SUPPORT_TICKETS.clear()
        CallRecording.query.delete()
        CallLog.query.delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        CallRecording.query.delete()
        CallLog.query.delete()
        db.session.commit()
        app.CUSTOMER_SUPPORT_CALL_LOGS.clear()
        app.CUSTOMER_SUPPORT_TICKETS.clear()
        self.app_context.pop()

    def test_customer_support_calls_include_persisted_sarv_logs(self):
        call = CallLog(
            sarv_call_id="SARV-1001",
            ctype="incoming",
            did="08012345678",
            customer_number="9876543210",
            agent_name="Support Desk",
            call_status="ANSWERED",
            talk_duration=125,
            total_duration=150,
            ivr_start_time=datetime.datetime(2026, 4, 25, 10, 30),
        )
        db.session.add(call)
        db.session.commit()

        records = app._customer_support_filter_calls(search="9876543210")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["call_id"], "SARV-1001")
        self.assertEqual(records[0]["caller"], "9876543210")
        self.assertEqual(records[0]["handled_by"], "Support Desk")

    def test_sarv_webhook_import_appears_in_customer_support_calls(self):
        response = self.client.post(
            "/sarv/webhook",
            json={
                "callId": "SARV-2002",
                "cType": "incoming",
                "did": "08012345678",
                "cNumber": "9123456780",
                "masterAgent": "Service Desk",
                "callStatus": "ANSWERED",
                "ivrSTime": "2026-04-25 11:15:00",
                "talkDuration": "61",
            },
        )

        self.assertEqual(response.status_code, 200)
        records = app._customer_support_filter_calls(search="SARV-2002")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["call_id"], "SARV-2002")
        self.assertEqual(records[0]["duration_minutes"], 2)

    def test_sarv_webhook_accepts_recordings_as_json_string(self):
        from integrations.sarv import routes as sarv_routes

        original_downloader = sarv_routes.download_call_recording
        sarv_routes.download_call_recording = lambda recording: None
        try:
            response = self.client.post(
                "/sarv/webhook",
                json={
                    "callId": "SARV-3003",
                    "cNumber": "9000000000",
                    "recordings": '[{"file": "/recordings/call-3003.wav", "nodeid": "n1", "visitId": "v1", "time": "2026-04-25 12:00:00"}]',
                },
            )
        finally:
            sarv_routes.download_call_recording = original_downloader

        self.assertEqual(response.status_code, 200)
        recording = CallRecording.query.one()
        self.assertEqual(recording.sarv_file_path, "/recordings/call-3003.wav")

    def test_sarv_webhook_ignores_unexpanded_recordings_placeholder(self):
        response = self.client.post(
            "/sarv/webhook",
            json={
                "callId": "SARV-4004",
                "cNumber": "9000000001",
                "recordings": "{{%%recordings%%}}",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CallRecording.query.count(), 0)

    def test_sarv_webhook_verification_ping_returns_expected_body(self):
        response = self.client.get("/sarv/webhook")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "GODBLESSYOU")


if __name__ == "__main__":
    unittest.main()
