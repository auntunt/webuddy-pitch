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
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlsplit

from scripts.rsi import trial_preparation as L
from scripts.rsi.provider_transport import FramingError, validate_framing
from tmh.platform import supervised_process as SP

VERSION = "server-messages-adapter-v1"
TOKEN_VERSION = "server-fixed-text-token-adapter-v2"
FINITE_VERSION = "server-fixed-text-finite-adapter-v3"
TOKEN_PROTOCOLS = {
    "messages": {"parameters": "messages-text-token-v1", "path": "/v1/messages", "usage": "input+cache_creation+cache_read+output"},
    "responses": {"parameters": "responses-text-token-v1", "path": "/v1/responses", "usage": "inclusive_input+inclusive_output;total=parent_sum"},
}
FINITE_PROTOCOLS = {k: dict(v, parameters=k+"-text-finite-v1", usage="reported_responses_only;hidden_attempts_unknown")
                    for k, v in TOKEN_PROTOCOLS.items()}
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


def validate_token_bound(profile, raw):
    """Check a private trusted admission, not infer a model limit from text size.

    Its truth is a deployment responsibility. Fixtures never establish a live
    provider bound; no profile is generated or approved by this primitive.
    """
    value = strict_json(raw)
    L.fields(value, {"schema", "kind", "mode", "model", "protocol", "input_cap_tokens", "output_cap_tokens",
                     "all_input_included", "all_output_included", "no_hidden_retries", "all_tokens_in_usage",
                     "verified", "source_sha256", "valid_until_us"})
    if (hashlib.sha256(raw).hexdigest() != profile["input_cap_reference_sha256"]
            or value["schema"] != "trusted-total-token-bound-v1" or value["kind"] != "provider_enforced_total_limit"
            or value["mode"] != profile["mode"] or value["model"] != profile["model"] or value["protocol"] != profile["protocol"]
            or any(value[k] is not True for k in ("all_input_included", "all_output_included", "no_hidden_retries", "all_tokens_in_usage", "verified"))
            or any(value[k] != profile[k] for k in ("input_cap_tokens", "output_cap_tokens"))):
        raise ValueError("verified complete provider token bound required")
    L.sha(value["source_sha256"])
    for name in ("input_cap_tokens", "output_cap_tokens", "valid_until_us"):
        L.integer(value[name], 1)
    if value["valid_until_us"] < profile["valid_until_us"]:
        raise ValueError("bound must cover the original profile window")
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
        keys = {"schema", "mode", "approved", "contract_sha256", "protocol_sha256", "endpoint", "credential_ref",
                     "model", "price", "input_cap_tokens", "output_cap_tokens", "call_timeout_ms", "valid_until_us",
                     "input_cap_reference_sha256", "parameters_version", "max_response_bytes", "billing_mode"}
        token_only = isinstance(p, dict) and p.get("schema") == TOKEN_VERSION
        finite = isinstance(p, dict) and p.get("schema") == FINITE_VERSION
        if token_only:
            keys.remove("price"); keys.update({"protocol", "bound_evidence_ref"})
        elif finite:
            keys -= {"price", "input_cap_tokens", "input_cap_reference_sha256"}
            keys.update({"protocol", "max_request_bytes"})
        L.fields(p, keys)
        protocol = (FINITE_PROTOCOLS if finite else TOKEN_PROTOCOLS).get(p.get("protocol")) if token_only or finite else None
        if p["approved"] is not True or (finite and (protocol is None or p["parameters_version"] != protocol["parameters"] or p["billing_mode"] != "observed-usage-v1")) or (token_only and (protocol is None or p["parameters_version"] != protocol["parameters"] or p["billing_mode"] != "tokens-inclusive-v1")) or (not (token_only or finite) and (p["schema"] != VERSION or p["parameters_version"] != "messages-text-standard-v1" or p["billing_mode"] != "token-only-upper-bound")):
            raise ValueError("approved supported profile required")
        L.sha(p["contract_sha256"]); L.sha(p["protocol_sha256"])
        if not finite: L.sha(p["input_cap_reference_sha256"])
        for key in ("max_request_bytes" if finite else "input_cap_tokens", "output_cap_tokens", "call_timeout_ms", "valid_until_us", "max_response_bytes"):
            L.integer(p[key], 1)
        url = urlsplit(p["endpoint"])
        if (url.username or url.password or url.query or url.fragment or not url.hostname
                or url.path != (protocol["path"] if token_only or finite else "/v1/messages") or url.port == 0):
            raise ValueError("exact supported protocol endpoint required")
        if p["mode"] == "fixture":
            if not self.fixture or url.scheme != "http" or url.hostname != "127.0.0.1":
                raise ValueError("fixture profile unavailable in production")
        elif p["mode"] != "live" or url.scheme != "https":
            raise ValueError("live profile requires HTTPS")
        elif self.uid == 0 or self.uid != os.geteuid():
            raise PermissionError("live profile requires its dedicated non-root broker owner")
        bound, bound_identity = None, None
        if token_only:
            bound, bound_identity = self._read(opaque(p["bound_evidence_ref"]), directory="bounds")
            validate_token_bound(p, bound)
            if p["protocol_sha256"] != L.digest(protocol):
                raise ValueError("fixed protocol definition changed")
        if finite and p["protocol_sha256"] != L.digest(protocol):
            raise ValueError("fixed finite protocol definition changed")
        secret, credential_identity = self._read(opaque(p["credential_ref"]), directory="credentials")
        credential = secret.decode("ascii")
        if not credential or any(ord(c) < 33 or ord(c) > 126 for c in credential):
            raise ValueError("invalid credential format")
        return {"profile": p, "raw": raw, "sha256": hashlib.sha256(raw).hexdigest(),
                "credential": credential, "credential_identity": credential_identity, "profile_identity": profile_identity,
                "token_bound": bound, "bound_identity": bound_identity}


