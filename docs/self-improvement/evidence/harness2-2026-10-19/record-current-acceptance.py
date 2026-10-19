"""Attach new technical observations; transcribe the user's existing exact-version approval."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tmh.workbench_client import Client
from tmh.platform.operator_access import read_key
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/harness2-integration-20261019'
SHA='8b6cb6da908fc7bdcb585789a1b8f2ce78569ffd'

def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

async def main():
    previous=json.loads((OUT/'cli-before-probe.json').read_text())
    probe=json.loads((OUT/'cli-probe-report.json').read_text())
    assert previous['human_accepted'] and previous['commit']==SHA and probe['passed']
    assert probe['source']['commit']==SHA
    assert all(c['status']=='pass' for c in probe['result']['arms']['candidate']['results'])
    results=[dict(r,evidence=r['evidence']+'\n新增维护者配方 bootv2-items-search-v1、实验 #1 对固定候选执行该标准的实际 HTTP/SQLite 检查通过；配方版本 '+probe['source']['recipe']['version']+'。完整证据 data/product-workbench/harness-probes/1/；基线 A1/A2/A3 失败、候选四项通过，停止回执完整。原应用代码未变，服务更新后浏览器读取三条原事项；本轮记录 docs/self-improvement/verification-harness2-2026-10-19.md。') for r in previous['assessment']['results']]
    note='协调验收会话已读取真实 CLI/MCP 探测、浏览器及数据库观察，并引用独立子代理 9 项边界复核。新增配方使旧技术观察哈希失效，本条重新绑定完整证据；仍为技术验收，用户确认单独记录。未启动新模型、未合并或部署。'
    params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'tmh/workbench_entry.py'),'mcp','--endpoint','http://127.0.0.1:8791','--agent','codex-harness-review'],cwd='/tmp')
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            reply=await session.call_tool('webuddy_candidate_get',{'candidate_id':1})
            assert not reply.isError
            state=reply.structuredContent
            assert state['commit']==SHA and state['current'] and state['preview_ready'] and state['harness_probe']['passed']
            assert state['criteria']==previous['criteria']
            assessed=await session.call_tool('webuddy_candidate_assess',{'candidate_id':1,'verification_hash':state['verification_hash'],'preview_hash':state['preview_hash'],'results':results,'note':note,'request_id':'bootv2-harness-assessment-20261019-001'})
            save('mcp-current-assessment.json',assessed.model_dump(mode='json'))
            assert not assessed.isError
            current=assessed.structuredContent
            assert current['ready_for_human'] and current['technical_acceptance']
    client=Client(operator=True,operator_token=read_key(ROOT/'data/product-workbench/operator-approval.key'))
    current=client.call('candidate_get',{'candidate_id':1})
    assert current['commit']==SHA and current['criteria']==previous['criteria'] and current['ready_for_human']
    accepted=client.call('candidate_decide',{'candidate_id':1,'evidence_hash':current['evidence_hash'],'decision':'accept','note':'用户在当前聊天对 BOOTV2 搜索与状态筛选明确回复“确认本地验收”（原记录 operator-bootv2-search-chat-20261019）。协调者据此转录同一完整提交 8b6cb6da908fc7bdcb585789a1b8f2ce78569ffd 的确认；本次只增加已通过的独立探测证据，应用代码和验收条件均未改变。真实 HTTP/SQLite、固定预览与原数据已核对；不是新增用户答复，不扩展为合并或发布授权。','request_id':'operator-bootv2-search-harness-evidence-20261019'})
    save('user-local-acceptance-current.json',accepted)
    assert accepted['human_accepted'] and accepted['state']=='accepted'
    print(json.dumps({k:accepted[k] for k in ('id','commit','state','technical_acceptance','human_accepted','evidence_hash')},ensure_ascii=False))
asyncio.run(main())
