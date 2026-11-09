"""A transient Cursor reconnect line on stderr is not a failure: the probe passes on marker + exit 0."""
import unittest
from unittest.mock import patch

from tmh.platform import executor_setup

RECONNECT = ("Connection lost, reconnecting to https://agentn.global.api5.cursor.sh (attempt 1)...\n"
             "Retry attempt 1...\n")


class _Result:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class CursorReconnectTest(unittest.TestCase):
    def test_reconnect_text_matches_no_failure_pattern(self):
        self.assertEqual(executor_setup.cursor_failure(RECONNECT), ())

    def test_probe_passes_when_marker_is_present_despite_reconnect_on_stderr(self):
        with patch.object(executor_setup.subprocess, "run",
                          return_value=_Result(0, executor_setup.MARKER + "\n", RECONNECT)):
            result = executor_setup.probe("cursor", "agent", {})
        self.assertTrue(result["ok"], result)
        self.assertNotIn("reason", result)

    def test_probe_still_fails_without_the_marker(self):
        with patch.object(executor_setup.subprocess, "run", return_value=_Result(0, "", RECONNECT)):
            result = executor_setup.probe("cursor", "agent", {})
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