def _base(c):
    c = json.loads(L.encoded(c))
    c.pop("provider_binding", None)
    c["schema"] = L.FINITE_VERSION if c["schema"] in L.FINITE_SCHEMAS else L.TOKEN_VERSION if c["schema"] in L.TOKEN_SCHEMAS else L.VERSION
    return L.validate_contract(c)


def normalize_messages(value, response):
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
    return normalized


def normalize_token_response(protocol, value, response):
    """Inclusive parent counts; one unambiguous full text for policy derivation."""
    if not isinstance(value, dict):
        raise ValueError("native response object required")
    policy = None
    if protocol == "messages":
        if (value.get("type") != "message" or value.get("role") != "assistant"
                or not isinstance(value.get("id"), str) or not value["id"].startswith("msg_")):
            raise ValueError("native Messages identity required")
        if not isinstance(value.get("usage"), dict):
            raise ValueError("explicit inclusive Messages usage required")
        for field in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
            L.integer(value["usage"][field])
        normalized = normalize_messages(value, response)
        content = value.get("content")
        if (value.get("stop_reason") == "end_turn" and isinstance(content, list) and len(content) == 1
                and isinstance(content[0], dict) and content[0].get("type") == "text"
                and isinstance(content[0].get("text"), str) and content[0].get("citations") in (None, [])):
            policy = content[0]["text"]
    elif protocol == "responses":
        if value.get("object") != "response" or not isinstance(value.get("id"), str) or not value["id"].startswith("resp_"):
            raise ValueError("native Responses identity required")
        usage = value["usage"]
        L.fields(usage, {"input_tokens", "input_tokens_details", "output_tokens", "output_tokens_details", "total_tokens"})
        details = usage["input_tokens_details"]
        detail_keys = {"cached_tokens"}
        if isinstance(details, dict) and "cache_write_tokens" in details:
            detail_keys.add("cache_write_tokens")
        L.fields(details, detail_keys)
        L.fields(usage["output_tokens_details"], {"reasoning_tokens"})
        input_tokens, output_tokens, total = (L.integer(usage[n]) for n in ("input_tokens", "output_tokens", "total_tokens"))
        cached = L.integer(usage["input_tokens_details"]["cached_tokens"])
        reasoning = L.integer(usage["output_tokens_details"]["reasoning_tokens"])
        written = L.integer(details["cache_write_tokens"]) if "cache_write_tokens" in details else 0
        if cached > input_tokens or written > input_tokens or reasoning > output_tokens or total != input_tokens + output_tokens:
            raise ValueError("contradictory inclusive Responses usage")
        normalized = {"provider_request_id": value["id"], "response_model": value["model"], "input_tokens": input_tokens,
                      "cached_input_tokens": cached, "output_tokens": output_tokens, "provider_charge_micro_cny": None,
                      "raw_response_sha256": hashlib.sha256(response).hexdigest()}
        output = value.get("output")
        if (value.get("status") == "completed" and value.get("error") is None and value.get("incomplete_details") is None
                and isinstance(output, list) and all(isinstance(v, dict) and v.get("type") in {"reasoning", "message"} for v in output)):
            messages = [v for v in output if v["type"] == "message"]
            if len(messages) == 1:
                message = messages[0]
                content = message.get("content")
                if (message.get("status") == "completed" and message.get("role") == "assistant"
                        and isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
                        and content[0].get("type") == "output_text" and isinstance(content[0].get("text"), str)
                        and content[0].get("annotations") == []):
                    policy = content[0]["text"]
    else:
        raise ValueError("unsupported explicit token protocol")
    return normalized, policy



