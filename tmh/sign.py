"""Signatures on exported evidence: who exported it, not only that it holds together.

One format whatever signs it: an SSH signature (SSHSIG, the format of `ssh-keygen -Y sign`) by an Ed25519 key kept
in the platform's data directory. The Python `cryptography` package signs and checks it when installed; otherwise
the system's ssh-keygen does; with neither, nothing is signed and the export says so. A client can check a
signature with webuddy (`tmh evidence-verify`) or with plain ssh-keygen, and compares the key's fingerprint with
the one the provider gave them (it is on the sign-off page).

Nothing here implements cryptography: Ed25519 comes from the library or from OpenSSH. This file only lays the
bytes out the way SSHSIG does (https://github.com/openssh/openssh-portable/blob/master/PROTOCOL.sshsig).
"""
from __future__ import annotations

import base64
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path

NAMESPACE = "webuddy-evidence@v1"
KEY = "signing_ed25519"
ARMOR = ("-----BEGIN SSH SIGNATURE-----", "-----END SSH SIGNATURE-----")
_LOCK = threading.Lock()
_CHECKED: dict = {}  # key directory -> public key line, once the pair was found to match


class Unverifiable(RuntimeError):
    """Nothing here can check the signature (no tool, or one too old): not the same as a bad signature."""


def _lib():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
        return True
    except ImportError:
        return False


def backend() -> str:
    """What can sign here: "cryptography", "ssh-keygen", or "" (nothing; exports go out unsigned)."""
    return "cryptography" if _lib() else "ssh-keygen" if shutil.which("ssh-keygen") else ""


def _s(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


def _read(buf: bytes, i: int) -> tuple[bytes, int]:
    n = struct.unpack(">I", buf[i:i + 4])[0]
    return buf[i + 4:i + 4 + n], i + 4 + n


def fingerprint(pub_line: str) -> str:
    blob = base64.b64decode(pub_line.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def _derive_pub(k: Path) -> str:
    """The public key that belongs to the private key file, as "ssh-ed25519 AAAA…"."""
    if _lib():
        from cryptography.hazmat.primitives import serialization as s
        key = s.load_ssh_private_key(k.read_bytes(), password=None)
        return key.public_key().public_bytes(s.Encoding.OpenSSH, s.PublicFormat.OpenSSH).decode()
    r = subprocess.run(["ssh-keygen", "-y", "-f", str(k)], capture_output=True, timeout=30, text=True)
    if r.returncode:
        raise RuntimeError("读不了签名私钥 %s：%s" % (k, r.stderr.strip()[:200]))
    return " ".join(r.stdout.split()[:2])


def _put(path: Path, data: bytes, mode: int) -> None:
    """Write a file whole or not at all, created with its final permissions (a private key is never readable by others)."""
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ensure_key(d: Path) -> str:
    """The platform's signing key (made on first use, readable only by its owner). Returns the public key line, or ""
    when nothing here can make one. Raises when the key files on disk do not belong together."""
    d = Path(d)
    k, pub = d / KEY, d / (KEY + ".pub")
    with _LOCK:
        if str(d) in _CHECKED and k.exists():
            return _CHECKED[str(d)]
        if not backend():
            return ""
        d.mkdir(parents=True, exist_ok=True)
        if not k.exists():
            if _lib():
                from cryptography.hazmat.primitives import serialization as s
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                key = Ed25519PrivateKey.generate()
                priv = key.private_bytes(s.Encoding.PEM, s.PrivateFormat.OpenSSH, s.NoEncryption())
            else:
                with tempfile.TemporaryDirectory() as t:
                    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "webuddy-evidence", "-f", t + "/k"], check=True,
                                   capture_output=True, timeout=30)
                    priv = Path(t, "k").read_bytes()
            _put(k, priv, 0o600)
            pub.unlink(missing_ok=True)
        line = _derive_pub(k)
        if not pub.exists():
            _put(pub, (line + " webuddy-evidence\n").encode(), 0o644)
        have = pub.read_text(encoding="utf-8").strip()
        if have.split()[:2] != line.split()[:2]:
            raise RuntimeError("签名钥匙对不上：%s 不是 %s 的公钥。别动这两个文件，先查是谁改的" % (pub, k))
        _CHECKED[str(d)] = have
        return have


def _signed_data(data: bytes) -> bytes:
    return b"SSHSIG" + _s(NAMESPACE.encode()) + _s(b"") + _s(b"sha512") + _s(hashlib.sha512(data).digest())


