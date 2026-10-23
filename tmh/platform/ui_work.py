"""The workbench pages: 今天 / 客户 / 需求 / 版本, the global "粘贴客户的话" box, and the ticket page's top summary.

Everything the platform already had lives under 工程 (the old tabs, unchanged, every #/ route still works). These
pages answer the owner's questions in plain words: who asked for what, where it is, what went out, what the AI is
doing now. User text always goes through h().
"""

WORK_CSS = r"""
#nav5{display:flex;gap:16px;margin:0;padding:0;border-bottom:1px solid var(--line);min-width:0}
#nav5 a{position:relative;display:flex;align-items:center;gap:8px;min-height:56px;padding:12px 8px;color:var(--mut);border-bottom:2px solid transparent;font-size:14px;font-weight:500;white-space:nowrap;text-decoration:none}
#nav5 a i{display:flex;font-style:normal}#nav5 a:hover{color:var(--blue)}
#nav5 a.on{color:var(--blue);border-bottom-color:var(--blue);font-weight:650}
#nav5 a b{background:var(--bad);color:#fff;border-radius:999px;font-size:11px;padding:0 6px;line-height:18px;font-weight:600}
.wicon{width:20px;height:20px;display:inline-block;vertical-align:middle;flex:none}
#nav5+#tabs{margin-top:0}#tabs .tnew{margin-left:auto;align-self:center;white-space:nowrap}
#say{display:flex;flex:1;max-width:420px;min-width:0;margin:0 0 0 6px}
#say input{flex:1;min-width:0;background:var(--soft);border:1px solid var(--line);color:var(--fg);border-radius:7px 0 0 7px;padding:6px 10px}
#say input::placeholder{color:var(--mut)}#say button{border-radius:0 7px 7px 0;white-space:nowrap}
.st{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:12px;line-height:1.5;white-space:nowrap;border:1px solid var(--line);font-weight:500}
.st.talk,.st.client{color:var(--mut);background:var(--soft)}.st.doing{color:var(--blue);background:var(--blue-s);border-color:var(--line)}
.st.you{color:var(--warn);background:var(--warn-s);border-color:var(--line)}
.st.shipped{color:var(--ok);background:var(--ok-s);border-color:var(--line)}.st.done{color:var(--mut);background:var(--soft)}
.wk{min-width:0}.wk h1{margin:0;font-size:26px;line-height:1.35;letter-spacing:-.02em}.wkh{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:24px}
.wk-heading{flex:1;min-width:0}.wk-heading .sub{margin-top:6px;line-height:1.6}.wk-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.wkg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:32px;align-items:start}
.wkg>.card,.wkg>div{min-width:0}.wkg h2{display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:16px}
.wkg .card{border:0;border-radius:0;padding:20px 0;background:transparent;border-top:1px solid var(--line)}
.saybig{margin:0 0 32px;padding:22px;background:var(--panel);border:1px solid var(--line);border-radius:10px}
.saybig label{display:block;font-weight:650;font-size:15px}.saybig textarea{min-height:86px;margin:12px 0;background:var(--panel)}.saybig .row{align-items:center;gap:14px}
.wr{display:flex;gap:12px;align-items:flex-start;padding:14px 0;border-top:1px solid var(--line);color:var(--fg);line-height:1.6}
.wr:first-of-type{border-top:0}.wr:hover{text-decoration:none}.wr:hover b{color:var(--blue)}.wr b{font-weight:550}
.wr .grow{min-width:0;overflow-wrap:anywhere}.wr .sub{display:block;margin-top:4px}.wr .go{color:var(--blue);font-size:13px;white-space:nowrap;margin-left:auto}
.wr .ico{display:flex;flex:none;width:22px;min-height:22px;align-items:center;justify-content:center;color:var(--mut);margin-top:2px}.wke{color:var(--mut);font-size:13px;line-height:1.7;padding:10px 0}
.live{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok)}
.steps3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:16px}
.steps3>div{font-size:13px;line-height:1.7;color:var(--mut)}.steps3 b{display:block;margin-bottom:5px;color:var(--fg);font-weight:550}
.clg{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:16px}
.clc{display:block;color:var(--fg);padding:22px;transition:border-color .15s ease,background .15s ease;overflow-wrap:anywhere}.clc:hover{text-decoration:none;border-color:var(--blue);background:var(--blue-s)}.clc h3{margin:0 0 8px;font-size:17px}
.cln{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 10px}
.wk-form{margin-bottom:24px;padding:22px}.wk-form h2{margin:0 0 16px}.wk-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.wk-field{display:flex;flex-direction:column;gap:6px;min-width:0;font-size:13px;font-weight:550}.wk-field input,.wk-field select,.wk-field textarea{width:100%;font-weight:400}.wk-field.full{grid-column:1/-1}.wk-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:20px}
.wk-empty{padding:28px 24px}.wk-empty p{max-width:60ch;margin:8px 0 0;line-height:1.7;color:var(--mut)}
.rqb{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;align-items:start;min-width:0}
.rqc{padding:0;min-width:0}.rqc h3{display:flex;justify-content:space-between;align-items:center;gap:6px;margin:0 0 12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.rqi{display:block;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:10px;color:var(--fg);overflow-wrap:anywhere;line-height:1.6}
.rqi b{font-size:13px;font-weight:550}.rqi:hover{text-decoration:none;border-color:var(--blue)}.rqi .sub{display:block;font-size:12px;margin-top:6px}
.rqc .wke{padding:16px 12px;background:var(--soft);border-radius:8px;text-align:center}
.version-card{margin-bottom:24px;padding:24px}.version-card>.hdr{padding-bottom:16px;margin-bottom:0;border-bottom:1px solid var(--line)}
.version-preview{padding:20px 0}.version-preview .sub{overflow-wrap:anywhere}.vcur{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.vcur>.sub{min-width:0;max-width:100%;font-variant-numeric:tabular-nums}
.version-share{margin-top:20px;padding-top:20px;border-top:1px solid var(--line)}.version-share>.sub{margin-top:6px}
.vtl{border-left:1px solid var(--line);margin:12px 0 0 6px;padding-left:20px}.vtl>div{position:relative;padding:0 0 20px;overflow-wrap:anywhere}.vtl>div:before{content:"";position:absolute;left:-24px;top:6px;width:7px;height:7px;border-radius:50%;background:var(--mut)}
.vtl ul{margin:8px 0 0;padding-left:18px}.vtl li{margin:6px 0;overflow-wrap:anywhere;line-height:1.6}
.lnk{display:flex;align-items:end;gap:10px;margin-top:12px;flex-wrap:wrap}.lnk input{flex:1;min-width:0}.lnk button{white-space:nowrap}.lnk .wk-field{flex:1;min-width:150px}.lnk .wk-field input{flex:none}
.ttop{margin:16px 0 20px;border-color:var(--line);background:var(--panel);padding:22px}
.ttop dl{display:grid;grid-template-columns:72px minmax(0,1fr);gap:12px 16px;margin:16px 0 0}.ttop dt{color:var(--mut);font-size:13px}.ttop dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap;line-height:1.7}
.ttop .na.warn{color:var(--fg)}.ttop .row{margin-top:16px;gap:8px}
details.fold>summary,details.eng>summary{cursor:pointer;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;list-style:none}
details.fold>summary::-webkit-details-marker,details.eng>summary::-webkit-details-marker{display:none}
details.fold>summary:before,details.eng>summary:before{content:"▸";color:var(--mut)}details[open].fold>summary:before,details[open].eng>summary:before{content:"▾"}
.engb{display:flex;flex-direction:column;gap:16px;margin-top:16px}
@media(max-width:1200px){.rqb{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:1000px){.wkg{grid-template-columns:minmax(0,1fr);gap:0}}
@media(max-width:700px){
  #nav5{position:fixed;left:0;right:0;bottom:0;z-index:8;margin:0;padding:0 4px env(safe-area-inset-bottom);background:var(--panel);border-top:1px solid var(--line);border-bottom:0;justify-content:space-around;gap:0}
  #nav5 a{flex-direction:column;gap:3px;min-height:60px;padding:8px 2px 6px;font-size:11px;border-bottom:0;border-top:2px solid transparent;flex:1;align-items:center;justify-content:center}
  #nav5 a i{display:flex}#nav5 a.on{border-top-color:var(--blue);background:var(--blue-s)}#nav5 a b{position:absolute;top:4px;right:2px;font-size:10px;line-height:15px;padding:0 4px}
  #page{padding-bottom:calc(92px + env(safe-area-inset-bottom))}#ast{z-index:9}#toast{bottom:calc(84px + env(safe-area-inset-bottom))}
  #say{flex:0 0 auto;max-width:none;margin:0 0 0 auto}#say input{display:none}#say button{border-radius:7px}#say button span{display:inline}
  #astOpen{bottom:78px;padding:8px 12px;font-size:13px}.wk h1{font-size:23px}.wkh{align-items:flex-start;margin-bottom:20px}.wk-heading{flex-basis:100%}.wkh>.sub{flex-basis:100%}
  .wkh button,.wk-actions button,.lnk button{min-height:44px}.wk input,.wk textarea,.wk select{font-size:16px}.saybig{padding:18px;margin-bottom:24px}.saybig .row>.sub{flex-basis:100%}
  .wk-fields,.steps3,.rqb{grid-template-columns:minmax(0,1fr)}.wk-form{padding:18px}.rqb{gap:24px}.rqc h3{margin-bottom:10px}.rqi{padding:16px}
  .wr{gap:10px;flex-wrap:wrap}.wr>.grow{flex-basis:calc(100% - 36px)}.wr .go{margin-left:32px}.wr>.st+.grow{flex-basis:100%}
  .version-card{padding:18px}.vcur{gap:10px}.vcur>.sub{flex-basis:100%}.vcur>.grow{display:none}.vcur button,.vcur a.btn{min-height:44px}.lnk .wk-field{flex-basis:100%}.lnk>input{flex-basis:100%;width:100%}
  .ttop{padding:18px}.ttop dl{grid-template-columns:minmax(0,1fr);gap:4px}.ttop dd{margin-bottom:8px}.ttop .row button,.ttop .row a.btn{min-height:44px}
}
"""

