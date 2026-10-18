"""The workbench pages: 今天 / 客户 / 需求 / 版本, the global "粘贴客户的话" box, and the ticket page's top summary.

Everything the platform already had lives under 工程 (the old tabs, unchanged, every #/ route still works). These
pages answer the owner's questions in plain words: who asked for what, where it is, what went out, what the AI is
doing now. User text always goes through h().
"""

WORK_CSS = r"""
#nav5{display:flex;gap:6px;margin:0 -22px 0;padding:10px 22px 0;border-bottom:1px solid var(--line)}
#nav5 a{display:flex;align-items:center;gap:6px;padding:8px 14px 10px;color:var(--fg);border-bottom:2px solid transparent;font-size:15px;white-space:nowrap}
#nav5 a i{display:none;font-style:normal}#nav5 a:hover{text-decoration:none;color:var(--blue)}
#nav5 a.on{color:var(--blue);border-bottom-color:var(--blue);font-weight:600}
#nav5 a b{background:var(--bad);color:#fff;border-radius:999px;font-size:11px;padding:0 6px;line-height:16px;font-weight:600}
#nav5+#tabs{margin-top:0}#nav5+#tabs[hidden]+main{margin-top:18px}
#tabs .tnew{margin-left:auto;align-self:center;white-space:nowrap}
#say{display:flex;flex:1;max-width:520px;min-width:0;margin:0 0 0 6px}
#say input{flex:1;min-width:0;background:#2C3A52;border:1px solid #46546E;color:#fff;border-radius:6px 0 0 6px;padding:6px 10px}
#say input::placeholder{color:#AEB7C4}#say input:focus{outline:2px solid #5CDBD3;outline-offset:-1px}
#say button{border-radius:0 6px 6px 0;white-space:nowrap}
.st{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;white-space:nowrap;border:1px solid}
.st.talk{color:#8E56E8;background:var(--pur-s);border-color:#DCCBF7}.st.doing{color:#13A3A3;background:#E6F7F7;border-color:#B5E4E4}
.st.you{color:var(--warn);background:var(--warn-s);border-color:#F2D79A}.st.client{color:#E2589B;background:#FDEEF5;border-color:#F5C6DC}
.st.shipped{color:var(--ok);background:var(--ok-s);border-color:#B7E3CC}.st.done{color:var(--mut);background:var(--soft);border-color:var(--line)}
.wk h1{margin-bottom:2px}.wkh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.wkg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;align-items:start}
.wkg>.card{min-width:0}.wkg h2{display:flex;align-items:center;gap:8px}
@media (max-width:1000px){.wkg{grid-template-columns:minmax(0,1fr)}}
.saybig{margin-bottom:14px;background:linear-gradient(135deg,#F3F8FF,#FFFFFF);border-color:#D6E6FF}
.saybig textarea{min-height:70px;margin:8px 0}.saybig .row{align-items:center;gap:10px}
.wr{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--line);color:var(--fg)}
.wr:first-of-type{border-top:0}.wr:hover{text-decoration:none}.wr:hover b{color:var(--blue)}
.wr .grow{min-width:0;overflow-wrap:anywhere}.wr .sub{display:block}.wr .go{color:var(--blue);font-size:13px;white-space:nowrap}
.wr .ico{flex:none;width:22px;text-align:center}.wke{color:var(--mut);font-size:13px;padding:6px 0}
.live{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(43,164,113,.6);animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(43,164,113,.5)}70%{box-shadow:0 0 0 8px rgba(43,164,113,0)}100%{box-shadow:0 0 0 0 rgba(43,164,113,0)}}
.steps3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:6px}
.steps3>div{background:var(--soft);border-radius:8px;padding:10px;font-size:13px}.steps3 b{display:block;margin-bottom:2px}
@media (max-width:700px){.steps3{grid-template-columns:minmax(0,1fr)}}
.clg{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.clc{display:block;color:var(--fg)}.clc:hover{text-decoration:none;border-color:var(--blue)}.clc h3{margin:0 0 2px}
.cln{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.rqb{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;align-items:start}
@media (max-width:1200px){.rqb{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:700px){.rqb{grid-template-columns:minmax(0,1fr)}}
.rqc{background:var(--soft);border-radius:10px;padding:10px;min-width:0}.rqc h3{display:flex;justify-content:space-between;align-items:center}
.rqi{display:block;background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px;color:var(--fg);overflow-wrap:anywhere}
.rqi:hover{text-decoration:none;border-color:var(--blue)}.rqi .sub{display:block;font-size:12px}
.vcur{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.vtl{border-left:2px solid var(--line);margin-left:6px;padding-left:16px}
.vtl>div{position:relative;padding:4px 0 12px}.vtl>div:before{content:"";position:absolute;left:-22px;top:9px;width:10px;height:10px;border-radius:50%;background:var(--ok)}
.vtl ul{margin:4px 0;padding-left:18px}.vtl li{margin:2px 0;overflow-wrap:anywhere}
.lnk{display:flex;gap:6px;margin-top:8px}.lnk input{flex:1;min-width:0}.lnk button{white-space:nowrap}
.ttop{margin:10px 0 12px;border-color:#D6E6FF;background:#FAFCFF}
.ttop dl{display:grid;grid-template-columns:72px minmax(0,1fr);gap:6px 10px;margin:8px 0 0}.ttop dt{color:var(--mut);font-size:13px}.ttop dd{margin:0;overflow-wrap:anywhere}
.ttop .na.warn{color:var(--fg)}.ttop .row{margin-top:10px;gap:8px}
details.fold>summary,details.eng>summary{cursor:pointer;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;list-style:none}
details.fold>summary::-webkit-details-marker,details.eng>summary::-webkit-details-marker{display:none}
details.fold>summary:before,details.eng>summary:before{content:"▸";color:var(--mut)}details[open].fold>summary:before,details[open].eng>summary:before{content:"▾"}
.engb{display:flex;flex-direction:column;gap:12px;margin-top:12px}
@media (max-width:700px){
  #nav5{position:fixed;left:0;right:0;bottom:0;z-index:8;margin:0;padding:0 4px calc(env(safe-area-inset-bottom) + 2px);background:#fff;border-top:1px solid var(--line);border-bottom:0;justify-content:space-around;gap:0}
  #nav5 a{flex-direction:column;gap:0;padding:6px 4px 4px;font-size:12px;border-bottom:0;border-top:2px solid transparent;flex:1;align-items:center}
  #nav5 a i{display:block;font-size:18px;line-height:22px}#nav5 a.on{border-top-color:var(--blue)}#nav5 a b{position:absolute;margin-left:22px}
  #page{padding-bottom:calc(84px + env(safe-area-inset-bottom))}#nav5+#tabs[hidden]+main{margin-top:12px}
  #ast{z-index:9}#toast{bottom:calc(84px + env(safe-area-inset-bottom))}  /* the assistant covers the bottom bar; toasts sit above it */
  #say{flex:0 0 auto;max-width:none;margin:0 0 0 auto}#say input{display:none}#say button{border-radius:6px}#say button span{display:inline}
  .ttop dl{grid-template-columns:60px minmax(0,1fr)}#astOpen{bottom:78px;padding:6px 12px;font-size:13px}
  .hdr>h1.grow,.wkh>h1.grow{flex-basis:100%}.lnk{flex-wrap:wrap}.lnk select{flex:1;min-width:0}
}
"""

