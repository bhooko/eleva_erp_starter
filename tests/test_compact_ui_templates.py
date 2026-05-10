import unittest
from pathlib import Path


class CompactUiTemplateTests(unittest.TestCase):
    def read_template(self, path):
        return Path(path).read_text(encoding="utf-8")

    def test_process_guide_is_in_top_bar_not_page_layer(self):
        template = self.read_template("templates/base.html")
        self.assertIn("data-topbar-guide-anchor", template)
        self.assertNotIn("data-floating-guide-anchor", template)
        self.assertNotIn("data-global-guide-anchor", template)
        self.assertNotIn(
            '<h1 class="text-2xl font-semibold tracking-tight">{{ section_title }}</h1>',
            template,
        )
        self.assertLess(
            template.index('id="notificationWrapper"'),
            template.index("data-topbar-guide-anchor"),
        )

    def test_projects_header_does_not_duplicate_guide_button(self):
        template = self.read_template("templates/projects.html")
        self.assertNotIn("data-floating-guide-anchor", template)
        self.assertNotIn("_section_guide_panel.html", template)

    def test_process_guides_are_not_standalone_sidebar_item(self):
        template = self.read_template("templates/base.html")
        self.assertNotIn('<span class="label">Process Guides</span>', template)

    def test_settings_contains_process_guides_tab(self):
        template = self.read_template("templates/settings.html")
        self.assertIn('"id": "process-guides"', template)
        self.assertIn("settings-panel-process-guides", template)
        self.assertIn("_process_guides_panel.html", template)

    def test_dashboard_summary_box_removed_and_filters_are_compact(self):
        template = self.read_template("templates/dashboard.html")
        self.assertNotIn("Pending Work for", template)
        self.assertNotIn("Only tasks and activities that are still pending", template)
        self.assertIn("data-dashboard-filter-toolbar", template)

    def test_customer_support_calls_uses_single_compact_title(self):
        template = self.read_template("templates/customer_support_calls.html")
        self.assertNotIn(">Customer Support</p>", template)
        self.assertIn("data-compact-page-title", template)
        self.assertIn("data-compact-filter-bar", template)

    def test_purchase_orders_removes_redundant_erp_copy(self):
        template = self.read_template("templates/purchase_orders.html")
        self.assertNotIn("This is an Eleva ERP Purchase Order workspace", template)


if __name__ == "__main__":
    unittest.main()
