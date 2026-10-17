"""Evidence signatures: one SSHSIG format whether the cryptography package or ssh-keygen made it, checkable by either."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tmh import evidence as ev
from tmh import sign

HAVE_LIB = sign._lib()
HAVE_SSH = bool(shutil.which("ssh-keygen"))


def statement():
    recs = []
    p = Path(tempfile.mkdtemp()) / "x.jsonl"
    ev.append(p, "pack", "li", {"snapshot": {"ac": []}})
    ev.append(p, "sign", "周敏", {"note": "通过"})
    recs = ev.read(p)
    return ev.statement("OA-1 证据包", recs, {"ticket": "OA-1"})


class SignTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="tmh-sign-"))

    def check_round_trip(self):
        st = statement()
        st["signature"] = sign.sign(self.d, ev.payload(st))
        fp = st["signature"]["fingerprint"]
        self.assertEqual((sign.fingerprint(sign.ensure_key(self.d)), (self.d / sign.KEY).stat().st_mode & 0o077), (fp, 0))
        self.assertEqual(ev.check_signature(st, fp)[0], "good")
        self.assertEqual(ev.check_signature(st, "SHA256:someoneelse")[0], "other-key")
        self.assertEqual(ev.verify_statement(st, st["subject"][0]["digest"]["sha256"], fp)[0], "anchored")
        st["predicate"]["summary"]["ticket"] = "OA-2"  # anything changed after signing, even outside the records
        self.assertEqual(ev.check_signature(st)[0], "bad")
        self.assertEqual(ev.verify_statement(st)[0], "bad")
        return fp

    @unittest.skipUnless(HAVE_LIB, "cryptography not installed")
    def test_with_the_cryptography_package(self):
        self.check_round_trip()

    @unittest.skipUnless(HAVE_SSH, "ssh-keygen not installed")
    def test_with_ssh_keygen_only(self):
        with mock.patch.object(sign, "_lib", return_value=False):
            self.check_round_trip()

    @unittest.skipUnless(HAVE_LIB and HAVE_SSH, "needs both")
    def test_a_client_can_check_it_with_plain_ssh_keygen(self):
        st = statement()
        st["signature"] = sign.sign(self.d, ev.payload(st))
        f = self.d / "x.sig"
        f.write_text(st["signature"]["sig"] + "\n", encoding="utf-8")
        r = subprocess.run(["ssh-keygen", "-Y", "check-novalidate", "-n", sign.NAMESPACE, "-s", str(f)], input=ev.payload(st), capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_nothing_to_sign_with_means_unsigned_and_said_so(self):
        with mock.patch.object(sign, "_lib", return_value=False), mock.patch.object(shutil, "which", return_value=None):
            self.assertIsNone(sign.sign(self.d, b"x"))
        self.assertEqual(ev.check_signature(statement())[0], "none")
        self.assertEqual(ev.verify_statement(statement())[0], "consistent")


if __name__ == "__main__":
    unittest.main()