def sign(d: Path, data: bytes) -> dict | None:
    """{"format", "namespace", "publicKey", "fingerprint", "sig"} or None when nothing here can sign."""
    pub = ensure_key(d)
    if not pub:
        return None
    k = Path(d) / KEY
    if _lib():
        from cryptography.hazmat.primitives import serialization as s
        key = s.load_ssh_private_key(k.read_bytes(), password=None)
        raw_pub = base64.b64decode(pub.split()[1])
        sig = _s(b"ssh-ed25519") + _s(key.sign(_signed_data(data)))
        blob = b"SSHSIG" + struct.pack(">I", 1) + _s(raw_pub) + _s(NAMESPACE.encode()) + _s(b"") + _s(b"sha512") + _s(sig)
        body = base64.b64encode(blob).decode()
        armored = "\n".join([ARMOR[0]] + [body[i:i + 70] for i in range(0, len(body), 70)] + [ARMOR[1]])
    else:
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "data"
            f.write_bytes(data)
            r = subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(k), "-n", NAMESPACE, str(f)], capture_output=True, timeout=30, text=True)
            if r.returncode:
                raise RuntimeError("ssh-keygen 签不了名（OpenSSH 8.0 起才支持 -Y sign）：%s" % r.stderr.strip()[:200])
            armored = (Path(t) / "data.sig").read_text(encoding="utf-8").strip()
    return {"format": "sshsig", "namespace": NAMESPACE, "publicKey": pub, "fingerprint": fingerprint(pub), "sig": armored}


def verify(sig: dict, data: bytes) -> tuple[bool, str]:
    """(valid, fingerprint of the key that made it). The caller compares the fingerprint with the provider's."""
    try:
        armored = sig["sig"].strip()
        blob = base64.b64decode("".join(l for l in armored.splitlines() if not l.startswith("-----")))
        if blob[:6] != b"SSHSIG" or struct.unpack(">I", blob[6:10])[0] != 1:
            return False, ""
        raw_pub, i = _read(blob, 10)
        ns, i = _read(blob, i)
        _, i = _read(blob, i)
        alg, i = _read(blob, i)
        sigblob, i = _read(blob, i)
        ktype, j = _read(raw_pub, 0)
        keybytes, _ = _read(raw_pub, j)
        styp, k = _read(sigblob, 0)
        rawsig, _ = _read(sigblob, k)
    except (KeyError, ValueError, struct.error, TypeError, AttributeError):
        return False, ""
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(raw_pub).digest()).decode().rstrip("=")
    if ns.decode(errors="replace") != NAMESPACE or alg != b"sha512" or ktype != b"ssh-ed25519" or styp != b"ssh-ed25519":
        return False, fp
    if _lib():
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            Ed25519PublicKey.from_public_bytes(keybytes).verify(rawsig, _signed_data(data))
            return True, fp
        except (InvalidSignature, ValueError):
            return False, fp
    if shutil.which("ssh-keygen"):
        with tempfile.TemporaryDirectory() as t:
            sf = Path(t) / "data.sig"
            sf.write_text(armored + "\n", encoding="utf-8")
            r = subprocess.run(["ssh-keygen", "-Y", "check-novalidate", "-n", NAMESPACE, "-s", str(sf)], input=data, capture_output=True, timeout=30)
            if r.returncode == 0:
                return True, fp
            if b"verification failed" in r.stderr.lower() or b"incorrect signature" in r.stderr.lower():
                return False, fp
            raise Unverifiable("这台机器的 ssh-keygen 验不了签（要 OpenSSH 8.2 以上）：%s" % r.stderr.decode(errors="replace").strip()[:200])
    raise Unverifiable("这台机器上没有能验签的工具：装 Python 的 cryptography 包，或 OpenSSH 8.2 以上的 ssh-keygen")


def ready(d: Path) -> str:
    """The fingerprint exports from here are signed with, after signing and checking a test message once; "" when
    signing does not work here (and so nothing should say exports are signed)."""
    key = str(Path(d))
    if key in _READY:
        return _READY[key]
    fp = ""
    try:
        s = sign(d, b"webuddy self-test")
        if s and verify(s, b"webuddy self-test")[0]:
            fp = s["fingerprint"]
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        fp = ""
    _READY[key] = fp
    return fp


_READY: dict = {}
