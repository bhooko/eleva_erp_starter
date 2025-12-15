import unittest

import app


class OtherDepartmentVisibilityTests(unittest.TestCase):
    def test_ticket_category_detection(self):
        self.assertTrue(app._ticket_is_other_department({"category": "Other Department"}))
        self.assertTrue(app._ticket_is_other_department({"category_key": "other-dept"}))
        self.assertFalse(app._ticket_is_other_department({"category": "Support – AMC"}))

    def test_filtering_other_department_records(self):
        records = [
            {"id": 1, "category": "Support – NI", "category_key": "support-ni"},
            {"id": 2, "category": "Other Department", "category_key": "other-dept"},
            {"id": 3, "category": "Other Query", "category_key": "other-query"},
        ]

        filtered = app._filter_other_department_records(records)
        self.assertEqual([record["id"] for record in filtered], [1, 3])

        with_other_department = app._filter_other_department_records(
            records, include_other_department=True
        )
        self.assertEqual([record["id"] for record in with_other_department], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
