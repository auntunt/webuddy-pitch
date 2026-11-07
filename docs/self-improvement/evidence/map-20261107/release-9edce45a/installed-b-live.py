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
   listed=await s.list_tools();names={t.name for t in listed.tools}
   assert {'webuddy_map_get','webuddy_maps_list','webuddy_map_create'}.issubset(names)
   projects=await call('projects_list',{})
   count=0
   for project in projects['items']:
    maps=await call('maps_list',{'project':project['key']})
    assert 'items' in maps and 'next_after' in maps
    count+=1
   intent=json.loads((out/'intent.json').read_text());m=json.loads((out/'manifest.json').read_text())
   base={'project':intent['project'],'plan_id':intent['plan_id'],'export_id':m['export_id']}
   assert await call('reform_report_get',base)==m
   proof=await call('reform_report_get',dict(base,file='report.md',offset=0))
   assert hashlib.sha256(base64.b64decode(proof['data_base64'])).hexdigest()==proof['sha256']
   print('INSTALLED_B_CLIENT_REAL_TENANT',count,'authorized projects; map listing and old frozen report identity/hash passed',flush=True)
   print('No task dispatched, no human decision; map creation/source covered in isolated SDK and browser',flush=True)
asyncio.run(main())
