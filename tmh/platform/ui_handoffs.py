"""Task handoffs: durable draft bindings, explicit receipt and full evidence."""

HANDOFFS_JS = r"""
const HANDOFFS={view:null,drafts:new Map(),pending:new Map(),serial:0};
const HF_ACTIONS={send:'发送交接',receive:'接收材料',return:'退回材料',block:'登记阻塞',resume:'恢复推进',withdraw:'撤回交接'};
const HF_STATUS={waiting:'待指定人员接收',received:'材料已接收',returned:'材料已退回',blocked:'推进已阻塞',withdrawn:'交接已撤回'};
function hfText(value){return typeof value==='string'?value:JSON.stringify(value??null,null,2)}
function hfRequestId(){return 'handoff-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2))}
function hfLive(view){return HANDOFFS.view===view&&view.host.isConnected&&view.live()}
function hfCurrent(key){const view=HANDOFFS.view;return view&&view.key===key&&hfLive(view)?view:null}
function hfDrafts(key){if(!HANDOFFS.drafts.has(key))HANDOFFS.drafts.set(key,new Map());return HANDOFFS.drafts.get(key)}
function hfDraftStale(view,draft){return draft.revision!==view.data.revision||(view.action==='send'?draft.source_token!==view.data.source_token:draft.handoff_id!==(view.data.current?.id??null))}
function hfNewDraft(data){return {revision:data.revision,source_token:data.source_token,handoff_id:data.current?.id??null,receiver:'',stage:'',note:'',materials:''}}
function hfDraft(view,action){const drafts=hfDrafts(view.key);if(!drafts.has(action))drafts.set(action,hfNewDraft(view.data));return drafts.get(action)}
function hfNotice(view,text,error=false){if(!hfLive(view))return;const n=view.host.querySelector('#hfNotice');n.className=error?'ws-inline-error':'sub';n.textContent=text}
function hfSnapshot(title,value){return `<details class="hf-source"><summary>${h(title)}</summary><pre>${h(hfText(value))}</pre></details>`}
function hfPaintFacts(view){
 const d=view.data,c=d.current,t=d.ticket,w=d.work||{},candidate=w.candidate,latestEvent=c?.events?.at(-1);
 view.host.querySelector('#hfFacts').innerHTML=`<div class="hf-progress"><span>${h(w.label||'打开处理入口查看当前进展')}</span>${stPill(t.status)}</div><dl class="hf-facts"><dt>当前负责人</dt><dd>${h(w.assignment?.assignee||t.assignee||'待分配')}</dd><dt>下一责任人</dt><dd>${h(d.next_actor||'未登记')}${c?.next_actor_active===false?'（账号已停用）':''}</dd><dt>独立复核人</dt><dd>${h(w.assignment?.reviewer||'待分配')}</dd><dt>交接阶段</dt><dd>${h(c?WS_STAGES[c.stage]||c.stage:'未登记阶段')}</dd><dt>交接状态</dt><dd>${h(c?HF_STATUS[c.status]||c.status:'尚无交接')}</dd><dt>当前等待</dt><dd>${h(wsHandoffWait(c,d.waiting_seconds))}</dd></dl>${latestEvent?`<section class="hf-latest-event"><h3>最近交接处理</h3><p class="sub">${h(HF_ACTIONS[latestEvent.action]||latestEvent.action)} · ${h(latestEvent.actor)} · ${h(latestEvent.ts||'时间未知')}</p><p class="hf-full-text">${h(latestEvent.note||'未填写额外说明')}</p></section>`:''}${c?.block_reason&&c.block_reason!==latestEvent?.note?`<div class="ws-block-reason"><b>阻塞原因</b><p>${h(c.block_reason)}</p></div>`:''}${c?.receiver_active===false?'<div class="ws-inline-error">接收人账号已失效，可由发送人或任务负责人撤回后重发。</div>':''}${c?.stale?`<div class="ws-inline-error">发送后的依据已变化；请核对最新需求和版本。${h(hfText(c.stale_reasons||[]))}</div>`:''}<div class="hf-evidence-state"><span>技术检查：${h({passed:'已通过',tests_passed:'测试通过',pending:'待检查',running:'检查中',not_started:'尚未开始'}[w.technical]||'未知')}</span><span>人工复核：${h({accepted:'已登记通过',pending:'待人工复核',rejected:'已退回',not_requested:'尚未提交'}[w.human]||'未知')}</span></div><div class="ws-actions"><a class="btn" href="#/t/${encodeURIComponent(view.key)}">完整任务与业务验收</a><a class="btn" href="#/team/ticket/${encodeURIComponent(view.key)}">代码提交与独立复核</a></div>`;
 view.host.querySelector('#hfRequirement').innerHTML=`<h3>完整需求与验收标准</h3><pre class="hf-full-text">${h(d.source?.ticket?.body??t.body??'尚未填写需求正文')}</pre>`;
 view.host.querySelector('#hfEvidence').innerHTML=`<h3>版本与依据</h3>${candidate?`<p>候选 #${h(candidate.id)} · <code>${h(candidate.commit)}</code></p>`:'<p class="sub">尚无候选版本。交接材料不能替代测试证据或人工验收。</p>'}${hfSnapshot('最新需求、讨论与版本依据（完整记录）',d.source)}${c?hfSnapshot('本次发送时的固定依据（完整快照）',c.source):''}`;
 view.host.querySelector('#hfHistory').innerHTML=`<h3>交接历史</h3>${(d.history||[]).length?(d.history||[]).map(item=>`<article class="hf-history-item"><div class="ws-row-meta"><b>${h(HF_STATUS[item.status]||item.status)}</b><span>${h(WS_STAGES[item.stage]||item.stage)}</span><span>${h(item.sent_at||'发送时间未知')}</span></div><p>${h(item.sender)}${item.sender_active===false?'（账号已停用）':''} → ${h(item.receiver)}${item.receiver_active===false?'（账号已停用）':''}</p><p class="hf-full-text">${h(item.note||'')}</p>${item.materials?`<details><summary>完整交接材料</summary><pre>${h(item.materials)}</pre></details>`:''}${hfSnapshot('交接、接收与阻塞事件（完整记录）',item.events||[])}${hfSnapshot('固定来源快照',item.source)}</article>`).join(''):'<p class="sub">还没有交接记录；旧任务的阶段和等待时长保持未知。</p>'}${d.events?hfSnapshot('全部交接事件',d.events):''}`;
 view.host.querySelector('#hfBoundary').textContent=d.boundary||'接收材料不等于技术通过、人工复核或业务验收。';
}
function hfCapture(view){if(!view.data||!view.action)return;const draft=hfDraft(view,view.action);for(const field of ['receiver','stage','note','materials']){const node=view.host.querySelector('[data-hf-field="'+field+'"]');if(node)draft[field]=node.value}}
function hfSyncOptions(view){
 const action=view.host.querySelector('#hfAction');if(action){action.innerHTML=Object.entries(HF_ACTIONS).filter(([a])=>view.data.actions?.[a]||a===view.action).map(([a,label])=>`<option value="${a}" ${a===view.action?'selected':''}>${label}</option>`).join('');action.value=view.action}
 const receiver=view.host.querySelector('[data-hf-field="receiver"]');if(receiver){const selected=hfDraft(view,view.action).receiver,members=view.data.members||[];receiver.innerHTML='<option value="">选择有效个人账号</option>'+members.map(m=>`<option value="${h(m.id)}" ${m.id===selected?'selected':''}>${h(m.name)}</option>`).join('')+(selected&&!members.some(m=>m.id===selected)?`<option value="${h(selected)}" selected>${h(selected)}（账号已不可用，请重选）</option>`:'');receiver.value=selected}
}
function hfPaintForm(view){
 const d=view.data,allowed=d.actions||{},pending=HANDOFFS.pending.get(view.key);let action=view.action;
 if(!action)action=Object.keys(HF_ACTIONS).find(a=>allowed[a])||'send';view.action=action;const draft=hfDraft(view,action);
 view.host.querySelector('#hfFormArea').innerHTML=`<form id="hfForm"><h3>推进交接</h3><label class="hf-field">操作<select id="hfAction">${Object.entries(HF_ACTIONS).filter(([a])=>allowed[a]||a===action).map(([a,label])=>`<option value="${a}" ${a===action?'selected':''}>${label}</option>`).join('')}</select></label><div class="hf-form-fields">${action==='send'?`<label class="hf-field">指定接收人<select data-hf-field="receiver" required><option value="">选择有效个人账号</option>${(d.members||[]).map(m=>`<option value="${h(m.id)}" ${m.id===draft.receiver?'selected':''}>${h(m.name)}</option>`).join('')}</select></label><label class="hf-field">交接目标阶段<select data-hf-field="stage" required><option value="">选择阶段</option>${Object.entries(WS_STAGES).filter(([code])=>code!=='unrecorded').map(([code,label])=>`<option value="${code}" ${code===draft.stage?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<label class="hf-field">${action==='send'?'交接说明与下一步':action==='block'?'阻塞原因':action==='return'?'退回原因':action==='withdraw'?'撤回原因':'处理说明'}<textarea data-hf-field="note" rows="4" ${['send','return','block','withdraw'].includes(action)?'required':''}>${h(draft.note)}</textarea></label>${action==='send'?`<label class="hf-field">完整交接材料<textarea data-hf-field="materials" rows="5" placeholder="填写执行步骤、环境、测试记录和未决问题。固定版本依据由系统随发送绑定。">${h(draft.materials)}</textarea></label>`:''}</div><p id="hfBinding" class="sub"></p><div class="ws-actions"><button class="primary" id="hfSubmit" type="submit">${h(HF_ACTIONS[action])}</button><button id="hfRebind" type="button">保留草稿，核对并绑定最新依据</button></div><p class="sub">接收只登记材料交接。技术检查、独立人工复核和业务验收继续在各自入口完成。</p></form><div id="hfPending"></div>`;
 view.host.querySelector('#hfAction').onchange=e=>{hfCapture(view);view.action=e.target.value;hfPaintForm(view);view.host.querySelector('#hfAction').focus()};
 view.host.querySelectorAll('[data-hf-field]').forEach(node=>node.oninput=()=>{hfCapture(view);hfFormStatus(view)});
 view.host.querySelector('#hfForm').onsubmit=e=>{e.preventDefault();return hfSubmit(view)};
 view.host.querySelector('#hfRebind').onclick=()=>{if(HANDOFFS.pending.has(view.key))return;hfCapture(view);const old=hfDraft(view,view.action);hfDrafts(view.key).set(view.action,{...old,revision:view.data.revision,source_token:view.data.source_token,handoff_id:view.data.current?.id??null});hfFormStatus(view);hfNotice(view,'已保留正文并绑定当前展示的最新依据；请核对后再提交。')};
 hfSyncOptions(view);hfFormStatus(view);
}
function hfFormStatus(view){
 if(!hfLive(view)||!view.data)return;const pending=HANDOFFS.pending.get(view.key),draft=hfDraft(view,view.action),allowed=!!view.data.actions?.[view.action],stale=hfDraftStale(view,draft),inactive=view.action==='send'&&!!draft.receiver&&!(view.data.members||[]).some(m=>m.id===draft.receiver);
 view.host.querySelector('#hfBinding').textContent=view.needsRefresh?'操作已登记，请先刷新记录读取最新状态再继续。':inactive?'原接收人账号已不可用；草稿已保留，请重新选择有效个人。':pending?'请求结果待确认；重试将发送原始内容和同一请求编号。':stale?'草稿仍绑定较早的记录版本。请先核对最新记录，再明确重新绑定；原文会保留。':!allowed?'当前身份或交接状态不允许此操作；刷新记录可核对最新权限。':'草稿已绑定当前需求和交接记录版本。';
 view.host.querySelectorAll('[data-hf-field]').forEach(node=>node.disabled=!!pending);view.host.querySelector('#hfAction').disabled=!!pending;
 view.host.querySelector('#hfSubmit').disabled=!!pending||!allowed||stale||inactive||!!view.needsRefresh;view.host.querySelector('#hfRebind').disabled=!!pending||!stale;
 const region=view.host.querySelector('#hfPending');region.innerHTML=pending?`<div class="ws-inline-error" role="status"><p>${pending.busy?'正在登记，请勿重复提交。':'未确认服务器是否已登记。原始草稿已保留，可用相同请求编号重试。'}</p><button id="hfRetryMutation" ${pending.busy?'disabled':''}>重试原请求</button>${hfSnapshot('本次原始请求内容',pending.body)}</div>`:'';
 if(pending)region.querySelector('#hfRetryMutation').onclick=()=>hfPerform(view,pending);
}
async function hfSubmit(view){
 if(!hfLive(view)||view.needsRefresh||HANDOFFS.pending.has(view.key)||!view.data.actions?.[view.action])return;hfCapture(view);const action=view.action,draft=hfDraft(view,action);
 if(hfDraftStale(view,draft)){hfNotice(view,'记录版本或来源依据已变化；请核对并重新绑定后提交。',true);return}
 if(['send','return','block','withdraw'].includes(action)&&!draft.note.trim()){hfNotice(view,'请填写本次处理的原因或说明。',true);return}
 if(action==='send'&&(!draft.receiver||!draft.stage||!(view.data.members||[]).some(m=>m.id===draft.receiver))){hfNotice(view,'请选择接收人和交接目标阶段。',true);return}
 const body={ticket:view.key,action,revision:draft.revision,request_id:hfRequestId(),...(action==='send'?{receiver:draft.receiver,stage:draft.stage,note:draft.note,materials:draft.materials,source_token:draft.source_token}:{handoff_id:draft.handoff_id,note:draft.note})};
 const pending={body,busy:false};HANDOFFS.pending.set(view.key,pending);return hfPerform(view,pending);
}
async function hfPerform(view,pending){
 if(pending.busy)return;pending.busy=true;const starting=hfCurrent(view.key);if(starting)hfFormStatus(starting);
 try{
  const result=await post('/api/handoffs',pending.body);
  if(!result||result.ticket?.key!==view.key||!Number.isInteger(result.revision)||!Object.hasOwn(result,'current')||result.receipt?.request_id!==pending.body.request_id)throw Error('服务器响应不完整');
  HANDOFFS.pending.delete(view.key);hfDrafts(view.key).delete(pending.body.action);
  const current=hfCurrent(view.key);if(!current)return;
  current.needsRefresh=true;current.completedAction=pending.body.action;hfPaintForm(current);hfNotice(current,'交接操作已登记。接收材料不等于验收通过。');await hfRefresh(current,true);if(hfLive(current)&&!current.needsRefresh&&current.onUpdate)await current.onUpdate();
 }catch(error){
  const current=hfCurrent(view.key);
  if([400,401,403,404,409,413,422,429].includes(error.status)){HANDOFFS.pending.delete(view.key);if(current)hfNotice(current,error.message+' 原始草稿已保留；刷新记录后可修正重试。',true)}else if(current)hfNotice(current,error.message+' 请求结果尚未确认，请重试原请求。',true);
 }finally{pending.busy=false;const current=hfCurrent(view.key);if(current)hfFormStatus(current)}
}
async function hfRefresh(view,afterMutation=false){
 const read=++view.read;if(!hfLive(view))return;const refresh=view.host.querySelector('#hfRefresh');refresh.disabled=true;
 try{
  const data=await get('/api/handoffs?ticket='+encodeURIComponent(view.key));if(!hfLive(view)||read!==view.read)return;
  if(!data||data.ticket?.key!==view.key||!Number.isInteger(data.revision)||!data.actions||!Object.hasOwn(data,'current'))throw Error('任务交接响应不完整');
  view.data=data;view.needsRefresh=false;
  if(view.completedAction){hfDrafts(view.key).delete(view.completedAction);if(view.action===view.completedAction)view.action='';view.completedAction=''}
  view.host.querySelector('#hfTitle').textContent=data.ticket.title;hfPaintFacts(view);
  const project=S.projects.find(p=>String(p.id)===String(data.ticket.project_id));if(typeof briefingOpen==='function'&&project){if(view.brief&&coLive(view.brief))coRefresh(view.brief);else view.brief=briefingOpen(view.host.querySelector('#hfBrief'),view.key,project.key,()=>hfLive(view))}
  if(!view.action||afterMutation){hfPaintForm(view)}else{hfSyncOptions(view);hfFormStatus(view)};
  if(view.focus){view.host.querySelector('#hfTitle').focus();view.focus=false}
 }catch(error){if(hfLive(view)&&read===view.read){if(!view.data)view.host.querySelector('#hfTitle').textContent=[401,403].includes(error.status)?'需要用个人账号登录后查看':'没能读取这张工单';hfNotice(view,([401,403].includes(error.status)?'交接记录只对个人登录账号开放（共享口令、显示名不算）。请用自己的账号登录后点“刷新记录”。':error.message+' 可重新读取；未提交的内容会保留。'),true)}}
 finally{if(hfLive(view)&&read===view.read)refresh.disabled=false}
}
async function handoffsOpen(host,key,live,focus=false,onUpdate=null){
 const old=HANDOFFS.view;if(old&&hfLive(old)&&old.key===key&&old.host===host)return hfRefresh(old);
 if(old&&old.host.isConnected)hfCapture(old);
 host.innerHTML=`<div class="hf-head"><div><div class="ws-eyebrow">${h(key)} · 任务交接</div><h2 id="hfTitle" tabindex="-1">正在读取工单…</h2></div><button id="hfRefresh">刷新记录</button></div><div id="hfNotice" role="status" aria-live="polite"></div><section id="hfBrief"></section><div id="hfFacts"></div><section id="hfRequirement" class="ws-section"></section><section id="hfEvidence" class="ws-section"></section><section id="hfFormArea" class="ws-section"></section><section id="hfHistory" class="ws-section"></section><p id="hfBoundary" class="sub"></p>`;
 const view={host,key,live,focus,onUpdate,read:0,data:null,action:''};HANDOFFS.view=view;host.querySelector('#hfRefresh').onclick=()=>hfRefresh(view);return hfRefresh(view);
}
"""
