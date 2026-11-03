"""业务状态图: each business flow as a Pele-drawn statechart, with its rules and the numbered path to a broken one.

The renderer (vendor/pele.global.js) is fetched through the project API only when this page opens. Colours come from the shared theme
tokens so the chart reads as part of Webuddy, not as a separate tool.
"""

STATES_CSS = r"""
.stc{background:var(--panel);border:1px solid var(--line);border-radius:8px;display:grid;grid-template-columns:200px minmax(0,1fr) 340px;
  height:calc(100vh - var(--shell-height) - 190px);min-height:560px;overflow:hidden}
.stc-rail{border-right:1px solid var(--line);padding:12px 10px;display:flex;flex-direction:column;gap:2px;overflow:auto}
.stc-rail button{display:flex;align-items:center;gap:8px;width:100%;text-align:left;border:1px solid transparent;background:none;color:var(--fg);padding:7px 10px;min-height:34px}
.stc-rail button.on{background:var(--blue-s);border-color:var(--selected-line);color:var(--blue)}
.stc-rail em{margin-left:auto;font-style:normal;font-size:11px;min-width:18px;height:18px;padding:0 5px;border-radius:9px;display:grid;place-items:center;font-weight:600}
.stc-rail em.bad{background:var(--bad-s);color:var(--bad)}.stc-rail em.ok{color:var(--ok)}.stc-rail em.chg{background:var(--warn-s);color:var(--warn)}
.stc-stage{position:relative;display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;
  background:radial-gradient(circle at 1px 1px,var(--line) 1px,transparent 0) 0 0/18px 18px}
.stc-bar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.stc-bar h2{margin:0;font-size:15px}
.stc-cv{flex:1;display:flex;padding:20px 24px 46px;min-height:0;overflow:hidden;
  --pele-bg:transparent;--pele-fg:var(--fg);--pele-muted:var(--mut);--pele-line:#98A2B3;--pele-surface:var(--panel);--pele-surface-alt:var(--soft);
  --pele-border:var(--control-line);--pele-accent:var(--blue);--pele-font-mono:var(--mono)}
.stc-cv svg{width:100%!important;height:100%!important;max-width:100%!important;overflow:visible}
.stc-cv .pele-node,.stc-cv .pele-edge,.stc-cv .pele-edge-label{transition:opacity .35s}
.stc-cv.tracing .pele-node,.stc-cv.tracing .pele-edge,.stc-cv.tracing .pele-edge-label{opacity:.35}
.stc-cv .lit{opacity:1!important}
.stc-cv .pele-node.lit>rect{stroke:var(--blue);stroke-width:2.5;fill:var(--blue-s)}
.stc-cv .pele-node.lit>text{font-weight:600}
.stc-cv .pele-edge.lit>path:not(.pele-marker){stroke:var(--blue);stroke-width:2.2;stroke-dasharray:6 5;animation:stcFlow .8s linear infinite}
.stc-cv .pele-edge.lit>.pele-marker{fill:var(--blue)}
.stc-cv .pele-edge-label.lit text{fill:var(--blue);font-weight:600}
.stc-cv .pele-node.end>rect{stroke:var(--bad)!important;stroke-width:2.5;fill:var(--bad-s)!important}
.stc-cv .pele-node.end>text{fill:var(--bad)}
@keyframes stcFlow{to{stroke-dashoffset:-22}}
@media (prefers-reduced-motion:reduce){.stc-cv .pele-edge.lit>path{animation:none}}
.stc-lg{position:absolute;left:16px;bottom:12px;display:flex;gap:16px;font-size:12px;color:var(--mut)}
.stc-lg span{display:flex;align-items:center;gap:6px}.stc-lg i{width:18px;border-top:2px dashed var(--blue)}
.stc-lg b{width:12px;height:12px;border:2px solid var(--bad);background:var(--bad-s);border-radius:3px}
.stc-side{border-left:1px solid var(--line);overflow:auto}
.stc-blk{padding:16px 18px;border-bottom:1px solid var(--line)}
.stc-blk h3{font-size:12px;font-weight:500;color:var(--mut);margin:0 0 8px}
.stc-rule{display:flex;gap:10px;padding:7px 10px;margin:0 -10px;border-radius:6px;font-size:13px;align-items:flex-start}
.stc-rule.bad{background:var(--bad-s)}
.stc-rule .m{width:18px;height:18px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:11px;font-weight:700;margin-top:2px;background:var(--ok-s);color:var(--ok)}
.stc-rule.bad .m{background:var(--bad);color:#fff}
.stc-rule small,.stc-step small{display:block;font:11.5px var(--mono);color:var(--mut);overflow-wrap:anywhere}
.stc-step{display:flex;gap:10px;padding:5px 0;align-items:flex-start;font-size:13px;opacity:.5;transition:opacity .3s}
.stc-step.on{opacity:1}
.stc-step .n{width:22px;height:22px;border-radius:50%;border:1.5px solid var(--blue);color:var(--blue);display:grid;place-items:center;font-size:11.5px;font-weight:700;flex:none}
.stc-step.on .n{background:var(--blue);color:#fff}
.stc-step.end .n{border-color:var(--bad);color:var(--bad)}.stc-step.end.on .n{background:var(--bad);color:#fff}
.stc-acts{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.stc-note{font-size:12.5px;color:var(--warn);background:var(--warn-s);border-radius:6px;padding:8px 10px;margin-top:8px;overflow-wrap:anywhere}
.stc-err{font-size:12.5px;color:var(--bad);background:var(--bad-s);border-radius:6px;padding:8px 10px;margin:4px 0}
.stc-empty{padding:40px;text-align:center}.stc-empty p{color:var(--mut);max-width:520px;margin:8px auto 18px}
@media(max-width:1100px){.stc{grid-template-columns:1fr;height:auto}.stc-rail{flex-direction:row;border-right:0;border-bottom:1px solid var(--line)}
 .stc-stage{height:62vh}.stc-side{border-left:0;border-top:1px solid var(--line)}}
"""

