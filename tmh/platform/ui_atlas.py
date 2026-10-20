"""项目图谱: the knowledge base drawn as one navigable picture (no external libraries, works offline).

Three levels, each a click deeper: 全景 (business domains and the tables they share), 业务域 (its flows and the tables
they read and write), 业务流 (entry → methods by layer → tables and side effects, with a step-by-step 讲解).
"""

ATLAS_CSS = r"""
.atl{--a-bg:#0B1020;--a-panel:#121A30;--a-card:#151F38;--a-line:#26324F;--a-fg:#E6ECF8;--a-mut:#8E9BB8;--a-gold:#E8B86D;
  --a-flow:#F5A3B5;--a-tbl:#5EEAD4;--a-tk:#F87171;--a-fx:#7DD3FC;background:var(--a-bg);color:var(--a-fg);border-radius:12px;overflow:hidden;
  display:flex;flex-direction:column;height:calc(100vh - 150px);min-height:540px;position:relative;color-scheme:dark}
.atl-top{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid var(--a-line);background:var(--a-panel)}
.atl-top .cr{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--a-mut);min-width:0}
.atl-top .cr a{color:var(--a-fg);text-decoration:none;cursor:pointer}.atl-top .cr a:hover{color:var(--a-gold)}
.atl-top .cr b{color:var(--a-gold);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px}
.atl-top .sp{flex:1}
.atl-q{position:relative}.atl-q input{width:240px;max-width:52vw;background:var(--a-bg);border:1px solid var(--a-line);color:var(--a-fg);border-radius:8px;padding:6px 10px 6px 28px;font-size:13px;height:auto}
.atl-q::before{content:"⌕";position:absolute;left:10px;top:5px;color:var(--a-mut)}
.atl-q .res{position:absolute;right:0;top:36px;width:340px;max-width:86vw;background:var(--a-panel);border:1px solid var(--a-line);border-radius:10px;z-index:5;max-height:360px;overflow:auto;box-shadow:0 12px 32px rgba(0,0,0,.45)}
.atl-q .res button{display:flex;gap:8px;width:100%;text-align:left;background:none;border:0;color:var(--a-fg);padding:7px 12px;font-size:13px;cursor:pointer;align-items:center;height:auto;border-radius:0}
.atl-q .res button:hover,.atl-q .res button.on{background:#1C2846}.atl-q .res i{font-style:normal;font-size:11px;padding:1px 6px;border-radius:4px;flex:none}
.atl-q .res span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.atl-q .res small{color:var(--a-mut);margin-left:auto;flex:none}
.atl-btn{background:#1A2440;color:var(--a-fg);border:1px solid var(--a-line);border-radius:8px;padding:5px 11px;font-size:13px;cursor:pointer;height:auto}
.atl-btn:hover{border-color:var(--a-gold);color:var(--a-gold)}.atl-btn.on{background:var(--a-gold);color:#1B1408;border-color:var(--a-gold)}
.atl-body{flex:1;display:flex;min-height:0;position:relative}
.atl-cv{flex:1;position:relative;min-width:0;background-image:radial-gradient(#1E2946 1px,transparent 1px);background-size:22px 22px}
.atl svg.atl-s{width:100%;height:100%;display:block;cursor:grab;user-select:none;touch-action:none}.atl svg.atl-s.drag{cursor:grabbing}
.atl-side{width:330px;flex:none;border-left:1px solid var(--a-line);background:var(--a-panel);overflow:auto;padding:16px;font-size:13px;line-height:1.6}
.atl-side h3{margin:0 0 4px;font-size:17px;color:var(--a-fg)}.atl-side h4{margin:16px 0 6px;font-size:12px;color:var(--a-mut);font-weight:600;letter-spacing:.06em}
.atl-side .ty{font-size:11px;letter-spacing:.08em;font-weight:600}.atl-side p{margin:6px 0;color:#C9D3E8}
.atl-side .kv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0}
.atl-side .kv div{background:var(--a-card);border:1px solid var(--a-line);border-radius:8px;padding:8px 10px}
.atl-side .kv b{display:block;font-size:20px;font-variant-numeric:tabular-nums;color:var(--a-fg)}.atl-side .kv span{font-size:11px;color:var(--a-mut)}
.atl-side .li{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:6px;cursor:pointer;color:var(--a-fg)}
.atl-side .li:hover{background:#1C2846}.atl-side .li span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.atl-side .li small{color:var(--a-mut);flex:none}
.atl-side .dot{width:8px;height:8px;min-width:8px;border-radius:50%;flex:none;display:inline-block}
.atl-side code{font-size:12px;color:#BFD0F0;background:#0E1528;padding:1px 5px;border-radius:4px;word-break:break-all}
.atl-side .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.atl-side .acts a,.atl-side .acts button{background:#1A2440;color:var(--a-fg);border:1px solid var(--a-line);border-radius:8px;padding:5px 11px;font-size:13px;cursor:pointer;text-decoration:none;height:auto}
.atl-side .acts .pri{background:var(--a-gold);color:#1B1408;border-color:var(--a-gold)}
.atl-side .chip{display:inline-block;font-size:12px;padding:1px 7px;border-radius:5px;margin:2px 4px 2px 0;background:#1A2440;border:1px solid var(--a-line)}
.atl-side .tour{background:linear-gradient(135deg,#2A2140,#1A2440);border:1px solid #4B3D6E;border-radius:10px;padding:12px;margin-bottom:14px}
.atl-side .tour .bar{height:4px;background:#2B3656;border-radius:2px;margin:8px 0}.atl-side .tour .bar i{display:block;height:100%;background:var(--a-gold);border-radius:2px;transition:width .3s}
.atl-ov{position:absolute;pointer-events:none;font-size:12px;color:var(--a-mut)}
.atl-ov.a-tl{left:14px;top:12px}.atl-ov.a-bl{left:14px;bottom:12px;display:flex;gap:12px;flex-wrap:wrap;max-width:70%}.atl-ov.a-bl span{display:inline-flex;gap:5px;align-items:center}
.atl-ov.a-bl i{width:10px;height:10px;border-radius:3px;display:inline-block}
.atl-ov.a-tl{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:calc(100% - 28px)}.atl-ov.a-tl b{color:var(--a-fg);font-size:13px;display:inline}
.atl-zm{position:absolute;right:12px;bottom:12px;display:flex;flex-direction:column;gap:4px}
.atl-zm button{width:30px;height:30px;padding:0;background:#1A2440;color:var(--a-fg);border:1px solid var(--a-line);border-radius:6px;cursor:pointer;font-size:15px}
.atl .e{fill:none;transition:opacity .25s,stroke-width .25s}.atl .n{cursor:pointer;transition:opacity .25s}
.atl .n .in{animation:atlIn .55s cubic-bezier(.2,.8,.3,1.2) both;transform-box:fill-box;transform-origin:center}
@keyframes atlIn{from{opacity:0;transform:scale(.4)}to{opacity:1;transform:none}}
.atl .e.flowing,.atl svg.dim .e.hi{stroke-dasharray:7 6;animation:atlDash 1.1s linear infinite}
@keyframes atlDash{to{stroke-dashoffset:-13}}
.atl svg.dim .n:not(.hi){opacity:.14}.atl svg.dim .e:not(.hi){opacity:.05}.atl svg.dim .e.hi{opacity:1;stroke-width:2.4}
.atl svg.dim .lbl:not(.hi){opacity:0}
.atl .n.sel .frame,.atl .n.sel circle.core{stroke:var(--a-gold);stroke-width:2.5;filter:drop-shadow(0 0 10px rgba(232,184,109,.75))}
.atl .n:hover .frame,.atl .n:hover circle.core{filter:drop-shadow(0 0 8px rgba(255,255,255,.35))}
.atl .n.pulse .frame,.atl .n.pulse circle.core{animation:atlPulse 1.4s ease-in-out infinite;stroke:var(--a-gold);stroke-width:2.5}
@keyframes atlPulse{0%,100%{filter:drop-shadow(0 0 4px rgba(232,184,109,.5))}50%{filter:drop-shadow(0 0 18px rgba(232,184,109,1))}}
.atl .tkring{animation:atlRing 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes atlRing{0%{opacity:.85;transform:scale(1)}100%{opacity:0;transform:scale(1.35)}}
.atl text{font-family:inherit;pointer-events:none}.atl .t-ty{font-size:11px;letter-spacing:.08em;font-weight:600}
.atl .t-tt{font-size:15px;fill:var(--a-fg);font-weight:600}.atl .t-st{font-size:12.5px;fill:var(--a-mut)}
.atl .t-dl{font-size:16px;fill:var(--a-fg);font-weight:700;text-anchor:middle}.atl .t-ds{font-size:11px;fill:var(--a-mut);text-anchor:middle}
.atl .t-tb{font-size:10px;fill:#BFEFE7;text-anchor:middle}.atl .t-hd{font-size:11px;fill:var(--a-mut);letter-spacing:.1em;font-weight:600}
.atl .t-lk{font-size:10px;fill:var(--a-gold);text-anchor:middle}
.atl svg.far .t-tb,.atl svg.far .t-lk,.atl svg.far .t-ds{display:none}.atl svg.mid .t-tb{display:none}
.atl svg.mid .n.hi .t-tb,.atl svg.far .n.hi .t-tb{display:block}
@media(max-width:900px){.atl{height:auto}.atl-body{flex-direction:column}.atl-cv{height:62vh;flex:none}.atl-side{width:auto;border-left:0;border-top:1px solid var(--a-line)}
 .atl-ov.a-bl{display:none}}
"""

