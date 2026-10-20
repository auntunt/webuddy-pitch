from pathlib import Path
import json, sys, threading, time
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_preview_health_flow import call
from tmh.platform import preview, server
out=Path(__file__).resolve().parent
folder=out/'live'
folder.mkdir(exist_ok=True)
assert (folder/'platform.db').exists(), 'Only reuse the prepared local fixture'
(folder/'autoflow.json').write_text('{"on":false,"preview":"off"}')
P=server.Platform(folder,'隔离健康验收',brand='Webuddy · 预览健康验收夹具')
P.preview_port=8799
P.public_url='http://127.0.0.1:8798'
fixture=json.loads((out/'live-fixture.json').read_text())
call(P,'candidate_preview',{'candidate_id':fixture['candidate']['candidate_id'],'request_id':'health-preview-ui-refresh'})
deadline=time.monotonic()+10
while preview.status(P.data_dir,'HP-1').get('state')!='up':
 assert time.monotonic()<deadline, 'Preview startup deadline exceeded'
 time.sleep(.05)
servers=[ThreadingHTTPServer(('127.0.0.1',8798),server.make_handler(P)),ThreadingHTTPServer(('127.0.0.1',8799),server.make_preview_handler(P))]
for srv in servers:
 threading.Thread(target=srv.serve_forever,daemon=True).start()
print(json.dumps({'url':'http://127.0.0.1:8798/#/t/HP-1','candidate':fixture['candidate']['candidate_id'],'preview':preview.status(P.data_dir,'HP-1')},ensure_ascii=False),flush=True)
try:
 threading.Event().wait()
except KeyboardInterrupt:
 pass
finally:
 for srv in servers:
  srv.shutdown();srv.server_close()
 preview.stop(P,'HP-1')
 P.store.db.close()