def normalize_finite_response(protocol, value, response):
    """Complete native text is independent of unproved usage completeness.

    Preserve the original usage object. Missing/unsupported counts never become
    zeros, a trusted billing bound, or a claim about hidden gateway attempts.
    """
    if not isinstance(value, dict): raise ValueError("native response object required")
    policy = None
    if protocol == "messages":
        if (value.get("type") != "message" or value.get("role") != "assistant"
                or not isinstance(value.get("id"), str) or not value["id"].startswith("msg_")):
            raise ValueError("native Messages identity required")
        content = value.get("content")
        if (value.get("stop_reason") == "end_turn" and isinstance(content, list) and len(content) == 1
                and isinstance(content[0], dict) and content[0].get("type") == "text"
                and isinstance(content[0].get("text"), str) and content[0].get("citations") in (None, [])):
            policy = content[0]["text"]
    elif protocol == "responses":
        if value.get("object") != "response" or not isinstance(value.get("id"), str) or not value["id"].startswith("resp_"):
            raise ValueError("native Responses identity required")
        output = value.get("output")
        if (value.get("status") == "completed" and value.get("error") is None and value.get("incomplete_details") is None
                and isinstance(output, list) and all(isinstance(v, dict) and v.get("type") in {"reasoning", "message"} for v in output)):
            messages = [v for v in output if v["type"] == "message"]
            if len(messages) == 1:
                message = messages[0];content = message.get("content")
                if (message.get("status") == "completed" and message.get("role") == "assistant"
                        and isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
                        and content[0].get("type") == "output_text" and isinstance(content[0].get("text"), str)
                        and content[0].get("annotations") == []):
                    policy = content[0]["text"]
    else: raise ValueError("unsupported finite protocol")
    L.text(value.get("model"))
    usage_raw = value.get("usage")
    normalized = None
    try:
        normalized, _ = normalize_token_response(protocol, value, response)
    except (ValueError, TypeError, KeyError):
        pass
    result = {"schema": "finite-reported-usage-v1", "provider_request_id": value["id"], "response_model": value["model"],
              "raw_response_sha256": hashlib.sha256(response).hexdigest(), "provider_charge_micro_cny": None,
              "usage_raw": usage_raw if isinstance(usage_raw, dict) else None,
              "usage_status": "reported" if normalized else "unknown",
              "usage_issue": "" if normalized else "missing_or_unsupported_original_usage", "hidden_attempts": "unknown"}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        result[field] = normalized[field] if normalized else None
    return result, policy


