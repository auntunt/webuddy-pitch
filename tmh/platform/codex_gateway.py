"""One fixed-target HTTP exchange for the trusted isolated Codex carrier.

This runs in the host controller under the original Runner supervision. It is
not a network listener, model adapter, retry loop or new budget authority.
The namespace's trusted relay must authenticate its caller before invoking it.
"""
import hashlib
import http.client
import json
import math
import runpy
import ssl
import time
from urllib.parse import urlsplit

from .. import resources
from .codex_frozen_config import PUBLIC_KEY, FrozenConfig

# One canonical source is shipped through the existing resource pipeline. This
# also works in wheels and vendored tools without a top-level scripts package.
validate_framing = runpy.run_path(str(resources.root() / "scripts/rsi/provider_transport.py"))["validate_framing"]

TARGET = "/v1/responses"
HOST = "127.0.0.1:48671"
HOP_HEADERS = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "te", "trailer", "upgrade"}


class GatewayError(ValueError):
    pass


def _left(deadline, cancel):
    if cancel is not None and cancel.is_set():
        raise GatewayError("isolated gateway cancelled")
    value = deadline - time.monotonic()
    if value <= 0:
        raise GatewayError("isolated gateway original deadline expired")
    return value


def forward(frozen, environment, method, target, headers, body, *, deadline,
            on_headers, on_body, journal, cancel=None):
    """Forward an official request; keep authentication exclusively in the host.

    All callbacks are trusted host code. journal receives original upstream
    headers and every received payload byte and MUST remain private on-server;
    it must never project them straight into a public API. No injected request
    credential is journalled. Exceptions export a fixed phase/type, not private
    http.client diagnostics. The owner must supervise this entire process so a
    blocking TLS/read is also cancelled with the original process group.
    """
    if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)):
        raise GatewayError("finite original gateway deadline required")
    _left(deadline, cancel)
    if type(frozen) is not FrozenConfig or method != "POST" or target != TARGET or not isinstance(body, bytes):
        raise GatewayError("only the fixed Responses route is permitted")
    def pairs(values):
        result = {}
        for name, value in values:
            if name in result:
                raise ValueError("duplicate request key")
            result[name] = value
        return result

    def constant(value):
        raise ValueError("non-JSON request number")

    try:
        payload = json.loads(body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise GatewayError("unambiguous complete JSON request required") from None
    if not isinstance(payload, dict) or payload.get("model") != frozen.model:
        raise GatewayError("request model differs from the frozen configuration")
    # Validate duplicates and raw framing before opening any upstream connection.
    mode, length = validate_framing(headers, len(body))
    if mode != "length" or length != len(body):
        raise GatewayError("complete Content-Length request required")
    by_name = {}
    for name, value in headers:
        by_name.setdefault(name.lower(), []).append(value)
    if (by_name.get("host") != [HOST]
            or by_name.get("authorization") != ["Bearer " + PUBLIC_KEY]
            or "proxy-authorization" in by_name or "upgrade" in by_name
            or by_name.get("content-type") != ["application/json"]):
        raise GatewayError("invalid isolated gateway request headers")
    tokens = {part.strip().lower() for value in by_name.get("connection", []) for part in value.split(",")}
    if tokens - {"close", "keep-alive"}:
        raise GatewayError("unsupported connection-specific request headers")
    upstream = frozen.upstream(environment)
    url = urlsplit(upstream["endpoint"])
    connection = None
    response = None
    received = 0
    digest = hashlib.sha256()
    phase = "connect"
    try:
        journal("request", {"method": method, "target": target, "bytes": len(body),
                            "sha256": hashlib.sha256(body).hexdigest()})
        journal("request_body", body)
        connection = http.client.HTTPSConnection(url.hostname, url.port or 443,
                                                 timeout=_left(deadline, cancel), context=ssl.create_default_context())
        # http.client ignores ambient HTTP(S)_PROXY, sends to the fixed host and
        # does not follow redirects. Preserve official non-hop identity headers.
        connection.putrequest("POST", url.path, skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", url.netloc)
        for name, value in headers:
            if name.lower() not in HOP_HEADERS | {"host", "authorization", "content-length"}:
                connection.putheader(name, value)
        connection.putheader("Authorization", "Bearer " + upstream["key"])
        connection.putheader("Content-Length", str(len(body)))
        connection.putheader("Connection", "close")
        _left(deadline, cancel)
        connection.endheaders(body)
        transport = connection.sock
        phase = "headers"
        if transport is not None:
            transport.settimeout(_left(deadline, cancel))
        response = connection.getresponse()
        original_headers = response.getheaders()
        journal("response_headers", {"status": response.status, "headers": original_headers})
        response_mode, response_length = validate_framing(original_headers)
        response.chunked = response_mode == "chunked"
        response.length = response_length
        # Deliver decoded transfer payload with connection-close framing. Never
        # let a redirect escape into the worker's own URL resolution machinery.
        refused = 300 <= response.status < 400 or response.status < 200 or any(
            name.lower() == "upgrade" for name, value in original_headers)
        status = 502 if refused else response.status
        forwarded = [(name, value) for name, value in original_headers
                     if name.lower() not in HOP_HEADERS | {"content-length", "location"}]
        on_headers(status, forwarded + [("Connection", "close")])
        phase = "body"

        def consume(chunk):
            nonlocal received
            if not chunk:
                return
            journal("response_body", chunk)
            received += len(chunk)
            digest.update(chunk)
            if not refused:
                on_body(chunk)

        while True:
            remaining = _left(deadline, cancel)
            if transport is not None:
                transport.settimeout(remaining)
            try:
                chunk = response.read1(65536)
            except http.client.IncompleteRead as error:
                consume(error.partial)
                raise
            if not chunk:
                break
            consume(chunk)
        validate_framing(original_headers, received)
        _left(deadline, cancel)
        receipt = {"status": response.status, "bytes": received, "sha256": digest.hexdigest(),
                   "complete": True, "redirect_followed": False, "http_exchanges": 1}
        # This records complete HTTP payload, not a successful owner admission.
        # All potentially blocking journal/close work precedes the final check.
        journal("response_complete", receipt)
        phase = "close"
        response.close()
        response = None
        connection.close()
        connection = None
        _left(deadline, cancel)
        if refused:
            raise GatewayError("upstream redirect or protocol upgrade refused")
        return receipt
    except BaseException as error:
        journal("failed", {"phase": phase, "type": type(error).__name__, "received_bytes": received,
                           "received_sha256": digest.hexdigest(), "complete": False})
        raise GatewayError("isolated gateway exchange failed in " + phase) from None
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            if connection is not None:
                connection.close()
