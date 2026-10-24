"""Exercise the shipped gateway fixture's port publisher at real file barriers."""
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from tests.test_tenant_parent_loss import _GATEWAY


_PORT_BARRIER = r'''
import http.server, socket, sys
from pathlib import Path
data = Path(sys.argv[1])
barrier = socket.socket(fileno=int(sys.argv[3]))
opening, replacing = Path.open, Path.replace
def observed_open(self, *args, **kwargs):
    stream = opening(self, *args, **kwargs)
    mode = args[0] if args else kwargs.get('mode', 'r')
    if self in (data / 'port', data / 'port.tmp') and mode == 'w':
        barrier.sendall(b'O')  # the real file exists; no body has been written
        if barrier.recv(1) != b'W':
            raise RuntimeError('publisher barrier was not released')
    return stream
def observed_replace(self, target):
    result = replacing(self, target)
    if Path(target) == data / 'port':
        barrier.sendall(b'P')  # the actual atomic rename has completed
    return result
Path.open, Path.replace = observed_open, observed_replace
namespace = {'data': data, 'original': http.server.ThreadingHTTPServer}
exec(sys.argv[2], namespace)
server = namespace['server'](('127.0.0.1', 0), http.server.BaseHTTPRequestHandler)
try:
    if barrier.recv(1) != b'C':
        raise RuntimeError('listener barrier was not released')
finally:
    server.server_close()
    barrier.close()
'''


@unittest.skipUnless(os.name == 'posix', 'real inherited socket barrier requires POSIX pass_fds')
class TenantPortPublicationTests(unittest.TestCase):
    def test_port_is_absent_until_complete_atomic_publication(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-tenant-port-publication-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name).resolve()
        # Use the exact function shipped inside the shared fixture, not a
        # reimplementation of its publication algorithm or a fake port value.
        node = next(n for n in ast.parse(_GATEWAY).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'server')
        publisher = ast.get_source_segment(_GATEWAY, node)
        self.assertIsNotNone(publisher)
        self.barrier, child = socket.socketpair()
        self.addCleanup(self.barrier.close)
        self.barrier.settimeout(5)
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-c', _PORT_BARRIER, str(self.data), publisher, str(child.fileno())],
                pass_fds=(child.fileno(),), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        finally:
            child.close()
        self.addCleanup(self.cleanup_process)
        self.assertEqual(self.barrier.recv(1), b'O')
        portfile, temporary = self.data / 'port', self.data / 'port.tmp'
        observation = {'pid': self.proc.pid, 'port_exists_before_body': portfile.exists(),
                       'temporary_exists_before_body': temporary.exists(),
                       'port_bytes_before_body': portfile.read_bytes().hex() if portfile.exists() else None}
        (self.data / 'publication-observation.json').write_text(json.dumps(observation))
        self.assertFalse(portfile.exists(), 'the consumer could observe an empty port before its body was written')
        self.assertEqual(temporary.read_bytes(), b'')
        self.barrier.sendall(b'W')
        self.assertEqual(self.barrier.recv(1), b'P')
        raw = portfile.read_bytes()
        port = int(raw)
        self.assertEqual(raw, str(port).encode('ascii'))
        self.assertGreater(port, 0)
        self.assertLessEqual(port, 65535)
        self.assertFalse(temporary.exists())
        with socket.create_connection(('127.0.0.1', port), timeout=5):
            pass
        observation.update(port_bytes_after_publish=raw.hex(), port=port, listener_connected=True)
        (self.data / 'publication-observation.json').write_text(json.dumps(observation))
        self.barrier.sendall(b'C')
        _, stderr = self.proc.communicate(timeout=5)
        self.assertEqual(self.proc.returncode, 0, stderr)

    def cleanup_process(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