ATLAS_JS = r"""
// ---------- 项目图谱: 全景 → 业务域 → 业务流, drawn in plain SVG so it also works without internet
const AT={d:null,at:0,view:'',arg:'',k:1,x:0,y:0,N:{},E:[],adj:{},sel:'',tour:null,flow:null,anim:0};
const LCOL={入口:'#FDBA74',业务:'#A78BFA',数据:'#6EE7B7',其他:'#94A3B8'};
const OPN={C:'增',R:'查',U:'改',D:'删',P:'过程',W:'写'};
const isW=o=>/[CUDPW]/.test(o||'');
const opCol=o=>isW(o)?'#FBBF24':'#5EEAD4';
const STC={已确认:'#4ADE80',待确认:'#FBBF24',需更新:'#F87171',未分析:'#64748B',仅事实:'#64748B'};
function domCol(id){const i=AT.d.domains.findIndex(d=>d.id===id);return i<0?'#94A3B8':`hsl(${Math.round(i*137.508)%360} 70% 66%)`}
function fitTxt(s,em){s=String(s||'');let w=0,o='';for(const c of s){w+=c.charCodeAt(0)>255?1:.58;if(w>em)return o+'…';o+=c}return o}
async function vAtlas(arg){
  if(!AT.d||AT.d.project&&AT.d.project.key!==S.proj||Date.now()-AT.at>60000){AT.d=await get('/api/projects/'+S.proj+'/atlas');AT.at=Date.now()}
  const D=AT.d;
  if(!D.built){$('#main').innerHTML=pageHead('项目图谱','业务域、业务流、代码和数据表连成的一张图。')+'<div class="hint">还没有知识图谱。到“知识库 → 建设进度”开始一次全项目分析，图谱会自动生成。</div>';return}
  D.dm={};D.domains.forEach(d=>D.dm[d.id]=d);D.fm={};D.flows.forEach(f=>D.fm[f.id]=f);D.tm={};D.tables.forEach(t=>D.tm[t.name]=t);
  if(!$('#atl')){
    $('#main').innerHTML=`<div class="atl" id="atl"><div class="atl-top"><div class="cr" id="atlCr"></div><span class="sp"></span>
      <div class="atl-q"><input id="atlQ" placeholder="搜索业务、流程、表（按 / ）" autocomplete="off" aria-label="搜索图谱"><div class="res" id="atlRes" hidden></div></div>
      <button class="atl-btn" id="atlTour" title="按顺序讲一遍（← → 翻页）">▶ 讲解</button><button class="atl-btn" id="atlTk" title="只看有在办工单的部分">只看有工单的</button></div>
     <div class="atl-body"><div class="atl-cv" id="atlCv"><svg class="atl-s" id="atlSvg" aria-label="项目图谱"><g id="atlVp"><g id="atlE"></g><g id="atlN"></g></g></svg>
      <div class="atl-ov a-tl" id="atlTl"></div><div class="atl-ov a-bl" id="atlLg"></div>
      <div class="atl-zm"><button data-z="1.25" title="放大">＋</button><button data-z="0.8" title="缩小">－</button><button data-z="0" title="适应窗口">⤢</button></div></div>
      <aside class="atl-side" id="atlSide"></aside></div></div>`;
    atlBind()}
  AT.tour=null;$('#atlTour').classList.remove('on');$('#atlTour').textContent='▶ 讲解';$('#atlTk').classList.toggle('on',!!AT.onlyT);
  if(arg.startsWith('flow:'))return atlFlow(arg);
  if(arg.startsWith('dom:'))return atlDom(arg);
  atlAll()}
function atlCrumb(parts){$('#atlCr').innerHTML=[`<a href="#/atlas">${h(AT.d.project.name||AT.d.project.key)} 全景</a>`].concat(parts).join('<span>/</span>')}
// ---- drawing
function atlDraw(nodes,edges){
  AT.N={};AT.adj={};AT.E=edges;nodes.forEach(n=>{AT.N[n.id]=n;AT.adj[n.id]=new Set()});
  edges.forEach(e=>{if(AT.adj[e.a])AT.adj[e.a].add(e.b);if(AT.adj[e.b])AT.adj[e.b].add(e.a)});
  $('#atlE').innerHTML=edges.map((e,i)=>{const a=AT.N[e.a],b=AT.N[e.b];if(!a||!b)return '';
    return `<path class="e ${e.cls||''}" data-i="${i}" d="${atlPath(a,b,e)}" stroke="${e.c}" stroke-width="${e.w||1.2}" stroke-opacity="${e.o==null?.55:e.o}" ${e.dash?`stroke-dasharray="${e.dash}"`:''}/>`+
      (e.label?`<text class="lbl t-lk ${e.lc||''}" data-i="${i}" x="${(a.x+b.x)/2+(e.lx||0)}" y="${(a.y+b.y)/2-6}">${h(e.label)}</text>`:'')}).join('');
  $('#atlN').innerHTML=nodes.map((n,i)=>atlNode(n,Math.min(i,60)*14)).join('');
  atlSel('');}
function atlPath(a,b,e){
  if(e.curve==='h'){const x1=a.x+(a.w||0)/2,x2=b.x-(b.w||0)/2,dx=Math.max(40,(x2-x1)/2);return `M${x1} ${a.y}C${x1+dx} ${a.y},${x2-dx} ${b.y},${x2} ${b.y}`}
  if(e.curve==='v'){const ah=(a.h||a.r*2||0)/2,bh=(b.h||b.r*2||0)/2;
    if(Math.abs(b.y-a.y)<Math.max(ah,bh)){const s=b.x>a.x?1:-1,x1=a.x+s*(a.w||0)/2,x2=b.x-s*(b.w||0)/2,dx=s*Math.max(30,Math.abs(x2-x1)/2);return `M${x1} ${a.y}C${x1+dx} ${a.y},${x2-dx} ${b.y},${x2} ${b.y}`}
    const s=b.y>a.y?1:-1,y1=a.y+s*ah,y2=b.y-s*bh,dy=s*Math.max(30,Math.abs(y2-y1)/2);return `M${a.x} ${y1}C${a.x} ${y1+dy},${b.x} ${y2-dy},${b.x} ${y2}`}
  if(e.curve==='q'){const mx=(a.x+b.x)/2,my=(a.y+b.y)/2,dx=b.x-a.x,dy=b.y-a.y,l=Math.hypot(dx,dy)||1,o=Math.min(60,l*.18);return `M${a.x} ${a.y}Q${mx-dy/l*o} ${my+dx/l*o},${b.x} ${b.y}`}
  return `M${a.x} ${a.y}L${b.x} ${b.y}`}
function atlNode(n,delay){
  const st=`style="animation-delay:${delay}ms"`;
  if(n.shape==='circle'){const r=n.r;
    return `<g class="n ${n.cls||''}" data-id="${h(n.id)}" transform="translate(${n.x},${n.y})"><g class="in" ${st}>
      ${n.tk?`<circle class="tkring" r="${r+6}" fill="none" stroke="#F87171" stroke-width="2"/>`:''}
      ${n.small?'':`<circle r="${r+14}" fill="${n.c}" fill-opacity=".07" pointer-events="none"/>`}<circle class="core" r="${r}" fill="${n.c}" fill-opacity="${n.fo||.2}" stroke="${n.c}" stroke-width="1.6"/>
      ${n.title?`<text class="${n.tc||'t-dl'}" y="${n.small?r+13:4}">${h(n.title)}</text>`:''}${n.sub?`<text class="t-ds" y="${r+16}">${h(n.sub)}</text>`:''}
      ${n.tk?`<g transform="translate(${r*.72},${-r*.72})"><circle r="9" fill="#F87171"/><text y="4" style="font-size:10px;fill:#fff;text-anchor:middle;font-weight:700">${n.tk}</text></g>`:''}</g></g>`}
  const w=n.w,hh=n.h,x=-w/2,y=-hh/2;
  return `<g class="n ${n.cls||''}" data-id="${h(n.id)}" transform="translate(${n.x},${n.y})"><g class="in" ${st}>
    <rect class="frame" x="${x}" y="${y}" width="${w}" height="${hh}" rx="9" fill="#151F38" stroke="#26324F"/>
    <rect x="${x}" y="${y}" width="4" height="${hh}" rx="2" fill="${n.c}"/>
    <text class="t-ty" x="${x+14}" y="${y+16}" fill="${n.c}">${h(n.ty||'')}</text>
    <text class="t-tt" x="${x+14}" y="${y+(n.sub?37:41)}">${h(fitTxt(n.title,(w-34)/15))}</text>
    ${n.sub?`<text class="t-st" x="${x+14}" y="${y+56}">${h(fitTxt(n.sub,(w-30)/12.5))}</text>`:''}
    ${n.dot?`<circle cx="${x+w-12}" cy="${y+12}" r="4" fill="${n.dot}"/>`:''}
    ${n.tk?`<g transform="translate(${x+w-12},${y+hh-12})"><circle r="9" fill="#F87171"/><text y="4" style="font-size:10px;fill:#fff;text-anchor:middle;font-weight:700">${n.tk}</text></g>`:''}</g></g>`}
function atlLegend(items){$('#atlLg').innerHTML=items.map(([c,t])=>`<span><i style="background:${c}"></i>${t}</span>`).join('')}
// ---- viewport
function atlApply(){const vp=$('#atlVp');if(!vp)return;vp.setAttribute('transform',`translate(${AT.x},${AT.y}) scale(${AT.k})`);const s=$('#atlSvg');s.classList.toggle('far',AT.k<.45);s.classList.toggle('mid',AT.k>=.45&&AT.k<.85)}
function atlFit(ids,pad,maxK,minK){
  const ns=(ids&&ids.length?ids.map(i=>AT.N[i]).filter(Boolean):Object.values(AT.N));if(!ns.length)return;
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;ns.forEach(n=>{const rw=(n.w||n.r*2+40)/2,rh=(n.h||n.r*2+40)/2;x0=Math.min(x0,n.x-rw);x1=Math.max(x1,n.x+rw);y0=Math.min(y0,n.y-rh);y1=Math.max(y1,n.y+rh)});
  const r=$('#atlSvg').getBoundingClientRect(),p=pad==null?40:pad,W=Math.max(r.width,200),H=Math.max(r.height,200);
  const k=Math.min(maxK||1.3,(W-p*2)/Math.max(x1-x0,1),(H-p*2)/Math.max(y1-y0,1));
  if(minK&&k<minK)return atlTo(minK,p-x0*minK,p+30-y0*minK);  // too big to read whole: start readable at the top left
  atlTo(k,W/2-(x0+x1)/2*k,H/2-(y0+y1)/2*k)}
function atlTo(k,x,y){const a={k:AT.k,x:AT.x,y:AT.y},t0=performance.now(),id=++AT.anim;
  const step=t=>{if(id!==AT.anim)return;const u=Math.min(1,(t-t0)/480),e=1-Math.pow(1-u,3);AT.k=a.k+(k-a.k)*e;AT.x=a.x+(x-a.x)*e;AT.y=a.y+(y-a.y)*e;atlApply();if(u<1)requestAnimationFrame(step)};requestAnimationFrame(step)}
function atlBind(){
  const svg=$('#atlSvg');
  svg.addEventListener('wheel',e=>{e.preventDefault();AT.anim++;const r=svg.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top;
    const k=Math.max(.08,Math.min(4,AT.k*Math.exp(-e.deltaY*.0016)));AT.x=px-(px-AT.x)*k/AT.k;AT.y=py-(py-AT.y)*k/AT.k;AT.k=k;atlApply()},{passive:false});
  svg.addEventListener('pointerdown',e=>{AT.drag={x:e.clientX,y:e.clientY,ox:AT.x,oy:AT.y};AT.moved=0;AT.anim++});
  if(!window.atlDragOn){window.atlDragOn=1;
    window.addEventListener('pointermove',e=>{const d=AT.drag,s=$('#atlSvg');if(!d||!s)return;const dx=e.clientX-d.x,dy=e.clientY-d.y;if(Math.abs(dx)+Math.abs(dy)>4){AT.moved=1;s.classList.add('drag')}
      if(AT.moved){AT.x=d.ox+dx;AT.y=d.oy+dy;atlApply()}});
    window.addEventListener('pointerup',()=>{AT.drag=null;const s=$('#atlSvg');if(s)s.classList.remove('drag')})}
  svg.addEventListener('click',e=>{if(AT.moved)return;const g=e.target.closest('.n');atlSel(g?g.dataset.id:'');if(!g)atlSide()});
  svg.addEventListener('dblclick',e=>{const g=e.target.closest('.n');if(g)atlOpen(g.dataset.id)});
  svg.addEventListener('mouseover',e=>{const g=e.target.closest('.n');if(g&&!AT.sel)atlFocus(g.dataset.id)});
  svg.addEventListener('mouseout',e=>{const g=e.target.closest('.n');if(g&&!AT.sel&&!(e.relatedTarget&&e.relatedTarget.closest&&e.relatedTarget.closest('.n')===g))atlFocus('')});
  document.querySelectorAll('.atl-zm button').forEach(b=>b.onclick=()=>{const z=+b.dataset.z;if(!z)return atlFit();const r=svg.getBoundingClientRect(),cx=r.width/2,cy=r.height/2,k=AT.k*z;atlTo(k,cx-(cx-AT.x)*z,cy-(cy-AT.y)*z)});
  $('#atlTour').onclick=()=>AT.tour?atlTourStop():atlTourStart();
  $('#atlTk').onclick=()=>{$('#atlTk').classList.toggle('on');AT.onlyT=$('#atlTk').classList.contains('on');vAtlas(AT.arg)};
  const q=$('#atlQ'),res=$('#atlRes');let hits=[],cur=0;
  const paint=()=>{res.hidden=!hits.length;res.innerHTML=hits.map((x,i)=>`<button class="${i===cur?'on':''}" data-i="${i}"><i style="background:${x.c}22;color:${x.c}">${x.k}</i><span>${h(x.t)}</span><small>${h(x.s||'')}</small></button>`).join('');
    res.querySelectorAll('button').forEach(b=>b.onmousedown=ev=>{ev.preventDefault();go(hits[+b.dataset.i])})};
  const go=x=>{res.hidden=true;q.value='';q.blur();if(x.k==='表'){if(AT.view!=='all')location.hash='#/atlas';setTimeout(()=>{atlSel(x.id);atlFit([x.id,...AT.adj[x.id]||[]],80,1.4)},AT.view==='all'?0:400)}else location.hash='#/atlas/'+encodeURIComponent(x.id)};
  q.oninput=()=>{const s=q.value.trim().toLowerCase();cur=0;if(!s){hits=[];return paint()}const D=AT.d,m=t=>(t||'').toLowerCase().includes(s);
    hits=[...D.domains.filter(d=>m(d.title)||m(d.id)).map(d=>({k:'业务域',id:d.id,t:d.title,s:d.flows+' 流',c:'#E8B86D'})),
      ...D.flows.filter(f=>m(f.title)||m(f.entry)||m(f.id)).map(f=>({k:'业务流',id:f.id,t:f.title,s:f.entry,c:'#F5A3B5'})),
      ...D.tables.filter(t=>m(t.name)||m(t.label)).map(t=>({k:'表',id:'tbl:'+t.name,t:t.name+(t.label?' '+t.label:''),s:t.flows+' 流',c:'#5EEAD4'}))].slice(0,14);paint()};
  q.onkeydown=e=>{if(e.key==='ArrowDown'){cur=Math.min(hits.length-1,cur+1);paint();e.preventDefault()}else if(e.key==='ArrowUp'){cur=Math.max(0,cur-1);paint();e.preventDefault()}
    else if(e.key==='Enter'&&hits[cur])go(hits[cur]);else if(e.key==='Escape'){q.value='';hits=[];paint();q.blur()}};
  q.onblur=()=>setTimeout(()=>res.hidden=true,150);
  if(!window.atlKeys){window.atlKeys=1;document.addEventListener('keydown',e=>{if(!$('#atl')||/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))return;
    if(e.key==='/'){e.preventDefault();$('#atlQ').focus()}else if(e.key==='Escape'){if(AT.tour)atlTourStop();else{atlSel('');atlSide()}}
    else if(AT.tour&&e.key==='ArrowRight')atlTourGo(AT.tour.i+1);else if(AT.tour&&e.key==='ArrowLeft')atlTourGo(AT.tour.i-1)})}}
function atlFocus(id){const s=$('#atlSvg');if(!id){s.classList.remove('dim');document.querySelectorAll('#atl .hi').forEach(x=>x.classList.remove('hi'));return}
  const keep=new Set([id,...(AT.adj[id]||[])]);s.classList.add('dim');
  document.querySelectorAll('#atlN .n').forEach(g=>g.classList.toggle('hi',keep.has(g.dataset.id)));
  document.querySelectorAll('#atlE [data-i]').forEach(p=>{const e=AT.E[+p.dataset.i];p.classList.toggle('hi',e.a===id||e.b===id)})}
function atlSel(id){AT.sel=id;document.querySelectorAll('#atlN .n').forEach(g=>g.classList.toggle('sel',g.dataset.id===id));atlFocus(id);if(id)atlSide(id)}
function atlOpen(id){if(id.startsWith('dom:'))location.hash='#/atlas/'+encodeURIComponent(id);else if(id.startsWith('flow:'))location.hash='#/atlas/'+encodeURIComponent(id)}
// ---- level 1: 全景
function atlAll(){
  AT.view='all';AT.arg='';const D=AT.d;atlCrumb([]);
  let doms=D.domains.filter(d=>!AT.onlyT||d.tickets);const dset=new Set(doms.map(d=>d.id));
  const R=d=>Math.min(70,20+Math.sqrt(d.flows)*5.5);
  const own={};D.tables.forEach(t=>{const ds=Object.keys(t.domains).filter(x=>dset.has(x));if(!ds.length)return;if(AT.onlyT&&!D.flows.some(f=>f.tickets.length&&f.crud[t.name]!=null))return;
    ds.sort((a,b)=>t.domains[b].length-t.domains[a].length);t.home=ds[0];t.also=ds.slice(1);(own[ds[0]]=own[ds[0]]||[]).push(t)});
  const E=d=>R(d)+26+Math.sqrt((own[d.id]||[]).length)*11;
  // place domains: a small force simulation (domains only; tables follow their domains)
  const P=doms.map((d,i)=>{const a=i/Math.max(doms.length,1)*Math.PI*2;return {d,x:Math.cos(a)*260*Math.sqrt(doms.length),y:Math.sin(a)*200*Math.sqrt(doms.length),vx:0,vy:0}});
  const ix={};P.forEach((p,i)=>ix[p.d.id]=i);const L=D.links.filter(l=>dset.has(l.a)&&dset.has(l.b));
  // only the strongest links per domain are drawn (and pull), so a big project does not turn into a hairball
  const keep=new Set();doms.forEach(d=>L.filter(l=>l.a===d.id||l.b===d.id).sort((a,b)=>b.n-a.n).slice(0,3).forEach(l=>keep.add(l)));const K=L.filter(l=>keep.has(l));
  for(let it=0;it<420;it++){const cool=1-it/420;
    for(let i=0;i<P.length;i++)for(let j=i+1;j<P.length;j++){const a=P[i],b=P[j];let dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;const min=E(a.d)+E(b.d)+40;
      let f=9000/(d*d);if(d<min)f+=(min-d)*.5;dx/=d;dy/=d;a.vx-=dx*f;a.vy-=dy*f;b.vx+=dx*f;b.vy+=dy*f}
    K.forEach(l=>{const a=P[ix[l.a]],b=P[ix[l.b]];let dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;const t=E(a.d)+E(b.d)+50,f=(d-t)*.012*Math.min(l.n,6);dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f});
    P.forEach(p=>{p.vx-=p.x*.004;p.vy-=p.y*.006;p.x+=p.vx*.5*cool;p.y+=p.vy*.5*cool;p.vx*=.55;p.vy*=.55})}
  const nodes=[],edges=[];
  P.forEach(p=>{const d=p.d,c=domCol(d.id);nodes.push({id:d.id,shape:'circle',x:p.x,y:p.y,r:R(d),c,title:fitTxt(d.title,8),sub:`${d.flows} 流 · ${d.tables} 表`,tk:d.tickets,fo:.22,cls:'dom'});
    (own[d.id]||[]).sort((a,b)=>b.flows-a.flows).forEach((t,i)=>{const a=i*2.39996+ix[d.id],rr=R(d)+30+Math.sqrt(i)*13;
      nodes.push({id:'tbl:'+t.name,shape:'circle',x:p.x+Math.cos(a)*rr,y:p.y+Math.sin(a)*rr,r:Math.min(9,3.5+Math.sqrt(t.flows)*1.4),c:t.write?'#5EEAD4':'#3B8F86',fo:.85,small:1,title:fitTxt(t.label||t.name,9),tc:'t-tb'});
      edges.push({a:d.id,b:'tbl:'+t.name,c,o:.16,w:.8});
      t.also.forEach(o=>edges.push({a:o,b:'tbl:'+t.name,c:domCol(o),o:.07,w:.8,curve:'q'}))})});
  K.forEach(l=>edges.push({a:l.a,b:l.b,c:'#E8B86D',o:.75,w:Math.min(1+Math.log2(l.n+1),5),dash:'6 6',cls:'flowing',curve:'q',label:`共享 ${l.n} 张表`}));
  atlDraw(nodes,edges);atlFit(null,50,1.1);
  $('#atlTl').innerHTML=`<b>${D.stats.domains}</b> 业务域 · <b>${D.stats.flows}</b> 业务流 · <b>${D.stats.tables}</b> 张表 · <b>${D.stats.methods}</b> 个方法${D.stats.tickets?` · <b style="color:#F87171">${D.stats.tickets}</b> 单在办`:''}`;
  atlLegend([['#E8B86D','业务域（大小=业务流数）'],['#5EEAD4','数据表（亮=有写入）'],['#E8B86D','金色虚线：两个域共用表'],['#F87171','红圈：有在办工单']]);
  atlSide()}
// ---- level 2: 业务域
function atlDom(id){
  AT.view='dom';AT.arg=id;const D=AT.d,d=D.dm[id];if(!d){location.hash='#/atlas';return}
  atlCrumb([`<b>${h(d.title)}</b>`]);
  let fl=D.flows.filter(f=>f.domain===id&&(!AT.onlyT||f.tickets.length));fl.sort((a,b)=>(a.kind||'').localeCompare(b.kind||'')||b.tickets.length-a.tickets.length||a.title.localeCompare(b.title));
  const per=fl.length>40?14:24,FW=290,FH=66,cols=Math.max(1,Math.ceil(fl.length/per)),nodes=[],edges=[],c=domCol(id);
  const rows=Math.min(per,fl.length);
  fl.forEach((f,i)=>{const col=Math.floor(i/per),row=i%per;
    nodes.push({id:f.id,x:col*(FW+40),y:row*(FH+14),w:FW,h:FH,c:'#F5A3B5',ty:'业务流'+(f.kind?' · '+f.kind:''),title:f.title,sub:f.entry,dot:STC[f.status],tk:f.tickets.length})});
  const tb={};fl.forEach((f,i)=>Object.entries(f.crud).forEach(([t,o])=>{(tb[t]=tb[t]||{n:t,ix:[],w:false}).ix.push(i%per);if(isW(o))tb[t].w=true}));
  const ts=Object.values(tb).sort((a,b)=>b.ix.length-a.ix.length||a.n.localeCompare(b.n));
  // tables: one column beside a small domain (ordered to cut crossings), a block of columns beside a big one
  const tper=Math.max(per,Math.ceil(ts.length/Math.max(1,Math.ceil(ts.length/per)))),TX=cols*(FW+40)+FW/2+150;
  if(ts.length<=per)ts.sort((a,b)=>a.ix.reduce((s,x)=>s+x,0)/a.ix.length-b.ix.reduce((s,x)=>s+x,0)/b.ix.length);
  const gap=ts.length>1&&ts.length<=per?Math.min(104,Math.max(FH+4,rows*(FH+14)/ts.length)):FH+14,t0=ts.length<=per?(rows-1)*(FH+14)/2-(ts.length-1)*gap/2:0;
  ts.forEach((t,i)=>{const T=D.tm[t.n]||{},others=Object.keys(T.domains||{}).filter(x=>x!==id),col=Math.floor(i/tper),row=i%tper;
    nodes.push({id:'tbl:'+t.n,x:TX+col*290,y:t0+row*gap,w:250,h:FH-4,c:'#5EEAD4',ty:'数据表'+(t.w?' · 有写入':''),title:t.n+(T.label?' '+T.label:''),sub:others.length?'也被 '+others.map(x=>(D.dm[x]||{}).title||x).join('、')+' 使用':'只在本域使用'})});
  fl.forEach(f=>Object.entries(f.crud).forEach(([t,o])=>edges.push({a:f.id,b:'tbl:'+t,c:opCol(o),o:fl.length>40?.16:.35,w:1.1,curve:'h'})));
  atlDraw(nodes,edges);atlFit(null,40,1,.62);
  $('#atlTl').innerHTML=`<b style="color:${c}">${h(d.title)}</b> · ${fl.length} 条业务流 · ${ts.length} 张表 · 双击业务流看代码链路`;
  atlLegend([['#F5A3B5','业务流'],['#5EEAD4','数据表'],['#FBBF24','黄线：写入'],['#5EEAD4','青线：读取'],['#4ADE80','绿点：知识页已确认']]);
  atlSide(id)}
// ---- level 3: 业务流的代码链路
async function atlFlow(id){
  AT.view='flow';AT.arg=id;const D=AT.d,f0=D.fm[id];
  const F=await get('/api/projects/'+S.proj+'/atlas/flow/'+encodeURIComponent(id));AT.flow=F;
  const dm=f0&&D.dm[f0.domain];atlCrumb([dm?`<a href="#/atlas/${encodeURIComponent(dm.id)}">${h(dm.title)}</a>`:'',`<b>${h(F.title)}</b>`].filter(Boolean));
  // vertical layers: entry on top, then one band per layer (入口/业务/数据/其他), tables and outside calls at the bottom
  const W=250,H=66,GX=36,GY=70,PER=4,nodes=[],edges=[];const order=['入口','业务','数据','其他'];
  let y=0;const band=(items,w,per)=>{const rows=Math.ceil(items.length/per);items.forEach((it,i)=>{const r=Math.floor(i/per),inRow=Math.min(per,items.length-r*per),c=i%per;
    it.x=(c-(inRow-1)/2)*(w+GX);it.y=y+r*(H+24);nodes.push(it)});y+=rows*(H+24)-24+GY};
  band([{id:'ep',w:W+40,h:H,c:'#FDBA74',ty:'入口'+(F.kind?' · '+F.kind:''),title:F.entry||F.title,sub:F.handler}],W,1);
  order.forEach(l=>{const ss=F.steps.filter(s=>s.layer===l);if(!ss.length)return;
    band(ss.map(s=>({id:s.id,w:W,h:H,c:LCOL[s.layer],ty:`第 ${F.steps.indexOf(s)+1} 步 · ${s.layer}层`,title:s.label,sub:s.comment||(s.file.split('/').pop()+':'+s.line)})),W,PER)});
  const ids=new Set(F.steps.map(s=>s.id)),hasIn=new Set();
  F.steps.forEach(s=>s.calls.forEach(t=>{if(ids.has(t)&&t!==s.id){edges.push({a:s.id,b:t,c:'#A5B4FC',o:.7,w:1.4,curve:'v',cls:'flowing'});hasIn.add(t)}}));
  if(F.steps[0]){edges.push({a:'ep',b:F.steps[0].id,c:'#FDBA74',o:.8,w:1.6,curve:'v',cls:'flowing'});hasIn.add(F.steps[0].id)}
  F.steps.forEach((s,i)=>{if(i&&!hasIn.has(s.id))edges.push({a:F.steps[i-1].id,b:s.id,c:'#64748B',o:.5,w:1,curve:'v',dash:'3 5'})});
  const tabs=Object.keys(F.crud),fx=[...new Set(F.steps.flatMap(s=>s.effects))];
  band([...tabs.map(t=>{const T=D.tm[t]||{};return {id:'tbl:'+t,w:220,h:H-6,c:'#5EEAD4',ty:'数据表 · '+String(F.crud[t]).split('').map(o=>OPN[o]||o).join(''),title:t+(T.label?' '+T.label:''),sub:T.summary||''}}),
    ...fx.map(x=>({id:'fx:'+x,w:220,h:H-6,c:'#7DD3FC',ty:'外部调用',title:x}))],220,5);
  F.steps.forEach(s=>{s.io.forEach(io=>{if(F.crud[io.table]!=null)edges.push({a:s.id,b:'tbl:'+io.table,c:opCol(io.op),o:.75,w:1.4,curve:'v',label:OPN[io.op]||io.op,lc:'hi'})});s.effects.forEach(x=>edges.push({a:s.id,b:'fx:'+x,c:'#7DD3FC',o:.6,w:1.2,curve:'v',dash:'4 4'}))});
  if(!F.steps.some(s=>s.io.length))tabs.forEach(t=>{const last=F.steps[F.steps.length-1];if(last)edges.push({a:last.id,b:'tbl:'+t,c:opCol(F.crud[t]),o:.5,w:1.1,curve:'v',dash:'3 5'})});
  // open tickets stack to the left of the entry; past a few they fold into one "+N" card (the full list is in the side panel)
  const tks=F.tickets.slice(0,F.tickets.length>3?2:3),TX=-(W+40)/2-GX-W/2-30;
  const tk=(id,i,o)=>{nodes.push(Object.assign({id,x:TX,y:i*(H+8),w:W,h:H-6,c:'#F87171'},o));edges.push({a:id,b:'ep',c:'#F87171',o:.5,w:1,dash:'4 4',curve:'h'})};
  tks.forEach((t,i)=>tk('tk:'+t.key,i,{ty:'在办工单 · '+(S.meta.statuses.find(x=>x[0]===t.status)||[0,t.status])[1],title:t.key+' '+t.title}));
  if(F.tickets.length>tks.length)tk('tkmore',tks.length,{ty:'在办工单',title:`还有 ${F.tickets.length-tks.length} 张`,sub:'右侧列表里看全部'});
  atlDraw(nodes,edges);atlFit(null,40,1.05,.55);
  $('#atlTl').innerHTML=`<b style="color:#F5A3B5">${h(F.title)}</b> · ${F.steps.length} 步 · ${tabs.length} 张表${F.unresolved?` · <span style="color:#FBBF24">${F.unresolved} 处静态分析断开</span>`:''}`;
  atlLegend([['#FDBA74','入口'],['#A78BFA','业务层'],['#6EE7B7','数据层'],['#5EEAD4','数据表'],['#7DD3FC','外部调用'],['#F87171','在办工单']]);
  atlSide(id)}
// ---- side panel
function atlSide(id){
  const D=AT.d,el=$('#atlSide');const tour=AT.tour?atlTourCard():'';
  const kb=pid=>`<a href="#/kb/${encodeURIComponent(pid)}">阅读知识页</a>`;
  const tkl=ts=>ts.length?`<h4>在办工单</h4>`+ts.map(t=>`<a class="li" href="#/t/${h(t.key)}"><i class="dot" style="background:#F87171"></i><span>${h(t.key)} ${h(t.title)}</span><small>${h((S.meta.statuses.find(x=>x[0]===t.status)||[0,t.status])[1])}</small></a>`).join(''):'';
  if(!id){id=AT.view==='dom'||AT.view==='flow'?AT.arg:''}
  if(!id){const top=D.domains.slice().sort((a,b)=>b.tickets-a.tickets||b.flows-a.flows).slice(0,8);
    el.innerHTML=tour+`<div class="ty" style="color:#E8B86D">项目全景</div><h3>${h(D.project.name||D.project.key)}</h3>${D.project.summary?`<p>${h(D.project.summary)}</p>`:''}
      <div class="kv"><div><b>${D.stats.domains}</b><span>业务域</span></div><div><b>${D.stats.flows}</b><span>业务流</span></div><div><b>${D.stats.tables}</b><span>数据表</span></div>
      <div><b>${D.stats.methods}</b><span>方法</span></div><div><b>${D.stats.written}</b><span>已写说明</span></div><div><b style="color:${D.stats.tickets?'#F87171':''}">${D.stats.tickets}</b><span>在办工单</span></div></div>
      <h4>业务域</h4>${top.map(d=>`<div class="li" data-go="${h(d.id)}"><i class="dot" style="background:${domCol(d.id)}"></i><span>${h(d.title)}</span><small>${d.flows} 流${d.tickets?` · <b style="color:#F87171">${d.tickets} 单</b>`:''}</small></div>`).join('')}
      <p style="color:#8E9BB8;font-size:12px;margin-top:14px">单击看详情，双击进入；滚轮缩放，拖动平移；按 / 搜索。图里的连线都来自代码解析，说明文字来自知识库。</p>`}
  else if(id.startsWith('dom:')){const d=D.dm[id];if(!d)return;const fl=D.flows.filter(f=>f.domain===id).sort((a,b)=>b.tickets.length-a.tickets.length||a.title.localeCompare(b.title));
    const lk=D.links.filter(l=>l.a===id||l.b===id).map(l=>({o:l.a===id?l.b:l.a,l})).sort((a,b)=>b.l.n-a.l.n);
    el.innerHTML=tour+`<div class="ty" style="color:${domCol(id)}">业务域</div><h3>${h(d.title)}</h3>${d.summary?`<p>${h(d.summary)}</p>`:'<p style="color:#8E9BB8">这个业务域还没写业务说明。</p>'}
      <div class="kv"><div><b>${d.flows}</b><span>业务流</span></div><div><b>${d.tables}</b><span>数据表</span></div><div><b style="color:${d.tickets?'#F87171':''}">${d.tickets}</b><span>在办工单</span></div></div>
      <div class="acts">${AT.view!=='dom'?`<button class="pri" data-go="${h(id)}">进入业务域</button>`:''}${id!=='dom:_'?kb(id):''}</div>
      ${lk.length?`<h4>和哪些业务域共用数据</h4>`+lk.slice(0,6).map(x=>`<div class="li" data-go="${h(x.o)}"><i class="dot" style="background:${domCol(x.o)}"></i><span>${h((D.dm[x.o]||{}).title||x.o)}</span><small title="${h(x.l.tables.join('、'))}">${x.l.n} 张表</small></div>`).join(''):''}
      <h4>业务流 · ${fl.length}</h4>${fl.slice(0,40).map(f=>`<div class="li" data-go="${h(f.id)}"><i class="dot" style="background:${STC[f.status]}"></i><span>${h(f.title)}</span><small>${f.tickets.length?`<b style="color:#F87171">${f.tickets.length} 单</b>`:h(f.kind||'')}</small></div>`).join('')}`}
  else if(id.startsWith('flow:')){const f=D.fm[id]||{},F=AT.flow&&AT.flow.id===id?AT.flow:null;
    el.innerHTML=tour+`<div class="ty" style="color:#F5A3B5">业务流${f.kind?' · '+h(f.kind):''}</div><h3>${h(f.title||id)}</h3>
      ${f.entry?`<p><code>${h(f.entry)}</code></p>`:''}${f.summary?`<p>${h(f.summary)}</p>`:'<p style="color:#8E9BB8">还没写业务说明，下面是代码事实。</p>'}
      <div>${Object.entries(f.crud||{}).map(([t,o])=>`<span class="chip" style="border-color:${opCol(o)}55">${h(t)} <b style="color:${opCol(o)}">${String(o).split('').map(x=>OPN[x]||x).join('')}</b></span>`).join('')}</div>
      <p style="color:#8E9BB8;font-size:12px">知识页：${h(f.status||'')} · 代码 <code>${h((f.file||'').split('/').pop())}:${f.line||''}</code>${f.unresolved?` · <span style="color:#FBBF24">${f.unresolved} 处断开需人工确认</span>`:''}</p>
      <div class="acts">${AT.view!=='flow'?`<button class="pri" data-go="${h(id)}">看代码链路</button>`:`<button class="pri" data-tour="1">▶ 一步步讲解</button>`}${kb(id)}</div>
      ${tkl(f.tickets||[])}${F?`<h4>执行步骤 · ${F.steps.length}</h4>`+F.steps.map((s,i)=>`<div class="li" data-pick="${h(s.id)}"><i class="dot" style="background:${LCOL[s.layer]}"></i><span>${i+1}. ${h(s.label)}</span><small>${h(s.layer)}</small></div>`).join(''):''}`}
  else if(id.startsWith('tbl:')){const t=D.tm[id.slice(4)]||{name:id.slice(4),domains:{}};const fl=D.flows.filter(f=>f.crud[t.name]!=null);
    el.innerHTML=tour+`<div class="ty" style="color:#5EEAD4">数据表</div><h3>${h(t.name)}</h3>${t.label?`<p>${h(t.label)}</p>`:''}${t.summary?`<p>${h(t.summary)}</p>`:''}
      <div class="kv"><div><b>${fl.length}</b><span>业务流使用</span></div><div><b>${fl.filter(f=>isW(f.crud[t.name])).length}</b><span>会写入</span></div><div><b>${Object.keys(t.domains).length}</b><span>业务域</span></div></div>
      <div class="acts">${kb(id)}</div>
      <h4>影响面：改这张表会碰到</h4>${fl.slice(0,40).map(f=>`<div class="li" data-go="${h(f.id)}"><i class="dot" style="background:${opCol(f.crud[t.name])}"></i><span>${h(f.title)}</span><small>${String(f.crud[t.name]).split('').map(x=>OPN[x]||x).join('')}${f.tickets.length?` · <b style="color:#F87171">${f.tickets.length} 单</b>`:''}</small></div>`).join('')}`}
  else if(id==='ep'&&AT.flow){const F=AT.flow;el.innerHTML=tour+`<div class="ty" style="color:#FDBA74">入口</div><h3>${h(F.entry||F.title)}</h3><p>处理方法 <code>${h(F.handler)}</code></p><p><code>${h(F.file)}:${F.line}</code></p>`}
  else if(id.startsWith('tk:')){location.hash='#/t/'+id.slice(3);return}
  else if(id==='tkmore'){return atlSide(AT.arg)}
  else if(AT.flow){const s=AT.flow.steps.find(x=>x.id===id);if(!s)return;const i=AT.flow.steps.indexOf(s);
    el.innerHTML=tour+`<div class="ty" style="color:${LCOL[s.layer]}">第 ${i+1} 步 · ${h(s.layer)}层</div><h3 style="word-break:break-all">${h(s.label)}</h3>${s.comment?`<p>${h(s.comment)}</p>`:''}
      <p><code>${h(s.file)}:${s.line}${s.end>s.line?'-'+s.end:''}</code></p>
      ${s.io.length?`<h4>读写的表</h4>`+s.io.map(x=>`<span class="chip">${h(x.table)} <b style="color:${opCol(x.op)}">${OPN[x.op]||x.op}</b></span>`).join(''):''}
      ${s.effects.length?`<h4>外部调用</h4>`+s.effects.map(x=>`<span class="chip">${h(x)}</span>`).join(''):''}`}
  el.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{location.hash='#/atlas/'+encodeURIComponent(b.dataset.go)});
  el.querySelectorAll('[data-pick]').forEach(b=>b.onclick=()=>{atlSel(b.dataset.pick);atlFit([b.dataset.pick],80,1.2)});
  el.querySelectorAll('[data-tour]').forEach(b=>b.onclick=atlTourStart);
  el.querySelectorAll('[data-tn]').forEach(b=>b.onclick=()=>atlTourGo(AT.tour.i+(+b.dataset.tn)));
  el.querySelectorAll('[data-tx]').forEach(b=>b.onclick=atlTourStop)}
// ---- 讲解: walk the current picture in a sensible order, one node at a time
function atlTourStart(){
  const D=AT.d;let items=[];
  if(AT.view==='flow'&&AT.flow){const F=AT.flow;items=[{id:'ep',t:'从这里进来',x:`${F.entry||''}，由 ${F.handler||'处理方法'} 接住。`}].concat(F.steps.map((s,i)=>({id:s.id,t:`第 ${i+1} 步：${s.label}`,
    x:`${s.layer}层。${s.comment?s.comment+'。':''}${s.io.length?'读写 '+s.io.map(x=>x.table+(OPN[x.op]?'（'+OPN[x.op]+'）':'')).join('、')+'。':''}${s.effects.length?'调用 '+s.effects.join('、')+'。':''}代码在 ${s.file.split('/').pop()}:${s.line}。`})))
    .concat(Object.keys(F.crud).map(t=>({id:'tbl:'+t,t:'落到数据表 '+t,x:`这条业务流对 ${t} 做「${String(F.crud[t]).split('').map(o=>OPN[o]||o).join('、')}」。${(D.tm[t]||{}).summary||''}`})))}
  else if(AT.view==='dom'){const d=D.dm[AT.arg];items=D.flows.filter(f=>f.domain===AT.arg).sort((a,b)=>b.tickets.length-a.tickets.length||(a.kind||'').localeCompare(b.kind||'')).slice(0,12)
    .map(f=>({id:f.id,t:f.title,x:(f.summary||'入口 '+f.entry)+`。用到 ${Object.keys(f.crud).join('、')||'没有表'}。`+(f.tickets.length?` 有 ${f.tickets.length} 张在办工单。`:'')}));if(d)items.unshift({id:items[0]&&items[0].id,t:d.title,x:d.summary||`这个业务域有 ${d.flows} 条业务流、${d.tables} 张表。`,all:1})}
  else items=D.domains.slice().sort((a,b)=>b.flows-a.flows).slice(0,12).map(d=>({id:d.id,t:d.title,x:(d.summary||`${d.flows} 条业务流，用到 ${d.tables} 张表。`)+(d.tickets?` 现在有 ${d.tickets} 张在办工单。`:'')}));
  items=items.filter(x=>x.id&&AT.N[x.id]);if(!items.length){toast('这一层没有可以讲解的内容');return}
  AT.tour={items,i:0};$('#atlTour').classList.add('on');$('#atlTour').textContent='■ 结束讲解';atlTourGo(0)}
function atlTourGo(i){const T=AT.tour;if(!T)return;T.i=Math.max(0,Math.min(T.items.length-1,i));const it=T.items[T.i];
  document.querySelectorAll('#atlN .n.pulse').forEach(g=>g.classList.remove('pulse'));
  if(it.all){atlSel('');atlFit(null,40,1)}else{atlSel(it.id);const g=document.querySelector(`#atlN .n[data-id="${CSS.escape(it.id)}"]`);if(g)g.classList.add('pulse');atlFit([it.id,...AT.adj[it.id]||[]],90,1.25)}
  atlSide(it.all?'':it.id)}
function atlTourStop(){AT.tour=null;$('#atlTour').classList.remove('on');$('#atlTour').textContent='▶ 讲解';document.querySelectorAll('#atlN .n.pulse').forEach(g=>g.classList.remove('pulse'));atlSel('');atlSide()}
function atlTourCard(){const T=AT.tour,it=T.items[T.i];return `<div class="tour"><div class="ty" style="color:#E8B86D">讲解 ${T.i+1} / ${T.items.length}</div><b style="font-size:15px">${h(it.t)}</b>
  <div class="bar"><i style="width:${(T.i+1)/T.items.length*100}%"></i></div><p>${h(it.x)}</p>
  <div class="acts"><button data-tn="-1" ${T.i?'':'disabled'}>← 上一步</button><button class="pri" data-tn="1" ${T.i<T.items.length-1?'':'disabled'}>下一步 →</button><button data-tx="1">结束</button></div></div>`}
"""
