from pathlib import Path
import unittest


APP_SOURCE = Path(__file__).resolve().parents[1] / "docs" / "app.js"


class DashboardFreshnessTests(unittest.TestCase):
    def test_latest_successful_check_query_is_server_filtered_before_pagination(self):
        source = APP_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "actions/workflows/publish-macos-latest.yml/runs?branch=main&event=schedule&status=success&per_page=1",
            source,
        )
        # Keep client-side checks as a defensive guard as well.
        self.assertIn('run.event === "schedule"', source)
        self.assertIn('run.conclusion === "success"', source)


if __name__ == "__main__":
    unittest.main()
