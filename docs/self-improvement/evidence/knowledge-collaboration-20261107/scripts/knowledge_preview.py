import json, signal
from pathlib import Path
from test_tenant_gateway import TenantGatewayTest
from tmh.platform import project_library as library
from tmh.platform.store import Store
f=TenantGatewayTest();f.setUp()
try:
 root=Path(f.reg.one('SELECT path FROM tenants WHERE id=?',(f.a,))['path'])
 for name in ('same','private'):
  folder=root/'repositories'/name/'.tmh'/'knowledge';folder.mkdir(parents=True)
  (folder/'decisions.md').write_text('- 退款规则：金额保留两位小数；'+('可访问项目' if name=='same' else '不可访问的内部规则')+'。\n')
 store=Store(root/'platform.db');library.schema(store)
 source=store.project('PRIVATE');target=store.project('SAME')
 sid=library.source(store,source,str(root/'repositories'/'private'),'合成来源')
 for i in (1,2):
  store.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author) VALUES(?,?,?,?,?,?,'ready','complete',?,?)",(f'demo-revision-{i}',source['id'],sid['id'] if isinstance(sid,dict) else sid,str(i)*40,source['root'],'synthetic','2026-11-07','synthetic-fixture'))
 library.grant(store,source,'SAME',[],'synthetic-fixture')
 # Synthetic metadata to inspect update UI, not evidence of a real build.
 store.x('INSERT INTO knowledge_references(project_id,revision_id,scopes,purpose,created,author) VALUES(?,?,?,?,?,?)',(target['id'],'demo-revision-1','[]','演示固定引用的更新提示','2026-11-07','synthetic-fixture'))
 store.db.close()
 Path('/private/tmp/knowledge-preview-info.json').write_text(json.dumps({'port':f.port,'tenant':f.a}))
 print('READY',f.port,f.a,flush=True)
 signal.pause()
finally:f.doCleanups()
