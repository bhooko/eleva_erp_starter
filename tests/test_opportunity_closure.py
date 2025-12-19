import unittest

import app
from eleva_app import db
from eleva_app.models import (
    ClientRequirementForm,
    FormTemplate,
    SalesOpportunity,
    SalesOpportunityItem,
)


class OpportunityClosureTests(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app.app_context()
        self.app_context.push()
        app.ensure_bootstrap()
        app._guarantee_primary_crf_template()

    def tearDown(self):
        db.session.rollback()
        self.app_context.pop()

    def test_final_crf_satisfies_missing_check(self):
        template = (
            FormTemplate.query.filter_by(type="client_requirements")
            .order_by(FormTemplate.updated_at.desc())
            .first()
        )
        opportunity = SalesOpportunity(title="Test Close", pipeline="lift", stage="Negotiation")
        item = SalesOpportunityItem(opportunity=opportunity, lift_type="MRL")
        db.session.add_all([opportunity, item])
        db.session.flush()

        form = ClientRequirementForm(
            opportunity=opportunity,
            template=template,
            version=1,
            status="design_confirmed",
            sales_section_data="{}",
            design_section_data="{}",
        )
        db.session.add(form)
        db.session.flush()
        opportunity.final_crf_id = form.id
        db.session.commit()

        missing = app._missing_confirmed_client_requirement_forms(opportunity)
        self.assertEqual(missing, [])

    def test_convert_creates_project_per_item(self):
        opportunity = SalesOpportunity(title="Won Deal", pipeline="lift", stage="Closed Won")
        item_one = SalesOpportunityItem(opportunity=opportunity, lift_type="Traction")
        item_two = SalesOpportunityItem(opportunity=opportunity, lift_type="Hydraulic")
        db.session.add_all([opportunity, item_one, item_two])
        db.session.commit()

        projects = app.convert_opportunity_to_projects(opportunity)

        self.assertEqual(len(projects), 2)
        self.assertTrue(all(item.project_id for item in [item_one, item_two]))
        self.assertIn("Item 1", projects[0].name)
        self.assertIn("Item 2", projects[1].name)


if __name__ == "__main__":
    unittest.main()