STATES_JS = r"""
// ---------- 业务状态图: statecharts the agent drew, rendered with Pele, rules and the path to a broken one
const STCH={d:null,cur:'',timer:0,step:-1,load:null};
function stcLib(){
  if(window.pele)return Promise.resolve();
  if(STCH.load)return STCH.load;
  STCH.load=get('/api/projects/'+S.proj+'/statecharts/renderer').then(r=>{const s=document.createElement('script');s.textContent=r.js;document.head.appendChild(s);
    if(!window.pele)throw apiErr('状态图组件没能加载，刷新试试。')}).catch(e=>{STCH.load=null;throw e});
  return STCH.load}
async function vStates(cid){
  clearInterval(STCH.timer);
  const d=await get('/api/projects/'+S.proj+'/statecharts');STCH.d=d;
  const busy=(d.running||[]).length;
  const head=pageHead('业务状态图','每条业务流程会走过哪些状态，要守住哪些规则。',
    d.built?`<button id="stcDraw" class="${d.charts.length?'':'primary'}" ${busy?'disabled':''}>${busy?'AI 正在画…':d.charts.length?'让 AI 重画':'让 AI 画状态图'}</button>`:'');
  if(!d.built){$('#main').innerHTML=head+'<div class="hint">还没有知识图谱。到“知识页 → 建设知识库”先分析一次代码，再来画状态图。</div>';return}
  if(!d.charts.length){
    $('#main').innerHTML=head+`<div class="card stc-empty"><h2>还没有状态图</h2><p>AI 读完代码，为每个业务域画一张：页面上能看到的状态、让它们切换的操作，以及代码里要守住的规则（都带 文件:行号）。画好的图先是“待确认”。</p>
      ${busy?`<a class="btn" href="#/runs">看 AI 的进度</a>`:'<button class="primary" id="stcDraw2">让 AI 画状态图</button>'}</div>`;
    stcBindDraw();return}
  await stcLib();
  STCH.cur=d.charts.some(c=>c.id===cid)?cid:(d.charts.find(c=>c.paths&&c.paths.length)||d.charts[0]).id;
  $('#main').innerHTML=head+`<div class="stc"><nav class="stc-rail" id="stcRail" aria-label="业务流程"></nav>
    <section class="stc-stage"><div class="stc-bar"><h2 id="stcTitle"></h2><span id="stcSt"></span></div><div class="stc-cv" id="stcCv"></div>
      <div class="stc-lg"><span><i></i>走到问题的路径</span><span><b></b>打破规则的状态</span></div></section>
    <aside class="stc-side" id="stcSide"></aside></div>`;
  stcBindDraw();stcPaint()}
function stcBindDraw(){
  for(const b of [$('#stcDraw'),$('#stcDraw2')])if(b)b.onclick=async()=>{b.disabled=true;
    try{await post('/api/projects/'+S.proj+'/runs',{mode:'chart'});toast('AI 开始画状态图，画好后回到这一页查看');b.textContent='AI 正在画…'}
    catch(e){b.disabled=false;toast(e.message)}}}
function stcFlag(c){if(c.problems&&c.problems.length)return '<em class="bad">!</em>';if(c.paths&&c.paths.length)return `<em class="bad">${c.paths.length}</em>`;
  if(c.changed&&c.changed.length)return '<em class="chg">改</em>';return '<em class="ok">✓</em>'}
function stcPaint(){
  clearInterval(STCH.timer);STCH.step=-1;
  const d=STCH.d,c=d.charts.find(x=>x.id===STCH.cur);
  $('#stcRail').innerHTML=d.charts.map(x=>`<button data-c="${h(x.id)}" class="${x.id===c.id?'on':''}" ${x.id===c.id?'aria-current="true"':''}>${h(x.title)}${stcFlag(x)}</button>`).join('');
  $('#stcRail').querySelectorAll('button').forEach(b=>b.onclick=()=>{STCH.cur=b.dataset.c;history.replaceState(null,'','#/states/'+encodeURIComponent(STCH.cur));stcPaint()});
  $('#stcTitle').textContent=c.title;
  $('#stcSt').innerHTML=`<span class="pill" style="background:var(--${c.status==='已确认'?'ok':'warn'}-s);color:var(--${c.status==='已确认'?'ok':'warn'})">${h(c.status||'待确认')}</span>`;
  const cv=$('#stcCv');cv.classList.remove('tracing');
  try{cv.innerHTML=pele.render(c.mermaid,{idPrefix:'stc-'+c.id.replace(/[^A-Za-z0-9_-]/g,''),fontSize:14,autoDirection:false,
    fontFamily:getComputedStyle(document.body).fontFamily}).svg}
  catch(e){cv.innerHTML=`<div class="stc-err">这张图画不出来：${h(e.message)}</div>`}
  (c.paths||[]).forEach(p=>{const last=p.steps[p.steps.length-1];if(last)stcMark(last.state,'end')});
  stcSide(c);
  if((c.paths||[]).length)setTimeout(()=>stcTrace(0),350)}
function stcMark(id,cls){const n=[...$('#stcCv').querySelectorAll('.pele-node')].find(x=>x.dataset.id===id);if(n)n.classList.add(cls)}
function stcSide(c){
  const p=(c.paths||[])[0];
  let o=`<div class="stc-blk"><h3>规则</h3>${c.rules.length?c.rules.map(r=>`<div class="stc-rule ${r.holds?'':'bad'}"><span class="m">${r.holds?'✓':'!'}</span><div>${h(r.text)}${r.where?`<small title="${h(r.where)}">${h(r.where.split('/').pop())}</small>`:''}</div></div>`).join(''):'<div class="sub">这张图还没有写规则。</div>'}
    ${c.changed&&c.changed.length?`<div class="stc-note">代码改了，这张图要重看：${c.changed.map(h).join('、')}</div>`:''}
    ${(c.problems||[]).map(x=>`<div class="stc-err">${h(x)}</div>`).join('')}</div>`;
  if(p)o+=`<div class="stc-blk"><h3>走到问题的路径 · ${h(c.rules[p.rule].text)}</h3>${p.steps.map((s,i)=>`<div class="stc-step ${i===p.steps.length-1?'end':''} ${i<=STCH.step?'on':''}"><span class="n">${i+1}</span><div>${h(stcLabel(c,s.state))}${s.note?`<small>${h(s.note)}</small>`:''}</div></div>`).join('')}
    <div class="stc-acts"><button class="primary" id="stcPlay">▶ 走一遍</button><button id="stcFix">记成需求</button></div></div>`;
  o+=`<div class="stc-blk"><h3>依据</h3><div class="sub">AI 读代码画的图${c.commit?'，基于提交 <code>'+h(c.commit.slice(0,10))+'</code>':''}。状态和规则以代码为准，看到不对的地方，在知识页里纠正或让 AI 重画。</div></div>`;
  $('#stcSide').innerHTML=o;
  const play=$('#stcPlay');if(play)play.onclick=()=>stcTrace(0);
  const fix=$('#stcFix');if(fix)fix.onclick=()=>newTicket({title:c.title+'：'+c.rules[p.rule].text,
    body:'业务状态图「'+c.title+'」里，这条规则会被打破：'+c.rules[p.rule].text+'\n\n路径：\n'+p.steps.map((s,i)=>(i+1)+'. '+stcLabel(c,s.state)+(s.note?'：'+s.note:'')).join('\n')})}
function stcLabel(c,id){const m=c.mermaid.match(new RegExp('state\\s+"([^"]*)"\\s+as\\s+'+id.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\b'));return m?m[1]:id}
function stcTrace(i){
  const c=STCH.d.charts.find(x=>x.id===STCH.cur),p=(c.paths||[])[i];if(!p)return;
  clearInterval(STCH.timer);const cv=$('#stcCv');cv.classList.add('tracing');cv.querySelectorAll('.lit').forEach(x=>x.classList.remove('lit'));
  STCH.step=-1;stcSide(c);
  const seq=[];p.steps.forEach((s,k)=>{seq.push(['n',s.state,k]);if(p.edges[k])seq.push(['e',p.edges[k]])});let j=0;
  STCH.timer=setInterval(()=>{if(!document.body.contains(cv)){clearInterval(STCH.timer);return}const [t,id,k]=seq[j];
    if(t==='n'){stcMark(id,'lit');STCH.step=k;$('#stcSide').querySelectorAll('.stc-step').forEach((x,n)=>x.classList.toggle('on',n<=k))}
    else cv.querySelectorAll('[data-id="'+id+'"]').forEach(x=>x.classList.add('lit'));
    if(++j>=seq.length)clearInterval(STCH.timer)},480)}
"""
