"""Startup dependency order only; no installer, sudo, official CLI or model."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tmh.platform import codex_registration as registration, learning_runs
from tmh.platform.agents import Runner
from tmh.platform.server import Platform


class CodexStartupTests(unittest.TestCase):
    def startup(self, carrier=None, error=None):
        observed = []

        class ObservedRecovery(Exception):
            pass

        def recover(platform):
            observed.append(platform)
            raise ObservedRecovery()

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(registration, "load_codex_carrier", return_value=carrier, side_effect=error) as load, \
                    mock.patch.object(Runner, "recover"), \
                    mock.patch.object(learning_runs, "recover", side_effect=recover):
                with self.assertRaises(ObservedRecovery):
                    Platform(Path(directory))
                load.assert_called_once_with(Path(directory).resolve())
            self.assertEqual(len(observed), 1)
            observed[0].store.db.close()
            return observed[0]

    def test_trusted_dependency_attached_before_learning_recovery(self):
        carrier = object()
        platform = self.startup(carrier)
        self.assertIs(platform.independent_codex_carrier, carrier)
        self.assertEqual(platform.independent_codex_registration, "configured")

    def test_absence_and_rejection_do_not_attach_a_fallback(self):
        platform = self.startup()
        self.assertIsNone(platform.independent_codex_carrier)
        self.assertEqual(platform.independent_codex_registration, "absent")
        for error in (OSError("SYNTHETIC_PRIVATE_TEXT"), ValueError("SYNTHETIC_PRIVATE_TEXT")):
            with self.subTest(type=type(error).__name__):
                platform = self.startup(error=error)
                self.assertIsNone(platform.independent_codex_carrier)
                self.assertEqual(platform.independent_codex_registration, "rejected")
                self.assertNotIn("SYNTHETIC_PRIVATE_TEXT", repr(vars(platform)))

    def test_registration_does_not_open_real_capability_gate(self):
        platform = self.startup(object())
        self.assertEqual(platform.independent_codex_registration, "configured")
        with self.assertRaisesRegex(ValueError, "Codex"):
            learning_runs._capabilities("/synthetic/not-executed", None, "codex")


if __name__ == "__main__":
    unittest.main()
