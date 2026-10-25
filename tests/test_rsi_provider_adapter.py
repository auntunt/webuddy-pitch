"""Controlled local HTTP proves adapter mechanics, not real provider/RSI gain."""
import copy
import hashlib
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from scripts.rsi import provider_adapter as P
from scripts.rsi import trial_preparation as L
from tmh.platform.store import Store
from tmh.platform import supervised_process as SP
from test_rsi_trial_preparation import contract


def native():
    return {"id": "msg_local_fixture", "type": "message", "role": "assistant", "model": "fixture-response-v1",
            "stop_reason": "end_turn", "content": [{"type": "text", "text": "完整输出\n中文 / 😀"}],
            "usage": {"input_tokens": 4, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2,
                      "cache_creation": {"ephemeral_5m_input_tokens": 3, "ephemeral_1h_input_tokens": 0}, "output_tokens": 2}}


@unittest.skipUnless(os.name == "posix", "private directory FDs and supervised HTTP transport require POSIX")
class ProviderAdapterTests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get("RSI_PROVIDER_EVIDENCE_DIR")
        if retained:
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=retained))
        else:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            self.root = Path(temp.name)
        self.root.chmod(0o700)
        self.store = Store(self.root / "fixture.db")
        self.addCleanup(self.store.db.close)
        self.ledger = L.Ledger(self.store)
        self.registry_dir = self.root / "registry"
        self.registry_dir.mkdir(mode=0o700)
        self.creds = self.registry_dir / "credentials"
        self.creds.mkdir(mode=0o700)
        self.secret = "synthetic_" + uuid.uuid4().hex
        (self.creds / "fixture-generation").write_text(self.secret)
        (self.creds / "fixture-generation").chmod(0o600)
        self.seen, self.release = threading.Event(), threading.Event()
        self.lock = threading.Lock()
        self.count, self.requests, self.auth_ok = 0, [], []
        self.response, self.status, self.wait = native(), 200, False
        self.raw_override, self.extra_length, self.chunked = None, 0, False
        case = self
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                with case.lock:
                    case.count += 1
                    case.requests.append(body)
                    case.auth_ok.append(self.headers.get("x-api-key") == case.secret)
                case.seen.set()
                if case.wait:
                    case.release.wait(15)
                raw = case.raw_override if case.raw_override is not None else json.dumps(case.response, ensure_ascii=False).encode()
                try:
                    self.send_response(case.status)
                    self.send_header("Content-Type", "application/json")
                    if case.status == 302:
                        self.send_header("Location", f"http://127.0.0.1:{case.server.server_port}/v1/messages")
                    if case.chunked:
                        self.send_header("Transfer-Encoding", "chunked")
                    else:
                        self.send_header("Content-Length", str(len(raw) + case.extra_length))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if case.chunked:
                        self.wfile.write(f"{len(raw):X}\r\n".encode() + raw + b"\r\n0\r\n\r\n")
                    else:
                        self.wfile.write(raw)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = False
        # Only the fixture's idle selector poll; real transport deadlines and
        # joining the non-daemon request handlers remain unchanged.
        self.server_thread = threading.Thread(target=self.server.serve_forever,
                                              kwargs={"poll_interval": 0.01})
        self.server_thread.start()
        self.addCleanup(self.shutdown)
        self.base = contract()
        self.base["limits"] = {"calls": 8, "billed_tokens": 10000, "cost_micro_cny": 100000, "deadline_us": time.time_ns() // 1000 + 60000000}
        self.base["price"]["cached_micro_cny_per_token"] = self.base["price"]["input_micro_cny_per_token"]
        self.profile = {"schema": P.VERSION, "mode": "fixture", "approved": True,
                        "contract_sha256": L.digest(self.base), "protocol_sha256": "a" * 64,
                        "endpoint": f"http://127.0.0.1:{self.server.server_port}/v1/messages", "credential_ref": "fixture-generation",
                        "model": copy.deepcopy(self.base["model"]), "price": copy.deepcopy(self.base["price"]),
                        "input_cap_tokens": 100, "output_cap_tokens": 20, "call_timeout_ms": 5000,
                        "valid_until_us": self.base["limits"]["deadline_us"], "input_cap_reference_sha256": "b" * 64,
                        "parameters_version": "messages-text-standard-v1", "max_response_bytes": 1000000,
                        "billing_mode": "token-only-upper-bound"}
        self.write_profile()
        self.registry = P.Registry(self.registry_dir, trusted_uid=os.getuid(), allow_test_loopback=True)
        self.addCleanup(lambda: self.registry.close())
        self.adapter = P.Adapter(self.ledger, self.registry, self.root / "evidence")
        self.key = self.adapter.register("fixture", self.base)
        self.system = "全部系统输入\n"
        self.messages = [{"role": "user", "content": "所有历史、知识输入\n😀"}]

    def shutdown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(3)
        if self.server_thread.is_alive():
            raise AssertionError("fixture server thread leaked")

    def write_profile(self):
        (self.registry_dir / "fixture.json").write_text(L.encoded(self.profile))
        (self.registry_dir / "fixture.json").chmod(0o600)

    def dispatch(self, req="one", phase="propose", **kwargs):
        return self.adapter.dispatch(self.key, req, phase, system=self.system, messages=self.messages, **kwargs)

    def unknown_held(self):
        result = self.dispatch()
        self.assertEqual(result["state"], "unknown")
        self.assertFalse(result["response_complete"])
        inspect = self.ledger.inspect(self.key)
        self.assertTrue(inspect["blocked"])
        self.assertEqual(inspect["totals"], {"calls": 1, "billed_tokens": 120, "cost_micro_cny": 1400})
        self.assertEqual(self.dispatch()["state"], "unknown")
        with self.assertRaises(L.Conflict):
            self.dispatch("another", "retry")
        self.assertEqual(self.count, 1)
        return result

    def test_success_full_raw_cache_accounting_and_no_credential_artifact(self):
        result = self.dispatch()
        self.assertEqual(result["state"], "settled")
        self.assertTrue(result["response_complete"])
        self.assertFalse(result["actual_provider_charge_verified"])
        self.assertFalse(result["rsi_qualified"])
        self.assertEqual((result["input_tokens"], result["output_tokens"]), (9, 2))
        self.assertEqual(self.ledger.inspect(self.key)["totals"], {"calls": 1, "billed_tokens": 11, "cost_micro_cny": 130})
        folder = Path(result["evidence"])
        frame, raw = (folder / "transport/output.bin").read_bytes().split(b"\n", 1)
        self.assertEqual(raw, json.dumps(self.response, ensure_ascii=False).encode())
        self.assertEqual(result["response_sha256"], hashlib.sha256(raw).hexdigest())
        sent = json.loads(self.requests[0])
        self.assertEqual(sent["messages"], self.messages)
        self.assertEqual(sent["system"], self.system)
        self.assertEqual(sent["max_tokens"], 20)
        self.assertFalse(sent["stream"])
        self.assertEqual(self.auth_ok, [True])
        for path in (self.root / "evidence").rglob("*"):
            if path.is_file():
                self.assertNotIn(self.secret.encode(), path.read_bytes(), path.name)
        self.assertFalse(self.dispatch()["new_dispatch"])
        self.assertTrue(self.adapter.reconcile(self.key, "one")["response_complete"])
        self.assertEqual(self.count, 1)

    def test_all_phases_share_root_and_terminal_consumption(self):
        for i, phase in enumerate(["propose", "probe", "judge", "retry", "terminal", "baseline", "candidate", "followup"]):
            if phase == "terminal":
                with self.assertRaises(L.Conflict):
                    self.dispatch(str(i), phase)
                self.assertTrue(self.ledger.consume_holdout(self.key))
            self.assertEqual(self.dispatch(str(i), phase)["state"], "settled")
        self.assertEqual(self.count, 8)
        self.assertEqual(self.ledger.inspect(self.key)["totals"]["calls"], 8)
        with self.assertRaises(L.Conflict):
            self.dispatch("ninth")
        changed = copy.deepcopy(self.base); changed["limits"]["calls"] += 1
        with self.assertRaises(L.Conflict):
            self.adapter.register("fixture", changed)

    def test_input_token_and_money_caps_deny_before_network(self):
        for cap, value in (("billed_tokens", 119), ("cost_micro_cny", 1399)):
            base = copy.deepcopy(self.base); base["root_family"] += cap; base["limits"][cap] = value
            self.profile["contract_sha256"] = L.digest(base)
            self.write_profile()
            key = self.adapter.register("fixture", base)
            with self.assertRaises(L.Conflict):
                self.adapter.dispatch(key, "x", "propose", system="", messages=self.messages)
            self.assertEqual(self.ledger.inspect(key)["totals"]["calls"], 0)
        self.assertEqual(self.count, 0)

    def test_missing_unapproved_changed_profile_and_material_zero_send(self):
        path = self.registry_dir / "fixture.json"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(FileNotFoundError):self.dispatch()
        path.write_bytes(original);path.chmod(0o600)
        for key, value in (("approved", False), ("input_cap_tokens", 99), ("valid_until_us", 1), ("protocol_sha256", "c" * 64)):
            self.profile[key], old = value, self.profile[key]
            self.write_profile()
            with self.assertRaises((L.Conflict, ValueError)):self.dispatch()
            self.profile[key] = old
        self.write_profile()
        self.assertEqual(self.count, 0)
        self.dispatch()
        self.messages[0]["content"] += "changed"
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(self.count, 1)

    def test_profile_and_credentials_modes_symlinks_and_production_fixture_rejection(self):
        for path in (self.registry_dir / "fixture.json", self.creds / "fixture-generation"):
            path.chmod(0o644)
            with self.assertRaises(ValueError):self.dispatch()
            path.chmod(0o600)
            original = path.with_suffix(".original")
            path.rename(original);path.symlink_to(original)
            with self.assertRaises(OSError):self.dispatch()
            path.unlink();original.rename(path)
        registry = P.Registry(self.registry_dir, trusted_uid=os.getuid())
        try:
            with self.assertRaises(ValueError):registry.load("fixture")
            for bad in ("../fixture", "fixture.json", "fixture\n", "/fixture"):
                with self.assertRaises(ValueError):registry.load(bad)
        finally:registry.close()
        self.assertEqual(self.count, 0)

    def test_unknown_http_errors_and_redirect_do_not_resend(self):
        self.status = 302
        self.unknown_held()

    def test_http_server_failure_holds_full_amount(self):
        self.status = 500
        self.unknown_held()

    def test_mismatched_actual_model_is_unknown(self):
        self.response["model"] = "another-model"
        self.unknown_held()

    def test_unreported_or_extra_usage_is_unknown(self):
        self.response["usage"]["server_tool_use"] = {"web_search_requests": 1}
        self.unknown_held()

    def test_standard_native_optional_usage_fields_are_accepted(self):
        self.response["usage"].update(service_tier="standard", speed="standard", inference_geo="not-specified",
                                     server_tool_use={"web_fetch_requests": 0, "web_search_requests": 0},
                                     output_tokens_details={"thinking_tokens": 1})
        self.assertTrue(self.dispatch()["response_complete"])
        self.assertEqual(json.loads(self.requests[0])["service_tier"], "standard_only")

    def test_unquoted_service_tier_is_unknown(self):
        self.response["usage"]["service_tier"] = "priority"
        self.unknown_held()

    def test_json_list_is_unknown_and_holds_full_reservation(self):
        self.raw_override = b'[]'
        self.unknown_held()

    def test_missing_usage_is_unknown(self):
        del self.response["usage"]
        self.unknown_held()

    def test_cache_sum_counts_toward_full_input_cap(self):
        self.response["usage"]["cache_read_input_tokens"] = 100
        self.unknown_held()

    def test_bad_cache_breakdown_is_unknown(self):
        self.response["usage"]["cache_creation"]["ephemeral_1h_input_tokens"] = 2
        self.unknown_held()

    def test_duplicate_json_is_unknown(self):
        raw = json.dumps(self.response).encode()
        self.raw_override = raw[:-1] + b',"model":"fixture-response-v1"}'
        self.unknown_held()

    def test_nonfinite_json_is_unknown(self):
        self.raw_override = json.dumps(self.response).replace('"output_tokens": 2', '"output_tokens": NaN').encode()
        self.unknown_held()

    def test_boolean_usage_is_unknown(self):
        self.response["usage"]["input_tokens"] = True
        self.unknown_held()

    def test_invalid_utf8_is_unknown_with_original_bytes(self):
        self.raw_override = b'\xff'
        result = self.unknown_held()
        self.assertTrue((Path(result["evidence"]) / "transport/output.bin").read_bytes().endswith(b'\xff'))

    def test_short_content_length_cannot_pass_from_valid_json_prefix(self):
        self.extra_length = 20
        result = self.unknown_held()
        receipt = SP.read_receipt(Path(result["evidence"]) / "transport")
        self.assertEqual(receipt["process_returncode"], 70)
        self.assertTrue(receipt["cleanup"]["complete"])
        self.assertTrue((Path(result["evidence"]) / "transport/output.bin").read_bytes().endswith(json.dumps(self.response, ensure_ascii=False).encode()))

    def test_chunked_response_is_complete(self):
        self.chunked = True
        self.assertTrue(self.dispatch()["response_complete"])
        self.assertEqual(self.count, 1)

    def test_output_cap_is_unknown_and_full_received_bytes_are_preserved(self):
        self.profile["max_response_bytes"] = 10
        self.write_profile()
        # New registration requires a fresh ledger root for this new trusted profile.
        self.base["root_family"] += "-resource"
        self.profile["contract_sha256"] = L.digest(self.base);self.write_profile()
        self.key = self.adapter.register("fixture", self.base)
        result = self.unknown_held()
        self.assertTrue((Path(result["evidence"]) / "transport/output.bin").read_bytes().endswith(json.dumps(self.response, ensure_ascii=False).encode()))

    def test_max_tokens_and_tool_content_are_not_task_success_or_executed(self):
        self.response["stop_reason"] = "max_tokens"
        first = self.dispatch()
        self.assertEqual(first["state"], "settled")
        self.assertFalse(first["response_complete"])
        self.response["stop_reason"] = "tool_use"
        self.response["content"] = [{"type": "tool_use", "name": "arbitrary-command", "input": {"command": "false"}}]
        second = self.dispatch("two")
        self.assertEqual(second["state"], "settled")
        self.assertFalse(second["response_complete"])
        self.assertEqual(self.count, 2)

    def run_waiting(self, action=None, timeout_ms=None):
        if timeout_ms is not None:
            self.base["root_family"] += "-timeout"
            self.profile["contract_sha256"] = L.digest(self.base)
            self.profile["call_timeout_ms"] = timeout_ms;self.write_profile()
            self.key = self.adapter.register("fixture", self.base)
        self.wait = True
        outcome, errors = [], []
        cancel = threading.Event()
        def work():
            try:outcome.append(self.dispatch(cancel_event=cancel))
            except BaseException as error:errors.append(error)
        thread = threading.Thread(target=work);thread.start()
        try:
            self.assertTrue(self.seen.wait(4), "transport did not reach the fixture")
            if action:action(cancel)
            thread.join(6)
            self.assertFalse(thread.is_alive(), "adapter ignored supervision")
            self.assertEqual(errors, [])
            self.assertEqual(outcome[0]["state"], "unknown")
            receipt = SP.read_receipt(Path(outcome[0]["evidence"]) / "transport")
            self.assertTrue(receipt["cleanup"]["complete"])
            self.assertFalse(receipt["cleanup"]["remaining_group"])
            self.assertTrue(self.ledger.inspect(self.key)["blocked"])
            self.assertEqual(self.ledger.inspect(self.key)["totals"]["cost_micro_cny"], 1400)
            return receipt
        finally:
            self.release.set();thread.join(6)

    def test_real_request_cancellation_retains_remote_unknown_and_reaps_child(self):
        receipt = self.run_waiting(lambda cancel: cancel.set())
        self.assertEqual(receipt["returncode"], 130)
        self.assertEqual(receipt["reason"], "cancelled")
        self.assertEqual(self.count, 1)

    def test_real_timeout_not_a_mock_clock_and_reaps_child(self):
        started = time.monotonic()
        receipt = self.run_waiting(timeout_ms=1500)
        self.assertEqual(receipt["returncode"], 124)
        self.assertEqual(receipt["reason"], "timeout")
        self.assertGreaterEqual(time.monotonic() - started, 1.4)
        self.assertEqual(self.count, 1)

    def test_profile_revocation_during_request_cancels_unknown(self):
        def revoke(_):
            self.profile["approved"] = False;self.write_profile()
        receipt = self.run_waiting(revoke)
        self.assertEqual(receipt["returncode"], 130)

    def test_credential_generation_rotation_cancels_unknown(self):
        def rotate(_):
            (self.creds / "fixture-generation").write_text("synthetic_rotated")
        receipt = self.run_waiting(rotate)
        self.assertEqual(receipt["returncode"], 130)

    def test_concurrent_callers_commit_one_actual_dispatch(self):
        self.wait = True
        results, errors = [], []
        def call():
            try:results.append(self.dispatch())
            except BaseException as error:errors.append(error)
        first = threading.Thread(target=call);first.start()
        try:
            self.assertTrue(self.seen.wait(4))
            second = threading.Thread(target=call);second.start();second.join(3)
            self.assertFalse(second.is_alive())
            self.assertEqual(self.count, 1)
            self.release.set();first.join(6)
            self.assertFalse(first.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(sorted(r["state"] for r in results), ["intent", "settled"])
            self.assertEqual(sum(r["new_dispatch"] for r in results), 1)
            self.assertEqual(self.ledger.inspect(self.key)["totals"]["calls"], 1)
        finally:self.release.set();first.join(6)

    def test_reconcile_uses_originals_without_live_key_or_second_http(self):
        result = self.dispatch()
        self.registry.close()
        # Replace registered cleanup to avoid double close; a new instance would
        # also have another generation and may reconcile but never dispatch.
        self.registry.close = lambda: None
        new = P.Adapter(L.Ledger(self.store), self.registry, self.root / "evidence")
        self.assertTrue(new.reconcile(self.key, "one")["response_complete"])
        self.assertEqual(self.count, 1)
        path = Path(result["evidence"]) / "request.bin"
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(L.Conflict):new.reconcile(self.key, "one")

    def test_late_original_reconciliation_does_not_unblock_or_resend(self):
        original = self.ledger.settle
        def interrupted(*args, **kwargs):
            raise RuntimeError("synthetic failure before settlement commit")
        self.ledger.settle = interrupted
        try:
            first = self.dispatch()
            self.assertEqual(first["state"], "unknown")
        finally:self.ledger.settle = original
        self.assertTrue(self.ledger.inspect(self.key)["blocked"])
        self.assertTrue(self.adapter.reconcile(self.key, "one")["response_complete"])
        self.assertTrue(self.ledger.inspect(self.key)["blocked"])
        self.assertEqual(self.count, 1)
        with self.assertRaises(L.Conflict):self.dispatch("again", "retry")

    def test_registry_directory_replacement_denies_old_descriptor(self):
        moved = self.root / "old-registry"
        self.registry_dir.rename(moved)
        self.registry_dir.mkdir(mode=0o700)
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(self.count, 0)

    def test_profile_revoke_and_restore_still_invalidates_running_identity(self):
        def restore(_):
            raw = (self.registry_dir / "fixture.json").read_bytes()
            self.profile["approved"] = False;self.write_profile()
            (self.registry_dir / "fixture.json").write_bytes(raw)
        receipt = self.run_waiting(restore)
        self.assertEqual(receipt["returncode"], 130)

    def test_source_change_cancels_transport_without_modifying_repository(self):
        original = P.SOURCES["adapter"]
        external = self.root / "adapter-source-copy.py"
        external.write_bytes(original.read_bytes())
        P.SOURCES["adapter"] = external
        try:
            def change(_):external.write_bytes(external.read_bytes() + b"\n# fixture source changed\n")
            receipt = self.run_waiting(change)
            self.assertEqual(receipt["returncode"], 130)
        finally:P.SOURCES["adapter"] = original

    def test_unsafe_sqlite_durability_denies_before_actual_send(self):
        self.store.db.execute("PRAGMA synchronous=OFF")
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(self.count, 0)
        self.assertEqual(self.ledger.snapshot(self.key, "one")["attempt"]["state"], "reserved")
        self.assertEqual(self.ledger.cancel(self.key, "one"), "cancelled")

    def test_cancel_before_intent_never_sends_or_reserves_money(self):
        cancel = threading.Event();cancel.set()
        result = self.dispatch(cancel_event=cancel)
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["new_dispatch"])
        self.assertEqual(self.count, 0)
        self.assertEqual(self.ledger.inspect(self.key)["totals"], {"calls": 1, "billed_tokens": 0, "cost_micro_cny": 0})

    def test_corrupt_original_output_replay_never_reports_complete_or_resends(self):
        result = self.dispatch()
        path = Path(result["evidence"]) / "transport/output.bin"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaises(ValueError):self.dispatch()
        with self.assertRaises(ValueError):self.adapter.reconcile(self.key, "one")
        self.assertEqual(self.count, 1)
        self.assertEqual(self.ledger.inspect(self.key)["totals"]["cost_micro_cny"], 130)

    def test_original_root_deadline_cannot_be_refreshed(self):
        self.ledger.wall = lambda: self.base["limits"]["deadline_us"]
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(self.count, 0)
        self.assertEqual(self.ledger.inspect(self.key)["totals"]["calls"], 0)

    def test_existing_intent_missing_originals_is_never_backfilled(self):
        c = self.ledger.snapshot(self.key)["contract"]
        body = L.encoded({"model": self.profile["model"]["requested_model"], "system": self.system, "messages": self.messages,
                          "max_tokens": 20, "stream": False, "service_tier": "standard_only"}).encode()
        material = L.digest([c["provider_binding"]["profile_sha256"], hashlib.sha256(body).hexdigest()])
        self.ledger.reserve(self.key, "one", "propose", 100, 20, material_sha256=material)
        self.ledger.intent(self.key, "one")
        self.assertEqual(self.dispatch()["state"], "intent")
        with self.assertRaises(FileNotFoundError):self.adapter.reconcile(self.key, "one")
        self.assertFalse(self.adapter._folder(self.key, "one").exists())
        self.assertEqual(self.count, 0)
