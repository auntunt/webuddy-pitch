import asyncio,json,sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'data/external-delivery-20261019'
RESULTS=[
 {'id':'A1','status':'pass','evidence':'固定提交8b6cb6da908fc7bdcb585789a1b8f2ce78569ffd：真实HTTP/SQLite用例覆盖中文、Unicode casefold、%、_、引号的字面搜索且不截断；平台独立构建/35项测试通过。独立会话另跑35项通过。见候选verification完整commands、bootv2-tests-coordinator.log、independent-review-bootv2.log。'},
 {'id':'A2','status':'pass','evidence':'真实HTTP用例核对全部/未完成/已完成、关键词交集、顺序和空结果；真实浏览器以原三条事项操作编辑+已完成得到2条，未完成得到空结果，清除后恢复3条。见browser-checks.json、browser-filter-empty.png及browser-filter-desktop.png。'},
 {'id':'A3','status':'pass','evidence':'真实浏览器经工作台授权入口进入完整SHA前缀；关键词和状态在刷新、进入编辑及取消后保持，实际URL和DOM保存在browser-checks.json。HTTP用例覆盖新增/保存/切换完成后的重定向及未知/重复状态安全归一。修正了直接预览端口401入口，并保留原失败说明。'},
 {'id':'A4','status':'pass','evidence':'原26项测试完整保留并通过，新增9项通过，覆盖200字符含换行、CSRF、转义、数据库503完整输入及重试、存储与重启。主数据原3行的id/title/done不变，既有3项目/4工单/45事件/6运行原行不变。见preservation-report.json；独立复核报告independent-review-final-diff.json。'}]
NOTE='外部Codex是实现者；本条由协调验收会话记录自己的浏览器/主数据观察，并引用独立子代理 /root/candidate_chain_review 的代码和实测复核。外部Codex沙箱不能监听TCP或提交共享Git元数据的失败已完整保留；本地协调者提交不伪称模型沙箱测试成功。技术验收不是客户/人的最终签收，不合并、不部署。完整证据归档 docs/self-improvement/evidence/external-candidate-2026-10-19/。'
(EVIDENCE/'assessment-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2)+'\n')
(EVIDENCE/'assessment-note.txt').write_text(NOTE+'\n')
async def main():
 params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'tmh/workbench_entry.py'),'mcp','--endpoint','http://127.0.0.1:8791','--agent','codex-acceptance'],cwd='/tmp')
 async with stdio_client(params) as (reader,writer):
  async with ClientSession(reader,writer) as session:
   await session.initialize(); tools=await session.list_tools(); names=[t.name for t in tools.tools]; assert 'webuddy_candidate_assess' in names and 'webuddy_candidate_decide' not in names
   before=await session.call_tool('webuddy_candidate_get',{'candidate_id':1}); assert not before.isError; v=before.structuredContent;assert v['current'] and v['preview_ready'] and v['verification_passed']; assert v['preview_url'].startswith('http://127.0.0.1:8791/pv/')
   reply=await session.call_tool('webuddy_candidate_assess',{'candidate_id':1,'verification_hash':v['verification_hash'],'preview_hash':v['preview_hash'],'results':RESULTS,'note':NOTE,'request_id':'bootv2-filter-independent-assessment-20261019'})
   (EVIDENCE/'mcp-technical-acceptance.json').write_text(json.dumps(reply.model_dump(mode='json'),ensure_ascii=False,indent=2)+'\n');assert not reply.isError,reply
   current=reply.structuredContent; assert current['ready_for_human'] and current['technical_acceptance'] and not current['human_accepted'];
   (EVIDENCE/'mcp-live-tools.json').write_text(json.dumps(names,indent=2)+'\n')
   print(json.dumps({k:current[k] for k in ['id','state','verification_passed','preview_ready','technical_acceptance','ready_for_human','human_accepted','preview_url','evidence_hash']},ensure_ascii=False,indent=2))
asyncio.run(main())
