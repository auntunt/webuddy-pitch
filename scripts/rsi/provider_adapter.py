"""Server-owned metered Messages primitive; NOT a production route or RSI proof.

A trusted admin registry freezes a full base-contract hash and input/price caps.
The only network child is fixed, single-shot, supervised and given private stdin.
Missing profiles fail closed. Fake loopback is opt-in and never production proof.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

from scripts.rsi import trial_preparation as L
from scripts.rsi.provider_transport import FramingError, validate_framing
from tmh.platform import supervised_process as SP

VERSION = "server-messages-adapter-v1"
HERE = Path(__file__).resolve().parent
SOURCES = {"ledger": HERE / "trial_preparation.py", "adapter": Path(__file__).resolve(),
           "transport": HERE / "provider_transport.py"}


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


LOADED_CODE = {key: file_hash(path) for key, path in SOURCES.items()}


def strict_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON field")
            value[key] = item
        return value
    def invalid(_):
        raise ValueError("nonfinite JSON")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def opaque(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("opaque registry name required")
    return value


def _private(st, uid, *, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(st.st_mode) or st.st_uid != uid or st.st_mode & 0o077:
        raise ValueError("trusted private owner and mode required")
    if not directory and st.st_nlink != 1:
        raise ValueError("single-link private file required")


class Registry:
    """Registry path and trusted UID come from deployment, never request data.

    Production default is root ownership. Fixture identity/HTTP must be explicitly
    enabled by the local harness; neither is an external API parameter.
    """
    def __init__(self, path, *, trusted_uid=0, allow_test_loopback=False):
        self.path = Path(path).absolute()
        self.uid = trusted_uid
        self.fixture = allow_test_loopback
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _private(os.fstat(self.fd), self.uid, directory=True)
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)

    def _read(self, name, *, directory=None):
        parent = self.fd
        child = None
        if directory:
            child = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
            parent = child
        try:
            if child is not None:
                _private(os.fstat(child), self.uid, directory=True)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                _private(before, self.uid)
                raw = stream.read()
                after = os.fstat(stream.fileno())
                identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
                if identity(before) != identity(after):
                    raise L.Conflict("registry file changed while reading")
                return raw, identity(after)
        finally:
            if child is not None:
                os.close(child)

    def load(self, profile_id):
        current, opened = os.lstat(self.path), os.fstat(self.fd)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise L.Conflict("registry directory was replaced")
        _private(opened, self.uid, directory=True)
        raw, profile_identity = self._read(opaque(profile_id) + ".json")
        p = strict_json(raw)
        L.fields(p, {"schema", "mode", "approved", "contract_sha256", "protocol_sha256", "endpoint", "credential_ref",
                     "model", "price", "input_cap_tokens", "output_cap_tokens", "call_timeout_ms", "valid_until_us",
                     "input_cap_reference_sha256", "parameters_version", "max_response_bytes", "billing_mode"})
        if p["schema"] != VERSION or p["approved"] is not True or p["parameters_version"] != "messages-text-standard-v1" or p["billing_mode"] != "token-only-upper-bound":
            raise ValueError("approved supported profile required")
        L.sha(p["contract_sha256"]); L.sha(p["protocol_sha256"]); L.sha(p["input_cap_reference_sha256"])
        for key in ("input_cap_tokens", "output_cap_tokens", "call_timeout_ms", "valid_until_us", "max_response_bytes"):
            L.integer(p[key], 1)
        url = urlsplit(p["endpoint"])
        if (url.username or url.password or url.query or url.fragment or not url.hostname
                or url.path != "/v1/messages" or url.port == 0):
            raise ValueError("exact Messages endpoint required")
        if p["mode"] == "fixture":
            if not self.fixture or url.scheme != "http" or url.hostname != "127.0.0.1":
                raise ValueError("fixture profile unavailable in production")
        elif p["mode"] != "live" or url.scheme != "https":
            raise ValueError("live profile requires HTTPS")
        elif self.uid == 0 or self.uid != os.geteuid():
            raise PermissionError("live profile requires its dedicated non-root broker owner")
        secret, credential_identity = self._read(opaque(p["credential_ref"]), directory="credentials")
        credential = secret.decode("ascii")
        if not credential or any(ord(c) < 33 or ord(c) > 126 for c in credential):
            raise ValueError("invalid credential format")
        return {"profile": p, "raw": raw, "sha256": hashlib.sha256(raw).hexdigest(),
                "credential": credential, "credential_identity": credential_identity, "profile_identity": profile_identity}


def _base(c):
    c = json.loads(L.encoded(c))
    c.pop("provider_binding", None)
    c["schema"] = L.VERSION
    return L.validate_contract(c)


class Adapter:
    def __init__(self, ledger, registry, evidence_root):
        if os.geteuid() == 0 and not registry.fixture:
            raise PermissionError("live transport must use a dedicated non-root broker identity")
        self.ledger, self.registry = ledger, registry
        self.root = Path(evidence_root).absolute()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("evidence symlink rejected")
        _private(self.root.stat(), os.getuid(), directory=True)

    def _check(self, c, loaded):
        p = loaded["profile"]
        if L.digest(_base(c)) != p["contract_sha256"]:
            raise L.Conflict("profile freezes another full root contract")
        if (p["model"] != c["model"] or p["price"] != c["price"]
                or p["price"]["input_micro_cny_per_token"] != p["price"]["cached_micro_cny_per_token"]):
            raise L.Conflict("profile model or conservative all-input quote mismatch")
        L.integer(p["price"]["input_micro_cny_per_token"], 1)
        L.integer(p["price"]["output_micro_cny_per_token"], 1)
        if self.ledger._time() >= min(p["valid_until_us"], c["limits"]["deadline_us"]):
            raise L.Conflict("original profile or root deadline expired")
        if p["valid_until_us"] < c["limits"]["deadline_us"]:
            raise L.Conflict("quote must cover entire original root deadline")
        current = {key: file_hash(path) for key, path in SOURCES.items()}
        if current != LOADED_CODE:
            raise L.Conflict("adapter sources changed after import")
        if c["schema"] == L.PROVIDER_VERSION:
            binding = c["provider_binding"]
            if (binding["profile_sha256"] != loaded["sha256"] or binding["code_sha256"] != current
                    or binding["protocol_sha256"] != p["protocol_sha256"]):
                raise L.Conflict("frozen profile, protocol or code changed")

    def register(self, profile_id, base_contract):
        c = _base(base_contract)
        loaded = self.registry.load(profile_id)
        self._check(c, loaded)
        c["schema"] = L.PROVIDER_VERSION
        c["provider_binding"] = {"profile_id": opaque(profile_id), "profile_sha256": loaded["sha256"],
                                 "protocol_sha256": loaded["profile"]["protocol_sha256"], "code_sha256": LOADED_CODE}
        return self.ledger.create(c)

    def _folder(self, key, request):
        return self.root / L.digest([key, request])

    def _owner(self, key, request, intent):
        return {"token": intent, "run_id": L.digest([key, request]), "data_dir": str(self.root)}

    def _seal(self, folder, name, raw):
        # No backfilling/replacing missing originals after an existing intent.
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())

    def _originals(self, key, request, c, row):
        folder = self._folder(key, request)
        profile_raw = (folder / "profile.json").read_bytes()
        body = (folder / "request.bin").read_bytes()
        profile_hash = hashlib.sha256(profile_raw).hexdigest()
        if (profile_hash != c["provider_binding"]["profile_sha256"]
                or L.digest([profile_hash, hashlib.sha256(body).hexdigest()]) != row["body"]["material_sha256"]):
            raise L.Conflict("original provider material mismatch")
        return folder, strict_json(profile_raw), body

    def _settle_original(self, key, request, c, row):
        folder, profile, body = self._originals(key, request, c, row)
        receipt = SP.read_receipt(folder / "transport", self._owner(key, request, row["intent"]))
        if receipt is None or not receipt["cleanup"].get("complete"):
            raise L.Conflict("complete original transport receipt required")
        raw = (folder / "transport" / "output.bin").read_bytes()
        if len(raw) != receipt["output"]["bytes"] or hashlib.sha256(raw).hexdigest() != receipt["output"]["sha256"]:
            raise L.Conflict("raw output changed after receipt verification")
        header, separator, response = raw.partition(b"\n")
        meta = strict_json(header)
        if (not separator or meta.get("schema") != "messages-text-transport-v1" or meta.get("status") != 200
                or meta.get("request_sha256") != hashlib.sha256(body).hexdigest()
                or meta.get("transport_sha256") != c["provider_binding"]["code_sha256"]["transport"]):
            raise L.Conflict("original HTTP transport binding mismatch")
        # Apply the stricter framing rule even to an old zero-exit receipt,
        # before version approval or any usage-based reduction of its hold.
        validate_framing(meta.get("headers"), len(response))
        if receipt["returncode"] != 0:
            raise L.Conflict("original transport did not complete successfully")
        if c["provider_binding"]["code_sha256"] != LOADED_CODE or any(file_hash(path) != LOADED_CODE[name] for name, path in SOURCES.items()):
            raise L.Conflict("settlement requires original adapter version")
        value = strict_json(response)
        if not isinstance(value, dict):
            raise ValueError("native message object required")
        if (value.get("type") != "message" or value.get("role") != "assistant"
                or not isinstance(value.get("id"), str) or not value["id"].startswith("msg_")):
            raise ValueError("native Messages response identity required")
        usage = value["usage"]
        # Refuse unsupported billable dimensions, rather than silently ignore a
        # new server tool, speed tier or opaque provider's charge object.
        allowed = {"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cache_creation", "service_tier", "speed", "inference_geo", "server_tool_use", "output_tokens_details"}
        if not isinstance(usage, dict) or set(usage) - allowed:
            raise ValueError("unsupported usage dimension")
        if usage.get("service_tier") not in (None, "standard") or usage.get("speed") not in (None, "standard"):
            raise ValueError("unquoted tier or speed")
        if usage.get("inference_geo") is not None and not isinstance(usage["inference_geo"], str):
            raise ValueError("invalid inference region")
        if usage.get("server_tool_use") is not None:
            tools = usage["server_tool_use"]
            L.fields(tools, {"web_fetch_requests", "web_search_requests"})
            if any(L.integer(n) != 0 for n in tools.values()):
                raise ValueError("unquoted server tools")
        if usage.get("output_tokens_details") is not None:
            details = usage["output_tokens_details"]
            L.fields(details, {"thinking_tokens"})
            if L.integer(details["thinking_tokens"]) > L.integer(usage["output_tokens"]):
                raise ValueError("output breakdown exceeds inclusive output")
        ordinary = L.integer(usage["input_tokens"])
        creation = L.integer(0 if usage.get("cache_creation_input_tokens") is None else usage["cache_creation_input_tokens"])
        cached = L.integer(0 if usage.get("cache_read_input_tokens") is None else usage["cache_read_input_tokens"])
        if usage.get("cache_creation") is not None:
            cache = usage["cache_creation"]
            L.fields(cache, {"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"})
            if sum(L.integer(v) for v in cache.values()) != creation:
                raise ValueError("cache creation breakdown mismatch")
        tokens = L.integer(ordinary + creation + cached)
        output = L.integer(usage["output_tokens"])
        normalized = {"provider_request_id": value["id"], "response_model": value["model"], "input_tokens": tokens,
                      "cached_input_tokens": cached, "output_tokens": output, "provider_charge_micro_cny": None,
                      "raw_response_sha256": hashlib.sha256(response).hexdigest()}
        state = self.ledger.settle(key, request, row["intent"], normalized)
        content = value.get("content")
        complete = (state == "settled" and value.get("stop_reason") == "end_turn" and isinstance(content, list)
                    and bool(content) and all(isinstance(block, dict) and block.get("type") == "text"
                                             and isinstance(block.get("text"), str) for block in content))
        return {"state": state, "response_complete": complete, "response_sha256": normalized["raw_response_sha256"],
                "input_tokens": tokens, "output_tokens": output, "accounting": "conservative_frozen_rate_upper_bound",
                "actual_provider_charge_verified": False, "rsi_qualified": False, "evidence": str(folder)}

    def reconcile(self, key, request):
        """Read original output and settle once; never read a key or send HTTP.

        Late settlement of an unknown request does not unblock the old root.
        """
        snap = self.ledger.snapshot(key, request)
        if snap["contract"]["schema"] != L.PROVIDER_VERSION:
            raise L.Conflict("provider v2 root required")
        try:
            return self._settle_original(key, request, snap["contract"], snap["attempt"])
        except FramingError:
            self.ledger.invalidate_framing(key, request, snap["attempt"]["intent"])
            return {"state": "unknown", "response_complete": False, "new_dispatch": False,
                    "actual_provider_charge_verified": False, "rsi_qualified": False,
                    "evidence": str(self._folder(key, request))}

    def dispatch(self, key, request, phase, *, system, messages, cancel_event=None):
        c = self.ledger.snapshot(key)["contract"]
        if c["schema"] != L.PROVIDER_VERSION:
            raise L.Conflict("provider v2 root required")
        loaded = self.registry.load(c["provider_binding"]["profile_id"])
        self._check(c, loaded)
        p = loaded["profile"]
        if not isinstance(system, str) or not isinstance(messages, list) or not messages:
            raise ValueError("complete text system/messages required")
        for msg in messages:
            L.fields(msg, {"role", "content"})
            if msg["role"] not in {"user", "assistant"} or not isinstance(msg["content"], str):
                raise ValueError("only native text messages supported")
        body = L.encoded({"model": p["model"]["requested_model"], "system": system, "messages": messages,
                          "max_tokens": p["output_cap_tokens"], "stream": False, "service_tier": "standard_only"}).encode()
        material = L.digest([loaded["sha256"], hashlib.sha256(body).hexdigest()])
        self.ledger.reserve(key, request, phase, p["input_cap_tokens"], p["output_cap_tokens"], material_sha256=material)
        if cancel_event is not None and cancel_event.is_set():
            return {"state": self.ledger.cancel(key, request), "response_complete": False, "new_dispatch": False}
        intent = self.ledger.intent(key, request)
        if not intent["new_intent"]:
            if intent["state"] == "settled":
                return dict(self.reconcile(key, request), new_dispatch=False)
            return {"state": intent["state"], "response_complete": False, "new_dispatch": False}
        folder = self._folder(key, request)
        adapter = self
        class Cancel:
            def is_set(self):
                if cancel_event is not None and cancel_event.is_set():
                    return True
                try:
                    now = adapter.registry.load(c["provider_binding"]["profile_id"])
                    adapter._check(c, now)
                    return (now["credential_identity"] != loaded["credential_identity"]
                            or now["profile_identity"] != loaded["profile_identity"])
                except (OSError, ValueError, KeyError, TypeError):
                    return True
        guard = Cancel()
        try:
            if guard.is_set():
                raise L.Conflict("profile, source or cancellation changed before transport")
            folder.mkdir(mode=0o700)  # Existing evidence is never repaired/overwritten.
            self._seal(folder, "profile.json", loaded["raw"])
            self._seal(folder, "request.bin", body)
            timeout = min(p["call_timeout_ms"] / 1000, (c["limits"]["deadline_us"] - self.ledger._time()) / 1000000)
            if timeout <= 0:
                raise L.Conflict("root deadline expired before transport")
            private = {"endpoint": p["endpoint"], "credential": loaded["credential"],
                       "body": base64.b64encode(body).decode(), "fixture": p["mode"] == "fixture",
                       "max_response_bytes": p["max_response_bytes"]}
            result = SP.run_supervised([sys.executable, "-I", str(SOURCES["transport"])], folder=folder / "transport",
                         owner=self._owner(key, request, intent["intent"]), cwd=folder,
                         env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
                         timeout=timeout, cancel_event=guard, stdin=L.encoded(private))
            if not result.cleanup.get("complete") or guard.is_set():
                raise L.Conflict("transport failed, cancelled or changed; remote outcome unknown")
            snap = self.ledger.snapshot(key, request)
            return dict(self._settle_original(key, request, c, snap["attempt"]), new_dispatch=True)
        except BaseException as error:
            # Includes all parsing/protocol failures. Never expose raw exceptions,
            # release funds or retry after the original intent has been committed.
            if isinstance(error, FramingError):
                self.ledger.invalidate_framing(key, request, intent["intent"])
            else:
                self.ledger.unknown(key, request, intent["intent"], "provider_or_transport_unverifiable")
            if not isinstance(error, Exception):
                raise
            return {"state": "unknown", "response_complete": False, "new_dispatch": True,
                    "actual_provider_charge_verified": False, "rsi_qualified": False, "evidence": str(folder)}