WORK_JS = r"""
// ---------- the workbench: 今天 / 客户 / 需求 / 版本; everything else is 工程
function workIcon(name){const icons={
  deliveries:'<path d="M4 5h16v14H4zM4 10h16M9 10v9"/>',
  today:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-12 4h3m2 0h3m-8 3h3"/>',
  clients:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/>',
  reqs:'<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10h6m-6 4h6m-6 4h3"/>',
  versions:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  eng:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  alert:'<path d="m12 3 10 18H2L12 3Zm0 6v5m0 3v1"/>',
  message:'<path d="M20 4H4v12h5l3 4 3-4h5V4ZM7 8h10M7 12h7"/>',
  question:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4m0 3v1"/>',
  edit:'<path d="m4 16 12-12 4 4L8 20H4v-4Zm9-9 4 4M13 20h7"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  up:'<path d="M12 20V4m-6 6 6-6 6 6"/>',
  next:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  dot:'<circle cx="12" cy="12" r="4"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'};
  return `<svg class="wicon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${icons[name]||icons.dot}</svg>`}
const NAV=[['workspace','工作台','#/workspace','today'],['projects','项目','#/projects','versions'],['tasks','任务','#/tickets','reqs'],['team','团队协作','#/team','clients'],['memory','知识与记忆','#/memory','message']];
const WK=['workspace','projects','team','memory','handoff','deliveries','delivery','today','clients','c','reqs','versions','t'];
function isEng(v){return !WK.includes(v)}
function navOf(v){return ['workspace','today','meetings'].includes(v)?'workspace':['team'].includes(v)?'team':['memory','handoff','kb','library','learn'].includes(v)?'memory':['tickets','t','reqs','board','home','rtickets'].includes(v)?'tasks':'projects'}
function paintNav(){const cur=navOf(curView()),nav=$('#nav5');
  const signature=JSON.stringify([cur,curView(),!!S.meta?.access?.can_manage]);if(nav.dataset.signature===signature)return;
  const focused=nav.contains(document.activeElement)?document.activeElement.closest('[data-n]')?.dataset.n:null;
  nav.innerHTML='<span class="ws-nav-label">工作空间</span>'+NAV.map(([k,l,u,ic])=>`<a href="${u}" class="${k===cur?'on':''}" data-n="${k}" ${k===cur?'aria-current="page"':''}><i aria-hidden="true">${workIcon(ic)}</i><span>${l}</span></a>`).join('')+`<div class="ws-nav-secondary"><span class="ws-nav-label">管理</span><a href="#/deliveries">${workIcon('deliveries')}<span>交付</span></a><a href="#/clients">${workIcon('clients')}<span>客户</span></a><a href="#/settings">${workIcon('eng')}<span>设置</span></a>${S.meta?.access?.can_manage?`<a href="#/access" ${curView()==='access'?'aria-current="page"':''}>${workIcon('clients')}<span>成员与权限</span></a>`:''}</div>`;
  nav.dataset.signature=signature;if(focused)nav.querySelector(`[data-n="${focused}"]`)?.focus()}
const STL={talk:'需求澄清',doing:'执行中',you:'待复核',client:'待客户确认',shipped:'已出版本',done:'已完成'};
const stChip=s=>`<span class="st ${h(s)}">${h(STL[s]||s)}</span>`;
const MODE={analyze:'分析',plan:'出方案',fix:'改代码',kb:'写知识页',diagnose:'诊断'};
const pk0=()=>S.scope!=='*'?S.scope:S.proj;
function nowStr(d){d=d||new Date();const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`}

// ---------- 粘贴客户的话: one box on every page, the requirement conversation with the client recorded
function sayWire(){/* Pasting keeps focus; recording begins only on explicit submit. */}
function sayOpen(){const i=$('#sayIn'),v=i?i.value:'';if(S.meta?.access&&S.meta.access.capabilities?.execution!==true){newTicket({body:v});return}if(i)i.value='';const c=location.hash.match(/^#\/c\/(\d+)/);pasteModal(v,c?+c[1]:undefined)}
async function pasteModal(text,cid){
  if(!S.projects.length)return newProject();
  let cs=[];try{cs=(await get('/api/clients')).clients}catch(e){}
  const want=cid!=null?String(cid):(ls.get('tmh.lastClient')||''),has=cs.some(c=>String(c.id)===want);
  const np=pk0()||S.proj;
  modal(`<h2>记录需求</h2><p class="sub">保留原话和上下文，先澄清目标与验收标准。</p>
   <div class="wk-fields"><label class="wk-field full" for="pmT">需求原文<textarea id="pmT" style="min-height:140px" placeholder="例如：请假审批通过后列表里还是草稿；另外，希望请假单能导出 Excel。">${h(text||'')}</textarea></label>
    <label class="wk-field" for="pmC">客户<select id="pmC"><option value="">不记客户</option>${cs.map(c=>`<option value="${c.id}" ${String(c.id)===want?'selected':''}>${h(c.name)}</option>`).join('')}<option value="__new" ${!cs.length?'selected':''}>＋ 新客户…</option></select></label>
    <label class="wk-field" id="pmNL" for="pmN" ${cs.length?'hidden':''}>客户称呼<input id="pmN" placeholder="例如：王总（某某集团）" ${cs.length?'hidden':''}></label>
    ${S.projects.length>1?`<label class="wk-field" for="pmP">所属项目<select id="pmP">${S.projects.map(p=>`<option value="${h(p.key)}" ${p.key===np?'selected':''}>${h(p.key)} · ${h(p.name)}</option>`).join('')}</select></label>`:''}</div>
   <div class="wk-actions"><button class="primary" id="pmGo">交给 AI 理清</button><button type="button" id="pmOld" class="ghost">直接填写工单</button></div>`,true);
  if(!has&&want&&cid==null)$('#pmC').value='';
  $('#pmC').onchange=()=>{$('#pmN').hidden=$('#pmC').value!=='__new';$('#pmNL').hidden=$('#pmN').hidden;if(!$('#pmN').hidden)$('#pmN').focus()};
  if(!text)$('#pmT').focus();
  $('#pmOld').onclick=()=>{const v=$('#pmT').value;closeModal();newTicket({title:v.split('\n')[0].slice(0,60),body:v})};
  $('#pmGo').onclick=async()=>{const v=$('#pmT').value,c=$('#pmC').value,pk=$('#pmP')?$('#pmP').value:np;
    const b={project:pk,text:v};if(c==='__new'){const n=$('#pmN').value.trim();if(!n)return toast('写上客户的称呼，或者选“不记客户”');b.client_name=n}else if(c)b.client=+c;
    $('#pmGo').disabled=true;$('#pmGo').textContent='正在理清…';
    try{const s=await post('/api/workbench/intake',b);ls.set('tmh.lastClient',s.client?String(s.client):'');
      const name=c==='__new'?b.client_name:(cs.find(x=>x.id===s.client)||{}).name||'';
      intakeOpen(s,name)}catch(e){toast(e.message,5000);$('#pmGo').disabled=false;$('#pmGo').textContent='交给 AI 理清'}}}
// the existing requirement conversation, opened on a talk that already started
function intakeOpen(s,clientName){intakeModal(s.project,s.text);intakePaint(s);
  const h2=$('#mbody h2');if(h2&&clientName)h2.insertAdjacentHTML('afterend',`<div style="margin:2px 0 6px"><span class="ev-tag info">来自 ${h(clientName)}</span></div>`)}
document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('[data-talk]');if(a){e.preventDefault();talkOpen(a.dataset.talk,a.dataset.cn||'')}});
async function talkOpen(id,clientName){try{intakeOpen(await get('/api/intake/'+encodeURIComponent(id)),clientName)}catch(e){toast(e.message)}}

// ---------- 今天: what needs me, what the AI did since I last looked, what it is doing now
function todaySince(){let s=null;try{s=sessionStorage.getItem('tmh.since')}catch(e){}
  if(s==null){s=ls.get('tmh.seen')||nowStr(new Date(Date.now()-864e5));try{sessionStorage.setItem('tmh.since',s)}catch(e){}}
  return s}
async function vToday(){
  const since=todaySince();
  const d=await get('/api/today?since='+encodeURIComponent(since));ls.set('tmh.seen',d.server_time);
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><div class="wk-heading"><h1>今天</h1><div class="sub">工作区动态 · 上次查看 ${h(ago(since))}</div></div><span class="st ${S.meta.autoflow&&S.meta.autoflow.on?'doing':'done'}">自动处理${S.meta.autoflow&&S.meta.autoflow.on?'已开启':'已关闭'}</span></div>
   <form class="saybig" id="sayBig" onsubmit="event.preventDefault()"><label for="sbT">记录新的需求</label><textarea id="sbT" placeholder="粘贴客户原话、聊天记录，或描述要解决的问题。"></textarea>
    <div class="row"><button class="primary" id="sbGo">交给 AI 理清</button><span class="sub">先澄清目标与验收标准，再进入执行。</span></div></form>
   <div class="wkg"><div style="display:flex;flex-direction:column;gap:14px;min-width:0"><section class="card" id="tNeed"></section><section class="card" id="tCl"></section></div>
    <div style="display:flex;flex-direction:column;gap:14px;min-width:0"><section class="card" id="tNow"></section><section class="card" id="tDid"></section></div></div></div>`;
  $('#sbGo').onclick=()=>{const v=$('#sbT').value;$('#sbT').value='';pasteModal(v)};
  todayPaint(d);
  poll(async()=>{if(!$('#tNow')||document.hidden)return;try{todayPaint(await get('/api/today?since='+encodeURIComponent(since)))}catch(e){}},5000,'page')}
function todayPaint(d){
  S.need=d.mine.length;paintNav();
  const cl=x=>x.client_name?` <span class="tag">${h(x.client_name)}</span>`:'';
  const row=(href,ico,title,sub,go,attrs)=>`<a class="wr" href="${href}" ${attrs||''}><span class="ico">${ico}</span><span class="grow"><b>${title}</b>${sub?`<span class="sub">${sub}</span>`:''}</span>${go?`<span class="go">${go} ›</span>`:''}</a>`;
  const need=d.mine.filter(x=>x.reason!=='stalled'),stalled=d.mine.filter(x=>x.reason==='stalled');
  $('#tNeed').innerHTML=`<h2>需要处理 ${need.length?`<span class="ibn">${need.length}</span>`:''}</h2>`+
    (stalled.length?row('#/settings',workIcon('alert'),`${stalled.length} 件新需求不会自己开始`,h(stalled[0].label),'去处理'):'')+
    (d.standing_failed||[]).map(x=>row('#/versions/'+h(x.project),workIcon('alert'),`${h(x.project)} 预览启动失败`,h(x.why||'看看启动日志'),'去看')).join('')+
    (need.length?need.map(x=>row('#/t/'+h(x.key),workIcon('dot'),`${h(x.title)}${cl(x)}`,`${h(x.label)}${x.note?' · “'+h(x.note)+'”':''} · ${h(x.key)} · 等了 ${waited(x.since||'')}`,h(x.action))).join('')
      :`<div class="wke">暂无需要复核的事项。${d.now.length?'AI 做完需要你的，会出现在这里。':''}</div>`);
  const talks=d.talks,ac=d.open_ac,sign=d.others;
  $('#tCl').innerHTML=`<h2>客户沟通</h2>`+
    (talks.length?talks.map(x=>row('javascript:void 0',workIcon('message'),`${x.client_name?h(x.client_name)+'：':''}${h(x.text)}`,`${x.questions?'还有 '+x.questions+' 个问题没答':'理清了，等你确认开工'} · ${h(x.project)} · ${h(ago(x.since))}`,'继续理清',`data-talk="${h(x.id)}" data-cn="${h(x.client_name)}"`)).join(''):'')+
    (ac.length?ac.map(x=>row('#/t/'+h(x.key),workIcon('question'),`${h(x.title)}${cl(x)}`,`有 ${x.open} 条验收标准要和客户确认，确认前 AI 不动手 · ${h(x.key)}`,'去确认')).join(''):'')+
    (sign.length?sign.map(x=>row('#/t/'+h(x.key),workIcon('edit'),`${h(x.title)}${cl(x)}`,`${h(x.label)} · ${h(x.key)} · 等了 ${waited(x.since||'')}`,'看看')).join(''):'')+
    (talks.length||ac.length||sign.length?'':'<div class="wke">没有等客户回答的问题。</div>');
  $('#tNow').innerHTML=`<h2>${d.now.length?'<span class="live"></span>':''} 当前运行 <span class="sub" style="font-weight:400">每 5 秒刷新</span></h2>`+
    (d.now.length?d.now.map(x=>row(x.key?'#/t/'+h(x.key):'#/runs',x.status==='running'?'<span class="spin"></span>':workIcon('clock'),x.key?`${h(x.title)}${cl(x)}`:h(MODE[x.mode]||x.mode),
      `${x.status==='running'?'正在':'排队等着'}${h(MODE[x.mode]||x.mode)} · ${h(x.key||x.project)} · ${x.status==='running'?'已经 '+waited(x.since||''):'刚排上'}`,'')).join('')
      :`<div class="wke">暂无进行中的运行。${d.auto?'新需求一确认，AI 就会开始。':'可在工程设置中查看自动处理配置。'}</div>`);
  const did=d.did,vs=d.versions,KD={release:workIcon('check'),adopt:workIcon('up'),conflict:workIcon('alert'),status:workIcon('next')};
  $('#tDid').innerHTML=`<h2>最近进展</h2>`+
    (vs.length?vs.map(v=>`<div class="wr"><span class="ico">${workIcon('versions')}</span><span class="grow"><b>${h(v.project)} 出了版本 ${h(v.version)}</b><span class="sub">${v.items.map(i=>h(i.title)).join('；')} · ${h(ago(v.ts))}</span></span><span class="go">${v.standing?`<a href="${h(v.standing)}" target="_blank" rel="noopener">打开</a>`:`<a href="#/versions/${h(v.project)}">启动</a>`} · <a href="#/versions/${h(v.project)}">发给客户 ›</a></span></div>`).join(''):'')+
    (did.length?(()=>{const by={};did.forEach(x=>(by[x.key]=by[x.key]||[]).push(x));  // one line per requirement: its latest step
      return Object.values(by).map(xs=>{const x=xs[0];return row('#/t/'+h(x.key),KD[x.kind]||workIcon('dot'),`${h(x.title)}${cl(x)}`,`${h(x.text)}${xs.length>1?' · 之前还有 '+(xs.length-1)+' 步':''} · ${h(ago(x.ts))}`,'')}).join('')})():'')+
    (vs.length||did.length?'':`<div class="wke">上次之后还没有新进展。</div><div class="steps3"><div><b>01 记录需求</b>保留目标、原话和上下文。</div><div><b>02 澄清与执行</b>确认验收标准后，推进具体工作。</div><div><b>03 验证交付</b>检查运行与版本证据，再分享预览。</div></div>`)}

// ---------- 客户: who they are, what they asked, where each thing is, what they got, what is still owed
async function vClients(){
  const d=await get('/api/clients?counts=1');
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><div class="wk-heading"><h1>客户</h1><div class="sub">${d.clients.length} 位客户 · 需求、沟通与交付记录</div></div><button class="primary" id="clNew">＋ 新建客户</button></div><div id="clF"></div>
   ${d.clients.length?`<div class="clg">${d.clients.map(c=>`<a class="card clc" href="#/c/${c.id}"><h3>${h(c.name)}</h3><div class="sub">${h(c.contact||'没有联系方式')} · ${c.projects.map(h).join('、')||'还没关联项目'}</div>
     <div class="cln">${c.counts.owed?`<span class="st you">待交付 ${c.counts.owed} 件</span>`:'<span class="st shipped">暂无待交付需求</span>'}${c.counts.client?`<span class="st client">待客户确认 ${c.counts.client}</span>`:''}${c.counts.talk?`<span class="st talk">理解中 ${c.counts.talk}</span>`:''}${c.counts.shipped?`<span class="st done">已出版本 ${c.counts.shipped}</span>`:''}</div>
     <div class="sub" style="margin-top:6px">最近 ${h(ago(c.last))}</div></a>`).join('')}</div>`
    :`<div class="card wk-empty"><b>还没有客户记录</b><p>新建客户后，可以关联项目、保存沟通原文，并追踪对应需求和版本。</p></div>`}</div>`;
  $('#clNew').onclick=()=>clientForm()}
function clientForm(c){c=c||{};const F=$('#clF');
  F.innerHTML=`<div class="card wk-form"><h2>${c.id?'编辑客户':'新建客户'}</h2>
   <div class="wk-fields"><label class="wk-field" for="cfN">客户称呼<input id="cfN" autocomplete="organization" placeholder="例如：王总（某某集团）" value="${h(c.name||'')}"></label><label class="wk-field" for="cfC">联系方式<input id="cfC" placeholder="电话、微信或群名" value="${h(c.contact||'')}"></label>
   <label class="wk-field full" for="cfP">关联项目<input id="cfP" placeholder="项目代号，多个用逗号分隔，例如 OA, CRM" value="${h((c.projects||[S.proj]).join(', '))}"></label><label class="wk-field full" for="cfT">沟通备注<textarea id="cfT" placeholder="关注的问题、沟通偏好或约定" style="min-height:90px">${h(c.notes||'')}</textarea></label></div>
   <div class="wk-actions"><button class="primary" id="cfS">保存客户</button><button class="ghost" id="cfX">取消</button>${c.id?'<button class="danger" id="cfD" style="margin-left:auto">删除客户</button>':''}</div></div>`;
  $('#cfN').focus();$('#cfX').onclick=()=>F.innerHTML='';
  $('#cfS').onclick=async()=>{const b={name:$('#cfN').value,contact:$('#cfC').value,projects:$('#cfP').value,notes:$('#cfT').value};
    try{const r=c.id?await post('/api/clients/'+c.id,Object.assign({action:'update'},b)):await post('/api/clients',b);toast('已保存');location.hash='#/c/'+r.id;render()}catch(e){toast(e.message,5000)}};
  if($('#cfD'))$('#cfD').onclick=async()=>{if(!confirm('删除客户“'+c.name+'”？他的需求和工单都还在，只是不再记在他名下。'))return;try{await post('/api/clients/'+c.id,{action:'delete'});location.hash='#/clients'}catch(e){toast(e.message)}}}
async function vClient(id){
  const d=await get('/api/clients/'+encodeURIComponent(id)),c=d.client;S.client=c;
  const reqRow=x=>`<a class="wr" href="${x.key?'#/t/'+h(x.key):'javascript:void 0'}" ${x.talk?`data-talk="${h(x.talk)}" data-cn="${h(c.name)}"`:''}>${stChip(x.state)}<span class="grow"><b>${h(x.title)}</b><span class="sub">${h(x.why||'')}${x.version?' · 版本 '+h(x.version):''}${x.key?' · '+h(x.key):''}</span></span></a>`;
  const CH={web:'网页',chat:'群聊',feishu:'飞书',dingtalk:'钉钉',wecom:'企业微信',api:'接口'};
  $('#main').innerHTML=`<div class="wk"><div class="sub" style="margin-bottom:4px"><a href="#/clients">客户</a> / ${h(c.name)}</div>
   <div class="wkh"><h1 class="grow">${h(c.name)}</h1><button class="primary" id="ccSay">＋ 记录新需求</button><button id="ccEd">编辑</button><button class="ghost" id="ccLk">关联群聊或工单</button></div>
   <div class="sub" style="margin:-8px 0 12px">${h(c.contact||'没有联系方式')} · 项目 ${c.projects.map(h).join('、')||'无'}${c.notes?' · '+h(c.notes):''}</div><div id="clF"></div><div id="ccL"></div>
   <div class="wkg"><div style="display:flex;flex-direction:column;gap:14px;min-width:0">
    <section class="card"><h2>待交付需求 ${d.owed.length?`<span class="ibn">${d.owed.length}</span>`:''}</h2>${d.owed.length?d.owed.map(reqRow).join(''):'<div class="wke">暂无待交付需求。</div>'}</section>
    <section class="card"><h2>沟通记录</h2>${d.asked.length?d.asked.map(a=>`<div class="wr"><span class="ico">${workIcon('message')}</span><span class="grow"><span class="sub">${h((a.ts||'').slice(0,16))} · ${h(CH[a.channel]||a.channel||'工单')} · ${h(a.project||'')}</span>“${h(a.text||'')}”
      <span class="sub">${a.kind==='talk'&&!['confirmed','dropped'].includes(a.state)?`<a href="javascript:void 0" data-talk="${h(a.id)}" data-cn="${h(c.name)}">${a.questions?'还有 '+a.questions+' 个问题没答，继续理清':'理清了，去确认开工'}</a>`:(a.tickets||[]).map(k=>`<a href="#/t/${h(k)}">${h(k)}</a>`).join(' ')}</span></span></div>`).join(''):'<div class="wke">暂无沟通记录，可从“记录新需求”添加原文。</div>'}</section></div>
   <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
    <section class="card"><h2>需求状态</h2>${d.requirements.length?d.requirements.map(x=>reqRow(x)).join(''):'<div class="wke">还没有建成需求的事。</div>'}</section>
    <section class="card"><h2>相关版本</h2>${d.versions.length?`<div class="vtl">${d.versions.map(v=>`<div><b>${h(v.project)} ${h(v.version)}</b> <span class="sub">${h((v.ts||'').slice(0,16))}</span><ul>${v.items.map(i=>`<li><a href="#/t/${h(i.key)}">${h(i.key)}</a> ${h(i.title)}</li>`).join('')}</ul></div>`).join('')}</div>`:'<div class="wke">还没有给他出过版本。</div>'}
     ${c.projects.length?`<div class="row" style="margin-top:6px;gap:8px">${c.projects.map(p=>`<a class="btn" href="#/versions/${h(p)}">查看 ${h(p)} 版本与分享</a>`).join('')}</div>`:''}</section></div></div></div>`;
  $('#ccSay').onclick=()=>pasteModal('',c.id);$('#ccEd').onclick=()=>clientForm(c);
  $('#ccLk').onclick=async()=>{let ch=[];try{ch=(await get('/api/chats')).chats}catch(e){}
    $('#ccL').innerHTML=`<div class="card" style="margin-bottom:14px;display:flex;flex-direction:column;gap:8px"><h2 style="margin:0">关联到 ${h(c.name)}</h2>
     <div class="sub">关联以后，从这个群聊或这张工单来的需求、出的版本，都记在他名下。</div>
     ${ch.length?`<label>群聊 <select id="lkC"><option value="">选一个群聊</option>${ch.map(x=>`<option value="${h(x.id)}">${h(x.project)} · ${h(x.channel)} · ${x.tickets.length} 件事${x.client?'（已关联）':''}</option>`).join('')}</select></label>`:'<div class="sub">还没有群聊对话（群机器人收到过需求后才会出现）。</div>'}
     <label>工单 <input id="lkT" placeholder="工单号，比如 OA-12"></label><div class="row" style="gap:8px"><button class="primary" id="lkGo">关联</button><button class="ghost" onclick="$('#ccL').innerHTML=''">取消</button></div></div>`;
    $('#lkGo').onclick=async()=>{try{if($('#lkC')&&$('#lkC').value)await post('/api/clients/'+c.id,{action:'link',kind:'chat',ref:$('#lkC').value});
      if($('#lkT').value.trim())await post('/api/clients/'+c.id,{action:'link',kind:'ticket',ref:$('#lkT').value.trim()});toast('已关联');vClient(c.id)}catch(e){toast(e.message,5000)}}}}

// ---------- 需求: every requirement in plain-word columns
async function vReqs(){
  const d=await get('/api/requirements?project='+encodeURIComponent(scopeQ()));
  const item=x=>x.kind==='talk'?`<a class="rqi" href="javascript:void 0" data-talk="${h(x.id)}" data-cn="${h(x.client_name)}"><b>${h(x.title)}</b><span class="sub">${x.client_name?h(x.client_name)+' · ':''}${h(x.why)}</span></a>`
    :`<a class="rqi" href="#/t/${h(x.key)}"><b>${h(x.title)}</b><span class="sub">${x.client_name?h(x.client_name)+' · ':''}${h(x.why||'')}${x.version?' · '+h(x.version):''}</span><span class="sub">${h(x.key)}${x.epic?' · 大需求':''}${x.parent?' · 属于 '+h(x.parent):''}</span></a>`;
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><div class="wk-heading"><h1>需求</h1><div class="sub">${d.columns.reduce((n,c)=>n+c.items.length,0)} 项需求 · 按当前状态推进</div></div><button class="primary" onclick="pasteModal('')">＋ 记录需求</button></div>
   <div class="rqb">${d.columns.map(c=>`<div class="rqc"><h3><span>${stChip(c.key)}</span><span class="sub">${c.items.length}</span></h3>${c.items.length?c.items.map(item).join(''):'<div class="wke">暂无需求</div>'}</div>`).join('')}</div></div>`;
  poll(async()=>{if(!$('.rqb')||document.hidden)return;try{const n=await get('/api/requirements?project='+encodeURIComponent(scopeQ()));if(JSON.stringify(n)!==JSON.stringify(d))vReqs()}catch(e){}},8000,'page')}

// ---------- 版本: per project, the current version clients can open, and every version with what it held
async function vVersions(key){
  const keys=key?[key.toUpperCase()]:S.scope!=='*'?[S.scope]:S.projects.map(p=>p.key);
  const all=await Promise.all(keys.map(k=>get('/api/projects/'+encodeURIComponent(k)+'/versions')));
  let cs=[];try{cs=(await get('/api/clients')).clients}catch(e){}
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><div class="wk-heading"><h1>版本</h1><div class="sub">查看主干版本、预览状态和客户分享记录。</div></div></div>
   ${all.length?all.map(v=>versionCard(v,cs)).join(''):'<div class="card wk-empty"><b>还没有可查看的项目版本</b><p>建立项目后，可以在这里管理预览和版本记录。</p></div>'}</div>`;
  all.forEach(v=>versionWire(v));
  if(all.some(v=>v.standing.state==='starting'))setTimeout(()=>{if(curView()==='versions')vVersions(key)},4000)}
function versionCard(v,cs){const p=v.project,s=v.standing,K=h(p.key),last=(((v.versions||[])[0]||{}).items||[]).map(i=>i.client_name).find(Boolean)||'';
  const st=s.state==='up'?'<span class="ev-tag ok">预览运行中</span>':s.state==='starting'?'<span class="ev-tag info"><span class="spin"></span> 正在启动</span>':s.state==='unhealthy'||s.state==='checking'?'<span class="ev-tag bad">预览暂不可用</span>':s.state==='failed'?'<span class="ev-tag bad">启动失败</span>':'<span class="ev-tag mute">尚未启动</span>';
  return `<section class="card version-card" id="vc-${K}"><div class="hdr"><h2 class="grow" style="margin:0">${K} · ${h(p.name)}</h2><span class="st done">${v.merge==='auto'?'自动合并已开启':'自动合并已关闭'}</span></div>
   <div class="version-preview"><div class="vcur"><b>当前预览</b>${st}<span class="sub">${s.commit?'提交 '+h(s.commit):''}${s.main?' · 主干 '+h(s.main):''}${s.stale?' · 主干有更新，可重新启动预览':''}</span><span class="grow"></span>
     ${s.url?`<a class="btn primary" href="${h(s.url)}" target="_blank" rel="noopener">打开预览 ↗</a>`:''}${s.configured&&s.state!=='starting'?`<button class="${s.url?'ghost':'primary'}" data-vs="start">${s.url||['unhealthy','checking'].includes(s.state)?'重新启动':'启动预览'}</button>`:''}${s.url||['starting','unhealthy','checking'].includes(s.state)?'<button class="ghost" data-vs="stop">停止预览</button>':''}</div>
     ${s.why&&['failed','unhealthy','checking'].includes(s.state)?`<div class="bad" style="font-size:13px;margin-top:6px">${h(s.why)}</div>`:''}
     ${s.fix?`<div class="sub" style="margin-top:8px">${h(s.fix)}</div><div class="lnk"><label class="wk-field" for="vcmd-${K}">预览启动命令<input id="vcmd-${K}" data-vcmd placeholder="例如 python3 app.py {port} {prefix}" value="${h(s.configured?s.cmd:(s.cmd||''))}"></label><button data-vsave>保存命令</button></div>`:''}
     ${s.configured?`<div class="version-share"><h3 style="margin:0">分享预览</h3><div class="sub">为客户生成带有效期的版本链接；可随时撤销。分享不代表客户已经验收。</div>
      <div class="lnk"><label class="wk-field" for="vcl-${K}">接收客户<select id="vcl-${K}" data-vcl><option value="">不指定客户（仅展示改进数量）</option>${cs.filter(c=>!c.projects.length||c.projects.includes(p.key)).map(c=>`<option value="${c.id}" ${c.name===last?'selected':''}>${h(c.name)}</option>`).join('')}</select></label><label class="wk-field" for="vdays-${K}">链接有效期<select id="vdays-${K}" data-vdays><option value="7">7 天</option><option value="30" selected>30 天</option><option value="90">90 天</option></select></label><button class="primary" data-vshare>生成分享链接</button></div><div data-vout></div>
      ${v.shares.length?`<div style="margin-top:8px">${v.shares.map(x=>`<div class="sub" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">给 ${h(x.client_name||'未指定')} · ${h(x.created.slice(5,16))} 发 · ${h(x.expires.slice(0,10))} 前有效 <button class="ghost" data-vrev="${h(x.id)}">收回</button></div>`).join('')}</div>`:''}</div>`:''}</div>
   <h3 style="margin-top:14px">版本记录</h3>${v.versions.length?`<div class="vtl">${v.versions.map(x=>`<div><b>${h(x.version)}</b> <span class="sub">${h((x.ts||'').slice(0,16))} · 提交 ${h(x.commit||'')}</span><ul>${x.items.map(i=>`<li>${i.client_name?`<span class="tag">${h(i.client_name)}</span> `:''}${h(i.title)} <a href="#/t/${h(i.key)}" class="sub">${h(i.key)}</a></li>`).join('')}</ul></div>`).join('')}</div>`
    :'<div class="wke">还没有版本记录。改动合入主干并形成版本后，会显示在这里。</div>'}</section>`}
function versionWire(v){const box=$('#vc-'+v.project.key);if(!box)return;if(typeof accessFenceControls==='function')accessFenceControls(box);const P='/api/projects/'+encodeURIComponent(v.project.key),re=()=>vVersions(curView()==='versions'?decodeURIComponent((location.hash.split('/')[2]||'')):'');
  box.querySelectorAll('[data-vs]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await post(P+'/standing',{action:b.dataset.vs});toast(b.dataset.vs==='stop'?'已停止预览':'正在启动预览')}catch(e){toast(e.message,6000)}re()});
  const sv=box.querySelector('[data-vsave]');if(sv)sv.onclick=async()=>{try{await post(P+'/preview-conf',{cmd:box.querySelector('[data-vcmd]').value,ready:'/'});toast('已保存预览启动命令');re()}catch(e){toast(e.message,6000)}};
  const sh=box.querySelector('[data-vshare]');if(sh)sh.onclick=async()=>{try{const r=await post(P+'/shares',{client:+box.querySelector('[data-vcl]').value||null,days:+box.querySelector('[data-vdays]').value});
    const url=r.url||r.path;box.querySelector('[data-vout]').innerHTML=`<div class="sub" style="margin-top:6px">${r.client_name?'给 '+h(r.client_name)+'，':''}${h(r.expires.slice(0,10))} 前有效。链接只显示这一次，复制后发到微信或群里：</div>${r.client_name?'':'<div class="bad" style="font-size:13px;margin-top:4px">没选客户：打开的人只看到“本版包含几项改进”，看不到每一项是什么。要让客户看到给他做了什么，选上他再生成。</div>'}${r.private?`<div class="bad" style="font-size:13px;margin-top:4px">${h(r.warn)}</div>`:''}<div class="lnk"><label class="wk-field">分享链接<input readonly aria-label="分享链接" value="${h(url)}"></label><button class="primary" data-vcp>复制链接</button></div>`;
    box.querySelector('[data-vcp]').onclick=()=>navigator.clipboard.writeText(url).then(()=>toast('已复制')).catch(()=>box.querySelector('[data-vout] input').select())}catch(e){toast(e.message,6000)}};
  box.querySelectorAll('[data-vrev]').forEach(b=>b.onclick=async()=>{try{await post(P+'/shares/'+b.dataset.vrev+'/revoke',{});toast('已收回，这个链接打不开了');re()}catch(e){toast(e.message)}})}

// ---------- ticket page: what the client asked, where it is, the one next step, the preview: first screen
function planless(s){return String(s||'').replace(/```tmh-[a-z]+[\s\S]*?```/g,'').replace(/tmh-plan\s*\{[\s\S]*$/,'')}
function planReadable(s){return String(s||'').replace(/```tmh-plan\s*([\s\S]*?)```/g,(m,j)=>{let p;try{p=JSON.parse(j)}catch(e){return m}
  const fs=(p.files||[]).map(f=>`- \`${f.path}\`：${f.goal||''}`).join('\n'),ac=(p.ac||[]).map(a=>`- ${a.id||''} ${a.text||''}${a.check?'（怎么验：'+a.check+'）':''}`).join('\n');
  return (fs?'**要改的文件**\n\n'+fs+'\n\n':'')+(ac?'**方案自己的检查项**\n\n'+ac+'\n':'')})}
function plainState(d){const s=d.plain_state;return s?[s.state,s.why]:['you','状态尚未加载，请刷新']}
function ticketTop(d,f,na){const t=d.ticket,[s,why]=plainState(d,f);const said=secOf(t.body||'',['原话'])||symptomOf(t);
  return `<div class="card ttop"><div class="row" style="margin:0;align-items:center;gap:8px">${stChip(s)}<span class="sub">${h(why)}</span><span id="ttCl"></span></div>
   ${d.intake_recovery?.status==='resolved'?`<details style="margin-top:10px"><summary>已根据保存答复补全标准 · 查看恢复记录</summary>${(d.intake_recovery.attempts||[]).map(a=>`<div style="margin-top:8px;white-space:pre-wrap">${h(a.at||'')} · ${h(a.requested_by||'客户答复处理')}<br>${h(a.reason||a.status||'')}${a.run?` <a href="javascript:void 0" onclick="showRun(${Number(a.run)})">查看运行 #${h(a.run)}</a>`:''}</div>`).join('')}</details>`:''}
   <dl><dt>客户要的</dt><dd>${h(said)}</dd><dt>下一步</dt><dd class="na ${na.tone}">${na.text}</dd></dl>
   <div class="row"><span id="ttPv"></span>${t.status!=='closed'&&d.intake_recovery?.can_retry?'<button class="primary" id="ttIntakeRetry">重试理解已保存答复</button>':''}${na.acc?'<button class="primary" id="ttOk"'+ticketSignoffAttrs(d)+'>验收通过</button><button class="danger" id="ttNo">退回重改</button>':''}${t.status==='verify'&&(d.package||{}).status&&d.package.status!=='none'?'<button id="ttSend"'+ticketSignoffAttrs(d)+'>发给客户签收</button>':''}${!['closed','verify'].includes(t.status)&&!(t.links||{}).handwork?'<button class="ghost" id="ttHw">我来写</button>':''}</div></div>`}
async function ticketTopWire(d,na){const t=d.ticket,key=t.key;
  if($('#ttIntakeRetry'))$('#ttIntakeRetry').onclick=()=>$('#naIntakeRetry')?.click();
  if($('#ttOk'))$('#ttOk').onclick=()=>{if(ticketSignoffGuard(d))$('#accOk').click()};
  if($('#ttNo'))$('#ttNo').onclick=()=>{const n=$('#accNote');n.scrollIntoView({block:'center',behavior:'smooth'});n.focus();n.placeholder='写明哪里不对，写好后点“验收不通过”';toast('写明哪里不对，再点“验收不通过”',4000)};
  if($('#ttSend'))$('#ttSend').onclick=()=>{if(!ticketSignoffGuard(d))return;const b=$('#pkLink');if(!b)return toast('证据包还没打好，稍等一下');b.click();$('#pkg').scrollIntoView({block:'start',behavior:'smooth'});const nm=S.ttClient;if(nm&&$('#pkS'))$('#pkS').value=nm};
  if($('#ttHw'))$('#ttHw').onclick=()=>{$('#engc').open=true;setTimeout(()=>{const c=$('#hwc');if(c&&!c.hidden)c.scrollIntoView({block:'start',behavior:'smooth'})},300)};
  S.ttClient='';const cid=(t.links||{}).client;
  if(cid)get('/api/clients').then(r=>{const c=r.clients.find(x=>x.id===cid);if(c&&$('#ttCl')){S.ttClient=c.name;$('#ttCl').innerHTML=`<a class="tag" href="#/c/${c.id}">${h(c.name)}</a>`}}).catch(()=>{});
  if($('#ttPv'))await pvLoad(key)}
"""
