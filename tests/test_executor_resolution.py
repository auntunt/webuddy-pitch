"""Every engine resolves to the same launchable path the run uses, including Windows .CMD shims via PATHEXT."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import agents


class ExecutorResolutionTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-resolve-")
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name) / "npm-global"
        self.dir.mkdir()

    def test_claude_resolves_to_its_cmd_shim_through_pathext(self):
        shim = self.dir / "claude.CMD"
        shim.write_text("@echo off\n", encoding="utf-8")
        with patch.object(agents.shutil, "which", side_effect=lambda name, path=None: str(shim) if name == "claude" else None):
            self.assertEqual(agents.executable("claude", {"bin": "claude"}), str(shim))
        with patch.dict(os.environ, {"PATH": str(self.dir), "PATHEXT": ".COM;.EXE;.BAT;.CMD"}):
            self.assertIn(agents.shutil.which("claude"), (None, str(shim)))

    def test_codex_bundled_path_still_wins_when_exported(self):
        exe = self.dir / "codex.exe"
        exe.write_text("bin", encoding="utf-8")
        with patch.dict(os.environ, {"WEBUDDY_CODEX_BIN": str(exe)}):
            self.assertEqual(agents.executable("codex", {"bin": "codex"}), str(exe))

    def test_unknown_executable_keeps_its_name_so_the_failure_is_visible(self):
        with patch.dict(os.environ, {"PATH": str(self.dir), "PATHEXT": ".EXE"}):
            self.assertEqual(agents.executable("claude", {"bin": "claude"}), "claude")


if __name__ == "__main__":
    unittest.main()
