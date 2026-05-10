import unittest

from flask import render_template_string
from flask_login import login_user

from app import SECTION_GUIDE_CONTENTS, app, db, ensure_bootstrap
from eleva_app.models import SectionGuide, User


class SectionGuideTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            ensure_bootstrap()
            self._cleanup()

    def tearDown(self):
        with app.app_context():
            self._cleanup()

    def _cleanup(self):
        SectionGuide.query.filter(
            SectionGuide.section_key.in_(
                ["test_process_guide", "test_disabled_guide"]
            )
        ).delete(synchronize_session=False)
        User.query.filter(
            User.username.in_(["section_guide_user", "section_guide_admin"])
        ).delete(synchronize_session=False)
        assets_guide = SectionGuide.query.filter_by(section_key="assets").first()
        if assets_guide:
            assets_guide.title = SECTION_GUIDE_CONTENTS["assets"]["title"]
            assets_guide.content = SECTION_GUIDE_CONTENTS["assets"]["content"]
            assets_guide.is_active = True
            assets_guide.updated_by = None
        db.session.commit()

    def _user(self, username="section_guide_user", role="Store"):
        user = User(username=username, role=role, active=True)
        user.set_password("test")
        db.session.add(user)
        db.session.commit()
        return user

    def test_bootstrap_seeds_operational_section_guides(self):
        with app.app_context():
            ensure_bootstrap()
            keys = {
                guide.section_key
                for guide in SectionGuide.query.filter_by(is_active=True).all()
            }
            self.assertTrue(
                {
                    "dashboard",
                    "customer_support",
                    "sales_leads",
                    "sales_opportunities",
                    "projects",
                    "design",
                    "procurement_plan",
                    "purchase_orders",
                    "vendors",
                    "grn",
                    "dc",
                    "inventory",
                    "assets",
                    "service_tasks",
                    "srt",
                    "qc_tasks",
                }.issubset(keys)
            )

    def test_process_guide_button_renders_for_supported_endpoint_from_db(self):
        with app.app_context():
            user = self._user()
            guide = SectionGuide.query.filter_by(section_key="assets").first()
            if not guide:
                guide = SectionGuide(section_key="assets")
                db.session.add(guide)
            guide.title = "Asset Process Guide"
            guide.content = "Purpose\n<script>alert(1)</script>\nLine two"
            guide.is_active = True
            guide.updated_by = user.id
            db.session.commit()

            with app.test_request_context("/store/assets"):
                login_user(user)
                rendered = render_template_string(
                    '{% include "_section_guide_panel.html" %}'
                )

            self.assertIn('aria-label="Process Guide"', rendered)
            self.assertIn("Asset Process Guide", rendered)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
            self.assertNotIn("<script>alert(1)</script>", rendered)
            self.assertIn("whitespace-pre-wrap", rendered)

    def test_purchase_order_detail_endpoint_uses_purchase_order_guide(self):
        with app.app_context():
            user = self._user()
            with app.test_request_context("/purchase/orders/1"):
                login_user(user)
                rendered = render_template_string(
                    '{% include "_section_guide_panel.html" %}'
                )

            self.assertIn("Purchase Orders Process Guide", rendered)

    def test_design_task_detail_endpoint_uses_design_tasks_guide(self):
        with app.app_context():
            user = self._user()
            with app.test_request_context("/design/tasks/4"):
                login_user(user)
                rendered = render_template_string(
                    '{% include "_section_guide_panel.html" %}'
                )

            self.assertIn("Design Tasks Process Guide", rendered)

    def test_admin_can_create_edit_and_deactivate_section_guides(self):
        with app.app_context():
            admin = self._user("section_guide_admin", role="Admin")

            with app.test_request_context(
                "/settings/process-guides",
                method="POST",
                data={
                    "action": "save_guide",
                    "section_key": "test_process_guide",
                    "title": "Test Process Guide",
                    "content": "Purpose\nUse carefully.",
                    "is_active": "1",
                },
            ):
                login_user(admin)
                app.view_functions["process_guides"]()

            guide = SectionGuide.query.filter_by(
                section_key="test_process_guide"
            ).one()
            self.assertEqual(guide.title, "Test Process Guide")
            self.assertEqual(guide.updated_by, admin.id)
            self.assertTrue(guide.is_active)

            with app.test_request_context(
                "/settings/process-guides",
                method="POST",
                data={
                    "action": "save_guide",
                    "guide_id": str(guide.id),
                    "section_key": "test_process_guide",
                    "title": "Edited Process Guide",
                    "content": "Rules / Restrictions\nEdited.",
                },
            ):
                login_user(admin)
                app.view_functions["process_guides"]()

            guide = db.session.get(SectionGuide, guide.id)
            self.assertEqual(guide.title, "Edited Process Guide")
            self.assertFalse(guide.is_active)

            with app.test_request_context(
                "/settings/process-guides",
                method="POST",
                data={
                    "action": "toggle_guide",
                    "guide_id": str(guide.id),
                    "is_active": "1",
                },
            ):
                login_user(admin)
                app.view_functions["process_guides"]()

            self.assertTrue(db.session.get(SectionGuide, guide.id).is_active)


if __name__ == "__main__":
    unittest.main()
