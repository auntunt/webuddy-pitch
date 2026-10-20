import asyncio,json,tomllib
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2]
async def main():
 cfg=tomllib.loads((ROOT/'data/agent-client-configs/external-candidates/codex.toml').read_text())['mcp_servers']['webuddy']
 async with stdio_client(StdioServerParameters(command=cfg['command'],args=cfg['args'],cwd='/tmp')) as (read,write):
  async with ClientSession(read,write) as session:
   await session.initialize();names=[t.name for t in (await session.list_tools()).tools]; assert len(names)==22 and 'webuddy_candidate_submit' in names and 'webuddy_candidate_decide' not in names
   reply=await session.call_tool('webuddy_candidate_get',{'candidate_id':1});assert not reply.isError;v=reply.structuredContent;assert v['ready_for_human'] and not v['human_accepted']
   result={'tools':names,'actual_generated_config_started':True,'candidate_id':v['id'],'commit':v['commit'],'state':v['state'],'preview_url':v['preview_url'],'evidence_hash':v['evidence_hash'],'human_accepted':v['human_accepted'],'scope':'Official SDK using generated Codex config; not a claim of Codex product session write approval'}
   (ROOT/'data/external-delivery-20261019/execution-config-protocol.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Generated execution config: 22 tools, fixed candidate read, no human decision tool.')
asyncio.run(main())
