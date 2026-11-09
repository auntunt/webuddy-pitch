"""Connection methods for executors: fixed login commands only, gateway model listing, and refusals for bad input."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tmh.platform import agent_connect
from tmh.platform.errors import ApiError


class _Gateway(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"data": [{"id": "gpt-local-a"}, {"id": "bad id with spaces"}, {"id": "gpt-local-b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class AgentConnectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Gateway)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_gateway_models_come_from_v1_models_and_drop_unsafe_ids(self):
        self.assertEqual(agent_connect.probe_gateway(self.url), ["gpt-local-a", "gpt-local-b"])

    def test_gateway_url_must_be_http_and_reachable(self):
        with self.assertRaises(ApiError):
            agent_connect.probe_gateway("ftp://example.com")
        with self.assertRaises(ApiError):
            agent_connect.probe_gateway("http://127.0.0.1:1")

    def test_login_only_runs_fixed_commands_per_engine(self):
        self.assertEqual(agent_connect.LOGIN_COMMANDS["codex"], ["login"])
        self.assertEqual(agent_connect.LOGIN_COMMANDS["claude"], ["setup-token"])
        with self.assertRaises(ApiError):
            agent_connect.start_login("cursor", "/bin/true", {})

    def test_unknown_login_session_is_not_found(self):
        with self.assertRaises(ApiError) as caught:
            agent_connect.read_login("missing")
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
