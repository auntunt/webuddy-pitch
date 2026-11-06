import json
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from tmh.platform.server import Platform, make_handler
from tmh.platform import login,development,tool_read
ROOT=Path(sys.argv[1]).resolve()
P=Platform(ROOT/'webuddy',user='demo-owner',brand='Webuddy ERP 演练')
projects=P.store.projects();project=next((p for p in projects if p['key']=='ERP'),None)
if project is None:project=P.store.add_project('ERP','JSHERP 退款说明演练',str(ROOT/'erp'))
items=P.store.tickets(project_id=project['id'])
if not items:
 ticket=P.store.create_ticket(project['id'],'【演练】退款说明必填与可追溯','demo-owner',body='演示假设：非零销售退款须填写5—200字符说明；保留单/多账户、保存回读、防重复与未登录拒绝。不是客户正式规则。财务过账、库存审核不在本轮范围。基线75a9311，候选4172462。',assignee='demo-owner',labels=['隔离演练'],links={'hold':True,'base':'75a9311d5bd485e7fe0701c042520831aa1fa44c'})
 state=development.act(P,'demo-owner','start',{'ticket':ticket['key'],'request_id':'demo-start'})
 development.act(P,'demo-owner','propose',{'ticket':ticket['key'],'request_id':'demo-propose','revision':state['revision'],'summary':'非零销售退款需要可追溯的退款说明（待人确认的演示规则）','design':'复用备注字段，新增/修改接口共用字符校验，前端显示同一规则；不修改审核和过账。','test_plan':'独立旧版/候选Jenkins：真实HTTP、MySQL、浏览器；非法说明拒绝不写库，单多账户、回读和防重复回归。','criteria':[{'id':'A1','text':'非法说明拒绝且不写库','check':'真实HTTP与数据库计数'},{'id':'A2','text':'有效说明保存后可回读','check':'数据库、API与页面'},{'id':'A3','text':'原金额、防重复与登录规则保持','check':'旧业务回归'}],'questions':[{'id':'scope','question':'仅要求非零销售退款，零退款和其他单据保持原行为，可以吗？','options':['按演示假设','需要调整'],'required':True},{'id':'history','question':'历史单据可查看，修改时补齐说明，可以吗？','options':['按演示假设','需要存量豁免'],'required':True}]})
 for number in (7,8):
  evidence=ROOT/'proof'/f'build-{number}'
  report=json.loads((evidence/'report.json').read_text())
  run=P.store.create_run(project['id'],ticket['id'],'external:jenkins-import','external_test','demo-import','真实自建Jenkins执行记录的只读导入；不是平台技术复核或业务验收。')
  P.store.update_run(run['id'],status='done' if number==8 else 'failed',exit_code=0 if number==8 else 1,result=f'Jenkins #{number} 外部实测记录；当前有效性需重新核对，尚未人工复核/验收',output=json.dumps({'source':f'https://127.0.0.1:18443/job/erp-verification/{number}/','report':report,'build':json.loads((evidence/'build.json').read_text())},ensure_ascii=False,indent=2))
else:ticket=items[0]
accounts=json.loads((ROOT/'private/accounts.json').read_text());login.set_user(P.data_dir,'demo-owner',accounts['admin_password'])
packet=tool_read.delivery_get(P,ticket['key'],[project['id']]);assert packet['ready_to_merge'] is None
(ROOT/'proof/webuddy-delivery.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
print('READY http://127.0.0.1:18985/#/t/'+ticket['key'],flush=True)
ThreadingHTTPServer(('127.0.0.1',18985),make_handler(P,token=accounts['reader_password'])).serve_forever()
