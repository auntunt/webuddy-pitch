import asyncio,json,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
phase=sys.argv[1]
async def main():
 params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'tmh/workbench_entry.py'),'mcp','--endpoint','http://127.0.0.1:8798','--agent','health-reader','--read-only'],cwd='/tmp')
 async with stdio_client(params) as (reader,writer):
  async with ClientSession(reader,writer) as session:
   init=await session.initialize()
   for tool,args in [('webuddy_candidate_get',{'candidate_id':1}),('webuddy_preview_get',{'ticket':'HP-1'})]:
    r=await session.call_tool(tool,args)
    (OUT/('mcp-'+phase+'-'+tool+'.json')).write_text(json.dumps(r.model_dump(mode='json'),ensure_ascii=False,indent=2)+'\n')
    assert not r.isError
    payload=r.structuredContent
    if tool=='webuddy_candidate_get':
     assert payload['preview_ready']==(phase!='failed')
     print(json.dumps({'phase':phase,'preview_ready':payload['preview_ready'],'preview_health':payload['preview']['health'],'human_accepted':payload['human_accepted']},ensure_ascii=False))
asyncio.run(main())
