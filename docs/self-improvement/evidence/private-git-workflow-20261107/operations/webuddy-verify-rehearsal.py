import asyncio,json,os,sys,tempfile
from datetime import timedelta
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from tmh.platform import project_ci
root=Path('/Users/auntlee/Desktop/workspace/运维智能体/部署包/jenkins-erp-demo-20261106')
out=root/'proof/git-workflow-20261107';state=json.loads((out/'state.json').read_text())
accounts=json.loads((root/'private/accounts.json').read_text())
os.environ.update(DEMO_JENKINS_USER=accounts['reader_user'],DEMO_JENKINS_TOKEN=(root/'jenkins/secrets/webuddy-demo/reader-token').read_text().strip(),SSL_CERT_FILE=str(root/'private/ca.crt'))
checks={v:project_ci.check(root/'platform-ci','ERP',state[v]) for v in ('baseline','candidate')}
assert checks['baseline']['state']!='pass',checks['baseline']
assert checks['candidate']['state']=='pass',checks['candidate']
checks['missing']=project_ci.check(root/'platform-ci','ERP','0'*40)
assert checks['missing']['state']!='pass'
(out/'platform-ci.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
async def main():
 config=json.loads((root/'private/git-workflow-mcp.json').read_text())['mcpServers']['webuddy-git-rehearsal']
 params=StdioServerParameters(command=config['command'],args=config['args'],cwd=str(Path.cwd()))
 with tempfile.TemporaryFile(mode='w+') as errors:
  async with stdio_client(params,errlog=errors) as (read,write):
   async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as client:
    await client.initialize();tools={v.name for v in (await client.list_tools()).tools}
    assert 'webuddy_delivery_get' in tools and 'webuddy_candidate_submit' not in tools
    r=await client.call_tool('webuddy_delivery_get',{'ticket':'ERP-1'});assert not r.isError, r
    packet=r.structuredContent
    assert packet['ready_to_merge'] is None and packet['current_validity']=='not_checked'
    assert packet['development']['state']=='clarifying' and len(packet['runs'])==2
    outputs=[json.loads(x['run']['output']) for x in packet['runs']]
    shas={o['build']['source'].split(':')[0] for o in outputs}
    assert shas=={state['baseline'],state['candidate']},shas
    (out/'mcp-delivery.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
    web=json.loads((out/'webuddy-browser/ERP-1-delivery.json').read_text())
    for key in ('development','runs','ready_to_merge','current_validity'):assert packet[key]==web[key],key
    dev=await client.call_tool('webuddy_development_get',{'ticket':'ERP-1'});assert not dev.isError
    assert dev.structuredContent['state']=='clarifying'
    (out/'checks.json').write_text(json.dumps({'ci':{k:v['state'] for k,v in checks.items()},'same_web_mcp_evidence':True,'mcp_read_only':True,'requirement_confirmed':False,'human_approved':False,'business_accepted':False},indent=2))
    print('REAL_JENKINS_EXACT_SHA_AND_WEB_MCP_MATCH; synthetic read-only connection; no human decisions')
asyncio.run(main())
