"""Fixed upstream transport with synthetic credentials and controlled responses.

These tests do not contact a provider or admit the namespace/Runner carrier.
"""
import hashlib
import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import os
import ssl
import threading
import time
import unittest
from unittest import mock

from tmh.platform import codex_gateway as G
from tmh.platform.codex_frozen_config import PUBLIC_KEY
from tests import test_codex_frozen_config as fixtures


class Response:
    def __init__(self, chunks=(b"abc", b"def"), status=200, headers=None):
        self.status = status
        self.headers = headers if headers is not None else [("Content-Length", "6"), ("Content-Type", "text/event-stream")]
        self.chunks = list(chunks)
        self.closed = False

    def close(self):
        self.closed = True

    def getheaders(self):
        return self.headers

    def read1(self, count):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk


class Connection:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.headers = []
        self.body = None
        self.sock = mock.Mock()
        self.closed = False

    def putrequest(self, *args, **kw):
        self.request = args, kw

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self, body):
        self.body = body

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


@unittest.skipUnless(os.name == "posix" and importlib.util.find_spec("tomllib"), "Linux carrier configuration requires POSIX/Python3.11+")
class CodexGatewayTest(unittest.TestCase):
    def setUp(self):
        # Reuse only the original file fixture, not its tests or assertions.
        self.fixture = fixtures.CodexFrozenConfigTest("test_generated_worker_gets_selected_model_and_only_public_gateway")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.frozen = self.fixture.freeze()
        self.body = b'{"model":"team-model","input":"synthetic"}'
        self.headers = [("Host", G.HOST), ("Authorization", "Bearer " + PUBLIC_KEY),
                        ("Content-Type", "application/json"), ("Content-Length", str(len(self.body))),
                        ("User-Agent", "synthetic-official-header"), ("x-client-request-id", "synthetic-request")]
        self.events = []
        self.out_headers = []
        self.out_body = []
        self.connection = Connection(Response())
        patch = mock.patch.object(G.http.client, "HTTPSConnection", return_value=self.connection)
        self.factory = patch.start()
        self.addCleanup(patch.stop)

    def forward(self, **kw):
        args = dict(deadline=time.monotonic() + 5, on_headers=lambda status, headers: self.out_headers.append((status, headers)),
                    on_body=self.out_body.append, journal=lambda kind, value: self.events.append((kind, value)))
        args.update(kw)
        return G.forward(self.frozen, {}, "POST", G.TARGET, self.headers, self.body, **args)

    def test_actor_auth_is_injected_only_by_host_and_worker_cannot_shadow_it(self):
        actor = "Bearer PUBLIC_SYNTHETIC_ACTOR_CREDENTIAL"
        self.fixture.write(self.fixture.base, self.fixture.base.read_text() +
            '\nrequires_openai_auth=false\nsupports_websockets=true\nsupports_standalone_web_search=true\n'
            '[model_providers.gateway.http_headers]\nx-openai-actor-authorization="' + actor + '"\n')
        self.frozen = self.fixture.freeze()
        with self.live_provider(fixed_body=b"public response") as server:
            receipt = self.forward()
            self.assertTrue(receipt["complete"])
            self.assertEqual(len(server.received), 1)
            target, headers, body = server.received[0]
            actors = [value for name, value in headers if name.lower() == "x-openai-actor-authorization"]
            self.assertEqual(actors, [actor])
            self.assertEqual(target, G.TARGET)
            self.assertEqual(body, self.body)
            self.assertEqual([value for name, value in headers if name.lower() == "authorization"],
                             ["Bearer SYNTHETIC_HOST_CREDENTIAL_ONLY"])
        self.assertNotIn(actor, str(self.events))
        self.assertNotIn(actor.encode(), self.frozen.worker_config())
        self.headers.append(("X-OpenAI-Actor-Authorization", "PUBLIC_WORKER_FORGERY"))
        self.factory.reset_mock()
        with self.assertRaises(G.GatewayError):
            self.forward()
        self.factory.assert_not_called()

    @contextlib.contextmanager
    def live_provider(self, short=False, fixed_body=None):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                self.server.received.append((self.path, list(self.headers.items()), self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                if fixed_body is not None:
                    self.send_header("Content-Length", str(len(fixed_body)))
                elif short:
                    self.send_header("Content-Length", "6")
                else:
                    self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(fixed_body if fixed_body is not None else
                                 b"abc" if short else b"3\r\nabc\r\n3\r\ndef\r\n0\r\n\r\n")
                self.wfile.flush()
                self.close_connection = True

        server = HTTPServer(("127.0.0.1", 0), Handler)
        server.received = []
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
        thread.start()
        # Only this test replaces TLS with a loopback HTTP peer. Production has
        # no fixture endpoint or connection-factory configuration switch.
        self.factory.side_effect = lambda host, port, **kw: http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=kw["timeout"])
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive(), "synthetic provider thread leaked")

    def test_real_loopback_chunked_http_preserves_payload_and_exact_request(self):
        with self.live_provider() as server:
            result = self.forward()
            self.assertEqual(len(server.received), 1)
            target, headers, body = server.received[0]
            self.assertEqual(target, G.TARGET)
            self.assertEqual(body, self.body)
            self.assertIn(("Authorization", "Bearer SYNTHETIC_HOST_CREDENTIAL_ONLY"), headers)
        self.assertEqual(b"".join(self.out_body), b"abcdef")
        self.assertTrue(result["complete"])
        self.assertEqual(result["bytes"], 6)
        self.assertEqual(b"".join(value for kind, value in self.events if kind == "response_body"), b"abcdef")
        self.assertNotIn("Transfer-Encoding", [name for name, value in self.out_headers[0][1]])

    def test_real_loopback_short_content_length_is_failure_with_original_prefix(self):
        with self.live_provider(short=True) as server:
            with self.assertRaises(G.GatewayError):
                self.forward()
            self.assertEqual(len(server.received), 1)
        self.assertEqual(b"".join(self.out_body), b"abc")
        self.assertEqual(self.events[-1][0], "failed")
        self.assertEqual(self.events[-1][1]["received_bytes"], 3)
        self.assertFalse(self.events[-1][1]["complete"])

    def test_real_loopback_complete_content_length_closes_without_false_failure(self):
        for body in (b"abcdef", b""):
            with self.subTest(body=body):
                self.events.clear()
                self.out_body.clear()
                with self.live_provider(fixed_body=body) as server:
                    result = self.forward()
                    self.assertEqual(len(server.received), 1)
                self.assertEqual(b"".join(self.out_body), body)
                self.assertEqual(result["bytes"], len(body))
                self.assertTrue(result["complete"])
                self.assertEqual(self.events[-1][0], "response_complete")

    def test_fixed_https_target_preserves_official_identity_and_full_body(self):
        result = self.forward()
        self.assertEqual(self.factory.call_args.args, ("gateway.example", 443))
        context = self.factory.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(self.connection.request, (("POST", "/v1/responses"), {"skip_host": True, "skip_accept_encoding": True}))
        self.assertEqual(self.connection.body, self.body)
        self.assertIn(("User-Agent", "synthetic-official-header"), self.connection.headers)
        self.assertIn(("x-client-request-id", "synthetic-request"), self.connection.headers)
        self.assertEqual([v for k, v in self.connection.headers if k == "Authorization"], ["Bearer SYNTHETIC_HOST_CREDENTIAL_ONLY"])
        self.assertEqual(b"".join(self.out_body), b"abcdef")
        self.assertEqual(result["sha256"], hashlib.sha256(b"abcdef").hexdigest())
        self.assertEqual(result["http_exchanges"], 1)
        self.assertTrue(result["complete"])
        self.assertTrue(self.connection.closed)
        self.assertNotIn("SYNTHETIC_HOST_CREDENTIAL_ONLY", repr(self.events))
        self.assertTrue(all(call.args[0] <= 5 for call in self.connection.sock.settimeout.call_args_list))

    def test_bad_route_identity_or_framing_never_opens_upstream(self):
        original = list(self.headers)
        mutations = [original + [("Host", G.HOST)],
                     [(k, "Bearer other") if k == "Authorization" else (k, v) for k, v in original],
                     [(k, "3") if k == "Content-Length" else (k, v) for k, v in original],
                     original + [("Transfer-Encoding", "chunked")],
                     original + [("Connection", "Authorization")]]
        for headers in mutations:
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                G.forward(self.frozen, {}, "POST", G.TARGET, headers, self.body,
                          deadline=time.monotonic() + 5, on_headers=mock.Mock(), on_body=mock.Mock(), journal=mock.Mock())
        for method, target in (("CONNECT", G.TARGET), ("POST", "https://other.example/v1/responses"), ("POST", "/v1/models")):
            with self.subTest(method=method, target=target), self.assertRaises(G.GatewayError):
                G.forward(self.frozen, {}, method, target, original, self.body,
                          deadline=time.monotonic() + 5, on_headers=mock.Mock(), on_body=mock.Mock(), journal=mock.Mock())
        self.factory.assert_not_called()

    def test_model_substitution_duplicate_keys_and_invalid_json_do_not_connect(self):
        for body in (b'{"model":"other-model"}', b'{"model":"other-model","model":"team-model"}',
                     b'{"model":"team-model","input":NaN}', b'{"model":"team-model"} trailing'):
            headers = [(name, str(len(body)) if name == "Content-Length" else value) for name, value in self.headers]
            with self.subTest(body=body), self.assertRaises(G.GatewayError):
                G.forward(self.frozen, {}, "POST", G.TARGET, headers, body,
                          deadline=time.monotonic() + 5, on_headers=mock.Mock(), on_body=mock.Mock(), journal=mock.Mock())
        self.factory.assert_not_called()

    def test_redirect_is_retained_but_not_followed_or_exposed_to_worker(self):
        self.connection.response = Response(status=307, headers=[("Location", "https://other.example/secret"), ("Content-Length", "6")])
        with self.assertRaises(G.GatewayError):
            self.forward()
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.out_headers[0][0], 502)
        self.assertNotIn("Location", [k for k, v in self.out_headers[0][1]])
        self.assertEqual(self.out_body, [])
        self.assertEqual(b"".join(value for kind, value in self.events if kind == "response_body"), b"abcdef")
        self.assertTrue(self.connection.closed)
        self.assertEqual(self.events[-1][0], "failed")

    def test_incomplete_response_keeps_all_received_bytes_and_is_not_complete(self):
        self.connection.response = Response(chunks=[b"abc", http.client.IncompleteRead(b"de", 1)])
        with self.assertRaises(G.GatewayError):
            self.forward()
        self.assertEqual(b"".join(self.out_body), b"abcde")
        self.assertEqual(b"".join(value for kind, value in self.events if kind == "response_body"), b"abcde")
        self.assertEqual(self.events[-1][1]["received_bytes"], 5)
        self.assertFalse(self.events[-1][1]["complete"])
        self.assertNotIn("completed", [kind for kind, value in self.events])
        self.assertTrue(self.connection.closed)

    def test_response_handle_is_closed_for_success_and_incomplete_input(self):
        for incomplete in (False, True):
            with self.subTest(incomplete=incomplete):
                response = Response(chunks=[b"abc", http.client.IncompleteRead(b"de", 1)] if incomplete else [b"abcdef"])
                self.connection = Connection(response)
                self.factory.return_value = self.connection
                if incomplete:
                    with self.assertRaises(G.GatewayError):
                        self.forward()
                else:
                    self.forward()
                self.assertTrue(response.closed, "HTTPResponse can retain a socket after HTTPConnection.close")
                self.assertTrue(self.connection.closed)

    def test_expiry_and_cancellation_preserve_original_deadline_no_retry(self):
        for deadline in (time.monotonic() - 1, float("inf"), True):
            with self.subTest(deadline=deadline), self.assertRaises(G.GatewayError):
                self.forward(deadline=deadline)
        self.factory.assert_not_called()
        stop = threading.Event()

        def first_chunk_then_cancel(chunk):
            self.out_body.append(chunk)
            stop.set()

        with self.assertRaises(G.GatewayError):
            self.forward(cancel=stop, on_body=first_chunk_then_cancel)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.out_body, [b"abc"])
        self.assertFalse(self.events[-1][1]["complete"])
        self.assertTrue(self.connection.closed)

    def test_changed_config_rejects_before_connect_and_diagnostics_hide_credential(self):
        original = self.fixture.base.read_text()
        self.fixture.write(self.fixture.base, original + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.forward()
        self.factory.assert_not_called()
        self.fixture.write(self.fixture.base, original)
        self.connection.getresponse = mock.Mock(side_effect=OSError("SYNTHETIC_HOST_CREDENTIAL_ONLY"))
        try:
            self.forward()
        except G.GatewayError as error:
            self.assertNotIn("SYNTHETIC_HOST_CREDENTIAL_ONLY", str(error))
        else:
            self.fail("failed upstream response accepted")
        self.assertNotIn("SYNTHETIC_HOST_CREDENTIAL_ONLY", repr(self.events))
        self.assertEqual(self.factory.call_count, 1)
        self.assertTrue(self.connection.closed)

    def test_journal_or_close_cannot_return_success_after_original_deadline(self):
        for late in ("journal", "close"):
            with self.subTest(late=late):
                clock = [100.0]
                self.connection = Connection(Response())
                self.factory.return_value = self.connection
                self.events.clear()
                original_close = self.connection.close

                def close():
                    original_close()
                    if late == "close":
                        clock[0] = 106.0

                def journal(kind, value):
                    self.events.append((kind, value))
                    if late == "journal" and kind in ("completed", "response_complete"):
                        clock[0] = 106.0

                self.connection.close = close
                with mock.patch.object(G.time, "monotonic", side_effect=lambda: clock[0]):
                    with self.assertRaises(G.GatewayError):
                        self.forward(deadline=105.0, journal=journal)
                self.assertTrue(self.connection.closed)


if __name__ == "__main__":
    unittest.main()
