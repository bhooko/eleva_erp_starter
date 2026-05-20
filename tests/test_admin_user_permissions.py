import unittest
from pathlib import Path

from flask_login import login_user

from app import WORKSPACE_MODULES, app, db, ensure_bootstrap
from eleva_app.models import User


class AdminUserPermissionsTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            ensure_bootstrap()
            self._cleanup()

    def tearDown(self):
        with app.app_context():
            self._cleanup()

    def _cleanup(self):
        User.query.filter(
            User.username.in_(["permissions_admin_test", "permissions_user_test"])
        ).delete(synchronize_session=False)
        db.session.commit()

    def test_workspace_modules_include_sidebar_operational_modules(self):
        keys = [module["key"] for module in WORKSPACE_MODULES]

        self.assertEqual(
            keys,
            [
                "customer_support",
                "service",
                "sales",
                "operations",
                "design",
                "purchase",
                "store",
                "srt",
                "qc",
            ],
        )
        labels = {module["key"]: module["label"] for module in WORKSPACE_MODULES}
        self.assertEqual(labels["operations"], "New Installation")

    def test_service_ic_control_lives_inside_user_permissions_modal(self):
        template = Path("templates/partials/admin_panel.html").read_text(
            encoding="utf-8"
        )
        modal_start = template.index('id="user-modal-{{ user.id }}"')
        table_markup = template[:modal_start]
        modal_markup = template[modal_start:]
        permissions_start = modal_markup.index("Module permissions")
        permissions_markup = modal_markup[permissions_start:]

        self.assertNotIn("admin_user_toggle_service_manager", table_markup)
        self.assertNotIn("Service I/C", table_markup)
        self.assertIn('name="is_service_manager"', permissions_markup)
        self.assertIn("Service I/C", permissions_markup)

    def test_admin_user_update_saves_service_ic_from_permissions_modal(self):
        with app.app_context():
            admin = User(username="permissions_admin_test", role="Admin", active=True)
            admin.set_password("test")
            target = User(
                username="permissions_user_test",
                role="Service",
                active=True,
                is_service_manager=False,
            )
            target.set_password("test")
            db.session.add_all([admin, target])
            db.session.commit()

            with app.test_request_context(
                f"/admin/users/{target.id}/update",
                method="POST",
                data={
                    "username": target.username,
                    "active": "1",
                    "is_service_manager": "1",
                },
            ):
                login_user(admin)
                app.view_functions["admin_users_update"](target.id)

            db.session.refresh(target)
            self.assertTrue(target.is_service_manager)

    def test_sidebar_uses_permissions_for_design_purchase_and_store(self):
        template = Path("templates/base.html").read_text(encoding="utf-8")

        self.assertIn("current_user.can_view_module('design')", template)
        self.assertIn("current_user.can_view_module('purchase')", template)
        self.assertIn("current_user.can_view_module('store')", template)
        self.assertNotIn("{% set store_visible = true %}", template)


if __name__ == "__main__":
    unittest.main()
