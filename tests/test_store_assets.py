import unittest

from flask import render_template_string
from flask_login import login_user

from app import app, db, ensure_bootstrap
from eleva_app.models import (
    AssetClass,
    AssetLocation,
    AssetMovement,
    AssetRepair,
    AssetType,
    OperationalAsset,
    User,
)


class StoreAssetWorkflowTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            ensure_bootstrap()
            self._cleanup()

    def tearDown(self):
        with app.app_context():
            self._cleanup()

    def _cleanup(self):
        test_assets = OperationalAsset.query.filter(
            OperationalAsset.asset_code.like("ZSA%")
            | OperationalAsset.asset_code.like("ZDR%")
            | OperationalAsset.asset_code.like("ZUT%")
            | OperationalAsset.asset_code.like("ZIN%")
        ).all()
        asset_ids = [asset.id for asset in test_assets]
        if asset_ids:
            AssetMovement.query.filter(AssetMovement.asset_id.in_(asset_ids)).delete(
                synchronize_session=False
            )
            AssetRepair.query.filter(AssetRepair.asset_id.in_(asset_ids)).delete(
                synchronize_session=False
            )
            OperationalAsset.query.filter(OperationalAsset.id.in_(asset_ids)).delete(
                synchronize_session=False
            )
        AssetType.query.filter(
            AssetType.name.in_(["Test Helmet", "Test Cable", "Inline Type"])
        ).delete(synchronize_session=False)
        AssetClass.query.filter(
            AssetClass.name.in_(["Test Safety", "Test Utility", "Inline Class"])
        ).delete(synchronize_session=False)
        AssetLocation.query.filter(AssetLocation.name == "Inline Yard").delete(
            synchronize_session=False
        )
        User.query.filter(User.username == "store_asset_test").delete(
            synchronize_session=False
        )
        User.query.filter(User.username == "asset_menu_user").delete(
            synchronize_session=False
        )
        db.session.commit()

    def _asset_type(
        self,
        class_name="Test Safety",
        type_name="Test Helmet",
        class_prefix="ZSA",
        type_prefix="ZH",
    ):
        asset_class = AssetClass(name=class_name, code_prefix=class_prefix, active=True)
        db.session.add(asset_class)
        db.session.flush()
        asset_type = AssetType(
            name=type_name,
            asset_class_id=asset_class.id,
            code_prefix=type_prefix,
            active=True,
        )
        db.session.add(asset_type)
        db.session.commit()
        return asset_class, asset_type

    def test_bulk_serialized_assets_get_individual_codes_and_history(self):
        import app as app_module

        with app.app_context():
            asset_class, asset_type = self._asset_type()

            assets = app_module._create_operational_assets(
                asset_name="Helmet",
                asset_class=asset_class,
                asset_type=asset_type,
                tracking_mode="serialized",
                qty=3,
                uom="Nos",
                status="Inventory",
                current_location="Main Store",
                current_custodian="Stores",
                condition="Good",
                remarks="Initial test bulk create",
            )
            db.session.commit()

            self.assertEqual([asset.asset_code for asset in assets], ["ZSAZH001", "ZSAZH002", "ZSAZH003"])
            self.assertTrue(all(asset.qty == 1 for asset in assets))
            self.assertTrue(all(asset.tracking_mode == "serialized" for asset in assets))
            self.assertEqual([asset.serial_number for asset in assets], ["001", "002", "003"])
            movement_count = AssetMovement.query.filter(
                AssetMovement.asset_id.in_([asset.id for asset in assets])
            ).count()
            self.assertEqual(movement_count, 3)
            self.assertTrue(
                all(
                    movement.movement_type == "Manual Update"
                    for movement in AssetMovement.query.filter(
                        AssetMovement.asset_id.in_([asset.id for asset in assets])
                    ).all()
                )
            )

    def test_serialized_issue_and_return_updates_authoritative_status_and_logs_movements(self):
        import app as app_module

        with app.app_context():
            asset_class, asset_type = self._asset_type()
            asset = app_module._create_operational_assets(
                asset_name="Helmet",
                asset_class=asset_class,
                asset_type=asset_type,
                tracking_mode="serialized",
                qty=1,
                uom="Nos",
                manual_code="ZSAZH901",
                status="Inventory",
                current_location="Main Store",
                current_custodian="Stores",
                condition="Good",
            )[0]
            db.session.commit()

            app_module._issue_asset(
                asset,
                issued_by="Stores",
                issued_to="Rahul",
                location="Site XYZ",
                condition="Good",
                quantity=1,
                remarks="Issued for site work",
            )
            db.session.commit()

            self.assertEqual(asset.status, "Issued")
            self.assertEqual(asset.current_custodian, "Rahul")
            self.assertEqual(asset.current_location, "Site XYZ")
            issue = AssetMovement.query.filter_by(movement_type="Issue").one()
            self.assertEqual(issue.previous_status, "Inventory")
            self.assertEqual(issue.new_status, "Issued")
            self.assertEqual(issue.issued_to, "Rahul")

            app_module._return_asset(
                asset,
                received_by="Stores",
                outcome_status="Inventory",
                location="Main Store",
                condition="Minor Damage",
                quantity=1,
                remarks="Returned with scratches",
            )
            db.session.commit()

            self.assertEqual(asset.status, "Inventory")
            self.assertEqual(asset.current_custodian, "Stores")
            self.assertEqual(asset.condition, "Minor Damage")
            self.assertEqual(
                AssetMovement.query.filter_by(movement_type="Return").count(),
                1,
            )

    def test_repair_lifecycle_sets_status_and_keeps_repair_movements(self):
        import app as app_module

        with app.app_context():
            asset_class, asset_type = self._asset_type(class_prefix="ZDR", type_prefix="DR")
            asset = app_module._create_operational_assets(
                asset_name="Drilling Machine",
                asset_class=asset_class,
                asset_type=asset_type,
                tracking_mode="serialized",
                qty=1,
                uom="Nos",
                manual_code="ZDRDR901",
                status="Inventory",
                current_location="Main Store",
                current_custodian="Stores",
                condition="Good",
            )[0]
            db.session.commit()

            repair = app_module._start_asset_repair(
                asset,
                sent_by="Stores",
                vendor_repair_agency="Workshop",
                problem_description="Chuck slipping",
                estimated_cost=1200,
                remarks="Needs inspection",
            )
            db.session.commit()

            self.assertEqual(asset.status, "In Repair")
            self.assertEqual(repair.repair_status, "Open")
            self.assertEqual(
                AssetMovement.query.filter_by(movement_type="Repair Send").count(),
                1,
            )

            app_module._close_asset_repair(
                repair,
                close_status="Breakdown",
                actual_cost=900,
                condition="Non Functional",
                remarks="Beyond site-safe use",
            )
            db.session.commit()

            self.assertEqual(asset.status, "Breakdown")
            self.assertEqual(repair.repair_status, "Closed")
            self.assertEqual(repair.close_status, "Breakdown")
            self.assertEqual(
                AssetMovement.query.filter_by(movement_type="Repair Return").count(),
                1,
            )

    def test_quantity_based_assets_allow_quantity_movements_without_normal_inventory_stock(self):
        import app as app_module

        with app.app_context():
            asset_class, asset_type = self._asset_type("Test Utility", "Test Cable", "ZUT", "CB")
            asset = app_module._create_operational_assets(
                asset_name="Reusable Site Cable",
                asset_class=asset_class,
                asset_type=asset_type,
                tracking_mode="quantity",
                qty=10,
                uom="Nos",
                manual_code="ZUTCB001",
                status="Inventory",
                current_location="Main Store",
                current_custodian="Stores",
                condition="Good",
            )[0]
            db.session.commit()

            app_module._issue_asset(
                asset,
                issued_by="Stores",
                issued_to="Vivek",
                location="Vehicle",
                condition="Good",
                quantity=2,
                remarks="Two cables issued",
            )
            db.session.commit()

            self.assertEqual(asset.status, "Issued")
            self.assertEqual(asset.qty, 10)
            movement = AssetMovement.query.filter_by(movement_type="Issue").one()
            self.assertEqual(movement.quantity, 2)
            self.assertEqual(movement.new_custodian, "Vivek")

    def test_create_asset_form_supports_inline_class_type_location_and_calibration(self):
        import app as app_module

        with app.app_context():
            assets, errors = app_module._create_assets_from_asset_form(
                {
                    "asset_name": "Inline Meter",
                    "asset_code": "ZINIT001",
                    "new_asset_class_name": "Inline Class",
                    "new_asset_class_prefix": "ZIN",
                    "new_asset_type_name": "Inline Type",
                    "new_asset_type_prefix": "IT",
                    "new_location_name": "Inline Yard",
                    "tracking_mode": "serialized",
                    "qty": "1",
                    "uom": "Nos",
                    "status": "Inventory",
                    "condition": "Needs Calibration",
                    "calibration_required": "1",
                    "last_calibration_date": "2026-05-01",
                    "recalibration_date": "2026-11-01",
                }
            )
            self.assertEqual(errors, [])
            db.session.commit()

            asset = assets[0]
            self.assertEqual(asset.current_location, "Inline Yard")
            self.assertEqual(asset.asset_class.name, "Inline Class")
            self.assertEqual(asset.asset_type.name, "Inline Type")
            self.assertTrue(asset.calibration_required)
            self.assertEqual(asset.condition, "Needs Calibration")
            self.assertEqual(asset.serial_number, "001")

    def test_asset_prefix_lengths_and_manual_code_are_enforced(self):
        import app as app_module

        with app.app_context():
            assets, errors = app_module._create_assets_from_asset_form(
                {
                    "asset_name": "Bad Prefix Meter",
                    "asset_code": "ZINIT002",
                    "new_asset_class_name": "Inline Class",
                    "new_asset_class_prefix": "ZI",
                    "new_asset_type_name": "Inline Type",
                    "new_asset_type_prefix": "IT",
                    "tracking_mode": "serialized",
                    "qty": "1",
                    "status": "Inventory",
                }
            )
            self.assertIsNone(assets)
            self.assertTrue(any("3 characters" in error for error in errors))

            asset_class, asset_type = self._asset_type()
            with self.assertRaises(ValueError):
                app_module._create_operational_assets(
                    asset_name="Wrong Code Helmet",
                    asset_class=asset_class,
                    asset_type=asset_type,
                    tracking_mode="serialized",
                    qty=1,
                    manual_code="BAD001",
                    status="Inventory",
                )

    def test_asset_list_and_detail_templates_render_for_store_role(self):
        import app as app_module

        with app.app_context():
            asset_class, asset_type = self._asset_type()
            asset = app_module._create_operational_assets(
                asset_name="Helmet",
                asset_class=asset_class,
                asset_type=asset_type,
                tracking_mode="serialized",
                qty=1,
                uom="Nos",
                manual_code="ZSAZH903",
                status="Inventory",
                current_location="Main Store",
                current_custodian="Stores",
                condition="Good",
            )[0]
            user = User(
                username="store_asset_test",
                password="test",
                first_name="Store",
                last_name="User",
                role="store",
                active=True,
            )
            db.session.add(user)
            db.session.commit()

            with app.test_request_context("/store/assets"):
                login_user(user)
                html = app_module.store_assets.__wrapped__()
                self.assertIn("Operational asset accountability", html)
                self.assertIn("ZSAZH903", html)

            with app.test_request_context("/store/assets/new"):
                login_user(user)
                html = app_module.create_store_asset.__wrapped__()
                self.assertIn("Create Asset", html)
                self.assertIn("Status must always be treated as authoritative persisted state.", html)

            with app.test_request_context("/store/settings"):
                login_user(user)
                html = app_module.store_settings.__wrapped__()
                self.assertIn("Asset Settings", html)
                self.assertIn("Location Settings", html)

            with app.test_request_context(f"/store/assets/{asset.id}"):
                login_user(user)
                html = app_module.store_asset_detail.__wrapped__(asset.id)
                self.assertIn("Movement History", html)
                self.assertIn("Issue Asset", html)

    def test_asset_menu_and_asset_list_are_not_role_gated(self):
        import app as app_module

        with app.app_context():
            user = User(
                username="asset_menu_user",
                password="test",
                first_name="Asset",
                last_name="Menu",
                role="user",
                active=True,
            )
            db.session.add(user)
            db.session.commit()

            with app.test_request_context("/store/inventory"):
                login_user(user)
                html = render_template_string(
                    "{% extends 'base.html' %}{% block content %}content{% endblock %}"
                )
                self.assertIn("Assets", html)
                self.assertIn("Asset Movements", html)

            with app.test_request_context("/store/assets"):
                login_user(user)
                html = app_module.store_assets.__wrapped__()
                self.assertIn("Operational asset accountability", html)


if __name__ == "__main__":
    unittest.main()