def token_request(profile, system, messages):
    if profile["protocol"] == "messages":
        return {"model": profile["model"]["requested_model"], "system": system, "messages": messages,
                "max_tokens": profile["output_cap_tokens"], "stream": False, "service_tier": "standard_only",
                "tools": [], "thinking": {"type": "disabled"}}
    if profile["protocol"] != "responses":
        raise ValueError("unsupported explicit request protocol")
    return {"model": profile["model"]["requested_model"], "instructions": system, "input": messages,
            "max_output_tokens": profile["output_cap_tokens"], "stream": False, "store": False,
            "background": False, "tools": [], "tool_choice": "none", "parallel_tool_calls": False,
            "truncation": "disabled", "include": []}


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
        finite = c["schema"] in L.FINITE_SCHEMAS
        if finite != (p["schema"] == FINITE_VERSION):
            raise L.Conflict("finite execution requires its distinct approved profile")
        token_only = c["schema"] in L.TOKEN_SCHEMAS
        if token_only != (p["schema"] == TOKEN_VERSION) or p["model"] != c["model"]:
            raise L.Conflict("profile model or budget protocol mismatch")
        if token_only:
            validate_token_bound(p, loaded["token_bound"])
        elif not finite:
            if (p["price"] != c["price"] or p["price"]["input_micro_cny_per_token"] != p["price"]["cached_micro_cny_per_token"]):
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
        if c["schema"] in L.PROVIDER_SCHEMAS:
            binding = c["provider_binding"]
            if (binding["profile_sha256"] != loaded["sha256"] or binding["code_sha256"] != current
                    or binding["protocol_sha256"] != p["protocol_sha256"]):
                raise L.Conflict("frozen profile, protocol or code changed")

    def register(self, profile_id, base_contract):
        c = _base(base_contract)
        loaded = self.registry.load(profile_id)
        self._check(c, loaded)
        c["schema"] = L.FINITE_PROVIDER_VERSION if c["schema"] == L.FINITE_VERSION else L.TOKEN_PROVIDER_VERSION if c["schema"] == L.TOKEN_VERSION else L.PROVIDER_VERSION
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
        profile = strict_json(profile_raw)
        if c["schema"] == L.TOKEN_PROVIDER_VERSION:
            validate_token_bound(profile, (folder / "input-bound.json").read_bytes())
        return folder, profile, body

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
        token_only = c["schema"] in {L.TOKEN_PROVIDER_VERSION, L.FINITE_PROVIDER_VERSION}
        if (not separator or meta.get("schema") != ("token-text-transport-v2" if token_only else "messages-text-transport-v1")
                or token_only and meta.get("protocol") != profile["protocol"] or meta.get("status") != 200
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
        if c["schema"] == L.FINITE_PROVIDER_VERSION:
            normalized, policy = normalize_finite_response(profile["protocol"], value, response)
            state = self.ledger.settle(key, request, row["intent"], normalized)
            return {"state": state, "response_complete": state == "settled" and policy is not None,
                    "response_text": policy, "response_sha256": normalized["raw_response_sha256"],
                    "input_tokens": normalized["input_tokens"], "output_tokens": normalized["output_tokens"],
                    "accounting": "reported_responses_only", "usage_status": normalized["usage_status"],
                    "hidden_attempts": "unknown", "actual_provider_charge_verified": False,
                    "rsi_qualified": False, "evidence": str(folder)}
        if token_only:
            normalized, policy = normalize_token_response(profile["protocol"], value, response)
            state = self.ledger.settle(key, request, row["intent"], normalized)
            return {"state": state, "response_complete": state == "settled" and policy is not None,
                    "response_text": policy, "response_sha256": normalized["raw_response_sha256"],
                    "input_tokens": normalized["input_tokens"], "output_tokens": normalized["output_tokens"],
                    "accounting": "inclusive_tokens", "actual_provider_charge_verified": False,
                    "rsi_qualified": False, "evidence": str(folder)}
        if not isinstance(value, dict):
            raise ValueError("native message object required")
        if (value.get("type") != "message" or value.get("role") != "assistant"
                or not isinstance(value.get("id"), str) or not value["id"].startswith("msg_")):
            raise ValueError("native Messages response identity required")
        normalized = normalize_messages(value, response)
        tokens, output = normalized["input_tokens"], normalized["output_tokens"]
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
        if snap["contract"]["schema"] not in L.PROVIDER_SCHEMAS:
            raise L.Conflict("explicit provider root required")
        try:
            return self._settle_original(key, request, snap["contract"], snap["attempt"])
        except FramingError:
            self.ledger.invalidate_framing(key, request, snap["attempt"]["intent"])
            return {"state": "unknown", "response_complete": False, "new_dispatch": False,
                    "actual_provider_charge_verified": False, "rsi_qualified": False,
                    "evidence": str(self._folder(key, request))}

    def dispatch(self, key, request, phase, *, system, messages, cancel_event=None, dispatch_guard=None):
        c = self.ledger.snapshot(key)["contract"]
        if c["schema"] not in L.PROVIDER_SCHEMAS:
            raise L.Conflict("explicit provider root required")
        loaded = self.registry.load(c["provider_binding"]["profile_id"])
        self._check(c, loaded)
        p = loaded["profile"]
        if not isinstance(system, str) or not isinstance(messages, list) or not messages:
            raise ValueError("complete text system/messages required")
        for msg in messages:
            L.fields(msg, {"role", "content"})
            if msg["role"] not in {"user", "assistant"} or not isinstance(msg["content"], str):
                raise ValueError("only native text messages supported")
        token_only = c["schema"] in {L.TOKEN_PROVIDER_VERSION, L.FINITE_PROVIDER_VERSION}
        if token_only and phase != "propose":
            self._verified_candidate(key)
            if phase in {"baseline", "candidate"}:
                expected = c["baseline_sha256"] if phase == "baseline" else self.ledger.snapshot(key)["candidate_binding"]["candidate_sha256"]
                if hashlib.sha256(system.encode()).hexdigest() != expected:
                    raise L.Conflict("arm changed its frozen policy")
        body = L.encoded(token_request(p, system, messages) if token_only else
                         {"model": p["model"]["requested_model"], "system": system, "messages": messages,
                          "max_tokens": p["output_cap_tokens"], "stream": False, "service_tier": "standard_only"}).encode()
        if c["schema"] == L.FINITE_PROVIDER_VERSION and len(body) > p["max_request_bytes"]:
            raise L.Conflict("complete request exceeds finite byte resource limit")
        material = L.digest([loaded["sha256"], hashlib.sha256(body).hexdigest()])
        # Trusted registered entry may serialize CURRENT authority with the
        # durable reservation/intent. Never hold this across the network child.
        with dispatch_guard if dispatch_guard is not None else nullcontext():
            self.ledger.reserve(key, request, phase, p["max_request_bytes"] if c["schema"] == L.FINITE_PROVIDER_VERSION else p["input_cap_tokens"], p["output_cap_tokens"], material_sha256=material)
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
                            or now["profile_identity"] != loaded["profile_identity"]
                            or now["bound_identity"] != loaded["bound_identity"])
                except (OSError, ValueError, KeyError, TypeError):
                    return True
        guard = Cancel()
        try:
            if guard.is_set():
                raise L.Conflict("profile, source or cancellation changed before transport")
            folder.mkdir(mode=0o700)  # Existing evidence is never repaired/overwritten.
            self._seal(folder, "profile.json", loaded["raw"])
            self._seal(folder, "request.bin", body)
            if c["schema"] == L.TOKEN_PROVIDER_VERSION:
                self._seal(folder, "input-bound.json", loaded["token_bound"])
            timeout = min(p["call_timeout_ms"] / 1000, (c["limits"]["deadline_us"] - self.ledger._time()) / 1000000)
            if timeout <= 0:
                raise L.Conflict("root deadline expired before transport")
            private = {"endpoint": p["endpoint"], "credential": loaded["credential"],
                       "body": base64.b64encode(body).decode(), "fixture": p["mode"] == "fixture",
                       "max_response_bytes": p["max_response_bytes"]}
            if token_only:
                private["protocol"] = p["protocol"]
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

    def bind_candidate(self, key, request):
        """Derive the complete policy from original supervised output, never caller text."""
        snapshot = self.ledger.snapshot(key, request)
        if snapshot["contract"]["schema"] not in {L.TOKEN_PROVIDER_VERSION, L.FINITE_PROVIDER_VERSION} or snapshot["attempt"]["body"]["phase"] != "propose":
            raise L.Conflict("original token proposal required")
        try:
            result = self.reconcile(key, request)
        except (OSError, ValueError) as error:
            raise L.Conflict("unverifiable original proposal response") from error
        if not result["response_complete"] or not result.get("response_text", "").strip():
            raise L.Conflict("one complete original policy response required")
        bound = self.ledger.bind_candidate(key, request, result["response_text"], result["response_sha256"])
        return dict(bound, candidate_derivation_verified=True, response_sha256=result["response_sha256"], rsi_qualified=False)

    def _verified_candidate(self, key):
        snapshot = self.ledger.snapshot(key)
        bound = snapshot.get("candidate_binding")
        if not bound:
            raise L.Conflict("original candidate binding required")
        result = self.reconcile(key, bound["proposal_request"])
        if (not result["response_complete"] or result.get("response_text") != bound["candidate_text"]
                or result["response_sha256"] != bound["raw_response_sha256"]):
            raise L.Conflict("candidate differs from its original response text")
        return bound
