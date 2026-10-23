"""Personal credential storage/import: private, endpoint-bound, no disclosure."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tmh import workbench_credentials as credentials
from tmh.workbench import main
from tmh.workbench_client import Client, ClientError


@unittest.skipUnless(os.name == "posix", "owner-only credential files require POSIX permission checks")
class WorkbenchCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-tool-credential-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.path = self.directory / "member.json"
        self.value = dict(schema=1, endpoint="https://webuddy.example/t/default", token="wbt_fixture.secret")
        self.env = patch.dict(os.environ, {"WEBUDDY_CREDENTIAL_FILE": "", "WEBUDDY_URL": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def status(self, **overrides):
        info = dict(id="fixture", user="member", tenant="default", scope="content", project_ids=[7],
                    expires_at="2026-12-01T00:00:00Z", execution=False, status="active")
        info.update(overrides)
        return dict(tool_connection=info, allowed_operations=["status", "ticket_get", "ticket_create", "message_send", "request_get"])

    def invoke(self, *args, input=""):
        out, err = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(input)), redirect_stdout(out), redirect_stderr(err):
            result = main(list(args))
        return result, out.getvalue(), err.getvalue()

    def test_round_trip_is_0600_and_never_overwrites_existing_file(self):
        self.assertEqual(credentials.save(self.path, self.value), str(self.path))
        self.assertEqual(credentials.load(self.path), self.value)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        before = self.path.read_bytes()
        with self.assertRaises(credentials.CredentialError) as caught:
            credentials.save(self.path, dict(self.value, token="wbt_new.other"))
        self.assertEqual(caught.exception.code, "credential_exists")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_concurrent_publication_has_one_complete_winner_and_no_temporary_files(self):
        def publish(index):
            try:
                credentials.save(self.path, dict(self.value, token="wbt_fixture.secret%d" % index))
                return index
            except credentials.CredentialError as exc:
                self.assertEqual(exc.code, "credential_exists")
                return None
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(publish, range(8)))
        winners = [x for x in results if x is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(credentials.load(self.path)["token"], "wbt_fixture.secret%d" % winners[0])
        self.assertEqual([x.name for x in self.directory.iterdir()], [self.path.name])

    def test_symlink_file_parent_hardlink_and_fifo_are_rejected(self):
        credentials.save(self.path, self.value)
        linked = self.directory / "link.json"
        linked.symlink_to(self.path)
        with self.assertRaises(credentials.CredentialError):
            credentials.load(linked)
        alias = self.directory / "alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(credentials.CredentialError):
            credentials.load(alias / self.path.name)
        hard = self.directory / "hard.json"
        os.link(self.path, hard)
        with self.assertRaises(credentials.CredentialError):
            credentials.load(self.path)
        fifo = self.directory / "fifo"
        os.mkfifo(fifo, mode=0o600)
        with self.assertRaises(credentials.CredentialError):
            credentials.load(fifo)

    def test_public_permissions_or_unowned_file_or_writable_parent_are_rejected(self):
        credentials.save(self.path, self.value)
        for mode in (0o644, 0o640, 0o666, 0o400):
            self.path.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(credentials.CredentialError):
                credentials.load(self.path)
        self.path.chmod(0o600)
        actual_fstat = os.fstat
        def unowned(fd):
            value = actual_fstat(fd)
            if stat.S_ISREG(value.st_mode):
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=value.st_mode, st_uid=os.getuid()+1, st_nlink=1)
            return value
        with patch.object(credentials.os, "fstat", side_effect=unowned), self.assertRaises(credentials.CredentialError):
            credentials.load(self.path)
        self.directory.chmod(0o770)
        try:
            with self.assertRaises(credentials.CredentialError):
                credentials.load(self.path)
            with self.assertRaises(credentials.CredentialError):
                credentials.save(self.directory / "unsafe.json", self.value)
        finally:
            self.directory.chmod(0o700)

    def test_serialization_failure_keeps_no_target(self):
        with patch.object(credentials.os, "fsync", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(credentials.CredentialError):
                credentials.save(self.path, self.value)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_credential_binding_rejects_other_endpoint_and_environment_conflicts(self):
        credentials.save(self.path, self.value)
        client = Client(credential_file=str(self.path))
        self.assertEqual(client.endpoint, self.value["endpoint"])
        with patch.dict(os.environ, {"WEBUDDY_CREDENTIAL_FILE": str(self.path)}):
            self.assertEqual(Client().tool_token, self.value["token"])
        for target in ("https://other.example/t/default", "https://webuddy.example/t/other", "https://webuddy.example"):
            with self.subTest(target=target), self.assertRaises(ClientError) as caught:
                Client(target, credential_file=str(self.path))
            self.assertEqual(caught.exception.code, "credential_endpoint_mismatch")
        with patch.dict(os.environ, {"WEBUDDY_URL": "https://other.example/t/default"}), self.assertRaises(ClientError):
            Client(credential_file=str(self.path))

    def test_tenant_endpoint_does_not_open_general_paths_or_allow_credential_in_url(self):
        for path in ("/t/default/api", "/t/default/../other", "/t/%64efault", "/t/default?x=1", "/t/default#x", "/t/Default", "/t/default\\x"):
            with self.subTest(path=path), self.assertRaises(ClientError):
                Client("https://example.test" + path, tool_token=self.value["token"])
        for endpoint in ("https://example.test", "https://user:pw@example.test/t/default", "http://example.test/t/default"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ClientError):
                Client(endpoint, tool_token=self.value["token"])

    def test_connect_verifies_before_saving_and_prints_only_scope_and_path(self):
        calls = []
        def call(client, operation, args=None):
            calls.append((client.endpoint, client.tool_token, operation))
            self.assertFalse(self.path.exists())
            return self.status()
        with patch.object(Client, "call", call):
            result, out, err = self.invoke("connect", "--stdin", "--save-to", str(self.path),
                                           input=json.dumps(dict(self.value, imported_metadata="untrusted-secret-text")))
        self.assertEqual(result, 0, err)
        self.assertEqual(calls, [(self.value["endpoint"], self.value["token"], "status")])
        self.assertEqual(credentials.load(self.path), self.value)
        self.assertEqual(json.loads(out)["tool_connection"]["user"], "member")
        for secret in (self.value["token"], "untrusted-secret-text"):
            self.assertNotIn(secret, out + err)

    def test_connect_token_stdin_and_existing_environment_do_not_forward_legacy_credentials(self):
        with patch.dict(os.environ, {"WEBUDDY_CREDENTIAL_FILE": "nonexistent-old-file"}), patch.object(Client, "call", return_value=self.status()):
            result, out, err = self.invoke("connect", "--stdin", "--endpoint", self.value["endpoint"],
                                           "--save-to", str(self.path), input=self.value["token"] + "\n")
        self.assertEqual(result, 0, err)
        self.assertNotIn(self.value["token"], out + err)

    def test_connect_invalid_live_identity_revocation_and_incomplete_scope_never_save(self):
        cases = [self.status(tenant="other"), self.status(execution=True), self.status(status="revoked"),
                 self.status(scope="read"), {}, self.status(project_ids="*")]
        for value in cases:
            with self.subTest(value=value), patch.object(Client, "call", return_value=value):
                result, out, err = self.invoke("connect", "--stdin", "--save-to", str(self.path), input=json.dumps(self.value))
            self.assertEqual(result, 1)
            self.assertEqual(out, "")
            self.assertFalse(self.path.exists())
            self.assertNotIn(self.value["token"], err)
        with patch.object(Client, "call", side_effect=ClientError("revoked", "tool_revoked", 401)):
            result, out, err = self.invoke("connect", "--stdin", "--save-to", str(self.path), input=json.dumps(self.value))
        self.assertEqual(result, 1)
        self.assertFalse(self.path.exists())

    def test_connect_requires_explicit_input_and_refuses_endpoint_mismatch(self):
        with patch.object(Client, "call") as call:
            result, out, err = self.invoke("connect", "--save-to", str(self.path))
            self.assertEqual(json.loads(err)["code"], "credential_input_required")
            result, out, err = self.invoke("connect", "--stdin", "--save-to", str(self.path),
                                           "--endpoint", "https://other.example/t/default", input=json.dumps(self.value))
            self.assertEqual(json.loads(err)["code"], "credential_endpoint_mismatch")
            call.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_interactive_import_never_falls_back_to_echoing_the_secret(self):
        import getpass
        import warnings
        source = io.StringIO()
        source.isatty = lambda: True
        out, err = io.StringIO(), io.StringIO()
        def insecure_input(*args):
            warnings.warn("echo cannot be disabled", getpass.GetPassWarning)
            self.fail("must stop before visible input fallback")
        with patch("sys.stdin", source), patch("tmh.workbench.getpass.getpass", side_effect=insecure_input), redirect_stdout(out), redirect_stderr(err):
            result = main(["connect", "--endpoint", self.value["endpoint"], "--save-to", str(self.path)])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(err.getvalue())["code"], "credential_input_required")
        self.assertEqual(out.getvalue(), "")
        self.assertFalse(self.path.exists())

    def test_config_only_references_credential_file_and_cannot_enable_execution(self):
        credentials.save(self.path, self.value)
        for name in ("claude", "cursor", "codex"):
            result, out, err = self.invoke("config", name, "--credential-file", str(self.path))
            self.assertEqual(result, 0, err)
            self.assertIn("--credential-file", out)
            self.assertIn(str(self.path), out)
            self.assertNotIn(self.value["token"], out + err)
            self.assertNotIn("WEBUDDY_TOKEN", out)
        for command in (("config", "claude"), ("mcp",)):
            result, out, err = self.invoke(*command, "--credential-file", str(self.path), "--allow-execution")
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(err)["code"], "tool_operation_forbidden")
            self.assertEqual(out, "")


class UnsupportedCredentialPlatformTest(unittest.TestCase):
    def test_platform_without_posix_acl_proof_fails_closed(self):
        with patch.object(credentials.os, "name", "nt"), self.assertRaises(credentials.CredentialError) as caught:
            credentials.load("member.json")
        self.assertEqual(caught.exception.code, "credential_platform_unsupported")
