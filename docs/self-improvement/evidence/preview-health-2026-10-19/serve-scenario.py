from pathlib import Path
import json, sys, threading
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_preview_health_flow import prepare
from tmh.platform import preview, server
out=Path(__file__).resolve().parent
folder=out/'live'
folder.mkdir(exist_ok=True)
assert not (folder/'platform.db').exists(), 'Refuse to duplicate the prepared scenario'
(folder/'autoflow.json').write_text('{"on":false,"preview":"off"}')
P=server.Platform(folder,'隔离健康验收',brand='Webuddy · 预览健康验收夹具')
P.preview_port=8799
P.public_url='http://127.0.0.1:8798'
fixture=prepare(P)
(out/'live-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
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
