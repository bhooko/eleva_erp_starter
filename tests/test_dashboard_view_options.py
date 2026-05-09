import unittest
from pathlib import Path


class DashboardViewOptionsTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = Path("templates/dashboard.html").read_text(encoding="utf-8")

    def test_dashboard_has_table_and_kanban_view_options(self):
        self.assertIn('data-view-mode-value="table"', self.template)
        self.assertIn('data-view-mode-value="kanban"', self.template)
        self.assertIn('data-view-pane data-view-mode="table"', self.template)
        self.assertIn('data-view-pane data-view-mode="kanban"', self.template)

    def test_dashboard_has_grouped_and_all_together_options(self):
        self.assertIn('data-group-mode-value="module"', self.template)
        self.assertIn('data-group-mode-value="all"', self.template)
        self.assertIn('data-group-mode="module"', self.template)
        self.assertIn('data-group-mode="all"', self.template)


if __name__ == "__main__":
    unittest.main()
