from tests.test_external_candidates import ExternalCandidateTest
from tmh.platform import login,reform
from tmh.platform.server import make_handler
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import json
f=ExternalCandidateTest(); f.setUp(); P=f.P
login.set_user(P.data_dir,'scenario-owner','isolated-scenario-fixture')
atlas={'built':'fixture','domains':[{'id':'sales','title':'销售','tables':1}]}
p=reform.create(P.data_dir,'EXT',atlas,dict(title='历史销售场景',goal='保留原始规则并补齐验证',wave=2,scenario={'sources':[{'id':'policy','kind':'policy','reference':'fixture://refund-policy','version':'v2'}],'rules':['退款必须为1250分'],'regressions':['原分页与权限保持'],'environment_gaps':['尚未运行该任务的业务测试']}),'historical-creator')
with reform._transaction(P.data_dir,P.store) as db:
 ps=reform._load(P.data_dir,'EXT',db);ps[0]['items'][0]['ticket']=f.ticket['key'];reform._save(P.data_dir,'EXT',ps,db)
P.store.update_ticket(f.ticket['id'],'fixture',links={'reform':{'plan':p['id'],'order':1}})
P.store.add_project('OTHER','另一个项目',str(f.repo))
patcher=patch.object(P.kb,'atlas',return_value=atlas);patcher.start()
http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(P))
print(json.dumps({'url':'http://127.0.0.1:'+str(http.server_port)+'/#/projects/EXT/reforms/'+p['id'],'data':str(P.data_dir),'sha':f.sha},ensure_ascii=False),flush=True)
http.serve_forever()
