"""Real process-launch backstop tests; audit hooks never enter unittest's process."""
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


CHILD = textwrap.dedent(r'''
    import json
    import os
    from pathlib import Path
    import shlex
    import subprocess
    import sys
    import tempfile
    import threading
    from tmh.platform.tenancy import Registry
    from tmh.platform.tenant_runtime import ACTOR, TenantContext, install_execution_gate

    case = json.loads(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="tmh-execution-gate-") as temporary:
        root = Path(temporary)
        (root / "users.json").write_text(json.dumps({
            "owner": {"pw": "local-fixture"}, "member": {"pw": "local-fixture"},
            "viewer": {"pw": "local-fixture"}}), encoding="utf-8")
        registry = Registry(root, bootstrap_owner="owner")
        with registry.authorization_guard(), registry.transaction() as db:
            db.execute("UPDATE memberships SET role='viewer' WHERE user='viewer'")
            db.execute("INSERT INTO tenants VALUES('customer','Customer',?,'active','disabled','now')", (str(root / "customer"),))
            db.executemany("INSERT INTO memberships VALUES('customer',?,?)", [("owner", "admin"), ("member", "admin"), ("viewer", "viewer")])
        context = TenantContext(registry, case.get("tenant", "default"))
        install_execution_gate(context)
        actor = case.get("actor", "owner")
        output = {"attempts": {}, "actor": actor, "tenant": context.tenant_id}
        command = [sys.executable, "-c", "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('executed')"]

        def attempt(kind):
            marker = root / (kind + ".executed")
            argv = command + [str(marker)]
            try:
                if kind == "popen":
                    subprocess.run(argv, check=True, timeout=10)
                elif kind == "system":
                    shell = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
                    if os.system(shell) != 0:
                        raise AssertionError("unexpected system failure")
                elif kind == "fork":
                    pid = os.fork()
                    if pid == 0:
                        marker.write_text("executed")
                        os._exit(0)
                    os.waitpid(pid, 0)
                elif kind == "forkpty":
                    pid, descriptor = os.forkpty()
                    if pid == 0:
                        marker.write_text("executed")
                        os._exit(0)
                    os.waitpid(pid, 0)
                    os.close(descriptor)
                elif kind == "spawn":
                    pid = os.posix_spawn(sys.executable, argv, os.environ)
                    os.waitpid(pid, 0)
                elif kind == "exec":
                    os.execv(sys.executable, argv)
                output["attempts"][kind] = {"denied": False, "executed": marker.exists()}
            except PermissionError:
                output["attempts"][kind] = {"denied": True, "executed": marker.exists()}

        mode = case["mode"]
        if mode == "denied":
            with context.acting(actor):
                for kind in ("popen", "system", "exec"):
                    attempt(kind)
                if hasattr(os, "fork"):
                    attempt("fork")
                if hasattr(os, "forkpty"):
                    attempt("forkpty")
                if hasattr(os, "posix_spawn"):
                    attempt("spawn")
        elif mode == "allowed":
            with context.acting(actor):
                attempt("popen")
        elif mode in ("thread", "revoked_thread"):
            started, release = threading.Event(), threading.Event()
            errors = []
            def run():
                try:
                    started.set()
                    if not release.wait(10):
                        raise AssertionError("thread barrier was not released")
                    output["thread_actor"] = ACTOR.get()
                    attempt("popen")
                except BaseException as exc:
                    errors.append(repr(exc))
            with context.acting(actor):
                thread = threading.Thread(target=run)
                thread.start()
            if not started.wait(10):
                raise AssertionError("thread did not start")
            output["parent_actor_after_exit"] = ACTOR.get()
            if mode == "revoked_thread":
                # A committed control-plane change precedes the actual launch.
                # Registry administration's own invariants have separate tests.
                with registry.authorization_guard(), registry.transaction() as db:
                    db.execute("UPDATE accounts SET active=0 WHERE name=?", (actor,))
            release.set()
            thread.join(10)
            if thread.is_alive() or errors:
                raise AssertionError(str(errors) or "thread did not finish")
        elif mode == "no_actor":
            attempt("popen")
        else:
            raise AssertionError("unknown mode")
        registry.close()
        print(json.dumps(output))
''')


class TenantExecutionTest(unittest.TestCase):
    def child(self, mode, actor="owner", tenant="default"):
        result = subprocess.run([sys.executable, "-c", CHILD, json.dumps({"mode": mode, "actor": actor, "tenant": tenant})],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def assert_denied(self, result):
        self.assertTrue(result["attempts"])
        for kind, attempt in result["attempts"].items():
            with self.subTest(kind=kind):
                self.assertTrue(attempt["denied"])
                self.assertFalse(attempt["executed"])

    def test_nonowners_and_new_tenants_cannot_launch_any_process_api(self):
        for actor, tenant in (("member", "default"), ("viewer", "default"), ("owner", "customer"), ("member", "customer")):
            with self.subTest(actor=actor, tenant=tenant):
                self.assert_denied(self.child("denied", actor, tenant))

    def test_default_platform_owner_can_explicitly_launch(self):
        result = self.child("allowed")
        self.assertEqual(result["attempts"], {"popen": {"denied": False, "executed": True}})

    def test_no_request_identity_does_not_inherit_owner_authority(self):
        self.assert_denied(self.child("no_actor"))

    def test_threads_inherit_the_launching_identity_after_parent_context_exits(self):
        for actor in ("owner", "member"):
            with self.subTest(actor=actor):
                result = self.child("thread", actor)
                self.assertEqual(result["thread_actor"], actor)
                self.assertEqual(result["parent_actor_after_exit"], "")
                self.assertEqual(result["attempts"]["popen"], {"denied": actor != "owner", "executed": actor == "owner"})

    def test_captured_owner_identity_is_rechecked_after_revocation(self):
        result = self.child("revoked_thread")
        self.assertEqual(result["thread_actor"], "owner")
        self.assert_denied(result)


if __name__ == "__main__":
    unittest.main()
