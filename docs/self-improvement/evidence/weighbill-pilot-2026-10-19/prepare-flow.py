from pathlib import Path
import json
import shlex
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CLONE = ROOT/'data/external-agents/weighbill-concurrency'
config = json.loads((CLONE/'.tmh/config.json').read_text())
# The added pytest test_editor_state_machine executes the Node controller.
# Do not require the new test file as a global command on the unchanged baseline.
config['commands']['extra_checks'] = []
(CLONE/'.tmh/config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
(OUT/'project-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
cmd = ('/Users/auntlee/workspace/weighbill-system/.venv/bin/python -B tools/webuddy_preview.py '
       '--port {port} --prefix {prefix} --data-dir '+shlex.quote(str(OUT/'preview-data')))
payload = {'cmd':cmd, 'ready':'/api/v1/health'}
(OUT/'preview-config.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
req = urllib.request.Request('http://127.0.0.1:8791/api/projects/WBILL/preview-conf', data=json.dumps(payload).encode(),
                             headers={'Content-Type':'application/json','X-TMH':'1'},method='POST')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(req,timeout=15) as response:
    (OUT/'preview-config-receipt.json').write_bytes(response.read())
criteria = [
 {'id':'A1','text':'条件保存拒绝旧版本及未知回执的旧请求重试，核对新版本后能继续','check':'真实双客户端HTTP、SQLite字段与history前后值；409无副作用'},
 {'id':'A2','text':'按所见版本审核，失败不报成功，修改已审核记录要求重审','check':'旧版本审核skipped、部分成功、保存返回版本及重审回归'},
 {'id':'A3','text':'真实页面冲突后完整草稿保留、显式核对最新数据后继续保存审核','check':'两个真实浏览器页面，草稿/重量/提示/操作记录与原始截图'},
 {'id':'A4','text':'原权限、来源、原图及Excel保真与历史数据保持，明确旧API兼容边界','check':'完整应用回归、原仓库/数据摘要、无版本兼容和非法版本测试'},
 {'id':'A5','text':'完整Git SHA前缀预览能读写和打开原图，CLI/MCP交付证据可查询','check':'固定候选独立构建测试、前缀实测与跨站拦截、原始日志和协议回执'}]
(OUT/'criteria.json').write_text(json.dumps(criteria,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'project':'WBILL','ready':payload['ready'],'criteria':[x['id'] for x in criteria]},ensure_ascii=False))
