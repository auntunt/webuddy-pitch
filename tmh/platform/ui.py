"""The platform's web UI: one self-contained page (no build step, no CDN — works offline on an intranet).

Shared product shell, delivery workflows, engineering pages and a docked assistant.
The product name comes from --brand; the visual contract is recorded in DESIGN.md.
"""
from __future__ import annotations

from .ui_atlas import ATLAS_CSS, ATLAS_JS
from .ui_css import CSS
from .ui_work import WORK_CSS, WORK_JS
from .ui_delivery import DELIVERY_CSS, DELIVERY_JS
from .ui_theme import THEME_CSS


def page() -> str:
    return HTML.replace("/*CSS*/", CSS + ATLAS_CSS + WORK_CSS + DELIVERY_CSS + THEME_CSS).replace("/*JS*/", JS + ATLAS_JS + WORK_JS + DELIVERY_JS)


HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>闭环工作台</title><style>/*CSS*/</style></head>
<body>
<a class="skip-link" href="#main" onclick="event.preventDefault();document.getElementById('main').focus()">跳到主要内容</a>
<header id="top">
  <a class="brand" href="#/deliveries" aria-label="Webuddy 交付工作台"><svg aria-hidden="true" width="32" height="32" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="9" fill="currentColor"/><path d="m7 10 4 12 5-8 5 8 4-12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span id="brandName">闭环工作台</span></a>
  <select id="projSel" title="切换项目" aria-label="项目范围"></select>
  <nav id="svc" aria-label="服务"><a data-s="ops" href="#/board">运维<span>服务</span></a><a data-s="reform" href="#/reform">重构<span>服务</span></a></nav>
  <span class="sp"></span>
  <button class="pts" id="ptsBtn" title="点卡：只有生成类动作扣点"><span class="dot"></span><span class="w">剩余</span> <b id="ptsN">-</b> 点</button>
  <form id="say" autocomplete="off" onsubmit="event.preventDefault();sayOpen()"><input id="sayIn" placeholder="粘贴客户的话…" aria-label="粘贴客户的话"><button id="sayGo" type="submit" aria-label="录入客户需求">＋<span> 录入需求</span></button></form>
  <button id="astToggle" title="AI 助手：提问，或一句话打开页面、代填表单（Ctrl+K）" aria-controls="ast" aria-expanded="false">AI 助手 <kbd>Ctrl K</kbd></button>
  <div id="account"><button class="me" id="me" title="用户与设置"></button><a id="logout" href="/logout" hidden>退出</a></div>
</header>
<div id="wrap">
  <div id="page"><div class="sheet"><nav id="nav5" aria-label="主导航"></nav><nav id="tabs" aria-label="工程"></nav><main id="main" tabindex="-1"></main></div></div>
  <aside id="ast" aria-label="AI 助手" hidden><div class="ah" id="astHead"></div><div id="amsg"></div><div class="sugg" id="astSugg"></div>
    <div class="ain"><div class="box"><textarea id="aq" placeholder="提问，或直接说要做什么：打开知识库、给这单写评论：……、把状态改成待验证" onkeydown="astKeys(event)" aria-label="输入问题"></textarea>
      <div class="abar"><button class="ghost tog" id="astDeep" onclick="A.setMode()" aria-pressed="false">深入分析</button><button class="ghost" onclick="A.draftTicket()" title="从当前会话起草工单，核对后才提交">起草工单</button><span class="grow"></span><button class="primary" id="astSend" onclick="astSend()">发送</button></div></div><div class="foot" id="astFoot"></div></div></aside>
</div>
<button id="astOpen" hidden>AI 助手 <kbd>Ctrl K</kbd></button>
<div id="modal" hidden><div class="mbox" role="dialog" aria-label="详情与操作" aria-modal="true" tabindex="-1"><button class="mx" aria-label="关闭对话框" onclick="closeModal()">×</button><div id="mbody"></div></div></div>
<div id="toast" role="status" aria-live="polite" hidden></div>
<script>/*JS*/</script></body></html>"""

JS = r"""
const S={meta:null,proj:localStorage.getItem('tmh.proj')||'',scope:localStorage.getItem('tmh.scope')||'*',user:localStorage.getItem('tmh.user')||'',projects:[],polls:[]};
const $=s=>document.querySelector(s);
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(m,p,b){
  const o={method:m,headers:{'X-TMH':'1'}};
  if(S.user)o.headers['X-TMH-User']=encodeURIComponent(S.user);
  if(b!==undefined){o.headers['Content-Type']='application/json';o.body=JSON.stringify(b)}
  // errors read as what happened and what to do; the raw cause goes to the console for whoever debugs it
  let r;try{r=await fetch(p,o)}catch(e){console.warn(m,p,e);throw apiErr(navigator.onLine===false?'网络断了，连上后再试。':'连不上服务器：可能是网络问题，或服务没在运行。稍后再试。')}
  let j;try{j=await r.json()}catch(e){j={}}
  if(!r.ok){if(j.detail)console.warn(m,p,j.detail);throw apiErr(j.error&&r.status!==401?j.error:HTTPMSG[r.status]||HTTPMSG[Math.floor(r.status/100)*100]||'出错了（'+r.status+'），稍后再试。')}
  return j}
const apiErr=msg=>Object.assign(new Error(msg),{api:1});
const HTTPMSG={401:'登录已过期，刷新页面重新登录。',403:'没有权限做这一步，需要的话找管理员开通。',404:'要找的内容不存在，可能已被删除或改名。',
  413:'文件太大了，换小一点的再试。',429:'操作太频繁，稍等一下再试。',502:'服务器暂时不可用，稍后再试。',503:'服务器暂时不可用，稍后再试。',504:'服务器响应超时，稍后再试；如果是长任务，它可能还在后台跑。',
  500:'服务器出错了，这一步没有完成。刷新看看结果再决定要不要重试；一直这样请告诉管理员。'};
const get=p=>api('GET',p),post=(p,b)=>api('POST',p,b||{});
function toast(t,ms){const e=$('#toast');e.textContent=t;e.hidden=false;clearTimeout(e._t);e._t=setTimeout(()=>e.hidden=true,ms||2600)}
let modalReturnFocus=null;
function modal(html,wide){
  const opening=$('#modal').hidden;if(opening)modalReturnFocus=document.activeElement;
  $('#mbody').innerHTML=html;$('#modal').hidden=false;$('.mbox').classList.toggle('wide',!!wide);
  $('.mbox').setAttribute('aria-label',($('#mbody h2')||$('#mbody h1'))?.textContent||'详情与操作');
  syncDialogScope();if(opening){if($('.mbox').inert)$('#aq').focus();else $('.mbox').focus()}
}
function syncDialogScope(){
  const active=!$('#modal').hidden;document.body.classList.toggle('dialog-open',active);
  $('#page').inert=active;$('#top').inert=active;$('#astOpen').inert=active;
  const skip=$('.skip-link');if(skip)skip.inert=active;
  // The assistant can fill dialog fields, so it remains an explicit part of the keyboard scope.
  $('.mbox').inert=active&&!$('#ast').hidden&&window.matchMedia('(max-width:1100px)').matches;
  $('.mbox').setAttribute('aria-modal',String(active&&$('#ast').hidden));
}
window.addEventListener('resize',()=>{syncDialogScope();if($('.mbox').inert&&$('.mbox').contains(document.activeElement))$('#aq').focus()});
function closeModal(){const active=!$('#modal').hidden;$('#modal').hidden=true;stopPolls('modal');syncDialogScope();
  if(active){const target=modalReturnFocus;modalReturnFocus=null;if(target&&target.isConnected&&!target.closest('[hidden],[inert]'))target.focus();else $('#main').focus()}}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
document.addEventListener('keydown',e=>{
  if($('#modal').hidden)return;
  if(e.key==='Escape'){e.preventDefault();if($('.mbox').inert)A.toggle(false);else closeModal();return}
  if(e.key!=='Tab')return;
  const selector='button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]';
  const scopes=$('.mbox').inert?[]:[$('.mbox')];if(!$('#ast').hidden)scopes.push($('#ast'));
  const items=scopes.flatMap(x=>Array.from(x.querySelectorAll(selector))).filter(x=>x.tabIndex>=0&&x.getClientRects().length&&!x.closest('[hidden],[inert]'));
  if(!items.length){e.preventDefault();$('.mbox').focus();return}
  const index=items.indexOf(document.activeElement);
  // DOM order puts the assistant before the modal; explicitly move every step across both scopes.
  e.preventDefault();items[index<0?(e.shiftKey?items.length-1:0):(index+(e.shiftKey?-1:1)+items.length)%items.length].focus();
});
const L=(pairs,k)=>{const f=(pairs||[]).find(x=>x[0]===k);return f?f[1]:k};
const stLabel=k=>L(S.meta.statuses,k),tyLabel=k=>L(S.meta.types,k),prLabel=k=>L(S.meta.priorities,k),moLabel=k=>L(S.meta.modes,k);
const stPill=k=>`<span class="pill" style="background:var(--s-${k})">${h(stLabel(k))}</span>`;
const ago=ts=>{if(!ts)return'';const d=(Date.now()-new Date(ts.replace(' ','T')).getTime())/1000;
  if(d<60)return'刚刚';if(d<3600)return Math.floor(d/60)+' 分钟前';if(d<86400)return Math.floor(d/3600)+' 小时前';if(d<86400*30)return Math.floor(d/86400)+' 天前';return ts.slice(0,10)};
function stopPolls(tag){S.polls=S.polls.filter(p=>{if(!tag||p.tag===tag){clearInterval(p.id);return false}return true})}
function poll(fn,ms,tag){const id=setInterval(fn,ms);S.polls.push({id,tag:tag||'page'});return id}

// ---------- markdown (small, safe: escapes first)
function md(src){
  if(!src)return'';const lines=String(src).replace(/\r/g,'').replace(/<!--[\s\S]*?-->/g,'').split('\n');let out=[],i=0;
  const inl=s=>h(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>').replace(/\[([^\]]+)\]\((#\/t\/[A-Za-z0-9-]+)\)/g,'<a href="$2">$1</a>').replace(/\[([^\]]+)\]\(domains\/([\w-]+)\.md\)/g,'<a href="#/kb/dom%3A$2">$1</a>').replace(/\[([^\]]+)\]\(([^)\s]+\.md)\)/g,'$1');
  while(i<lines.length){let l=lines[i];
    if(/^```/.test(l)){let b=[];i++;while(i<lines.length&&!/^```/.test(lines[i]))b.push(lines[i++]);i++;out.push('<pre><code>'+h(b.join('\n'))+'</code></pre>');continue}
    let m=l.match(/^(#{1,4})\s+(.*)/);if(m){out.push(`<h${m[1].length}>${inl(m[2])}</h${m[1].length}>`);i++;continue}
    if(/^\s*\|.*\|\s*$/.test(l)){let rows=[];while(i<lines.length&&/^\s*\|.*\|\s*$/.test(lines[i]))rows.push(lines[i++]);
      rows=rows.filter(r=>!/^\s*\|[\s:|-]+\|\s*$/.test(r));out.push('<table>'+rows.map((r,j)=>'<tr>'+r.trim().replace(/^\||\|$/g,'').split('|').map(c=>j?`<td>${inl(c.trim())}</td>`:`<th>${inl(c.trim())}</th>`).join('')+'</tr>').join('')+'</table>');continue}
    if(/^\s*([-*]|\d+\.)\s+/.test(l)){const ol=/^\s*\d+\./.test(l);let it=[];while(i<lines.length&&/^\s*([-*]|\d+\.)\s+/.test(lines[i]))it.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/,''));
      out.push((ol?'<ol>':'<ul>')+it.map(x=>'<li>'+inl(x)+'</li>').join('')+(ol?'</ol>':'</ul>'));continue}
    if(/^>\s?/.test(l)){let b=[];while(i<lines.length&&/^>\s?/.test(lines[i]))b.push(lines[i++].replace(/^>\s?/,''));out.push('<blockquote>'+inl(b.join(' '))+'</blockquote>');continue}
    if(!l.trim()){i++;continue}
    let p=[];while(i<lines.length&&lines[i].trim()&&!/^(#{1,4}\s|```|\s*([-*]|\d+\.)\s|\s*\||>)/.test(lines[i]))p.push(lines[i++]);
    if(!p.length)p.push(lines[i++]);out.push('<p>'+inl(p.join(' '))+'</p>')}
  return '<div class="md">'+out.join('')+'</div>'}
function diffHtml(d){return '<pre class="diff">'+d.split('\n').map(l=>{const c=l.startsWith('+')&&!l.startsWith('+++')?'a':l.startsWith('-')&&!l.startsWith('---')?'d':(l.startsWith('@@')||l.startsWith('diff '))?'h':'';return c?`<span class="${c}">${h(l)}</span>`:h(l)}).join('\n')+'</pre>'}

// ---------- shell
// Two services on one base: 运维 (tickets from people, monitoring and alerts) and 重构 (reform plans released in
// waves). Each has its own pages and its own numbers; the knowledge base, the map, agent runs and settings serve both.
const SVC={ops:{name:'运维服务',tabs:[['home','工单看板','#/board'],['tickets','工单列表','#/tickets'],['lead','运维成效','#/lead'],['overview','监控总览','#/overview'],['eff','提效报告','#/eff'],['learn','闭环改进','#/learn'],['int','外部系统','#/int']]},
  reform:{name:'重构服务',tabs:[['reform','改造计划','#/reform'],['rtickets','改造工单','#/rtickets'],['rdeps','依赖清单','#/rdeps']]}};
const SHARED=[['atlas','项目图谱','#/atlas'],['kb','知识库','#/kb'],['map','架构与依据','#/map'],['runs','智能体运行','#/runs'],['settings','设置','#/settings']];
const TOP=['home','tickets','lead','kb','reform','rtickets','rdeps'];
S.svc=localStorage.getItem('tmh.svc')==='reform'?'reform':'ops';
function svcOf(view){for(const k in SVC)if(SVC[k].tabs.some(t=>t[0]===view))return k;return S.svc}
document.addEventListener('click',e=>{const d=document.querySelector('#tabs .tmore');if(d&&d.open&&!d.contains(e.target))d.open=false});
function paintTabs(tab){const s=S.svc,eng=isEng(curView());document.body.classList.toggle('svc-reform',s==='reform'&&eng);ls.set('tmh.svc',s);
  paintNav();$('#tabs').hidden=!eng;$('#svc').hidden=!eng;
  document.querySelectorAll('#svc a').forEach(a=>a.classList.toggle('on',a.dataset.s===s));
  const a=([k,l,u])=>`<a data-r="${k}" href="${u}" class="${k===tab?'on':''}" ${k===tab?'aria-current="page"':''}>${l}</a>`;
  // Four tabs people use daily stay in sight; the rest sit under 更多, which takes the open page's name.
  const all=SVC[s].tabs.concat(SHARED),top=all.filter(t=>TOP.includes(t[0])),rest=all.filter(t=>!TOP.includes(t[0]));
  const cur=rest.find(t=>t[0]===tab),grp=(n,ts)=>ts.length?`<div class="tmg"><span>${n}</span>${ts.map(a).join('')}</div>`:'';
  $('#tabs').innerHTML=top.map(a).join('')+`<details class="tmore${cur?' on':''}"><summary><b>${cur?h(cur[1]):'更多'}</b><i>▾</i></summary><div class="tmp">${grp(SVC[s].name,rest.filter(t=>SVC[s].tabs.includes(t)))}${grp('共用',rest.filter(t=>SHARED.includes(t)))}</div></details>`;
  const d=$('#tabs .tmore');d.querySelectorAll('a').forEach(x=>x.onclick=()=>setTimeout(()=>d.open=false));
  $('#tabs').insertAdjacentHTML('beforeend',`<button class="ghost tnew" id="newBtn">＋ ${s==='reform'?'新建改造计划':'新建工单'}</button>`);
  $('#newBtn').onclick=()=>{if(S.svc!=='reform')return newTicket();S.rfNew=1;if(curView()==='reform')vReform();else location.hash='#/reform'}}
async function boot(){
  try{S.meta=await get('/api/meta')}catch(e){$('#main').innerHTML='<div class="empty">'+h(e.message)+'</div>';return}
  if(S.meta.login)S.user=S.meta.user;else if(!S.user)S.user=S.meta.user||'';
  document.title=S.meta.brand;$('#brandName').textContent=S.meta.brand;
  $('#me').textContent=S.user||'未设置用户';$('#me').onclick=()=>location.hash='#/settings';
  $('#me').setAttribute('aria-label',(S.user||'当前用户')+'，用户与设置');$('#logout').hidden=!S.meta.login;
  await loadProjects();
  $('#projSel').onchange=e=>{const v=e.target.value;if(v==='__new'){newProject();paintSel();return}
    if(v==='*'){S.scope='*';ls.set('tmh.scope','*');if(!isCross())location.hash='#/';else render();return}
    if(isCross()){S.scope=v;ls.set('tmh.scope',v)}setProj(v);render()};
  $('#ptsBtn').onclick=showPoints;sayWire();
  $('#astToggle').onclick=()=>A.toggle();$('#astOpen').onclick=()=>{A.toggle(true);A.focus()};
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&!e.altKey&&e.key.toLowerCase()==='k'){e.preventDefault();if(A.open&&document.activeElement===$('#aq'))A.toggle(false);else{A.toggle(true);A.focus()}}});
  A.init();
  window.addEventListener('hashchange',render);render()}
async function loadProjects(){
  S.projects=await get('/api/projects');
  if(!S.projects.find(p=>p.key===S.proj))S.proj=S.projects[0]?S.projects[0].key:'';
  if(S.scope!=='*'&&!S.projects.find(p=>p.key===S.scope))S.scope='*';
  paintSel();loadPoints()}
// Work that spans projects (board, list, 运维成效) shows every project unless narrowed; pages about one codebase
// (knowledge base, map, runs…) follow the project of whatever you opened last, so nobody has to pick one by hand.
const CROSS=['home','board','tickets','lead','t','today','clients','c','reqs','versions','deliveries','delivery'];
function curView(){return (location.hash||'#/').slice(2).split('/')[0]||'deliveries'}
function isCross(){return CROSS.includes(curView())}
function paintSel(){const cross=isCross()&&!['t','delivery'].includes(curView()),v=cross?S.scope:S.proj;
  $('#projSel').innerHTML=(cross?`<option value="*" ${v==='*'?'selected':''}>全部项目（${S.projects.length}）</option>`:'')+S.projects.map(p=>`<option value="${h(p.key)}" ${p.key===v?'selected':''}>${h(p.key)} · ${h(p.name)}</option>`).join('')+(cross?'':'<option value="*">全部项目</option>')+'<option value="__new">＋ 添加项目…</option>';
  $('#projSel').title=cross?(['deliveries','delivery'].includes(curView())?'查看项目范围（默认全部）':'看哪些项目的工单（默认全部）'):'这一页属于哪个项目'}
function setProj(k){if(!k||k===S.proj)return;S.proj=k;ls.set('tmh.proj',k);A.reset();loadPoints()}
const scopeQ=()=>S.scope==='*'?'*':S.scope;
async function loadPoints(){if(!S.proj){$('#ptsN').textContent='-';return}try{const r=await get('/api/projects/'+S.proj+'/points');S.points=r;$('#ptsN').textContent=r.balance.toLocaleString();if(A.open)A.paintFoot()}catch(e){}}
function render(){
  stopPolls();if(S.meta)document.title=S.meta.brand;const r=(location.hash||'#/').slice(2).split('/');const view=r[0]||'deliveries';
  document.body.classList.toggle('delivery-surface',['deliveries','delivery'].includes(view));
  if(view!=='t')S.svc=svcOf(view==='board'?'home':view);
  paintTabs(view==='t'?(S.svc==='reform'?'rtickets':'home'):view==='board'?'home':view);
  if(!S.proj&&!['settings','deliveries','delivery'].includes(view)){$('#main').innerHTML=`<div style="max-width:640px;padding:20px 0"><h1>欢迎使用 ${h(S.meta.brand)}</h1><p class="sub">从一个新产品开始，或连接已有项目继续开发。</p><a class="btn primary" href="#/deliveries/new">创建新项目</a> <button onclick="newProject()">连接已有项目</button></div>`;return}
  const V={deliveries:()=>vDeliveries(r[1]||''),delivery:()=>vDelivery(decodeURIComponent(r[1]||''),decodeURIComponent(r[2]||'')),today:vToday,clients:vClients,c:()=>vClient(decodeURIComponent(r[1]||'')),reqs:vReqs,versions:()=>vVersions(decodeURIComponent(r[1]||'')),board:vHome,home:vHome,lead:vLead,overview:vOverview,tickets:vTickets,t:()=>vTicket(decodeURIComponent(r[1]||''),r[2]||''),eff:vEff,map:()=>vMap(decodeURIComponent(r[1]||'')),matters:()=>{location.hash='#/today'},atlas:()=>vAtlas(decodeURIComponent(r.slice(1).join('/'))),kb:()=>vKb(decodeURIComponent(r.slice(1).join('/'))),runs:vRuns,learn:vLearn,reform:vReform,rtickets:vRtickets,rdeps:vRdeps,int:vInt,settings:vSettings}[view]||(()=>{location.hash='#/deliveries'});
  if(view!=='t')A.setTicket(null);
  paintSel();
  if(view==='atlas'&&$('#atl')){S.renderP=Promise.resolve(vAtlas(decodeURIComponent(r.slice(1).join('/')))).then(()=>A.paintCtx());return}
  if(view==='kb'&&r[1]&&$('#kbTree')){S.renderP=Promise.resolve(kbRead(decodeURIComponent(r.slice(1).join('/')))).then(()=>A.paintCtx());return}
  $('#main').innerHTML='<div class="empty"><span class="spin"></span></div>';
  // a slow page that finishes after the user already moved on would paint over the newer one: draw the current page again
  const rt=S.rt=(S.rt||0)+1;
  S.renderP=Promise.resolve(V()).then(()=>{if(rt!==S.rt)return render();remember();A.paintCtx()}).catch(e=>{if(!e.api)console.error(e);$('#main').innerHTML='<div class="empty">'+h(e.api?e.message:'这一页没能显示出来，刷新试试；还不行请告诉管理员。')+'<div style="margin-top:12px"><button onclick="render()">再试一次</button></div></div>'})}
// pages visited lately, per project: the assistant's jump list
function remember(){const r=location.hash||'#/';const t=(($('#main h1')||{}).textContent||'').trim();if(!S.proj||!t)return;
  const k='tmh.recent.'+S.proj;let L=[];try{L=JSON.parse(ls.get(k)||'[]')}catch(e){}
  const lab=r.startsWith('#/t/')?r.slice(4).split('/')[0]+' '+t:t;L=[{r,t:lab.slice(0,40)}].concat(L.filter(x=>x.r!==r)).slice(0,8);ls.set(k,JSON.stringify(L))}
function recents(){try{return JSON.parse(ls.get('tmh.recent.'+S.proj)||'[]')}catch(e){return[]}}
async function showPoints(){
  const r=await get('/api/projects/'+S.proj+'/points');
  const L={ask:'助手起草',analyze:'分析定位',plan:'修改方案',fix:'修改代码',kb:'撰写知识页'};
  modal(`<h2>点卡 · ${h(S.proj)}</h2><div class="row" style="align-items:baseline;gap:10px"><b style="font-size:30px;font-variant-numeric:tabular-nums">${r.balance.toLocaleString()}</b><span class="sub">剩余点数</span></div>
   <div class="hint" style="margin:10px 0">点卡按实际消耗计：只有“生成”类动作扣点（助手起草、分析定位、修改方案、修改代码、撰写知识页），看工单、查依据、打开详情都不扣。单价待定（19 号确认），现在是演示价。</div>
   <h3>演示价</h3><div class="tags" style="margin-bottom:12px">${Object.entries(r.prices).map(([k,v])=>`<span class="ev-tag mute">${h(L[k]||k)} ${v} 点</span>`).join('')}</div>
   <h3>最近记录</h3><div class="tw"><table class="t"><tr><th>时间</th><th>动作</th><th>人</th><th style="text-align:right">点数</th></tr>${r.log.map(x=>`<tr><td class="sub">${h(x.ts.slice(5,16))}</td><td>${h(x.reason)}${x.run_id?` <a href="javascript:void 0" onclick="showRun(${x.run_id})">#${x.run_id}</a>`:''}</td><td>${h(x.author)}</td><td style="text-align:right;font-variant-numeric:tabular-nums;color:${x.delta<0?'var(--bad)':'var(--ok)'}">${x.delta>0?'+':''}${x.delta}</td></tr>`).join('')}</table></div>
   <div class="row" style="margin-top:12px;align-items:center"><input id="ptAdd" type="number" placeholder="充值点数" style="width:140px"><button id="ptGo">充值（演示）</button></div>`,true);
  $('#ptGo').onclick=async()=>{try{await post('/api/projects/'+S.proj+'/points',{delta:+$('#ptAdd').value,reason:'充值（演示）'});closeModal();loadPoints();toast('已充值')}catch(e){toast(e.message)}}}

// ---------- closed-loop board (home)
const NODES=[
  {s:'new',l:'已提交',role:'报告人 / 售后 / 驻场',c:'var(--s-new)',ic:'doc'},
  {s:'analyzing',l:'分析中',role:'智能体定位',c:'var(--s-analyzing)',ic:'search'},
  {s:'confirm',l:'待确认',role:'技术负责人',c:'var(--s-confirm)',ic:'shield'},
  {s:'doing',l:'处理中',role:'开发 / 智能体改码',c:'var(--s-doing)',ic:'code'},
  {s:'verify',l:'待验证',role:'测试 / 验收人',c:'var(--s-verify)',ic:'flask'},
  {s:'closed',l:'已闭环',role:'闭环完成',c:'var(--s-closed)',ic:'check'}];
const GLYPH={doc:'<path d="M-7-10h9l5 5v15h-14z M2-10v5h5 M-3 0h7 M-3 4h7" />',search:'<circle cx="-2" cy="-2" r="6.5"/><path d="M3 3l6 6"/>',
  shield:'<path d="M0-11l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10v-6z M-3.5 0l2.5 2.5 4.5-5"/>',code:'<path d="M-4-6l-6 6 6 6 M4-6l6 6-6 6 M2-9l-4 18"/>',
  flask:'<path d="M-3-10h6 M-2-10v7l-7 12h18l-7-12v-7 M-5 4h10"/>',check:'<circle r="10"/><path d="M-4.5 0l3 3 6-6.5"/>'};
function gaugeSvg(p,col,sz){sz=sz||62;const r=sz/2-5,c=2*Math.PI*r;return `<svg width="${sz}" height="${sz}" viewBox="0 0 ${sz} ${sz}" role="img" aria-label="${p}%"><circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="#3F4D66" stroke-width="5"/><circle cx="${sz/2}" cy="${sz/2}" r="${r}" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c*p/100} ${c}" transform="rotate(-90 ${sz/2} ${sz/2})"/><text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" style="fill:#fff;font-size:${sz>56?15:13}px;font-weight:700">${p}%</text></svg>`}
async function vHome(){
  const [L,ts]=await Promise.all([get('/api/projects/'+encodeURIComponent(scopeQ())+'/loop'),get('/api/tickets?svc=ops&project='+encodeURIComponent(scopeQ()))]);
  S.loop=L;S.home=S.home||{view:'ring',sel:''};$('#ptsN').textContent=L.points.toLocaleString();
  if(!L.total){$('#main').innerHTML=firstRun(L);poll(async()=>{if(!$('#first'))return;try{const n=await get('/api/projects/'+encodeURIComponent(scopeQ())+'/loop');if(n.total||n.kb_built!==L.kb_built)vHome()}catch(e){}},15000,'page');return}
  const gc=['#52C41A','#4096FF','#9254DE','#36CFC9'];
  const ic=(bg,svg)=>`<div class="ic" style="background:${bg}"><svg width="20" height="20" viewBox="-12 -12 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${svg}</svg></div>`;
  $('#main').innerHTML=`<div id="inbox"></div><div id="rels"></div><div class="band"><div class="gauges">${L.metrics.map((m,i)=>`<div class="gauge">${gaugeSvg(m.pct,gc[i])}<div style="min-width:0"><div class="gl">${h(m.label)}</div><div class="gs">${h(m.sub)}</div></div></div>`).join('')}</div>
   <div class="caps"><div class="cap" data-sel="open">${ic('#1677FF','<path d="M2-10l-8 12h7l-2 8 8-12h-7z"/>')}<div><b>${L.open}</b><span>流转中</span></div></div>
    <div class="cap" data-sel="failed">${ic('#F5222D','<circle r="9"/><path d="M-3.5-3.5l7 7M3.5-3.5l-7 7"/>')}<div><b>${L.failed}</b><span>失败</span></div></div>
    <div class="cap" data-sel="closed">${ic('#52C41A','<circle r="9"/><path d="M-4 0l3 3 5.5-6"/>')}<div><b>${L.closed}</b><span>已关闭</span></div></div>
    <div class="today">今日新建 ${L.today.created} · 今日闭环 ${L.today.closed}</div></div>
   ${L.waiting?`<div class="catch"><span><b>${L.waiting} 张已有工单还没走自动处理</b>（自动处理只接新进来的工单；这些是之前就在、或自动处理关着时进来的）。交给它后会从各自停下的那一步接着做，同时最多跑 2 张。</span><button class="primary" id="catchUp">全部交给自动处理</button></div>`:''}
   <div class="insight"><b>智能洞察</b><span>${S.scope==='*'&&L.projects>1?h(L.projects+' 个项目合计：'):''}${h(L.insight)}</span></div></div>
  <div class="viewbar"><div class="seg"><button data-v="ring" class="${S.home.view==='ring'?'on':''}">闭环视图</button><button data-v="board" class="${S.home.view==='board'?'on':''}">列表看板</button></div><span class="grow"></span><span class="sub">最后更新 ${new Date().toTimeString().slice(0,8)}</span><button id="hRef">刷新</button></div>
  <div id="hView"></div><div id="hList" style="margin-top:14px"></div>`;
  document.querySelectorAll('.viewbar .seg button').forEach(b=>b.onclick=()=>{S.home.view=b.dataset.v;vHome()});
  $('#hRef').onclick=()=>vHome();rels();
  if($('#catchUp'))$('#catchUp').onclick=async()=>{try{const r=await post('/api/projects/'+encodeURIComponent(scopeQ())+'/catchup',{});toast(`已交给自动处理 ${r.queued} 张，按顺序开始`);vHome()}catch(e){toast(e.message)}};
  document.querySelectorAll('.cap').forEach(c=>c.onclick=()=>homeList(c.dataset.sel,ts));
  if(S.home.view==='ring'){$('#hView').innerHTML=ringSvg(L)+'<div class="ringhint">点击环上的数字看该节点的工单，再点单条工单看详情</div>';
    document.querySelectorAll('.ring [data-s]').forEach(n=>n.addEventListener('click',()=>homeList(n.dataset.s,ts)))}
  else{$('#hView').innerHTML=boardHtml(ts);bindBoard()}
  if(S.home.sel)homeList(S.home.sel,ts,true);
  paintInbox();
  poll(async()=>{if(!$('#hView'))return;try{const n=await get('/api/projects/'+encodeURIComponent(scopeQ())+'/loop');if(JSON.stringify(n.by_status)!==JSON.stringify(S.loop.by_status)||n.failed!==S.loop.failed||n.waiting!==S.loop.waiting)vHome();else paintInbox()}catch(e){}},15000,'page')}
// A board with no tickets is a ring of zeros; a first visit gets the three steps to a first closed loop instead.
function firstRun(L){const has=S.projects.length,kb=L.kb_built,auto=(!S.meta.autoflow||S.meta.autoflow.on)&&(S.meta.agents||[]).some(a=>a.available);
  const step=(n,done,title,body,btn)=>`<div class="frs${done?' done':''}"><span class="frn">${done?'✓':n}</span><div class="grow" style="min-width:0"><b>${title}</b><div class="sub">${body}</div></div>${done?'':btn||''}</div>`;
  return `<div class="card first" id="first"><h2>三步跑通第一张工单</h2><div class="sub" style="margin:-4px 0 12px">工单进来后，智能体先定位到业务和代码，再出方案和改动；需要人拍板的那一步会出现在首页“等你处理”。</div>
   ${step(1,has,'接入项目代码',has?'已接入 '+S.projects.map(p=>h(p.name||p.key)).join('、'):'填本机项目目录，工单编号会用它的代号开头。','<button class="primary" onclick="newProject()">添加项目</button>')}
   ${step(2,kb,'建设知识库（推荐）',kb?'已构建，工单会自动关联到业务流、表和代码位置。':'从代码解析出业务域、表和入口，分析会更准。不建也能先建工单。',has?'<a class="btn" href="#/kb">去建设</a>':'')}
   ${step(3,false,'提交第一张工单','用一句话描述现象就行，比如“月结凭证没传到 NC”。'+(auto?'系统会追问缺的信息，然后自动开始分析。':'现在还不会自动分析：'+(S.meta.autoflow&&!S.meta.autoflow.on?'自动处理关着。':'这台机器上没有可用的智能体，到“设置”里配置一个。')),has?'<button class="primary" onclick="newTicket()">新建工单</button>':'')}
   <div class="sub frk" style="margin-top:10px">也可以按 <kbd>Ctrl K</kbd> 打开 AI 助手，直接说“帮我建一张工单：……”。</div></div>`}
// What waits for me right now, with the one thing to do on each; what waits on people outside the team, apart.
// The board above says how the loop is doing; this says where to start.
async function paintInbox(){
  let d;try{d=await get('/api/projects/'+encodeURIComponent(scopeQ())+'/inbox')}catch(e){return}
  const box=$('#inbox');if(!box)return;S.inbox=d;S.home.open=S.home.open||{};
  // tickets nobody will start share one cause (the line is off / no agent): one line for the cause, not a row each
  const stalled=d.mine.filter(x=>x.reason==='stalled');d=Object.assign({},d,{mine:d.mine.filter(x=>x.reason!=='stalled')});
  document.title=(d.mine.length?`(${d.mine.length}) `:'')+S.meta.brand;
  const PR={urgent:['bad','紧急'],high:['warn','高'],normal:['mute','中'],medium:['mute','中'],low:['mute','低']};
  // grouped by what is asked of you, the most pressing kind first; a group shows its 3 most urgent and folds the rest
  const G=[['returned','bad','甲方退回'],['rejected','bad','验收没通过'],['failed','bad','智能体没跑成'],['expired','warn','签收链接过期'],['verify','warn','等你验收'],['review','info','改好了，等你审阅'],['confirm','info','分析出结论，等你确认']];
  const gname=k=>(G.find(g=>g[0]===k)||[])[2];
  const row=x=>{const sub=[x.label!==gname(x.reason)?h(x.label):'',x.note?'“'+h(x.note)+'”':'',x.since?'等了 '+waited(x.since):'',h(x.assignee)].filter(Boolean).join(' · ');
    return `<a class="ibx" href="#/t/${h(x.key)}"><span class="ev-tag ${(PR[x.priority]||PR.normal)[0]}">${(PR[x.priority]||PR.normal)[1]}</span>
    <span class="grow" style="min-width:0"><b>${h(x.key)}</b> ${h(x.title)}${sub?`<span class="sub ibw">${sub}</span>`:''}</span><span class="ibgo">${h(x.action)} ›</span></a>`};
  const groups=G.map(([k,tone,name])=>{const xs=d.mine.filter(x=>x.reason===k);if(!xs.length)return '';const all=S.home.open[k]||xs.length<=3;
    return `<div class="ibg"><div class="ibh"><span class="ev-tag ${tone}">${name}</span><span class="sub">${xs.length} 张</span></div>${(all?xs:xs.slice(0,3)).map(row).join('')}${all?'':`<button class="ghost ibmore" data-g="${k}">还有 ${xs.length-3} 张</button>`}</div>`}).join('');
  box.innerHTML=`<div class="card inbox"><div class="hdr" style="margin-bottom:4px"><h2 class="grow" style="margin:0">等你处理${d.mine.length?` <span class="ibn">${d.mine.length}</span>`:''}</h2>
     <span class="sub">${d.running?`<span class="spin"></span> 智能体正在处理 ${d.running} 张`:''}</span></div>
   ${stalled.length?`<a class="ibx ibst" href="#/settings"><span class="ev-tag warn">没人接手</span><span class="grow" style="min-width:0"><b>${stalled.length} 张新工单不会自动开始</b><span class="sub ibw">${h(stalled[0].label)}。打开后会从各自停下的那一步接着做；也可以逐张手动开始。</span></span><span class="ibgo">${d.auto?'配置智能体':'去打开'} ›</span></a>`:''}
   ${d.mine.length?groups:`<div class="sub" style="padding:6px 0">现在没有要你处理的事。${d.running?'智能体在跑的工单有结果后，需要你的会出现在这里。':d.open?'在流转的工单都还没到需要人的那一步。':'新工单进来后，需要人的那一步会出现在这里。'}${!d.auto?' 自动处理现在关着，新工单要有人手动开始。':!d.agent?' 这台机器上还没有可用的智能体，新工单不会自动分析，到“设置”里配置一个。':''}</div>`}
   ${d.others.length?`<details class="ibo"><summary class="sub">等甲方签收 ${d.others.length} 张</summary>${d.others.map(row).join('')}</details>`:''}</div>`;
  box.querySelectorAll('.ibmore').forEach(b=>b.onclick=()=>{S.home.open[b.dataset.g]=1;paintInbox()})}
function waited(ts){const m=Math.max(0,(Date.now()-new Date(ts.replace(' ','T')).getTime())/6e4);
  return m<60?Math.max(1,Math.round(m))+' 分钟':m<1440?Math.round(m/60)+' 小时':Math.round(m/1440)+' 天'}
function ringSvg(L){
  const W=620,cx=310,cy=300,R=215,by=L.by_status||{},pct=L.metrics[0].pct;
  let g=`<svg class="ring" viewBox="0 0 ${W} 610" role="img" aria-label="闭环视图：闭环完成率 ${pct}%">`;
  g+=`<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#E4E9F2" stroke-width="10"/>`;
  NODES.forEach((n,i)=>{const a0=(-90+i*60+12)*Math.PI/180,a1=(-90+(i+1)*60-12)*Math.PI/180;
    g+=`<path d="M${cx+R*Math.cos(a0)} ${cy+R*Math.sin(a0)} A${R} ${R} 0 0 1 ${cx+R*Math.cos(a1)} ${cy+R*Math.sin(a1)}" fill="none" stroke="${n.c}" stroke-width="4" stroke-dasharray="14 9" opacity=".75"/>`});
  const r0=118,c0=2*Math.PI*96;
  g+=`<circle cx="${cx}" cy="${cy}" r="${r0}" fill="#F7F9FC" stroke="#E4E9F2"/><circle cx="${cx}" cy="${cy}" r="96" fill="none" stroke="#E4E9F2" stroke-width="13"/>
   <circle cx="${cx}" cy="${cy}" r="96" fill="none" stroke="url(#gg)" stroke-width="13" stroke-linecap="round" stroke-dasharray="${c0*pct/100} ${c0}" transform="rotate(-90 ${cx} ${cy})"/>
   <defs><linearGradient id="gg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#36CFC9"/><stop offset="1" stop-color="#52C41A"/></linearGradient></defs>
   <text x="${cx}" y="${cy-22}" text-anchor="middle" style="font-size:38px;font-weight:700;fill:var(--fg)">${pct}%</text>
   <text x="${cx}" y="${cy+4}" text-anchor="middle" style="font-size:12px">闭环完成率</text>
   <text x="${cx}" y="${cy+30}" text-anchor="middle" style="font-size:12px">共 ${L.total} 单 · 已闭环 ${L.closed}</text>
   <g data-s="failed" style="cursor:pointer"><rect x="${cx-46}" y="${cy+44}" width="92" height="24" rx="12" fill="#FDECEC" stroke="#F5B5B7"/><text x="${cx}" y="${cy+60}" text-anchor="middle" style="font-size:12px;fill:#D4380D">失败 ${L.failed}</text></g>`;
  NODES.forEach((n,i)=>{const a=(-90+i*60)*Math.PI/180,x=cx+R*Math.cos(a),y=cy+R*Math.sin(a),k=by[n.s]||0;
    g+=`<g class="node" data-s="${n.s}" transform="translate(${x} ${y})"><title>${n.l} ${k} 单</title><circle class="halo" r="44" fill="${n.c}" opacity=".15"/><circle r="34" fill="${n.c}"/>
     <g fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" transform="scale(1.35)">${GLYPH[n.ic]}</g>
     <g class="badge" transform="translate(27 -27)"><circle r="13" fill="#fff" stroke="${n.c}" stroke-width="2"/><text text-anchor="middle" dy="4" style="font-size:12px;font-weight:700;fill:var(--fg)">${k}</text></g>
     <text class="nl" text-anchor="middle" y="56">${n.l}</text><text class="nr" text-anchor="middle" y="72" style="fill:${n.c}">${n.role}</text></g>`});
  return `<div class="ringwrap">${g}</svg></div>`}
function homeList(sel,ts,quiet){
  S.home.sel=sel;const f=new Set(S.loop.failed_ids||[]);
  const pick={open:t=>t.status!=='closed',failed:t=>f.has(t.id),closed:t=>t.status==='closed'}[sel]||(t=>t.status===sel);
  const name={open:'流转中',failed:'失败（最近一次智能体运行失败）',closed:'已关闭'}[sel]||(NODES.find(n=>n.s===sel)||{}).l||sel;
  const list=ts.filter(pick);
  $('#hList').innerHTML=`<div class="hdr" style="margin-bottom:8px"><h2 style="margin:0" class="grow">${h(name)} · ${list.length} 单</h2><button class="ghost" onclick="S.home.sel='';$('#hList').innerHTML=''">收起</button></div>`+(list.length?`<div class="tw">${ticketTable(list)}</div>`:'<div class="empty">这个节点没有工单</div>');
  if(!quiet)$('#hList').scrollIntoView({behavior:'smooth',block:'nearest'})}

// ---------- overview
async function vOverview(){
  const d=await get('/api/projects/'+S.proj);const s=d.stats,k=d.kb,p=d.project;
  const n=x=>s.by_status[x]||0,open=Object.entries(s.by_status).filter(([a])=>a!=='closed').reduce((a,[,b])=>a+b,0);
  const kpi=(l,v,c)=>`<div class="card kpi"><div class="n" style="color:${c||'inherit'}">${v}</div><div class="l">${l}</div></div>`;
  let html=`<div class="hdr"><div class="grow"><h1>${h(p.name)}</h1><div class="sub">${h(p.key)} · ${h(p.root)}</div></div></div>
  <div class="grid4" style="margin-bottom:16px">${kpi('未关闭工单',open)}${kpi('待确认（分析已出结论）',n('confirm'),'var(--warn)')}${kpi('处理中',n('doing'),'var(--acc)')}${kpi('待验证',n('verify'),'var(--s-verify)')}</div>
  <div class="grid2"><div style="display:flex;flex-direction:column;gap:16px">
  <div class="card"><h2>近 14 天工单</h2>${chart(s)}</div>
  <div class="card"><h2>最近更新的工单</h2>${ticketTable(d.recent,true)}</div></div>
  <div style="display:flex;flex-direction:column;gap:16px">${kbCard(k)}
  <div class="card"><h2>未关闭工单的优先级</h2>${priBars(s.open_by_priority)}</div>
  <div class="card"><h2>最近的智能体运行</h2>${runList(d.runs)}</div></div></div>`;
  $('#main').innerHTML=html}
function chart(s){
  const days=[];for(let i=13;i>=0;i--){const d=new Date(Date.now()-i*864e5);days.push(d.toISOString().slice(0,10))}
  const c=Object.fromEntries(s.created_by_day),x=Object.fromEntries(s.closed_by_day);
  const mx=Math.max(1,...days.map(d=>Math.max(c[d]||0,x[d]||0)));const W=560,H=150,bw=W/14;
  let g='';days.forEach((d,i)=>{const a=(c[d]||0)/mx*(H-24),b=(x[d]||0)/mx*(H-24);
    g+=`<rect x="${i*bw+4}" y="${H-18-a}" width="${bw/2-5}" height="${a}" rx="2" fill="var(--acc2)"><title>${d} 新建 ${c[d]||0}</title></rect><rect x="${i*bw+bw/2}" y="${H-18-b}" width="${bw/2-5}" height="${b}" rx="2" fill="var(--ok)"><title>${d} 关闭 ${x[d]||0}</title></rect>`;
    if(i%2===0)g+=`<text x="${i*bw+bw/2}" y="${H-4}" text-anchor="middle">${d.slice(5)}</text>`});
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" role="img" aria-label="近14天新建与关闭">${g}</svg><div class="legend"><span><i style="background:var(--acc2)"></i>新建</span><span><i style="background:var(--ok)"></i>关闭</span><span>最高 ${mx} 张/天</span></div>`}
function priBars(o){const tot=Object.values(o).reduce((a,b)=>a+b,0);if(!tot)return'<div class="sub">没有未关闭的工单</div>';
  const col={urgent:'var(--bad)',high:'var(--acc)',normal:'var(--acc2)',low:'var(--s-new)'};
  return `<div class="stack">${S.meta.priorities.map(([k])=>o[k]?`<div style="width:${o[k]/tot*100}%;background:${col[k]}" title="${prLabel(k)} ${o[k]}"></div>`:'').join('')}</div><div class="legend" style="margin-top:8px">${S.meta.priorities.map(([k,l])=>`<span><i style="background:${col[k]}"></i>${l} ${o[k]||0}</span>`).join('')}</div>`}
function kbCard(k){
  if(!k.built)return `<div class="card"><h2>业务知识库</h2><div class="hint">这个项目还没有知识库。到“知识库”页点“全项目分析”构建，工单就能自动关联到业务流、表和代码位置。</div></div>`;
  const c=k.coverage.total||{},tot=Object.values(c).reduce((a,b)=>a+b,0)||1;
  const col={'已确认':'var(--ok)','待确认':'var(--warn)','过期':'var(--bad)','未分析':'var(--s-new)','仅事实':'var(--line)'};
  const top=k.domains.slice(0,8),mx=Math.max(1,...top.map(x=>x[2]));
  return `<div class="card"><div class="hdr" style="margin-bottom:8px"><h2 class="grow" style="margin:0">业务知识库</h2><a href="#/kb">查看</a></div>
  <div class="row" style="gap:22px;margin-bottom:10px"><div><b style="font-size:22px">${k.flows.toLocaleString()}</b><div class="sub">条业务流</div></div><div><b style="font-size:22px">${k.tables.toLocaleString()}</b><div class="sub">张表</div></div><div><b style="font-size:22px">${k.domains.length}</b><div class="sub">个业务域</div></div></div>
  <div class="stack">${Object.keys(col).map(s=>c[s]?`<div style="width:${c[s]/tot*100}%;background:${col[s]}" title="${s} ${c[s]}"></div>`:'').join('')}</div>
  <div class="legend" style="margin:6px 0 12px">${Object.keys(col).filter(s=>c[s]).map(s=>`<span><i style="background:${col[s]}"></i>${s} ${c[s]}</span>`).join('')}</div>
  <div class="bars">${top.map(d=>`<div class="r"><span title="${h(d[0])}">${h(d[1])}</span><div class="bar" style="width:${d[2]/mx*100}%"></div><span>${d[2]}</span></div>`).join('')}</div>
  <div class="sub" style="margin-top:6px">知识库构建于 ${h(k.built_at)}</div></div>`}

// ---------- tickets
function ticketTable(ts,compact){
  if(!ts.length)return '<div class="empty">还没有工单</div>';
  return `<table class="t"><tr><th>编号</th><th>标题</th>${compact?'':'<th>类型</th><th>优先级</th>'}<th>状态</th>${compact?'':'<th>经办人</th>'}<th>更新</th></tr>`+
  ts.map(t=>`<tr class="click" onclick="location.hash='#/t/${t.key}'"><td class="key">${t.key}</td><td>${h(t.title)}${(t.external||{}).key?` <span class="tag">${h(t.external.key)}</span>`:''}</td>${compact?'':`<td>${tyLabel(t.type)}</td><td class="pri-${t.priority}">${prLabel(t.priority)}</td>`}<td>${stPill(t.status)}</td>${compact?'':`<td>${h(t.assignee||'-')}</td>`}<td class="sub">${ago(t.updated)}</td></tr>`).join('')+'</table>'}
async function vTickets(){
  const f=JSON.parse(sessionStorage.getItem('tmh.f')||'{}');
  const q=new URLSearchParams({svc:'ops',project:scopeQ(),status:f.status||'',q:f.q||'',assignee:f.mine?S.user:''});
  let ts=await get('/api/tickets?'+q);if(f.open)ts=ts.filter(t=>t.status!=='closed');
  $('#main').innerHTML=`<div class="hdr"><h1 class="grow">工单${S.scope==='*'&&S.projects.length>1?' <span class="sub" style="font-size:13px;font-weight:400">全部 '+S.projects.length+' 个项目</span>':''}</h1>
   <input id="fq" placeholder="搜索标题或描述" value="${h(f.q||'')}">
   <select id="fs"><option value="">全部状态</option>${S.meta.statuses.map(([k,l])=>`<option value="${k}" ${f.status===k?'selected':''}>${l}</option>`).join('')}</select>
   <label class="sub"><input type="checkbox" id="fo" ${f.open?'checked':''}> 只看未关闭</label>
   <label class="sub"><input type="checkbox" id="fm" ${f.mine?'checked':''}> 指派给我</label>
   <button class="primary" onclick="newTicket()">＋ 新建</button></div><div class="tw">${ticketTable(ts)}</div><div class="sub" style="margin-top:8px">共 ${ts.length} 张</div>`;
  const upd=()=>{sessionStorage.setItem('tmh.f',JSON.stringify({q:$('#fq').value,status:$('#fs').value,open:$('#fo').checked,mine:$('#fm').checked}));vTickets()};
  $('#fs').onchange=upd;$('#fo').onchange=upd;$('#fm').onchange=upd;$('#fq').onkeydown=e=>{if(e.key==='Enter')upd()}}
function boardHtml(ts){
  return `<div class="sub" style="margin-bottom:8px">拖动卡片改变状态</div><div class="board">`+
  S.meta.statuses.map(([k,l])=>{const c=ts.filter(t=>t.status===k);return `<div class="col" data-s="${k}"><h3><span>${stPill(k)}</span><span class="sub">${c.length}</span></h3>`+
   c.slice(0,k==='closed'?30:200).map(t=>`<div class="tc" draggable="true" data-k="${t.key}" onclick="location.hash='#/t/${t.key}'"><div class="key">${t.key}</div><div class="tt">${h(t.title)}</div><div class="meta"><span class="tag">${tyLabel(t.type)}</span><span class="pri-${t.priority}">${prLabel(t.priority)}</span>${t.assignee?'<span>'+h(t.assignee)+'</span>':''}</div></div>`).join('')+'</div>'}).join('')+'</div>'}
function bindBoard(){
  document.querySelectorAll('.tc').forEach(c=>c.addEventListener('dragstart',e=>e.dataTransfer.setData('text/plain',c.dataset.k)));
  document.querySelectorAll('.col').forEach(c=>{c.addEventListener('dragover',e=>{e.preventDefault();c.classList.add('over')});c.addEventListener('dragleave',()=>c.classList.remove('over'));
    c.addEventListener('drop',async e=>{e.preventDefault();c.classList.remove('over');const k=e.dataTransfer.getData('text/plain');
      try{await post('/api/tickets/'+k,{status:c.dataset.s});vHome()}catch(x){toast(x.message)}})})}

// model picked per run: "auto" = the agent's default for that kind of task, "" = whatever the agent itself is set to
function mShort(a,v){const m=(a.models||[]).find(x=>x[0]===v);return m?m[1].split('（')[0]:v}
function modelSel(id,agent,mode){const a=((S.meta&&S.meta.agents)||[]).find(x=>x.name===agent)||{};const ms=a.models||[],d=a.defaults||{};
  let saved='auto';try{saved=localStorage.getItem('tmh.model.'+agent)??'auto'}catch(e){}
  if(saved&&saved!=='auto'&&!ms.some(x=>x[0]===saved))saved='auto';
  let auto;if(mode)auto=d[mode]?'自动：'+mShort(a,d[mode]):'自动：沿用本机设置';
  else{const g={};for(const [k,v] of Object.entries(d)){if(['analyze','plan','fix'].includes(k))(g[v]=g[v]||[]).push({analyze:'分析',plan:'方案',fix:'改码'}[k])}
    auto=Object.keys(g).length?'自动（'+Object.entries(g).map(([v,ks])=>ks.join('')+' '+mShort(a,v)).join(' · ')+'）':'自动：沿用本机设置'}
  return `<select id="${id}" data-agent="${h(agent)}" title="这次用哪个模型；自动＝按任务类型选" aria-label="模型"><option value="auto">${h(auto)}</option>${ms.map(([v,l])=>`<option value="${h(v)}" ${v===saved?'selected':''}>${h(l)}</option>`).join('')}<option value="" ${saved===''?'selected':''}>沿用本机设置</option></select>`}
function bindModel(id){const e=$('#'+id);if(e)e.onchange=()=>{try{localStorage.setItem('tmh.model.'+e.dataset.agent,e.value)}catch(x){}}}
function mTag(r){return r&&r.model?' · '+h(r.model):''}
function agentOptions(){const first=(S.meta.agents.find(a=>a.available)||{}).name;return S.meta.agents.map(a=>`<option value="${h(a.name)}" ${a.name===first?'selected':''}>${h(a.title)}${a.available?'':'（本机未安装）'}</option>`).join('')}
function newTicket(prefill){
  const types='<option value="auto" selected>自动判断</option>'+S.meta.types.map(([k,l])=>`<option value="${k}">${l}</option>`).join(''),pris=S.meta.priorities.map(([k,l])=>`<option value="${k}" ${k==='normal'?'selected':''}>${l}</option>`).join('');
  const np=S.scope!=='*'?S.scope:S.proj,af=(S.meta.autoflow||{}).on;
  modal(`<h2>新建工单${S.projects.length>1?` <select id="nproj" aria-label="项目" style="font-size:14px;margin-left:6px">${S.projects.map(p=>`<option value="${h(p.key)}" ${p.key===np?'selected':''}>${h(p.key)} · ${h(p.name)}</option>`).join('')}</select>`:' · '+h(np)}</h2><div class="grid2"><div class="form">
  <input class="full" id="nt" placeholder="一句话说清楚：哪里、什么问题 / 要什么">
  <textarea id="nb" placeholder="详细描述：业务场景、操作步骤、期望和实际结果、报错信息…（写业务语言就行，平台会对照知识库找相关业务流）" style="min-height:160px"></textarea>
  <div class="row"><label>类型 <select id="ny">${types}</select></label><label>优先级 <select id="np">${pris}</select></label><label>经办人 <input id="na" value="${h(S.user)}" size="10"></label></div>
  ${af?'<div class="hint">创建后自动受理：关联涉及的业务，让本机智能体分析定位，有结论后进入“处理中”，不用再手动点。</div>':`<label><input type="checkbox" id="nr" checked> 创建后让 <select id="ng">${agentOptions()}</select> 先分析定位</label>`}
  <label class="sub" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="nh"> 我来写：自动处理不接这张单，建好后下载开工包自己（或用自己的 AI 工具）写</label>
  <div class="row" style="gap:8px"><button class="primary" id="ns">创建</button><button class="ghost" id="nIn">说不清楚？让平台帮你理清</button></div></div>
  <div><div id="nsim"></div><h3>可能相关的业务 <span class="sub">边写边找</span></h3><div id="nrel" class="sub">输入标题或描述后显示</div></div></div>`,true);
  const sel=new Set();let tmr;const pk=()=>$('#nproj')?$('#nproj').value:np;
  if($('#nproj'))$('#nproj').onchange=()=>{sel.clear();look()};
  const look=()=>{clearTimeout(tmr);tmr=setTimeout(async()=>{const q=$('#nt').value+' '+$('#nb').value;if(q.trim().length<2)return;
    post('/api/projects/'+pk()+'/similar',{title:$('#nt').value,body:$('#nb').value}).then(r=>{$('#nsim').innerHTML=r.similar.length?`<h3>可能重复的工单 <span class="sub">先看看是不是同一个问题</span></h3>${simList(r.similar)}`:''}).catch(()=>{});
    try{const r=await get('/api/projects/'+pk()+'/related?limit=6&q='+encodeURIComponent(q));
      $('#nrel').innerHTML=r.flows.length?'<div class="sub" style="margin-bottom:6px">点选要关联的业务流</div><div class="chips">'+r.flows.map(f=>`<span class="chip ${sel.has(f.id)?'on':''}" data-f="${h(f.id)}" title="${h(f.file)}:${f.line}">${h(f.name)} <small>${h(f.domain||'')}</small></span>`).join('')+'</div>'+
       (r.tables.length?'<h3 style="margin-top:12px">相关表</h3><div class="chips">'+r.tables.map(t=>`<span class="tag">${h(t.name)}</span>`).join(' ')+'</div>':''):'<span class="sub">知识库里没找到相关业务流</span>';
      document.querySelectorAll('#nrel .chip').forEach(c=>c.onclick=()=>{const f=c.dataset.f;sel.has(f)?sel.delete(f):sel.add(f);c.classList.toggle('on')})}catch(e){$('#nrel').textContent=e.message}},350)};
  $('#nt').oninput=look;$('#nb').oninput=look;$('#nt').focus();
  $('#nIn').onclick=()=>intakeModal(pk(),[$('#nt').value,$('#nb').value].filter(Boolean).join('\n'));
  if(prefill){$('#nt').value=prefill.title||'';$('#nb').value=prefill.body||'';look()}
  $('#ns').onclick=async()=>{const b={project:pk(),title:$('#nt').value,body:$('#nb').value,type:$('#ny').value,priority:$('#np').value,assignee:$('#na').value,flows:[...sel]};
    if($('#nh').checked)b.handwork=true;else if($('#nr')){if($('#nr').checked){b.agent=$('#ng').value;b.mode='analyze'}else b.auto=false}
    try{const t=await post('/api/tickets',b);closeModal();location.hash='#/t/'+t.key;toast('已创建 '+t.key)}catch(e){toast(e.message)}}}

// ---------- ticket detail
function simList(xs){return `<div class="sim">${xs.map(x=>`<a class="drow" href="#/t/${h(x.key)}" onclick="closeModal()"><span class="grow"><b>${h(x.key)}</b> ${h(x.title)}<span class="sub">${h(x.shared.join('、'))}${x.external?' · '+h(x.external):''}</span></span>${stPill(x.status)}<small class="sub">${Math.round(x.score*100)}%</small></a>`).join('')}</div>`}
// The ticket page answers three questions in order: where is it in the flow, what should happen next (one
// button), and what did we find. Everything else (manual agent runs, raw logs) sits folded below.
const FLOW=[['intake','受理'],['analyze','分析定位'],['plan','修改方案'],['fix','修改代码'],['verify','人工验收'],['closed','闭环']];
function flowState(d){
  const t=d.ticket,R=m=>d.runs.find(r=>r.mode===m),ev=k=>d.events.filter(e=>e.kind===k).pop();
  const an=R('analyze'),pl=R('plan'),fx=R('fix'),live=d.runs.find(r=>r.status==='running'||r.status==='queued');
  const review=t.status!=='closed'&&fx&&fx.status==='done'&&!fx.decision&&fx.diff!=='';
  const acc=d.events.filter(e=>e.kind==='accept'||e.kind==='reject').pop(),it=ev('intake');
  const rs=r=>!r?'todo':r.status==='done'?'done':(r.status==='running'||r.status==='queued')?'cur':r.status==='failed'?'bad':'todo';
  const st={intake:'done',analyze:rs(an),plan:rs(pl),fix:fx?(fx.decision&&fx.decision.startsWith('accepted')?'done':fx.decision==='discarded'?'todo':rs(fx)==='done'?'cur':rs(fx)):'todo',
    verify:review?'todo':t.status==='closed'?'done':t.status==='verify'?'cur':acc&&acc.kind==='reject'?'bad':'todo',closed:t.status==='closed'?'done':'todo'};
  if(t.status==='closed'||t.status==='verify'){['analyze','plan','fix'].forEach(k=>{if(st[k]==='todo')st[k]='skip'})}
  else if(an&&an.status==='done'&&!d.evidence.refs&&!pl)st.analyze='bad';
  const sub={intake:it?(it.author==='自动流转'?'自动':h(it.author))+' · '+ago(it.ts):h(t.reporter||'')+' · '+ago(t.created),
    analyze:an?h(an.agent)+' · '+(an.status==='done'?(d.evidence.refs?d.evidence.refs+' 处代码':'卡住：没找到代码证据'):({running:'进行中',queued:'排队',failed:'失败',cancelled:'已取消'}[an.status]||'')):'',
    plan:pl?h(pl.agent)+' · '+({done:'已出方案',running:'进行中',queued:'排队',failed:'失败',cancelled:'已取消'}[pl.status]||''):'',
    fix:fx?(fx.decision?(fx.decision.startsWith('accepted')?(adopted(d)&&adopted(d).auto?'已自动提交':'已采纳'):'已放弃'):fx.status==='done'?(fx.diff===''?'无改动':'待审阅'):({running:'进行中',queued:'排队',failed:'失败',cancelled:'已取消'}[fx.status]||'')):'',
    verify:review?'等待审阅最新改动':acc?h(acc.author)+' · '+(acc.kind==='accept'?'通过':'不通过'):t.status==='verify'?'等验收':'',closed:t.status==='closed'?ago(t.updated):''};
  return {st,sub,an,pl,fx,live,acc,review}}
function stepper(f){return `<ol class="fsteps">${FLOW.map(([k,l],i)=>`<li class="${f.st[k]}"><span class="dot">${f.st[k]==='done'?'✓':f.st[k]==='bad'?'!':i+1}</span><b>${l}</b><small>${f.sub[k]||(f.st[k]==='skip'?'跳过':'')}</small></li>`).join('')}</ol>`}
function defAgent(){let a='';try{a=localStorage.getItem('tmh.agent')||''}catch(e){}const ags=S.meta.agents;return (ags.find(x=>x.name===a&&x.available)||ags.find(x=>x.available)||ags[0]||{}).name}
// Tickets run on their own until the change sits on its own branch; a person can take one over and hand it back.
const MERGE_ON=()=>(S.meta.autoflow||{}).merge==='auto';
function onAuto(d){return !!((S.meta.autoflow||{}).on)&&!(d.ticket.links||{}).hold&&!['verify','closed'].includes(d.ticket.status)}
// what the change went through before anyone looks at it: per-file agents, build and tests, diagnosis rounds
function vfy(r){const v=r&&r.verify;if(!v)return '';const c={pass:'构建测试通过',fail:'构建测试没通过',skip:'没跑构建测试'}[v.check]||'';
  return `${v.split?`${v.files} 个文件分工改，`:''}${c}${v.check==='skip'&&v.skip?'（'+h(v.skip)+'）':''}，${v.by_hand?h(v.reviewer||'')+' 审查':'诊断'}${{pass:'认为已解决',fail:'认为还没解决',unknown:'没给结论'}[v.verdict]||''}${v.rounds?'，共 '+v.rounds+' 轮':''}。`}
function adopted(d){const r=d.runs.find(x=>x.mode==='fix');if(!r?.decision?.startsWith('accepted:'))return null;
  const e=d.events.filter(x=>x.kind==='adopt'&&String((x.data||{}).run)===String(r.id)).pop(),[branch,commit]=r.decision.slice(9).split('@');
  return {branch:branch||'',commit:commit||'',auto:e?.author==='自动流转'}}
function autoChip(d){const t=d.ticket;if(!(S.meta.autoflow||{}).on||['verify','closed'].includes(t.status))return '';const lk=t.links||{},held=lk.hold;
  if(!held&&lk.open_ac)return `<span class="autoc off" title="验收标准有待确认的，答清楚前不自动开始">等客户确认</span>`;
  if(!held&&lk.later)return `<span class="autoc off" title="${h(lk.later)}">${d.epic?'大需求父单':'排队等前一批'}</span>`;
  return `<span class="autoc ${held?'off':''}" title="${held?'自动处理已暂停，由人处理':'智能体会自动分析、出方案、在独立分支上改代码并提交，停在等人验收'}">${held?'人工处理中':'自动处理中'}<button class="link" data-hold="${held?0:1}">${held?'交回自动':'接管'}</button></span>`}
function nextAction(d,f){
  const t=d.ticket,pr=(S.points&&S.points.prices)||{},cost=m=>pr[m]?`（${pr[m]} 点）`:'';
  const B=(id,label,cls)=>`<button id="${id}" class="${cls||''}">${label}</button>`;
  const auto=onAuto(d),br=adopted(d);
  if(f.live)return {tone:'info',text:`<span class="spin"></span> 智能体正在${h(moLabel(f.live.mode))}${auto&&f.live.author==='自动流转'?'，跑完会自动接着往下做，直到提交到独立分支等你验收':'，完成后这里会给出下一步'}。`,btns:B('naLog','看实时过程','ghost')+(auto?`<button class="ghost" data-hold="1">接管</button>`:'')};
  const ir=d.intake_recovery;
  if(t.status!=='closed'&&ir&&['failed','blocked','running'].includes(ir.status)){
    const answers=(ir.items||[]).flatMap(it=>(it.answers||[]).map(a=>`<div style="margin-top:6px;white-space:pre-wrap">${h(a.question)}<br><b>${h(a.value)}</b> <span class="sub">${h(a.from||'')}</span></div>`)).join('');
    const history=(ir.attempts||[]).map(a=>`<div style="margin-top:6px;white-space:pre-wrap">${h(a.at||'')}${a.run?' · 运行 #'+h(a.run):''}：${h(a.reason||a.status||'')}</div>`).join('');
    return {tone:ir.status==='running'?'info':'warn',text:(ir.status==='running'?'<span class="spin"></span> 正在根据已保存答复补全验收标准。':'<b>客户答复已保存，再理解未完成。</b> 请处理已保存的答复。')+
      '<div class="sub">已有答案无需重复填写；已确认的标准继续保留。</div>'+
      (ir.status!=='running'&&(ir.blocked||[]).length?'<div style="white-space:pre-wrap">'+ir.blocked.map(h).join('<br>')+'</div>':'')+
      (answers||history||ir.reason?'<details style="margin-top:8px"><summary>查看已保存答复与处理记录</summary>'+(ir.reason?'<div style="white-space:pre-wrap">'+h(ir.reason)+'</div>':'')+answers+history+'</details>':''),
      btns:(ir.can_retry?B('naIntakeRetry','重试理解已保存答复','primary'):'')+(ir.run?B('naIntakeLog','查看理解运行','ghost'):'')};
  }
  const lt=(t.links||{}).later;  // held off the line by an app: a feature's parent, or a child waiting for its batch
  if(d.epic&&t.status==='closed')return {tone:'ok',text:'大需求已整体验收通过，全部完成。要再改，请提一个新的需求。'};
  if(lt&&t.status!=='closed'){if(d.epic&&t.status==='verify')return {tone:'warn',text:'全部子单都完成了，<b>等你整体验收</b>：对照规格卡的整体验收标准和每个子单的版本验证。通过就关闭这个大需求；不通过写明原因，会自动开一个跟进子单按原因重改。',acc:true};
    return {tone:'info',text:d.epic?'大需求的父单不直接改代码：子单分批放出、各自验收，全部完成后回到这里整体验收。':h(lt)+'。'}}
  if((t.links||{}).client_change&&t.status!=='closed')return {tone:'warn',text:'客户的答复会<b>改动已经确认的验收标准</b>（改了什么见下面的动态）。采用后按新标准继续；不采用就按原来确认的标准。在你决定之前不自动开工。',
    btns:B('naCcYes','采用客户的改动','primary')+B('naCcNo','不采用，按原标准','ghost')};
  const hw=(t.links||{}).handwork;
  const hwe=(d.events||[]).filter(e=>e.author==='我来写').pop();
  const hwr=(d.runs||[]).find(r=>r.mode!=='ask'),hwc=hwr&&hwr.agent==='人工'&&(d.events||[]).filter(e=>e.author==='我来写'&&e.kind==='flow'&&(e.data||{}).run===hwr.id&&['pass','fail','unknown'].includes((e.data||{}).verdict)).pop();
  if(hw&&!['verify','closed'].includes(t.status)&&hwe&&hwe.kind==='flow'&&/^收到/.test(hwe.body||''))return {tone:'info',text:`<span class="spin"></span> ${h(hwe.body)}：构建测试、对照验收标准审查，通过就转待验证。`};
  if(hw&&!['verify','closed'].includes(t.status)&&hwc&&['fail','unknown'].includes(hwc.data.verdict))return {tone:'bad',text:h(hwc.body),btns:B('naHwScan','改好推上去了，现在检查','primary')};
  if(hw&&!['verify','closed'].includes(t.status))return {tone:'info',text:`<b>${h(hw)} 在写</b>：按开工包在自己电脑上改（Claude Code、Codex 或手写都行），提交到分支 <code>wb/${h(t.key)}</code> 推上去。平台一分钟内发现，自动构建测试、换一个模型对照验收标准审查，通过就转待验证；自动处理不会接这张单。`,
    btns:B('naHwPack','下载开工包','primary')+B('naHwScan','推好了，现在检查','ghost')};
  const oa=(t.links||{}).open_ac;
  if(oa&&!(t.links||{}).hold&&!['verify','closed'].includes(t.status)&&!f.live)return {tone:'warn',text:`有 <b>${oa} 条验收标准还待确认</b>，答清楚之前不自动开始。把问题发给客户，客户答完验收标准自动补全${(S.meta.autoflow||{}).on?'、自动开始':''}；你已经和客户确认过，也可以直接交给自动处理。`,
    btns:B('naAsk','把问题发给客户','primary')+B('naGo','已确认，交给自动处理','ghost')+B('naClaim','我来写','ghost')};
  if(auto&&d.auto_next&&!f.live&&!(d.events.slice(-1)[0]||{}).body?.startsWith('交给自动处理'))return {tone:'info',text:`这张工单还没走自动处理（自动处理只接新进来的工单）。交给它后从“${{analyze:'分析定位',plan:'修改方案',fix:'修改代码',commit:'提交改动'}[d.auto_next]}”接着做，停在等你验收。`,btns:B('naGo','交给自动处理','primary')+'<button class="ghost" data-hold="1">我自己处理</button>'};
  if(auto&&['new','analyzing'].includes(t.status)&&!f.an)return {tone:'info',text:'<span class="spin"></span> 已自动受理，智能体马上开始分析定位，之后会自动出方案、改代码并提交到独立分支，停在等你验收。',btns:'<button class="ghost" data-hold="1">接管</button>'};
  if(t.status==='closed'){const ev=d.events||[],rl=ev.filter(e=>e.kind==='release').slice(-1)[0],wt=ev.filter(e=>e.kind==='flow'&&(e.data||{}).release==='waiting').slice(-1)[0];
    const hold=wt&&(!rl||wt.id>rl.id);
    return {tone:hold?'warn':'ok',text:`已闭环${f.acc&&f.acc.kind==='accept'?'：'+h(f.acc.author)+' 验收通过':''}。`+(rl&&!hold?h(rl.body)+'。':'')+(hold?'<b>'+h(wt.body)+'</b>':''),
      btns:(hold?B('naShip','重试合并','primary'):'')+B('naReopen','重新打开','ghost')}}
  if(f.review){const why=d.events.filter(e=>e.kind==='flow'&&(e.data||{}).run===f.fx.id).pop();
    return {tone:'warn',text:`运行 #${h(f.fx.id)}：`+vfy(f.fx)+(why?h(why.body.replace(/^改动已生成，/,'').replace(/，留给人审阅后再提交$/,''))+'，所以没有自动提交。':'智能体改好了代码，')+'<b>等你审阅</b>。采纳后提交到独立分支，不动你的工作目录。',btns:B('naReview','审阅改动','primary')}}
  if(t.status==='verify')return {tone:'warn',text:(f.fx&&f.fx.verify?vfy(f.fx)+' ':'')+(br?`改动${br.auto?'已自动':'已'}提交到分支 <code>${h(br.branch)}</code>（提交 ${h(br.commit)}，主干还没动）。`:'改动已就绪，')+'<b>等你验收</b>：按业务操作实际验证。'+(MERGE_ON()?'通过后自动合并进主干、出一个新版本；':'通过后由人合并分支；')+'不通过写明原因，退回重改。',acc:true};
  if(f.fx&&f.fx.decision&&f.fx.decision.startsWith('accepted'))return {tone:'info',text:`改动已提交到分支 <code>${h(f.fx.decision.slice(9).split('@')[0])}</code>。转给验收人${MERGE_ON()?'，验收通过后自动合并进主干':'，验收通过后由人合并'}。`,btns:B('naVerify','转待验证','primary')};
  if(['failed','cancelled'].includes(d.runs[0]?.status))return {tone:'bad',text:'最近一次'+h(moLabel(d.runs[0].mode))+'未完成。已有改动和执行记录保留，请查看停止原因后继续处理。',btns:B('naLog','查看停止原因与恢复入口','primary')};
  if(f.pl&&f.pl.status==='done')return {tone:'info',text:'修改方案已经出来了（见下方结论）。下一步是改代码：可以交给智能体，也可以自己改完转待验证。',btns:B('naFix','让智能体改代码'+cost('fix'),'primary')+B('naVerify','我自己改，改完转待验证','ghost')};
  if(f.an&&f.an.status==='done')return {tone:'info',text:d.evidence.refs?`已定位到 ${d.evidence.refs} 处代码。下一步：起草修改方案，确认改法后再动代码。`:'分析没有找到代码证据，先在讨论里补充信息（单据号、截图、报错），再重新分析。',btns:d.evidence.refs?B('naPlan','起草修改方案'+cost('plan'),'primary')+B('naFix','直接改代码'+cost('fix'),'ghost'):B('naAn','重新分析定位'+cost('analyze'),'primary')};
  if(f.an&&f.an.status==='failed')return {tone:'bad',text:'上一次分析定位失败了（原因见执行记录）。',btns:B('naAn','重新分析定位'+cost('analyze'),'primary')+B('naLog','看失败原因','ghost')};
  return {tone:'info',text:'还没有分析。交给智能体先定位到业务和代码。',btns:B('naAn','分析定位'+cost('analyze'),'primary')}}
// Pull one section out of an agent's answer ("结论", "方案概要"...), as plain text for the conclusion card.
function secOf(text,names){
  const L=(text||'').split('\n'),hd=/^\s*(#{1,4}\s+|\*\*|【)?\s*(\d+[.、)]\s*)?/;
  for(let i=0;i<L.length;i++){
    const m=L[i].replace(hd,'');const nm=names.find(n=>m.startsWith(n));if(!nm)continue;
    const out=[];const rest=m.slice(nm.length).replace(/^[\s*】:：]+/,'');if(rest)out.push(rest);
    for(let j=i+1;j<L.length;j++){const x=L[j];if(/^\s*#{1,4}\s/.test(x)||/^\s*\*\*[^*]{1,16}\*\*\s*[:：]?\s*$/.test(x))break;
      if(out.length&&(!x.trim()||/^\s*([-*•]|\d+[.、)])\s/.test(x)))break;if(x.trim())out.push(x.trim())}
    const t=out.join(' ').replace(/[*_`>#]/g,'').replace(/^\s*[-•]\s*/,'').replace(/\s+/g,' ').trim();if(t)return t}
  return ''}
function firstPara(text){const t=(text||'').split(/\n\s*\n/).map(x=>x.replace(/[*_`>#]/g,'').replace(/\s+/g,' ').trim()).find(x=>x&&x.length>8);return t||''}
// The first line that says something: skip greetings and "在吗" so the card shows the problem, not "各位好："
function symptomOf(t){
  const hi=/^(各位|大家|领导|老师|您|你|王|李|张|刘|陈)?(好|们好|老师好|领导好)[!！,，。:：~～ ]*$|^(在吗|在不在|hi|hello|您好|你好)(?![A-Za-z])[?？!！,，。:：~～ ]*/i;
  for(const raw of (t.body||'').split('\n')){let x=raw.trim();if(!x||/^——/.test(x)||/^#{1,6}\s/.test(x))continue;
    x=x.replace(hi,'').trim();if(x.length>=4)return x}
  return t.title}
const clip=(t,n)=>t.length>n?t.slice(0,n)+'…':t;
// Which linked flows a person stands behind; the rest were linked by the automatic flow and wait for a look.
function okFlows(d){const ok=new Set(((d.ticket.links||{}).flows_ok)||[]);
  d.events.forEach(e=>{const m=e.kind==='link'&&!isMachine(e.author)&&/^关联业务流 (\S+)/.exec(e.body||'');if(m)ok.add(m[1])});return ok}
function isMachine(a){return !a||['自动流转','system','知识库','agent','告警'].includes(a)||(S.meta.agents||[]).some(x=>x.name===a)}
function ticketRunCount(runs){const points=runs.reduce((a,r)=>a+(r.points||0),0);return `${runs.length} 次运行${points?' · 共 '+points+' 点':''}`}
function ticketRunHistory(runs){return runs.length>1?'<span class="sub">全部运行：</span> '+runs.map(r=>`<a href="javascript:void 0" onclick="showRun(${r.id})">#${r.id} ${h(moLabel(r.mode))}${['queued','running'].includes(r.status)?' <span class="spin"></span>':''}${r.points?' · '+h(r.points)+' 点':''}</a>`).join('　'):''}
function ticketSummarySync(initial,changed){
  const key=initial.ticket.key,anchor=$('#tTop'),signature=d=>JSON.stringify([d.ticket,d.plain_state,d.intake_recovery,d.runs.map(r=>[r.id,r.status,r.decision,r.points,r.verify,r.result]),d.events.length,d.evidence,d.auto_next,d.package]);
  let applied=signature(initial),request=0;
  return async()=>{const seq=++request,n=await get('/api/tickets/'+encodeURIComponent(key));
    if(seq!==request||!anchor?.isConnected||$('#tTop')!==anchor||S.cur?.ticket?.key!==key)return null;
    if(n.ticket?.key!==key)throw new Error('工单状态与当前页面不一致');
    const next=signature(n);if(next===applied)return n;
    const prior=S.cur,f=flowState(n),na=nextAction(n,f),focused=anchor.contains(document.activeElement)?document.activeElement.id:'';
    S.cur=n;anchor.innerHTML=ticketTop(n,f,na);
    $('#tSteps').innerHTML=stepper(f);$('#tNextText').innerHTML=na.text;$('#tNextText').className='na '+na.tone;
    $('#tNextActions').innerHTML=na.btns||'';$('#tNextActions').hidden=!na.btns;
    $('#tRunCount').textContent=ticketRunCount(n.runs);$('#tRunHistory').innerHTML=ticketRunHistory(n.runs);$('#tStatus').innerHTML=stPill(n.ticket.status);
    const status=$('#fs');if(status&&document.activeElement!==status&&status.value===prior.ticket.status)status.value=n.ticket.status;
    if(n.ticket.body!==prior.ticket.body&&$('#bodyv')&&!$('#be'))$('#bodyv').innerHTML=md(n.ticket.body||'');
    if(JSON.stringify(n.package)!==JSON.stringify(prior.package)||n.ticket.status!==prior.ticket.status)pkgSync(n);
    changed(n);ticketTopWire(n,na);if(focused)$('#'+focused)?.focus({preventScroll:true});applied=next;return n;
  }
}
function pkgSync(d){
  const summary=$('#pkSummary'),actions=$('#pkActions');if(!summary||!actions)return;
  summary.innerHTML=pkgSummary(d);actions.innerHTML=pkgActions(d);
  const notice=$('#pkDraftNotice'),form=$('#pkForm');if(notice)notice.hidden=!form?.childElementCount;
  // Keep the actual form and file input nodes: selected FileLists cannot be restored from HTML.
  pkgWire(d);
}
function watchIntakeRecovery(key){
  stopPolls('intake');const refresh=S.ticketRefresh;
  if(S.cur?.ticket?.key!==key||S.cur?.intake_recovery?.status!=='running')return;
  poll(async()=>{if(S.ticketRefresh!==refresh||S.cur?.ticket?.key!==key)return stopPolls('intake');
    try{const n=await refresh();if(n?.intake_recovery?.status!=='running')stopPolls('intake')}catch(e){}},1500,'intake');
}
// ---------- candidate code paths: inspect on demand, never an acceptance decision
function pathMapContent(m,selected){
  const text=v=>typeof v==='string'?v:JSON.stringify(v??'',null,2),source=m.source||{},flows=m.flows||[];
  const label={mapped:'已定位静态入口',partial:'仅部分定位',unsupported:'当前解析不支持',blocked:'暂不可关联',unavailable:'暂无可用映射',failed:'解析未完成'};
  const loc=n=>h(n.file||'')+(n.line?':'+h(n.line)+(n.end_line&&n.end_line!==n.line?'–'+h(n.end_line):''):'');
  const list=xs=>xs.map(x=>'<li style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(text(x))+'</li>').join('');
  return `<p role="status"><b>${h(label[m.status]||m.status||'解析状态未知')}</b></p>
    ${m.why?'<p style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(text(m.why))+'</p>':''}
    <p class="sub" style="white-space:pre-wrap;overflow-wrap:anywhere">${h(text(m.scope||'当前候选提交的静态代码入口与函数关联。'))}</p>
    <p class="sub">这是方法级静态关联；HTTP 分派方法中的多个 URL 可能共用调用链，不能据此认定某个 URL 已被精确验证，也不代表业务验收通过。</p>
    <div class="sub">候选提交</div><code style="display:block;overflow-wrap:anywhere">${h(source.commit||'未提供，无法绑定候选版本')}</code>
    <details style="margin-top:8px"><summary>版本与映射指纹</summary><div class="sub">差异 SHA-256</div><code style="display:block;overflow-wrap:anywhere">${h(source.diff_sha256||'未提供')}</code><div class="sub">映射摘要</div><code style="display:block;overflow-wrap:anywhere">${h(m.digest||'未提供')}</code></details>
    ${(m.limitations||[]).length?'<h3 style="margin-top:14px">静态分析限制</h3><ul>'+list(m.limitations)+'</ul>':''}
    ${(m.diagnostics||[]).length?'<h3 style="margin-top:14px">解析诊断</h3><ul>'+m.diagnostics.map(x=>`<li><code style="overflow-wrap:anywhere">${loc(x)}</code><div style="white-space:pre-wrap;overflow-wrap:anywhere">${h(x.message||'')}</div></li>`).join('')+'</ul>':''}
    <h3 style="margin-top:14px">改动函数与入口</h3>${(m.changes||[]).length?m.changes.map(c=>`<div style="padding:10px 0;border-bottom:1px solid var(--line)"><code style="overflow-wrap:anywhere">${h(c.file||'')}</code><span class="tag">${h(c.status||'未知')}</span>
      ${c.why?'<div style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(c.why)+'</div>':''}<div class="sub" style="overflow-wrap:anywhere">新增或修改行（候选版本）：${h(Array.isArray(c.lines)?c.lines.join('、')||'无':'未提供')}</div>
      <div class="sub" style="overflow-wrap:anywhere">删除行（旧版本）：${h(Array.isArray(c.removed_lines)?c.removed_lines.join('、')||'无':'未提供')}</div>
      <div style="white-space:pre-wrap;overflow-wrap:anywhere">函数：${h((c.functions||[]).join('\n')||'未定位到函数')}</div><div class="sub" style="white-space:pre-wrap;overflow-wrap:anywhere">关联入口：${h((c.flow_ids||[]).join('\n')||'未定位到入口')}</div>
      ${(c.locations||[]).length?'<details style="margin-top:8px"><summary>查看新旧行定位证据</summary><p class="sub">old 为旧版本，new 为候选版本；保留每行对应的函数与入口。</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(text(c.locations))+'</pre></details>':''}</div>`).join(''):'<p class="sub">没有可显示的改动函数；这不表示业务没有影响。</p>'}
    <h3 style="margin-top:14px">可记录的代码入口</h3>${flows.length?flows.map((f,i)=>`<div style="padding:10px 0;border-bottom:1px solid var(--line)"><label style="display:flex;gap:8px;align-items:flex-start"><input type="checkbox" data-path-flow="${i}" style="width:auto;margin-top:4px" ${selected.has(f.id)?'checked':''}><span style="min-width:0;overflow-wrap:anywhere"><b>${h(f.trigger||f.id)}</b><br><code>${h(f.handler||'')}</code><br><small>${h(f.id)}</small></span></label>
      <details style="margin-top:6px"><summary>查看方法与静态断点</summary>${(f.nodes||[]).map(n=>`<div style="margin-top:6px;overflow-wrap:anywhere"><code>${h(n.key||'')}</code><div class="sub">${loc(n)}</div></div>`).join('')||'<p class="sub">没有已解析的方法节点。</p>'}
      ${(f.unresolved||[]).length?'<h4>未解析部分</h4><ul>'+list(f.unresolved)+'</ul>':'<p class="sub">已解析范围内未报告静态断点；未解析范围不作结论。</p>'}</details></div>`).join(''):'<p class="sub">没有可选的代码入口，请核对解析诊断和限制。</p>'}
    <p class="sub">记录只保存此候选版本的技术关联，不增加人工复核，也不确认业务范围。</p>
    <div class="row" style="gap:8px;margin-top:10px"><button data-path-record ${m.can_record===true&&source.commit&&m.digest&&selected.size?'':'disabled'}>记录代码关联</button><button class="ghost" data-path-reload>重新加载入口</button></div>`;
}
function ticketPathMapWire(key){
  const fold=$('#pathMapDetails'),panel=$('#pathMapPanel');if(!fold||!panel)return;
  const url='/api/tickets/'+encodeURIComponent(key)+'/path-map',refresh=S.ticketRefresh;
  let mapping=null,selected=new Set(),loaded=false,loading=false,saving=false;
  const current=()=>panel.isConnected&&$('#pathMapPanel')===panel&&S.cur?.ticket?.key===key;
  const errorText=e=>String(e?.message??e);
  const selection=(value,fallback)=>{const choices=new Set((value.flows||[]).map(f=>f.id));return new Set((value.selected?.length?value.selected:fallback?value.suggested||[]:[]).filter(id=>choices.has(id)));};
  function paint(message='',error=''){
    if(!current())return;
    panel.innerHTML=(message?'<p role="status">'+h(message)+'</p>':'')+(error?'<div role="alert" style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(error)+'</div>':'')+
      (mapping?pathMapContent(mapping,selected):'<button data-path-reload style="margin-top:8px">重试加载候选入口</button>');
    const reload=panel.querySelector('[data-path-reload]');if(reload)reload.onclick=load;
    const record=panel.querySelector('[data-path-record]');if(record){if(error)record.disabled=true;record.onclick=save;}
    panel.querySelectorAll('[data-path-flow]').forEach(box=>{box.onchange=()=>{const id=mapping.flows[Number(box.dataset.pathFlow)]?.id;if(!id)return;
      box.checked?selected.add(id):selected.delete(id);if(record)record.disabled=!!error||mapping.can_record!==true||!mapping.source?.commit||!mapping.digest||!selected.size;};});
  }
  async function load(){
    if(loading||saving||!current())return;loading=true;panel.innerHTML='<p role="status"><span class="spin"></span> 正在读取候选代码入口…</p>';
    try{const value=await get(url);if(!current())return;mapping=value;selected=selection(value,true);loaded=true;paint();}
    catch(e){loaded=false;paint('',errorText(e));}finally{loading=false;}
  }
  async function save(){
    if(saving||loading||!current()||mapping?.can_record!==true||!mapping.source?.commit||!mapping.digest||!selected.size)return;
    const button=panel.querySelector('[data-path-record]');if(button?.disabled)return;saving=true;if(button)button.disabled=true;
    panel.querySelectorAll('[data-path-flow]').forEach(box=>box.disabled=true);
    try{const value=await post(url,{commit:mapping.source.commit,digest:mapping.digest,flows:[...selected]});if(!current())return;
      mapping=value;selected=selection(value,false);paint('代码关联已记录；仍需独立验证和业务验收。');
      try{if(S.ticketRefresh===refresh)await refresh();}catch(e){paint('代码关联已记录；工单摘要刷新未完成。',errorText(e));}
    }catch(e){paint('',errorText(e));}finally{saving=false;}
  }
  fold.ontoggle=()=>{if(fold.open&&!loaded&&!loading)return load();};
}
// ---------- ticket page
async function vTicket(key,sub){
  let d=await get('/api/tickets/'+key);const t=d.ticket;S.cur=d;setProj(d.project.key);paintSel();A.setTicket(t);
  S.svc=(t.links||{}).reform?'reform':'ops';paintTabs(S.svc==='reform'?'rtickets':'home');
  const opt=(pairs,v)=>pairs.map(([k,l])=>`<option value="${k}" ${k===v?'selected':''}>${l}</option>`).join('');
  const ext=t.external||{},e=d.evidence||{};let f=flowState(d),na=nextAction(d,f);
  const res=f.pl&&f.pl.status==='done'?f.pl:f.an&&f.an.status==='done'?f.an:null;
  const accUi=`<textarea id="accNote" placeholder="验收说明（不通过时必填）" style="min-height:64px"></textarea>
     <div class="row" style="gap:8px;margin-top:8px"><button class="primary" id="accOk">验收通过</button><button class="danger" id="accNo">验收不通过</button><button class="ghost" id="accDraft">让助手起草验收说明</button></div>`;
  const reviewing=f.fx&&f.fx.status==='done'&&!f.fx.decision;
  // the four lines a reader needs: what happens, why, how sure, and who acts next
  const sym=clip(symptomOf(t),120);
  const an=f.an&&f.an.status==='done'?f.an.result:'';
  const cause=an?clip(secOf(an,['结论','原因分析','原因'])||firstPara(an),220):'';
  const plan=f.pl&&f.pl.status==='done'?clip(secOf(planless(f.pl.result),['方案概要','修改方案','方案'])||firstPara(planless(f.pl.result)),220):'';
  const evi=[e.verified?`<span class="ev-tag ok">核实 ${e.verified}</span>`:'',e.guesses?`<span class="ev-tag warn">推断 ${e.guesses}</span>`:'',
    res?(e.refs?`<span class="ev-tag info">代码 ${e.refs} 处</span>`:'<span class="ev-tag warn">没找到代码证据</span>'):''].join(' ');
  const causeTxt=cause?h(cause):f.live&&f.live.mode==='analyze'?'<span class="sub"><span class="spin"></span> 智能体正在分析</span>':f.an&&f.an.status==='failed'?'<span class="sub">分析失败，见执行记录</span>':'<span class="sub">还没有分析</span>';
  const concl=`<div class="card concl"><dl class="c4">
     <dt>现象</dt><dd>${h(sym)}</dd>
     <dt>根因</dt><dd>${causeTxt}${!f.live&&an&&/待确认/.test(cause)?' <span class="ev-tag warn">待确认</span>':''}</dd>
     ${plan?`<dt>方案</dt><dd>${h(plan)}</dd>`:''}
     <dt>证据</dt><dd>${res?evi+` <a href="javascript:void 0" id="evOpen">看完整${res.mode==='plan'?'方案':'分析'}和代码位置</a>`:'<span class="sub">分析后在这里列出核实和推断的条数</span>'}</dd>
     <dt>等谁</dt><dd id="tNextText" class="na ${na.tone}">${na.text}</dd></dl>
     ${na.acc?`<div class="cact">${accUi}</div>`:''}<div id="tNextActions" class="row cact" style="gap:8px" ${na.btns?'':'hidden'}>${na.btns||''}</div>
     ${res?`<div class="cbox" id="cbox" hidden><div class="sub" style="margin-bottom:6px">${res.mode==='plan'?'修改方案':'分析结论'} · ${h(res.agent)}${mTag(res)} · ${ago(res.ended)}</div>${md(planReadable(res.result))}</div>`:''}</div>`;
  // the timeline: people's words stay in view; what the machines did folds into one line per run of steps
  const groups=[];d.events.forEach(ev=>{const m=isMachine(ev.author)&&ev.kind!=='comment';const g=groups[groups.length-1];if(m&&g&&g.auto)g.evs.push(ev);else groups.push({auto:m,evs:[ev]})});
  const tl=groups.map(g=>{if(!g.auto||g.evs.length<2)return g.evs.map(evHtml).join('');
    const a=g.evs[0].ts,z=g.evs[g.evs.length-1].ts,span=(new Date(z.replace(' ','T'))-new Date(a.replace(' ','T')))/36e5;
    return `<details class="evg"><summary><span class="dot"></span><b>自动处理</b> · ${g.evs.length} 步${span>0?' · 用时 '+dur(span):''}<span class="when">${ago(z)}</span></summary>${g.evs.map(evHtml).join('')}</details>`}).join('');
  const nAuto=d.events.filter(x=>isMachine(x.author)&&x.kind!=='comment').length;
  $('#main').innerHTML=`<div class="sub" style="margin-bottom:6px"><a href="#/reqs">需求</a> / ${h(d.project.key)} / ${t.key}</div>
  <div class="hdr"><h1 class="grow" id="ttl" title="点击修改">${h(t.title)}</h1><span id="tStatus">${stPill(t.status)}</span><button onclick="A.toggle(true);A.enterTicket(S.cur.ticket)">在助手中讨论</button></div>
  <div class="props"><span class="tag">${h(d.project.key)}</span>
   <label>状态<select id="fs" data-autosave="1" ${d.epic?'disabled title="父单的状态跟着子单走"':''}>${opt(S.meta.statuses.filter(([k])=>k!=='closed'||t.status==='closed'),t.status)}</select></label>
   <label>类型<select id="fy" data-autosave="1">${opt(S.meta.types,t.type)}</select></label>
   <label>优先级<select id="fp" data-autosave="1">${opt(S.meta.priorities,t.priority)}</select></label>
   <label>经办人<input id="fa" data-autosave="1" value="${h(t.assignee)}" placeholder="无人" size="6"></label>
   ${autoChip(d)}${d.parent?`<span class="tag">大需求 <a href="#/t/${h(d.parent.key)}">${h(d.parent.key)}</a> 的第 ${h(String((t.links||{}).order||''))} 个子单</span>`:''}${(t.links||{}).alert?`<span class="ev-tag bad" title="监控告警自动开的单，同一告警再触发只累计次数">告警 ×${t.links.alert.count||1}</span>`:''}
   <span class="sub">${h(t.reporter||'-')} 提交 · ${h(t.created.slice(5,16))}${ext.key?' · '+h(ext.system)+' '+(ext.url?`<a href="${h(ext.url)}" target="_blank" rel="noopener">${h(ext.key)}</a>`:h(ext.key)):''}</span></div>
  <div id="tTop" ${sub==='prompt'?'hidden':''}>${ticketTop(d,f,na)}</div>
  <nav class="ttabs"><a href="#/t/${t.key}" class="${sub==='prompt'?'':'on'}">工单详情</a><a href="#/t/${t.key}/prompt" class="${sub==='prompt'?'on':''}">提示词</a></nav>
  <div id="pp" ${sub==='prompt'?'':'hidden'}></div>
  <div ${sub==='prompt'?'hidden':''}>
  <div id="tSteps">${stepper(f)}</div>
  <div class="detail"><div style="display:flex;flex-direction:column;gap:12px;min-width:0">
   ${concl}
   ${d.epic?epicCard(d.epic):''}
   <details class="blk fold"><summary><b>完整描述</b><span class="sub">原话、理解、补充的信息和验收标准</span></summary><div class="hdr" style="margin:8px 0 4px"><span class="grow"></span><button class="ghost" id="eb">编辑</button></div><div id="bodyv">${t.body?md(t.body):'<span class="sub">没有描述</span>'}</div></details>
   <div class="card"><div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">动态与讨论</h2>${nAuto?`<div class="seg" id="tlf"><button data-f="" class="on">全部</button><button data-f="talk">只看讨论</button><button data-f="auto">只看自动记录</button></div>`:''}</div><div class="tl" id="tl">${tl}</div>
     <div style="margin-top:14px"><textarea id="cm" placeholder="写评论（支持 Markdown）。智能体下次运行会读到最近的讨论。"></textarea><div class="row" style="margin-top:6px"><button class="primary" id="cb">评论</button>${ext.key?'<button id="pb">同步到 '+h(ext.system)+'</button>':''}</div></div></div>
   <details class="card adv" id="aiCard" ${f.live||reviewing||sub==='runs'?'open':''}><summary><b>执行记录与手动运行</b><span class="sub" id="tRunCount">${ticketRunCount(d.runs)}</span></summary>
     <div class="hdr" style="margin:10px 0"><span class="sub grow">手动指派：</span><select id="ag">${agentOptions()}</select><span id="mdw"></span>
     <div class="seg">${S.meta.modes.filter(([k])=>k!=='kb'&&k!=='ask'&&k!=='understand').map(([k,l])=>`<button data-m="${k}">${l}</button>`).join('')}</div></div>
     <label class="sub" style="display:flex;gap:6px;align-items:center;margin-bottom:6px"><input type="checkbox" id="kbAfter" style="width:auto"> 分析定位后，顺手补写涉及的业务流知识页（最多 2 页，只补还没写的）</label>
     <div class="sub" id="aihint">分析定位、修改方案只读代码；修改代码在独立的 git 工作树里进行，改动经你审阅后才采纳。</div>
     ${na.acc?'':`<div style="margin-top:10px"><b style="font-size:13px">人工验收</b> <span class="sub">通常在“待验证”时做；也可以直接在这里验收</span><div style="margin-top:6px">${accUi}</div></div>`}
     <div id="runv"></div>
     <div id="tRunHistory" style="margin-top:10px">${ticketRunHistory(d.runs)}</div></details>
  </div><div style="display:flex;flex-direction:column;gap:12px;min-width:0">
   <div class="card" id="pvc" hidden></div>
   ${pkgCard(d)}
   <details class="card eng" id="engc"><summary><b>工程细节</b><span class="sub">我来写、代码改动、候选代码入口、相关业务</span></summary><div class="engb">
   <div class="card" id="simc" hidden><h2>可能重复</h2><div id="simv"></div></div>
   <div class="card" id="hwc" hidden></div>
   <div id="upc"></div>
   ${mrBlock(d)}
   <details class="card" id="pathMapDetails"><summary><b>候选代码入口</b><span class="sub">固定版本、改动函数与静态分析限制</span></summary><div id="pathMapPanel" style="margin-top:12px"><p class="sub">展开后读取当前候选提交的代码入口；不会自动运行模型。</p></div></details>
   <div class="card"><div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">相关业务</h2><a href="javascript:void 0" onclick="showContext()">智能体看到的上下文</a></div><div id="rel"><span class="spin"></span></div></div></div></details>
  </div></div></div>`;
  ticketTopWire(d,na);
  get('/api/tickets/'+key+'/similar').then(r=>{const xs=r.similar.slice(0,3);if(xs.length){$('#simc h2').textContent=xs[0].score>=.4?'可能重复':'相似工单';$('#simv').innerHTML=simList(xs);$('#simc').hidden=false}}).catch(()=>{});
  if($('#tlf'))$('#tlf').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('#tlf').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));$('#tl').dataset.f=b.dataset.f;if(b.dataset.f==='auto')$('#tl').querySelectorAll('details.evg').forEach(x=>x.open=true)});
  if($('#evOpen'))$('#evOpen').onclick=()=>{const c=$('#cbox');c.hidden=!c.hidden;$('#evOpen').textContent=c.hidden?'看完整'+(res.mode==='plan'?'方案':'分析')+'和代码位置':'收起'};
  const save=async(f)=>{try{await post('/api/tickets/'+key,f);vTicket(key)}catch(e){toast(e.message)}};
  $('#fs').onchange=e=>save({status:e.target.value});$('#fy').onchange=e=>save({type:e.target.value});$('#fp').onchange=e=>save({priority:e.target.value});$('#fa').onchange=e=>save({assignee:e.target.value});
  $('#ttl').onclick=()=>{prompt2('修改标题',t.title,v=>save({title:v}))};
  $('#eb').onclick=()=>{$('#bodyv').innerHTML=`<textarea id="be" style="min-height:200px">${h(t.body)}</textarea><button class="primary" id="bs">保存</button>`;$('#bs').onclick=()=>save({body:$('#be').value})};
  $('#cb').onclick=async()=>{const b=$('#cm').value.trim();if(!b)return;try{await post('/api/tickets/'+key+'/comments',{body:b});vTicket(key)}catch(e){toast(e.message)}};
  if($('#pb'))$('#pb').onclick=()=>pushExt(key,$('#cm').value);
  const acc=async res=>{try{await post('/api/tickets/'+key+'/accept',{result:res,note:$('#accNote').value});toast(res==='pass'?'已验收通过，工单关闭':'已记录不通过，工单退回处理中');vTicket(key)}catch(e){toast(e.message)}};
  $('#accOk').onclick=()=>acc('pass');$('#accNo').onclick=()=>acc('fail');
  $('#accDraft').onclick=()=>{A.askTicket(t,'起草这张工单的人工验收说明：列出要验证的业务操作、预期结果，以及分析和改动里还没核实的点。只写说明，不要替人判断通过。','draft')};
  const run=async(mode,agent,model)=>{
    const a=S.meta.agents.find(x=>x.name===agent);if(a&&!a.available)toast('本机没找到 '+a.title+'，仍会尝试启动');
    try{const r=await post('/api/tickets/'+key+'/runs',{agent,mode,model,kb_after:mode==='analyze'&&$('#kbAfter').checked?2:0});toast('已交给 '+(a?a.title:agent)+' '+moLabel(mode)+(r.model?'（'+r.model+'）':''));vTicket(key)}catch(e){toast(e.message)}};
  const wireNext=()=>{const go={naAn:'analyze',naPlan:'plan',naFix:'fix'};
  Object.entries(go).forEach(([id,m])=>{if($('#'+id))$('#'+id).onclick=()=>run(m,defAgent(),'auto')});
  if($('#naVerify'))$('#naVerify').onclick=()=>save({status:'verify'});
  if($('#naShip'))$('#naShip').onclick=()=>post('/api/tickets/'+key+'/release',{}).then(r=>{toast(r.state==='merged'?'已合并，版本 '+r.version:r.why,6000);vTicket(key)}).catch(e=>toast(e.message,6000));
  if($('#naGo'))$('#naGo').onclick=()=>save({auto:'go'}).then(()=>toast('已交给自动处理'));
  if($('#naAsk'))$('#naAsk').onclick=async()=>{try{const r=await post('/api/tickets/'+key+'/ask-client',{});const url=location.origin+r.path;
    try{await navigator.clipboard.writeText(url)}catch(e){}modal(`<h2>把问题发给客户</h2><div class="sub">${r.questions} 个问题，${h(r.expires.slice(5,16))} 前有效${r.told_chat?'；已同时发到这单来源的群里':''}。客户用大白话回答，答复会写回验收标准，答清楚就自动开始。</div><input class="full" readonly value="${h(url)}" onclick="this.select()" style="margin-top:8px"><div class="sub" style="margin-top:6px">链接已复制，发给客户（微信、短信都行）。</div>`)}catch(e){toast(e.message,6000)}};
  ['naCcYes','naCcNo'].forEach(id=>{if($('#'+id))$('#'+id).onclick=()=>post('/api/tickets/'+key+'/client-change',{accept:id==='naCcYes'}).then(()=>{toast(id==='naCcYes'?'已采用，验收标准已更新':'已保留原来的验收标准');vTicket(key)}).catch(e=>toast(e.message,6000))});
  if($('#naIntakeRetry')){const button=$('#naIntakeRetry');button.onclick=async()=>{if(button.disabled)return;button.disabled=true;const refresh=S.ticketRefresh;
    try{await post('/api/tickets/'+key+'/intake-retry',{});if(S.ticketRefresh===refresh&&S.cur?.ticket?.key===key){await refresh();watchIntakeRecovery(key)}}
    catch(e){toast(e.message,6000)}finally{button.disabled=false}};}
  if($('#naIntakeLog'))$('#naIntakeLog').onclick=()=>showRun(d.intake_recovery.run);
  const hwBtn=id=>()=>{const b=$(id);if(b)return b.click();$('#engc').open=true;toast('稍等，开工包还在准备')};
  if($('#naHwPack'))$('#naHwPack').onclick=hwBtn('#hwPack');if($('#naHwScan'))$('#naHwScan').onclick=hwBtn('#hwScan');
  if($('#naClaim'))$('#naClaim').onclick=()=>post('/api/tickets/'+key+'/claim',{}).then(()=>{toast('已认领：自动处理不会再接这张单');vTicket(key)}).catch(e=>toast(e.message,6000));
  document.querySelectorAll('[data-hold]').forEach(b=>b.onclick=()=>save({hold:b.dataset.hold==='1'}).then(()=>toast(b.dataset.hold==='1'?'已接管，自动处理暂停':'已交回自动处理')));
  if($('#naReopen'))$('#naReopen').onclick=()=>save({status:'doing'});
  const openLog=()=>{$('#aiCard').open=true;$('#runv').scrollIntoView({behavior:'smooth',block:'start'})};
  if($('#naLog'))$('#naLog').onclick=()=>{const r=f.live||d.runs[0];if(r)showRun(r.id,true);openLog()};if($('#naReview'))$('#naReview').onclick=()=>{showRun(f.fx.id,true);openLog()};};
  wireNext();pkgWire(d);upWire(d);pvLoad(key);hwLoad(d);epicWire(d);
  S.ticketRefresh=ticketSummarySync(d,n=>{d=n;f=flowState(n);na=nextAction(n,f);wireNext()});
  ticketPathMapWire(key);
  watchIntakeRecovery(key);
  document.querySelectorAll('#aiCard .seg button').forEach(b=>b.onclick=()=>{
    if(b.dataset.m==='fix'&&!d.runs.some(r=>r.mode!=='fix'&&r.status==='done')){if(!window.confirmFix){window.confirmFix=1;toast('还没有分析或方案结论，建议先分析定位。再点一次直接修改。',4000);return}}
    run(b.dataset.m,$('#ag').value,$('#md').value)});
  try{const last=localStorage.getItem('tmh.agent');if(last)$('#ag').value=last}catch(e){}
  const paintMd=()=>{$('#mdw').innerHTML=modelSel('md',$('#ag').value);bindModel('md')};paintMd();
  $('#ag').onchange=e=>{try{localStorage.setItem('tmh.agent',e.target.value)}catch(x){}paintMd()};
  try{$('#kbAfter').checked=localStorage.getItem('tmh.kbAfter')!=='0'}catch(e){$('#kbAfter').checked=true}
  $('#kbAfter').onchange=e=>{try{localStorage.setItem('tmh.kbAfter',e.target.checked?'1':'0')}catch(x){}};
  if(sub==='prompt'){promptPane(t);return}
  if(d.runs.length)showRun((f.live||(reviewing?f.fx:null)||d.runs[0]).id,true);
  // between two automatic steps nothing is running: watch for the next one so the page never sits on a stale step
  stopPolls('auto');if(onAuto(d)){const refresh=S.ticketRefresh;poll(async()=>{if(S.ticketRefresh!==refresh||!onAuto(S.cur))return stopPolls('auto');try{const n=await refresh();if(n){const live=flowState(n).live;if(live&&String(live.id)!==$('#runv')?.dataset.runId)showRun(live.id,true)}}catch(e){}},3000,'auto')}
  loadRelated(t)}
// ---------- 大需求: the parent's spec card, its children with status and version, and the batch it is on
function epicCard(e){const c=e.counts,sp=e.spec,w=x=>c.total?x/c.total*100:0;
  return `<div class="card" id="epc"><div class="hdr" style="margin-bottom:6px"><span class="ev-tag info">大需求</span><h2 class="grow" style="margin:0">规格卡与子单</h2>${e.status==='closed'?'<span class="ev-tag ok">整体验收通过</span>':e.status==='verify'?'<span class="ev-tag warn">子单都完成了，等整体验收</span>':`<span class="sub">第 ${e.batch} 批 · 每批 ${e.wave} 个</span>`}</div>
   <dl class="c4"><dt>目标</dt><dd>${h(sp.goal)}</dd><dt>不能变</dt><dd>${h(sp.keep)}</dd><dt>不做</dt><dd>${h(sp.out)}</dd><dt>证据</dt><dd>${h(sp.evidence)}</dd></dl>
   <div style="margin-top:8px"><b style="font-size:13px">整体验收标准</b>${sp.done.map(a=>`<div style="font-size:13px;margin-top:3px"><span class="ev-tag ${a.open?'warn':'ok'}">${a.open?'待确认':h(a.id)}</span> ${h(a.text)}<div class="sub">怎么验：${h(a.check)}</div></div>`).join('')}</div>
   ${e.paused?`<div class="rfpz"><span class="grow"><b>已暂停自动推进：</b>${h(e.paused)}</span><button class="ghost" id="epRes">处理好了，恢复</button></div>`:''}
   <div class="row" style="gap:10px;align-items:center;margin:10px 0"><div class="rfbar"><i class="ok" style="width:${w(c.closed)}%"></i><i class="vf" style="width:${w(c.verify)}%"></i><i class="rl" style="width:${w(c.released-c.closed-c.verify)}%"></i></div><span class="sub" style="white-space:nowrap">完成 ${c.closed} · 待验收 ${c.verify} · 已放出 ${c.released} / ${c.total}</span><label class="sub rfau"><input type="checkbox" id="epAuto" ${e.auto?'checked':''}> 通过一批自动放下一批</label></div>
   <div class="tw"><table class="t"><tr><th class="num">#</th><th>子单</th><th>批次</th><th>依赖</th><th>状态</th><th>版本</th></tr>${e.children.map(x=>`<tr><td class="num">${x.order}</td><td><a href="#/t/${h(x.key)}">${h(x.key)}</a> ${h(x.title)}${x.follow_up?' <span class="ev-tag warn">整体验收退回的跟进</span>':''}${x.rejects?` <span class="ev-tag bad">退回 ${x.rejects}</span>`:''}${x.open_ac?' <span class="ev-tag warn">有待确认</span>':''}</td><td>${x.released?'第 '+x.batch+' 批':'<span class="sub">排队</span>'}</td><td>${x.after.length?x.after.map(h).join('、'):'<span class="sub">无</span>'}</td><td>${x.released?stPill(x.status):'<span class="sub">未放出</span>'}</td><td>${x.version?`<span class="key">${h(x.version)}</span>`:'<span class="sub">-</span>'}</td></tr>`).join('')}</table></div>
   ${e.status!=='closed'&&e.children.some(x=>!x.released)?'<div class="row" style="margin-top:8px"><button class="ghost" id="epRel">现在放出下一批</button></div>':''}
   ${e.log.length?`<div class="rflog">${e.log.slice(-6).reverse().map(x=>`<div><span class="sub">${h(x.at.slice(5,16))}</span> ${h(x.text)}</div>`).join('')}</div>`:''}</div>`}
function epicWire(d){const e=d.epic;if(!e)return;const P='/api/tickets/'+e.key+'/epic',re=()=>vTicket(e.key);
  if($('#epRes'))$('#epRes').onclick=()=>post(P,{action:'resume'}).then(()=>{toast('已恢复自动推进');re()}).catch(x=>toast(x.message));
  if($('#epAuto'))$('#epAuto').onchange=ev=>post(P,{action:'auto',on:ev.target.checked}).then(re).catch(x=>toast(x.message));
  if($('#epRel'))$('#epRel').onclick=()=>post(P,{action:'release'}).then(r=>{toast('已放出 '+r.opened.join('、'));re()}).catch(x=>toast(x.message,5000))}
// ---------- ticket prompt tab: one prompt per scenario, to paste into any agent or write into the project
async function promptPane(t,scene){
  if(!scene){try{scene=localStorage.getItem('tmh.scene')}catch(e){}}
  const r=await get('/api/tickets/'+t.key+'/prompt?scene='+(scene||'bugfix'));const w=r.written||{};
  const sc=r.scenes.find(s=>s.key===r.scene)||{};
  const KS={flow:'业务流',tbl:'表',code:'代码',page:'知识页'};
  const inProj=w.cursor||w.claude;
  $('#pp').innerHTML=`<div class="pgrid"><div class="card" style="min-width:0">
    <div class="hdr" style="margin-bottom:8px"><h2 class="grow" style="margin:0">按场景生成的提示词</h2><div class="seg">${r.scenes.map(s=>`<button data-s="${s.key}" class="${s.key===r.scene?'on':''}" title="${h(s.hint)}">${h(s.label)}</button>`).join('')}</div></div>
    <div class="sub" style="margin-bottom:10px">${h(sc.hint)}工单内容、关联的业务流、表、代码位置和知识页已经拼好，可以直接粘贴到 Cursor、Claude Code、Codex 或任何对话里。</div>
    <textarea id="ptx" class="ptx" readonly aria-label="提示词">${h(r.text)}</textarea>
    <div class="row" style="gap:8px;margin-top:10px;align-items:center"><button class="primary" id="pcp">复制提示词</button><button id="pcu">写入 Cursor 规则</button><button id="pcl">写入 CLAUDE.md</button><span class="grow"></span><span class="sub">${r.chars.toLocaleString()} 字</span></div></div>
   <div style="display:flex;flex-direction:column;gap:12px;min-width:0">
    <div class="card"><h2>写进项目</h2>
     ${inProj?`<div style="margin-bottom:8px"><span class="ev-tag ${w.ticket===t.key?'ok':'warn'}">项目里现在是 ${h(w.ticket||'某张工单')} 的段落</span></div>
       <div class="sub">${[w.cursor?'<code>.cursor/rules/tmh-ticket.mdc</code>':'',w.claude?'<code>CLAUDE.md</code> 末尾的临时段落':''].filter(Boolean).join('、')}。在这个项目里打开的 Cursor 或 Claude Code 会自动带上它，IDE 里调用 tmh MCP 工具也会记到这张工单上。</div>
       <button class="ghost" id="pclr" style="margin-top:8px">从项目里清除</button>`
     :`<div class="sub">还没有写入。写入后，在这个项目里打开的 Cursor 或 Claude Code 会自动带上这张工单的上下文；IDE 里调用 tmh MCP 工具也会记到这张工单上。只会写 <code>.cursor/rules/tmh-ticket.mdc</code> 和 <code>CLAUDE.md</code> 里带标记的一段，不碰其他内容。</div>`}
     <div class="hint" style="margin-top:10px">复制和写入都会记在工单动态里，计入提效报告的 AI 参与率。</div></div>
    <div class="card"><h2>带上的依据</h2>${r.sources.length?r.sources.map(x=>`<div class="flowrow"><span class="tag">${KS[x.kind]||x.kind}</span><span class="grow" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${h(x.id)}">${h(x.title||x.id)}</span></div>`).join(''):'<div class="sub">知识库里没有检索到依据，提示词只带了工单本身。</div>'}</div>
   </div></div>`;
  document.querySelectorAll('#pp .seg button').forEach(b=>b.onclick=()=>{try{localStorage.setItem('tmh.scene',b.dataset.s)}catch(e){}promptPane(t,b.dataset.s)});
  const use=async a=>{try{return await post('/api/tickets/'+t.key+'/prompt',{scene:r.scene,action:a})}catch(e){toast(e.message,5000)}};
  $('#pcp').onclick=async()=>{const ta=$('#ptx');let ok=false;try{await navigator.clipboard.writeText(ta.value);ok=true}catch(e){ta.focus();ta.select();try{ok=document.execCommand('copy')}catch(x){}}
    toast(ok?'已复制「'+sc.label+'」提示词':'没能自动复制，已选中全文，请按 Ctrl+C');if(ok)use('copy')};
  const wr=async a=>{const x=await use(a);if(x){toast('已写入 '+x.files.join('、'));promptPane(t,r.scene)}};
  $('#pcu').onclick=()=>wr('cursor');$('#pcl').onclick=()=>wr('claude');
  if($('#pclr'))$('#pclr').onclick=async()=>{const x=await use('clear');if(x){toast('已清除');promptPane(t,r.scene)}}}
function mrBlock(d){
  const f=d.runs.find(r=>r.mode==='fix');if(!f)return '';
  const dec=f.decision||'';let st,msg;
  if(dec.startsWith('accepted')){const [br,sha]=dec.slice(9).split('@');st='<span class="ev-tag ok">已提交到分支</span>';msg=`分支 <code>${h(br)}</code>，提交 <code>${h(sha||'')}</code>。${MERGE_ON()?'验收通过后自动合并进主干；如果主干上后来的改动和它冲突，会交回智能体重做。':'验收通过后由人合并这个分支到主干。'}`}
  else if(dec==='discarded'){st='<span class="ev-tag mute">已放弃</span>';msg='这次改动已放弃，工作树和分支已删除。'}
  else if(f.status==='done'){st='<span class="ev-tag warn">待人工审阅</span>';msg=`在“执行过程”里看 #${f.id} 的代码改动，采纳后提交到独立分支，不会动你的工作目录。`}
  else{st=`<span class="ev-tag ${f.status==='failed'?'bad':'info'}">${{failed:'修改失败',running:'修改中',queued:'排队',cancelled:'已取消'}[f.status]||f.status}</span>`;msg=`运行 #${f.id}`}
  return `<div class="blk mr"><h3>代码改动 ${st}</h3><div class="sub">${msg}</div></div>`}
function prompt2(title,val,cb){modal(`<h2>${h(title)}</h2><input class="full" id="pv" value="${h(val)}"><div style="margin-top:10px"><button class="primary" id="pok">保存</button></div>`);$('#pv').focus();$('#pok').onclick=()=>{closeModal();cb($('#pv').value)}}
function evHtml(e){
  const icon={prompt:'提示词','prompt-clear':'提示词',created:'创建',status:'状态',assign:'指派',edit:'编辑',comment:'',run:'智能体','run-done':'智能体','run-failed':'智能体','run-cancelled':'智能体',accept:'采纳',discard:'放弃',link:'关联',import:'导入',sync:'同步',kb:'知识库'}[e.kind]||e.kind;
  if(e.kind==='comment')return `<div class="ev comment"><div class="dot"></div><div class="grow" style="min-width:0"><span class="who">${h(e.author||'-')}</span><span class="when">${ago(e.ts)}</span><div class="cbody">${md(e.body)}</div></div></div>`;
  const rr=(e.data||{}).run;
  return `<div class="ev ${h(e.kind)}${isMachine(e.author)?' auto':''}"><div class="dot"></div><div class="grow" style="min-width:0"><span class="who">${h(e.author||'-')}</span> ${h(e.body)}${rr?` <a href="javascript:void 0" onclick="showRun(${rr})">#${rr}</a>`:''}<span class="when">${ago(e.ts)}</span>
  ${e.kind==='run-done'&&(e.data||{}).summary?`<div class="cbody sub">${h(e.data.summary.slice(0,220))}${e.data.summary.length>220?'…':''}</div>`:''}</div></div>`}
async function loadRelated(t){
  try{const r=await get('/api/tickets/'+t.key+'/related');const linked=((t.links||{}).flows)||[],ok=okFlows(S.cur);
    const nm=Object.fromEntries(r.flows.map(f=>[f.id,f.name]));const name=f=>h(nm[f]||f.replace(/^flow:/,''));
    const row=(f,btns)=>`<div class="flowrow"><a class="fx" href="javascript:void 0" onclick="showFlow('${h(f)}')">${name(f)}</a><span class="fb">${btns}</span></div>`;
    const mine=linked.filter(f=>ok.has(f)),sugg=linked.filter(f=>!ok.has(f)),more=r.flows.filter(f=>!linked.includes(f.id));
    let html='';
    html+='<h3>已关联</h3>'+(mine.length?mine.map(f=>row(f,`<button class="ghost" onclick="linkFlow('${t.key}','${h(f)}',0)">取消</button>`)).join(''):'<div class="sub">还没有人确认过。</div>');
    if(sugg.length)html+=`<div class="hdr" style="margin-top:10px"><h3 class="grow" style="margin:0">智能体建议 <span class="sub" style="font-weight:400">待确认</span></h3><a href="javascript:void 0" onclick="confirmFlows('${t.key}')">全部确认</a></div>`+sugg.map(f=>row(f,`<button class="ghost" onclick="confirmFlows('${t.key}',['${h(f)}'])">确认</button><button class="ghost" onclick="linkFlow('${t.key}','${h(f)}',0)">移除</button>`)).join('');
    const mr=more.map(f=>`<div class="flowrow"><div class="fx"><a href="javascript:void 0" onclick="showFlow('${h(f.id)}')">${h(f.name)}</a><div class="sub">${h(f.domain||'')}${f.tables.length?' · '+f.tables.slice(0,3).map(x=>h(x[0])).join('、'):''}</div></div><button class="ghost" onclick="linkFlow('${t.key}','${h(f.id)}',1)">关联</button></div>`);
    const extra=(r.tables.length?'<h3 style="margin-top:10px">表</h3><div class="chips">'+r.tables.map(x=>`<span class="tag" title="${x.users} 条业务流使用">${h(x.name)}</span>`).join(' ')+'</div>':'')
      +(r.pages.length?'<h3 style="margin-top:10px">知识页</h3>'+r.pages.slice(0,5).map(p=>`<div class="flowrow"><a class="fx" href="#/kb/${encodeURIComponent(p.id)}">${h(p.title)}</a><span class="tag">${h(p.status)}</span></div>`).join(''):'');
    if(mr.length||extra)html+=`<details class="more" style="margin-top:10px"><summary>其他可能相关${mr.length?' · 业务流 '+mr.length+' 条':''}${r.tables.length?' · 表 '+r.tables.length+' 张':''}</summary>${mr.join('')}${extra}</details>`;
    if(!linked.length&&!more.length&&!r.tables.length&&!r.pages.length)html='<div class="sub">知识库里没找到相关内容（或这个项目还没有知识库）。</div>';
    $('#rel').innerHTML=html}catch(e){$('#rel').textContent=e.message}}
async function confirmFlows(key,fs){try{await post('/api/tickets/'+key,{confirm_flows:fs||'*'});vTicket(key)}catch(e){toast(e.message)}}
async function linkFlow(key,f,on){try{await post('/api/tickets/'+key,on?{link_flow:f}:{unlink_flow:f});vTicket(key)}catch(e){toast(e.message)}}
async function showContext(){const r=await get('/api/tickets/'+S.cur.ticket.key+'/context');modal('<h2>智能体看到的知识库上下文</h2><div class="sub">每次运行都会把它和工单一起交给智能体，让它从这些业务流、表和代码位置开始，而不是通读仓库。</div>'+md(r.text),true)}
async function showFlow(id){
  const f=await get('/api/projects/'+S.proj+'/flows/'+encodeURIComponent(id));const crud=f.data.crud||{};
  modal(`<h2>${h(f.name)}</h2><div class="sub">${h(f.domain||'')} · <span class="key">${h(f.file)}:${f.line}</span></div>
   <p><b>入口</b> <code>${h(f.data.trigger||'')}</code> → <code>${h(f.data.handler||'')}</code></p>
   ${Object.keys(crud).length?'<h3>读写的表</h3><div class="chips">'+Object.entries(crud).map(([k,v])=>`<span class="tag">${h(k)} ${h(v)}</span>`).join(' ')+'</div>':''}
   ${f.steps.length?'<h3 style="margin-top:12px">调用链（前 '+f.steps.length+' 步）</h3><div style="max-height:260px;overflow:auto">'+f.steps.map(s=>`<div class="sub"><span class="key">${h(s.file)}:${s.line}</span> ${h(s.label)}</div>`).join('')+'</div>':''}
   <h3 style="margin-top:12px">关联的工单</h3>${f.tickets.length?f.tickets.map(t=>`<div><a href="#/t/${t.key}" onclick="closeModal()">${t.key}</a> ${h(t.title)} ${stPill(t.status)}</div>`).join(''):'<div class="sub">还没有</div>'}
   <div style="margin-top:14px"><button onclick="closeModal();newTicket({title:'',body:'业务流：${h(f.id)}\\n'})">为这条业务流新建工单</button></div>`,true)}

// ---------- runs
function runRecoveryBlocked(r){return r.lifecycle?.recovery?.state==='blocked'}
function runStopReceiptReady(r){const c=r.lifecycle;
  return !!c&&typeof c==='object'&&!Array.isArray(c)&&c.finished===true&&c.stopped_reason!=='recovery_pending'&&Array.isArray(c.attempts)&&
    c.attempts.every(a=>a&&typeof a==='object'&&!Array.isArray(a)&&(a.pid==null?a.cleanup?.complete!==false:a.cleanup?.complete===true))&&
    (c.recovery===undefined||!!c.recovery&&typeof c.recovery==='object'&&!Array.isArray(c.recovery)&&c.recovery.state==='complete');}
function runStillActive(r){return !runRecoveryBlocked(r)&&(['running','queued'].includes(r.status)||r.lifecycle?.finished===false)}
function runLifecycleHtml(r){
  const c=r.lifecycle;
  if(!c||typeof c!=='object')return r.lifecycle_error?`<div class="hint" role="status">${h(r.lifecycle_error)}。尚不能确认进程回收状态。</div>`:'';
  const recovery=c.recovery&&typeof c.recovery==='object'&&!Array.isArray(c.recovery)?c.recovery:null,blocked=runRecoveryBlocked(r),ready=runStopReceiptReady(r);
  const rawAttempts=Array.isArray(c.attempts)?c.attempts:[],attempts=rawAttempts.filter(a=>a&&typeof a==='object'&&!Array.isArray(a)),invalid=c.attempts!==undefined&&(!Array.isArray(c.attempts)||attempts.length!==rawAttempts.length),reason={timeout:'达到整次任务总时限',cancelled:'已请求停止',orphaned:'启动器已退出，仍发现子进程',cleanup_failed:'进程回收未完成',error:'执行发生错误',owner_lost:ready?'平台连接中断，受管进程已停止':'平台连接中断，受管进程停止情况尚未确认',restarted:'平台重启后恢复停止记录',recovery_pending:'平台重启后的停止回执尚未核对完成'}[c.stopped_reason]||c.stopped_reason||'';
  const stopping=c.finished===false&&(!!c.stopped_reason||['failed','cancelled'].includes(r.status)),incomplete=attempts.some(a=>a.cleanup?.complete===false);
  const phase=blocked?'无法确认受管进程已安全停止，不能重新运行；请检查完整回执。':invalid?'运行停止回执格式异常，尚不能确认进程回收状态。':c.stopped_reason==='recovery_pending'?'平台重启后的停止回执尚未核对完成，不能重新运行。':recovery?.state==='complete'&&!ready?'恢复回执仍不完整，无法确认进程回收状态，不能重新运行。':stopping?'正在回收运行进程，完成前不能重新运行。':c.finished===true?(incomplete?'进程回收未完成，请查看回执中的残留进程与错误。':attempts.length&&attempts.every(a=>a.cleanup?.complete===true)?'本轮执行已结束，进程回收完成。':'本轮执行已结束；进程回收情况以各次回执为准。'):'本轮运行尚未结束。';
  const errors=recovery?(Array.isArray(recovery.errors)?recovery.errors:recovery.errors?[recovery.errors]:[]):[];
  return `<section class="run-check" aria-label="运行时限与停止状态"><p role="status"><b>${h(phase)}</b></p>${reason?`<p>停止原因：${h(reason)}</p>`:''}${recovery?`<div class="sub" style="white-space:pre-wrap;overflow-wrap:anywhere">${h(recovery.reason||'')}</div><p class="sub">${recovery.output_complete===true?'已确认输出完整。':'输出尚未确认完整，请核对原始回执与日志。'} 恢复记录只说明进程收尾，不代表业务成功，也不代表测试或验收通过。</p>${errors.length?'<ul>'+errors.map(e=>'<li style="white-space:pre-wrap;overflow-wrap:anywhere">'+h(typeof e==='string'?e:JSON.stringify(e,null,2))+'</li>').join('')+'</ul>':''}`:''}<p class="sub">${c.started_at?'开始：'+h(c.started_at)+' · ':''}整次任务总时限：${h(c.timeout_seconds==null?'未记录':c.timeout_seconds+' 秒')}${c.elapsed_seconds==null?'':' · 已记录耗时：'+h(c.elapsed_seconds)+' 秒'}</p>${attempts.length?`<details><summary>查看每次执行的退出与回收结果（${attempts.length} 次）</summary>${attempts.map(a=>`<p>第 ${h(a.attempt)} 次 · ${h(a.kind||'执行')} · 退出码 ${h(a.returncode==null?'尚未记录':a.returncode)} · ${a.cleanup?.complete===true?'回收完成':a.cleanup?.complete===false?'回收未完成':'尚无回收回执'}</p>`).join('')}</details>`:''}<details><summary>查看完整运行停止回执</summary><pre class="log">${h(JSON.stringify(c,null,2))}</pre></details></section>`}
function runRecoveryHtml(r){
  if(!['failed','cancelled'].includes(r.status))return '';
  const reasons=Array.isArray(r.retry_blocked)?r.retry_blocked:[],ready=runStopReceiptReady(r),details=(reasons.length?`<p class="sub">${h(reasons.join('；'))}</p>`:'')+(!ready?'<p class="sub">停止回执尚不完整，不能重新运行；请检查完整回执。</p>':'')+(runRecoveryBlocked(r)?'<button type="button" data-run-recover>重新检查停止回执</button>':'');
  if(r.delivery_id)return `<section class="run-review"><h3>继续这个交付阶段</h3><p>已有改动和失败记录保留。请在交付阶段页核对当前资料与复核条件后重新执行。</p>${details}<a class="btn" href="#/delivery/${encodeURIComponent(r.delivery_id)}/${encodeURIComponent(r.delivery_stage||'')}" onclick="closeModal()">返回交付阶段</a></section>`;
  return `<section class="run-review"><h3>继续处理</h3><p class="sub">原运行和已有改动保留；重新运行会创建新的记录，不代表原运行已经成功。</p>${details}${r.can_retry===true&&ready&&!runStillActive(r)?'<button type="button" class="primary" data-run-resume>保留改动并重新运行</button>':''}</section>`}
function runVerificationHtml(r){
  const v=r.verification,labels={pass:'通过',fail:'失败',skip:'未执行',unknown:'未知'};
  if(!v||typeof v!=='object')return '<div class="hint">没有实际验证记录。运行完成不代表构建或测试通过；请先重新验证，或检查项目的验证命令。</div>';
  const commands=Array.isArray(v.commands)?v.commands:[];
  return `<p>命令检查：<b>${h(labels[v.check]||'尚无结论')}</b> · 实现诊断：<b>${h(v.diagnosis_invalidated?'未知（待重新诊断）':labels[v.verdict]||'尚无结论')}</b></p><p class="sub">以下是实际执行的命令。构建、测试和其他检查各自以记录为准；人工复核不会改变这些结果。</p>${v.skip?`<div class="hint">${h(v.skip)}</div>`:''}${commands.length?commands.map(c=>`<details class="run-check" ${c.exit_code!==0?'open':''}><summary>${h(c.kind||'检查')} · ${c.exit_code===0?'通过':'未通过'} · 退出码 ${h(c.exit_code==null?'未记录':c.exit_code)}</summary><pre>${h(Array.isArray(c.command)?c.command.join(' '):c.command||'命令未记录')}</pre>${c.output||c.tail?`<pre class="log">${h(c.output||c.tail)}</pre>`:''}</details>`).join(''):'<div class="hint">没有执行命令的记录，不能据此判断测试通过。</div>'}<details class="run-check"><summary>查看完整验证记录</summary><pre class="log">${h(JSON.stringify(v,null,2))}</pre></details>`}
function runConclusionHtml(r){
  const original=r.result?md(r.result):'<p class="sub">这次运行没有单独的结论，请查看过程和代码改动。</p>',reason=r.verification?.diagnosis_invalidated;
  if(!reason)return original;
  return `<div class="hint" role="status"><b>当前结论已失效</b><p>${h(typeof reason==='string'?reason:'原运行诊断不再适用于当前改动。')}</p><p>请以当前实际验证记录为准。原运行输出中的判断仅供历史参考，不能证明当前改动已解决问题。</p></div><h3>当前实际验证</h3>${runVerificationHtml(r)}<details class="run-check"><summary>原运行历史输出（仅供参考）</summary>${original}</details>`}
function runPreviewPath(r){return r.mode==='fix'&&r.ticket_key&&String(r.decision||'').startsWith('accepted:')?'/api/tickets/'+encodeURIComponent(r.ticket_key)+'/preview':''}
function runPreviewHtml(r,d,error){
  if(r.decision==='discarded')return '<p class="sub">这次改动已放弃，没有可供验收的预览。</p>';
  if(!String(r.decision||'').startsWith('accepted:'))return '<p class="sub">先核对代码与验证结果，再采纳到独立分支，才能预览这次改动。采纳不会合并主干，也不代表用户已验收。</p>';
  if(!r.ticket_key)return '<p class="sub">这次运行没有关联执行工单，暂时无法在这里启动预览。</p>';
  const refresh='<button type="button" data-run-preview-refresh>刷新预览状态</button>';
  if(error)return `<div class="bad" role="alert">${h(error)}</div><div class="row">${refresh}</div>`;
  if(!d)return '<p class="sub" role="status"><span class="spin"></span> 正在核对本次改动的预览状态…</p>';
  if(Number(d.run_id)!==Number(r.id)||!d.expected_commit)return `<div class="hint">暂时无法确认预览对应本次运行，没有提供打开入口。请刷新状态后再试。</div><div class="row">${refresh}</div>`;
  const p=d.preview||{},same=d.matches_run===true,ready=same&&p.state==='up'&&typeof d.url==='string'&&d.url.startsWith('/pv/'),starting=same&&p.state==='starting';
  const mismatch=!!p.commit&&!same,failed=p.state==='failed';
  const why=ready?'本次改动已启动，可以打开实际操作。请核对需求与验收场景；打开预览不代表验收通过。':starting?'本次改动正在启动，准备好后会出现打开入口。':mismatch?'当前预览无法确认对应本次改动。请启动本次预览，再验证当前实现。':failed?'本次预览未能启动，请查看原因后重试。':'本次改动已保存到独立分支，预览尚未启动。';
  return `<p class="${mismatch||failed?'hint':'sub'}" role="status">${starting?'<span class="spin"></span> ':''}${why}</p>${failed&&p.why?`<div class="bad">${h(p.why)}</div>`:''}${p.tail?`<details class="run-check" ${failed?'open':''}><summary>预览启动日志（服务返回的最近记录）</summary><pre class="log">${h(p.tail)}</pre></details>`:''}<div class="row run-actions">${ready?`<a class="btn primary" href="${h(d.url)}" target="_blank" rel="noopener">打开本次改动预览 ↗</a>`:''}${!starting&&d.cmd?`<button type="button" data-run-preview-start ${ready?'':'class="primary"'}>${ready?'重新启动本次预览':mismatch?'切换到本次预览':failed?'重试本次预览':'启动本次预览'}</button>`:''}${refresh}</div>${!d.cmd?`<p class="sub">尚未配置项目的预览命令。<a href="#/t/${encodeURIComponent(r.ticket_key)}" onclick="closeModal()">到执行工单配置</a></p>`:''}${!d.own_address?'<p class="sub">当前预览使用浏览器隔离环境。需要脚本读写数据的应用应先配置独立预览端口。</p>':''}<details class="run-check"><summary>核对代码版本</summary><p class="sub">本次改动：<code>${h(d.expected_commit)}</code><br>当前预览：<code>${h(p.commit||'尚无')}</code></p></details>`}
async function showRun(rid,inline){
  const target=inline?$('#runv'):$('#mbody'),tag=inline?'run':'modal';if(!target)return;
  const token=String(S.runViewSeq=(S.runViewSeq||0)+1);let since=0,last=null,pane='res',busy=false,checking=false,preview=null,previewError='',checkError='',watcher=null,previewSeq=0,previewMutating=false,ticketSig='';
  if(inline)target.dataset.runId=String(rid);
  if(!inline)modal('',true);stopPolls(tag);target.innerHTML=`<div class="run-detail" data-run-view="${token}"><span class="spin"></span> 正在读取运行记录…</div>`;
  const current=()=>target.isConnected&&!!target.querySelector(`[data-run-view="${token}"]`)&&(inline||!$('#modal').hidden);
  const error=message=>{if(current()){const el=target.querySelector('[data-run-error]');if(el){el.textContent=message;el.hidden=false}else target.innerHTML=`<div class="run-detail" data-run-view="${token}"><div class="bad" role="alert">${h(message)}</div><button type="button" data-run-retry>重新读取运行记录</button></div>`;const retry=target.querySelector('[data-run-retry]');if(retry)retry.onclick=()=>showRun(rid,inline)}};
  S.logs=S.logs||{};S.logs[rid]='';
  const draw=r=>{
    const live=runStillActive(r),cancelable=['running','queued'].includes(r.status)&&!r.lifecycle?.stopped_reason,fix=r.mode==='fix',accepted=String(r.decision||'').startsWith('accepted:'),discarded=r.decision==='discarded';
    const tabs=[['res','结论'],...(r.diff?[['diff','代码改动']]:[]),...(fix?[['verify','实际验证']]:[]),['log','过程']];if(!tabs.some(t=>t[0]===pane))pane='res';
    return `<div class="run-detail" data-run-view="${token}"><div class="hdr" style="margin:10px 0 0"><b>#${r.id} ${h(r.agent)}${mTag(r)} · ${moLabel(r.mode)}</b><span class="tag">${h(runRecoveryBlocked(r)?'恢复受阻':live&&!cancelable?'正在停止':{queued:'排队',running:'运行中',done:'完成',failed:'失败',cancelled:'已取消'}[r.status]||r.status)}</span>${live?'<span class="spin"></span>':''}<span class="sub grow">${h(r.author)} ${ago(r.created)}</span>${cancelable?`<button type="button" class="danger" data-run-cancel>停止</button>`:''}<a href="javascript:void 0" onclick="showPrompt(${r.id})">提示词</a></div><div class="bad" data-run-error role="alert" hidden></div>${runLifecycleHtml(r)}${runRecoveryHtml(r)}
    ${live?`<pre class="log" data-run-log>${h(S.logs[r.id]||'')}</pre>`:`<div class="tabs" role="tablist" aria-label="运行记录">${tabs.map(([key,label])=>`<button type="button" role="tab" aria-selected="${pane===key}" class="${pane===key?'on':''}" data-tab="${key}">${label}</button>`).join('')}</div><div data-pane="res" ${pane==='res'?'':'hidden'}>${runConclusionHtml(r)}</div>${r.diff?`<div data-pane="diff" ${pane==='diff'?'':'hidden'}>${diffHtml(r.diff)}</div>`:''}${fix?`<div data-pane="verify" ${pane==='verify'?'':'hidden'}>${runVerificationHtml(r)}</div>`:''}<div data-pane="log" ${pane==='log'?'':'hidden'}><pre class="log" data-run-log>${h(S.logs[r.id]||'')}</pre></div>`}
    ${fix&&!live?`<section class="run-review"><h3>试用本次改动</h3><p class="sub">代码与验证结果在上方。将改动保存到独立分支后，就可以启动对应版本的预览。</p>${checking?'<p role="status"><span class="spin"></span> 正在重新验证，完成后会更新实际验证记录…</p>':''}${checkError?`<div class="bad" role="alert">${h(checkError)}</div>`:''}${accepted?'<p class="hint">本次改动已采纳到独立分支。主干合并和用户验收仍需各自完成。</p>':discarded?'<p class="hint">这次改动已放弃。</p>':r.status==='done'&&r.exit_code===0&&r.diff?`<div class="row run-actions"><button type="button" class="primary" data-run-decision="accept" ${checking?'disabled':''}>采纳到独立分支</button><button type="button" class="danger" data-run-decision="discard" ${checking?'disabled':''}>放弃改动</button></div>`:'<p class="hint">本次运行未成功产生可采纳的改动。请查看失败原因与过程，再决定下一步。</p>'}${r.status==='done'&&!discarded&&r.diff?`<div class="row run-actions"><button type="button" data-run-recheck ${checking?'disabled':''}>${checking?'正在重新验证…':'重新验证本次改动'}</button></div>`:''}<div data-run-preview>${runPreviewHtml(r,preview,previewError)}</div></section>`:''}</div>`};
  const paintPreview=()=>{if(!current())return;const el=target.querySelector('[data-run-preview]');if(el){el.innerHTML=runPreviewHtml(last,preview,previewError);wirePreview()}};
  const loadPreview=async()=>{if(!current()||previewMutating||!runPreviewPath(last))return;const request=++previewSeq;try{const d=await get(runPreviewPath(last)+'?run_id='+encodeURIComponent(rid));if(!current()||request!==previewSeq)return;preview=d;previewError=''}catch(e){if(!current()||request!==previewSeq)return;preview=null;previewError=e.message}paintPreview()};
  const wirePreview=()=>{
    const refresh=target.querySelector('[data-run-preview-refresh]');if(refresh){refresh.disabled=previewMutating;refresh.onclick=async()=>{if(!current()||previewMutating)return;refresh.disabled=true;await loadPreview();watch()}};
    const start=target.querySelector('[data-run-preview-start]');if(start){start.disabled=checking||previewMutating;start.onclick=async()=>{if(!current()||busy||checking||!runPreviewPath(last))return;const request=++previewSeq;busy=true;previewMutating=true;start.disabled=true;if(refresh)refresh.disabled=true;start.textContent='正在启动本次预览…';try{const d=await post(runPreviewPath(last),{action:'start',run_id:Number(rid)});if(!current()||request!==previewSeq)return;preview=d;previewError='';previewMutating=false;paintPreview();watch()}catch(e){if(current()&&request===previewSeq){previewError=e.message;previewMutating=false;paintPreview()}}finally{busy=false;previewMutating=false;if(current())wirePreview()}}}};
  const paint=()=>{
    if(!current())return;target.innerHTML=draw(last);
    const tabs=Array.from(target.querySelectorAll('[data-tab]'));tabs.forEach((b,i)=>{b.onclick=()=>{pane=b.dataset.tab;tabs.forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-selected',String(x===b))});target.querySelectorAll('[data-pane]').forEach(p=>p.hidden=p.dataset.pane!==pane)};b.onkeydown=e=>{const n=e.key==='ArrowRight'?(i+1)%tabs.length:e.key==='ArrowLeft'?(i+tabs.length-1)%tabs.length:e.key==='Home'?0:e.key==='End'?tabs.length-1:null;if(n!==null){e.preventDefault();tabs[n].focus();tabs[n].click()}}});
    target.querySelectorAll('[data-run-decision]').forEach(b=>b.onclick=async()=>{if(busy||checking)return;busy=true;target.querySelectorAll('[data-run-decision]').forEach(x=>x.disabled=true);try{await post(`/api/runs/${rid}/decide`,{decision:b.dataset.runDecision});if(!current())return;toast(b.dataset.runDecision==='accept'?'已采纳到独立分支，可以启动本次预览':'已放弃这次改动');await read();watch()}catch(e){if(!current())return;error(e.message);target.querySelectorAll('[data-run-decision]').forEach(x=>x.disabled=false)}finally{busy=false}});
    const cancel=target.querySelector('[data-run-cancel]');if(cancel)cancel.onclick=async()=>{if(busy||!current())return;busy=true;cancel.disabled=true;try{await post(`/api/runs/${rid}/cancel`,{});if(!current())return;toast('已请求停止');await read();watch()}catch(e){if(current()){error(e.message);cancel.disabled=false}}finally{busy=false}};
    const retry=target.querySelector('[data-run-resume]');if(retry)retry.onclick=async()=>{if(busy||checking||!current())return;busy=true;retry.disabled=true;retry.textContent='正在创建继续运行…';try{const next=await post(`/api/runs/${rid}/retry`,{});if(!current())return;if(!next||!Number.isInteger(next.id)||next.id===Number(rid))throw new Error('未能取得新的运行记录，请刷新后核对。');await showRun(next.id,inline)}catch(e){if(current()){error(e.message);retry.disabled=false;retry.textContent='保留改动并重新运行'}}finally{busy=false}};
    const recover=target.querySelector('[data-run-recover]');if(recover)recover.onclick=async()=>{if(busy||!current())return;busy=true;recover.disabled=true;try{await post(`/api/runs/${rid}/recover`,{});if(!current())return;await read();watch()}catch(e){if(current()){error(e.message);recover.disabled=false}}finally{busy=false}};
    const re=target.querySelector('[data-run-recheck]');if(re)re.onclick=async()=>{if(busy||checking)return;busy=true;re.disabled=true;try{await post(`/api/runs/${rid}/recheck`,{});if(!current())return;checking=true;checkError='';paint();watch()}catch(e){if(!current())return;error(e.message);re.disabled=false}finally{busy=false}};
    wirePreview();if(runStillActive(last)){const lg=target.querySelector('[data-run-log]');if(lg)lg.scrollTop=lg.scrollHeight}};
  const read=async()=>{const r=await get(`/api/runs/${rid}?since=${since}`);if(!current())return;S.logs[rid]+=r.output||'';since=r.output_len;last=r;
    if(r.mode==='fix'&&r.status==='done'&&!runStillActive(r)&&r.decision!=='discarded'){try{const c=await get(`/api/runs/${rid}/recheck`);if(!current())return;checking=!!c.running;checkError=''}catch(e){checkError='无法读取重新验证状态：'+e.message}}
    paint();await loadPreview();if(!current())return;
    if(r.ticket_key&&S.cur?.ticket?.key===r.ticket_key&&S.ticketRefresh){const sig=JSON.stringify([r.id,r.status,r.decision,r.lifecycle?.finished]);if(sig!==ticketSig){try{if(await S.ticketRefresh())ticketSig=sig}catch(e){error('运行记录已更新，但工单摘要未同步：'+e.message)}}}};
  const stopWatch=()=>{if(watcher!==null){clearInterval(watcher);S.polls=S.polls.filter(p=>p.id!==watcher);watcher=null}};
  const watch=()=>{stopWatch();if(!current()||!last)return;const live=runStillActive(last),starting=preview?.matches_run===true&&preview?.preview?.state==='starting';if(!live&&!checking&&!starting)return;
    watcher=poll(async()=>{if(!current()){stopWatch();return}if(busy)return;busy=true;try{if(runStillActive(last))await read();else if(checking){const c=await get(`/api/runs/${rid}/recheck`);if(!current())return;if(!c.running){checking=false;await read()}else await loadPreview()}else await loadPreview();watch()}catch(e){error(e.message)}finally{busy=false}},1800,tag)};
  try{await read();watch()}catch(e){error(e.message)}}
async function showPrompt(rid){const r=await get(`/api/runs/${rid}?prompt=1&since=999999999`);modal('<h2>交给智能体的提示词 #'+rid+'</h2>'+md(r.prompt),true)}
async function cancelRun(rid){try{await post(`/api/runs/${rid}/cancel`);toast('已请求停止')}catch(e){toast(e.message)}}
async function recheck(rid){try{await post(`/api/runs/${rid}/recheck`,{});await showRun(rid)}catch(e){toast(e.message,5000)}}
async function decide(rid,d){try{await post(`/api/runs/${rid}/decide`,{decision:d});toast(d==='accept'?'已采纳到独立分支':'已放弃');await showRun(rid)}catch(e){toast(e.message,5000)}}
function runList(rs){if(!rs.length)return '<div class="sub">还没有运行过</div>';return rs.map(r=>`<div class="flowrow"><a class="fx" href="javascript:void 0" onclick="showRun(${r.id})">#${r.id} ${h(r.agent)}${mTag(r)} · ${moLabel(r.mode)}</a><span class="sub">${{queued:'排队',running:'运行中',done:'完成',failed:'失败',cancelled:'已取消'}[r.status]} · ${ago(r.created)}</span></div>`).join('')}

// ---------- business map & kb
// ---------- shared page header
const KST={'已确认':'ok','待确认':'warn','需更新':'bad','过期':'bad','未分析':'mute','仅事实':'mute'};
const kst=s=>`<span class="ev-tag ${KST[s]||'mute'}">${h(s==='过期'?'需更新':s||'-')}</span>`;
const KKIND={index:'系统总览',dom:'业务域',flow:'业务流',tbl:'业务对象',mod:'模块'};
function pageHead(title,sub,right){const p=S.projects.find(x=>x.key===S.proj)||{};
  return `<div class="ph"><div class="grow"><div class="eyebrow">${h(S.proj)} / ${h(p.name||'')}</div><h1>${h(title)}</h1><div class="sub">${h(sub)}</div></div>${right||''}</div>`}

// ---------- 运维成效: what the team got done, across all projects, for the people who manage it
async function vLead(){
  const days=+(ls.get('tmh.leadDays')||30);const d=await get('/api/lead?days='+days),k=d.kpi,a=d.agent;
  const fmt=(v,u)=>v==null?'—':u==='h'?dur(v):u==='%'?v+'%':v+' '+u;
  const tile=c=>{const dv=c.value!=null&&c.prev!=null?c.value-c.prev:null,better=dv==null||dv===0?null:(dv<0)===c.lower_better;
    const arrow=dv==null?'<span class="sub">上期无数据</span>':dv===0?'<span class="sub">与上期持平</span>':`<span class="${better?'up':'down'}">${dv>0?'↑':'↓'} ${fmt(Math.abs(Math.round(dv*10)/10),c.unit)}</span> <span class="sub">对比上期 ${fmt(c.prev,c.unit)}</span>`;
    return `<div class="card kpi core"><div class="l">${c.label}</div><div class="n">${fmt(c.value,c.unit)}</div><div class="chg">${arrow}</div></div>`};
  const HINT={resp:'报单到第一次有人回应',res:'报单到闭环',ftf:'验收一次通过、没被退回',backlog:'超过 3 天还没闭环'};
  const right=`<div class="seg" id="ldD">${[7,30,90].map(x=>`<button data-d="${x}" class="${x===days?'on':''}">近 ${x} 天</button>`).join('')}</div>`;
  const W=d.weeks,mx=Math.max(1,...W.map(w=>Math.max(w.created,w.closed))),bw=600/W.length;
  const trend=`<svg viewBox="0 0 600 160" class="trend" role="img" aria-label="每周新建与闭环">${W.map((w,i)=>{const X=i*bw+bw/2,a1=w.created/mx*110,a2=w.closed/mx*110,bwid=Math.min(26,bw/3);
    return `<rect x="${X-bwid-2}" y="${130-a1}" width="${bwid}" height="${a1}" rx="2" fill="var(--acc2)"><title>${w.from} 起一周新建 ${w.created}</title></rect><rect x="${X+2}" y="${130-a2}" width="${bwid}" height="${a2}" rx="2" fill="var(--ok)"><title>${w.from} 起一周闭环 ${w.closed}</title></rect>
    <text x="${X-bwid/2-2}" y="${124-a1}" text-anchor="middle" class="tv">${w.created||''}</text><text x="${X+bwid/2+2}" y="${124-a2}" text-anchor="middle" class="tv">${w.closed||''}</text>
    <text x="${X}" y="150" text-anchor="middle" class="tl">${w.from.slice(5).replace('-','/')}</text>`}).join('')}</svg>
    <div class="legend"><span><i style="background:var(--acc2)"></i>新建</span><span><i style="background:var(--ok)"></i>闭环</span><span>每组是一周，从标注的日期起</span></div>`;
  const pm=Math.max(1,...d.people.map(p=>p.tickets));
  const people=d.people.length?`<div class="tw"><table class="t"><tr><th>人员</th><th style="width:30%">经手工单</th><th class="num">解决</th><th class="num">平均解决时长</th><th class="num">被退回</th><th class="num">知识页</th></tr>${d.people.map(p=>`<tr><td><b>${h(p.name)}</b></td><td><div class="lbar"><i style="width:${p.tickets/pm*100}%"></i><span>${p.tickets}</span></div></td><td class="num">${p.closed}</td><td class="num">${dur(p.avg_h)}</td><td class="num">${p.rejected?`<span style="color:var(--bad)">${p.rejected}</span>`:0}</td><td class="num">${p.kb}</td></tr>`).join('')}</table></div>`:'<div class="sub">这段时间还没有人处理过工单</div>';
  const proj=`<div class="tw"><table class="t"><tr><th>项目</th><th class="num">新建</th><th class="num">闭环</th><th class="num">在途</th><th class="num">周期中位</th><th class="num">AI 参与</th><th class="num">知识页 已写/已确认</th><th class="num">消耗点数</th></tr>${d.by_project.map(p=>`<tr><td><b>${h(p.key)}</b> <span class="sub">${h(p.name)}</span></td><td class="num">${p.created}</td><td class="num">${p.closed}</td><td class="num">${p.open}</td><td class="num">${dur(p.cycle.median_h)}</td><td class="num">${p.ai}</td><td class="num">${p.kb_written.toLocaleString()} / ${p.kb_confirmed.toLocaleString()}</td><td class="num">${p.spent.toLocaleString()}</td></tr>`).join('')}</table></div>`;
  const ai=`<div class="facts">${d.ai.map(x=>`<div class="fact"><span class="grow">${x.label}</span>${x.value==null?'<span class="ev-tag mute">未启用</span>':`<b>${x.value}</b> <span class="sub">${x.unit}</span>`}</div>`).join('')}</div>`;
  const done=d.done.length?d.done.map(t=>`<a class="drow done" href="#/t/${h(t.key)}"><span class="grow"><b>${h(t.key)}</b> ${h(t.title)}
     <span class="sub">${t.reporter?h(t.reporter)+' 报单 · ':''}${t.cause?'根因：'+h(t.cause)+' · ':''}${t.by?h(t.by)+' 解决 · ':''}用时 ${dur(t.cycle_h)}${t.rejected?' · 退回过 '+t.rejected+' 次':''}</span></span><small class="sub">${h(t.closed.slice(5,10))}</small></a>`).join(''):'<div class="sub">这段时间还没有闭环的工单</div>';
  const lst=(xs,f)=>xs.length?xs.map(f).join(''):'<div class="sub">没有</div>';
  $('#main').innerHTML=`<div class="ph"><div class="grow"><div class="eyebrow">全部 ${d.projects} 个项目 · ${d.kpi.people} 人参与</div><h1>运维成效</h1><div class="sub">近 ${d.days} 天（${h(d.since)} 起），和上一个 ${d.days} 天比。全部来自工单动态和运行记录，没有估算。</div></div>${right}</div>
  <div class="grid4" style="margin-bottom:16px">${d.core.map(c=>tile(c).replace('</div><div class="chg">',`<div class="sub">${HINT[c.key]}</div></div><div class="chg">`)).join('')}</div>
  <div class="grid2"><div style="display:flex;flex-direction:column;gap:16px;min-width:0">
   <div class="card"><h2>本期做成了什么 <span class="sub" style="font-weight:400">闭环 ${d.kpi.closed} 张</span></h2>${done}</div>
   <div class="card"><h2>团队</h2>${people}</div></div>
   <div style="display:flex;flex-direction:column;gap:16px;min-width:0">
   <div class="card"><h2>智能体分担了什么</h2>${ai}</div>
   <div class="card"><h2>积压：超过 3 天未闭环</h2>${lst(d.aged,t=>`<a class="drow" href="#/t/${h(t.key)}"><span class="grow"><b>${h(t.key)}</b> ${h(t.title)}<span class="sub">${h(t.assignee||'无人负责')} · 已 ${dur(t.age_h)}</span></span>${stPill(t.status)}</a>`)}</div>
   <div class="card"><h2>每周新建与闭环</h2>${trend}</div></div></div>
  <div class="card" style="margin-top:16px"><h2>各项目</h2>${proj}</div>`;
  document.querySelectorAll('#ldD button').forEach(b=>b.onclick=()=>{ls.set('tmh.leadDays',b.dataset.d);vLead()})}

// ---------- requirement conversation: split, restate on the business map, ask only what is missing, EARS criteria
const IKIND={bug:'缺陷',feature:'新功能',change:'改动',question:'咨询',data:'数据问题'};
function intakeModal(pk,text,pin){
  modal(`<h2>理清需求 · ${h(pk)}</h2><div class="sub">直接说现象或想要什么，几件事一起说也行。平台会拆开、复述理解、只问缺的，最后生成验收标准，你确认后才建单。</div>
   ${pin?`<pre class="log" style="margin-top:8px;white-space:pre-wrap">${h(pin.summary)}</pre><div class="sub">框选的位置会写进工单（第 2、3 层是推断）。</div>`:''}
   <textarea id="inT" style="min-height:110px;width:100%;margin-top:8px" placeholder="例如：请假审批通过后状态还是草稿。另外希望请假列表能导出 Excel。">${h(text||'')}</textarea>
   <div class="row" style="margin-top:8px"><button class="primary" id="inGo">开始</button></div><div id="inBox"></div>`,true);
  $('#inGo').onclick=async()=>{try{intakePaint(await post(pin?'/api/pins/'+pin.id+'/intake':'/api/projects/'+encodeURIComponent(pk)+'/intake',{text:$('#inT').value}))}catch(e){toast(e.message,5000)}}}
function inQ(q,i){return `<div style="margin-top:8px"><div>${h(q.q)}</div>${q.options.length?`<div class="chips" style="margin-top:4px">${q.options.map(o=>`<span class="chip inO" data-i="${i}" data-s="${h(q.slot)}" data-v="${h(o)}">${h(o)}</span>`).join('')}<span class="chip inO" data-i="${i}" data-s="${h(q.slot)}" data-v="不清楚">不清楚</span></div>`
   :`<input class="inA" data-i="${i}" data-s="${h(q.slot)}" placeholder="写一句就行；不知道就写“不清楚”" style="width:100%;margin-top:4px">`}</div>`}
function inSpec(s,done){const sp=s.spec,work=s.items.map((it,i)=>[it,i]).filter(([it])=>it.kind!=='question');
  return `<div class="card" style="margin-top:10px"><div class="hdr"><b class="grow">大需求规格卡</b><span class="ev-tag info">一张父单 + ${work.length} 个子单，分批上线，最后整体验收</span>${done?'':' <a href="javascript:void 0" id="inUnbig">不按大需求做</a>'}</div>
   ${(s.spec_q||[]).map(q=>inQ(q,'spec')).join('')}
   <dl class="c4" style="margin-top:8px"><dt>目标</dt><dd>${h(sp.goal)}</dd><dt>不能变</dt><dd>${h(sp.keep)}</dd><dt>不做</dt><dd>${h(sp.out)}</dd><dt>证据</dt><dd>${h(sp.evidence)}</dd></dl>
   <div style="margin-top:8px"><b style="font-size:13px">整体验收标准</b>${sp.done.map(a=>`<div style="font-size:13px;margin-top:3px"><span class="ev-tag ${a.open?'warn':'ok'}">${a.open?'待确认':done?'已确认':'写清了'}</span> ${h(a.id)} ${h(a.text)}<div class="sub">怎么验：${h(a.check)}</div></div>`).join('')}</div>
   ${done?(s.epic?`<div style="margin-top:6px">已建父单 <a href="#/t/${h(s.epic)}" onclick="closeModal()">${h(s.epic)}</a>，子单 ${(s.children||[]).map(h).join('、')}</div>`:''):
    `<div style="margin-top:10px"><b style="font-size:13px">顺序和分批</b><div class="sub">子单按顺序分批放出，一批全部验收通过再放下一批；依赖前面某件的，等它通过后从它的代码开始。</div>
     ${work.slice(1).map(([it,i],n)=>`<div class="sub" style="margin-top:4px">第 ${n+2} 件「${h(clip(it.text,24))}」在 <select class="inDep" data-i="${i}"><option value="">不依赖</option>${work.slice(0,n+1).map(([x,j],m)=>`<option value="${j}">第 ${m+1} 件之后</option>`).join('')}</select></div>`).join('')}
     <label class="sub" style="display:flex;gap:6px;align-items:center;margin-top:6px">每批 <input id="inWave" type="number" min="1" max="10" value="2" style="width:56px"> 个子单</label></div>`}</div>`}
function intakePaint(s){const B=$('#inBox');if(!B)return;$('#inT').readOnly=true;$('#inGo').hidden=true;
  clearTimeout(window._inPoll);
  if(s.state==='understanding'){B.innerHTML=`<div class="card" style="margin-top:10px"><span class="spin"></span> AI 正在读这段话：拆开每件事、对上业务地图、写验收标准。一般几十秒；读不出来就按规则理解，不用等。<div class="row" style="margin-top:8px"><button class="ghost" id="inNo">放弃</button></div></div>`;
    $('#inNo').onclick=()=>post('/api/intake/'+s.id,{action:'drop'}).then(closeModal).catch(e=>toast(e.message,5000));
    window._inPoll=setTimeout(()=>{if($('#inBox'))get('/api/intake/'+s.id).then(intakePaint).catch(()=>{})},1500);return}
  const done=s.state==='confirmed',u=s.understood||{},asks=s.asked_client||[];
  const head=`<div class="sub" style="margin-top:10px">${u.by==='智能体'?`<span class="ev-tag ok">AI 理解</span> ${h(u.agent||'')}`:`<span class="ev-tag mute">按规则理解</span>${u.why?' <span class="sub">（AI 没用上：'+h(clip(u.why,60))+'）</span>':''}`}
    ${s.title?` · 标题「${h(s.title)}」`:''}${(s.dropped||[]).length?` · 去掉了 ${s.dropped.length} 句寒暄或转述：<span title="${h(s.dropped.join(' / '))}">${h(clip(s.dropped.join(' / '),40))}</span>`:''}</div>`;
  const hasQ=s.items.some(it=>(it.questions||[]).some(q=>q.slot!=='flow'));
  B.innerHTML=head+s.items.map((it,i)=>`<div class="card" style="margin-top:10px"><div class="hdr"><b class="grow">第 ${i+1} 件：${h(clip(it.title||it.text,40))}</b>
     <select data-i="${i}" class="inK" ${done?'disabled':''}>${Object.entries(IKIND).map(([k,l])=>`<option value="${k}" ${k===it.kind?'selected':''}>${l}</option>`).join('')}</select></div>
     <div class="sub" style="margin-top:4px">客户原话：${h(clip(it.text,120))}</div>
     <div style="margin-top:4px">${h(it.restated?(it.restated.startsWith('我理解的是')?it.restated:'我理解的是：'+it.restated):'我理解的是：'+it.text)}${it.flow?` <span class="ev-tag info">${h(it.flow.name)}</span>`:it.new_module?' <span class="ev-tag warn">新模块</span>':''}</div>
     ${it.kind==='question'?`<div class="sub" style="white-space:pre-wrap;margin-top:6px">${h(it.answer||'')}</div><div class="sub">咨询直接答复，不建单。</div>`:`
     ${(it.questions||[]).map(q=>inQ(q,i)).join('')}
     <div style="margin-top:10px"><b style="font-size:13px">验收标准（客户确认后就是合同）</b>${(it.ac||[]).map(a=>`<div style="font-size:13px;margin-top:3px"><span class="ev-tag ${a.open?'warn':'ok'}">${a.open?'待确认':done?'已确认':'写清了'}</span> ${h(a.id)} ${h(a.text)}<div class="sub">怎么验：${h(a.check)}</div></div>`).join('')}</div>
     ${it.ticket?`<div style="margin-top:6px">已建单 <a href="#/t/${h(it.ticket)}" onclick="closeModal()">${h(it.ticket)}</a></div>`:done||s.big?'':`<label class="sub" style="display:flex;gap:6px;align-items:center;margin-top:8px"><input type="checkbox" class="inHand" data-i="${i}"> 这件我来写（自动处理不接，开工包给我）</label>`}`}</div>`).join('')+
   (s.big?inSpec(s,done):s.suggest_big&&!done?`<div class="sub" style="margin-top:10px">这几件如果是一个整体、要一起验收：<button class="ghost" id="inBig">作为大需求</button> 写一张规格卡，拆成子单分批上线，最后整体验收。</div>`:'')+
   (hasQ&&s.state!=='dropped'?`<div class="card" style="margin-top:10px"><div class="hdr"><b class="grow">问题让客户自己答</b>${asks.length?`<span class="sub">已发过 ${asks.length} 次</span>`:''}</div><div class="sub">生成一个链接发给客户（微信、短信都行），客户用大白话回答；答复会写回验收标准${done?'，等着的工单自动开工':''}。</div><div class="row" style="margin-top:6px"><button class="ghost" id="inAsk">把问题发给客户</button></div><div id="inAskOut"></div></div>`:'')+
   (done?'':`<div class="row" style="gap:8px;margin-top:10px">${s.state==='asking'?'<button class="primary" id="inAns">提交回答</button>':''}
     <button class="${s.state==='asking'?'ghost':'primary'}" id="inOk">${s.state==='asking'?'先这样建单（没答的记为待确认）':s.big?'确认规格卡，建父单和子单':'确认，建单'}</button><button class="ghost" id="inNo">放弃</button></div>`);
  const pick={};B.querySelectorAll('.inO').forEach(c=>c.onclick=()=>{const i=c.dataset.i,sl=c.dataset.s;(pick[i]=pick[i]||{})[sl]=c.dataset.v;
    B.querySelectorAll(`.inO[data-i="${i}"][data-s="${sl}"]`).forEach(x=>x.classList.toggle('on',x===c))});
  const gather=()=>{const a=JSON.parse(JSON.stringify(pick));B.querySelectorAll('.inA').forEach(x=>{if(x.value.trim())(a[x.dataset.i]=a[x.dataset.i]||{})[x.dataset.s]=x.value.trim()});
    B.querySelectorAll('.inK').forEach(x=>{const it=s.items[x.dataset.i];if(x.value!==it.kind)(a[x.dataset.i]=a[x.dataset.i]||{}).kind=x.value});return a};
  const act=b=>post('/api/intake/'+s.id,b).then(intakePaint).catch(e=>toast(e.message,5000));
  B.querySelectorAll('.inK').forEach(x=>x.onchange=()=>act({action:'answer',answers:gather()}));
  if($('#inAns'))$('#inAns').onclick=()=>act({action:'answer',answers:gather()});
  if($('#inAsk'))$('#inAsk').onclick=async()=>{try{const r=await post('/api/intake/'+s.id,{action:'ask_client'});const url=location.origin+r.path;
    $('#inAskOut').innerHTML=`<div style="margin-top:8px"><input class="full" readonly value="${h(url)}" onclick="this.select()"><div class="sub">${r.questions} 个问题，${h(r.expires.slice(5,16))} 前有效${r.told_chat?'；已同时发到群里':''}。</div></div>`;
    try{await navigator.clipboard.writeText(url);toast('链接已复制，发给客户就行',4000)}catch(e){}}catch(e){toast(e.message,5000)}};
  if($('#inOk'))$('#inOk').onclick=async()=>{const a=gather();try{if(Object.keys(a).length){const r=await post('/api/intake/'+s.id,{action:'answer',answers:a});if(r.state==='understanding'){intakePaint(r);return toast('AI 正在按回答重写验收标准，写好再确认',4000)}}
    const b={action:'confirm',hand:[...B.querySelectorAll('.inHand')].filter(x=>x.checked).map(x=>+x.dataset.i)};if(s.big){b.deps={};B.querySelectorAll('.inDep').forEach(x=>{if(x.value!=='')b.deps[x.dataset.i]=[+x.value]});b.wave=+($('#inWave')||{}).value||2}
    const r=await post('/api/intake/'+s.id,b);intakePaint(r);toast(r.epic?'已建大需求 '+r.epic+'，第一批子单开工':'已建单 '+r.tickets.join('、'),5000)}catch(e){toast(e.message,5000)}};
  if($('#inBig'))$('#inBig').onclick=()=>act({action:'big',on:true});
  if($('#inUnbig'))$('#inUnbig').onclick=()=>act({action:'big',on:false});
  if($('#inNo'))$('#inNo').onclick=()=>act({action:'drop'}).then(closeModal)}

// ---------- the change itself, running: a link the person and the client open before accepting
const PVL={up:['ok','可以打开'],starting:['info','启动中'],failed:['bad','没起来']};
async function pvLoad(key){const el=$('#pvc');if(!el)return;let d;try{d=await get('/api/tickets/'+key+'/preview')}catch(e){return}
  if(!$('#pvc')||curView()!=='t')return;const st=d.preview||{},s=st.state,lb=PVL[s];
  if(!d.branch&&!s){el.hidden=true;return}
  el.hidden=false;
  el.innerHTML=`<div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">预览版本</h2>${lb?`<span class="ev-tag ${lb[0]}">${lb[1]}</span>`:''}</div>
   ${s==='up'?`<div class="sub">这次改动（提交 <code>${h(st.commit)}</code>）正跑在平台上，验收前先亲手试一遍。发出去的签收链接里也有这个入口。${d.own_address?'':'<br>它在浏览器的隔离环境里运行，碰不到平台。直接出页面的程序可以正常用；页面打开后再用脚本取数据的（单页应用）在这里取不到数据，要给预览配一个独立端口。'}</div>
     <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap"><a class="btn primary" href="${h(d.url)}" target="_blank" rel="noopener">打开预览 ↗</a><button class="ghost" id="pvStop">停掉</button><button class="ghost" id="pvGo">重新启动</button></div>`
   :s==='starting'?`<div class="sub"><span class="spin"></span> 正在用 <code>${h(clip(st.cmd||'',80))}</code> 启动 ${h(st.branch||'')}，起来后这里会出现打开按钮。</div><div class="row" style="margin-top:8px"><button class="ghost" id="pvStop">停掉</button></div>`
   :s==='failed'?`<div class="bad" style="font-size:13px">${h(st.why||'')}</div>${st.tail?`<details style="margin-top:6px"><summary class="sub">启动日志最后几行</summary><pre class="log" style="max-height:200px;overflow:auto;font-size:12px;white-space:pre-wrap">${h(st.tail)}</pre></details>`:''}<div class="row" style="gap:6px;margin-top:8px"><button class="primary" id="pvGo">再启动一次</button><button class="ghost" id="pvCfg">改启动命令</button></div>`
   :d.cmd?`<div class="sub">还没启动。会用 <code>${h(clip(d.cmd,80))}</code>${d.configured?'':'（按项目结构猜的）'}把这次改动跑起来。</div><div class="row" style="gap:6px;margin-top:8px"><button class="primary" id="pvGo">启动预览</button><button class="ghost" id="pvCfg">改启动命令</button></div>`
   :`<div class="sub">填一条能把这个项目跑起来的命令，以后每次自动改完都会起一个预览，客户在签收页就能点开试。用 <code>{port}</code> 表示端口，<code>{prefix}</code> 表示它挂在哪个路径下（程序要能挂在这个路径下运行，页面里的链接才不会断），只监听 127.0.0.1。</div><div class="row" style="margin-top:8px"><button class="primary" id="pvCfg">填启动命令</button></div>`}
   <div id="pvF"></div>`;
  const act=a=>post('/api/tickets/'+key+'/preview',{action:a}).then(()=>pvLoad(key)).catch(e=>toast(e.message,6000));
  if($('#pvGo'))$('#pvGo').onclick=()=>act('start');
  if($('#pvStop'))$('#pvStop').onclick=()=>act('stop');
  if($('#pvCfg'))$('#pvCfg').onclick=async()=>{const pk=key.split('-')[0];let c={};try{c=await get('/api/projects/'+pk+'/preview-conf')}catch(e){}
    $('#pvF').innerHTML=`<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px"><input id="pvCmd" value="${h(c.cmd||c.detected||'')}" placeholder="例如 python3 -m http.server {port} 或 mvn spring-boot:run -Dserver.port={port}">
      <input id="pvReady" value="${h(c.ready||'/')}" placeholder="起来后能打开的路径，默认 /"><div class="row" style="gap:6px"><button class="primary" id="pvSave">保存</button><span class="sub">留空保存就回到按项目结构猜</span></div></div>`;
    $('#pvSave').onclick=async()=>{try{await post('/api/projects/'+pk+'/preview-conf',{cmd:$('#pvCmd').value,ready:$('#pvReady').value});toast('已保存启动命令');pvLoad(key)}catch(e){toast(e.message,6000)}}};
  if(s==='starting')setTimeout(()=>{if($('#pvc')&&location.hash.includes(key))pvLoad(key)},4000)}

// ---------- 我来写: a person writes it (by hand or with their own tools); the platform checks it like any change
async function hwLoad(d){const el=$('#hwc'),t=d.ticket;if(!el||t.status==='closed')return;let w;try{w=await get('/api/tickets/'+t.key+'/starter')}catch(e){return}
  if(!$('#hwc'))return;const pk=t.key.split('-')[0];el.hidden=false;
  const mine=(t.links||{}).hold;
  el.innerHTML=`<div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">我来写</h2>${mine?`<span class="ev-tag info">${h(mine)} 在写</span>`:'<button class="primary" id="hwClaim">认领：我来写</button>'}</div>
   <div class="sub">自己写，或者用自己的 AI 工具写。${w.remote?`推到分支 <code>${h(w.branch)}</code>，平台${w.heartbeat==='auto'?'一分钟内':'点“现在检查”后'}会自己发现`:'把补丁传上来，平台会'}，构建测试、换一个模型对照验收标准审查，通过就转给验收人。</div>
   <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap"><button class="primary" id="hwPack">下载开工包</button>
    ${w.remote?'<button class="ghost" id="hwScan">现在检查</button>':`<a class="btn ghost" href="/p/${h(pk)}/code.bundle" download>下载代码</a><label class="btn ghost" style="cursor:pointer">上传补丁<input type="file" id="hwPatch" accept=".patch,.diff,.txt" hidden></label>`}</div>`;
  if($('#hwClaim'))$('#hwClaim').onclick=()=>post('/api/tickets/'+t.key+'/claim',{}).then(()=>{toast('已认领：自动处理不会再接这张单，下载开工包开始写');vTicket(t.key)}).catch(e=>toast(e.message,6000));
  $('#hwPack').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([w.markdown],{type:'text/markdown'}));a.download=t.key+'-开工包.md';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)};
  if($('#hwScan'))$('#hwScan').onclick=()=>post('/api/projects/'+pk+'/scan',{}).then(r=>{toast(r.taken.length?'发现新提交，开始检查':'分支 '+w.branch+' 上没有新提交',5000);if(r.taken.length)vTicket(t.key)}).catch(e=>toast(e.message,6000));
  if($('#hwPatch'))$('#hwPatch').onchange=async e=>{const f=e.target.files[0];if(!f)return;if(f.size>4*1024*1024)return toast('补丁不能超过 4MB');
    try{await post('/api/tickets/'+t.key+'/handwork',{patch:await f.text()});toast('收到补丁，开始构建和审查',5000);vTicket(t.key)}catch(err){toast(err.message,6000)}}}

// ---------- evidence package on a ticket, the ledger on the report
const PKC={none:'mute',incomplete:'warn',ready:'info',signed:'ok',rejected:'bad',upstream_merged:'ok',upstream_closed:'bad'};
const GTC={pass:'ok',fail:'bad',unknown:'warn'},GTL={pass:'通过',fail:'没过',unknown:'未知'};
function pkgSummary(d){const k=d.package||{};if(!k.status)return '';
  const dec=k.decision,ln=k.link;
  return `<div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">证据包</h2><span class="ev-tag ${PKC[k.status]}">${h(k.label)}</span></div>
   ${k.status==='none'?'<div class="sub">工单转到“待验证”时自动打包：验收标准、方案、改动、构建测试、范围和业务流检查。</div>':`
   ${k.intact?`<div class="sub">${k.records} 条记录，哈希 <code>${h(k.hash.slice(0,12))}</code>，追加式，改任何一条都会对不上。</div>`:`<div class="bad">证据包被改动过：${h(k.problem)}</div>`}
   ${k.missing.length?`<div style="margin-top:6px"><b style="font-size:13px">还缺</b> ${k.missing.map(x=>`<span class="ev-tag warn">${h(x)}</span>`).join(' ')}</div>`:'<div class="ok" style="margin-top:6px">证据齐全</div>'}
   ${k.gates?`<div style="margin-top:8px"><b style="font-size:13px">验证门</b> <span class="sub">从便宜到贵，每道给出通过、没过或未知</span>
     <div style="display:flex;flex-direction:column;gap:3px;margin-top:4px">${k.gates.map(g=>`<div style="font-size:13px"><span class="ev-tag ${GTC[g.state]}">${GTL[g.state]}</span> ${h(g.name)}<span class="sub"> ${h(clip(g.why,90))}${g.waived?` · ${h(g.waived.by)} 放行：${h(clip(g.waived.reason,40))}`:''}</span></div>`).join('')}</div></div>`:''}
   ${k.review?`<div class="sub" style="margin-top:4px">乙方复核：${h(k.review.by)} · ${h((k.review.ts||'').slice(5,16))}</div>`:''}
   ${dec?`<div style="margin-top:6px">${dec.kind==='sign'?'签收':'退回'}：<b>${h(dec.signer)}</b>${dec.role?'（'+h(dec.role)+'）':''} · ${h(dec.ts.slice(5,16))} · ${h(dec.via)}${dec.note?`<div class="sub">${h(dec.note)}</div>`:''}</div>`
     :ln?`<div class="sub" style="margin-top:4px">已发签收链接给 ${h(ln.signer)}，有效至 ${h(ln.expires.slice(5,16))}</div>`:''}`}`}
function pkgActions(d){const t=d.ticket;if(!d.package?.status||d.package.status==='none')return '';
  return `<div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap"><a class="btn" href="/e/${h(t.key)}" target="_blank" rel="noopener">打开证据包</a><a class="btn ghost" href="/e/${h(t.key)}.intoto.json" download title="in-toto 格式，甲方可以离线核对">下载</a>
    <button class="ghost" id="pkShot">补截图</button><button class="ghost" id="pkRev">复核</button>${t.status==='verify'?'<button class="primary" id="pkLink">发签收链接</button>':''}</div>`;}
function pkgCard(d){if(!d.package?.status)return '';
  return `<div class="card" id="pkg"><div id="pkSummary">${pkgSummary(d)}</div><div id="pkActions">${pkgActions(d)}</div><p class="sub" id="pkDraftNotice" hidden>证据状态已更新；表单草稿与所选文件已保留，请按最新验证门核对后提交。</p><div id="pkForm"></div></div>`;}
function pkgWire(d){const key=d.ticket.key,F=$('#pkForm');if(!F)return;
  const P=b=>post('/api/tickets/'+key+'/evidence',b);
  const acs=(()=>{const r=d.runs.find(x=>x.mode==='plan'&&x.status==='done');const m=r&&/```tmh-plan\s*([\s\S]*?)```/.exec(r.result||'');try{return m?(JSON.parse(m[1]).ac||[]):[]}catch(e){return []}})();
  if($('#pkShot'))$('#pkShot').onclick=()=>{F.innerHTML=`<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px"><select id="pkAc"><option value="">整单</option>${acs.map(a=>`<option value="${h(a.id)}">${h(a.id)} ${h(clip(a.text,30))}</option>`).join('')}</select>
     <input type="file" id="pkImg" accept="image/png,image/jpeg,image/webp"><input id="pkNote" placeholder="说明：在哪个页面做了什么、看到了什么"><button class="primary" id="pkGo">加到证据包</button></div>`;
    $('#pkGo').onclick=async()=>{const f=$('#pkImg').files[0];let image='';
      if(f){if(f.size>3*1024*1024)return toast('截图不能超过 3MB');image=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(f)})}
      try{await P({kind:'attach',ac:$('#pkAc').value,note:$('#pkNote').value,image});toast('已加到证据包');vTicket(key)}catch(e){toast(e.message,5000)}}};
  if($('#pkRev'))$('#pkRev').onclick=()=>{const k=d.package||{},m=k.missing||[];
    const open=(k.gates||[]).filter(g=>g.state!=='pass'&&!(g.state==='fail'&&(g.id==='build'||g.id==='test')));
    const exception=open.length||(!k.gates&&(m.includes('改动没超出方案')||m.includes('改动落在本单的业务流上')));
    if(!exception){const b=$('#pkRev');b.disabled=true;
      return P({kind:'review',note:''}).then(()=>{toast('已记录复核');vTicket(key)}).catch(e=>{b.disabled=false;toast(e.message,5000)})}
    F.innerHTML=`<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px"><div class="sub">有需要确认的例外；只需为要放行的项目写明理由。</div><details><summary>${!k.gates?'复核意见（认可范围例外时必填）':'补充复核意见（可选）'}</summary><textarea id="pkRn" placeholder="看了什么、为什么认可这项例外" style="min-height:56px"></textarea></details>
     ${!k.gates&&m.includes('改动没超出方案')?'<label class="sub"><input type="checkbox" id="pkSc" style="width:auto"> 超出方案的改动我看过，认可（要写理由）</label>':''}
     ${!k.gates&&m.includes('改动落在本单的业务流上')?'<label class="sub"><input type="checkbox" id="pkPa" style="width:auto"> 不在业务流上的改动我看过，认可（要写理由）</label>':''}
     ${open.length?`<div class="sub">要放行没通过的验证门，逐条写理由（不写就不放行；构建、测试没过只能改代码）：</div>${open.map(g=>`<input class="pkW" data-g="${h(g.id)}" placeholder="放行“${h(g.name)}”的理由">`).join('')}`:''}
     <button class="primary" id="pkRgo">记录复核</button></div>`;
    $('#pkRgo').onclick=async()=>{const waive={};document.querySelectorAll('.pkW').forEach(x=>{if(x.value.trim())waive[x.dataset.g]=x.value.trim()});
      try{await P({kind:'review',note:$('#pkRn').value,waive,scope_ok:!!($('#pkSc')&&$('#pkSc').checked),path_ok:!!($('#pkPa')&&$('#pkPa').checked)});toast('已记录复核');vTicket(key)}catch(e){toast(e.message,5000)}}};
  if($('#pkLink'))$('#pkLink').onclick=()=>{const m=(d.package||{}).missing||[];F.innerHTML=`<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px"><input id="pkS" placeholder="签收人姓名（甲方业务确认人）"><input id="pkR" placeholder="角色，如 人事业务负责人">
     ${m.length?`<textarea id="pkN" placeholder="证据还缺 ${h(m.join('、'))}，写明为什么现在就请甲方签" style="min-height:48px"></textarea>`:''}<button class="primary" id="pkLgo">生成链接</button><div id="pkOut"></div></div>`;
    $('#pkLgo').onclick=async()=>{try{const r=await P({kind:'link',signer:$('#pkS').value,role:$('#pkR').value,note:$('#pkN')?$('#pkN').value:''});const url=location.origin+r.path;
      $('#pkOut').innerHTML=`<div class="sub">发给 ${h(r.signer)}，${h(r.expires.slice(0,16))} 前有效，只能用一次。对方打开就能签，不用登录，页面上没有代码：</div><input id="pkU" readonly value="${h(url)}"><button id="pkCp">复制链接</button>`;
      $('#pkCp').onclick=()=>{navigator.clipboard.writeText(url).then(()=>toast('已复制')).catch(()=>{$('#pkU').select()})}}catch(e){toast(e.message,6000)}}};
}
function upCard(u){if(!u)return '';
  const f=(v,unit)=>v==null?'—':v+(unit||'');
  return `<div class="card"><h2>外部 PR <span class="ev-tag info">第三方验收</span></h2>${u.submitted?`<div class="grid2" style="gap:6px">
    <div><div class="sub">合并率</div><b>${f(u.merge_rate,'%')}</b></div><div><div class="sub">已提交 / 合并</div><b>${u.submitted} / ${u.merged}</b></div>
    <div><div class="sub">合并前评审轮次</div><b>${f(u.rounds_avg)}</b></div><div><div class="sub">提交到合并</div><b>${f(u.hours_to_merge_median,' 小时')}</b></div></div>
    <div class="sub" style="margin-top:6px">维护者合并前又加提交 ${u.maintainer_edited} 个${u.reasons.length?'；关闭原因：'+u.reasons.map(r=>h(r.label)+' '+r.n).join('、'):''}</div>
    ${u.rows.slice(0,8).map(r=>`<div class="srow"><a href="#/t/${h(r.key)}">${h(r.key)}</a><a class="grow" href="${h(r.url)}" target="_blank" rel="noopener">${h(r.repo)}#${h(r.pr)}</a><span class="ev-tag ${r.state==='merged'?'ok':r.state==='closed'?'bad':'info'}">${h(r.label)}</span></div>`).join('')}`
    :'<div class="sub">还没有提交过外部 PR。给开源老项目提真实 PR、跟踪到维护者合并，是可以公开复查的验收证据。</div>'}</div>`}
async function upWire(d){const t=d.ticket,box=$('#upc');if(!box)return;const key=t.key;
  let u;try{u=await get('/api/tickets/'+key+'/upstream')}catch(e){return}
  const up=u.upstream||{};const P=b=>post('/api/tickets/'+key+'/upstream',b);
  if(!up.repo){box.innerHTML=`<details class="card"><summary><b>外部 PR</b> <span class="sub">把这单做成给开源项目的 PR</span></summary><div style="display:flex;flex-direction:column;gap:6px;margin-top:8px"><input id="upR" placeholder="上游仓库，如 apache/ofbiz-framework"><input id="upI" placeholder="上游 issue 号（可空）"><input id="upP" placeholder="已有 PR 号（可空）"><button class="primary" id="upL">关联</button></div></details>`;
    $('#upL').onclick=()=>P({action:'link',repo:$('#upR').value,issue:$('#upI').value,pr:$('#upP').value}).then(()=>vTicket(key)).catch(e=>toast(e.message,5000));return}
  const s=u.summary||{},dr=u.draft,ap=u.approved;
  box.innerHTML=`<div class="card"><div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">外部 PR</h2><span class="ev-tag ${u.state==='merged'?'ok':u.state==='closed'?'bad':'info'}">${h(u.label)}</span></div>
   <div class="sub">${h(up.repo)}${up.issue?` · <a href="https://github.com/${h(up.repo)}/issues/${h(up.issue)}" target="_blank" rel="noopener">issue #${h(up.issue)}</a>`:''}${up.pr?` · <a href="${h(up.url)}" target="_blank" rel="noopener">PR #${h(up.pr)}</a>`:''}</div>
   ${up.pr?`<div class="sub" style="margin-top:4px">CI ${h(u.ci||'—')} · 评审 ${s.rounds??'—'} 轮${s.maintainer_commits?' · 维护者加了 '+s.maintainer_commits+' 个提交':''}${u.synced?' · 同步于 '+h(u.synced.slice(5,16)):''}</div>
     ${(u.reviews||[]).slice(-3).map(r=>`<div class="cbody sub" style="margin-top:4px"><b>${h(r.by)}</b> ${h(r.state)}：${h(clip(r.body||'',160))}</div>`).join('')}
     <div class="row" style="gap:6px;margin-top:8px"><button id="upSync">从 GitHub 同步</button>${u.state==='closed'&&!(u.outcome||{}).reason?'<button class="ghost" id="upWhy">补记关闭原因</button>':''}</div>`
   :dr?`<div style="margin-top:6px"><b>${h(dr.title)}</b><div class="sub">${h(dr.head)} → ${h(dr.base)}</div><div class="cbox">${md(dr.body)}</div>
     ${ap?`<div class="ok" style="margin-top:4px">${h(ap.by)} 已批准提交（${h(ap.at.slice(5,16))}）</div>`:'<div class="warn" style="margin-top:4px">等人过目：这是用你的账号对外发布，批准后才能提交</div>'}
     <div class="row" style="gap:6px;margin-top:8px">${ap?'<button class="primary" id="upGo">提交到 GitHub</button>':'<button class="primary" id="upOk">我看过了，批准提交</button>'}<button class="ghost" id="upEd">改草稿</button></div></div>`
   :'<div class="row" style="margin-top:8px"><button class="primary" id="upEd">起草 PR</button></div>'}</div>`;
  const edit=()=>modal(`<h2>上游 PR 草稿</h2><input class="full" id="dT" placeholder="标题（照项目的提交规范）" value="${h(dr?dr.title:t.title)}"><input class="full" id="dH" placeholder="分支，如 auntunt:fix-xxx" value="${h(dr?dr.head:'')}" style="margin-top:6px"><input class="full" id="dB" placeholder="目标分支" value="${h(dr?dr.base:'trunk')}" style="margin-top:6px"><textarea class="full" id="dD" style="min-height:200px;margin-top:6px" placeholder="描述：照项目的 PR 模板写，按项目规则写明 AI 辅助">${h(dr?dr.body:'')}</textarea><div style="margin-top:8px"><button class="primary" id="dS">保存草稿</button></div>`,true);
  if($('#upEd'))$('#upEd').onclick=()=>{edit();$('#dS').onclick=()=>P({action:'draft',title:$('#dT').value,head:$('#dH').value,base:$('#dB').value,body:$('#dD').value}).then(()=>{closeModal();vTicket(key)}).catch(e=>toast(e.message,5000))};
  if($('#upOk'))$('#upOk').onclick=()=>{const k=d.package||{},bad=(k.gates||[]).filter(g=>g.state!=='pass');
    const ask=!k.gates?'这单没有带验证门的证据包，写明为什么仍然提交':bad.some(g=>g.state==='fail')?'':bad.length?'验证门有未知：'+bad.map(g=>g.name).join('、')+'。写明为什么仍然提交':'';
    if(k.gates&&bad.some(g=>g.state==='fail'))return toast('验证门没过，不能提交上游：'+bad.filter(g=>g.state==='fail').map(g=>g.name).join('、'),6000);
    const go=note=>P({action:'approve',note}).then(()=>{toast('已批准');vTicket(key)}).catch(e=>toast(e.message,5000));
    if(!ask)return go('');
    modal(`<h2>批准提交上游 PR</h2><div class="sub">${h(ask)}</div><textarea id="upAn" style="min-height:60px;width:100%;margin-top:8px"></textarea>
      <div class="row" style="gap:8px;margin-top:8px"><button class="primary" id="upAgo">批准</button><button id="upAno">取消</button></div>`);
    $('#upAno').onclick=closeModal;$('#upAgo').onclick=()=>{const n=$('#upAn').value;closeModal();go(n)}};
  if($('#upGo'))$('#upGo').onclick=()=>P({action:'submit',confirm:true}).then(()=>{toast('已提交');vTicket(key)}).catch(e=>toast(e.message,6000));
  if($('#upSync'))$('#upSync').onclick=()=>P({action:'sync'}).then(()=>{toast('已同步');vTicket(key)}).catch(e=>toast(e.message,6000));
  if($('#upWhy'))$('#upWhy').onclick=()=>{modal(`<h2>为什么没合并</h2><select id="rW" class="full">${[['direction','方向不对'],['style','风格或规范'],['scope','范围太大'],['duplicate','重复或已修'],['stale','没人理、过期'],['policy','项目规则'],['other','其他']].map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select><textarea class="full" id="rN" placeholder="维护者原话或我们的判断" style="margin-top:6px"></textarea><div style="margin-top:8px"><button class="primary" id="rS">记下</button></div>`);
    $('#rS').onclick=()=>P({action:'reason',reason:$('#rW').value,note:$('#rN').value}).then(()=>{closeModal();vTicket(key)}).catch(e=>toast(e.message,5000))};
}
function ledgerCard(L){if(!L)return '';const T=L.totals;
  return `<div class="card"><h2>账本（每单）</h2><div class="sub" style="margin-bottom:6px">本期经手 ${T.tickets} 张，关闭 ${T.closed} 张；证据包 ${T.packed} 张，已签收 ${T.signed} 张（甲方签收链接 ${T.client_signed} 张）；返工 ${T.reworks} 次；人工动作 ${T.human_actions} 次</div>
   <div class="tw"><table class="t"><tr><th>工单</th><th>周期</th><th>返工</th><th>AI 运行</th><th>点数</th><th>标价（元）</th><th>人工动作</th><th>证据包</th></tr>
   ${L.rows.slice(0,40).map(x=>`<tr><td><a href="#/t/${h(x.key)}">${h(x.key)}</a> <span class="sub">${h(clip(x.title,16))}</span></td><td>${dur(x.cycle_h)}</td><td class="num">${x.reworks}</td><td class="num">${x.ai_runs}</td><td class="num">${x.points}</td><td class="num">${x.list_yuan==null?'—':x.list_yuan.toFixed(2)}</td><td class="num">${x.human_actions}</td>
     <td>${x.evidence_status==='none'?'<span class="sub">未生成</span>':`<a href="/e/${h(x.key)}" target="_blank" rel="noopener"><span class="ev-tag ${PKC[x.evidence_status]}">${h(x.evidence)}</span></a>`}${x.signer?' <span class="sub">'+h(x.signer)+'</span>':''}</td></tr>`).join('')||'<tr><td colspan="8" class="sub">本期还没有经手的工单</td></tr>'}</table></div>
   <div class="sub" style="margin-top:6px">${h(L.method.list_yuan)}；${h(L.method.paid_yuan)}；${h(L.method.human_actions)}。</div></div>`}
// ---------- efficiency dashboard and monthly report
function dur(x){if(x==null)return '—';if(x<1)return Math.max(1,Math.round(x*60))+' 分钟';if(x<48)return x.toFixed(1)+' 小时';return (x/24).toFixed(1)+' 天'}
function chg(c,better){if(c==null)return '';const good=better==='down'?c<0:c>0;return `<span class="ev-tag ${c===0?'mute':good?'ok':'bad'}">${c>0?'+':''}${c}%</span>`}
async function vEff(){
  const mo=S.effMonth===undefined?new Date().toISOString().slice(0,7):S.effMonth;
  const m=await get('/api/projects/'+S.proj+'/metrics?month='+mo);const cand=m.baseline,p=m.pilot,k=m.kb,G=m.gate,L=m.ledger;
  const b=G.sealed?m.sealed.stats:{n:0,cycle:{},cycle_by_type:{},systems:[]};
  const months=[];const d0=new Date();for(let i=0;i<12;i++){const x=new Date(d0.getFullYear(),d0.getMonth()-i,1);months.push(x.getFullYear()+'-'+String(x.getMonth()+1).padStart(2,'0'))}
  const kpi=(l,v,sub,extra)=>`<div class="card kpi"><div class="l">${l} <span class="ev-tag mute" style="font-size:11px;padding:0 5px">实测</span></div><div class="n">${v}</div><div class="sub">${sub}</div>${extra||''}</div>`;
  const pc=x=>x==null?'—':x+'%';
  const C=m.compare[0];
  const right=`<div class="row" style="gap:8px;align-items:center"><select id="effM"><option value="">全部时间</option>${months.map(x=>`<option value="${x}" ${x===mo?'selected':''}>${x.slice(0,4)} 年 ${+x.slice(5)} 月</option>`).join('')}</select><button id="effMd">导出报告（Markdown）</button><a class="btn" href="/p/${encodeURIComponent(S.proj)}/efficiency?month=${mo}" target="_blank" rel="noopener">打开可打印版</a></div>`;
  const srcMax=Math.max(1,...p.ai.by_source.map(x=>x.n));
  const tMax=Math.max(1,...m.trend.map(x=>x.closed));
  const trend=`<svg viewBox="0 0 600 170" class="trend" role="img" aria-label="近六个月关闭工单">${m.trend.map((x,i)=>{const bh=x.closed/tMax*100,X=20+i*96;return `<rect x="${X}" y="${118-bh}" width="56" height="${bh}" rx="3" class="tb"/><text x="${X+28}" y="${112-bh}" text-anchor="middle" class="tv">${x.closed}</text><text x="${X+28}" y="136" text-anchor="middle" class="tl">${x.month.slice(2).replace('-','/')}</text><text x="${X+28}" y="154" text-anchor="middle" class="ts">${dur(x.cycle_median_h)}</text><text x="${X+28}" y="168" text-anchor="middle" class="ts">AI ${x.ai_rate==null?'—':x.ai_rate+'%'}</text>`}).join('')}</svg>`;
  $('#main').innerHTML=pageHead('AI 提效报告',`${m.period} · 本期经手 ${p.handled} 张、关闭 ${p.closed} 张 · ${G.sealed?'封存基线 '+b.n+' 张历史工单':'基线未封存，不出对比数'}`,right)+
  `<div class="grid5" style="margin-bottom:16px">
    ${kpi('工单周期（中位数）',dur(p.cycle.median_h),G.sealed?`基线 ${dur(b.cycle.median_h)} ${chg(C.change,'down')}`:'基线未封存，不出对比',`<div class="sub">${p.cycle.n} 张验收通过</div>`)}
    ${kpi('首次定位耗时',dur(p.locate.median_h),`${p.locate.n} 张有定位结论`,'<div class="sub">基线：外部系统无记录</div>')}
    ${kpi('验收退回率',pc(p.reject.rate),`验收 ${p.reject.reviewed} 张 · 退回 ${p.reject.rejected} 张`,`<div class="sub">返工 ${p.reject.reworks} 次</div>`)}
    ${kpi('AI 参与率',pc(p.ai.rate),`${p.ai.tickets} / ${p.ai.total} 张`,`<div class="sub">含 IDE 里的 MCP 调用</div>`)}
    ${kpi('每单 AI 成本',p.cost.per_ticket==null?'—':p.cost.per_ticket+' 点',`本期共 ${p.cost.total.toLocaleString()} 点 · 标价 ${L.totals.list_yuan==null?'—':L.totals.list_yuan+' 元'}`,`<div class="sub">实付 ${L.totals.paid_yuan==null?'未录入':L.totals.paid_yuan+' 元'}</div>`)}
  </div>
  <div class="grid2"><div style="display:flex;flex-direction:column;gap:16px;min-width:0">
    <div class="card"><h2>基线与本期对比</h2><div class="tw"><table class="t"><tr><th>指标</th><th>基线</th><th>本期</th><th>变化</th></tr>${m.compare.map(c=>`<tr><td>${h(c.label)}</td><td class="sub">${h(c.baseline)}</td><td><b>${h(c.pilot)}</b></td><td>${chg(c.change,c.better)||'<span class="sub">—</span>'}</td></tr>`).join('')}</table></div>
      <div class="sub" style="margin-top:8px">${G.sealed?`封存基线：${b.n} 张从 ${h(b.systems.join('、')||'外部系统')} 导入、已在原系统关闭的工单，窗口 ${h(m.sealed.window[0])} 至 ${h(m.sealed.window[1])}；${h(m.sealed.sealed_at.slice(0,16))} 由 ${h(m.sealed.sealed_by)} 封存，哈希 <code>${h(m.sealed.hash.slice(0,16))}</code>，之后不能改。`
        :`<span class="bad">${h(G.reason)}。</span>${cand.n?`已导入 ${cand.n} 张已关闭的历史工单（${cand.range[0]} 至 ${cand.range[1]}）。选好窗口封存一次，之后口径和样本都不能改：
        <div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap"><input type="date" id="blF" value="${cand.range[0]}"><input type="date" id="blT" value="${cand.range[1]}"><input id="blN" placeholder="说明（如：试点前 6 个月）" size="16"><button class="primary" id="blSeal">封存基线</button></div>`
        :'先在<a href="#/int">外部系统</a>里导入过去 3～6 个月的 Jira 或禅道工单，已关闭的可以封存为基线。'}`}</div></div>
    <div class="card"><h2>按类型的工单周期</h2><div class="tw"><table class="t"><tr><th>类型</th><th>基线中位数</th><th>本期中位数</th><th>本期样本</th></tr>${S.meta.types.filter(([c])=>b.cycle_by_type[c]||p.cycle_by_type[c]).map(([c,l])=>{const x=b.cycle_by_type[c],y=p.cycle_by_type[c];return `<tr><td>${l}</td><td class="sub">${dur(x&&x.median_h)}${x?` · ${x.n} 张`:''}</td><td><b>${dur(y&&y.median_h)}</b></td><td>${y?y.n:0}</td></tr>`}).join('')||'<tr><td colspan="4" class="sub">还没有验收通过的工单</td></tr>'}</table></div>
      <div class="sub" style="margin-top:8px">周期从工单创建算到人工验收通过。</div></div>
    <div class="card"><h2>近六个月</h2>${trend}<div class="sub">柱子是每月验收通过的工单数，下方是周期中位数和 AI 参与率。</div></div>
  </div><div style="display:flex;flex-direction:column;gap:16px;min-width:0">
    <div class="card"><h2>AI 怎么参与的</h2>${p.ai.by_source.map(x=>`<div class="srow"><span>${h(x.label)}</span><span class="sbar"><i style="width:${x.n/srcMax*100}%"></i></span><b>${x.n}</b></div>`).join('')}
      <div class="sub" style="margin-top:6px">一张工单可能有多种参与方式。</div></div>
    <div class="card"><h2>IDE 里的使用</h2>${p.ide.calls?`<div class="sub" style="margin-bottom:6px">本期 ${p.ide.calls} 次 MCP 调用，关联 ${p.ide.tickets} 张工单，${p.ide.unlinked} 次没有工单号。</div>
      ${p.ide.clients.map(([c,n])=>`<div class="srow"><span>${h(c)}</span><span class="grow"></span><b>${n}</b></div>`).join('')}
      <div class="tags" style="margin-top:8px">${p.ide.tools.map(([t,n])=>`<span class="tag">${h(t)} ${n}</span>`).join('')}</div>`
      :'<div class="sub">本期还没有记录。开发者在 Cursor 或 Claude Code 里接上 <code>tmh mcp</code> 后，每次调用都会记在项目的 <code>.tmh/usage.jsonl</code>；先在工单的“提示词”里写入项目，调用就能对上工单。</div>'}</div>
    ${upCard(m.upstream)}
    <div class="card"><h2>知识库</h2>${k.built?`<div class="sub">业务理解页已写 ${k.written} / ${k.scope} 页，过期 ${k.stale} 页；${k.flows} 条业务流中 ${k.flows_with_tables} 条能追到表。</div>`:'<div class="sub">项目尚未构建知识库。</div>'}</div>
  </div></div><div style="margin-top:16px">${ledgerCard(L)}</div>`;
  $('#effM').onchange=e=>{S.effMonth=e.target.value;vEff()};
  if($('#blSeal'))$('#blSeal').onclick=async()=>{const f=$('#blF').value,t=$('#blT').value;
    try{const c=await get(`/api/projects/${S.proj}/baseline?from=${f}&to=${t}`);
      const note=$('#blN').value;
      modal(`<h2>封存基线</h2><p>把 ${h(f)} 至 ${h(t)} 的 <b>${c.candidate.n}</b> 张历史工单封存为基线，周期中位数 ${dur(c.candidate.cycle.median_h)}。${c.candidate.warning?'<br><span class="warn">'+h(c.candidate.warning)+'</span>':''}</p><p class="sub">封存后窗口、口径和样本清单都不能再改。</p><div class="row" style="gap:8px"><button class="primary" id="blOk">确认封存</button><button class="ghost" onclick="closeModal()">再想想</button></div>`);
      $('#blOk').onclick=async()=>{closeModal();try{await post(`/api/projects/${S.proj}/baseline/seal`,{from:f,to:t,note});toast('基线已封存');vEff()}catch(e){toast(e.message,5000)}}}catch(e){toast(e.message,5000)}};
  $('#effMd').onclick=async()=>{try{const r=await get('/api/projects/'+S.proj+'/report?month='+mo);const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([r.markdown],{type:'text/markdown;charset=utf-8'}));a.download=r.filename;document.body.appendChild(a);a.click();a.remove();toast('已导出 '+r.filename)}catch(e){toast(e.message)}}}

// ---------- knowledge base: read on the left/right; review and building have their own tabs
async function vKb(pid){
  const tab=pid?'read':(sessionStorage.getItem('tmh.kbTab')||'read');
  const tr=await get('/api/projects/'+S.proj+'/kb/tree');
  const head=pageHead('知识库','业务说明、项目规则与代码依据。',`<button onclick="kbTriage()">需求预判</button><button onclick="kbTab('build')">＋ 建设知识库</button>`);
  if(!tr.built){$('#main').innerHTML=head+`<div class="hint" style="margin:12px 0">这个项目还没有知识库。下面开始建设：先构建知识图谱，再让本机智能体写业务说明。</div><div id="svy"></div>`;return survey()}
  const c=tr.coverage.total||{},bk=tr.coverage.by_kind||{};
  const wr=k=>['待确认','已确认'].reduce((a,s)=>a+((bk[k]||{})[s]||0),0),all=k=>Object.values(bk[k]||{}).reduce((a,b)=>a+b,0);
  const todo=(c['待确认']||0),upd=(c['过期']||0);
  $('#main').innerHTML=head+`<div class="seg kbt" role="tablist"><button data-t="read" class="${tab==='read'?'on':''}">知识内容</button><button data-t="review" class="${tab==='review'?'on':''}">待确认与更新${todo+upd?` <b class="cnt">${todo+upd}</b>`:''}</button><button data-t="build" class="${tab==='build'?'on':''}">建设进度</button></div><div id="kbBody"></div>`;
  document.querySelectorAll('.kbt button').forEach(b=>b.onclick=()=>kbTab(b.dataset.t));
  S.kbTree=tr;
  if(tab==='review')return kbReview();
  if(tab==='build'){const tot=Object.keys(bk).reduce((a,k)=>a+all(k),0),done=Object.keys(bk).reduce((a,k)=>a+wr(k),0);
    const top=all('dom')+all('index'),topd=wr('dom')+wr('index');
    $('#kbBody').innerHTML=`<div class="kpis">${[[done+' / '+tot,'全项目已写页数','所有业务流、业务对象、业务域和总览'],[topd+' / '+top,'业务地图已写','业务域和系统总览'],[(c['已确认']||0)+'','人工已确认','确认人和时间记在每一页'],[upd+'','需更新','代码变了，说明可能已过时']].map(([n,l,d])=>`<div><b>${n}</b><span>${l}</span><small>${d}</small></div>`).join('')}</div>
      <div class="sub" style="margin:-6px 0 12px">口径：按知识页计；数据来自同一份知识库登记，更新于 ${h(tr.built_at)}。本批次进度见下方和“智能体运行”。</div><div id="svy"></div>`;return survey()}
  const f=JSON.parse(sessionStorage.getItem('tmh.kbf')||'{}');
  $('#kbBody').innerHTML=`<div class="kbread"><aside class="kbdir"><input id="kbq" placeholder="搜索业务或知识页" value="${h(f.q||'')}" aria-label="搜索知识">
     <label class="sub chk"><input type="checkbox" id="kbw" ${f.w?'checked':''}> 只看有业务说明的</label><div id="kbTree"></div></aside><section class="kbdoc card" id="kbDoc"></section></div>`;
  const upd2=o=>{Object.assign(f,o);sessionStorage.setItem('tmh.kbf',JSON.stringify(f));kbTreePaint(f,pid)};
  $('#kbq').oninput=e=>upd2({q:e.target.value});$('#kbw').onchange=e=>upd2({w:e.target.checked});
  kbTreePaint(f,pid);
  const first=pid||(tr.index&&tr.index.status!=='仅事实'?'index':'')||((tr.domains.find(d=>d.status!=='仅事实'&&d.status!=='未分析')||tr.domains[0]||{}).id);
  if(first)kbRead(first);else $('#kbDoc').innerHTML='<div class="sub">选左侧的业务域或业务流阅读。</div>'}
function kbTab(t){sessionStorage.setItem('tmh.kbTab',t);if(location.hash!=='#/kb')location.hash='#/kb';else vKb()}
function kbTreePaint(f,cur){
  const tr=S.kbTree;const q=(f.q||'').toLowerCase();const okS=s=>!f.w||s==='已确认'||s==='待确认'||s==='需更新';
  const m=x=>!q||(x.title+' '+x.id+' '+(x.summary||'')+' '+(x.entry||'')).toLowerCase().includes(q);
  const it=(x,cls)=>`<a class="kn ${cls||''} ${x.id===cur?'on':''} ${x.status==='仅事实'||x.status==='未分析'?'dim':''}" href="#/kb/${encodeURIComponent(x.id)}" data-id="${h(x.id)}"><span>${h(x.title)}</span><i class="dot ${KST[x.status]||'mute'}" title="${h(x.status)}"></i></a>`;
  let html='';
  if(tr.index&&okS(tr.index.status)&&m(tr.index))html+=it(tr.index,'top');
  tr.domains.forEach(d=>{const fl=d.flows.filter(x=>okS(x.status)&&(m(x)||m(d)));const show=(okS(d.status)&&m(d))||fl.length;if(!show)return;
    const open=q||cur===d.id||fl.some(x=>x.id===cur)||sessionStorage.getItem('tmh.kbo.'+d.id)==='1';
    html+=`<details class="kd" data-d="${h(d.id)}" ${open?'open':''}><summary>${h(d.title)}<small>${d.written}/${d.flows.length}</small></summary>${d.id?it(Object.assign({},d,{title:'业务域说明'}),'dom'):''}${fl.map(x=>it(x)).join('')}</details>`});
  $('#kbTree').innerHTML=html||'<div class="sub">没有匹配的内容</div>';
  document.querySelectorAll('#kbTree details').forEach(d=>d.ontoggle=()=>sessionStorage.setItem('tmh.kbo.'+d.dataset.d,d.open?'1':'0'))}
async function kbRead(pid){
  document.querySelectorAll('#kbTree .kn').forEach(a=>a.classList.toggle('on',a.dataset.id===pid));
  const el=$('#kbDoc');if(!el)return;el.innerHTML='<span class="spin"></span>';
  let p;try{p=await get(`/api/projects/${S.proj}/kb/page?id=${encodeURIComponent(pid)}`)}catch(e){el.innerHTML='<div class="sub">'+h(e.message)+'</div>';return}
  const m=p.text.match(/^---\n([\s\S]*?)\n---\n?/);const meta={};if(m)m[1].split('\n').forEach(l=>{const i=l.indexOf(':');if(i>0)meta[l.slice(0,i).trim()]=l.slice(i+1).trim()});
  let body=m?p.text.slice(m[0].length):p.text;body=body.replace(/^#\s+.*\n/,'');
  const st=p.status||'';const unwritten=st==='仅事实'||st==='未分析';
  // purpose and key flow up front; code evidence, boundaries and notes folded
  const parts=body.split(/\n(?=##\s)/);const fold=/代码|证据|依据|附注|边界|技术|实现|指纹|调用链|变更|待确认问题/;
  const main=[],side=[];parts.forEach(x=>{const hd=(x.match(/^##\s+(.*)/)||[])[1]||'';(hd&&fold.test(hd)?side:main).push(x)});
  const dom=(S.kbTree.domains.find(d=>d.id===pid||d.flows.some(f=>f.id===pid))||{});
  el.innerHTML=`<div class="crumb">${h(KKIND[p.kind]||'知识页')}${dom.title&&dom.id!==pid?' / '+h(dom.title):''}</div>
   <div class="row" style="align-items:flex-start;gap:10px"><h1 class="grow" style="margin:4px 0 6px">${h(meta.title||pid)}</h1>${kst(st)}</div>
   <div class="note">${unwritten?'这页还没有业务说明，下面只有工具从代码解析出的事实。':'状态针对业务说明；代码事实来自工具解析。'}${p.confirmed_by?` 已由 ${h(p.confirmed_by)} 确认${p.confirmed_at?'（'+h(p.confirmed_at)+'）':''}${p.confirm_note?'：'+h(p.confirm_note):''}。`:''} <span class="key">${h(pid)}</span></div>
   ${meta.summary&&!unwritten?`<p class="lead">${h(meta.summary)}</p>`:''}
   <div class="kbmd">${md(main.join('\n'))}</div>
   ${side.length?`<details class="fold"><summary>展开代码依据与边界</summary>${md(side.join('\n'))}<div class="sub" style="margin-top:6px">${h(p.path)}</div></details>`:''}
   ${pid.startsWith('flow:')?`<button class="ghost" onclick="showFlow('${h(pid)}')">查看调用链与读写的表 →</button>`:''}
   <div class="row acts2"><button onclick="kbAsk('${h(pid)}','${h(meta.title||pid)}')">在助手中追问</button>
    ${st==='待确认'||st==='需更新'?`<button class="primary" id="kc">确认这份说明</button>`:''}
    <span class="grow"></span><select id="kag" aria-label="智能体">${agentOptions()}</select><span id="kmw"></span><button id="kw">${unwritten?'让智能体撰写':'让智能体修订'}</button></div>`;
  if($('#kc'))$('#kc').onclick=()=>prompt2('确认这份说明（可写一句备注）','',async v=>{try{await post(`/api/projects/${S.proj}/kb/confirm`,{id:pid,note:v});toast('已确认，记录了确认人和时间');S.kbTree=await get('/api/projects/'+S.proj+'/kb/tree');kbTreePaint(JSON.parse(sessionStorage.getItem('tmh.kbf')||'{}'),pid);kbRead(pid)}catch(e){toast(e.message)}});
  $('#kw').onclick=async()=>{const pr=(S.points&&S.points.prices&&S.points.prices.kb)||0;
    modal(`<h2>${unwritten?'撰写':'修订'}知识页</h2><p>让 ${h($('#kag').selectedOptions[0].text)} 阅读这页涉及的代码，${unwritten?'写出':'修订'}「${h(meta.title||pid)}」的业务说明。只改知识库里的这一页，写完是“待确认”，由人确认。</p><p class="sub">预计消耗 ${pr} 点；过程在“智能体运行”里能看到。</p><div class="row"><button class="primary" id="kwOk">确认执行</button><button onclick="closeModal()">取消</button></div>`);
    const ag=$('#kag').value,mdl=$('#kmd').value;$('#kwOk').onclick=async()=>{closeModal();try{const r=await post(`/api/projects/${S.proj}/runs`,{agent:ag,mode:'kb',target:pid,model:mdl});showRun(r.id)}catch(e){toast(e.message)}}}
  const pk=()=>{$('#kmw').innerHTML=modelSel('kmd',$('#kag').value,'kb');bindModel('kmd')};pk();$('#kag').onchange=pk}
function kbAsk(pid,title){A.toggle(true);const t=$('#aq');t.value=`「${title}」（${pid}）`;t.focus()}
// business questions: people answer in their own words; the answer is written into the page as is and the page is queued for revision
function kbAnswer(n,q){modal(`<h2>记录业务方答复 #${n}</h2><p>${h(q)}</p><textarea class="full" id="ansT" rows="5" placeholder="业务方的原话，照录，不要改写"></textarea>
  <input class="full" id="ansB" placeholder="答复人（默认是你）" style="margin-top:8px"><div class="sub" style="margin:6px 0">原话会写进问题清单和相关知识页的“业务方答复”，页面排进修订队列；智能体修订后仍由人确认。</div>
  <div class="row"><button class="primary" id="ansOk">保存答复</button><button onclick="closeModal()">取消</button></div>`);
  $('#ansOk').onclick=async()=>{const text=$('#ansT').value.trim();if(!text)return toast('答复不能为空');try{const r=await post(`/api/projects/${S.proj}/kb/answer`,{n,text,by:$('#ansB').value.trim()});closeModal();toast(r.pages.length?'已写入 '+r.pages.length+' 个知识页，等待修订':'已记录');kbReview()}catch(e){toast(e.message)}}}
function kbTriage(){modal(`<h2>需求预判</h2><div class="sub" style="margin-bottom:6px">按知识库原文判断能不能做、把握多大、依据哪些页面、要问业务方什么。涉及资金/审批/口径、依据未经确认或有未答问题时，一律交人判断。</div>
  <textarea class="full" id="trQ" rows="4" placeholder="业务方的原话，例如：资金计划能不能按部门导出执行分析？"></textarea>
  <div class="row" style="margin-top:8px"><button class="primary" id="trGo">预判</button><span class="grow"></span></div><div id="trOut"></div>`,true);
  $('#trGo').onclick=async()=>{const q=$('#trQ').value.trim();if(!q)return;$('#trOut').innerHTML='<span class="spin"></span>';
    try{const r=await post(`/api/projects/${S.proj}/kb/triage`,{request:q});const lk=id=>`<a href="#/kb/${encodeURIComponent(id)}" onclick="closeModal()">${h(id)}</a> <small class="sub">${h(r.status[id]||'')}</small>`;
      const grp=[r.chain.domains,r.chain.flows,r.chain.tables].filter(x=>x.length).map(x=>x.map(lk).join('、')).join(' → ');
      $('#trOut').innerHTML=`<div class="card" style="margin-top:10px"><h2>${h(r.verdict)} <small class="sub">预判 ${h(r.id)} · 把握：${h(r.confidence)}${r.model?' · 转发模型 '+h(r.model)+(r.draft_verdict?' 初判“'+h(r.draft_verdict)+'”':''):''}</small></h2>
        ${r.answer?`<p><b>${r.verdict==='需要人判断'?'答复草稿（核对后再发）':'答复'}：</b>${h(r.answer)}</p>`:''}<p class="sub">依据：${grp||'无'}</p>
        ${r.reasons.length?`<ul>${r.reasons.map(x=>`<li>${h(x)}</li>`).join('')}</ul>`:''}
        ${r.open_questions.length?`<p><b>已有未答复问题：</b></p><ul>${r.open_questions.map(x=>`<li>#${x.n} ${h(x.question)}</li>`).join('')}</ul>`:''}
        ${r.questions.length?`<p><b>需要问业务方：</b></p><ul>${r.questions.map(x=>`<li>${h(x.question)} <small class="sub">问：${h(x.who||'待指定')}</small></li>`).join('')}</ul>`:''}
        ${r.questions.length||r.to_write.length?`<button id="trRec">记入待答问题${r.to_write.length?'，并排队补写 '+r.to_write.length+' 条业务流':''}</button>`:''}</div>`;
      if($('#trRec'))$('#trRec').onclick=async()=>{try{const x=await post(`/api/projects/${S.proj}/kb/triage`,{request:q,record:true,model:!!r.model});toast('已记入问题 '+x.recorded.questions.map(n=>'#'+n).join('、'));$('#trRec').disabled=true}catch(e){toast(e.message)}}
    }catch(e){$('#trOut').innerHTML='<div class="sub">'+h(e.message)+'</div>'}}}
async function kbReview(){
  const [a,b,qq,mm]=await Promise.all([get(`/api/projects/${S.proj}/kb?status=待确认`),get(`/api/projects/${S.proj}/kb?status=过期`),get(`/api/projects/${S.proj}/kb/questions`),get(`/api/projects/${S.proj}/kb/metrics`)]);
  const row=(p,act)=>`<tr><td><a href="#/kb/${encodeURIComponent(p.id)}">${h(p.title)}</a><div class="key">${h(p.id)}</div></td><td>${h(KKIND[p.kind]||p.kind)}</td><td class="sub">${h((p.summary||'').slice(0,90))}</td><td style="white-space:nowrap">${act}</td></tr>`;
  $('#kbBody').innerHTML=`<div class="grid2"><div class="card"><h2>待人工确认 <small class="sub">${a.pages.length} 页</small></h2><div class="sub" style="margin-bottom:8px">智能体写好、通过了校验，但还没人看过。确认会记下确认人、时间和备注。</div>
     ${a.pages.length?`<div class="tw"><table class="t">${a.pages.map(p=>row(p,`<a href="#/kb/${encodeURIComponent(p.id)}">阅读并确认 →</a>`)).join('')}</table></div>`:'<div class="sub">没有待确认的页面</div>'}</div>
    <div class="card"><h2>代码变化，需更新 <small class="sub">${b.pages.length} 页</small></h2><div class="sub" style="margin-bottom:8px">这些页面依据的代码指纹变了，说明可能已过时；原来的确认记录保留。</div>
     ${b.pages.length?`<div class="tw"><table class="t">${b.pages.map(p=>row(p,`<a href="#/kb/${encodeURIComponent(p.id)}">查看并修订 →</a>`)).join('')}</table></div>`:'<div class="sub">没有需要更新的页面</div>'}</div></div>
    ${kbQuestions(qq)}${kbMetrics(mm)}`;
  document.querySelectorAll('[data-ovr]').forEach(x=>x.onclick=()=>kbOverrule(x.dataset.ovr));
  document.querySelectorAll('[data-ans]').forEach(x=>x.onclick=()=>{const q=qq.questions.find(y=>y.n===+x.dataset.ans);kbAnswer(q.n,q.question)})}
// 少找人: how many requests were answered without a person, and whether people later overruled them
function kbMetrics(mm){const m=mm.metrics,pc=x=>x==null?'—':Math.round(x*100)+'%';
  if(!m.triage&&!m.answered&&!m.waiting)return '';
  return `<div class="card" style="margin-top:16px"><h2>少找人 <small class="sub">需求预判 ${m.triage} 次</small></h2>
   <div class="row" style="gap:24px;margin:6px 0 10px"><div><b>${pc(m.auto_rate)}</b><div class="sub">不用找人直接答（${m.auto} 次）</div></div>
    <div><b>${pc(m.adopted_rate)}</b><div class="sub">采纳率（被改判 ${m.overruled} 次）</div></div><div><b>${m.handoff}</b><div class="sub">转人工</div></div>
    <div><b>${m.answer_wait_hours==null?'—':m.answer_wait_hours+' 小时'}</b><div class="sub">业务方平均答复（还在等 ${m.waiting} 个）</div></div></div>
   ${mm.recent.length?`<div class="tw"><table class="t"><tr><th>编号</th><th>时间</th><th>来源</th><th>需求</th><th>结论</th><th></th></tr>${mm.recent.map(r=>`<tr><td class="key">${h(r.id||'')}</td><td class="sub">${h(r.at||'')}</td><td class="sub">${h(r.channel||'cli')}${r.sender?' · '+h(r.sender):''}</td><td>${h(r.request||'')}</td>
     <td>${h(r.verdict)} <small class="sub">${h(r.confidence||'')}</small></td><td style="white-space:nowrap">${r.overruled?`<span class="sub">${h(r.overruled.by)} 已改判</span>`:r.id?`<button class="ghost" data-ovr="${h(r.id)}">改判</button>`:''}</td></tr>`).join('')}</table></div>`:''}</div>`}
function kbOverrule(id){modal(`<h2>改判预判 ${h(id)}</h2><select id="ovV" class="full"><option value="">正确结论（可不选）</option><option>可以做</option><option>不能做</option><option>需要人判断</option></select>
  <textarea class="full" id="ovR" rows="3" placeholder="为什么不对" style="margin-top:8px"></textarea><div class="sub" style="margin:6px 0">改判会从少找人的采纳率里扣掉，并记进项目动态。</div>
  <div class="row"><button class="primary" id="ovOk">保存</button><button onclick="closeModal()">取消</button></div>`);
  $('#ovOk').onclick=async()=>{const reason=$('#ovR').value.trim();if(!reason)return toast('写一句理由');try{await post(`/api/projects/${S.proj}/kb/overrule`,{id,reason,verdict:$('#ovV').value});closeModal();toast('已改判');kbReview()}catch(e){toast(e.message)}}}
function kbQuestions(qq){const open=qq.questions.filter(q=>q.open),st=qq.stats;
  return `<div class="card" style="margin-top:16px"><h2>待业务方答复 <small class="sub">${open.length} 个 · 已答复 ${st.questions_answered} 个 · 答复后待修订 ${st.revise} 页</small></h2>
   <div class="sub" style="margin-bottom:8px">知识库和代码都说不清、必须由业务方回答的问题。答复按原话记录，写回相关知识页。</div>
   ${open.length?`<div class="tw"><table class="t">${open.map(q=>`<tr><td>#${q.n}</td><td>${h(q.question)}</td><td class="sub">${q.pages.map(p=>`<a href="#/kb/${encodeURIComponent(p)}">${h(p)}</a>`).join('、')||h(q.pages_text)}</td><td class="sub">${h(q.who)}</td><td style="white-space:nowrap"><button class="ghost" data-ans="${q.n}">记录答复</button></td></tr>`).join('')}</table></div>`:'<div class="sub">没有待答复的问题</div>'}</div>`}

// ---------- architecture & evidence: overview → domain → flow → call chain and code
async function vMap(did){
  if(did)return archDomain(did);
  const a=await get('/api/projects/'+S.proj+'/arch');
  const rep=`/p/${encodeURIComponent(S.proj)}/report/index.html`;
  const head=pageHead('架构与依据','项目组件、业务模块与代码证据。',a.report?`<a class="btn" href="${rep}" target="_blank" rel="noopener">完整业务全景报告 ↗</a>`:'');
  if(!a.built){$('#main').innerHTML=head+'<div class="hint">还没有知识图谱。到“知识库 → 建设进度”开始一次全项目分析。</div>';return}
  $('#main').innerHTML=head+`<div class="card"><div class="row" style="align-items:center"><h2 class="grow" style="margin:0">系统结构概览</h2><span class="ev-tag info">代码事实 · 工具解析</span><span class="ev-tag mute">部署关系未核实</span></div>
    <div class="sub" style="margin:4px 0 8px">入口、业务域、数据表和外部调用都是从代码解析出来的；服务器、代理、缓存等部署结构不在代码事实里，图里不画。更新于 ${h(a.built_at)}。</div>
    <div class="archwrap">${archSvg(a)}</div></div>
   <div class="grid2" style="margin-top:16px"><div class="card"><h2>从业务进入依据</h2>${a.domains.map(d=>`<a class="drow" href="#/map/${encodeURIComponent(d.id)}"><span class="grow"><b>${h(d.title)} →</b><span class="sub">${d.flows} 条业务流 · ${d.tables} 张表${d.summary?' · '+h(d.summary.slice(0,40)):''}</span></span>${kst(d.status)}</a>`).join('')}</div>
    <div class="card"><h2>维护时先核对什么</h2><ul class="chk2">
     <li>部署包和这份源码是否一致（反编译源码尤其要核对版本）。</li>
     <li>${a.unresolved?`<b>${a.unresolved} 处</b>静态分析断开（动态表名、按配置分派、反射），相关结论只能算推断。`:'静态分析没有发现断开的调用（动态表名、反射等）。'}</li>
     <li>结论是代码事实、模型推断还是待确认：知识页里分别标为“代码核实”和“【推断】”。</li>
     <li>系统总览${a.overview_status&&a.overview_status!=='仅事实'&&a.overview_status!=='未分析'?'已撰写（'+h(a.overview_status)+'）':'还没写，可以在知识库里用“业务地图”模式先写业务域和总览'}。</li></ul>
     <a class="btn" href="#/kb">阅读相关业务说明 →</a></div></div>`}
function archSvg(a){
  const W=980,colX=[20,330,700],bw=[230,300,260];const doms=a.domains.slice(0,6);const more=a.domains.length-doms.length;
  const ent=a.entries.slice(0,4);const ext=a.ext.slice(0,3);
  const rows=Math.max(doms.length+(more?1:0),ent.length,2+ext.length);const RH=62,H=Math.max(300,40+rows*RH);
  const box=(x,y,w,t,s,cls,href)=>`${href?`<a href="${href}">`:''}<g class="ab ${cls||''}"><rect x="${x}" y="${y}" width="${w}" height="50" rx="8"/><text x="${x+14}" y="${y+21}" class="t1">${h(t)}</text><text x="${x+14}" y="${y+39}" class="t2">${h(s)}</text></g>${href?'</a>':''}`;
  const ey=i=>30+i*RH*(rows/Math.max(ent.length,1))*.8,dy=i=>30+i*RH,ry=i=>30+i*RH*1.1;
  let g='';const cx1=colX[0]+bw[0],cx2=colX[1],cx3=colX[1]+bw[1],cx4=colX[2];
  const mid=(H-20)/2;
  ent.forEach(([k,n],i)=>{const y=ey(i);g+=`<path class="ln" d="M${cx1} ${y+25} C ${cx1+50} ${y+25}, ${cx2-50} ${mid}, ${cx2} ${mid}"/>`;g+=box(colX[0],y,bw[0],k,n+' 个入口','e')});
  doms.forEach((d,i)=>{const y=dy(i);g+=`<path class="ln" d="M${cx3} ${y+25} C ${cx3+50} ${y+25}, ${cx4-50} ${55}, ${cx4} ${55}"/>`;g+=box(colX[1],y,bw[1],d.title,`${d.flows} 条业务流 · ${d.tables} 张表`,'d',`#/map/${encodeURIComponent(d.id)}`)});
  if(more)g+=`<text x="${colX[1]+14}" y="${dy(doms.length)+28}" class="t2">另有 ${more} 个业务域 …</text>`;
  g+=box(colX[2],30,bw[2],`数据库表 ${a.tables} 张`,'最常用：'+a.top_tables.slice(0,2).map(x=>x[0]).join('、'),'t');
  ext.forEach((e,i)=>{const y=ry(i+1)+10;g+=`<path class="ln dash" d="M${cx3} ${dy(0)+25} C ${cx3+60} ${dy(0)+25}, ${cx4-60} ${y+25}, ${cx4} ${y+25}"/>`;g+=box(colX[2],y,bw[2],e.title,e.users+' 处调用','x')});
  const lab=(x,t)=>`<text x="${x}" y="16" class="cap">${t}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" class="arch" role="img" aria-label="系统结构概览">${lab(colX[0],'入口（'+a.flows+' 条业务流）')}${lab(colX[1],'业务域')}${lab(colX[2],'数据与外部调用')}${g}</svg>`}
async function archDomain(did){
  const d=await get('/api/projects/'+S.proj+'/arch/'+encodeURIComponent(did));
  const ops={C:'增',R:'查',U:'改',D:'删',P:'过程'};
  $('#main').innerHTML=`<div class="crumb"><a href="#/map">架构与依据</a> / ${h(d.title)}</div>`+pageHead(d.title,d.summary||'这个业务域还没有业务说明；下面是工具从代码解析出的入口、处理和数据操作。',`<div class="row" style="gap:8px">${kst(d.status)}<a class="btn" href="#/kb/${encodeURIComponent(d.id)}">读业务说明</a></div>`)+
   `<div class="card"><div class="row" style="align-items:center;margin-bottom:8px"><h2 class="grow" style="margin:0">业务流 · ${d.flows.length} 条</h2><span class="ev-tag info">代码事实</span><span class="ev-tag warn">断开处需人工确认</span></div>
    <div class="tw"><table class="t"><tr><th>业务流</th><th>入口</th><th>处理</th><th>数据操作</th><th>代码位置</th><th></th></tr>${d.flows.map(f=>`<tr class="click" onclick="showFlow('${h(f.id)}')"><td><b>${h(f.title)}</b><div>${kst(f.status)}</div></td><td><span class="tag">${h(f.entry_kind||'入口')}</span><div class="key" style="white-space:normal">${h(f.entry)}</div></td><td class="key" style="white-space:normal">${h(f.handler)}<div class="sub">${f.steps} 步调用${f.states?' · '+f.states+' 处状态变化':''}</div></td>
      <td>${Object.entries(f.crud).map(([t,o])=>`<span class="tag">${h(t)} <b>${h(String(o).split('').map(c=>ops[c]||c).join(''))}</b></span>`).join(' ')||'<span class="sub">无</span>'}</td><td class="key" style="white-space:normal">${h(f.file)}:${f.line}</td><td>${f.unresolved?`<span class="ev-tag warn" title="动态表名、反射或按配置分派">${f.unresolved} 处断开</span>`:''}</td></tr>`).join('')}</table></div></div>`}

// ---------- agent runs: tasks and batches, with where each one came from
async function vRuns(){
  const rs=await get('/api/runs?project='+S.proj);const f=sessionStorage.getItem('tmh.rf')||'all';
  const ST={queued:'排队',running:'运行中',done:'完成',failed:'失败',cancelled:'已取消'};const SC={queued:'mute',running:'info',done:'ok',failed:'bad',cancelled:'mute'};
  const items=[];const bat={};
  rs.forEach(r=>{if(r.batch){if(!bat[r.batch]){bat[r.batch]={batch:r.batch,runs:[],created:r.created};items.push(bat[r.batch])}bat[r.batch].runs.push(r)}else items.push(r)});
  const live=rs.filter(r=>['queued','running'].includes(r.status)).length,bad=rs.filter(r=>r.status==='failed').length;
  const lastB=items.find(x=>x.batch);const lastOk=lastB?lastB.runs.filter(r=>r.status==='done').length:0;
  const review=rs.filter(r=>r.mode==='fix'&&r.status==='done'&&!r.decision).length;
  const src=r=>r.ticket?`工单 <a href="#/t/${h(r.ticket)}" onclick="event.stopPropagation()">${h(r.ticket)}</a> ${h(r.ticket_title)}`:r.session_id?`会话「${h(r.session_title||'')}」`:r.mode==='kb'?'知识库 · 单页撰写':'项目';
  const obj=r=>r.mode==='kb'?`<span class="key">${h(r.target)}</span>`:r.mode==='ask'?h(r.target||''):'';
  const one=r=>{const rev=r.mode==='fix'&&r.status==='done'?(r.decision?(r.decision.startsWith('acc')?'<span class="ev-tag ok">已采纳</span>':'<span class="ev-tag mute">已放弃</span>'):'<span class="ev-tag warn">待审阅改动</span>'):'';
    return `<div class="ri"><div class="grow" style="min-width:0"><div class="rt"><span class="ev-tag ${SC[r.status]}">${ST[r.status]}${r.status==='running'?' <span class="spin"></span>':''}</span><b>${h(moLabel(r.mode))}</b>${rev}</div>
      <div class="sub">来源：${src(r)}${obj(r)?' · 对象：'+obj(r):''} · ${h(r.agent)}${mTag(r)} · 发起人 ${h(r.author)} · ${ago(r.created)}</div>
      ${r.status!=='running'&&r.result?`<details class="run-check"><summary>原运行输出 · 历史记录</summary><p class="sub">当前代码与实际验证请点击「查看运行」。历史输出中的判断不代表当前验证结果。</p>${md(r.result)}</details>`:''}</div>
     <div class="ra"><button onclick="showRun(${r.id})">查看运行</button>${r.session_id?`<button class="ghost" onclick="A.toggle(true);A.switchTo(${r.session_id})">打开所属会话</button>`:''}</div></div>`};
  const batch=b=>{const n=b.runs.length,ok=b.runs.filter(r=>r.status==='done').length,ko=b.runs.filter(r=>r.status==='failed'),run=b.runs.filter(r=>['queued','running'].includes(r.status)).length;
    const st=run?'running':ko.length&&ok?'part':ko.length?'failed':'done';const lab={running:'进行中',part:'部分失败',failed:'失败',done:'完成'}[st];
    const after=b.batch.startsWith('after-'),ev=b.batch.startsWith('eval-');if(ev)return evBatch(b,st,lab);const t=b.runs.find(r=>r.ticket)||{};
    return `<div class="ri"><div class="grow" style="min-width:0"><div class="rt"><span class="ev-tag ${{running:'info',part:'warn',failed:'bad',done:'ok'}[st]}">${lab}</span><b>${after?'分析后补写知识页':'知识库建设 · 批次 '+h(b.batch)}</b></div>
      <div class="sub">来源：${after?'工单分析 #'+h(b.batch.slice(6)):'知识库建设'} · ${h(b.runs[0].agent)} · 发起人 ${h(b.runs[0].author)} · ${ago(b.runs[b.runs.length-1].created)}</div>
      <div class="out">${n} 个子任务：完成 ${ok}${ko.length?'，失败 '+ko.length:''}${run?'，进行中 '+run:''}。执行完成只代表页面通过了入库校验，业务说明仍需人工确认。</div>
      <details class="sub2"><summary>展开子任务</summary>${b.runs.map(r=>`<div class="svr"><span class="ev-tag ${SC[r.status]}">${ST[r.status]}</span><a href="#/kb/${encodeURIComponent(r.target)}">${h(r.target)}</a><a href="javascript:void 0" onclick="showRun(${r.id})">运行 #${r.id}</a>${r.status==='failed'?`<button class="ghost" onclick="retryKb(${r.id},'${h(r.target)}','${h(r.agent)}','${h(b.batch)}')">重试</button>`:''}</div>`).join('')}</details></div>
     <div class="ra">${ko.length?`<button onclick="retryAll('${h(b.batch)}')">重试失败项（${ko.length}）</button>`:''}</div></div>`};
  const keep=x=>f==='all'?true:f==='live'?(x.batch?x.runs.some(r=>['queued','running'].includes(r.status)):['queued','running'].includes(x.status)):(x.batch?x.runs.some(r=>r.status==='failed'):x.status==='failed');
  S.runItems=items;
  $('#main').innerHTML=pageHead('智能体运行','当前任务、运行阶段与交付结果。执行状态、知识是否确认、改动是否采纳分开显示。',`<select id="rf" aria-label="筛选"><option value="all">全部任务</option><option value="live" ${f==='live'?'selected':''}>进行中</option><option value="bad" ${f==='bad'?'selected':''}>有异常</option></select>`)+
   `<div class="kpis">${[[live,'运行中的任务'],[bad,'失败的任务'],[lastOk,'最近一批产出知识页'],[review,'待审代码改动']].map(([n,l])=>`<div><b>${n}</b><span>${l}</span></div>`).join('')}</div>`+
   (items.length?`<div class="card rl">${items.filter(keep).map(x=>x.batch?batch(x):one(x)).join('')||'<div class="sub">没有符合条件的任务</div>'}</div>`:'<div class="empty">还没有运行过智能体。打开一张工单点“分析定位”，或在知识库里开始建设。</div>');
  $('#rf').onchange=e=>{sessionStorage.setItem('tmh.rf',e.target.value);vRuns()};
  if(live)poll(()=>{if(location.hash==='#/runs')vRuns()},5000)}
async function retryKb(rid,target,agent,batch){try{const r=await post(`/api/projects/${S.proj}/runs`,{agent,mode:'kb',target,batch});toast('已重试 '+target+'（运行 #'+r.id+'，原记录保留）');vRuns()}catch(e){toast(e.message)}}
async function retryAll(batch){const b=(S.runItems||[]).find(x=>x.batch===batch);if(!b)return;const ko=b.runs.filter(r=>r.status==='failed');
  const done=new Set(b.runs.filter(r=>r.status==='done').map(r=>r.target));const todo=[...new Set(ko.map(r=>r.target))].filter(t=>!done.has(t));
  if(!todo.length){toast('失败项后来都已写成，不用重试');return}
  for(const t of todo){try{await post(`/api/projects/${S.proj}/runs`,{agent:ko[0].agent,mode:'kb',target:t,batch})}catch(e){toast(e.message);break}}
  toast('已重试 '+todo.length+' 个失败项，成功的不会重写');vRuns()}

function evBatch(b,st,lab){const SC={queued:'mute',running:'info',done:'ok',failed:'bad',cancelled:'mute'};
  return `<div class="ri"><div class="grow" style="min-width:0"><div class="rt"><span class="ev-tag ${{running:'info',part:'warn',failed:'bad',done:'ok'}[st]}">${lab}</span><b>评测回放 · ${b.runs.length} 个用例</b></div>
    <div class="sub">来源：<a href="#/learn">闭环改进</a> · ${h(b.runs[0].agent)}${mTag(b.runs[0])} · 发起人 ${h(b.runs[0].author)} · ${ago(b.runs[b.runs.length-1].created)}</div>
    <details class="sub2"><summary>展开用例</summary>${b.runs.map(r=>`<div class="svr"><span class="ev-tag ${SC[r.status]}">${h(r.status)}</span>${h(r.target)}<a href="javascript:void 0" onclick="showRun(${r.id})">运行 #${r.id}</a></div>`).join('')}</details></div><div class="ra"><a class="btn" href="#/learn">看得分</a></div></div>`}

// ---------- 重构升级: a big reform split by business domain into ordinary change tickets, released in waves
async function vReform(){
  const P='/api/projects/'+encodeURIComponent(S.proj)+'/reforms';const d=await get(P);S.rf=d;
  const RC={'低':'ok','中':'warn','高':'bad'};
  const head=pageHead('改造计划','老项目的结构重构、依赖升级、框架迁移和兼容适配。大目标按业务域拆成改动工单，牵连少的先做、当试点；每张单照常走自动分析、改代码、构建测试，停在人工验收；一批全部验收通过就自动放出下一批，验收时说的话带给后面的单。',d.built?`<button class="primary" id="rfNew">新建改造计划</button>`:'');
  if(!d.built){$('#main').innerHTML=head+'<div class="empty">这个项目还没有知识库，没法按业务域拆分。先到“知识库”建设一次。</div>';return}
  const bar=c=>{const w=x=>c.total?x/c.total*100:0;return `<div class="rfbar" title="已闭环 ${c.closed} · 待验收 ${c.verify} · 已放出 ${c.released} · 共 ${c.total}"><i class="ok" style="width:${w(c.closed)}%"></i><i class="vf" style="width:${w(c.verify)}%"></i><i class="rl" style="width:${w(c.released-c.closed-c.verify)}%"></i></div>`};
  const row=it=>`<tr><td class="num">${it.lead?'先导':it.order}</td><td><b>${h(it.title)}</b>${it.lead?'<div class="sub">公共部分，验收通过后其余各部分从它的代码开始</div>':''}</td><td class="num">${it.flows}</td><td class="num">${it.tables}</td><td>${it.shared.length?it.shared.slice(0,3).map(([n,c])=>`<span class="tag">${h(n)} ${c}</span>`).join(' '):'<span class="sub">无</span>'}${it.unresolved?` <span class="ev-tag warn">${it.unresolved} 处断开</span>`:''}</td><td><span class="ev-tag ${RC[it.risk]}">${it.risk}</span></td><td>${it.ticket?`<a href="#/t/${h(it.ticket)}">${h(it.ticket)}</a> ${it.status?stPill(it.status):''}`:'<span class="sub">未放出</span>'}</td></tr>`;
  const table=items=>`<div class="tw"><table class="t"><tr><th class="num">顺序</th><th>业务域</th><th class="num">业务流</th><th class="num">表</th><th>和别的域共用表</th><th>牵连</th><th>工单</th></tr>${items.map(row).join('')}</table></div>`;
  const plan=p=>{const c=p.counts,left=c.total-c.released;
    return `<div class="card rfp"><div class="hdr" style="margin-bottom:6px"><span class="ev-tag info">${h(p.kind_label)}</span><h2 class="grow" style="margin:0">${h(p.title)}</h2>${!left?'<span class="ev-tag ok">已全部放出</span>':c.lead&&!c.released?`<button class="primary" data-rel="${h(p.id)}">放出先导部分（1 张）</button>`:c.lead&&!p.lead_passed?'<span class="ev-tag warn">等先导部分验收通过</span>':`<button class="primary" data-rel="${h(p.id)}">${c.released>(c.lead?1:0)?'放出下一批':'放出第一批（试点）'}（${Math.min(p.wave,left)} 张）</button>`}</div>
     <div class="sub" style="white-space:pre-wrap">${h(p.goal)}</div>${p.target?`<div class="sub" style="margin-top:4px"><b>目标目录：</b><span class="key">${h(p.target)}/</span>（原代码只读）</div>`:''}${p.keep?`<div class="sub" style="margin-top:4px"><b>不能变：</b>${h(p.keep)}</div>`:''}
     ${p.paused?`<div class="rfpz"><span class="grow"><b>已暂停自动推进：</b>${h(p.paused)}</span><button class="ghost" data-res="${h(p.id)}">处理好了，恢复</button></div>`:''}
     <div class="row" style="gap:10px;align-items:center;margin:10px 0">${bar(c)}<span class="sub" style="white-space:nowrap">闭环 ${c.closed} · 待验收 ${c.verify} · 已放出 ${c.released} / ${c.total}</span><label class="sub rfau"><input type="checkbox" data-auto="${h(p.id)}" ${p.auto?'checked':''}> 通过一批自动放下一批</label></div>
     <details ${c.released?'open':''}><summary>${c.lead?'先导部分 + '+(c.total-1):c.total} 个业务域，按牵连从少到多</summary>${table(p.items)}${(p.log||[]).length?`<div class="rflog">${p.log.slice(-6).reverse().map(x=>`<div><span class="sub">${h(x.at.slice(5,16))}</span> ${h(x.text)}</div>`).join('')}</div>`:''}<div class="row" style="margin-top:8px"><span class="sub grow">${h(p.by)} 建于 ${h(p.created.slice(0,16))} · 每批 ${p.wave} 张</span><button class="ghost" data-rm="${h(p.id)}">删除计划（已开的工单保留）</button></div></details></div>`};
  const list=d.plans.length?d.plans.map(plan).join(''):`<div class="empty">还没有改造计划。点右上角“新建改造计划”：写清目标，选业务域，系统按牵连从少到多排好顺序，分批放出改动工单。</div>`;
  const T=d.plans.reduce((a,p)=>{for(const k in p.counts)a[k]=(a[k]||0)+p.counts[k];return a},{}),paused=d.plans.filter(p=>p.paused).length;
  const kpi=d.plans.length?`<div class="kpis"><div><span>改造计划</span><b>${d.plans.length}</b><small>${paused?paused+' 个暂停等人处理':'没有暂停的计划'}</small></div>
    <div><span>业务域块已闭环</span><b>${T.closed||0}<small style="font-size:14px"> / ${T.total||0}</small></b><small>已放出 ${T.released||0} 块</small></div>
    <div><span>待验收</span><b>${T.verify||0}</b><small>改好了，等人验收</small></div>
    <div><span>一次验收通过</span><b>${T.closed?Math.round(T.first_pass/T.closed*100)+'%':'—'}</b><small>已闭环的 ${T.closed||0} 块里没被退回过的${T.rejected?' · 退回过 '+T.rejected+' 块':''}</small></div></div>`:'';
  $('#main').innerHTML=head+kpi+`<div id="rfForm" hidden></div>`+list;
  if($('#rfNew'))$('#rfNew').onclick=()=>rfForm();
  if(S.rfNew&&$('#rfNew')){S.rfNew=0;rfForm()}
  document.querySelectorAll('[data-rel]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await post(P+'/'+b.dataset.rel,{action:'release'});toast('已放出 '+r.opened.join('、')+'，开始自动处理');vReform()}catch(e){toast(e.message);b.disabled=false}});
  document.querySelectorAll('[data-res]').forEach(b=>b.onclick=()=>post(P+'/'+b.dataset.res,{action:'resume'}).then(()=>{toast('已恢复，下一批验收通过后继续自动推进');vReform()}).catch(e=>toast(e.message)));
  document.querySelectorAll('[data-auto]').forEach(c=>c.onchange=()=>post(P+'/'+c.dataset.auto,{action:'auto',on:c.checked}).then(vReform).catch(e=>toast(e.message)));
  document.querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>{if(b.dataset.ok){post(P+'/'+b.dataset.rm,{action:'remove'}).then(vReform).catch(e=>toast(e.message))}else{b.dataset.ok=1;b.textContent='再点一次确认删除'}})}
// ---------- 改造工单: every ticket a reform plan released, in plan order; not on the 运维 board or in its numbers
async function vRtickets(){
  const P='/api/projects/'+encodeURIComponent(S.proj);const [d,ts]=await Promise.all([get(P+'/reforms'),get('/api/tickets?svc=reform&project='+encodeURIComponent(S.proj))]);
  const tk={};ts.forEach(t=>tk[t.key]=t);const f=JSON.parse(sessionStorage.getItem('tmh.rtf')||'{}');
  const rows=[];d.plans.forEach(p=>p.items.filter(i=>i.ticket).forEach(i=>rows.push({p,i,t:tk[i.ticket]||{}})));
  const show=rows.filter(r=>(!f.plan||r.p.id===f.plan)&&(!f.open||r.i.status!=='closed'));
  $('#main').innerHTML=pageHead('改造工单','改造计划放出的工单。它们和运维工单走同一条自动处理流程（分析、改代码、构建测试、等验收），但不进运维看板和运维成效。',
    `<div class="row" style="gap:8px;flex-wrap:wrap"><select id="rtP"><option value="">全部计划（${d.plans.length}）</option>${d.plans.map(p=>`<option value="${h(p.id)}" ${f.plan===p.id?'selected':''}>${h(p.title)}</option>`).join('')}</select><label class="sub" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="rtO" ${f.open?'checked':''}> 只看未关闭</label></div>`)+
    (show.length?`<div class="tw"><table class="t"><tr><th>工单</th><th>计划</th><th class="num">部分</th><th>业务域</th><th>状态</th><th class="num">退回</th><th>负责人</th><th>更新</th></tr>${show.map(({p,i,t})=>`<tr><td><a href="#/t/${h(i.ticket)}">${h(i.ticket)}</a></td><td><span class="ev-tag info">${h(p.kind_label)}</span> ${h(p.title)}${p.paused?' <span class="ev-tag warn">暂停</span>':''}</td><td class="num">${i.lead?'先导':i.order+' / '+(p.counts.total-(p.counts.lead?1:0))}</td><td><b>${h(i.title)}</b></td><td>${i.status?stPill(i.status):''}</td><td class="num">${i.rejects||''}</td><td>${h(t.assignee||'')||'<span class="sub">自动</span>'}</td><td class="sub">${t.updated?ago(t.updated):''}</td></tr>`).join('')}</table></div>`
     :`<div class="empty">${rows.length?'没有符合条件的工单。':'还没有放出过改造工单。到“改造计划”建一个计划，放出第一批。'}</div>`);
  const save=()=>{sessionStorage.setItem('tmh.rtf',JSON.stringify({plan:$('#rtP').value,open:$('#rtO').checked}));vRtickets()};
  $('#rtP').onchange=save;$('#rtO').onchange=save}
// ---------- 依赖清单: what the project declares, for writing upgrade and migration goals
async function vRdeps(){
  const r=await get('/api/projects/'+encodeURIComponent(S.proj)+'/reforms/deps');const by={};r.deps.forEach(x=>by[x.system]=(by[x.system]||0)+1);
  $('#main').innerHTML=pageHead('依赖清单','从 pom.xml（含父 POM 和 properties 里的版本）、package.json、.csproj / packages.config、requirements*.txt 读出的依赖和版本。写升级、迁移计划的目标版本时对照。',
    r.deps.length?`<input id="rdQ" placeholder="筛选名称" style="width:180px">`:'')+
    (r.deps.length?`<div class="row" style="gap:6px;flex-wrap:wrap;margin-bottom:10px">${Object.entries(by).map(([k,n])=>`<span class="tag">${h(k)} ${n}</span>`).join('')}</div><div class="tw"><table class="t" id="rdT"><tr><th>类型</th><th>名称</th><th>版本</th><th>声明在</th></tr>${r.deps.map(x=>`<tr data-n="${h(x.name.toLowerCase())}"><td>${h(x.system)}</td><td class="key">${h(x.name)}</td><td class="key">${h(x.version||'—')}</td><td class="sub">${h(x.file)}</td></tr>`).join('')}</table></div>`
     :'<div class="empty">没有找到 pom.xml、package.json、.csproj 或 requirements.txt。</div>');
  if($('#rdQ'))$('#rdQ').oninput=e=>{const q=e.target.value.trim().toLowerCase();document.querySelectorAll('#rdT tr[data-n]').forEach(tr=>tr.hidden=!!q&&!tr.dataset.n.includes(q))}}
function rfForm(){const d=S.rf,P='/api/projects/'+encodeURIComponent(S.proj)+'/reforms',f=$('#rfForm');f.hidden=false;$('#rfNew').hidden=true;document.querySelectorAll('#main>.rfp,#main>.empty').forEach(x=>x.hidden=true);
  const RC={'低':'ok','中':'warn','高':'bad'};let kind='restructure';const sel=new Set();
  const doms=d.domains.filter(x=>x.id!=='dom:_');
  f.innerHTML=`<div class="card" style="margin-bottom:16px"><h2>新建改造计划</h2>
   <div class="rfk">${Object.entries(d.kinds).map(([k,v])=>`<button class="rfkb ${k===kind?'on':''}" data-k="${k}"><b>${h(v.label)}</b><span>${h(v.desc)}</span></button>`).join('')}</div>
   <div class="grid2" style="margin-top:12px"><div style="display:flex;flex-direction:column;gap:8px;min-width:0">
    <input id="rfT" placeholder="名称，例如：请假审批模块分层整理">
    <textarea id="rfG" style="min-height:90px" placeholder="改成什么样：目标、做法、完成的标准。例如：Spring 4.3 升到 5.3，JDK 8 升到 17，替换掉已废弃的接口。"></textarea>
    <textarea id="rfK" style="min-height:60px" placeholder="不能变的东西（可空）：对外接口、表结构、报表口径……"></textarea>
    <input id="rfTg" placeholder="目标目录（跨语言重写必填，例如 java；新代码写在这里，原代码只读）">
    <details id="rfLd"><summary>先导部分（可空）：各业务域都要用的公共部分，先单独做、验收通过后再放出其余部分</summary>
     <div style="display:flex;flex-direction:column;gap:8px;margin-top:6px"><input id="rfLt" placeholder="名称，例如：工程骨架"><textarea id="rfLb" style="min-height:70px" placeholder="要做什么，例如：建工程和依赖、数据库配置、建表、实体、登录鉴权、统一错误格式"></textarea></div></details>
    <label class="sub" style="display:flex;gap:8px;align-items:center">每批放出 <input id="rfW" type="number" min="1" max="20" value="3" style="width:70px"> 张工单</label>
    <label class="sub" style="display:flex;gap:8px;align-items:center"><input id="rfA" type="checkbox" checked> 一批全部验收通过后，自动放出下一批（有一块重改后仍不通过就暂停）</label>
    <details id="rfDeps"><summary>看项目当前依赖（升级、迁移时写目标版本用）</summary><div class="sub">加载中…</div></details></div>
   <div style="min-width:0"><div class="hdr" style="margin-bottom:6px"><b class="grow">范围：业务域</b><input id="rfQ" placeholder="筛选" style="width:120px"><button class="ghost" id="rfAll">全选</button><button class="ghost" id="rfNone">清空</button></div>
    <div class="rfdl" id="rfDl"></div></div></div>
   <h3 style="margin:14px 0 6px">拆分预览 <span class="sub" id="rfPn" style="font-weight:400"></span></h3><div id="rfPv"><div class="sub">选了业务域后在这里看顺序和牵连。不选就是全部业务域。</div></div>
   <div class="row" style="gap:8px;margin-top:12px"><button class="primary" id="rfGo">建立计划</button><button class="ghost" id="rfX">取消</button><span class="sub">建好后不会马上开单，由你点“放出第一批”。</span></div></div>`;
  const paint=()=>{const q=$('#rfQ').value.trim();$('#rfDl').innerHTML=doms.filter(x=>!q||x.title.includes(q)).map(x=>`<label class="rfd"><input type="checkbox" data-d="${h(x.id)}" ${sel.has(x.id)?'checked':''}><span class="grow">${h(x.title)}</span><span class="sub">${x.flows} 流 · ${x.tables} 表</span></label>`).join('')||'<div class="sub">没有匹配的业务域</div>';
    document.querySelectorAll('#rfDl [data-d]').forEach(c=>c.onchange=()=>{c.checked?sel.add(c.dataset.d):sel.delete(c.dataset.d);preview()})};
  let tm;const preview=()=>{clearTimeout(tm);tm=setTimeout(async()=>{const r=await post(P,{preview:true,domains:[...sel]});$('#rfPn').textContent=r.items.length+' 张工单，按牵连从少到多';
    $('#rfPv').innerHTML=`<div class="tw"><table class="t"><tr><th class="num">顺序</th><th>业务域</th><th class="num">业务流</th><th class="num">表</th><th>和别的域共用表</th><th>牵连</th></tr>${r.items.slice(0,40).map(it=>`<tr><td class="num">${it.order}</td><td><b>${h(it.title)}</b></td><td class="num">${it.flows}</td><td class="num">${it.tables}</td><td>${it.shared.slice(0,3).map(([n,c])=>`<span class="tag">${h(n)} ${c}</span>`).join(' ')||'<span class="sub">无</span>'}</td><td><span class="ev-tag ${RC[it.risk]}">${it.risk}</span></td></tr>`).join('')}</table></div>${r.items.length>40?`<div class="sub">另有 ${r.items.length-40} 个</div>`:''}`},250)};
  document.querySelectorAll('.rfkb').forEach(b=>b.onclick=()=>{kind=b.dataset.k;document.querySelectorAll('.rfkb').forEach(x=>x.classList.toggle('on',x===b))});
  $('#rfQ').oninput=paint;$('#rfAll').onclick=()=>{const q=$('#rfQ').value.trim();doms.filter(x=>!q||x.title.includes(q)).forEach(x=>sel.add(x.id));paint();preview()};$('#rfNone').onclick=()=>{sel.clear();paint();preview()};
  $('#rfDeps').ontoggle=async e=>{if(!e.target.open||e.target.dataset.l)return;e.target.dataset.l=1;const r=await get(P+'/deps');
    e.target.lastElementChild.outerHTML=r.deps.length?`<div class="tw" style="max-height:260px;overflow:auto"><table class="t"><tr><th>类型</th><th>名称</th><th>版本</th><th>文件</th></tr>${r.deps.map(x=>`<tr><td>${h(x.system)}</td><td class="key">${h(x.name)}</td><td class="key">${h(x.version||'—')}</td><td class="sub">${h(x.file)}</td></tr>`).join('')}</table></div>`:'<div class="sub">没有找到 pom.xml、package.json、.csproj 或 requirements.txt</div>'};
  $('#rfX').onclick=()=>vReform();
  $('#rfGo').onclick=async()=>{try{await post(P,{kind,title:$('#rfT').value,goal:$('#rfG').value,keep:$('#rfK').value,target:$('#rfTg').value,lead:{title:$('#rfLt').value,body:$('#rfLb').value},wave:+$('#rfW').value,auto:$('#rfA').checked,domains:[...sel]});toast('计划已建立，点“放出第一批”开始');vReform()}catch(e){toast(e.message)}};
  paint();preview()}

// ---------- 闭环改进: lessons from acceptance, the eval set, alerts that open tickets
async function vLearn(){
  const d=await get('/api/projects/'+encodeURIComponent(S.proj)+'/learn');S.learn=d;
  const pc=v=>v==null?'—':Math.round(v*100)+'%';
  const last=d.batches[0];
  const KL={reject:['bad','验收没通过'],'human-fix':['warn','人工补改'],review:['warn','对照官方复盘'],pass:['ok','通过的做法']};
  const SRC={accepted:['ok','验收入库'],history:['info','历史工单'],manual:['mute','手动']};
  const bt=d.batches.length?`<div class="tw"><table class="t"><tr><th>时间</th><th>智能体</th><th class="num">用例</th><th class="num">找全率</th><th class="num">准确率</th></tr>${d.batches.map((b,i)=>`<tr class="click" onclick="document.getElementById('evb${i}').hidden^=1"><td>${h(b.ts.slice(5,16))}</td><td>${h(b.agent||'')}${b.model?' · '+h(b.model):''}</td><td class="num">${b.scored}/${b.n}</td><td class="num"><b>${pc(b.recall)}</b></td><td class="num">${pc(b.precision)}</td></tr>
    <tr id="evb${i}" hidden><td colspan="5">${Object.keys(b.sources||{}).length>1?`<div class="sub" style="margin-bottom:6px">${Object.entries(b.sources).map(([k,v])=>`${(SRC[k]||[0,k])[1]} ${v.n} 个：找全 ${pc(v.recall)} · 准确 ${pc(v.precision)}`).join('；')}</div>`:''}${b.rows.map(r=>`<div class="fact" style="flex-direction:column;align-items:stretch"><div class="row" style="gap:8px"><b class="grow">${h(r.case)} ${h(r.title||'')}</b>${r.error?`<span class="ev-tag bad">${h(r.error)}</span>`:`<span class="ev-tag ${r.recall>=0.99?'ok':r.recall>0?'warn':'bad'}">找全 ${pc(r.recall)}</span><span class="ev-tag mute">准确 ${pc(r.precision)}</span>`}${r.run?`<a href="javascript:void 0" onclick="showRun(${r.run})">#${r.run}</a>`:''}</div>
      ${(r.missed||[]).length?`<div class="sub">漏掉：<span class="key">${r.missed.map(h).join('、')}</span></div>`:''}${(r.extra||[]).length?`<div class="sub">多列：<span class="key">${r.extra.slice(0,8).map(h).join('、')}</span></div>`:''}</div>`).join('')}</td></tr>`).join('')}</table></div>`:'<div class="sub">还没回放过。</div>';
  const cs=d.cases.length?d.cases.map(c=>`<div class="fact"><span class="grow" style="min-width:0"><b>${h(c.id)}</b> ${c.ticket?`<a href="#/t/${h(c.ticket)}">${h(c.ticket)}</a> `:''}${h(c.title)}<div class="sub key" style="white-space:normal;overflow-wrap:anywhere">${c.gold.map(h).join('、')}</div></span><span class="ev-tag ${(SRC[c.source]||SRC.manual)[0]}">${(SRC[c.source]||SRC.manual)[1]}</span><button class="ghost" data-rm="${h(c.id)}">移除</button></div>`).join(''):'<div class="sub">验收通过的自动改动会自动成为用例，也可以在下面手动加。</div>';
  const LS={candidate:['warn','待确认'],active:['ok','在用'],probation:['bad','暂停：常跟着失败'],retired:['mute','已停用']};
  const LF=[['symptom','现象'],['cause','根因'],['fix','改法'],['verify','验法'],['anti','别这样改']];
  const lsum=d.lesson_summary||{};
  const ls=d.lessons.length?d.lessons.map(l=>{const st=l.stats||{},n=(st.passed||0)+(st.failed||0),sl=LS[l.status]||LS.active,pv=l.provenance||{};
    return `<div class="fact" style="flex-direction:column;align-items:stretch"><div class="row" style="gap:8px;flex-wrap:wrap"><b>${h(l.id)}</b><span class="ev-tag ${(KL[l.kind]||['mute'])[0]}">${(KL[l.kind]||['',l.kind])[1]}</span><span class="ev-tag ${sl[0]}">${sl[1]}</span><a href="#/t/${h(l.ticket)}">${h(l.ticket)}</a><span class="grow"></span><span class="sub">${h((l.ts||'').slice(5,16))}</span></div>
    <div style="font-weight:600;margin:2px 0">${h(l.title)}</div>${l.note?`<div class="sub" style="white-space:normal">${h(l.note)}</div>`:''}${LF.filter(([k])=>l[k]).map(([k,lb])=>`<div class="sub" style="white-space:normal"><span style="font-size:inherit;font-weight:600">${lb}：</span>${h(l[k])}</div>`).join('')}
    ${(l.files||[]).length?`<div class="sub key" style="white-space:normal;overflow-wrap:anywhere">${l.files.slice(0,6).map(h).join('、')}</div>`:''}
    <div class="sub">${st.used?`放进提示词 ${st.used} 次`:'还没被用过'}${n?` · 之后验收通过 ${st.passed}、没通过 ${st.failed}`:''}${st.cited?` · 智能体明确引用 ${st.cited} 次`:''}${pv.package_hash?` · 来自证据包 <span class="key">${h(pv.package_hash.slice(0,12))}</span>${pv.signer?'，'+h(pv.signer)+' 签收':''}`:''}</div>
    <div class="row" style="gap:6px;margin-top:4px">${l.status==='candidate'?`<button class="primary" data-ls="${h(l.id)}" data-act="confirm">确认入库</button>`:''}${l.status==='probation'||l.status==='retired'?`<button data-ls="${h(l.id)}" data-act="restore">恢复使用</button>`:''}${l.status!=='retired'?`<button class="ghost" data-ls="${h(l.id)}" data-act="retire">停用</button>`:''}${l.shared?`<span class="ev-tag info" title="${h(l.shared.by)} 于 ${h((l.shared.ts||'').slice(0,16))} 共享">已共享</span><button class="ghost" data-ls="${h(l.id)}" data-act="unshare">收回共享</button>`:l.status==='active'?`<button class="ghost" data-lshare="${h(l.id)}">共享给其他项目</button>`:''}<details style="flex:1"><summary class="sub">修改</summary><div style="display:flex;flex-direction:column;gap:4px;margin-top:6px">${LF.map(([k,lb])=>`<textarea data-lf="${h(l.id)}" data-k="${k}" placeholder="${lb}" style="min-height:38px">${h(l[k]||'')}</textarea>`).join('')}<div><button data-lsave="${h(l.id)}">保存</button></div></div></details></div></div>`}).join(''):'<div class="sub">还没有。验收不通过、自动提交后有人又改过的工单会直接留下经验；带证据通过验收的工单会留一条待确认的做法，确认后才用。</div>';
  const a=d.alerts,url=location.origin+a.path;
  const ast=!a.configured?'<span class="ev-tag mute">未开启</span>':a.ready?'<span class="ev-tag ok">已就绪</span>':`<span class="ev-tag warn">缺环境变量 ${h(a.key_env)}</span>`;
  const at=a.tickets.length?a.tickets.map(t=>`<a class="drow" href="#/t/${h(t.key)}"><span class="grow"><b>${h(t.key)}</b> ${h(t.title)}<span class="sub">${h(t.source||'告警')} · 触发 ${t.count} 次 · ${ago(t.created)}</span></span>${stPill(t.status)}</a>`).join(''):'<div class="sub">还没有告警开的单</div>';
  $('#main').innerHTML=pageHead('闭环改进','验收结果变成经验卡，在用的写进之后相近工单的提示词，并记下用了以后有没有帮上忙；验收通过的自动改动成为评测用例，换模型或改提示词后回放打分；告警和报错日志自动开单。')+
  `<div class="grid4" style="margin-bottom:16px">${[[d.cases.length,'评测用例'],[last?pc(last.recall):'—','最近一次找全率'],[lsum.active||0,'在用经验'],[a.tickets.length,'告警开的单']].map(([n,l])=>`<div class="card kpi"><div class="l">${l}</div><div class="n">${n}</div></div>`).join('')}</div>
  <div class="grid2"><div style="display:flex;flex-direction:column;gap:16px;min-width:0">
   <div class="card"><div class="hdr" style="margin-bottom:8px"><h2 class="grow" style="margin:0">评测集回放</h2><select id="evAg" aria-label="智能体">${agentOptions()}</select><button class="primary" id="evGo" ${d.running||!d.cases.length?'disabled':''}>${d.running?'<span class="spin"></span> 回放中':'回放全部用例'}</button></div>
     <div class="sub" style="margin-bottom:8px">每个用例回到当初改动之前的代码，让智能体照真实工单起草修改方案，对照实际改过的文件打分。找全率：该改的文件列出了几成；准确率：列出的文件有几成是真该改的。</div>${bt}</div>
   <div class="card"><h2>用例 · ${d.cases.length}</h2>${cs}
     <details style="margin-top:10px"><summary>手动添加用例</summary><div style="display:flex;flex-direction:column;gap:6px;margin-top:8px"><input id="ecT" placeholder="标题（像工单标题一样写）"><textarea id="ecB" placeholder="描述" style="min-height:60px"></textarea><input id="ecF" placeholder="该改的文件，逗号或空格分隔，相对项目根目录"><input id="ecS" placeholder="起点提交（可空：用当前代码）"><div><button id="ecAdd">添加</button></div></div></details>
     <details style="margin-top:10px"><summary>从历史工单生成用例</summary><div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">
       <div class="sub">从禅道、Jira 或 GitHub 导入的、已经关闭的工单里，找提交信息写了工单号（如 TOG-12、bug#123）的修复提交：回到修复之前的代码，只给当时写的标题和描述，拿修复实际改过的文件打分。找不到提交的单直接跳过，不按时间猜。</div>
       <div class="row" style="gap:6px;flex-wrap:wrap"><button id="hiIm">先导入提交里提到的已关闭工单</button><span class="sub">从已接入的工单系统（禅道、Jira、GitHub、GitLab）按提交信息里的单号拉取；GitHub 上合并请求关掉的 issue 也算。</span></div><div id="hiImOut"></div>
       <div class="row" style="gap:6px;flex-wrap:wrap"><label class="sub">关闭时间 <input type="date" id="hiS"></label><label class="sub">到 <input type="date" id="hiU"></label><button id="hiGo">预览</button></div>
       <div id="hiOut"></div></div></details></div></div>
   <div style="display:flex;flex-direction:column;gap:16px;min-width:0">
   <div class="card"><h2>经验库 <span class="sub" style="font-weight:400">退回后自动重改最多 ${d.refix||0} 次</span></h2>
     ${(d.shared_in||[]).length?(()=>{const nt=d.shared_in.filter(x=>x.taken).length;return `<details style="margin-bottom:8px"><summary class="sub">其他项目共享来的经验 ${d.shared_in.length} 条，本项目引入了 ${nt} 条（引入的才会在相近时放 1 条进提示词）</summary><div class="sub" style="margin:4px 0 6px;white-space:normal">这些是别的项目的人写的，已脱敏。读过、觉得适用再引入；它在本项目跟着失败多于通过时会自动不再使用。</div>${d.shared_in.map(x=>`<div class="fact" style="flex-direction:column;align-items:stretch"><div class="row" style="gap:8px"><span class="grow"><b>${h(x.id)}</b> ${h(x.title)}</span>${x.here&&x.here.used?`<span class="sub">本项目用过 ${x.here.used} 次，通过 ${x.here.passed} 次</span>`:''}${x.taken?`<span class="ev-tag info">已引入</span><button class="ghost" data-ltake="${h(x.id)}" data-act="untake">不再引入</button>`:`<button data-ltake="${h(x.id)}" data-act="take">引入本项目</button>`}</div>${LF.filter(([k])=>x[k]).map(([k,lb])=>`<div class="sub" style="white-space:normal"><b style="font-size:inherit">${lb}：</b>${h(x[k])}</div>`).join('')}</div>`).join('')}</details>`})():''}
     ${(()=>{const im=d.impact||{},c=im.carried||{},hd=im.held||{},no=im.none||{},pr=x=>x.rate==null?`${x.n} 张`:`${pc(x.rate)}（${x.n} 张）`;return `<div class="imp"><div class="row" style="gap:8px;align-items:baseline"><b class="grow">经验有没有用</b><label class="sub" title="对所有项目生效">对照组（全平台）<select id="hoSel">${[[0,'关'],[0.1,'10%'],[0.2,'20%']].concat([0,0.1,0.2].some(v=>Math.abs((im.holdout||0)-v)<1e-9)?[]:[[im.holdout,Math.round(im.holdout*100)+'%']]).map(([v,lb])=>`<option value="${v}"${Math.abs((im.holdout||0)-v)<1e-9?' selected':''}>${lb}</option>`).join('')}</select></label></div>
       <div class="impg"><div><span class="sub">带经验</span><b>${pr(c)}</b></div><div><span class="sub">对照（相近但没放）</span><b>${im.holdout||hd.n?pr(hd):'未开'}</b></div><div><span class="sub">没有相近经验</span><b>${pr(no)}</b></div></div>
       <div class="sub" style="white-space:normal">${h(im.verdict||'')}。比的是第一次验收就通过的比例${im.since?'，从 '+h(im.since.slice(0,10))+' 开对照组起算':''}。${im.holdout?'':'打开对照组后，有相近经验的工单里会按比例固定留一部分不放经验，这样两组问题相近，差别才算经验的作用。'}</div></div>`})()}
     <div class="sub" style="margin-bottom:8px">在用 ${lsum.active||0} · 待确认 ${lsum.candidate||0} · 暂停 ${lsum.probation||0} · 停用 ${lsum.retired||0}${lsum.pass_rate!=null?` · 用过的经验，之后验收通过率 ${pc(lsum.pass_rate)}`:''}。只有"在用"的会放进相近工单的提示词，每次最多 3 条；跟着失败的次数多于通过的，会自动暂停等人看。</div>${ls}</div>
   <div class="card"><div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">告警自动开单</h2>${ast}</div>
     <div class="sub" style="margin-bottom:6px">监控（Alertmanager、SkyWalking、日志平台等）POST 到 <span class="key">${h(url)}</span>，带 <span class="key">Authorization: Bearer 密钥</span>。同一告警只累计次数，堆栈会对到项目代码，开单后直接进入自动处理。${a.configured?'':'在数据目录的 alerts.json 里写 {"'+h(S.proj)+'":{"key_env":"环境变量名"}} 开启。'}</div>
     <textarea id="alT" placeholder="也可以把告警或报错日志（含堆栈）贴在这里直接开单" style="min-height:70px"></textarea><div class="row" style="margin:6px 0 8px"><button id="alGo">贴入开单</button></div>${at}</div></div></div>`;
  const lsPost=async(id,body)=>{try{await post('/api/projects/'+encodeURIComponent(S.proj)+'/lessons/'+encodeURIComponent(id),body);vLearn()}catch(e){toast(e.message)}};
  const ho=$('#hoSel');if(ho)ho.onchange=async()=>{try{await post('/api/learn/holdout',{rate:+ho.value});toast(+ho.value?'对照组已打开：'+Math.round(+ho.value*100)+'% 有相近经验的工单不放经验':'对照组已关闭');vLearn()}catch(e){toast(e.message)}};
  document.querySelectorAll('[data-ltake]').forEach(b=>b.onclick=()=>lsPost(b.dataset.ltake,{action:b.dataset.act}));
  document.querySelectorAll('[data-ls]').forEach(b=>b.onclick=()=>{const act=b.dataset.act;if(act==='retire')prompt2('为什么停用经验 '+b.dataset.ls+'？','',why=>{if(why.trim())lsPost(b.dataset.ls,{action:act,why});else toast('停用要写原因')});else lsPost(b.dataset.ls,{action:act})});
  // sharing shows exactly what leaves the project: the redacted copy, editable, and nothing about the code
  document.querySelectorAll('[data-lshare]').forEach(b=>b.onclick=async()=>{const id=b.dataset.lshare;let pv;try{pv=await get('/api/projects/'+encodeURIComponent(S.proj)+'/lessons/'+encodeURIComponent(id)+'/share')}catch(e){return toast(e.message)}
    modal(`<h2>共享经验 ${h(id)} 给其他项目</h2><div class="hint" style="margin-bottom:10px">其他项目（可能是别的甲方）的智能体会看到下面这些文字，只当思路参考。不会带出代码、文件名、工单内容。常见的密码、密钥、连接串、链接、IP、主机名、邮箱、手机号、证件号、长号码、目录和本项目名称已尽量替换成［…］，但自动替换会有漏网的。请逐字读一遍，把客户名、系统名、人名和任何没替换掉的敏感内容改掉。别的项目要有人点"引入"才会用它。</div>
     <div class="form"><label>标题<input class="full" id="shT" value="${h(pv.title)}"></label>${LF.filter(([k])=>pv.fields[k]!=null).map(([k,lb])=>`<label>${lb}<textarea class="full" data-shf="${k}" style="min-height:52px">${h(pv.fields[k])}</textarea></label>`).join('')}
     <div class="row" style="gap:8px"><button class="primary" id="shGo">确认共享</button><span class="sub">随时可以收回。</span></div></div>`);
    $('#shGo').onclick=async()=>{const f={};document.querySelectorAll('[data-shf]').forEach(t=>f[t.dataset.shf]=t.value);try{await post('/api/projects/'+encodeURIComponent(S.proj)+'/lessons/'+encodeURIComponent(id),{action:'share',title:$('#shT').value,fields:f});closeModal();toast('已共享');vLearn()}catch(e){toast(e.message)}}});
  document.querySelectorAll('[data-lsave]').forEach(b=>b.onclick=()=>{const f={};document.querySelectorAll('[data-lf="'+CSS.escape(b.dataset.lsave)+'"]').forEach(t=>f[t.dataset.k]=t.value);lsPost(b.dataset.lsave,{fields:f})});
  $('#evGo').onclick=async()=>{try{const r=await post('/api/projects/'+encodeURIComponent(S.proj)+'/evals/run',{agent:$('#evAg').value});toast('开始回放 '+r.cases+' 个用例');vLearn()}catch(e){toast(e.message)}};
  document.querySelectorAll('[data-rm]').forEach(b=>b.onclick=async()=>{try{await post('/api/projects/'+encodeURIComponent(S.proj)+'/evals/cases',{remove:b.dataset.rm});vLearn()}catch(e){toast(e.message)}});
  const hist=async(apply)=>{const o=$('#hiOut');try{const fl=$('#hiF')?$('#hiF').checked:false;
    const r=await post('/api/projects/'+encodeURIComponent(S.proj)+'/evals/history',{since:$('#hiS').value,until:$('#hiU').value,apply,flagged:fl});
    if(apply){toast('已入库 '+r.added.length+' 个用例');vLearn();return}
    const li=x=>`<div class="fact" style="flex-direction:column;align-items:stretch"><div class="row" style="gap:8px"><a href="#/t/${h(x.ticket)}">${h(x.external)}</a><span class="grow">${h(x.title)}</span>${x.why?`<span class="ev-tag warn">${h(x.why)}</span>`:''}<span class="sub">${h(x.done)}</span></div><div class="sub key" style="white-space:normal;overflow-wrap:anywhere">${x.gold.slice(0,8).map(h).join('、')}${x.gold.length>8?' 等 '+x.gold.length+' 个':''}</div></div>`;
    o.innerHTML=`<div class="sub" style="margin:4px 0">已关闭的导入工单 ${r.tickets} 张：能找到修复提交 <b>${r.matched.length+r.flagged.length}</b> 张，其中 ${r.flagged.length} 张太大或只改配置/SQL（默认不入库）；找不到提交 ${r.unmatched} 张${r.existing?'；已在用例里 '+r.existing+' 张':''}。</div>`+
      r.matched.slice(0,30).map(li).join('')+(r.matched.length>30?`<div class="sub">还有 ${r.matched.length-30} 张</div>`:'')+r.flagged.slice(0,10).map(li).join('')+
      (r.matched.length+r.flagged.length?`<div class="row" style="gap:8px;margin-top:6px">${r.flagged.length?'<label class="sub"><input type="checkbox" id="hiF"> 也收入标记的</label>':''}<button class="primary" id="hiAp">入库 ${r.matched.length} 个用例</button></div>`:'');
    const ap=$('#hiAp');if(ap){ap.onclick=()=>hist(true);const f=$('#hiF');if(f)f.onchange=()=>{ap.textContent='入库 '+(r.matched.length+(f.checked?r.flagged.length:0))+' 个用例'}}}catch(e){toast(e.message)}};
  $('#hiGo').onclick=()=>hist(false);
  $('#hiIm').onclick=async()=>{const b=$('#hiIm'),o=$('#hiImOut');b.disabled=true;b.innerHTML='<span class="spin"></span> 导入中';try{
    const r=await post('/api/projects/'+encodeURIComponent(S.proj)+'/evals/history/import',{since:$('#hiS').value,until:$('#hiU').value});
    o.innerHTML=`<div class="sub" style="margin:4px 0">提交里提到、还没查过的单号 ${r.refs} 个：查了 ${r.checked} 个，导入已关闭工单 <b>${r.imported.length}</b> 张${r.open?'，还开着的 '+r.open+' 张没导':''}${r.failed?'，查不到 '+r.failed+' 个':''}${r.left?'，剩 '+r.left+' 个下次接着查':''}。${r.stopped?'<span class="ev-tag warn">'+h(r.stopped)+'</span>':''}</div>`}
    catch(e){toast(e.message)}finally{b.disabled=false;b.textContent='先导入提交里提到的已关闭工单'}};
  $('#ecAdd').onclick=async()=>{try{const c=await post('/api/projects/'+encodeURIComponent(S.proj)+'/evals/cases',{title:$('#ecT').value,body:$('#ecB').value,gold:$('#ecF').value,base:$('#ecS').value});toast('已添加用例 '+c.id);vLearn()}catch(e){toast(e.message)}};
  $('#alGo').onclick=async()=>{try{const r=await post('/api/projects/'+encodeURIComponent(S.proj)+'/alerts',{text:$('#alT').value});toast(r.opened.length?'已开单 '+r.opened.join('、'):r.updated.length?'已有同一告警的单 '+r.updated.join('、')+'，累计了次数':'没有可开单的内容');vLearn()}catch(e){toast(e.message)}};
  if(d.running)poll(()=>{if(location.hash==='#/learn')get('/api/projects/'+encodeURIComponent(S.proj)+'/learn').then(n=>{if(!n.running)vLearn()})},5000)}

// ---------- full-project analysis: agents write the knowledge base page by page
async function survey(){
  const key=S.proj;let v;try{v=await get(`/api/projects/${key}/survey`)}catch(e){return}
  const el=$('#svy');if(!el||S.proj!==key)return;
  const busy=['starting','building','running','stopping'].includes(v.state);
  // while it runs: the scope it was started with; otherwise what the person picked here, then the last run's
  let scope=(busy?v.scope:(S.svScope||v.scope))||'top';
  const cov=v.coverage||{},bk=cov.by_kind||{};const sum=(ks,sts)=>ks.reduce((a,k)=>a+sts.reduce((b,x)=>b+((bk[k]||{})[x]||0),0),0);
  const kinds=scope==='top'?['dom','index']:['flow','tbl','mod','dom','index'];
  const done=sum(kinds,['待确认','已确认']),todo=sum(kinds,['未分析','过期']),tot=done+todo;
  const topTodo=sum(['dom','index'],['未分析','过期']),allTodo=sum(['flow','tbl','mod','dom','index'],['未分析','过期']);
  const pct=tot?Math.round(done/tot*100):0;
  const stName=v.state==='done'&&v.hit_limit&&todo?'本次上限已到，还有 '+todo+' 页':{idle:'',starting:'准备中',building:'构建知识图谱',running:'分析中',stopping:'正在停止',done:'已完成',stopped:'已停止',failed:'中断'}[v.state]||v.state;
  const prog=tot?`<div class="row" style="align-items:center;gap:10px;margin:10px 0 4px"><div class="stack grow"><div style="width:${pct}%;background:var(--ok)"></div></div><span class="sub" style="font-variant-numeric:tabular-nums">已写 ${done} / ${tot} 页（${pct}%）</span></div>`:'';
  let html=`<div class="card"><div class="hdr" style="margin-bottom:4px"><h2 class="grow" style="margin:0">全项目分析</h2>${v.state!=='idle'?`<span class="tag">${h(stName)}</span>`:''}${busy?'<span class="spin"></span>':''}</div>
   <div class="sub">让本机的智能体逐页阅读代码、撰写知识页，每页都要通过平台校验（结论带 文件:行号 证据），写好的是“待确认”，由人确认。业务流和表的“事实部分”是工具自动解析的，不花 token，工单分析随时可用。</div>${prog}`;
  if(busy){
    html+=`<div class="sub" style="margin:6px 0">${scope==='top'?'业务地图':'全部页面'} · ${h(v.agent)}${v.model?' · '+h(v.model):''} · 并行 ${v.parallel}${v.limit?' · 本次最多 '+v.limit+' 页':''} · 已写成 ${v.ok} 页${v.failed?'，未完成 '+v.failed+' 页':''} · ${h(v.author||'')} 开始于 ${ago(v.started)}</div>`;
    if(v.active.length)html+='<div style="margin:6px 0">'+v.active.map(a=>`<div class="svr"><span class="spin"></span><span class="key">${h(a.worker)}</span>正在写 ${(a.pages||[a.page]).map(x=>`<a href="#/kb/${encodeURIComponent(x)}">${h(x)}</a>`).join('、')}${a.run?` · <a href="javascript:void 0" onclick="showRun(${a.run})">看过程</a>`:''}</div>`).join('')+'</div>';
    html+=v.state==='stopping'?'':`<button class="danger" id="svStop">停止（写完手头的页面）</button>`;
  }else{
    const ags=S.meta.agents;const pick=(ags.find(a=>a.name==='codex'&&a.available)||ags.find(a=>a.available)||ags[0]||{}).name;
    html+=`<div class="row" style="align-items:center;gap:10px;margin-top:10px">
     <label class="sub">范围 <select id="svSc"><option value="top" ${scope==='top'?'selected':''}>业务地图：只写业务域和总览（${topTodo} 页）</option><option value="all" ${scope==='all'?'selected':''}>全部页面（${allTodo} 页，token 消耗大）</option></select></label>
     <label class="sub">智能体 <select id="svAg">${ags.map(a=>`<option value="${h(a.name)}" ${a.name===pick?'selected':''}>${h(a.title)}${a.available?'':'（本机未安装）'}</option>`).join('')}</select></label>
     <label class="sub">模型 <span id="svMw"></span></label>
     <label class="sub">并行 <select id="svPar">${[1,2,3,4].map(n=>`<option ${n===2?'selected':''}>${n}</option>`).join('')}</select></label>
     <label class="sub">本次最多 <select id="svLim">${[[5,'5 页（试跑）'],[20,'20 页'],[50,'50 页'],[0,'全部']].map(([n,l])=>`<option value="${n}" ${n===5&&!done?'selected':n===0&&done?'selected':''}>${l}</option>`).join('')}</select></label>
     <button class="primary" id="svGo">${done?'继续全项目分析':'开始全项目分析'}</button></div>
     <div class="sub" style="margin-top:6px">${scope==='top'?'业务地图模式直接用工具解析出的业务流事实写业务域，最后写系统总览，花费约为全写的一小部分。业务流细节靠工单“分析后补写”逐步补齐。':'全写会逐个业务流、表撰写，页数多时 token 消耗很大。'}第一次建议先试跑 5 页看质量。</div>`;
  }
  if(v.finished&&v.finished.length)html+=`<details style="margin-top:8px" ${busy?'open':''}><summary class="sub">本次结果：写成 ${v.ok} 页${v.failed?'，未完成 '+v.failed+' 页':''}</summary>`+v.finished.slice(0,40).map(f=>`<div class="svr"><span>${f.ok?'✓':'✗'}</span><a href="#/kb/${encodeURIComponent(f.page)}">${h(f.title||f.page)}</a>${f.ok?'':`<span class="sub">${h(f.why||'')}</span>`}${f.run?` · <a href="javascript:void 0" onclick="showRun(${f.run})">运行 #${f.run}</a>`:''}</div>`).join('')+'</details>';
  if(v.log&&v.log.length)html+=`<details style="margin-top:6px"><summary class="sub">进度日志</summary><pre class="log">${h(v.log.join('\n'))}</pre></details>`;
  const open=[...el.querySelectorAll('details')].map(d=>d.open);
  el.innerHTML=html+'</div>';el.querySelectorAll('details').forEach((d,i)=>{if(open[i]!==undefined)d.open=open[i]});
  if($('#svSc'))$('#svSc').onchange=e=>{S.svScope=e.target.value;survey()};
  if($('#svMw')){const pm=()=>{$('#svMw').innerHTML=modelSel('svMd',$('#svAg').value,'kb');bindModel('svMd')};pm();$('#svAg').onchange=pm}
  if($('#svGo'))$('#svGo').onclick=async()=>{try{await post(`/api/projects/${key}/survey`,{scope:$('#svSc').value,agent:$('#svAg').value,model:$('#svMd').value,parallel:+$('#svPar').value,limit:+$('#svLim').value});toast('已开始全项目分析');survey()}catch(e){toast(e.message)}};
  if($('#svStop'))$('#svStop').onclick=async()=>{try{await post(`/api/projects/${key}/survey/stop`);survey()}catch(e){toast(e.message)}};
  stopPolls('survey');
  if(busy)poll(()=>{if(!$('#svy'))return stopPolls('survey');survey()},3000,'survey');
  else if(S.svLive===key){S.svLive='';if(v.ok&&location.hash.startsWith('#/kb'))setTimeout(()=>vKb(),300)}
  if(busy)S.svLive=key}
async function vInt(){
  const ints=await get(`/api/projects/${S.proj}/integrations`);const iss=ints.filter(i=>i.capabilities.includes('issues'));
  $('#main').innerHTML=`<div class="hdr"><h1 class="grow">外部系统</h1></div>
  <div class="grid2"><div class="card"><h2>已接入</h2>${ints.length?`<table class="t"><tr><th>名称</th><th>类型</th><th>能力</th></tr>`+ints.map(i=>`<tr><td>${h(i.name)}<div class="sub">${h(i.url)}</div></td><td>${h(i.title)}</td><td>${i.capabilities.map(c=>`<span class="tag">${h(c)}</span>`).join(' ')}</td></tr>`).join('')+'</table>':'<div class="sub">还没有接入外部系统。</div>'}
   <div class="hint" style="margin-top:12px">接入在项目目录用命令配置，例如 <code>tmh int add jira --url https://jira.example.com --token-env JIRA_TOKEN</code> 或 <code>tmh int add zentao …</code>。凭据只从环境变量读，不写进文件。启动平台的终端里要有这些环境变量。</div></div>
  <div class="card"><h2>导入工单</h2>${iss.length?`<div class="form"><label>来源 <select id="iv">${iss.map(i=>`<option>${h(i.name)}</option>`).join('')}</select></label>
   <label>外部工单号（多个用逗号或空格分开）<input class="full" id="ik" placeholder="例如 OA-123, OA-124"></label><label>或搜索条件（Jira 用 JQL，禅道用关键词）<input class="full" id="iq"></label>
   <div><button class="primary" id="ib">导入</button></div><div class="sub">已导入过的工单只更新外部状态，不会重复创建。导入后可在工单页把评论同步回去。</div></div>`:'<div class="sub">接入 Jira、禅道等能提供工单的系统后，可以在这里导入。</div>'}</div></div>
  <div class="card" id="pinC" style="margin-top:14px"><h2>框选定位</h2><div class="sub">加载中…</div></div>`;
  pinCard();
  if($('#ib'))$('#ib').onclick=async()=>{try{const r=await post(`/api/projects/${S.proj}/import`,{via:$('#iv').value,keys:$('#ik').value,query:$('#iq').value});toast('导入 '+r.imported.length+' 张：'+r.imported.join('、'),5000);location.hash='#/tickets'}catch(e){toast(e.message,6000)}}}
// ---------- box-select on the client's page: a bookmarklet posts what is in the box, the platform finds the code
async function pinCard(bm){const el=$('#pinC');if(!el)return;let d;try{d=await get(`/api/projects/${S.proj}/pins`)}catch(e){el.innerHTML='<h2>框选定位</h2><div class="sub">'+h(e.message)+'</div>';return}
  const L=x=>(x.found.layer1.length?'源码标记 ':'')+(x.found.layer2.length?x.found.layer2.length+' 个候选文件 ':'')+(x.found.layer3.length?x.found.layer3.length+' 个后端入口':'')||'没找到，转人工';
  el.innerHTML=`<h2>框选定位</h2><div class="sub">把书签拖到浏览器书签栏，在业务系统的页面上点它，拖一个框圈住有问题的地方，说一句话。框里的文字、字段和页面发出的接口会发到这里，平台按知识库找到代码位置：带源码标记的精确到行，老模板经标签文件反查，接口对到业务流和表。</div>
   <div class="row" style="gap:8px;margin-top:8px;align-items:center">${bm?`<a class="btn primary" href="${h(bm)}" onclick="return false" draggable="true">框选报问题 · ${h(S.proj)}</a><span class="sub">拖到书签栏；旧书签已失效</span>`
     :`<button id="pinT">${d.has_token?'重新生成书签（旧的会失效）':'生成书签'}</button>`}</div>
   <div style="margin-top:10px">${d.pins.length?d.pins.map(x=>`<div class="flowrow" style="align-items:flex-start"><span class="grow" style="min-width:0"><b>${h(clip(x.capture.note||x.capture.texts.join(' '),50)||'（没写说明）')}</b>
      <div class="sub">${h(clip(x.capture.url,70))} · ${h(x.at.slice(5,16))} · ${h(L(x))}</div>
      <details><summary class="sub">定位结果</summary><pre class="log" style="white-space:pre-wrap">${h(x.summary)}

${h(x.found.basis.join('\n'))}</pre></details></span>
      <button class="ghost pinI" data-id="${h(x.id)}">理清需求并建单</button></div>`).join(''):'<div class="sub">还没有框选记录。</div>'}</div>`;
  if($('#pinT'))$('#pinT').onclick=async()=>{try{const r=await post(`/api/projects/${S.proj}/capture-token`,{base:location.origin});pinCard(r.bookmarklet)}catch(e){toast(e.message,5000)}};
  el.querySelectorAll('.pinI').forEach(b=>b.onclick=()=>{const x=d.pins.find(p=>p.id===b.dataset.id);intakeModal(S.proj,x.capture.note,x)})}
async function pushExt(key,body){
  if(!body.trim()){toast('先在评论框写好要同步的内容');return}
  try{const r=await post(`/api/tickets/${key}/push`,{body,confirm:false});
    modal(`<h2>同步评论到外部工单</h2><div class="sub">将发出的请求（预演，尚未发送）：</div><pre class="diff">${h(JSON.stringify(r.result,null,2))}</pre><button class="primary" id="pc">确认发送</button>`);
    $('#pc').onclick=async()=>{try{await post(`/api/tickets/${key}/push`,{body,confirm:true});closeModal();toast('已同步');vTicket(key)}catch(e){toast(e.message,5000)}}}catch(e){toast(e.message,5000)}}
async function vSettings(){
  $('#main').innerHTML=`<h1>设置</h1><div class="card" id="rdy" style="margin-top:14px"><h2>上线体检</h2><div class="sub">检查中…</div></div><div class="grid2" style="margin-top:14px"><div class="card form"><h2>我</h2><label>名字（写在评论、指派和审阅记录里）<input class="full" id="un" value="${h(S.user)}"></label><div><button class="primary" id="us">保存</button></div></div>
  <div class="card"><h2>智能体</h2>${S.meta.agents.map(a=>`<div class="flowrow"><span>${h(a.title)} <span class="key">${h(a.name)}</span></span><span class="tag">${a.available?'可用':'本机未找到'}</span></div>`).join('')}
  <div class="hint" style="margin-top:10px">平台用本机已安装的 <code>claude</code>（Claude Code）和 <code>codex</code> 命令，沿用它们自己的登录或环境变量。接第三方模型用 <code>tmh agent-config</code> 生成配置。也可以在 <code>${h(S.meta.data_dir)}/agents.json</code> 里加自研智能体：<code>{"my": {"title":"自研","cmd":["my-agent","--dir","{workdir}","{prompt_file}"]}}</code></div></div>
  <div class="card"><h2>项目</h2>${S.projects.map(p=>`<div class="flowrow"><span><b>${h(p.key)}</b> ${h(p.name)}<div class="sub">${h(p.root)}${p.exists?'':'（目录不存在）'}</div></span><span class="sub">${p.open} 张未关闭</span></div>`).join('')}<div style="margin-top:10px"><button onclick="newProject()">＋ 添加项目</button></div></div>
  <div class="card form" id="tbx"><h2>测试机</h2><div class="sub">加载中…</div></div>
  <div class="card"><h2>数据</h2><div class="sub">工单、讨论和运行记录都在 <code>${h(S.meta.data_dir)}/platform.db</code>（SQLite），修改代码用的工作树在 <code>worktrees/</code>。备份这个目录即可。</div></div></div>`;
  $('#us').onclick=()=>{S.user=$('#un').value.trim();try{localStorage.setItem('tmh.user',S.user)}catch(e){}$('#me').textContent='当前用户：'+S.user;toast('已保存')};
  testbox();readiness()}
// ---------- versions that went out: the end of the line a client cares about
async function rels(){const el=$('#rels');if(!el)return;let d;try{d=await get('/api/projects/'+encodeURIComponent(scopeQ())+'/releases')}catch(e){return}
  if(!d.releases.length)return;const r=d.releases.slice(0,3);
  el.innerHTML=`<div class="card rel"><div class="hdr" style="margin-bottom:4px"><h2 class="grow" style="margin:0">最近出的版本</h2><span class="sub">${d.merge==="auto"?"验收通过后自动合并进主干":"自动合并已关闭"}</span></div>${r.map(x=>`<div class="relr"><b class="key">${h(x.project)} ${h(x.version)}</b><span class="grow" style="min-width:0">${x.tickets.map(k=>`<a href="#/t/${h(k.key)}">${h(k.key)}</a> ${h(k.title)}`).join('；')}</span><span class="sub">${ago(x.ts)} · ${h(x.commit)}</span></div>`).join('')}</div>`}
// ---------- 上线体检: the real state of this machine, worst first, each with what to do
async function readiness(){
  const el=$('#rdy');if(!el)return;let r;try{r=await get('/api/readiness')}catch(e){el.innerHTML='<h2>上线体检</h2><div class="sub">'+h(e.message)+'</div>';return}
  const ic={bad:'✗',warn:'!',ok:'✓'};
  el.innerHTML=`<div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">上线体检</h2><span class="tag ${r.counts.bad?'bad':r.counts.warn?'warn':''}">${h(r.summary)}</span><button class="ghost" id="rdyR">重新检查</button></div>
   ${r.items.map(x=>`<div class="rdy ${x.state}"><span class="rdi">${ic[x.state]}</span><div class="grow"><b>${h(x.label)}</b> <span class="sub">${h(x.detail)}</span>${x.fix?`<div class="rdf">${h(x.fix)}${x.link&&x.link!==location.hash?` <a href="${h(x.link)}">去处理</a>`:''}</div>`:''}</div></div>`).join('')}`;
  $('#rdyR').onclick=readiness}
// ---------- the test machine: where the platform builds and tests changes, over SSH with key login
async function testbox(d){
  const el=$('#tbx');if(!el)return;try{d=d||await get('/api/testbox')}catch(e){el.innerHTML='<h2>测试机</h2><div class="sub">'+h(e.message)+'</div>';return}
  const c=d.conf||{},L=d.last;
  const tools=L&&L.tools?Object.entries(L.tools).map(([k,v])=>`<div class="flowrow"><span>${h(k)}</span><span class="tag ${v?'':'warn'}">${v?h(v.slice(0,40)):'没有'}</span></div>`).join(''):'';
  el.innerHTML=`<h2>测试机</h2><div class="sub">改完代码后，平台把改动发到这台机器上编译和测试，结果交回给智能体。只用 SSH 密钥登录，不保存密码。不设置就不跑构建。</div>
   <div class="row" style="margin-top:8px"><label class="grow">地址 <input class="full" id="tbH" placeholder="用户名@地址，或 ~/.ssh/config 里的名字" value="${h(c.host||'')}"></label><label>端口 <input id="tbP" size="6" placeholder="默认" value="${h(c.port?String(c.port):'')}"></label></div>
   <label>工作目录（可不填，Windows 默认 C:/tmh-runner）<input class="full" id="tbD" value="${h(c.dir||'')}"></label>
   <div class="row" style="gap:8px"><button class="primary" id="tbS">保存</button>${c.host?'<button id="tbC">体检</button>':''}</div>
   ${L?`<div style="margin-top:10px">${L.error?`<div class="sub" style="color:var(--bad)">${h(L.error)}</div>`:`<div class="sub">${h(L.os==='windows'?'Windows':'Linux/macOS')} · ${h(L.dir||'')} · ${h(L.at||'')}</div>${tools}`}</div>`:''}
   ${L&&L.missing&&L.missing.length?`<div style="margin-top:8px" id="tbI"><div class="sub">缺 ${h(L.missing.join('、'))}。可以让平台在测试机上下载免安装版，解压到工作目录的 tools 下（不需要管理员权限，不改系统设置）。</div><button id="tbI1">下载安装缺的工具</button></div>`:''}
   ${L&&L.log?`<pre class="log">${h(L.log.join('\n'))}</pre>`:''}`;
  $('#tbS').onclick=async()=>{try{testbox(await post('/api/testbox',{host:$('#tbH').value.trim(),port:+$('#tbP').value||0,dir:$('#tbD').value.trim()}));toast('已保存')}catch(e){toast(e.message,5000)}};
  if($('#tbC'))$('#tbC').onclick=async()=>{$('#tbC').disabled=true;$('#tbC').textContent='体检中…';try{await post('/api/testbox/check',{})}catch(e){toast(e.message,5000)}testbox()};
  if($('#tbI1'))$('#tbI1').onclick=()=>{$('#tbI').innerHTML=`<div class="sub">会在测试机上下载并解压：${h(L.missing.join('、'))}，可能要几分钟到几十分钟。</div><div class="row" style="gap:8px"><button class="primary" id="tbI2">确认下载安装</button><button id="tbI3">取消</button></div>`;
    $('#tbI3').onclick=()=>testbox();
    $('#tbI2').onclick=async()=>{$('#tbI2').disabled=true;$('#tbI2').textContent='正在下载安装…';try{await post('/api/testbox/install',{})}catch(e){toast(e.message,5000)}testbox()}}}
function newProject(){
  modal(`<h2>添加项目</h2><div class="form"><label>项目目录（本机绝对路径）<input class="full" id="pr" placeholder="/Users/me/workspace/together-project"></label>
  <div class="row"><label>代号（工单编号前缀）<input id="pk" placeholder="TOG" size="8"></label><label class="grow">名称 <input class="full" id="pn" placeholder="together 协同办公"></label></div>
  <div><button class="primary" id="pa">添加</button></div><div class="sub">目录里已有 .tmh/（运行过 tmh kb build）就能用上知识库和业务全景。</div></div>`);
  $('#pr').oninput=()=>{const n=$('#pr').value.split('/').filter(Boolean).pop()||'';if(!$('#pk').dataset.t)$('#pk').value=n.replace(/[^A-Za-z0-9]/g,'').slice(0,3).toUpperCase()};$('#pk').oninput=()=>$('#pk').dataset.t=1;
  $('#pa').onclick=async()=>{try{const p=await post('/api/projects',{root:$('#pr').value.trim(),key:$('#pk').value.trim(),name:$('#pn').value.trim()});S.proj=p.key;try{localStorage.setItem('tmh.proj',p.key)}catch(e){}closeModal();await loadProjects();location.hash='#/';render()}catch(e){toast(e.message,5000)}}}

// ---------- closed-loop assistant (right drawer)
// ---------- maintenance assistant: one session at a time; each session keeps its own messages, draft and context
const KIND={consult:'项目咨询',matter:'项目咨询',ticket:'关联工单'};
const ls={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{v==null?localStorage.removeItem(k):localStorage.setItem(k,v)}catch(e){}}};
const A={
  open:true,mode:'evidence',sid:null,sess:null,msgs:[],list:[],matters:[],hist:false,q:'',offer:null,view:null,timer:null,wall:null,running:{},pending:null,
  get ticket(){return this.sess&&this.sess.ticket?Object.assign({id:this.sess.ticket_id},this.sess.ticket):null},
  init(){
    this.open=ls.get('tmh.ast')==='1';const m=ls.get('tmh.astMode');this.mode=m==='draft'?'draft':'evidence';  // folded until asked for
    this.paint();this.reset()},
  async reset(){this.saveDraft();this.sid=null;this.sess=null;this.msgs=[];this.offer=null;this.hist=false;
    if(!S.proj)return;await this.loadList();const want=+ls.get('tmh.sess.'+S.proj);
    const s=this.list.find(x=>x.id===want&&!x.archived_at)||this.list.find(x=>!x.archived_at);
    if(s)await this.switchTo(s.id,true);else this.paint()},
  toggle(on){const wasOpen=this.open;this.open=on===undefined?!this.open:on;ls.set('tmh.ast',this.open?'1':'0');this.paint();if(this.open&&this.sid)this.load();
    if(wasOpen&&!this.open){if(!$('#modal').hidden)$('.mbox').focus();else $('#astToggle').focus()}},
  focus(){setTimeout(()=>{const t=$('#aq');if(t)t.focus()},50)},
  saveDraft(){const t=$('#aq');if(this.sid&&t)ls.set('tmh.draft.'+this.sid,t.value||null)},
  async loadList(){if(!S.proj)return;try{const r=await get('/api/projects/'+S.proj+'/sessions');this.list=r.sessions;this.matters=r.matters;this.checkDone()}catch(e){}},
  async switchTo(sid,quiet){
    this.saveDraft();this.sid=sid;ls.set('tmh.sess.'+S.proj,String(sid));this.hist=false;this.pending=null;
    const t=$('#aq');if(t)t.value=ls.get('tmh.draft.'+sid)||'';
    await this.load();if(this.view&&this.sess&&(!this.sess.ticket_id||this.sess.ticket_id!==this.view.id))this.offer=this.view;else this.offer=null;
    this.paint();if(!quiet)this.focus()},
  // opening a ticket never rebinds the current session silently: offer the ticket's session instead
  setTicket(t){this.view=t;if(!t){this.offer=null;this.paintHead();return}
    if(!this.sid){this.enterTicket(t);return}
    this.offer=(this.sess&&this.sess.ticket_id===t.id)?null:t;this.paintHead();this.paintSugg()},
  async enterTicket(t){try{const s=await post('/api/projects/'+S.proj+'/sessions',{kind:'ticket',ticket:t.key});await this.loadList();await this.switchTo(s.id,true)}catch(e){toast(e.message)}},
  async newSession(kind,extra){
    try{const s=await post('/api/projects/'+S.proj+'/sessions',Object.assign({kind},extra||{}));await this.loadList();await this.switchTo(s.id);toast('已新建会话：'+s.title)}catch(e){toast(e.message)}},
  async load(){
    if(!this.sid)return;
    try{const r=await get('/api/sessions/'+this.sid);if(r.session.id!==this.sid)return;this.sess=r.session;this.msgs=r.messages;
      if(r.balance!==undefined)$('#ptsN').textContent=r.balance.toLocaleString();this.paintHead();this.paintMsgs();this.watch()}
    catch(e){if(/没有这个会话/.test(e.message)){this.sid=null;this.sess=null;ls.set('tmh.sess.'+S.proj,null);this.paint()}}},
  watch(){clearTimeout(this.timer);if(this.msgs.some(m=>m.role==='assistant'&&(m.data||{}).state==='running'))this.timer=setTimeout(()=>this.load(),1500);
    clearTimeout(this.wall);if(this.list.some(s=>s.running))this.wall=setTimeout(()=>this.loadList(),4000)},
  // an answer that finishes in another session is announced by that session's name; clicking goes there
  checkDone(){const now={};this.list.forEach(s=>{now[s.id]=s.running});
    Object.keys(this.running).forEach(id=>{if(this.running[id]&&!now[id]&&+id!==this.sid){const s=this.list.find(x=>x.id===+id);if(s)toastAct(`「${s.title}」的回答好了`,'查看',()=>{this.toggle(true);this.switchTo(s.id)})}});
    this.running=now;clearTimeout(this.wall);if(this.list.some(s=>s.running))this.wall=setTimeout(()=>this.loadList(),4000)},
  paint(){$('#ast').hidden=!this.open;document.body.classList.toggle('ast-on',this.open);$('#astOpen').hidden=this.open;$('#astToggle').setAttribute('aria-expanded',String(this.open));syncDialogScope();if(this.open){this.paintHead();this.paintMsgs();this.paintSugg();this.paintFoot()}},
  chips(s){if(!s)return'';const c=[`<span class="tag on">${h(S.proj)}</span>`];
    if(s.ticket)c.push(`<a class="tag" href="#/t/${h(s.ticket.key)}" title="${h(s.ticket.title)}">工单 ${h(s.ticket.key)}</a>`);
    if(!s.ticket)c.push(`<span class="tag">${KIND[s.kind]||'会话'}</span>`);
    if(s.archived_at)c.push('<span class="tag warn">已归档</span>');return c.join('')},
  // one slim header: the session (click to switch or jump), new, more, close. The page context and any
  // "you opened another ticket" hint share one line below it; agent/model live in the ⋯ menu.
  paintHead(){
    if(!this.open)return;const s=this.sess;
    const ags=(S.meta&&S.meta.agents)||[];const pick=(ags.find(a=>a.name==='codex'&&a.available)||ags.find(a=>a.available)||ags[0]||{}).name;const saved=ls.get('tmh.astAgent')||'';
    $('#astHead').innerHTML=`<div class="t"><button class="stitle ${this.hist?'on':''}" id="astHist" aria-expanded="${this.hist}" title="切换会话、跳转页面">${s?`<span class="nm">${h(s.title)}</span>`:'<span class="nm">AI 助手</span>'}${s&&s.archived_at?'<span class="tag warn">已归档</span>':''}<span class="car">▾</span></button><span class="grow"></span>
      <div class="nw"><button class="hbtn" id="astNew" title="新会话" aria-label="新会话">＋</button><div class="menu" id="astMenu" hidden>
       <button data-k="consult"><b>项目咨询</b><span>了解业务、查代码、解释依据</span></button>
       ${this.view?`<button data-t="1"><b>${h(this.view.key)} 处理会话</b><span>当前打开的工单</span></button>`:''}</div></div>
      <div class="nw"><button class="hbtn" id="astMore" title="更多" aria-label="更多">⋯</button><div class="menu" id="astMoreM" hidden>
       ${s?`<button data-a="ren"><b>重命名会话</b></button><button data-a="arc"><b>${s.archived_at?'恢复会话':'归档会话'}</b><span>消息都保留</span></button>`:''}
       <div class="mh">“深入分析”用哪个本机智能体</div><div class="mset"><select id="astAgent" aria-label="本机智能体">${ags.map(a=>`<option value="${h(a.name)}" ${a.name===(saved||pick)?'selected':''}>${h(a.title)}${a.available?'':'（未安装）'}</option>`).join('')}</select>${modelSel('astModel',saved||pick,'ask')}</div></div></div>
      <button class="ghost" id="astClose" title="收起（Ctrl+K）" aria-label="收起助手">✕</button></div>
     <div class="ctx" id="astCtx"></div>`;
    $('#astClose').onclick=()=>this.toggle(false);
    $('#astHist').onclick=()=>{this.hist=!this.hist;if(this.hist)this.loadList().then(()=>this.paintMsgs());this.paintHead();this.paintMsgs()};
    const menu=(btn,m)=>{$(btn).onclick=e=>{e.stopPropagation();document.querySelectorAll('#astHead .menu').forEach(x=>{if(x!==$(m))x.hidden=true});$(m).hidden=!$(m).hidden}};
    menu('#astNew','#astMenu');menu('#astMore','#astMoreM');$('#astMoreM').onclick=e=>e.stopPropagation();
    document.querySelectorAll('#astMenu button').forEach(b=>b.onclick=()=>{$('#astMenu').hidden=true;
      if(b.dataset.k==='consult')prompt2('新的项目咨询会话','项目咨询',v=>this.newSession('consult',{title:v}));
      else if(b.dataset.t)post('/api/projects/'+S.proj+'/sessions',{kind:'ticket',ticket:this.view.key}).then(async s=>{await this.loadList();this.switchTo(s.id)})});
    document.querySelectorAll('#astMoreM button[data-a]').forEach(b=>b.onclick=async()=>{$('#astMoreM').hidden=true;
      if(b.dataset.a==='ren')prompt2('重命名会话',s.title,async v=>{try{await post('/api/sessions/'+s.id,{title:v});await this.loadList();this.load()}catch(e){toast(e.message)}});
      else{try{await post('/api/sessions/'+s.id,{archived:!s.archived_at});toast(s.archived_at?'已恢复，可以继续发送':'已归档：消息都保留，正在跑的回答也不会停');await this.loadList();this.load()}catch(e){toast(e.message)}}});
    bindModel('astModel');
    $('#astAgent').onchange=e=>{ls.set('tmh.astAgent',e.target.value);this.paintHead();$('#astMoreM').hidden=false};
    this.paintCtx();this.paintMode()},
  setMode(m){this.mode=m||(this.mode==='draft'?'evidence':'draft');ls.set('tmh.astMode',this.mode);this.paintMode();this.paintFoot()},
  paintMode(){const b=$('#astDeep');if(!b)return;const pr=(S.points&&S.points.prices&&S.points.prices.ask)||0;b.classList.toggle('on',this.mode==='draft');b.setAttribute('aria-pressed',this.mode==='draft');
    b.title=this.mode==='draft'?'已开启：提问交给本机智能体读代码作答，每次 '+pr+' 点。再点关闭':'开启后提问交给本机智能体读代码作答（每次 '+pr+' 点）；关闭时只查已建知识，不扣点'},
  // what the assistant can act on here: the page, and the fields it can fill for you
  paintCtx(){const el=$('#astCtx');if(!el||!this.open)return;const p=pageSnap();
    const fl=[...new Set(p.fields.map(f=>f.label).filter(x=>x&&x.length<=8))].slice(0,4);
    const tk=this.sess&&this.sess.ticket;
    el.innerHTML=this.offer?`<span class="lbl">当前页面</span><b>${h(this.offer.key)}</b><span class="sub">${tk?'会话属于 '+h(tk.key):'会话没关联工单'}</span><a href="javascript:void 0" id="ofGo">切到这单的会话</a>`
      :`<span class="lbl">当前页面</span><b title="${h(p.route)}">${h(p.title||'')}</b>${fl.length?`<span class="sub">可代填：${h(fl.join('、'))}</span>`:''}`;
    if($('#ofGo'))$('#ofGo').onclick=()=>this.enterTicket(this.offer)},
  paintFoot(){const pr=(S.points&&S.points.prices&&S.points.prices.ask)||0;const arch=this.sess&&this.sess.archived_at;
    $('#astFoot').innerHTML=`<span>${arch?'会话已归档，恢复后才能发送':this.mode==='draft'?'深入分析：智能体读代码作答，每次 '+pr+' 点':'查已建知识，不扣点 · 说“打开…”“填…”直接操作页面'}</span><span>Enter 发送</span>`;
    const send=$('#astSend');if(send)send.disabled=!!arch},
  paintSugg(){
    const t=this.ticket,s=[];const el=$('#astSugg');if(!el)return;
    if(this.hist||!this.sid){el.innerHTML='';return}
    if(this.view){s.push(['写评论…','fill','评论：']);if(this.view.status!=='verify'&&this.view.status!=='closed')s.push(['改为待验证','cmd','把这单改成待验证'])}
    else if(!this.msgs.length){s.push(['新建工单…','fill','新建工单：']);s.push(['打开知识库','cmd','打开知识库'])}
    if(t){const failed=S.loop&&(S.loop.failed_ids||[]).includes(t.id);
      if(failed)s.push(['这单为什么失败？','draft']);
      s.push(['这单涉及哪些业务流和表？','evidence']);
      if(t.status==='verify')s.push(['起草验收说明','draft','起草这张工单的人工验收说明：列出要验证的业务操作、预期结果，以及分析和改动里还没核实的点。只写说明，不要替人判断通过。']);
      else s.push(['下一步该做什么？','draft']);
      if(['new','analyzing','confirm'].includes(t.status))s.push(['交给智能体分析定位','action:analyze'])}
    else if(!this.msgs.length){s.push(['这个系统有哪些主要业务？','evidence']);s.push(['审批是在哪里实现的？','evidence'])}
    el.innerHTML=s.map((x,i)=>`<button data-i="${i}">${h(x[0])}</button>`).join('');
    el.querySelectorAll('button').forEach(b=>b.onclick=()=>{const x=s[+b.dataset.i];if(x[1].startsWith('action:'))this.confirmRun(x[1].slice(7));
      else if(x[1]==='fill'){const q=$('#aq');q.value=x[2];q.focus();q.setSelectionRange(q.value.length,q.value.length)}else if(x[1]==='cmd')this.send(x[2]);else this.ask(x[2]||x[0],x[1])})},
  paintHist(){
    const q=this.q.trim().toLowerCase();const L=this.list.filter(s=>!q||(s.title+' '+(s.matter?s.matter.title:'')+' '+(s.ticket?s.ticket.key+s.ticket.title:'')).toLowerCase().includes(q));
    const row=s=>`<button class="hrow ${s.id===this.sid?'on':''}" data-s="${s.id}"><span class="grow"><b>${h(s.title)}</b>${q&&s.matter?`<i>${h(s.matter.title)}</i>`:''}</span>${s.running?'<span class="spin"></span>':''}<small>${s.n||0} 条 · ${ago(s.updated)}</small></button>`;
    const act=L.filter(s=>!s.archived_at),arc=L.filter(s=>s.archived_at);
    const grp=(title,inner,n,open)=>`<details class="hg" ${open?'open':''}><summary>${title}<small>${n}</small></summary>${inner||'<div class="sub" style="padding:4px 10px">没有</div>'}</details>`;
    const rc=recents();
    return `<div class="hist"><input id="hq" placeholder="搜索会话标题或工单号" value="${h(this.q)}" aria-label="搜索会话">
      <div class="hg"><div class="hgt">跳转</div><div class="jump">${[['#/','今天'],['#/board','工单看板'],['#/kb','知识库'],['#/map','架构与依据'],['#/eff','提效报告'],['#/settings','设置']].map(([r,t])=>`<a class="tag" href="${r}">${t}</a>`).join('')}</div>
       ${rc.length?`<div class="hgt">最近访问</div><div class="jump">${rc.map(x=>`<a class="tag" href="${h(x.r)}" title="${h(x.t)}">${h(x.t)}</a>`).join('')}</div>`:''}</div>
      ${grp('项目咨询',act.filter(s=>s.kind!=='ticket').map(row).join(''),act.filter(s=>s.kind!=='ticket').length,true)}
      ${grp('关联工单',act.filter(s=>s.kind==='ticket').map(s=>row(Object.assign({},s,{title:s.title}))).join(''),act.filter(s=>s.kind==='ticket').length,true)}
      ${grp('已归档',arc.map(row).join(''),arc.length,!!q)}</div>`},
  card(c){
    const k={flow:'业务流',tbl:'表',dom:'业务域',index:'总览',mod:'模块',code:'代码',page:'知识页'}[c.kind]||c.kind;
    const act=c.kind==='flow'?`showFlow('${h(c.id)}')`:c.kind==='code'?`toast('${h(c.file)}:${c.line}')`:`location.hash='#/kb/${encodeURIComponent(c.id)}'`;
    return `<div class="cite" role="button" tabindex="0" onclick="${act}"><span class="k ${h(c.kind)}">${k}</span><div class="ct"><b>${h(c.title)}</b>${c.sub?`<span>${h(c.sub)}</span><br>`:''}${c.summary?`<span>${h(c.summary.slice(0,120))}</span>`:''}${c.file&&c.kind!=='code'?`<div class="key" title="${h(c.file)}:${c.line}">${h(c.file.split('/').slice(-2).join('/'))}:${c.line}</div>`:''}</div>${c.status?`<span class="tag">${h(c.status==='过期'?'需更新':c.status)}</span>`:''}</div>`},
  cards(cs){if(!cs||!cs.length)return'';const top=cs.slice(0,3).map(c=>this.card(c)).join('');
    return `<div class="sec">关键依据</div>${top}${cs.length>3?`<details class="more"><summary>其余 ${cs.length-3} 条依据</summary>${cs.slice(3).map(c=>this.card(c)).join('')}</details>`:''}`},
  paintMsgs(){
    const el=$('#amsg');if(!el||!this.open)return;
    if(this.hist){el.innerHTML=this.paintHist();const q=$('#hq');q.oninput=()=>{this.q=q.value;const p=q.selectionStart;el.innerHTML=this.paintHist();this.bindHist();const n=$('#hq');n.focus();n.setSelectionRange(p,p)};this.bindHist();$('#astSugg').innerHTML='';return}
    if(!this.sid){el.innerHTML=`<div class="sub" style="padding:8px 2px">直接在下面输入就会开始一个会话。可以提问项目里的业务和代码，也可以让助手替你操作页面：“打开知识库”“新建工单：审批后单据未生效”“给这单写评论：已联系现场”。要提交或保存的操作，会先停下来等你确认。</div>`;return}
    if(!this.msgs.length&&!this.pending){el.innerHTML=`<div class="sub" style="padding:8px 2px">${this.ticket?'问这张工单的任何事：为什么失败、哪条没验收、改动影响哪些业务。':'问项目里的业务和代码。'}也可以直接说要做什么，比如“给这单写评论：……”“打开知识库里的请假审批”，助手会在页面上替你填好，提交前等你确认。回答带依据，查不到会明说。</div>`;this.paintSugg();return}
    el.innerHTML=this.msgs.map((m,i)=>{
      const d=m.data||{};const tm=(m.ts||'').slice(11,16);
      if(d.kind==='cmd'&&m.role==='user'){const nx=this.msgs[i+1];if(nx&&(nx.data||{}).kind==='cmd'&&nx.role!=='user')return '';return `<div class="m-u">${h(m.body)}<div class="m-time" style="justify-content:flex-end">${h(m.author)} ${tm}</div></div>`}
      if(m.role==='user')return `<div class="m-u">${h(m.body)}<div class="m-time" style="justify-content:flex-end">${h(m.author)} ${tm}</div></div>`;
      if(d.kind==='cmd')return this.cmdCard(m,tm);
      const run=d.state==='running';
      const body=run?`<div class="sub"><span class="spin"></span> ${h(d.agent||'智能体')} 正在查知识库和代码… <a href="javascript:void 0" onclick="showRun(${d.run})">看过程</a> · <a href="javascript:void 0" onclick="cancelRun(${d.run})">停止</a></div>`:md(m.body);
      const noev=!run&&d.no_evidence?`<div class="noev">⚠ 未检索到依据</div>`:'';
      const next=!run&&d.next?`<div class="sec">下一步</div><div class="nx">${h(d.next)}</div>`:'';
      const prev=(this.msgs[i-1]||{}).body||'';
      // what the answer offers: buttons that act (each confirmed here), the next questions, and the way to a deeper look
      const later=this.msgs.slice(i+1).some(x=>x.role==='user');
      const acts=!run&&!later&&(d.actions||[]).length?`<div class="row aact">${d.actions.map((a,j)=>`<button class="${j?'':'primary'}" data-act="${m.id}:${j}">${h(a.label)}</button>`).join('')}</div>`:'';
      const pr=(S.points&&S.points.prices&&S.points.prices.ask)||0;
      const deep=!run&&!later&&d.deep&&prev?`<button class="ghost" data-deep="${i}">让智能体读代码深入查（${pr} 点）</button>`:'';
      const fol=!run&&!later&&(d.follow||[]).length||deep?`<div class="afol">${(d.follow||[]).map(x=>`<button data-fol="${h(x)}">${h(x)}</button>`).join('')}${deep}</div>`:'';
      const fill=!run&&this.view&&/验收/.test(prev)&&$('#accNote')?`<button style="margin-top:6px" onclick="$('#accNote').value=${h(JSON.stringify(m.body))};toast('已填入验收说明，请人工确认后再点通过或不通过')">填入验收说明</button>`:'';
      return `<div class="m-a"><div class="av" aria-hidden="true"><svg width="16" height="16" viewBox="-12 -12 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><rect x="-9" y="-6" width="18" height="14" rx="4"/><path d="M0-6v-4 M-4 1h0 M4 1h0"/></svg></div><div class="bd">${body}${noev}${run?'':this.cards(d.cards)}${next}${acts}${fill}${fol}
        <div class="m-time">${d.mode==='evidence'?'<span class="tag">'+h(d.source||'查项目知识')+'</span>':'<span class="tag">'+h(d.agent||m.author)+(d.model?' · '+h(d.model):'')+'</span>'}${!run?`<span class="cost">本次 ${d.points||0} 点</span>`:''}${d.run&&!run?`<a href="javascript:void 0" onclick="showRun(${d.run})">过程</a>`:''}<span>${tm}</span></div></div></div>`}).join('')+(this.pending?this.pending:'');
    el.scrollTop=el.scrollHeight;this.paintSugg();this.bindCmd();this.bindAns()},
  bindAns(){
    document.querySelectorAll('#amsg [data-fol]').forEach(b=>b.onclick=()=>this.send(b.dataset.fol));
    document.querySelectorAll('#amsg [data-deep]').forEach(b=>b.onclick=()=>this.ask((this.msgs[+b.dataset.deep-1]||{}).body,'draft'));
    document.querySelectorAll('#amsg [data-act]').forEach(b=>b.onclick=()=>{const [mid,j]=b.dataset.act.split(':');const m=this.msgs.find(x=>x.id===+mid);const a=m&&(m.data.actions||[])[+j];if(a)this.act(a)})},
  // an action from an answer: say what it will do, then do it only after the person confirms
  act(a){
    const go=async()=>{this.pending=null;this.paintMsgs();let ok=0;
      for(const k of a.keys||[]){try{if(a.do==='resume'){await post('/api/tickets/'+k,{auto:'go'});ok++}}catch(e){toast(k+'：'+e.message,5000)}}
      if(ok)toast('已重新交给智能体：'+ok+' 单');if(this.view&&(a.keys||[]).includes(this.view.key))vTicket(this.view.key);this.load()};
    if(!a.confirm)return go();
    this.pending=`<div class="confirm"><b>${h(a.label)}</b><div style="margin-top:4px">${h(a.confirm)}涉及：${(a.keys||[]).map(h).join('、')}</div><div class="row"><button class="primary" id="acOk">确认</button><button id="acNo">取消</button></div></div>`;
    this.paintMsgs();$('#acOk').onclick=go;$('#acNo').onclick=()=>{this.pending=null;this.paintMsgs()}},
  bindHist(){document.querySelectorAll('#amsg .hrow').forEach(b=>b.onclick=()=>this.switchTo(+b.dataset.s))},
  // one box for both: a sentence that asks the page to do something becomes a plan; anything else is a question
  async send(q){
    q=(q||'').trim();if(!q||!S.proj)return;
    if(this.sess&&this.sess.archived_at){toast('会话已归档，先点“恢复”');return}
    if(this.live&&this.live.state==='waiting')this.cmdEnd('cancelled','被新的指令取代');
    let r=null;try{r=await post('/api/projects/'+S.proj+'/command',{text:q,page:pageSnap()})}catch(e){}
    if(!r||r.plan.kind!=='command')return this.ask(q);
    if(!this.sid){await this.newSession(this.view?'ticket':'consult',this.view?{ticket:this.view.key}:{title:'项目咨询'});if(!this.sid)return}
    try{r=await post('/api/projects/'+S.proj+'/command',{text:q,page:pageSnap(),session:this.sid,model:r.plan.source==='model'})}catch(e){return toast(e.message)}
    if(r.plan.kind!=='command')return this.ask(q);
    ls.set('tmh.draft.'+this.sid,null);await this.load();
    if(r.message&&r.plan.steps.length)this.runCmd(r.message,r.plan,0);else if(r.message)this.cmdEnd('done','',r.message)},
  // one card per action: 待你确认 → 已执行 (with 撤销 when the change can be put back); the steps fold away
  cmdCard(m,tm){
    const d=m.data,p=d.plan||{steps:[]};const L=this.live&&this.live.mid===m.id?this.live:null;
    const st=L?L.state:d.state,done=L?L.i:(d.done||0);
    const OP={nav:'跳转',open:'打开',fill:'填写',pick:'选择',click:'提交',session:'会话',project:'项目'};
    const txt=x=>x.op==='fill'?`${h(x.label)}：${x.value?h(x.value.length>90?x.value.slice(0,90)+'…':x.value):'<span class="sub">（光标放到这里）</span>'}`:x.op==='pick'?`${h(x.label)} → ${h(x.text)}`:x.op==='click'?`点击「${h(x.label)}」`:h(x.label);
    const cur=p.steps[done]||{};
    const steps=p.steps.length>1?`<details class="csd"><summary>${p.steps.length} 步</summary><ol class="csteps">${p.steps.map((x,i)=>`<li class="${i<done&&st!=='proposed'?'ok':i===done&&(st==='waiting'||st==='running')?'run':''}"><span class="op">${OP[x.op]||x.op}</span><span class="tx">${txt(x)}</span></li>`).join('')}</ol></details>`:'';
    let state='',foot='';
    if(L&&st==='waiting'){state='<span class="cst wait">待你确认</span>';
      foot=`<div class="sub" style="margin-top:4px">${txt(cur)}${cur.op==='click'?'。内容已经填在页面上，可以先改再确认。':''}</div><div class="row"><button class="primary" data-cmdok>${cur.op==='click'?'确认提交':'确认'}</button><button data-cmdno>取消</button></div>`}
    else if(L&&st==='running')state='<span class="cst run"><span class="spin"></span> 执行中</span>';
    else if(st==='done'){state=`<span class="cst ok">✓ 已执行 ${tm}</span>`;if(d.undo)foot=`<div class="row"><button class="ghost" data-cmdundo="${m.id}">撤销（改回「${h(d.undo.text||d.undo.value)}」）</button></div>`}
    else if(st==='undone')state=`<span class="cst">已撤销</span>`;
    else if(st==='cancelled')state=`<span class="cst">已取消</span>${d.note?`<span class="sub"> ${h(d.note)}</span>`:''}`;
    else if(st==='failed'){state=`<span class="cst bad">没完成</span><span class="sub"> ${h(d.note||'')}</span>`;foot=`<div class="row"><button data-cmdre="${m.id}">重新执行</button></div>`}
    else if(p.steps.length){state='<span class="cst">已中断</span>';foot=`<div class="row"><button data-cmdre="${m.id}">重新执行</button></div>`}
    return `<div class="m-a"><div class="av cmd" aria-hidden="true">⌘</div><div class="bd"><div class="cmdc ${h(st||'')}"><div class="chd"><b class="grow">${h(p.summary||m.body)}</b>${state}</div>${p.note?`<div class="sub" style="margin-top:4px">${h(p.note)}</div>`:''}${p.source==='model'&&st!=='done'?'<div class="sub" style="margin-top:4px">由操作模型理解你的话，代填内容请核对。</div>':''}${foot}${steps}</div></div></div>`},
  bindCmd(){
    const ok=document.querySelector('#amsg [data-cmdok]'),no=document.querySelector('#amsg [data-cmdno]');
    if(ok)ok.onclick=()=>this.confirmCmd();if(no)no.onclick=()=>this.cmdEnd('cancelled','');
    document.querySelectorAll('#amsg [data-cmdre]').forEach(b=>b.onclick=()=>{const m=this.msgs.find(x=>x.id===+b.dataset.cmdre);if(m)this.runCmd(m.id,m.data.plan,0)});
    document.querySelectorAll('#amsg [data-cmdundo]').forEach(b=>b.onclick=()=>this.undoCmd(+b.dataset.cmdundo))},
  async undoCmd(mid){
    const m=this.msgs.find(x=>x.id===mid);const u=m&&m.data.undo;if(!u)return;
    try{await cmdExec({op:'nav',to:u.route});await cmdExec({op:'pick',target:u.target,value:u.value,label:'',confirm:true})}catch(e){return toast('没能撤销：'+e.message,5000)}
    m.data.state='undone';delete m.data.undo;this.paintMsgs();toast('已改回「'+(u.text||u.value)+'」');
    try{await post('/api/sessions/'+this.sid+'/command/'+mid,{state:'undone',done:m.data.done||0})}catch(e){}},
  async runCmd(mid,plan,from){
    const undo=this.live&&this.live.mid===mid?this.live.undo:null;this.live={mid,plan,i:from||0,state:'running',undo};this.paintMsgs();
    for(;this.live&&this.live.mid===mid&&this.live.i<plan.steps.length;this.live.i++){
      const x=plan.steps[this.live.i];
      if(x.undo){const el=await waitEl(x.target);if(el&&el.value!==x.value){const o=el.options?[...el.options].find(o=>o.value===el.value):null;this.live.undo={target:x.target,value:el.value,text:o?o.text:el.value,route:location.hash}}}
      if(x.confirm){await cmdPrep(x);this.live.state='waiting';this.paintMsgs();post('/api/sessions/'+this.sid+'/command/'+mid,{state:'waiting',done:this.live.i}).catch(()=>{});return}
      if(x.op==='session'||x.op==='project'){this.live.i++;await this.cmdEnd('done');return cmdExec(x)}
      try{await cmdExec(x,!!x.undo)}catch(e){return this.cmdEnd('failed',e.message)}
      this.paintMsgs()}
    if(this.live&&this.live.mid===mid)this.cmdEnd('done')},
  async confirmCmd(){const L=this.live;if(!L||L.state!=='waiting')return;const x=L.plan.steps[L.i];L.state='running';this.paintMsgs();
    try{await cmdExec(x,true)}catch(e){return this.cmdEnd('failed',e.message)}
    this.runCmd(L.mid,L.plan,L.i+1)},
  async cmdEnd(state,note,mid){
    const L=this.live;mid=mid||(L&&L.mid);if(!mid)return;const done=L&&L.mid===mid?L.i:0;const undo=state==='done'&&L&&L.mid===mid?L.undo:null;if(L&&L.mid===mid)this.live=null;
    document.querySelectorAll('.ai-hl').forEach(e=>e.classList.remove('ai-hl'));
    const m=this.msgs.find(x=>x.id===mid);if(m){m.data.state=state;m.data.done=done;if(note)m.data.note=note;if(undo)m.data.undo=undo}this.paintMsgs();
    if(state==='failed')toast('没完成：'+note,5000);
    try{await post('/api/sessions/'+this.sid+'/command/'+mid,{state,done,note:note||'',undo})}catch(e){}},
  async ask(q,mode){
    q=(q||'').trim();if(!q||!S.proj)return;mode=mode||this.mode;
    if(!this.sid){await this.newSession(this.view?'ticket':'consult',this.view?{ticket:this.view.key}:{title:q.slice(0,20)});if(!this.sid)return}
    if(this.sess&&this.sess.archived_at){toast('会话已归档，先点“恢复”');return}
    const agent=$('#astAgent')?$('#astAgent').value:'codex';const sid=this.sid,idem=sid+'-'+Date.now()+'-'+Math.random().toString(36).slice(2,8);
    this.msgs.push({role:'user',body:q,author:S.user,ts:''});this.paintMsgs();
    const model=$('#astModel')?$('#astModel').value:'auto';
    try{const r=await post('/api/sessions/'+sid+'/messages',{question:q,mode,agent,model,idem});ls.set('tmh.draft.'+sid,null);
      if(this.sid===sid){this.sess=r.session;this.msgs=r.messages;this.paintMsgs()}
      $('#ptsN').textContent=r.balance.toLocaleString();await this.loadList();this.watch()}
    catch(e){toast(e.message);const t=$('#aq');if(t&&!t.value)t.value=q;this.load()}},
  async askTicket(t,q,mode){if(!this.sess||this.sess.ticket_id!==t.id)await this.enterTicket(t);this.toggle(true);this.ask(q,mode)},
  confirmRun(mode){
    const t=this.ticket;if(!t)return;const ag=$('#astAgent')?$('#astAgent').value:((S.meta.agents.find(a=>a.available)||{}).name||'codex');
    const price=(S.points&&S.points.prices&&S.points.prices[mode])||0;const ml=moLabel(mode);
    this.pending=`<div class="confirm"><b>确认执行</b><div style="margin-top:4px">让 ${h(ag)} 对 ${h(t.key)} ${h(ml)}。只读代码，结论记在工单上，结果回到这个会话。预计消耗 ${price} 点。</div><div class="row"><button class="primary" id="cfOk">确认执行</button><button id="cfNo">取消</button></div></div>`;
    this.paintMsgs();
    $('#cfNo').onclick=()=>{this.pending=null;this.paintMsgs()};
    $('#cfOk').onclick=async()=>{this.pending=null;this.paintMsgs();try{const r=await post('/api/tickets/'+t.key+'/runs',{agent:ag,mode,model:'auto',kb_after:2,session:this.sid});toast('已启动 #'+r.id);if(location.hash==='#/t/'+t.key)vTicket(t.key)}catch(e){toast(e.message)}}},
  // draft a ticket from this session; nothing is created until a person checks it and submits
  async draftTicket(){
    if(!this.sid){toast('先在一个会话里把问题说清楚，再起草工单');return}
    let d;try{d=await post('/api/sessions/'+this.sid+'/ticket-draft')}catch(e){return toast(e.message)}
    const sid=this.sid,idem='d'+sid+'-'+Date.now();
    modal(`<h2>起草工单</h2><div class="hint" style="margin-bottom:10px">草稿来自会话「${h(this.sess.title)}」。核对后提交才会创建工单；取消不会创建任何东西，会话也不变。根因没查实就保持“待确认”，负责人和验收条件不知道就留空。</div>
     ${d.existing?`<div class="seg" id="dtTarget" style="margin-bottom:10px"><button data-v="existing" class="on">补充到 ${h(d.existing.key)}</button><button data-v="new">另建工单</button></div>`:''}
     <label class="fl">标题<input class="full" id="dtTitle" value="${h(d.title)}"></label>
     <label class="fl">现象、排查情况与依据<textarea class="full" id="dtBody" rows="12">${h(d.body)}</textarea></label>
     <div class="row" style="gap:10px"><label class="fl">类型<select id="dtType">${S.meta.types.map(([k,l])=>`<option value="${k}" ${k===d.type?'selected':''}>${l}</option>`).join('')}</select></label>
      <label class="fl">优先级<select id="dtPri">${S.meta.priorities.map(([k,l])=>`<option value="${k}" ${k===d.priority?'selected':''}>${l}</option>`).join('')}</select></label>
      <label class="fl grow">负责人<input class="full" id="dtWho" placeholder="不确定就留空"></label></div>
     <label class="fl">验收条件<textarea class="full" id="dtAcc" rows="3" placeholder="例：审批通过后单据状态变为“已生效”，并能在列表里查到（不确定就留空）"></textarea></label>
     ${d.flows.length?`<div class="sub" style="margin:4px 0 10px">会关联业务流：${d.flows.map(f=>`<span class="key">${h(f)}</span>`).join(' ')}</div>`:''}
     <div class="row"><button class="primary" id="dtOk">${d.existing?'补充到工单':'提交工单'}</button><button id="dtNo">取消</button></div>`,true);
    let target=d.existing?'existing':'new';
    document.querySelectorAll('#dtTarget button').forEach(b=>b.onclick=()=>{target=b.dataset.v;document.querySelectorAll('#dtTarget button').forEach(x=>x.classList.toggle('on',x===b));$('#dtOk').textContent=target==='existing'?'补充到工单':'提交工单'});
    $('#dtNo').onclick=closeModal;
    $('#dtOk').onclick=async()=>{const b=$('#dtOk');b.disabled=true;
      try{const r=await post('/api/sessions/'+sid+'/ticket',{idem,target,title:$('#dtTitle').value,body:$('#dtBody').value,type:$('#dtType').value,priority:$('#dtPri').value,assignee:$('#dtWho').value,accept:$('#dtAcc').value,flows:d.flows});
        closeModal();toastAct(r.created?'已创建工单 '+r.key:'已补充到 '+r.key,'打开',()=>location.hash='#/t/'+r.key);await this.loadList();this.load()}
      catch(e){b.disabled=false;toast('提交失败，草稿还在：'+e.message,5000)}}}
};
function astKeys(e){if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();astSend()}}
function astSend(){const t=$('#aq');const v=t.value;if(!v.trim())return;t.value='';A.send(v)}

// ---------- page operations for the assistant: what is on screen, and how to act on it
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function vis(el){const d=el&&el.closest('details:not([open])');return !!(el&&el.getClientRects().length&&!el.closest('[hidden]')&&!(d&&!el.closest('summary')))}
function fieldLabel(el){
  const a=el.getAttribute('aria-label');if(a)return a.trim();
  const lb=el.id&&document.querySelector(`label[for="${CSS.escape(el.id)}"]`);if(lb)return lb.textContent.trim();
  const wrap=el.closest('label');if(wrap){const c=wrap.cloneNode(true);c.querySelectorAll('input,select,textarea,option').forEach(x=>x.remove());const t=c.textContent.trim();if(t)return t}
  const sib=el.parentElement&&el.parentElement.querySelector(':scope > label');if(sib)return sib.textContent.trim();
  if(el.placeholder)return el.placeholder.split(/[（(。，,]/)[0].trim();
  return el.id||''}
function pageSnap(){
  let n=0;const roots=[];if(!$('#modal').hidden)roots.push($('#mbody'));roots.push($('#main'));
  const key=el=>el.id||el.dataset.ai||(el.dataset.ai='a'+Date.now().toString(36)+(n++));
  const fields=[],buttons=[];
  roots.forEach(r=>{r.querySelectorAll('input,textarea,select').forEach(el=>{if(!vis(el)||['hidden','file','password'].includes(el.type))return;
      const f={key:key(el),label:fieldLabel(el).slice(0,30),type:el.tagName==='SELECT'?'select':el.tagName==='TEXTAREA'?'textarea':(el.type||'text')};
      if(f.type==='select')f.options=[...el.options].map(o=>[o.value,o.text.trim()]).slice(0,30);else if(f.type!=='checkbox')f.value=(el.value||'').slice(0,120);
      if(el.dataset.autosave)f.autosave=true;fields.push(f)});
    r.querySelectorAll('button').forEach(el=>{const t=el.textContent.trim();if(!vis(el)||!t||t.length>16)return;buttons.push({key:key(el),label:t})})});
  const hsh=location.hash||'#/';const mt=hsh.match(/^#\/t\/([^/]+)/);
  return {route:hsh,title:(($('#modal').hidden?$('#main h1'):$('#mbody h2'))||$('#main h1')||{textContent:''}).textContent.trim().slice(0,60),
    ticket:mt?decodeURIComponent(mt[1]):'',modal:!$('#modal').hidden,fields:fields.slice(0,40),buttons:buttons.slice(0,40)}}
function cmdEl(k){return document.getElementById(k)||document.querySelector(`[data-ai="${CSS.escape(k)}"]`)}
async function waitEl(k,ms){const t0=Date.now();while(Date.now()-t0<(ms||5000)){const e=cmdEl(k);if(vis(e))return e;await sleep(80)}return null}
function setVal(el,v){const pr=Object.getPrototypeOf(el);const d=Object.getOwnPropertyDescriptor(pr,'value');if(d&&d.set)d.set.call(el,v);else el.value=v}
function flash(el){el.classList.add('ai-hl');el.scrollIntoView({block:'center',behavior:'smooth'})}
// before a confirm step: point at the control so the person sees what will be saved or pressed
async function cmdPrep(x){const el=await waitEl(x.target);if(!el)return;flash(el)}
async function cmdExec(x,confirmed){
  if(x.op==='nav'){if(location.hash!==x.to){location.hash=x.to;await sleep(40)}await (S.renderP||Promise.resolve());await sleep(40);return}
  if(x.op==='open'){if(x.what==='new_ticket'){newTicket();if(!await waitEl('nt'))throw new Error('新建工单表单没有打开')}return}
  if(x.op==='session'){if(x.action==='new')await A.newSession('consult',{title:x.title});else await A.switchTo(x.id);return}
  if(x.op==='project'){const sel=$('#projSel');sel.value=x.key;sel.onchange({target:sel});return}
  const el=await waitEl(x.target);if(!el)throw new Error('页面上找不到「'+x.label+'」');
  if(x.op==='click'){el.classList.remove('ai-hl');el.click();await sleep(300);await (S.renderP||Promise.resolve());return}
  flash(el);setVal(el,x.op==='fill'?x.value:x.value);
  if(x.op==='fill'){el.dispatchEvent(new Event('input',{bubbles:true}));if(!x.value)el.focus()}
  if(x.op==='pick'||x.confirm)el.dispatchEvent(new Event('change',{bubbles:true}));
  if(x.confirm||confirmed){await sleep(300);await (S.renderP||Promise.resolve())}}
function toastAct(t,label,fn,ms){const e=$('#toast');e.innerHTML=`<span>${h(t)}</span> <button class="ghost">${h(label)}</button>`;e.hidden=false;e.querySelector('button').onclick=()=>{e.hidden=true;fn()};clearTimeout(e._t);e._t=setTimeout(()=>e.hidden=true,ms||7000)}
document.addEventListener('click',e=>{if(!e.target.closest('.nw'))document.querySelectorAll('#astHead .menu').forEach(m=>m.hidden=true)});

boot();
"""
