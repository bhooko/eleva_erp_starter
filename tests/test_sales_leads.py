import json
import unittest
import uuid

import app
from eleva_app import db
from eleva_app import models
from eleva_app.models import SalesClient, SalesOpportunity, User


class SalesLeadTests(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app.app_context()
        self.app_context.push()
        app.ensure_bootstrap()
        self.prefix = f"LEAD{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        db.session.rollback()
        sales_lead_model = getattr(models, "SalesLead", None)
        if sales_lead_model is not None:
            sales_lead_model.query.filter(
                sales_lead_model.title.like(f"{self.prefix}%")
            ).delete(synchronize_session=False)
        SalesOpportunity.query.filter(
            SalesOpportunity.title.like(f"{self.prefix}%")
        ).delete(synchronize_session=False)
        SalesClient.query.filter(
            SalesClient.display_name.like(f"{self.prefix}%")
        ).delete(synchronize_session=False)
        User.query.filter(User.username.like(f"{self.prefix}%")).delete(
            synchronize_session=False
        )
        db.session.commit()
        self.app_context.pop()

    def _sales_lead_model(self):
        sales_lead_model = getattr(models, "SalesLead", None)
        self.assertIsNotNone(sales_lead_model, "SalesLead model is required")
        return sales_lead_model

    def _create_user(self):
        user = User(
            username=f"{self.prefix}_sales",
            password="test",
            first_name="Sales",
            last_name="User",
            email=f"{self.prefix.lower()}@example.com",
            role="user",
            active=True,
            module_permissions_json=json.dumps(
                {"sales": {"visibility": True, "assignment": True}}
            ),
        )
        db.session.add(user)
        db.session.flush()
        return user

    def test_qualified_new_installation_lead_creates_lift_opportunity(self):
        sales_lead_model = self._sales_lead_model()
        owner = self._create_user()

        lead = app._create_sales_lead(
            title=f"{self.prefix} New Installation",
            pipeline="new_installation",
            status="qualified",
            source="Call on toll free",
            contact_name="Test Contact",
            phone="9876543210",
            email="contact@example.com",
            company_name=f"{self.prefix} Customer",
            owner_user=owner,
            notes="Qualified from support call",
            convert_if_qualified=True,
        )
        db.session.commit()

        stored = sales_lead_model.query.filter_by(id=lead.id).one()
        self.assertEqual(stored.status, "qualified")
        self.assertEqual(stored.source, "Call on toll free")
        self.assertIsNotNone(stored.opportunity_id)
        self.assertEqual(stored.opportunity.pipeline, "lift")
        self.assertEqual(stored.opportunity.stage, "New Enquiry")
        self.assertEqual(stored.opportunity.owner_id, owner.id)

    def test_qualified_service_lead_creates_amc_opportunity(self):
        sales_lead_model = self._sales_lead_model()
        owner = self._create_user()

        lead = app._create_sales_lead(
            title=f"{self.prefix} AMC Renewal",
            pipeline="service",
            status="qualified",
            source="Call on toll free",
            phone="9876543211",
            company_name=f"{self.prefix} AMC Customer",
            owner_user=owner,
            convert_if_qualified=True,
        )
        db.session.commit()

        stored = sales_lead_model.query.filter_by(id=lead.id).one()
        self.assertEqual(stored.status, "qualified")
        self.assertIsNotNone(stored.opportunity_id)
        self.assertEqual(stored.opportunity.pipeline, "amc")
        self.assertEqual(stored.opportunity.stage, "New AMC Enquiry")

    def test_csv_rows_create_fresh_leads_and_convert_qualified_rows(self):
        sales_lead_model = self._sales_lead_model()
        owner = self._create_user()

        result = app._import_sales_lead_rows(
            [
                {
                    "Lead Name": f"{self.prefix} Campaign Fresh",
                    "Pipeline": "new_installation",
                    "Status": "",
                    "Contact Name": "Fresh Contact",
                    "Phone": "9000000001",
                    "Email": "fresh@example.com",
                    "Company Name": f"{self.prefix} Fresh Co",
                    "Source": "Website Campaign",
                    "Owner Email": owner.email,
                    "Notes": "Landing page form",
                },
                {
                    "Lead Name": f"{self.prefix} Campaign Qualified",
                    "Pipeline": "service",
                    "Status": "Qualified",
                    "Contact Name": "Qualified Contact",
                    "Phone": "9000000002",
                    "Email": "qualified@example.com",
                    "Company Name": f"{self.prefix} Qualified Co",
                    "Source": "Google Ads",
                    "Owner Email": owner.email,
                    "Notes": "Requested AMC quote",
                },
            ],
            actor=owner,
        )
        db.session.commit()

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["qualified"], 1)
        fresh = sales_lead_model.query.filter_by(
            title=f"{self.prefix} Campaign Fresh"
        ).one()
        qualified = sales_lead_model.query.filter_by(
            title=f"{self.prefix} Campaign Qualified"
        ).one()
        self.assertEqual(fresh.status, "fresh")
        self.assertEqual(fresh.source, "Website Campaign")
        self.assertIsNone(fresh.opportunity_id)
        self.assertEqual(qualified.status, "qualified")
        self.assertEqual(qualified.opportunity.pipeline, "amc")


if __name__ == "__main__":
    unittest.main()
