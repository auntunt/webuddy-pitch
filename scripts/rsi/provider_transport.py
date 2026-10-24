"""Fixed one-request Messages transport. Private stdin; framed raw stdout.

No CLI commands, model tools, redirects, proxies, retries or response execution.
This child MUST only be started by the server-owned provider_adapter supervisor.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit


VERSION = "messages-text-transport-v1"


class FramingError(ValueError):
    """Original response headers/body cannot establish complete HTTP framing."""


def validate_framing(headers, body_bytes=None):
    """RFC 9112 6.3, with strict single-chunked/no-TE+CL adapter policy.

    Parse every original field, including comma lists. Never use the standard
    library's permissive integer/first-header normalization as the evidence.
    """
    if not isinstance(headers, list):
        raise FramingError("original response headers required")
    lengths, transfers = [], []
    for pair in headers:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise FramingError("original header pair required")
        name, value = pair
        if (not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                or not isinstance(value, str) or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value)):
            raise FramingError("unsupported original header syntax")
        if name.lower() == "content-length":
            for item in value.split(","):
                decimal = item.strip(" \t")
                if not re.fullmatch(r"[0-9]+", decimal):
                    raise FramingError("Content-Length must contain ASCII decimals")
                lengths.append(decimal.lstrip("0") or "0")
        elif name.lower() == "transfer-encoding":
            transfers.extend(item.strip(" \t").lower() for item in value.split(","))
    if transfers:
        if lengths or transfers != ["chunked"]:
            raise FramingError("only single chunked without Content-Length is supported")
        mode, length = "chunked", None
    elif lengths:
        if any(value != lengths[0] for value in lengths) or len(lengths[0]) > 19:
            raise FramingError("contradictory or unsupported Content-Length")
        length = int(lengths[0])
        if length > 2 ** 63 - 1:
            raise FramingError("Content-Length exceeds resource representation")
        mode = "length"
    else:
        mode, length = "close", None
    if body_bytes is not None:
        if type(body_bytes) is not int or body_bytes < 0 or mode == "length" and body_bytes != length:
            raise FramingError("received body does not match original Content-Length")
    return mode, length


def main():
    connection = None
    try:
        request = json.load(sys.stdin)
        url = urlsplit(request["endpoint"])
        if (url.username or url.password or url.query or url.fragment or not url.hostname
                or url.path != "/v1/messages"):
            raise ValueError("fixed Messages endpoint required")
        body = base64.b64decode(request["body"], validate=True)
        key = request["credential"]
        if not isinstance(key, str) or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("invalid credential format")
        if url.scheme == "https":
            connection = http.client.HTTPSConnection(url.hostname, url.port, context=ssl.create_default_context())
        elif request["fixture"] is True and url.scheme == "http" and url.hostname == "127.0.0.1":
            connection = http.client.HTTPConnection(url.hostname, url.port)
        else:
            raise ValueError("HTTPS required")
        # Direct http.client deliberately ignores ambient proxy variables.
        connection.request("POST", url.path, body=body, headers={"Content-Type": "application/json",
                           "x-api-key": key, "anthropic-version": "2023-06-01"})
        response = connection.getresponse()
        metadata = {"schema": VERSION, "status": response.status, "headers": response.getheaders(),
                    "request_sha256": hashlib.sha256(body).hexdigest(),
                    "transport_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        sys.stdout.buffer.write(json.dumps(metadata, separators=(",", ":")).encode() + b"\n")
        sys.stdout.buffer.flush()
        invalid_framing = False
        try:
            mode, length = validate_framing(metadata["headers"])
        except FramingError:
            # Retain the body of this unusable response up to the SAME resource
            # cap/deadline; no connection reuse, retries or JSON settlement.
            invalid_framing, mode, length = True, "invalid", None
        response.length = length
        response.chunked = mode == "chunked"
        received_bytes = 0
        while True:
            try:
                chunk = response.read1(65536)
            except http.client.IncompleteRead as exc:
                sys.stdout.buffer.write(exc.partial)
                sys.stdout.buffer.flush()
                raise
            if not chunk:
                if invalid_framing or response.length not in (None, 0):
                    raise ValueError("incomplete Content-Length")
                break
            # Preserve every received byte even if the declared resource cap is
            # crossed; stop rather than ever claim this partial response complete.
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            received_bytes += len(chunk)
            if received_bytes > request["max_response_bytes"]:
                raise ValueError("response resource cap exceeded")
        validate_framing(metadata["headers"], received_bytes)
        return 0
    except BaseException:
        # Exceptions/headers can include credentials; raw errors are not exported.
        return 70
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
