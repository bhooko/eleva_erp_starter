import datetime
import unittest
import uuid

from flask_login import login_user

import app
from eleva_app import db
from eleva_app.models import (
    DeliveryChallan,
    DeliveryChallanItem,
    DesignTask,
    InventoryItem,
    InventoryReceipt,
    InventoryReceiptItem,
    Lift,
    Project,
    PurchaseOrder,
    PurchaseOrderItem,
    ServiceContract,
    ServiceContractLift,
    SRTTask,
    User,
)


class Phase1FlowFixTests(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app.app_context()
        self.app_context.push()
        app.ensure_bootstrap()
        self.prefix = f"T{uuid.uuid4().hex[:8]}"
        app.SRT_SAMPLE_TASKS.clear()

    def tearDown(self):
        db.session.rollback()
        prefix_like = f"{self.prefix}%"

        DeliveryChallanItem.query.filter(
            DeliveryChallanItem.item_code.like(prefix_like)
        ).delete(synchronize_session=False)
        DeliveryChallan.query.filter(
            DeliveryChallan.dc_number.like(prefix_like)
        ).delete(synchronize_session=False)
        InventoryReceiptItem.query.filter(
            InventoryReceiptItem.item_code.like(prefix_like)
        ).delete(synchronize_session=False)
        InventoryReceipt.query.filter(
            InventoryReceipt.receipt_number.like(prefix_like)
        ).delete(synchronize_session=False)
        PurchaseOrderItem.query.filter(
            PurchaseOrderItem.item_code.like(prefix_like)
        ).delete(synchronize_session=False)
        PurchaseOrder.query.filter(
            PurchaseOrder.po_number.like(prefix_like)
        ).delete(synchronize_session=False)
        ServiceContractLift.query.filter(
            ServiceContractLift.lift_identity.like(prefix_like)
        ).delete(synchronize_session=False)
        ServiceContract.query.filter(
            ServiceContract.contract_no.like(prefix_like)
        ).delete(synchronize_session=False)
        SRTTask.query.filter(SRTTask.summary.like(prefix_like)).delete(
            synchronize_session=False
        )
        DesignTask.query.filter(DesignTask.task_name.like(prefix_like)).delete(
            synchronize_session=False
        )
        Project.query.filter(Project.name.like(prefix_like)).delete(
            synchronize_session=False
        )
        InventoryItem.query.filter(InventoryItem.item_code.like(prefix_like)).delete(
            synchronize_session=False
        )
        Lift.query.filter(Lift.lift_code.like(prefix_like)).delete(
            synchronize_session=False
        )
        User.query.filter(User.username.like(prefix_like)).delete(
            synchronize_session=False
        )
        db.session.commit()
        app.SRT_SAMPLE_TASKS.clear()
        self.app_context.pop()

    def _create_user(self, suffix="user"):
        user = User(
            username=f"{self.prefix}_{suffix}",
            password="test",
            first_name="Flow",
            last_name=suffix.title(),
            role="user",
            active=True,
        )
        db.session.add(user)
        db.session.flush()
        return user

    def test_support_ticket_linked_lift_object_creates_service_visit(self):
        lift = Lift(lift_code=f"{self.prefix}-LIFT")
        db.session.add(lift)
        db.session.flush()

        ticket = {
            "id": f"{self.prefix}-TICKET",
            "category_key": "breakdown",
            "category": "Breakdown",
            "subject": "Lift stopped",
            "remarks": "Customer reported stoppage",
            "linked_lift": {"id": lift.id, "name": lift.lift_code},
        }

        app._create_service_visit_from_support_ticket(ticket)
        db.session.flush()

        schedule = lift.service_schedule
        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule[0]["source"], "support_ticket")
        self.assertEqual(schedule[0]["support_ticket_ref"], ticket["id"])

    def test_contract_save_links_lift_to_amc_contract(self):
        lift = Lift(lift_code=f"{self.prefix}-AMC")
        contract = ServiceContract(contract_no=f"{self.prefix}-CONTRACT")
        db.session.add_all([lift, contract])
        db.session.flush()

        with app.app.test_request_context(
            "/service/contracts/new",
            method="POST",
            data={
                "contract_no": contract.contract_no,
                "customer_name": "Test Customer",
                "contract_type": "non_comprehensive",
                "duration_years": "1",
                "frequency_per_year": "12",
                "start_date": "2026-04-25",
                "apply_to_lift_amc": "on",
            },
        ):
            app._save_contract_from_form(
                contract,
                lift_rows=[
                    {
                        "linked_lift_id": lift.id,
                        "lift_identity": lift.lift_code,
                        "lift_type_key": "passenger",
                        "floors_value": "G+1",
                    }
                ],
            )

        self.assertEqual(lift.amc_contract_id, str(contract.id))
        self.assertEqual(lift.amc_start, datetime.date(2026, 4, 25))

    def test_receipt_logged_quantity_counts_only_closed_ok_receipts(self):
        po = PurchaseOrder(po_number=f"{self.prefix}-PO", status="Issued")
        db.session.add(po)
        db.session.flush()
        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            item_code=f"{self.prefix}-ITEM",
            part_name="Test part",
            quantity_ordered=10,
        )
        db.session.add(po_item)
        db.session.flush()

        rows = [
            ("OPEN", "Open", "OK", 4),
            ("NG", "Closed", "NG", 3),
            ("OK", "Closed", "OK", 2),
        ]
        for suffix, status, qc_status, qty in rows:
            receipt = InventoryReceipt(
                purchase_order_id=po.id,
                receipt_number=f"{self.prefix}-GRN-{suffix}",
                status=status,
            )
            db.session.add(receipt)
            db.session.flush()
            db.session.add(
                InventoryReceiptItem(
                    inventory_receipt_id=receipt.id,
                    purchase_order_item_id=po_item.id,
                    item_code=po_item.item_code,
                    quantity_received=qty,
                    qc_status=qc_status,
                )
            )
        db.session.flush()

        self.assertEqual(app._receipt_qty_already_logged(po_item.id), 2)

    def test_dispatch_completion_blocks_when_physical_stock_is_short(self):
        inventory = InventoryItem(
            item_code=f"{self.prefix}-STOCK",
            description="Stock item",
            current_stock=2,
            book_stock=2,
        )
        dispatch = DeliveryChallan(dc_number=f"{self.prefix}-DC", status="Draft")
        db.session.add_all([inventory, dispatch])
        db.session.flush()
        db.session.add(
            DeliveryChallanItem(
                delivery_challan_id=dispatch.id,
                item_code=inventory.item_code,
                description=inventory.description,
                qty_delivered=5,
            )
        )
        db.session.commit()

        with app.app.test_request_context(
            f"/store/dispatch/{dispatch.id}/complete",
            method="POST",
            data={
                "receiver_name": "Site Receiver",
                "receiver_signature": "data:image/png;base64,abc",
            },
        ):
            app.complete_dispatch.__wrapped__(dispatch.id)

        db.session.refresh(inventory)
        db.session.refresh(dispatch)
        self.assertEqual(inventory.current_stock, 2)
        self.assertFalse(dispatch.is_completed)

    def test_srt_update_persists_db_backed_task(self):
        user = self._create_user("srt")
        task = SRTTask(
            summary=f"{self.prefix} SRT",
            description="Site readiness",
            status="Scheduled",
            priority="Normal",
            due_date=datetime.date(2026, 4, 30),
            assigned_to_id=user.id,
        )
        db.session.add(task)
        db.session.commit()

        original_visibility_guard = app._module_visibility_required
        app._module_visibility_required = lambda module_key: None
        try:
            with app.app.test_request_context(
                f"/srt/task/SRT-{task.id}/update",
                method="POST",
                data={
                    "status": "Closed",
                    "owner": user.display_name,
                    "due_date": "2026-05-01",
                    "comment": "Completed at site",
                },
            ):
                login_user(user)
                app.srt_task_update.__wrapped__(f"SRT-{task.id}")
        finally:
            app._module_visibility_required = original_visibility_guard

        db.session.refresh(task)
        self.assertEqual(task.status, "Closed")
        self.assertEqual(task.due_date, datetime.date(2026, 5, 1))

    def test_dashboard_includes_assigned_design_and_srt_tasks(self):
        user = self._create_user("dashboard")
        project = Project(name=f"{self.prefix} Project")
        db.session.add(project)
        db.session.flush()
        design = DesignTask(
            project_id=project.id,
            project_name=project.name,
            task_type="design",
            task_name=f"{self.prefix} Design",
            status="Drawing pending",
            assigned_to_user_id=user.id,
            requested_by_user_id=user.id,
            due_date=datetime.date(2026, 4, 29),
        )
        srt = SRTTask(
            project_id=project.id,
            summary=f"{self.prefix} SRT dashboard",
            description="Check shaft readiness",
            status="Scheduled",
            priority="High",
            due_date=datetime.date(2026, 4, 28),
            assigned_to_id=user.id,
        )
        db.session.add_all([design, srt])
        db.session.commit()

        with app.app.test_request_context("/dashboard"):
            login_user(user)
            overview = app._build_task_overview(user)

        all_titles = [
            item["title"]
            for module in overview["pending_modules"]
            for item in module.get("items", [])
        ]
        self.assertIn(design.task_name, all_titles)
        self.assertIn(srt.summary, all_titles)


if __name__ == "__main__":
    unittest.main()
