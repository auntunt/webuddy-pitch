"""Task test-environment values: private storage, env injection, redaction; never in DB rows or prompts."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tmh.platform import task_secrets
from tmh.platform.errors import ApiError


class TaskSecretsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-task-secrets-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)

    def test_values_are_private_injected_and_redacted(self):
        names = task_secrets.save(self.data, "TSK-1", [{"name": "db_password", "value": "s3cret-VALUE"},
                                                       {"name": "db_host", "value": "10.0.0.8"}])
        self.assertEqual(names, ["db_host", "db_password"])
        self.assertEqual(task_secrets.names(self.data, "TSK-1"), ["db_host", "db_password"])
        env = task_secrets.environment(self.data, "TSK-1")
        self.assertEqual(env["TMH_ENV_DB_PASSWORD"], "s3cret-VALUE")
        text = "connect to 10.0.0.8 with s3cret-VALUE"
        redacted = task_secrets.redact(text, self.data, "TSK-1")
        self.assertNotIn("s3cret-VALUE", redacted)
        self.assertNotIn("10.0.0.8", redacted)

    def test_values_never_reach_a_database_row(self):
        db = sqlite3.connect(self.data / "platform.db")
        db.execute("CREATE TABLE tickets(id INTEGER, body TEXT)")
        db.execute("INSERT INTO tickets VALUES(1, '完成修改后测试')")
        db.commit()
        task_secrets.save(self.data, "TSK-2", [{"name": "db_password", "value": "hidden-PW-99"}])
        dumped = "\n".join(str(row) for line in db.iterdump() for row in [line])
        self.assertNotIn("hidden-PW-99", dumped)
        private = self.data / "task-secrets"
        for path in self.data.rglob("*"):
            if path.is_file() and private not in path.parents:
                self.assertNotIn("hidden-PW-99", path.read_bytes().decode("utf-8", errors="ignore"), str(path))

    def test_names_are_validated_and_duplicates_refused(self):
        with self.assertRaises(ApiError):
            task_secrets.save(self.data, "TSK-3", [{"name": "bad name", "value": "x"}])
        with self.assertRaises(ApiError):
            task_secrets.save(self.data, "TSK-3", [{"name": "a", "value": "x"}, {"name": "A", "value": "y"}])
        with self.assertRaises(ApiError):
            task_secrets.environment(self.data, "../escape")

    def test_clearing_removes_the_file(self):
        task_secrets.save(self.data, "TSK-4", [{"name": "k", "value": "v"}])
        task_secrets.save(self.data, "TSK-4", [])
        self.assertEqual(task_secrets.names(self.data, "TSK-4"), [])
        self.assertFalse((self.data / "task-secrets" / "TSK-4.json").exists())


if __name__ == "__main__":
    unittest.main()


class TaskSecretsSpawnTest(unittest.TestCase):
    def test_subprocess_env_has_values_and_names_only_elsewhere(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from tmh.platform import task_secrets
        with tempfile.TemporaryDirectory(prefix="tmh-spawn-") as folder:
            data = Path(folder)
            task_secrets.save(data, "TSK-9", [{"name": "db_password", "value": "SPAWN-VALUE-42"}])
            env = dict(__import__("os").environ, **task_secrets.environment(data, "TSK-9"))
            out = subprocess.run([sys.executable, "-c", "import os;print(os.environ['TMH_ENV_DB_PASSWORD'])"],
                                 env=env, capture_output=True, text=True).stdout.strip()
            self.assertEqual(out, "SPAWN-VALUE-42")
            self.assertEqual(task_secrets.names(data, "TSK-9"), ["db_password"])
            self.assertNotIn("SPAWN-VALUE-42", str(task_secrets.names(data, "TSK-9")))
