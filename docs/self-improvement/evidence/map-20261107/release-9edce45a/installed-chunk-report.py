import asyncio,json,tomllib,os,hashlib,base64
from pathlib import Path
from datetime import timedelta
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
os.umask(0o077)
out=Path('/private/tmp/webuddy-map-20261107/private-report');out.mkdir(exist_ok=True)
async def main():
 cfg=tomllib.loads((Path.home()/'.codex/config.toml').read_text())['mcp_servers']['webuddy']
 params=StdioServerParameters(command=cfg['command'],args=['/private/tmp/scenario-known-test-host.py',*cfg['args']],env={**os.environ,**cfg.get('env',{})})
 async with stdio_client(params) as (read,write):
  async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=75)) as s:
   await s.initialize()
   async def call(name,args):
    r=await s.call_tool('webuddy_'+name,args)
    if r.isError:raise RuntimeError('Tool failed: '+name+' '+str(r.content))
    return r.structuredContent or json.loads(next(c.text for c in r.content if c.type=='text'))
   if (out/'intent.json').exists(): intent=json.loads((out/'intent.json').read_text())
   else:
    projects=await call('projects_list',{})
    intent=None
    for p in projects['items']:
     plans=await call('reforms_list',{'project':p['key']})
     if plans['items']:
      plan=plans['items'][0]
      detail=await call('reform_get',{'project':p['key'],'plan_id':plan['id']})
      intent={'project':p['key'],'plan_id':plan['id'],'expected_revision':detail['revision'],'request_id':'a-report-installed-sdk-20261107-01'};break
    assert intent
    (out/'intent.json').write_text(json.dumps(intent))
   m=await call('reform_report_create',intent)
   (out/'manifest.json').write_text(json.dumps(m))
   print('FROZEN',m['export_id'],'files',len(m['files']),'bytes',sum(f['bytes'] for f in m['files']),flush=True)
   base={'project':intent['project'],'plan_id':intent['plan_id'],'export_id':m['export_id']}
   completed=[]
   for f in m['files']:
    path=out/f['name'];offset=path.stat().st_size if path.exists() else 0
    if offset and offset!=f['bytes'] and offset%m['chunk_bytes']:raise ValueError('partial length')
    if offset:
     saved=path.read_bytes()
     for i in range(0,len(saved),m['chunk_bytes']):assert hashlib.sha256(saved[i:i+m['chunk_bytes']]).hexdigest()==f['chunk_sha256'][i//m['chunk_bytes']]
     print('RESUME',f['name'],offset,flush=True)
    with path.open('ab') as stream:
     while offset<f['bytes']:
      chunk=await call('reform_report_get',dict(base,file=f['name'],offset=offset))
      b=base64.b64decode(chunk['data_base64']);assert chunk['export_id']==m['export_id'] and chunk['offset']==offset
      assert hashlib.sha256(b).hexdigest()==chunk['sha256']==f['chunk_sha256'][offset//m['chunk_bytes']]
      stream.write(b);stream.flush();offset+=len(b)
      if os.environ.get('STOP_AFTER_FIRST') and len(completed)==0:print('INTERRUPTED_AFTER_SAVED_CHUNK',offset,flush=True);return
    assert offset==f['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
    completed.append({k:f[k] for k in ('name','bytes','sha256')});print('FILE_VERIFIED',f['name'],offset,flush=True)
   assert await call('reform_report_get',base)==m
   receipt={'installed_sdk':True,'real_test_network':True,'export_id':m['export_id'],'files':completed,'total_bytes':sum(f['bytes'] for f in m['files']),'all_hashes_verified':True,'actual_host_write':False}
   (out.parent/'installed-report-receipt.json').write_text(json.dumps(receipt,indent=2));print('COMPLETE_VERIFIED',receipt['total_bytes'],flush=True)
asyncio.run(main())
