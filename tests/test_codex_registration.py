"""Focused loader checks; local owner stands in for root only in these fixtures.

No sudo, launcher, SP, socket, server, model or real credential is used.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tmh.platform import codex_registration as R
from tmh.platform import codex_host_completion as C
from tmh.platform.codex_frozen_config import FrozenConfig
from tmh.platform.codex_host import RootCarrier


class RegistrationLoaderTests(unittest.TestCase):
    def setUp(self):
        self.assertNotEqual(os.geteuid(), 0, "run owner-simulation fixtures as a normal local user")
        temporary = tempfile.TemporaryDirectory(prefix="tmh-registration-loader-", dir=Path.home())
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.home.chmod(0o700)
        self.bundle = self.home / "installed"
        self.bundle.mkdir(mode=0o700)
        self.entry = self.bundle / "source/root_entry"
        self.entry.parent.mkdir(mode=0o700)
        self.entry.write_bytes(b"PUBLIC_SYNTHETIC_ENTRY_NEVER_EXECUTED\n")
        self.entry.chmod(0o700)
        self.completed = self.bundle / "completions"
        self.completed.mkdir(mode=0o750)
        self.completed.chmod(0o750)
        self.source = self.home / "configuration"
        self.source.mkdir(mode=0o700)
        base = (b'model="synthetic"\nmodel_provider="fixture"\n[model_providers.fixture]\n'
                b'name="fixture"\nbase_url="https://provider.example/v1"\nwire_api="responses"\n'
                b'experimental_bearer_token="PUBLIC_SYNTHETIC_CREDENTIAL"\n')
        for name, raw in (("config.toml", base), ("team.config.toml", b'approval_policy="never"\n')):
            path = self.source / name
            path.write_bytes(raw)
            path.chmod(0o600)
        self.data = self.home / "registered-data"
        self.data.mkdir(mode=0o700)
        frozen = FrozenConfig(self.source, "team", "synthetic", {})
        info = self.entry.stat()
        execution = dict(bin=str(self.entry), args=[], engine="codex", profile="team",
                         prompt_transport="stdin", resume=False, retry_busy=False, timeout=30,
                         sha256=C.digest(self.entry.read_bytes()), size=info.st_size, mtime_ns=info.st_mtime_ns)
        self.value = dict(schema=R.SCHEMA, registration_id="a" * 64,
            service_uid=os.geteuid(), service_gid=os.getegid(), data_root=str(self.data),
            source_home=str(self.source), source_owner_uid=os.geteuid(), profile="team", model="synthetic",
            configuration=frozen.binding(), execution=execution, controller_entry=str(self.entry),
            controller_sha256=C.digest(self.entry.read_bytes()), bundle_manifest_sha256="b" * 64,
            official_runtime_manifest_sha256="c" * 64, completion_root=str(self.completed), timeout_max_seconds=30)
        self.descriptor = self.bundle / "public-descriptor.json"
        patch = mock.patch.multiple(R, BUNDLE=self.bundle, DESCRIPTOR=self.descriptor,
                                    ENTRY=self.entry, COMPLETIONS=self.completed)
        patch.start()
        self.addCleanup(patch.stop)
        owner = mock.patch.object(C, "ROOT_UID", os.geteuid())
        owner.start()
        self.addCleanup(owner.stop)
        self.write()

    def write(self, value=None, raw=None):
        self.descriptor.write_bytes(raw if raw is not None else C.encoded(self.value if value is None else value))
        self.descriptor.chmod(0o640)

    def load(self, path=None):
        return R.load_codex_carrier(self.data if path is None else path, environment={})

    def test_absence_and_foreign_data_are_unconfigured_before_service_or_source_access(self):
        self.descriptor.unlink()
        self.assertIsNone(self.load())
        self.write()
        with mock.patch.object(R, "FrozenConfig") as source, mock.patch.object(R, "RootCarrier") as carrier:
            with mock.patch.object(R.os, "geteuid", return_value=0), mock.patch.object(R.os, "getegid", return_value=0):
                self.assertIsNone(self.load(self.home / "temporary-copy"))
            source.assert_not_called()
            carrier.assert_not_called()
        with mock.patch.object(R, "BUNDLE", self.home / "absent-installation"):
            self.assertIsNone(self.load())

    def test_registered_data_gets_fixed_carrier_and_public_descriptor_has_no_credential(self):
        carrier = self.load()
        self.assertIs(type(carrier), RootCarrier)
        self.assertEqual(carrier.registration, self.value["registration_id"])
        self.assertEqual(carrier.execution, self.value["execution"])
        self.assertEqual(carrier.frozen.binding(), self.value["configuration"])
        self.assertEqual(carrier.entry, self.entry)
        self.assertEqual(carrier.completion_root, self.completed)
        self.assertEqual(len(self.value), 17)
        self.assertNotIn("credential_sha256", self.value)
        self.assertNotIn(b"PUBLIC_SYNTHETIC_CREDENTIAL", self.descriptor.read_bytes())

    def test_exact_fields_types_profile_paths_and_original_source_reject_changes(self):
        changes = ({"profile": "other"}, {"model": "other"}, {"service_uid": True},
                   {"source_owner_uid": 0}, {"service_gid": os.getegid() + 1},
                   {"controller_entry": "/other/entry"}, {"completion_root": "/other/completions"},
                   {"timeout_max_seconds": float("inf")}, {"registration_id": "bad"},
                   {"credential_sha256": "d" * 64})
        for change in changes:
            with self.subTest(change=next(iter(change))):
                # json.dumps permits Infinity here to exercise strict parsing.
                self.write(raw=json.dumps(dict(self.value, **change)).encode())
                with self.assertRaises((OSError, ValueError)):
                    self.load()
        self.write()
        with mock.patch.object(R.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(OSError, "service identity"):
                self.load()
        source = self.source / "config.toml"
        source.write_bytes(source.read_bytes() + b"\n# changed source\n")
        with self.assertRaisesRegex(OSError, "source configuration changed"):
            self.load()

    def test_duplicate_missing_oversize_and_invalid_foreign_descriptor_are_not_absence(self):
        cases = (b'{"schema":"duplicate",' + C.encoded(self.value)[1:], b"{", b"x" * (R.MAX_DESCRIPTOR_BYTES + 1),
                 C.encoded({k: v for k, v in self.value.items() if k != "execution"}))
        for raw in cases:
            with self.subTest(length=len(raw)):
                self.write(raw=raw)
                for path in (self.data, self.home / "temporary-copy"):
                    with self.assertRaises((OSError, ValueError)):
                        self.load(path)

    def test_links_writable_mode_and_wrong_production_owner_reject(self):
        self.descriptor.chmod(0o660)
        with self.assertRaises(OSError):
            self.load()
        self.write()
        link = self.bundle / "alias"
        os.link(self.descriptor, link)
        with self.assertRaises(OSError):
            self.load()
        link.unlink()
        self.descriptor.rename(link)
        self.descriptor.symlink_to(link)
        with self.assertRaises(OSError):
            self.load()
        self.descriptor.unlink()
        link.rename(self.descriptor)
        with mock.patch.object(C, "ROOT_UID", 0):
            with self.assertRaises(OSError):
                self.load()

    def test_incomplete_installed_entry_or_completion_root_does_not_fallback(self):
        self.entry.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()
        self.entry.write_bytes(b"PUBLIC_SYNTHETIC_ENTRY_NEVER_EXECUTED\n")
        self.entry.chmod(0o700)
        self.completed.chmod(0o770)
        with self.assertRaises(OSError):
            self.load()

    def test_directory_replacement_during_read_is_rejected(self):
        real = C.open_root
        count = 0
        def replacing(path, gid=None):
            nonlocal count
            count += 1
            if count == 2:
                self.bundle.rename(self.home / "previous-installation")
                self.bundle.mkdir(mode=0o700)
                self.write()
            return real(path, gid)
        with mock.patch.object(C, "open_root", side_effect=replacing):
            with self.assertRaisesRegex(OSError, "directory replaced"):
                self.load()


if __name__ == "__main__":
    unittest.main()
