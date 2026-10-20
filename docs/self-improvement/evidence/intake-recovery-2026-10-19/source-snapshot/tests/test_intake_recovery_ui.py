"""A saved customer answer can be recovered from the shipped ticket UI."""
import shutil
import unittest

from tests import test_ui_ticket_run_sync as sync_tests


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped ticket handlers")
class IntakeRecoveryUiTest(unittest.TestCase):
    run_js = sync_tests.TicketRunSyncUiTest.run_js

    def test_saved_answers_offer_recovery_instead_of_asking_the_customer_again(self):
        self.run_js(r'''
latest=ticket([],'you','客户答复已保存，再理解未完成');latest.ticket.links={open_ac:1};
latest.intake_recovery={status:'failed',can_retry:true,reason:'运行超时 <保留原文>',run:9,blocked:[],
 items:[{ticket:'APP-7',answers:[{question:'多久显示？',value:'马上 <script>原文</script>',from:'王总（客户）'}]}]};
await S.ticketRefresh();
assert.ok(nodes.tNextText.innerHTML.includes('客户答复已保存'));
assert.ok(nodes.tNextActions.innerHTML.includes('重试理解已保存答复'));
assert.ok(nodes.tTop.innerHTML.includes('id="ttIntakeRetry"'));
assert.ok(!nodes.tNextActions.innerHTML.includes('naAsk'));
assert.ok(!nodes.tNextActions.innerHTML.includes('naGo'));
assert.ok(nodes.tNextText.innerHTML.includes('&lt;保留原文&gt;'));
assert.ok(nodes.tNextText.innerHTML.includes('&lt;script&gt;'));
assert.ok(!nodes.tNextText.innerHTML.includes('<script>'));
''')

    def test_retry_posts_once_and_follows_success_without_clearing_drafts(self):
        self.run_js(r'''
latest=ticket([],'you','客户答复已保存，再理解未完成');latest.ticket.links={open_ac:1};
latest.intake_recovery={status:'failed',can_retry:true,reason:'超时',blocked:[],items:[]};
await S.ticketRefresh();nodes.cm.value='未发送评论';nodes.cm.focus();
let posts=0;const pending=later();
postHandler=async url=>{assert.equal(url,'/api/tickets/APP-7/intake-retry');posts++;return pending.promise};
const first=$('#naIntakeRetry').onclick();await $('#naIntakeRetry').onclick();assert.equal(posts,1);
latest={...latest,intake_recovery:{...latest.intake_recovery,status:'running',can_retry:false}};
pending.resolve(latest.intake_recovery);await first;
assert.ok(nodes.tNextText.innerHTML.includes('正在根据已保存答复补全'));
assert.ok(!nodes.tNextActions.innerHTML.includes('naIntakeRetry'));
assert.ok(!nodes.tTop.innerHTML.includes('id="ttIntakeRetry"'));
latest=ticket([],'you','自动处理已关闭');latest.intake_recovery={status:'resolved',can_retry:false,items:[],attempts:[{run:9,reason:'原失败保留'},{run:10,reason:'已补全原待确认标准'}]};
const timer=S.polls.find(x=>x.fn);await timer.fn();
assert.ok(!nodes.tNextText.innerHTML.includes('正在根据已保存答复补全'));
assert.ok(!nodes.tNextActions.innerHTML.includes('naIntakeRetry'));
assert.ok(nodes.tTop.innerHTML.includes('查看运行 #9'));assert.ok(nodes.tTop.innerHTML.includes('查看运行 #10'));
assert.equal(nodes.cm.value,'未发送评论');assert.equal(document.activeElement,nodes.cm);
''')

    def test_blocked_retry_and_closed_ticket_never_offer_execution(self):
        self.run_js(r'''
const value=ticket([]);value.ticket.links={open_ac:1};
value.intake_recovery={status:'failed',can_retry:false,reason:'超时',blocked:['原进程尚未回收','没有可用的需求理解智能体'],items:[]};
let action=nextAction(value,flowState(value));
assert.ok(action.text.includes('原进程尚未回收'));assert.ok(action.text.includes('没有可用的需求理解智能体'));
assert.ok(!(action.btns||'').includes('naIntakeRetry'));
value.ticket.status='closed';action=nextAction(value,flowState(value));
assert.ok(!(action.btns||'').includes('naIntakeRetry'));assert.ok(action.text.includes('已闭环'));
''')

    def test_recovery_only_transition_refreshes_summary(self):
        self.run_js(r'''
latest=ticket([]);latest.ticket.links={open_ac:1};
latest.intake_recovery={status:'running',can_retry:false,items:[]};await S.ticketRefresh();
const before=applied;
latest={...latest,intake_recovery:{status:'failed',can_retry:true,reason:'再次失败',items:[]}};
await S.ticketRefresh();assert.equal(applied,before+1);
assert.ok(nodes.tNextText.innerHTML.includes('再次失败'));assert.ok(nodes.tNextActions.innerHTML.includes('naIntakeRetry'));
''')

    def test_retry_failure_keeps_a_retryable_button_and_the_typed_comment(self):
        self.run_js(r'''
latest=ticket([]);latest.ticket.links={open_ac:1};
latest.intake_recovery={status:'failed',can_retry:true,reason:'超时',items:[]};await S.ticketRefresh();
nodes.cm.value='网络失败也不丢';postHandler=async()=>{throw new Error('断网')};
await $('#naIntakeRetry').onclick();assert.equal($('#naIntakeRetry').disabled,false);
assert.equal(nodes.cm.value,'网络失败也不丢');assert.ok(nodes.tNextActions.innerHTML.includes('naIntakeRetry'));
''')

    def test_success_updates_read_only_criteria_but_keeps_an_open_editor(self):
        self.run_js(r'''
delete nodes.be;nodes.bodyv=new TestElement();nodes.bodyv.innerHTML='旧标准';
latest=ticket([]);latest.ticket.body='客户答复后更新的验收标准';await S.ticketRefresh();
assert.equal(nodes.bodyv.innerHTML,'客户答复后更新的验收标准');
nodes.be=new TestElement();nodes.be.value='工程师未保存的编辑';
latest={...latest,ticket:{...latest.ticket,body:'另一份已更新标准'}};await S.ticketRefresh();
assert.equal(nodes.be.value,'工程师未保存的编辑');assert.equal(nodes.bodyv.innerHTML,'客户答复后更新的验收标准');
''')

    def test_a_departed_ticket_does_not_refresh_or_start_polling_after_retry(self):
        self.run_js(r'''
latest=ticket([]);latest.ticket.links={open_ac:1};
latest.intake_recovery={status:'failed',can_retry:true,reason:'超时',items:[]};await S.ticketRefresh();
const pending=later();postHandler=()=>pending.promise;const request=$('#naIntakeRetry').onclick();
let newerReads=0;S.cur={ticket:{key:'OTHER-1'}};S.ticketRefresh=async()=>{newerReads++};
pending.resolve({status:'running'});await request;
assert.equal(newerReads,0);assert.ok(!S.polls.some(x=>x.tag==='intake'));
''')


if __name__ == '__main__':
    unittest.main()