WORK_JS = r"""
// ---------- the workbench: 今天 / 客户 / 需求 / 版本; everything else is 工程
const NAV=[['today','今天','#/','◎'],['clients','客户','#/clients','☺'],['reqs','需求','#/reqs','☰'],['versions','版本','#/versions','◆'],['eng','工程','','⚙']];
const WK=['today','clients','c','reqs','versions','t'];
function isEng(v){return !WK.includes(v)}
function navOf(v){return v==='today'?'today':v==='clients'||v==='c'?'clients':v==='reqs'||v==='t'?'reqs':v==='versions'?'versions':'eng'}
function paintNav(){const v=curView(),cur=navOf(v);if(cur==='eng')ls.set('tmh.eng',location.hash||'#/board');
  $('#nav5').innerHTML=NAV.map(([k,l,u,ic])=>`<a href="${k==='eng'?h(ls.get('tmh.eng')||'#/board'):u}" class="${k===cur?'on':''}" data-n="${k}"><i aria-hidden="true">${ic}</i><span>${l}</span>${k==='today'&&S.need?`<b>${S.need}</b>`:''}</a>`).join('')}
const STL={talk:'理解中',doing:'做着',you:'等你看',client:'等客户确认',shipped:'已出版本',done:'已完成'};
const stChip=s=>`<span class="st ${h(s)}">${h(STL[s]||s)}</span>`;
const MODE={analyze:'分析',plan:'出方案',fix:'改代码',kb:'写知识页',diagnose:'诊断'};
const pk0=()=>S.scope!=='*'?S.scope:S.proj;
function nowStr(d){d=d||new Date();const p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`}

// ---------- 粘贴客户的话: one box on every page, the requirement conversation with the client recorded
function sayWire(){const i=$('#sayIn');if(!i)return;
  i.addEventListener('paste',()=>setTimeout(()=>{if(i.value.trim().length>=4)sayOpen()},0))}
function sayOpen(){const i=$('#sayIn'),v=i?i.value:'';if(i)i.value='';const c=location.hash.match(/^#\/c\/(\d+)/);pasteModal(v,c?+c[1]:undefined)}
async function pasteModal(text,cid){
  if(!S.projects.length)return newProject();
  let cs=[];try{cs=(await get('/api/clients')).clients}catch(e){}
  const want=cid!=null?String(cid):(ls.get('tmh.lastClient')||''),has=cs.some(c=>String(c.id)===want);
  const np=pk0()||S.proj;
  modal(`<h2>客户说了什么</h2><div class="sub">把原话粘进来，一整段聊天记录也行。AI 会拆开、复述、只问缺的；你确认一次，它就开工。</div>
   <textarea id="pmT" style="min-height:120px;margin-top:8px" placeholder="例如：刚和王总通了电话，他说请假审批通过后列表里还是草稿；另外想要请假单能导出 Excel。">${h(text||'')}</textarea>
   <div class="row" style="margin-top:8px;align-items:center;gap:10px">
    <label>谁说的 <select id="pmC"><option value="">不记客户</option>${cs.map(c=>`<option value="${c.id}" ${String(c.id)===want?'selected':''}>${h(c.name)}</option>`).join('')}<option value="__new" ${!cs.length?'selected':''}>＋ 新客户…</option></select></label>
    <input id="pmN" placeholder="客户称呼，比如 王总（某某集团）" ${cs.length?'hidden':''} style="min-width:0;flex:1">
    ${S.projects.length>1?`<label>哪个项目 <select id="pmP">${S.projects.map(p=>`<option value="${h(p.key)}" ${p.key===np?'selected':''}>${h(p.key)} · ${h(p.name)}</option>`).join('')}</select></label>`:''}</div>
   <div class="row" style="margin-top:12px;align-items:center;gap:12px"><button class="primary" id="pmGo">交给 AI 理清</button><a href="javascript:void 0" id="pmOld" class="sub">不用理清，直接填工单表单</a></div>`,true);
  if(!has&&want&&cid==null)$('#pmC').value='';
  $('#pmC').onchange=()=>{$('#pmN').hidden=$('#pmC').value!=='__new';if(!$('#pmN').hidden)$('#pmN').focus()};
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
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><h1>今天</h1><span class="sub">${S.meta.autoflow&&S.meta.autoflow.on?'自动处理开着：你确认过的需求，AI 会自己做到出版本':'自动处理关着：需求要有人手动开始'} · 上次来是 ${h(ago(since))}</span></div>
   <form class="card saybig" id="sayBig" onsubmit="event.preventDefault()"><b>客户刚说了什么？</b><textarea id="sbT" placeholder="把客户的原话、聊天记录粘进来。几件事一起说也行。"></textarea>
    <div class="row"><button class="primary" id="sbGo">交给 AI 理清</button><span class="sub">你确认一次，AI 就开工；出了版本，这里会告诉你，链接直接发给客户。</span></div></form>
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
  $('#tNeed').innerHTML=`<h2>等你 ${need.length?`<span class="ibn">${need.length}</span>`:''}</h2>`+
    (stalled.length?row('#/settings','⚠',`${stalled.length} 件新需求不会自己开始`,h(stalled[0].label),'去处理'):'')+
    (d.standing_failed||[]).map(x=>row('#/versions/'+h(x.project),'⚠',`${h(x.project)} 现在的版本没起来，客户的链接打不开`,h(x.why||'看看启动日志'),'去看')).join('')+
    (need.length?need.map(x=>row('#/t/'+h(x.key),'●',`${h(clip(x.title,60))}${cl(x)}`,`${h(x.label)}${x.note?' · “'+h(x.note)+'”':''} · ${h(x.key)} · 等了 ${waited(x.since||'')}`,h(x.action))).join('')
      :`<div class="wke">现在没有要你拍板的事。${d.now.length?'AI 做完需要你的，会出现在这里。':''}</div>`);
  const talks=d.talks,ac=d.open_ac,sign=d.others;
  $('#tCl').innerHTML=`<h2>客户那边</h2>`+
    (talks.length?talks.map(x=>row('javascript:void 0','💬',`${x.client_name?h(x.client_name)+'：':''}${h(clip(x.text,60))}`,`${x.questions?'还有 '+x.questions+' 个问题没答':'理清了，等你确认开工'} · ${h(x.project)} · ${h(ago(x.since))}`,'继续理清',`data-talk="${h(x.id)}" data-cn="${h(x.client_name)}"`)).join(''):'')+
    (ac.length?ac.map(x=>row('#/t/'+h(x.key),'?',`${h(x.title)}${cl(x)}`,`有 ${x.open} 条验收标准要和客户确认，确认前 AI 不动手 · ${h(x.key)}`,'去确认')).join(''):'')+
    (sign.length?sign.map(x=>row('#/t/'+h(x.key),'✎',`${h(x.title)}${cl(x)}`,`${h(x.label)} · ${h(x.key)} · 等了 ${waited(x.since||'')}`,'看看')).join(''):'')+
    (talks.length||ac.length||sign.length?'':'<div class="wke">没有等客户回答的问题。</div>');
  $('#tNow').innerHTML=`<h2>${d.now.length?'<span class="live"></span>':''} AI 正在做 <span class="sub" style="font-weight:400">每 5 秒刷新</span></h2>`+
    (d.now.length?d.now.map(x=>row(x.key?'#/t/'+h(x.key):'#/runs',x.status==='running'?'<span class="spin"></span>':'…',x.key?`${h(x.title)}${cl(x)}`:h(MODE[x.mode]||x.mode),
      `${x.status==='running'?'正在':'排队等着'}${h(MODE[x.mode]||x.mode)} · ${h(x.key||x.project)} · ${x.status==='running'?'已经 '+waited(x.since||''):'刚排上'}`,'')).join('')
      :`<div class="wke">现在没有在跑的。${d.auto?'新需求一确认，AI 就会开始。':'自动处理关着，到 工程 › 设置 打开。'}</div>`);
  const did=d.did,vs=d.versions,KD={release:'✓',adopt:'⇡',conflict:'!',status:'→'};
  $('#tDid').innerHTML=`<h2>上次之后</h2>`+
    (vs.length?vs.map(v=>`<div class="wr"><span class="ico">◆</span><span class="grow"><b>${h(v.project)} 出了版本 ${h(v.version)}</b><span class="sub">${v.items.map(i=>h(i.title)).join('；')} · ${h(ago(v.ts))}</span></span><span class="go">${v.standing?`<a href="${h(v.standing)}" target="_blank" rel="noopener">打开</a>`:`<a href="#/versions/${h(v.project)}">启动</a>`} · <a href="#/versions/${h(v.project)}">发给客户 ›</a></span></div>`).join(''):'')+
    (did.length?(()=>{const by={};did.forEach(x=>(by[x.key]=by[x.key]||[]).push(x));  // one line per requirement: its latest step
      return Object.values(by).slice(0,10).map(xs=>{const x=xs[0];return row('#/t/'+h(x.key),KD[x.kind]||'·',`${h(clip(x.title,60))}${cl(x)}`,`${h(x.text)}${xs.length>1?' · 之前还有 '+(xs.length-1)+' 步':''} · ${h(ago(x.ts))}`,'')}).join('')})():'')+
    (vs.length||did.length?'':`<div class="wke">上次之后还没有新进展。</div><div class="steps3"><div><b>1 粘贴客户的话</b>上面的框，或者顶栏的“客户的话”。</div><div><b>2 你确认一次</b>AI 把话拆开、问清楚，写好验收标准，你点确认它就开工。</div><div><b>3 出版本，发链接</b>做好后合进主干、出版本，在“版本”里把链接发给客户。</div></div>`)}

// ---------- 客户: who they are, what they asked, where each thing is, what they got, what is still owed
async function vClients(){
  const d=await get('/api/clients?counts=1');
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><h1 class="grow">客户</h1><button class="primary" id="clNew">＋ 新客户</button></div><div id="clF"></div>
   ${d.clients.length?`<div class="clg">${d.clients.map(c=>`<a class="card clc" href="#/c/${c.id}"><h3>${h(c.name)}</h3><div class="sub">${h(c.contact||'没有联系方式')} · ${c.projects.map(h).join('、')||'还没关联项目'}</div>
     <div class="cln">${c.counts.owed?`<span class="st you">还欠 ${c.counts.owed} 件</span>`:'<span class="st shipped">都交付了</span>'}${c.counts.client?`<span class="st client">等他确认 ${c.counts.client}</span>`:''}${c.counts.talk?`<span class="st talk">理解中 ${c.counts.talk}</span>`:''}${c.counts.shipped?`<span class="st done">已出版本 ${c.counts.shipped}</span>`:''}</div>
     <div class="sub" style="margin-top:6px">最近 ${h(ago(c.last))}</div></a>`).join('')}</div>`
    :`<div class="card"><b>还没有客户。</b><div class="sub" style="margin-top:4px">粘贴客户的话时选“新客户”，或者点右上角新建。之后他提的每件事、出给他的每个版本、还欠他什么，都在他的页面上。</div></div>`}</div>`;
  $('#clNew').onclick=()=>clientForm()}
function clientForm(c){c=c||{};const F=$('#clF');
  F.innerHTML=`<div class="card" style="margin-bottom:14px;display:flex;flex-direction:column;gap:8px"><h2 style="margin:0">${c.id?'编辑客户':'新客户'}</h2>
   <input id="cfN" placeholder="称呼，比如 王总（某某集团）" value="${h(c.name||'')}"><input id="cfC" placeholder="联系方式：电话、微信、群名" value="${h(c.contact||'')}">
   <input id="cfP" placeholder="项目代号，多个用逗号分开，比如 OA" value="${h((c.projects||[S.proj]).join(', '))}"><textarea id="cfT" placeholder="备注：他关心什么、怎么沟通" style="min-height:60px">${h(c.notes||'')}</textarea>
   <div class="row" style="gap:8px"><button class="primary" id="cfS">保存</button><button class="ghost" id="cfX">取消</button>${c.id?'<button class="danger" id="cfD" style="margin-left:auto">删除这个客户</button>':''}</div></div>`;
  $('#cfN').focus();$('#cfX').onclick=()=>F.innerHTML='';
  $('#cfS').onclick=async()=>{const b={name:$('#cfN').value,contact:$('#cfC').value,projects:$('#cfP').value,notes:$('#cfT').value};
    try{const r=c.id?await post('/api/clients/'+c.id,Object.assign({action:'update'},b)):await post('/api/clients',b);toast('已保存');location.hash='#/c/'+r.id;render()}catch(e){toast(e.message,5000)}};
  if($('#cfD'))$('#cfD').onclick=async()=>{if(!confirm('删除客户“'+c.name+'”？他的需求和工单都还在，只是不再记在他名下。'))return;try{await post('/api/clients/'+c.id,{action:'delete'});location.hash='#/clients'}catch(e){toast(e.message)}}}
async function vClient(id){
  const d=await get('/api/clients/'+encodeURIComponent(id)),c=d.client;S.client=c;
  const reqRow=x=>`<a class="wr" href="${x.key?'#/t/'+h(x.key):'javascript:void 0'}" ${x.talk?`data-talk="${h(x.talk)}" data-cn="${h(c.name)}"`:''}>${stChip(x.state)}<span class="grow"><b>${h(x.title)}</b><span class="sub">${h(x.why||'')}${x.version?' · 版本 '+h(x.version):''}${x.key?' · '+h(x.key):''}</span></span></a>`;
  const CH={web:'网页',chat:'群聊',feishu:'飞书',dingtalk:'钉钉',wecom:'企业微信',api:'接口'};
  $('#main').innerHTML=`<div class="wk"><div class="sub" style="margin-bottom:4px"><a href="#/clients">客户</a> / ${h(c.name)}</div>
   <div class="wkh"><h1 class="grow">${h(c.name)}</h1><button class="primary" id="ccSay">＋ 他又说了什么</button><button id="ccEd">编辑</button><button class="ghost" id="ccLk">关联群聊或工单</button></div>
   <div class="sub" style="margin:-8px 0 12px">${h(c.contact||'没有联系方式')} · 项目 ${c.projects.map(h).join('、')||'无'}${c.notes?' · '+h(c.notes):''}</div><div id="clF"></div><div id="ccL"></div>
   <div class="wkg"><div style="display:flex;flex-direction:column;gap:14px;min-width:0">
    <section class="card"><h2>还欠什么 ${d.owed.length?`<span class="ibn">${d.owed.length}</span>`:''}</h2>${d.owed.length?d.owed.map(reqRow).join(''):'<div class="wke">他提的事都交付了。</div>'}</section>
    <section class="card"><h2>他提过的</h2>${d.asked.length?d.asked.map(a=>`<div class="wr"><span class="ico">💬</span><span class="grow"><span class="sub">${h((a.ts||'').slice(0,16))} · ${h(CH[a.channel]||a.channel||'工单')} · ${h(a.project||'')}</span>“${h(clip(a.text||'',220))}”
      <span class="sub">${a.kind==='talk'&&!['confirmed','dropped'].includes(a.state)?`<a href="javascript:void 0" data-talk="${h(a.id)}" data-cn="${h(c.name)}">${a.questions?'还有 '+a.questions+' 个问题没答，继续理清':'理清了，去确认开工'}</a>`:(a.tickets||[]).map(k=>`<a href="#/t/${h(k)}">${h(k)}</a>`).join(' ')}</span></span></div>`).join(''):'<div class="wke">还没有记下他说过的话。点“他又说了什么”粘进来。</div>'}</section></div>
   <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
    <section class="card"><h2>每件事现在怎样</h2>${d.requirements.length?d.requirements.map(x=>reqRow(x)).join(''):'<div class="wke">还没有建成需求的事。</div>'}</section>
    <section class="card"><h2>给他的版本</h2>${d.versions.length?`<div class="vtl">${d.versions.map(v=>`<div><b>${h(v.project)} ${h(v.version)}</b> <span class="sub">${h((v.ts||'').slice(0,16))}</span><ul>${v.items.map(i=>`<li><a href="#/t/${h(i.key)}">${h(i.key)}</a> ${h(i.title)}</li>`).join('')}</ul></div>`).join('')}</div>`:'<div class="wke">还没有给他出过版本。</div>'}
     ${c.projects.length?`<div class="row" style="margin-top:6px;gap:8px">${c.projects.map(p=>`<a class="btn" href="#/versions/${h(p)}">把 ${h(p)} 现在的版本发给他</a>`).join('')}</div>`:''}</section></div></div></div>`;
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
  const item=x=>x.kind==='talk'?`<a class="rqi" href="javascript:void 0" data-talk="${h(x.id)}" data-cn="${h(x.client_name)}"><b>${h(clip(x.title,50))}</b><span class="sub">${x.client_name?h(x.client_name)+' · ':''}${h(x.why)}</span></a>`
    :`<a class="rqi" href="#/t/${h(x.key)}"><b>${h(x.title)}</b><span class="sub">${x.client_name?h(x.client_name)+' · ':''}${h(x.why||'')}${x.version?' · '+h(x.version):''}</span><span class="sub">${h(x.key)}${x.epic?' · 大需求':''}${x.parent?' · 属于 '+h(x.parent):''}</span></a>`;
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><h1 class="grow">需求</h1><span class="sub">从听到客户的话，到出版本。工单是每件事里面的执行细节。</span><button class="primary" onclick="pasteModal('')">＋ 客户的话</button></div>
   <div class="rqb">${d.columns.map(c=>`<div class="rqc"><h3><span>${stChip(c.key)}</span><span class="sub">${c.items.length}</span></h3>${c.items.length?c.items.map(item).join(''):'<div class="wke">没有</div>'}</div>`).join('')}</div></div>`;
  poll(async()=>{if(!$('.rqb')||document.hidden)return;try{const n=await get('/api/requirements?project='+encodeURIComponent(scopeQ()));if(JSON.stringify(n)!==JSON.stringify(d))vReqs()}catch(e){}},8000,'page')}

// ---------- 版本: per project, the current version clients can open, and every version with what it held
async function vVersions(key){
  const keys=key?[key.toUpperCase()]:S.scope!=='*'?[S.scope]:S.projects.map(p=>p.key);
  const all=await Promise.all(keys.map(k=>get('/api/projects/'+encodeURIComponent(k)+'/versions')));
  let cs=[];try{cs=(await get('/api/clients')).clients}catch(e){}
  $('#main').innerHTML=`<div class="wk"><div class="wkh"><h1 class="grow">版本</h1><span class="sub">验收通过的改动合进主干，就是一个新版本。“现在的版本”一直开着，链接可以直接发给客户。</span></div>
   ${all.map(v=>versionCard(v,cs)).join('')}</div>`;
  all.forEach(v=>versionWire(v));
  if(all.some(v=>v.standing.state==='starting'))setTimeout(()=>{if(curView()==='versions')vVersions(key)},4000)}
function versionCard(v,cs){const p=v.project,s=v.standing,K=h(p.key),last=(((v.versions||[])[0]||{}).items||[]).map(i=>i.client_name).find(Boolean)||'';
  const st=s.state==='up'?'<span class="ev-tag ok">开着</span>':s.state==='starting'?'<span class="ev-tag info"><span class="spin"></span> 正在启动</span>':s.state==='failed'?'<span class="ev-tag bad">没起来</span>':'<span class="ev-tag mute">没开</span>';
  return `<section class="card" style="margin-bottom:14px" id="vc-${K}"><div class="hdr" style="margin-bottom:8px"><h2 class="grow" style="margin:0">${K} · ${h(p.name)}</h2><span class="sub">${v.merge==='auto'?'验收通过后自动合并、出版本':'自动合并关着，合并要有人做'}</span></div>
   <div class="card" style="background:var(--soft)"><div class="vcur"><b>现在的版本</b>${st}<span class="sub">${s.commit?'提交 '+h(s.commit):''}${s.main?' · 主干 '+h(s.main):''}${s.stale?' · 主干已经有更新，重启后换上':''}</span><span class="grow"></span>
     ${s.url?`<a class="btn primary" href="${h(s.url)}" target="_blank" rel="noopener">打开 ↗</a>`:''}${s.configured&&s.state!=='starting'?`<button class="${s.url?'ghost':'primary'}" data-vs="start">${s.url?'重启':'启动'}</button>`:''}${s.url||s.state==='starting'?'<button class="ghost" data-vs="stop">停掉</button>':''}</div>
     ${s.why&&s.state==='failed'?`<div class="bad" style="font-size:13px;margin-top:6px">${h(s.why)}</div>`:''}
     ${s.fix?`<div class="sub" style="margin-top:8px">${h(s.fix)}</div><div class="lnk"><input data-vcmd placeholder="例如 python3 app.py {port} {prefix}" value="${h(s.configured?s.cmd:(s.cmd||''))}"><button data-vsave>保存命令</button></div>`:''}
     ${s.configured?`<div style="margin-top:10px"><b style="font-size:13px">发给客户</b> <span class="sub">客户打开链接，先看到这个版本给他做了什么，再点进去试。看不到平台的任何其他东西。</span>
      <div class="lnk"><select data-vcl><option value="">不指定客户（只说改了几项）</option>${cs.filter(c=>!c.projects.length||c.projects.includes(p.key)).map(c=>`<option value="${c.id}" ${c.name===last?'selected':''}>${h(c.name)}</option>`).join('')}</select><select data-vdays><option value="7">7 天有效</option><option value="30" selected>30 天有效</option><option value="90">90 天有效</option></select><button class="primary" data-vshare>生成链接</button></div><div data-vout></div>
      ${v.shares.length?`<div style="margin-top:8px">${v.shares.map(x=>`<div class="sub" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">给 ${h(x.client_name||'未指定')} · ${h(x.created.slice(5,16))} 发 · ${h(x.expires.slice(0,10))} 前有效 <button class="ghost" data-vrev="${h(x.id)}">收回</button></div>`).join('')}</div>`:''}</div>`:''}</div>
   <h3 style="margin-top:14px">出过的版本</h3>${v.versions.length?`<div class="vtl">${v.versions.map(x=>`<div><b>${h(x.version)}</b> <span class="sub">${h((x.ts||'').slice(0,16))} · 提交 ${h(x.commit||'')}</span><ul>${x.items.map(i=>`<li>${i.client_name?`<span class="tag">${h(i.client_name)}</span> `:''}${h(i.title)} <a href="#/t/${h(i.key)}" class="sub">${h(i.key)}</a></li>`).join('')}</ul></div>`).join('')}</div>`
    :'<div class="wke">还没有出过版本。需求验收通过、合进主干后，会出现在这里。</div>'}</section>`}
function versionWire(v){const box=$('#vc-'+v.project.key);if(!box)return;const P='/api/projects/'+encodeURIComponent(v.project.key),re=()=>vVersions(curView()==='versions'?decodeURIComponent((location.hash.split('/')[2]||'')):'');
  box.querySelectorAll('[data-vs]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await post(P+'/standing',{action:b.dataset.vs});toast(b.dataset.vs==='stop'?'已停掉':'正在启动现在的版本')}catch(e){toast(e.message,6000)}re()});
  const sv=box.querySelector('[data-vsave]');if(sv)sv.onclick=async()=>{try{await post(P+'/preview-conf',{cmd:box.querySelector('[data-vcmd]').value,ready:'/'});toast('已保存，之后每出一个版本都会自动换上');re()}catch(e){toast(e.message,6000)}};
  const sh=box.querySelector('[data-vshare]');if(sh)sh.onclick=async()=>{try{const r=await post(P+'/shares',{client:+box.querySelector('[data-vcl]').value||null,days:+box.querySelector('[data-vdays]').value});
    const url=r.url||r.path;box.querySelector('[data-vout]').innerHTML=`<div class="sub" style="margin-top:6px">${r.client_name?'给 '+h(r.client_name)+'，':''}${h(r.expires.slice(0,10))} 前有效。链接只显示这一次，复制后发到微信或群里：</div>${r.client_name?'':'<div class="bad" style="font-size:13px;margin-top:4px">没选客户：打开的人只看到“本版包含几项改进”，看不到每一项是什么。要让客户看到给他做了什么，选上他再生成。</div>'}${r.private?`<div class="bad" style="font-size:13px;margin-top:4px">${h(r.warn)}</div>`:''}<div class="lnk"><input readonly value="${h(url)}"><button class="primary" data-vcp>复制</button></div>`;
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
   <dl><dt>客户要的</dt><dd>${h(clip(said,240))}</dd><dt>下一步</dt><dd class="na ${na.tone}">${na.text}</dd></dl>
   <div class="row"><span id="ttPv"></span>${na.acc?'<button class="primary" id="ttOk">验收通过</button><button class="danger" id="ttNo">退回重改</button>':''}${t.status==='verify'&&(d.package||{}).status&&d.package.status!=='none'?'<button id="ttSend">发给客户签收</button>':''}${!['closed','verify'].includes(t.status)&&!(t.links||{}).handwork?'<button class="ghost" id="ttHw">我来写</button>':''}</div></div>`}
async function ticketTopWire(d,na){const t=d.ticket,key=t.key;
  if($('#ttOk'))$('#ttOk').onclick=()=>$('#accOk').click();
  if($('#ttNo'))$('#ttNo').onclick=()=>{const n=$('#accNote');n.scrollIntoView({block:'center',behavior:'smooth'});n.focus();n.placeholder='写明哪里不对，写好后点“验收不通过”';toast('写明哪里不对，再点“验收不通过”',4000)};
  if($('#ttSend'))$('#ttSend').onclick=()=>{const b=$('#pkLink');if(!b)return toast('证据包还没打好，稍等一下');b.click();$('#pkg').scrollIntoView({block:'start',behavior:'smooth'});const nm=S.ttClient;if(nm&&$('#pkS'))$('#pkS').value=nm};
  if($('#ttHw'))$('#ttHw').onclick=()=>{$('#engc').open=true;setTimeout(()=>{const c=$('#hwc');if(c&&!c.hidden)c.scrollIntoView({block:'start',behavior:'smooth'})},300)};
  S.ttClient='';const cid=(t.links||{}).client;
  if(cid)get('/api/clients').then(r=>{const c=r.clients.find(x=>x.id===cid);if(c&&$('#ttCl')){S.ttClient=c.name;$('#ttCl').innerHTML=`<a class="tag" href="#/c/${c.id}">${h(c.name)}</a>`}}).catch(()=>{});
  try{const p=await get('/api/tickets/'+key+'/preview');const el=$('#ttPv');if(!el||!S.cur||S.cur.ticket.key!==key)return;const st=(p.preview||{}).state;
    el.innerHTML=p.url?`<a class="btn primary" href="${h(p.url)}" target="_blank" rel="noopener">打开预览 ↗</a>`:st==='starting'?'<span class="ev-tag info"><span class="spin"></span> 预览启动中</span>':''}catch(e){}}
"""
