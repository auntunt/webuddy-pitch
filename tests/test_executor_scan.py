"""Executor scan reads local Codex config without returning secret values."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import executor_setup

CONFIG = '''model = "gpt-6-astra"
model_provider = "aiseat"

[model_providers.aiseat]
name = "aiseat"
base_url = "https://gateway.example/v1"
wire_api = "responses"
experimental_bearer_token = "SECRET-TOKEN-VALUE"
'''


class ExecutorScanTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-scan-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name) / "codex"
        self.home.mkdir()

    def test_model_is_the_top_level_model_not_the_provider_name(self):
        (self.home / "config.toml").write_text(CONFIG, encoding="utf-8")
        info = executor_setup._codex_home(self.home)
        self.assertEqual(info["model"], "gpt-6-astra")
        self.assertEqual(info["model_provider"], "aiseat")

    def test_bearer_token_in_the_selected_provider_counts_as_present_without_returning_it(self):
        (self.home / "config.toml").write_text(CONFIG, encoding="utf-8")
        info = executor_setup._codex_home(self.home)
        self.assertTrue(info["auth_present"])
        self.assertNotIn("SECRET-TOKEN-VALUE", str(info))

    def test_env_key_set_counts_as_present(self):
        (self.home / "config.toml").write_text(CONFIG.replace('experimental_bearer_token = "SECRET-TOKEN-VALUE"', 'env_key = "AISEAT_KEY"'), encoding="utf-8")
        with patch.dict(os.environ, {"AISEAT_KEY": "x"}):
            self.assertTrue(executor_setup._codex_home(self.home)["auth_present"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(executor_setup._codex_home(self.home)["auth_present"])

    def test_no_provider_credentials_and_no_auth_file_is_not_present(self):
        (self.home / "config.toml").write_text('model = "m"\n', encoding="utf-8")
        self.assertFalse(executor_setup._codex_home(self.home)["auth_present"])

    def test_bundled_codex_directory_on_path_is_found(self):
        bundled = Path(tempfile.mkdtemp(prefix="tmh-bundled-")) / "codex-path"
        bundled.mkdir(parents=True)
        exe = bundled / ("codex.exe" if os.name == "nt" else "codex")
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
        with patch.dict(os.environ, {"PATH": str(bundled)}):
            self.assertIn(str(exe), executor_setup._codex_candidates())


if __name__ == "__main__":
    unittest.main()
