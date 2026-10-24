"""Fixed one-request Messages transport. Private stdin; framed raw stdout.

No CLI commands, model tools, redirects, proxies, retries or response execution.
This child MUST only be started by the server-owned provider_adapter supervisor.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit


VERSION = "messages-text-transport-v1"


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
        while True:
            try:
                chunk = response.read1(65536)
            except http.client.IncompleteRead as exc:
                sys.stdout.buffer.write(exc.partial)
                sys.stdout.buffer.flush()
                raise
            if not chunk:
                if response.length not in (None, 0):
                    raise ValueError("incomplete Content-Length")
                break
            # Preserve every received byte even if the declared resource cap is
            # crossed; stop rather than ever claim this partial response complete.
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            request["response_bytes"] = request.get("response_bytes", 0) + len(chunk)
            if request["response_bytes"] > request["max_response_bytes"]:
                raise ValueError("response resource cap exceeded")
        return 0
    except BaseException:
        # Exceptions/headers can include credentials; raw errors are not exported.
        return 70
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
