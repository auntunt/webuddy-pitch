"""Task conversation with durable operation receipts and explicit recovery."""
ASSISTANT_CSS = r'''
#ast{width:min(520px,100vw);background:#fafbf9}#astHead{background:#fff}#amsg{padding:20px 18px}.assistant-welcome{padding:28px 6px}.assistant-welcome h2{font-size:24px;line-height:1.35;margin:0 0 12px}.assistant-welcome p{color:#64716c;line-height:1.7}.assistant-result{padding:12px 0 20px;line-height:1.75;overflow-wrap:anywhere}.assistant-result details{margin-top:12px;border-top:1px solid #dde3df;padding-top:10px}.assistant-result summary{cursor:pointer;color:#53655b;font-size:13px}.assistant-result pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:360px;overflow:auto}.assistant-progress{display:flex;align-items:center;gap:8px;color:#52645a}.assistant-receipt{padding:10px 0;border-bottom:1px solid #e6eae7}.assistant-receipt:last-child{border:0}.assistant-actions{display:flex;gap:8px;margin-top:12px}#astDeep,#astMoreM .mh,#astMoreM .mset{display:none}#astFoot{color:#758078}#ast .m-u{margin-bottom:18px}#astSugg{gap:8px;padding:8px 18px}#astSugg button{white-space:normal;text-align:left}#aq{min-height:70px}@media(max-width:760px){#ast{width:100vw;max-width:100vw}}
'''
ASSISTANT_JS = r'''
const assistantNames={status:'检查可用能力',projects_list:'查看项目',tickets_list:'查找工单',ticket_get:'读取工单',ticket_create:'创建工单',messages_list:'查看沟通记录',message_send:'写入沟通记录',request_get:'核对操作回执',run_get:'查看执行结果',run_start:'启动任务',run_cancel:'停止任务',run_retry:'重试任务',ticket_hold:'调整任务接管',candidates_list:'查看候选版本',candidate_get:'读取候选证据',library_get:'查看知识资料',library_search:'检索知识',library_read:'读取知识',preview_get:'查看预览',intake_start:'录入需求',intake_get:'查看需求',intake_understand:'分析需求',intake_answer:'补充需求'};
A.turn=null;
A.paintMode=function(){};
A.paintFoot=function(){const busy=this.turn?.sid===this.sid;$('#astFoot').textContent=busy?'正在处理，可在下面查看每一步结果':'Enter 发送 · Shift+Enter 换行';$('#astSend').disabled=!!busy||!!this.sess?.archived_at;$('#aq').placeholder='说说你要做什么…'};
A.paintSugg=function(){const e=$('#astSugg');if(!e)return;const questions=this.ticket?['看看这张工单现在卡在哪里','帮我分析这张工单','查看最近一次执行结果']:['看看这个项目有哪些待办','帮我记录一个新需求','查找项目知识'];e.innerHTML=this.hist||this.msgs.length?'':questions.map(q=>`<button data-question="${h(q)}">${h(q)}</button>`).join('');e.querySelectorAll('button').forEach(b=>b.onclick=()=>{if(b.dataset.question==='帮我记录一个新需求'){$('#aq').value='我想新增：';this.focus()}else this.send(b.dataset.question)})};
A.paintMsgs=function(){
 const el=$('#amsg');if(!el||!this.open)return;
 if(this.hist){el.innerHTML=this.paintHist();this.bindHist();const q=$('#hq');if(q)q.oninput=()=>{this.q=q.value;this.paintMsgs();const n=$('#hq');n.focus();n.setSelectionRange(n.value.length,n.value.length)};return}
 if(!this.msgs.length){el.innerHTML='<div class="assistant-welcome"><h2>接下来，想做什么？</h2><p>查进度、整理需求，或把任务交给智能体。</p></div>';this.paintSugg();this.paintFoot();return}
 el.innerHTML=this.msgs.map(m=>{
  const d=m.data||{};if(m.role==='user')return `<div class="m-u">${h(m.body)}</div>`;
  if(d.kind!=='assistant')return `<div class="assistant-result">${md(m.body)}${this.cards(d.cards)}${d.run?`<button onclick="showRun(${Number(d.run)})">查看原执行记录</button>`:''}</div>`;
  const working=d.state==='working',busy=this.turn?.sid===this.sid;
  const steps=(d.trace||[]).map(t=>`<div class="assistant-receipt"><b>${h(assistantNames[t.operation]||t.operation)}</b> · ${t.status==='done'?'已完成':'未完成'}<details><summary>查看参数和回执</summary><pre>${h(JSON.stringify({arguments:t.arguments,result:t.result},null,2))}</pre></details></div>`).join('');
  return `<article class="assistant-result">${working?`<div class="assistant-progress">${busy?'<span class="spin"></span>':''}${h(m.body)}</div>`:md(m.body)}${steps?`<details ${working?'open':''}><summary>${d.trace.length} 项操作记录</summary>${steps}</details>`:''}${working?`<div class="assistant-actions">${!busy?`<button class="primary" data-assistant-resume="${m.id}">继续处理</button>`:''}<button data-assistant-stop="${m.id}">${this.turn?.stop?'正在停止…':'停止继续处理'}</button></div>`:''}</article>`
 }).join('');
 el.querySelectorAll('[data-assistant-resume]').forEach(b=>b.onclick=()=>this.resumeAssistant(+b.dataset.assistantResume));
 el.querySelectorAll('[data-assistant-stop]').forEach(b=>b.onclick=()=>this.stopAssistant(+b.dataset.assistantStop));
 el.scrollTop=el.scrollHeight;this.paintSugg();this.paintFoot();
};
A.updateAssistant=function(sid,r){if(this.sid!==sid)return;const i=this.msgs.findIndex(m=>m.id===r.message.id);if(i>=0)this.msgs[i]=r.message;else this.msgs.push(r.message);this.paintMsgs()};
A.resumeAssistant=async function(mid){
 if(this.turn)return toast('请先等待当前操作返回');
 const sid=this.sid,m=this.msgs.find(m=>m.id===mid);if(!m)return;
 const turn={sid,mid,stop:false};this.turn=turn;this.paintMsgs();let r={message:m,pending:true,step:m.data.step};
 try{while(r.pending&&!turn.stop){r=await post('/api/sessions/'+sid+'/assistant',{message:mid,step:r.step});this.updateAssistant(sid,r)}
  if(turn.stop){r=await post('/api/sessions/'+sid+'/assistant',{message:mid,action:'stop'});this.updateAssistant(sid,r)}
 }catch(e){if(this.sid===sid)toast(e.message,6000)}
 finally{if(this.turn===turn)this.turn=null;if(this.sid===sid){await this.load();this.paintMsgs()}await this.loadList()}
};
A.stopAssistant=async function(mid){if(this.turn?.mid===mid){this.turn.stop=true;this.paintMsgs();return}const sid=this.sid;try{const r=await post('/api/sessions/'+sid+'/assistant',{message:mid,action:'stop'});this.updateAssistant(sid,r)}catch(e){toast(e.message)}};
A.send=async function(q){
 q=(q||'').trim();if(!q||!S.proj)return;if(this.turn)return toast('上一条仍在处理，稍后再发送');
 const project=S.proj,originalSid=this.sid,input=$('#aq').value;const starting={sid:this.sid,starting:true};this.turn=starting;this.paintFoot();
 try{
  if(!originalSid){const session=await post('/api/projects/'+project+'/sessions',this.view?{kind:'ticket',ticket:this.view.key}:{kind:'consult',title:q.slice(0,24)});if(S.proj!==project||this.sid!==originalSid)return;await this.switchTo(session.id,true)}
  if(S.proj!==project||!this.sid||(originalSid&&this.sid!==originalSid))return;
  const sid=this.sid;starting.sid=sid;
  const draftKey='tmh.assistant.pending.'+sid;let pending;try{pending=JSON.parse(ls.get(draftKey)||'null')}catch(e){}
  if(!pending||pending.question!==q)pending={question:q,request_id:crypto.randomUUID()};ls.set(draftKey,JSON.stringify(pending));
  const r=await post('/api/sessions/'+sid+'/assistant',pending);ls.set(draftKey,null);ls.set('tmh.draft.'+sid,null);
  if(this.turn===starting)this.turn=null;
  if(this.sid===sid&&S.proj===project){if($('#aq').value===input)$('#aq').value='';await this.load();this.updateAssistant(sid,r);if(r.pending)await this.resumeAssistant(r.message.id)}
 }catch(e){if(S.proj===project&&this.sid===starting.sid){toast(e.message,6000)}}
 finally{if(this.turn===starting)this.turn=null;this.paintFoot()}
};
A.ask=function(q){return this.send(q)};
astSend=function(){const t=$('#aq');if(t.value.trim())A.send(t.value)};
'''
