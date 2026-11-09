"""Loopback-only preview of a verified, separately retained ERP distribution."""
import argparse
from functools import partial
from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('dist', type=Path)
args = parser.parse_args()
assert (args.dist / 'index.html').is_file()

class Handler(SimpleHTTPRequestHandler):
    def proxy(self):
        connection = HTTPConnection('127.0.0.1', 19998, timeout=30)
        try:
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            connection.request(self.command, self.path, body, dict(self.headers))
            response = connection.getresponse(); raw = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        finally:
            connection.close()
    def do_GET(self):
        if self.path.startswith('/jshERP-boot/'): self.proxy()
        else: super().do_GET()
    def do_POST(self): self.proxy()
    def do_PUT(self): self.proxy()
    def do_DELETE(self): self.proxy()

ThreadingHTTPServer(('127.0.0.1', 18981), partial(Handler, directory=str(args.dist.resolve()))).serve_forever()
