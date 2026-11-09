"""The API route table (method, pattern, handler name, registration order) must not change when routes move between modules."""
import json
from pathlib import Path
import unittest

from tmh.platform import server
from tmh.platform.api import ROUTES

FIXTURE = Path(__file__).parent / "fixtures" / "route_table.json"


class RouteTableTest(unittest.TestCase):
    def test_route_table_matches_recorded_registration_order(self):
        recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = [[method, rx.pattern, fn.__name__] for method, rx, fn in ROUTES]
        self.assertEqual(actual, recorded)

    def test_server_module_exposes_the_same_registry(self):
        self.assertIs(server.ROUTES, ROUTES)

    def test_every_route_handler_is_still_importable_from_server(self):
        for _, _, fn in ROUTES:
            self.assertIs(getattr(server, fn.__name__), fn)


if __name__ == "__main__":
    unittest.main()
