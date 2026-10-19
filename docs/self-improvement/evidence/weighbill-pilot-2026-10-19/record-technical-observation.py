"""Record actual partial observations, never turn an incomplete browser run green."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
COMMIT = 'ab9601e305bf9efdf908554174c56ca101194405'
RESULTS = [
    {'id': 'A1', 'status': 'pass', 'evidence': '独立真实 HTTP/SQLite：旧版本保存 409 且记录/版本/history 不变；模拟客户端未接收已提交 ACK 后，旧条件重放不能覆盖 B 后续更改；明确核对后可保存。两个实例 CAS 只有一个成功。基线显式条件协议 2/9，候选 10/10，详见 independent-candidate/REVIEW-FINAL.md 与完整 API 请求响应。真实浏览器 A 旧草稿保存被拒绝，preview-after-b-save.json 与 preview-after-a-conflict.json 完全相等。'},
    {'id': 'A2', 'status': 'pass', 'evidence': '独立 API 验证旧版本审核跳过、混合批次部分成功、不改变失败项及历史、修改已审核记录要求重审；真实发货页面函数独立 8/8，审核绑定 PATCH 成功返回版本，失败不跳下一条或报成功。这些 API/控制函数结果不替代 A3 的真实浏览器后半段。'},
    {'id': 'A3', 'status': 'unknown', 'evidence': '真实双页面已执行 B 保存 10900/900、A 旧全量草稿 409、完整货名/备注草稿保留，并在比较表选择采用 B 新重量。点击“已核对”后原生确认框使 IAB 控制超时；getJsDialog 返回 undefined，后续 DOM/键盘/关闭均超时。不能宣称实际浏览器完成核对后的保存和审核。用户手动处理确认框的请求待答复。见 browser-timeline.json、browser-conflict.jpg、preview-after-a-conflict.json。独立控制函数 8/8 只是补充证据。'},
    {'id': 'A4', 'status': 'pass', 'evidence': '最终候选平台独立构建通过、应用 251 passed / 11 skipped / 2 dependency warnings；跳过明确为未配置真实 S3/OceanBase，未声称这些集成验证。原权限/来源/原图及 Excel 原编码回归通过；原仓库 102 个跟踪文件、253 个本地文件及原 Git 状态不变，原平台各表既有行不变。preservation-report.json 全部 true；显式非法版本拒绝，省略版本旧 API 仍兼容且不受客户端条件保护。'},
    {'id': 'A5', 'status': 'pass', 'evidence': '固定完整 SHA 的授权入口经 8791→8793 实际进入采集/台账页，真实页面读取与 B 保存成功；完整前缀 3 张原图实际 HTTP 200，字节与 SHA256 均等于生成原图，已打开渲染。独立检查前缀静态/历史/CSV、跨站拒绝及预览重启。官方 MCP 读取当前候选并记录本条部分技术观察，CLI 可读完整版本/验证/预览与缺项；A3 未完成，不能最终签收。'},
]
NOTE = ('外部 Codex 是主要实现者，协调者提供隔离预览启动器并修复独立复核发现的迟到读取竞态。'
        '独立子代理 /root/candidate_chain_review 复核最终源码；本条由协调者记录实际浏览器与保留性观察。'
        'A3 的浏览器后半段未知，技术验收与人工验收必须保持 false。'
        '合成数据预览关闭真实 OCR；未合入原仓库、未推送、未部署。'
        '完整证据归档 docs/self-improvement/evidence/weighbill-pilot-2026-10-19/。')

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT/'tmh/workbench_entry.py'), 'mcp', '--endpoint', 'http://127.0.0.1:8791', '--agent', 'codex-acceptance'], cwd='/tmp')
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert 'webuddy_candidate_assess' in names and 'webuddy_candidate_decide' not in names
            before = await session.call_tool('webuddy_candidate_get', {'candidate_id': 4})
            assert not before.isError
            v = before.structuredContent
            assert v['commit'] == COMMIT and v['current'] and v['preview_ready'] and v['verification_passed']
            (OUT/'mcp-before-observation.json').write_text(json.dumps(before.model_dump(mode='json'), ensure_ascii=False, indent=2)+'\n')
            reply = await session.call_tool('webuddy_candidate_assess', {
                'candidate_id': 4, 'verification_hash': v['verification_hash'], 'preview_hash': v['preview_hash'],
                'results': RESULTS, 'note': NOTE, 'request_id': 'weighbill-ab9601e-partial-browser-observation-20261019'})
            (OUT/'mcp-technical-observation.json').write_text(json.dumps(reply.model_dump(mode='json'), ensure_ascii=False, indent=2)+'\n')
            assert not reply.isError, reply
            current = reply.structuredContent
            assert not current['technical_acceptance'] and not current['ready_for_human'] and not current['human_accepted']
            (OUT/'mcp-live-tools.json').write_text(json.dumps(names, indent=2)+'\n')
            (OUT/'assessment-results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2)+'\n')
            (OUT/'assessment-note.txt').write_text(NOTE+'\n')
            print(json.dumps({k: current[k] for k in ['id','state','verification_passed','preview_ready','technical_acceptance','ready_for_human','human_accepted','preview_url','evidence_hash']}, ensure_ascii=False, indent=2))

asyncio.run(main())
