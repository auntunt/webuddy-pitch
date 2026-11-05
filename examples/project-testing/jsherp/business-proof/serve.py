from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from http.client import HTTPConnection
from functools import partial
class Handler(SimpleHTTPRequestHandler):
 def proxy(self):
  conn=HTTPConnection('127.0.0.1',19999,timeout=30)
  body=self.rfile.read(int(self.headers.get('Content-Length','0')))
  conn.request(self.command,self.path,body,dict(self.headers));r=conn.getresponse();raw=r.read()
  self.send_response(r.status)
  for k,v in r.getheaders():
   if k.lower() not in ('transfer-encoding','connection','content-length'):self.send_header(k,v)
  self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);conn.close()
 def do_GET(self):
  if self.path.startswith('/jshERP-boot/'):self.proxy()
  else:super().do_GET()
 def do_POST(self):self.proxy()
 def do_PUT(self):self.proxy()
 def do_DELETE(self):self.proxy()
ThreadingHTTPServer(('127.0.0.1',18980),partial(Handler,directory='jshERP-web/dist')).serve_forever()
