"""Bind completed browser observations to the unchanged verified candidate."""
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BEFORE = json.loads((OUT/'candidate-before.json').read_text())
RESULTS = json.loads((ROOT/'data/weighbill-pilot-20261019/assessment-results.json').read_text())
for result in RESULTS:
    result['evidence'] = '前轮同版本证据：docs/self-improvement/evidence/weighbill-pilot-2026-10-19/。' + result['evidence']
    if result['id'] == 'A3':
        result.update(status='pass', evidence='本轮真实浏览器续跑同SHA：恢复时DOM明确显示已核对v1，完整A草稿和B重量保持；点击保存后真实记录v2/history2、净重900和完整货名备注；单独审核后v3/history3 approved。B旧页审核被拒，完整HTTP/SQLite前后快照相等。刷新已审核台账仍可读到同一内容，打开原图成功。browser-timeline.json、browser-approved.jpg、business-checks.json及独立复核见docs/self-improvement/evidence/weighbill-acceptance-2026-10-19/。前轮冲突/草稿原始证据保留；恢复原因未知，不推断人工处理情况，不称全程无人值守。')
    elif result['id'] == 'A4':
        result['evidence'] += ' 本轮业务源码无修改，沿用同SHA的operation4完整应用回归（不是新跑251项）；本轮重新核对原102跟踪文件/253本地文件和既有平台行相等，BOOTV2原验收不变，两条未操作的合成记录完整保持，三个原图SHA/字节保持。'
    elif result['id'] == 'A5':
        result['evidence'] = '完整SHA预览8791→8793保持，真实页面完成保存/审核/刷新，并在新标签打开原图（860×1100）；原始截图和HTTP/SQLite及精确版本证据已保存。本轮官方MCP重新读取当前候选、绑定同verification_hash/preview_hash写全部技术观察，再由CLI读取。源码/验证/预览身份不变，未调用人工批准工具。'

NOTE = ('接续真实外部Codex实现的ab9601e305bf9efdf908554174c56ca101194405，不重新生成或登记候选。'
        '前轮A3 unknown历史保持；本轮由协调者完成实际浏览器保存、审核、旧页拒绝、刷新与原图查看，独立子代理复核真实数据及证据。'
        '确认框本轮已不再阻塞，但恢复原因未知，不能声称全程无人值守。页面内合成记录approved不等于项目用户验收。'
        '本条只是独立技术观察，human_accepted必须保持false；没有合并、推送或部署。'
        '本轮证据目录docs/self-improvement/evidence/weighbill-acceptance-2026-10-19/。')

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT/'tmh/workbench_entry.py'),'mcp','--endpoint','http://127.0.0.1:8791','--agent','codex-acceptance'], cwd='/tmp')
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert 'webuddy_candidate_assess' in names and 'webuddy_candidate_decide' not in names
            before = await session.call_tool('webuddy_candidate_get', {'candidate_id':4})
            assert not before.isError
            v = before.structuredContent
            for field in ['commit','requirement_hash','verification_hash','preview_hash']:
                assert v[field] == BEFORE[field], (field, 'source changed; re-evaluation required')
            assert v['commit'] == 'ab9601e305bf9efdf908554174c56ca101194405'
            assert v['current'] and v['verification_passed'] and v['preview_ready'] and not v['human_accepted']
            (OUT/'mcp-before-acceptance.json').write_text(json.dumps(before.model_dump(mode='json'),ensure_ascii=False,indent=2)+'\n')
            reply = await session.call_tool('webuddy_candidate_assess', {'candidate_id':4,'verification_hash':v['verification_hash'],'preview_hash':v['preview_hash'],
                'results':RESULTS,'note':NOTE,'request_id':'weighbill-ab9601e-complete-browser-acceptance-20261019'})
            (OUT/'mcp-technical-acceptance.json').write_text(json.dumps(reply.model_dump(mode='json'),ensure_ascii=False,indent=2)+'\n')
            assert not reply.isError, reply
            current = reply.structuredContent
            assert current['technical_acceptance'] and current['ready_for_human'] and not current['human_accepted']
            (OUT/'mcp-live-tools.json').write_text(json.dumps(names,indent=2)+'\n')
            (OUT/'assessment-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2)+'\n')
            (OUT/'assessment-note.txt').write_text(NOTE+'\n')
            print(json.dumps({k:current[k] for k in ['id','state','verification_passed','preview_ready','technical_acceptance','ready_for_human','human_accepted','preview_url','evidence_hash']},ensure_ascii=False,indent=2))

asyncio.run(main())
