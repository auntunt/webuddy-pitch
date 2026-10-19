"""Isolated actual platform; fault injection drops one committed comment response."""
import json, os, socket, sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from tmh.platform.server import Platform, make_handler
root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
(root/'autoflow.json').write_text(json.dumps({'on':False,'plan':False,'merge':'off','preview':'off'}))
P=Platform(root, user='草稿验收员', brand='Webuddy · 草稿隔离验收')
if not P.store.projects():
    pr=root/'project'; pr.mkdir(exist_ok=True)
    project=P.store.add_project('DRAFT','沟通草稿验收',str(pr))
    for title in ('全页刷新与发送重试','另一张工单的独立草稿'):
        P.store.create_ticket(project['id'],title,author='合成夹具',body='本地隔离验收，不触发模型或客户签收。')
Base=make_handler(P)
class H(Base):
    def _json(self, code, obj):
        flag=root/'drop-next-comment-response'
        if self.command=='POST' and self.path.endswith('/comments') and code==200 and flag.exists():
            flag.rename(root/'response-dropped-after-commit')
            print('dropped committed response',self.path,flush=True)
            self.close_connection=True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        super()._json(code,obj)
server=ThreadingHTTPServer(('127.0.0.1',8797),H)
print(json.dumps({'pid':os.getpid(),'data':str(root),'port':8797}),flush=True)
server.serve_forever()
