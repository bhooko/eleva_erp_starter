import unittest

import app


class TicketClosureRuleTests(unittest.TestCase):
    def test_sales_ni_ignores_open_opportunity_tasks(self):
        ticket = {
            "category": "Sales - NI",
            "category_key": "sales-ni",
            "linked_tasks": [
                {
                    "status": "Open",
                    "related_type": "opportunity",
                }
            ],
        }

        self.assertFalse(app._ticket_has_open_linked_tasks(ticket))

    def test_other_categories_still_block_open_opportunity_tasks(self):
        ticket = {
            "category": "Support – AMC",
            "category_key": "support-amc",
            "linked_tasks": [
                {
                    "status": "Open",
                    "related_type": "opportunity",
                }
            ],
        }

        self.assertTrue(app._ticket_has_open_linked_tasks(ticket))


if __name__ == "__main__":
    unittest.main()
