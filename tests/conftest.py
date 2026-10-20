# Tests never hand clients' words to whatever coding agent happens to be installed on the machine: understanding by
# an agent is switched on per test, with a stand-in agent (tests/test_understand.py).
import os
import urllib.request

os.environ.setdefault("TMH_UNDERSTAND", "rules")

# Test HTTP servers bind 127.0.0.1, but on a Windows dev box urllib reads the *system* proxy from the registry and
# does not bypass loopback by default (urllib.request.proxy_bypass("127.0.0.1") == 0). Loopback requests then leave
# the machine, the proxy drops them, and tests fail with http.client.RemoteDisconnected before reaching the server.
# Bypass the proxy for loopback only: the tests still make real HTTP requests to the real servers, and every other
# host keeps the machine's configured proxy behaviour.
_LOOPBACK_PREFIXES = ("127.", "localhost", "[::1]", "::1")
_original_proxy_bypass = urllib.request.proxy_bypass


def _loopback_proxy_bypass(host):
    if host and host.strip().lower().startswith(_LOOPBACK_PREFIXES):
        return True
    return _original_proxy_bypass(host)


urllib.request.proxy_bypass = _loopback_proxy_bypass

# Child processes spawned by tests (python -m tmh ...) inherit the environment, not this module-level patch.
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")
