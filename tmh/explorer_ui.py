"""CSS and JavaScript of the explorer (see explorer.py). Plain browser JS, no libraries, works from file://."""

APP_CSS = r"""
:root{--bg:#f6f5f1;--panel:#fff;--ink:#1d2321;--sub:#5d6662;--faint:#8b938f;--line:#e2e0d8;--soft:#efede6;
--accent:#1f6f5c;--accent-soft:#e1efe9;--warn:#a85a12;--warn-soft:#f8ead9;--bad:#a8322a;--bad-soft:#f7e1de;--info:#2d5b8a;--info-soft:#e2ebf5;
--c:#2e7d4f;--r:#5d6662;--u:#2d5b8a;--d:#a8322a;--p:#7a4fa0;
--l-entry:#1f6f5c;--l-service:#2d5b8a;--l-dao:#7a4fa0;--l-table:#a85a12;--l-dispatch:#a8322a;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141816;--panel:#1c211f;--ink:#e6e9e7;--sub:#a3aca8;--faint:#77807c;--line:#2e3532;--soft:#232926;
--accent:#5fbf9f;--accent-soft:#1d332b;--warn:#e0a060;--warn-soft:#3a2c1c;--bad:#ec7f75;--bad-soft:#3b2220;--info:#82aee0;--info-soft:#1d2a3a;
--c:#6fcf97;--r:#a3aca8;--u:#82aee0;--d:#ec7f75;--p:#c39be6;--l-entry:#5fbf9f;--l-service:#82aee0;--l-dao:#c39be6;--l-table:#e0a060;--l-dispatch:#ec7f75;color-scheme:dark}}
:root[data-theme=dark]{--bg:#141816;--panel:#1c211f;--ink:#e6e9e7;--sub:#a3aca8;--faint:#77807c;--line:#2e3532;--soft:#232926;
--accent:#5fbf9f;--accent-soft:#1d332b;--warn:#e0a060;--warn-soft:#3a2c1c;--bad:#ec7f75;--bad-soft:#3b2220;--info:#82aee0;--info-soft:#1d2a3a;
--c:#6fcf97;--r:#a3aca8;--u:#82aee0;--d:#ec7f75;--p:#c39be6;--l-entry:#5fbf9f;--l-service:#82aee0;--l-dao:#c39be6;--l-table:#e0a060;--l-dispatch:#ec7f75;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 -apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code,pre,.mono{font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:12.5px}
header.top{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header.top .brand{font-weight:650;font-size:15px;cursor:pointer}
header.top .brand small{font-weight:400;color:var(--faint);margin-left:8px}
.searchbox{position:relative;flex:1;min-width:220px;max-width:560px}
.searchbox input{width:100%;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}
.results{position:absolute;left:0;right:0;top:40px;background:var(--panel);border:1px solid var(--line);border-radius:8px;max-height:60vh;overflow:auto;box-shadow:0 8px 28px rgba(0,0,0,.14)}
.results div{padding:7px 12px;cursor:pointer;border-bottom:1px solid var(--soft)}.results div:hover,.results div.on{background:var(--accent-soft)}
.results b{font-weight:600}.results .k{display:inline-block;min-width:44px;font-size:11px;color:var(--faint)}
.top .sp{flex:1}.btn{border:1px solid var(--line);background:var(--panel);color:var(--sub);border-radius:7px;padding:5px 10px;cursor:pointer;font:inherit;font-size:13px}
.btn.on,.btn:hover{border-color:var(--accent);color:var(--accent)}
main{max-width:1320px;margin:0 auto;padding:18px 20px 60px}
.crumb{color:var(--faint);font-size:13px;margin-bottom:6px}.crumb a{color:var(--sub)}
h1{font-size:24px;line-height:1.3;margin:0 0 6px;text-wrap:balance}h2{font-size:17px;margin:0 0 10px}h3{font-size:14px;margin:16px 0 6px;color:var(--sub);letter-spacing:.02em}
.lede{color:var(--sub);max-width:70ch}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>*{min-width:0}
.grid2{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:18px}
@media (max-width:980px){.grid2{grid-template-columns:minmax(0,1fr)}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.stats{display:flex;gap:22px;flex-wrap:wrap;margin:12px 0 16px}.stats div{font-variant-numeric:tabular-nums}.stats b{font-size:20px;display:block;line-height:1.2}.stats span{color:var(--faint);font-size:12px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:14px 0 16px;flex-wrap:wrap}
.tabs a{padding:7px 12px;color:var(--sub);border-bottom:2px solid transparent;margin-bottom:-1px}.tabs a.on{color:var(--ink);border-color:var(--accent);font-weight:600}.tabs a:hover{text-decoration:none;color:var(--ink)}
.badge{display:inline-block;font-size:11px;line-height:18px;padding:0 7px;border-radius:9px;background:var(--soft);color:var(--sub);vertical-align:middle;white-space:nowrap}
.b-ok{background:var(--accent-soft);color:var(--accent)}.b-draft{background:var(--info-soft);color:var(--info)}.b-stale,.b-mid{background:var(--warn-soft);color:var(--warn)}.b-high{background:var(--bad-soft);color:var(--bad)}.b-none{background:var(--soft);color:var(--faint)}
.verified{display:inline-block;font-size:11px;padding:0 6px;border-radius:4px;background:var(--accent-soft);color:var(--accent);margin-left:4px;font-family:"SF Mono",Menlo,Consolas,monospace;white-space:nowrap;cursor:help}
.infer{background:linear-gradient(transparent 60%,var(--warn-soft) 60%);}
.infer-tag{display:inline-block;font-size:11px;padding:0 6px;border-radius:4px;background:var(--warn-soft);color:var(--warn);margin-right:4px;font-weight:600}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--sub);margin:4px 0 10px}
.md{max-width:78ch}.md p{margin:6px 0}.md ul,.md ol{margin:6px 0;padding-left:22px}.md li{margin:2px 0}.md h2{font-size:15px;margin:18px 0 6px;padding-top:8px;border-top:1px solid var(--soft)}.md h2:first-child{border:0;margin-top:0;padding-top:0}.md h3{font-size:14px}
.md table,.tbl{border-collapse:collapse;width:100%;font-size:13px}.md td,.md th,.tbl td,.tbl th{border-bottom:1px solid var(--soft);padding:5px 8px;text-align:left;vertical-align:top}.md th,.tbl th{color:var(--faint);font-weight:500;font-size:12px}
.tbl tr.click{cursor:pointer}.tbl tr.click:hover td{background:var(--accent-soft)}
.scroll{overflow-x:auto}
pre.code{background:var(--soft);border-radius:6px;padding:8px 10px;overflow-x:auto;white-space:pre;margin:6px 0}
.empty{color:var(--faint);font-style:normal}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;cursor:pointer;display:flex;flex-direction:column;gap:4px}
.tile:hover{border-color:var(--accent)}.tile .t{font-weight:600;font-size:15px}.tile .k{color:var(--faint);font-size:12px}.tile .s{color:var(--sub);font-size:13px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tile .m{color:var(--faint);font-size:12px;font-variant-numeric:tabular-nums;margin-top:auto}
.bar{height:4px;border-radius:2px;background:var(--soft);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12.5px;background:var(--panel)}.chip small{color:var(--faint);margin-left:4px}
.ops span{display:inline-block;min-width:16px;text-align:center;font:600 11px/16px "SF Mono",Menlo,monospace;border-radius:3px;margin-right:2px;color:#fff}
.oC{background:var(--c)}.oR{background:var(--r)}.oU{background:var(--u)}.oD{background:var(--d)}.oP{background:var(--p)}
.risk{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--soft)}.risk:last-child{border:0}.risk .why{color:var(--sub);font-size:13px}
.flowlist .it{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:8px 10px;border-bottom:1px solid var(--soft);cursor:pointer}.flowlist .it:hover{background:var(--accent-soft)}
.flowlist .nm{font-weight:550}.flowlist .tr{color:var(--faint);font-size:12px;grid-column:1/-1;font-family:"SF Mono",Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.filter{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}.filter input{padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--ink);font:inherit;min-width:220px;flex:1}
.diagram{overflow:auto;border:1px solid var(--soft);border-radius:8px;background:var(--bg);max-height:72vh}
.diagram svg text{font-size:12px;fill:var(--ink)}.diagram svg .sub{fill:var(--faint);font-size:10.5px}
.outline{font-family:"SF Mono",Menlo,Consolas,monospace;font-size:12.5px;line-height:1.7}.outline ul{list-style:none;margin:0;padding-left:18px;border-left:1px dashed var(--line)}.outline>ul{border:0;padding-left:0}
.outline .lay{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}.outline .cm{color:var(--faint);font-family:inherit;margin-left:6px}
.facts h3{margin-top:18px}.loc{color:var(--faint);font-size:12px;font-family:"SF Mono",Menlo,monospace;word-break:break-all}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);gap:18px}@media (max-width:1080px){.split{grid-template-columns:minmax(0,1fr)}}
.side-title{display:flex;align-items:center;gap:8px;margin-bottom:8px}.side-title h2{margin:0}
.arch{width:100%}.arch text{fill:var(--ink);font-size:12px}.arch .sub{fill:var(--faint);font-size:11px}
.note{font-size:12.5px;color:var(--sub);background:var(--soft);border-radius:8px;padding:8px 12px;margin:8px 0}
.more{color:var(--faint);font-size:12px;margin-top:6px}
details summary{cursor:pointer;color:var(--sub)}
"""

APP_JS = r"""
(function(){
var O=window.TMH_OVERVIEW, cache={}, waiting={}, app=document.getElementById('app');
window.TMH={loaded:function(i,d){cache[i]=d;(waiting[i]||[]).forEach(function(f){f(d)});delete waiting[i];}};
function load(i,cb){if(cache[i])return cb(cache[i]);if(waiting[i]){waiting[i].push(cb);return;}waiting[i]=[cb];var s=document.createElement('script');s.src='data/d'+i+'.js';s.onerror=function(){app.querySelector('main').innerHTML='<div class="panel empty">数据文件 data/d'+i+'.js 加载失败。请把 report 整个文件夹放在一起打开。</div>'};document.head.appendChild(s);}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function fmt(n){return (n||0).toLocaleString('zh-CN')}
var LAYER={entry:'入口',service:'服务',dao:'数据访问',table:'表',dispatch:'分派点'};
var OPN={C:'新增',R:'查询',U:'修改',D:'删除',P:'过程'};
function ops(s){return '<span class="ops">'+String(s||'').split('').map(function(c){return '<span class="o'+c+'" title="'+(OPN[c]||c)+'">'+c+'</span>'}).join('')+'</span>'}
function stBadge(st){if(!st)return '<span class="badge b-none">未分析</span>';var c={'已确认':'b-ok','待确认':'b-draft','过期':'b-stale'}[st]||'b-none';return '<span class="badge '+c+'">'+esc(st)+'</span>'}
function loc(f,l){return f?'<span class="loc">'+esc(f)+(l?':'+l:'')+'</span>':''}
// ---- markdown with verification marks ----
function inline(s){
  s=esc(s);var keep=[];function hold(x){keep.push(x);return '\u0001'+(keep.length-1)+'\u0001'}
  function ver(path,l1,l2){return hold('<span class="verified" title="代码核实：'+path+':'+l1+(l2||'')+'">✓ '+path.split('/').pop()+':'+l1+'</span>')}
  s=s.replace(/`([^`]+)`/g,function(m,c){var v=c.match(/^([\w.\/\\-]+\.(?:java|xml|sql|jsp|cs|properties|ya?ml|js|ts|vue|kt|aspx|config)):(\d+)(-\d+)?$/);
    return v?ver(v[1],v[2],v[3]):hold('<code>'+c+'</code>')});
  s=s.replace(/([\w.\/-]*[\w-]+\.(?:java|xml|sql|jsp|cs|properties|ya?ml|kt)):(\d+)(-\d+)?/g,function(m,path,l1,l2){return ver(path,l1,l2)});
  s=s.replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
  s=s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,function(m,t,h){return /^https?:/.test(h)?'<a href="'+h+'" target="_blank" rel="noopener">'+t+'</a>':'<span class="kblink">'+t+'</span>'});
  s=s.replace(/\u0001(\d+)\u0001/g,function(m,k){return keep[+k]});
  if(/【推断】|〔推断〕/.test(s)){s=s.replace(/【推断】|〔推断〕/g,'<span class="infer-tag" title="模型推断，未经代码直接证实，需要人工确认">模型推断</span>');s='<span class="infer">'+s+'</span>';}
  return s}
function md(t){
  if(!t)return '';var L=String(t).split('\n'),out=[],i=0,list=null;
  function close(){if(list){out.push('</'+list+'>');list=null}}
  while(i<L.length){var l=L[i];
    if(/^```/.test(l)){close();var b=[];i++;while(i<L.length&&!/^```/.test(L[i])){b.push(L[i]);i++}i++;out.push('<pre class="code">'+esc(b.join('\n'))+'</pre>');continue}
    if(/^\s*\|.*\|\s*$/.test(l)&&i+1<L.length&&/^\s*\|[\s:|-]+\|\s*$/.test(L[i+1])){close();var h=cells(l);i+=2;var rows=[];while(i<L.length&&/^\s*\|.*\|\s*$/.test(L[i])){rows.push(cells(L[i]));i++}
      out.push('<div class="scroll"><table><tr>'+h.map(function(c){return '<th>'+inline(c)+'</th>'}).join('')+'</tr>'+rows.map(function(r){return '<tr>'+r.map(function(c){return '<td>'+inline(c)+'</td>'}).join('')+'</tr>'}).join('')+'</table></div>');continue}
    var m;
    if(m=l.match(/^(#{1,4})\s+(.*)/)){close();var lv=Math.min(4,m[1].length+1);out.push('<h'+lv+'>'+inline(m[2])+'</h'+lv+'>')}
    else if(m=l.match(/^\s*[-*]\s+(.*)/)){if(list!=='ul'){close();out.push('<ul>');list='ul'}out.push('<li>'+inline(m[1])+'</li>')}
    else if(m=l.match(/^\s*\d+[.、)]\s+(.*)/)){if(list!=='ol'){close();out.push('<ol>');list='ol'}out.push('<li>'+inline(m[1])+'</li>')}
    else if(/^>\s?/.test(l)){close();out.push('<p class="note">'+inline(l.replace(/^>\s?/,''))+'</p>')}
    else if(!l.trim()){close()}
    else{close();out.push('<p>'+inline(l)+'</p>')}
    i++}
  close();return '<div class="md">'+out.join('')+'</div>'}
function cells(l){return l.trim().replace(/^\||\|$/g,'').split('|').map(function(c){return c.trim()})}
// ---- chrome ----
function shell(inner){
  return '<header class="top"><span class="brand" data-go="#/">'+esc(O.project)+'<small>业务全景 · '+esc(O.generated)+'</small></span>'+
  '<div class="searchbox"><input id="q" placeholder="搜业务名、中文规则提示、URL、类名、表名" autocomplete="off"><div class="results" id="res" hidden></div></div>'+
  '<span class="sp"></span><button class="btn" id="theme" type="button">明暗</button></header><main>'+inner+'</main>'}
function render(){
  var h=location.hash.replace(/^#\/?/,''),p=h.split('/').map(decodeURIComponent);
  if(p[0]==='d'){return load(+p[1],function(d){paint(domainView(d,p[2]||'flows'))})}
  if(p[0]==='f'){return load(+p[1],function(d){var f=d.flows.filter(function(x){return x.id===p[2]})[0];paint(f?flowView(d,f,p[3]||'graph'):'<div class="panel empty">没有找到这条业务流。</div>')})}
  paint(overview(p[0]||'map'));
}
function paint(html){app.innerHTML=shell(html);wire();window.scrollTo(0,0)}
function wire(){
  var q=document.getElementById('q'),res=document.getElementById('res'),sel=-1,hits=[];
  q.addEventListener('input',function(){var v=q.value.trim().toLowerCase();if(!v){res.hidden=true;return}
    var terms=v.split(/\s+/);hits=[];
    for(var i=0;i<O.search.length&&hits.length<40;i++){var s=O.search[i],hay=(s[3]+' '+s[4]+' '+s[5]+' '+s[1]).toLowerCase();if(terms.every(function(t){return hay.indexOf(t)>=0}))hits.push(s)}
    res.innerHTML=hits.length?hits.map(function(s,k){var d=O.domains[s[2]];var kind={f:'业务流',t:'表',d:'业务域'}[s[0]];
      return '<div data-k="'+k+'"><span class="k">'+kind+'</span><b>'+esc(s[3]||s[4]||s[1])+'</b> <span class="loc">'+esc(s[0]==='f'?s[4]:s[0]==='t'?s[1]:'')+'</span> <small style="color:var(--faint)">· '+esc(d?d.title:'')+'</small></div>'}).join(''):'<div class="empty">没有匹配。中文规则提示、业务说明在已分析的页面里，可以用 tmh context 做更深的定位。</div>';
    res.hidden=false;sel=-1});
  function go(s){res.hidden=true;q.value='';location.hash=s[0]==='f'?'#/f/'+s[2]+'/'+encodeURIComponent(s[1]):s[0]==='t'?'#/d/'+s[2]+'/tables':'#/d/'+s[2]}
  res.addEventListener('click',function(e){var el=e.target.closest('[data-k]');if(el)go(hits[+el.dataset.k])});
  q.addEventListener('keydown',function(e){var els=res.querySelectorAll('[data-k]');if(e.key==='ArrowDown'||e.key==='ArrowUp'){sel=Math.max(0,Math.min(els.length-1,sel+(e.key==='ArrowDown'?1:-1)));els.forEach(function(x,k){x.classList.toggle('on',k===sel)});e.preventDefault()}
    if(e.key==='Enter'&&hits.length)go(hits[Math.max(sel,0)]);if(e.key==='Escape')res.hidden=true});
  document.getElementById('theme').onclick=function(){var r=document.documentElement,dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('tmh-theme',r.dataset.theme)}catch(e){}};
  app.querySelectorAll('[data-go]').forEach(function(el){el.addEventListener('click',function(e){if(e.target.closest('a'))return;location.hash=el.dataset.go})});
  var fi=document.getElementById('ff');if(fi)fi.addEventListener('input',function(){var v=fi.value.trim().toLowerCase();app.querySelectorAll('[data-hay]').forEach(function(el){el.hidden=v&&el.dataset.hay.indexOf(v)<0})});
  app.querySelectorAll('[data-expand]').forEach(function(b){b.onclick=function(){var t=document.getElementById(b.dataset.expand);t.hidden=!t.hidden}});
}
try{var th=localStorage.getItem('tmh-theme');if(th)document.documentElement.dataset.theme=th}catch(e){}
// ---- overview ----
function overview(tab){
  var s=O.stats,b=O.build||{},cov=O.coverage||{},tot=cov.total||{};
  var written=(tot['待确认']||0)+(tot['已确认']||0),all=0;for(var k in tot)all+=tot[k];
  var h='<h1>'+esc(O.project)+'</h1><div class="lede">'+(O.index&&O.index.summary?esc(O.index.summary):'静态分析给出可核实的事实（调用链、读写的表、状态流转、校验规则与代码位置）；智能体在这些事实上写业务理解，并把推断单独标出。')+'</div>';
  h+='<div class="stats">'+[[s.domains,'业务域'],[s.flows,'业务流'],[s.with_tables,'追到数据表的业务流'],[s.tables,'表'],[s.sms,'状态机'],[s.rules,'代码里的校验规则'],[written+' / '+all,'已写业务说明的页面']].map(function(x){return '<div><b>'+(typeof x[0]==='number'?fmt(x[0]):esc(x[0]))+'</b><span>'+x[1]+'</span></div>'}).join('')+'</div>';
  h+='<div class="tabs">'+[['map','业务全景'],['build','项目构建'],['kb','术语、坑与待确认']].map(function(t){return '<a href="#/'+t[0]+'" class="'+(tab===t[0]?'on':'')+'">'+t[1]+'</a>'}).join('')+'</div>';
  if(tab==='build')return h+buildView(b);
  if(tab==='kb')return h+kbView();
  h+='<div class="grid2"><div class="panel"><div class="side-title"><h2>系统总览</h2>'+(O.index?stBadge(O.index.status):'<span class="badge b-none">还没有</span>')+'</div>'+
     (O.index?md(O.index.body):'<p class="empty">还没有系统总览。让智能体运行 legacy-onboard 技能（或 <code>tmh kb next</code> 的队列走到“系统总览”），它会在下面这些事实基础上写：系统是什么、角色、业务域之间的关系、技术架构、维护须知。</p>')+
     '</div><div class="panel"><h2>业务域关系</h2><div class="legend"><span>圆的大小 = 业务流数</span><span>连线 = 一个域的业务流读写另一个域的表</span></div>'+domainGraph()+'</div></div>';
  var doms=O.domains.slice(),big=doms.filter(function(d){return d.flows>=3||d.status}),small=doms.filter(function(d){return !(d.flows>=3||d.status)});
  h+='<h2 style="margin-top:22px">业务域</h2><div class="legend"><span>'+stBadge('已确认')+' 人已确认</span><span>'+stBadge('待确认')+' 智能体已写、待人确认</span><span>'+stBadge('')+' 只有代码事实</span><span>进度条 = 已写业务说明的业务流比例</span></div><div class="tiles">';
  big.forEach(function(d){h+=tile(d)});
  h+='</div>';
  if(small.length)h+='<details style="margin-top:12px"><summary>其余 '+small.length+' 个小业务域（少于 3 条业务流）</summary><div class="chips" style="margin-top:8px">'+small.map(function(d){return '<a class="chip" href="#/d/'+d.i+'">'+esc(d.title)+'<small>'+d.flows+'</small></a>'}).join('')+'</div></details>';
  return h}
function tile(d){var pct=d.flows?Math.round(100*d.pages/d.flows):0;
  return '<div class="tile" data-go="#/d/'+d.i+'"><div class="row" style="justify-content:space-between;gap:8px"><span class="t">'+esc(d.title)+'</span>'+stBadge(d.status)+'</div>'+
  (d.title!==d.key?'<span class="k mono">'+esc(d.key)+'</span>':'')+
  '<div class="s">'+(d.summary?esc(d.summary):'<span class="empty">主要读写：'+esc(d.tables.slice(0,4).join('、')||'无')+'</span>')+'</div>'+
  '<div class="m">业务流 '+d.flows+' · 写 '+d.writes+' 张表 · 状态机 '+d.sms+' · 规则 '+d.rules+(d.infer?' · 推断 '+d.infer:'')+'</div><div class="bar"><i style="width:'+pct+'%"></i></div></div>'}
function domainGraph(){
  var ds=O.domains.filter(function(d){return d.id!=='_'}).slice(0,24);if(ds.length<2)return '<p class="empty">业务域太少，不画关系图。</p>';
  var W=560,H=440,cx=W/2,cy=H/2,R=Math.min(W,H)/2-70,pos={},max=Math.max.apply(null,ds.map(function(d){return d.flows}));
  ds.forEach(function(d,k){var a=-Math.PI/2+2*Math.PI*k/ds.length;pos[d.id]={x:cx+R*Math.cos(a),y:cy+R*Math.sin(a),r:6+18*Math.sqrt(d.flows/max),d:d,a:a}});
  var e='',n='',maxc=1;ds.forEach(function(d){d.rel.forEach(function(r){if(pos[r[0]])maxc=Math.max(maxc,r[1])})});
  ds.forEach(function(d){d.rel.forEach(function(r){var a=pos[d.id],b=pos[r[0]];if(!b)return;
    e+='<path d="M'+a.x.toFixed(1)+','+a.y.toFixed(1)+' Q'+cx+','+cy+' '+b.x.toFixed(1)+','+b.y.toFixed(1)+'" fill="none" stroke="var(--accent)" stroke-opacity="'+(0.15+0.5*r[1]/maxc).toFixed(2)+'" stroke-width="'+(0.8+3*r[1]/maxc).toFixed(1)+'"><title>'+esc(d.title)+' → '+esc(b.d.title)+'：'+r[1]+' 次读写</title></path>'})});
  ds.forEach(function(d){var p=pos[d.id],right=Math.cos(p.a)>=0,lx=p.x+(right?1:-1)*(p.r+5);
    n+='<g style="cursor:pointer" data-go="#/d/'+d.i+'"><circle cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="'+p.r.toFixed(1)+'" fill="'+(d.status?'var(--accent)':'var(--panel)')+'" stroke="var(--accent)" stroke-width="1.5"><title>'+esc(d.title)+'：'+d.flows+' 条业务流</title></circle>'+
    '<text x="'+lx.toFixed(1)+'" y="'+(p.y+4).toFixed(1)+'" text-anchor="'+(right?'start':'end')+'">'+esc(d.title.length>10?d.title.slice(0,10)+'…':d.title)+'</text></g>'});
  return '<div class="scroll"><svg viewBox="0 0 '+W+' '+H+'" width="100%" style="max-width:'+W+'px;display:block;margin:auto" class="arch">'+e+n+'</svg></div>'+(O.domains.length>24?'<p class="more">只画了最大的 24 个业务域。</p>':'')}
function buildView(b){
  var j=b.java||{},h='<div class="grid2"><div class="panel"><h2>架构分层</h2>'+archSvg(b)+'</div><div class="panel"><h2>技术组件</h2><div class="legend"><span>数字 = import 了它的源文件数，可以看出依赖有多深</span></div><div class="chips">'+
    (b.components||[]).map(function(c){return '<span class="chip" title="例：'+esc(c.example)+'">'+esc(c.name)+'<small>'+(c.files||'构建文件声明')+'</small></span>'}).join('')+'</div>'+
    '<h3>代码</h3><div class="mono" style="font-size:12.5px">Java '+fmt(j.files)+' 个文件 · '+fmt(j.lines)+' 行 · 构建 '+esc(j.build||'未发现 pom/gradle')+' · JDK '+esc(j.version||'未声明')+(j.spring_boot?' · Spring Boot '+esc(j.spring_boot):'')+'<br>主包 '+esc((j.packages||[]).join('、'))+'</div>';
  if(b.decompiled&&b.decompiled.files)h+='<p class="note">'+fmt(b.decompiled.files)+' 个文件（'+Math.round(b.decompiled.share*100)+'%）是反编译出来的代码。</p>';
  h+='</div></div>';
  h+='<div class="grid2" style="margin-top:18px"><div class="panel"><h2>部署与运行</h2>';
  var dep=b.deploy||[];if(!dep.length)h+='<p class="empty">没有发现 Dockerfile、compose、Tomcat 或脚本。</p>';
  dep.forEach(function(d){h+='<div style="padding:6px 0;border-bottom:1px solid var(--soft)"><span class="badge">'+esc(d.kind)+'</span> <span class="loc">'+esc(d.file)+'</span>';
    if(d.services&&d.services.length)h+='<div class="chips" style="margin-top:6px">'+d.services.map(function(s){return '<span class="chip">'+esc(s.name)+'<small>'+esc(s.image||'本地构建')+(s.ports.length?' · '+esc(s.ports.join(' ')):'')+'</small></span>'}).join('')+'</div>';
    if(d.from)h+=' <small>FROM '+esc(d.from)+'</small>';if(d.proxy&&d.proxy.length)h+=' <small>→ '+esc(d.proxy.join('、'))+'</small>';h+='</div>'});
  if((b.artifacts||[]).length)h+='<h3>构建产物</h3>'+b.artifacts.map(function(a){return '<div class="loc">'+esc(a.file)+' · '+a.mb+' MB</div>'}).join('');
  if((b.configs||[]).length)h+='<h3>配置文件</h3><div class="scroll"><table class="tbl"><tr><th>文件</th><th>键</th><th>数据库</th></tr>'+b.configs.map(function(c){return '<tr><td class="loc">'+esc(c.file)+'</td><td>'+c.keys+(c.plain_secrets?' <span class="badge b-mid">明文密码类 '+c.plain_secrets+'</span>':'')+'</td><td class="loc">'+esc(c.jdbc.map(function(x){return x.db+'@'+x.host+(x.name?'/'+x.name:'')}).join(' '))+'</td></tr>'}).join('')+'</table></div>';
  h+='</div><div class="panel"><h2>维护风险</h2>';
  var rs=b.risks||[];if(!rs.length)h+='<p class="empty">没有从事实里看出明显风险。</p>';
  rs.forEach(function(r){h+='<div class="risk"><span class="badge '+(r.level==='高'?'b-high':r.level==='中'?'b-mid':'b-none')+'">'+esc(r.level)+'</span><div><b>'+esc(r.title)+'</b><div class="why">'+esc(r.why)+'</div>'+(r.at||[]).map(function(a){return '<div class="loc">'+esc(a)+'</div>'}).join('')+'</div></div>'});
  if(b.big_methods&&b.big_methods.top&&b.big_methods.top.length)h+='<h3>超长方法</h3><table class="tbl">'+b.big_methods.top.slice(0,8).map(function(m){return '<tr><td class="mono">'+esc(m.name)+'</td><td>'+m.lines+' 行</td><td class="loc">'+esc(m.at)+'</td></tr>'}).join('')+'</table>';
  if((b.hubs||[]).length)h+='<h3>被调用最多的方法（改它影响面最大）</h3><table class="tbl">'+b.hubs.slice(0,8).map(function(m){return '<tr><td class="mono">'+esc(m.name)+'</td><td>'+m.fan_in+' 处调用</td><td class="loc">'+esc(m.at)+'</td></tr>'}).join('')+'</table>';
  h+='</div></div>';
  if(O.index&&/技术架构/.test(O.index.body)){var sec=O.index.body.split(/^## /m).filter(function(x){return /^技术架构/.test(x)})[0];if(sec)h+='<div class="panel" style="margin-top:18px"><div class="side-title"><h2>智能体的架构解读</h2>'+stBadge(O.index.status)+'</div>'+md('## '+sec)+'</div>'}
  return h}
function archSvg(b){
  var en=b.entries||{},ly=b.layers||{},W=560,y=10,rows=[],svc=[];
  rows.push(['入口',Object.keys(en).map(function(k){return k+' '+fmt(en[k])})]);
  rows.push(['控制层',['入口类 '+fmt(ly.entry||0)]]);
  rows.push(['业务层',['服务类 '+fmt(ly.service||0)].concat((b.dispatch_points||[]).length?['配置分派点 '+b.dispatch_points.length]:[])]);
  rows.push(['数据访问',['DAO/仓库类 '+fmt(ly.dao||0)]]);
  rows.push(['数据',['表 '+fmt(b.tables||0),'状态机 '+fmt(b.state_machines||0)].concat((b.dynamic_tables||[]).length?['运行时决定的表 '+b.dynamic_tables.length+' 种']:[])]);
  var seenS={};(b.deploy||[]).forEach(function(d){(d.services||[]).forEach(function(s){if(seenS[s.name]&&!s.image)return;if(seenS[s.name])svc.splice(svc.indexOf(seenS[s.name]),1);var lab=s.name+(s.image?' · '+s.image.split(':')[0].split('/').pop():'');seenS[s.name]=lab;svc.push(lab)})});
  var out='',colW=svc.length?400:W-20;
  rows.forEach(function(r,k){var yy=y+k*62;out+='<text x="10" y="'+(yy+26)+'" class="sub">'+r[0]+'</text>';
    var bw=(colW-90)/Math.max(1,r[1].length);r[1].forEach(function(t,i){var x=90+i*bw;out+='<rect x="'+x+'" y="'+yy+'" width="'+(bw-8)+'" height="40" rx="7" fill="var(--soft)" stroke="var(--line)"/><text x="'+(x+(bw-8)/2)+'" y="'+(yy+25)+'" text-anchor="middle">'+esc(t)+'</text>'});
    if(k<rows.length-1)out+='<path d="M'+(90+(colW-90)/2)+','+(yy+42)+' v16" stroke="var(--faint)" marker-end="url(#ar)"/>'});
  if(svc.length){var x0=420;out+='<text x="'+x0+'" y="'+(y+6)+'" class="sub">运行环境（compose）</text>';svc.slice(0,8).forEach(function(s,i){out+='<rect x="'+x0+'" y="'+(y+14+i*40)+'" width="130" height="32" rx="6" fill="var(--info-soft)" stroke="var(--line)"/><text x="'+(x0+65)+'" y="'+(y+34+i*40)+'" text-anchor="middle" style="font-size:11px">'+esc(s.length>18?s.slice(0,18)+'…':s)+'</text>'})}
  var H=Math.max(y+rows.length*62,y+20+Math.min(svc.length,8)*40);return '<div class="scroll"><svg class="arch" viewBox="0 0 '+W+' '+H+'" style="max-width:'+W+'px"><defs><marker id="ar" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="var(--faint)"/></marker></defs>'+out+'</svg></div>'}
function kbView(){var f=O.free||{},names={'glossary.md':'术语表','pitfalls.md':'坑与反直觉的地方','open-questions.md':'待确认问题','decisions.md':'决定'};var h='';
  Object.keys(names).forEach(function(k){if(f[k])h+='<div class="panel" style="margin-bottom:14px">'+md(f[k].replace(/^#\s+/,'## '))+'</div>'});
  return h||'<div class="panel empty">还没有。智能体在分析时会把业务词对照、坑和需要业务方回答的问题记到 .tmh/knowledge 下对应的文件里。</div>'}
// ---- domain ----
function domainView(d,tab){
  var meta=O.domains.filter(function(x){return x.id===d.id})[0]||{};var i=meta.i;
  var h='<div class="crumb"><a href="#/">业务全景</a> / 业务域</div><div class="row" style="align-items:center;gap:10px"><h1>'+esc(d.title)+'</h1>'+stBadge(d.page&&d.page.status)+'</div>'+
    (d.title!==d.id?'<div class="loc">'+esc(d.id)+'</div>':'')+(d.page&&d.page.summary?'<p class="lede">'+esc(d.page.summary)+'</p>':'');
  h+='<div class="stats">'+[[d.flows.length,'业务流'],[d.tables.length,'相关表'],[d.sms.length,'状态机'],[meta.rules,'校验规则'],[meta.pages+' / '+d.flows.length,'已写说明的业务流']].map(function(x){return '<div><b>'+esc(typeof x[0]==='number'?fmt(x[0]):x[0])+'</b><span>'+x[1]+'</span></div>'}).join('')+'</div>';
  h+='<div class="tabs">'+[['flows','业务流'],['tables','业务对象与表'],['states','状态流转'],['about','业务说明']].map(function(t){return '<a href="#/d/'+i+'/'+t[0]+'" class="'+(tab===t[0]?'on':'')+'">'+t[1]+'</a>'}).join('')+'</div>';
  if(tab==='about')return h+'<div class="panel">'+(d.page?md(d.page.body)+'<p class="loc">'+esc(d.page.file)+'</p>':'<p class="empty">这个业务域还没有业务说明。智能体写业务域页面时会给它起业务名称、讲清职责边界、核心流程和风险。</p>')+(meta.rel&&meta.rel.length?'<h3>和其他业务域的数据往来</h3><div class="chips">'+meta.rel.map(function(r){var o=O.domains.filter(function(x){return x.id===r[0]})[0];return o?'<a class="chip" href="#/d/'+o.i+'">'+esc(o.title)+'<small>'+r[1]+'</small></a>':''}).join('')+'</div>':'')+'</div>';
  if(tab==='tables'){h+='<div class="panel"><div class="scroll"><table class="tbl"><tr><th>表</th><th>业务含义</th><th>写它的业务流</th><th>只读的业务流</th><th>状态字段</th><th>归属</th></tr>';
    d.tables.forEach(function(t){var own=O.domains.filter(function(x){return x.id===t.owner})[0];
      h+='<tr><td class="mono">'+esc(t.name)+(t.entity?'<div class="loc">'+esc(t.entity)+'</div>':'')+'</td><td>'+(t.page?esc(t.page.summary||'')+' '+stBadge(t.page.status):'<span class="empty">—</span>')+'</td><td>'+t.w+'</td><td>'+t.r+'</td><td class="mono">'+esc(t.sm.join(' '))+'</td><td>'+(own&&own.id!==d.id?'<a href="#/d/'+own.i+'/tables">'+esc(own.title)+'</a>':'本域')+'</td></tr>'});
    return h+'</table></div></div>'}
  if(tab==='states'){if(!d.sms.length)return h+'<div class="panel empty">这个域的表没有发现状态字段赋值。</div>';
    d.sms.forEach(function(sm,k){h+='<div class="panel" style="margin-bottom:14px"><h2 class="mono">'+esc(sm.table)+'.'+esc(sm.column)+'</h2><div class="legend"><span>从代码里的 UPDATE … SET、setStatus(…) 和 INSERT 推出</span><span>“*”= 代码没有限定原状态</span></div>'+smSvg(sm)+
      '<details><summary>'+sm.total+' 条转换明细</summary><div class="scroll"><table class="tbl"><tr><th>从</th><th>到</th><th>由哪个业务触发</th><th>位置</th></tr>'+sm.tr.map(function(t){return '<tr><td>'+esc(t[0])+'</td><td><b>'+esc(t[1])+'</b></td><td><a href="#/f/'+i+'/'+encodeURIComponent(t[2])+'">'+esc(t[3])+'</a></td><td class="loc">'+esc(t[4])+':'+t[5]+'</td></tr>'}).join('')+'</table></div></details></div>'});
    return h}
  // flows
  var groups={};d.flows.forEach(function(f){(groups[f.kind]=groups[f.kind]||[]).push(f)});
  h+='<div class="panel"><div class="filter"><input id="ff" placeholder="在这个域里筛选：名称、URL、类名、表名"><span class="legend" style="margin:0"><span>'+ops('C')+'新增</span><span>'+ops('R')+'查询</span><span>'+ops('U')+'修改</span><span>'+ops('D')+'删除</span></span></div><div class="flowlist">';
  Object.keys(groups).forEach(function(g){h+='<h3>'+esc(g)+' · '+groups[g].length+'</h3>';
    groups[g].sort(function(a,b){return (b.page?1:0)-(a.page?1:0)||Object.keys(b.crud).length-Object.keys(a.crud).length}).forEach(function(f){
      var nm=(f.page&&f.page.title)||f.name||f.handler,w=Object.keys(f.crud).filter(function(t){return /[CUDP]/.test(f.crud[t])});
      h+='<div class="it" data-go="#/f/'+i+'/'+encodeURIComponent(f.id)+'" data-hay="'+esc((nm+' '+f.trigger+' '+f.handler+' '+Object.keys(f.crud).join(' ')).toLowerCase())+'"><span class="nm">'+esc(nm)+' '+(f.page?stBadge(f.page.status):'')+'</span><span>'+
      (w.slice(0,3).map(function(t){return '<span class="mono" style="font-size:12px;margin-left:8px">'+ops(f.crud[t])+esc(t)+'</span>'}).join('')+(w.length>3?' <small style="color:var(--faint)">+'+(w.length-3)+'</small>':'')+(!w.length&&Object.keys(f.crud).length?'<small style="color:var(--faint)">只读 '+Object.keys(f.crud).length+' 张表</small>':''))+
      '</span><span class="tr">'+esc(f.trigger)+(f.rules.length?' · 规则 '+f.rules.length:'')+(f.st.length?' · 状态变化 '+f.st.length:'')+(f.un.length?' · 断点 '+f.un.length:'')+'</span></div>'})});
  return h+'</div></div>'}
function smSvg(sm){
  var st=sm.states.slice(0,14),W=Math.max(420,st.length*120),H=170,pos={};st.forEach(function(s,k){pos[s]={x:60+k*(W-120)/Math.max(1,st.length-1),y:85}});
  if(st.length===1)pos[st[0]].x=W/2;
  var seen={},e='';sm.tr.forEach(function(t){var key=t[0]+'>'+t[1];if(seen[key])return;seen[key]=1;var b=pos[t[1]];if(!b)return;
    if(t[0]==='*'||!pos[t[0]]){e+='<path d="M'+b.x+',20 L'+b.x+',68" stroke="var(--faint)" stroke-dasharray="3 3" marker-end="url(#sa)" fill="none"/><text x="'+(b.x+4)+'" y="30" class="sub">'+esc(t[0]==='*'?'*':t[0])+'</text>';return}
    var a=pos[t[0]];var up=a.x<b.x,dy=up?-1:1,mx=(a.x+b.x)/2,c=85+dy*Math.min(70,20+Math.abs(b.x-a.x)/4);
    e+='<path d="M'+a.x+','+(85+dy*16)+' Q'+mx+','+c+' '+b.x+','+(85+dy*16)+'" stroke="var(--accent)" fill="none" marker-end="url(#sa)"><title>'+esc(t[0]+' → '+t[1]+'：'+t[3])+'</title></path>'});
  var n=st.map(function(s){var p=pos[s],w=Math.max(60,s.length*8+18);return '<rect x="'+(p.x-w/2)+'" y="'+(p.y-15)+'" width="'+w+'" height="30" rx="15" fill="var(--panel)" stroke="var(--accent)"/><text x="'+p.x+'" y="'+(p.y+4)+'" text-anchor="middle">'+esc(s)+'</text>'}).join('');
  return '<div class="diagram" style="max-height:none"><svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'"><defs><marker id="sa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="var(--accent)"/></marker></defs>'+e+n+'</svg></div>'+(sm.states.length>14?'<p class="more">只画了前 14 个状态。</p>':'')}
// ---- flow ----
function flowView(d,f,tab){
  var i=(O.domains.filter(function(x){return x.id===d.id})[0]||{}).i,base='#/f/'+i+'/'+encodeURIComponent(f.id)+'/';
  var nm=(f.page&&f.page.title)||f.name||f.handler;
  var h='<div class="crumb"><a href="#/">业务全景</a> / <a href="#/d/'+i+'">'+esc(d.title)+'</a> / 业务流</div><div class="row" style="align-items:center;gap:10px"><h1>'+esc(nm)+'</h1>'+stBadge(f.page&&f.page.status)+'</div>'+
    '<div class="loc">'+esc(f.kind)+' · '+esc(f.trigger)+' → '+esc(f.handler)+' · '+esc(f.file)+':'+f.line+'</div>';
  if(f.page&&f.page.summary)h+='<p class="lede">'+esc(f.page.summary)+'</p>';
  h+='<div class="legend" style="margin-top:10px"><span><span class="verified">✓ 文件:行</span> 代码核实</span><span><span class="infer-tag">模型推断</span> 需要人确认</span><span>右侧全部是从代码静态抽取的事实</span></div>';
  h+='<div class="split"><div class="panel"><div class="side-title"><h2>业务理解</h2>'+stBadge(f.page&&f.page.status)+(f.page&&f.page.infer?'<span class="badge b-mid">推断 '+f.page.infer+' 处</span>':'')+'</div>'+
    (f.page?md(f.page.body)+'<p class="loc">'+esc(f.page.file)+'</p>':'<p class="empty">还没有业务说明。智能体写这一页时会读右边的事实和相关源码，用业务语言写目的、角色、步骤、规则、状态变化和例外，静态分析看不到的部分标成推断。</p>'+(f.rules.length?'<h3>代码里的校验提示（可先看这些）</h3><ul>'+f.rules.filter(function(r){return r[1]}).slice(0,12).map(function(r){return '<li>'+esc(r[1])+' <span class="verified" title="'+esc(r[2]+':'+r[3])+'">✓ '+esc(r[2].split('/').pop()+':'+r[3])+'</span></li>'}).join('')+'</ul>':''))+
    '</div><div class="panel facts"><div class="side-title"><h2>代码事实</h2><span class="badge b-ok">静态分析</span></div>';
  var big=f.n.length>45;tab=tab==='graph'&&big?'outline':tab;
  h+='<div class="tabs" style="margin-top:4px">'+[['graph','调用链图'],['outline','调用链大纲'],['data','数据与状态'],['rules','规则与断点']].map(function(t){return '<a href="'+base+t[0]+'" class="'+(tab===t[0]?'on':'')+'">'+t[1]+'</a>'}).join('')+'</div>';
  if(tab==='graph')h+=flowSvg(f);
  else if(tab==='outline')h+=(big?'<p class="note">这条链有 '+f.n.length+(f.more?'+'+f.more:'')+' 个节点，图会太密，先用大纲看；重复调用只展开一次。</p>':'')+outline(f);
  else if(tab==='data')h+=dataFacts(f,i);
  else h+=ruleFacts(f);
  return h+'</div></div>'}
function depthOf(f){var ch={};f.e.forEach(function(e){(ch[e[0]]=ch[e[0]]||[]).push(e)});var dep={},q=[f.root];dep[f.root]=0;while(q.length){var x=q.shift();(ch[x]||[]).forEach(function(e){if(dep[e[1]]==null){dep[e[1]]=dep[x]+1;q.push(e[1])}})}return {dep:dep,ch:ch}}
function flowSvg(f){
  var r=depthOf(f),dep=r.dep,cols={},maxd=0,tabs=[];
  f.n.forEach(function(n,k){if(dep[k]==null)return;if(n[1]==='table'){tabs.push(k);return}var c=Math.min(dep[k],6);maxd=Math.max(maxd,c);(cols[c]=cols[c]||[]).push(k)});
  var tc=maxd+1;if(tabs.length)cols[tc]=tabs;
  var CW=270,BW=196,BH=40,GY=12,pos={},H=0;
  Object.keys(cols).forEach(function(c){cols[c].forEach(function(k,j){pos[k]={x:20+c*CW,y:20+j*(BH+GY)};H=Math.max(H,pos[k].y+BH)})});
  var W=20+(tabs.length?tc:maxd)*CW+BW+20,e='',n='';
  f.e.forEach(function(x){var a=pos[x[0]],b=pos[x[1]];if(!a||!b)return;var col=x[2]?'var(--'+x[2].toLowerCase()+')':'var(--faint)';
    var x1=a.x+BW,y1=a.y+BH/2,x2=b.x,y2=b.y+BH/2;if(x2<=x1){x2=b.x+BW/2;y2=b.y}
    e+='<path d="M'+x1+','+y1+' C'+(x1+40)+','+y1+' '+(x2-40)+','+y2+' '+x2+','+y2+'" fill="none" stroke="'+col+'" stroke-opacity=".7" stroke-width="'+(x[2]&&x[2]!=='R'?1.8:1)+'"/>';
    if(x[2])e+='<text x="'+(x2-14)+'" y="'+(y2-4)+'" style="font:600 10px monospace;fill:'+col+'">'+x[2]+'</text>'});
  f.n.forEach(function(nd,k){var p=pos[k];if(!p)return;var lay=nd[1],lab=nd[0],sub=nd[4]||LAYER[lay]||lay;
    n+='<g><title>'+esc(lab+(nd[4]?'\n'+nd[4]:'')+(nd[2]?'\n'+nd[2]+':'+nd[3]:''))+'</title><rect x="'+p.x+'" y="'+p.y+'" width="'+BW+'" height="'+BH+'" rx="6" fill="var(--panel)" stroke="var(--l-'+lay+',var(--line))" stroke-width="'+(lay==='dispatch'?2:1.2)+'"'+(lay==='dispatch'?' stroke-dasharray="4 3"':'')+'/>'+
    '<rect x="'+p.x+'" y="'+p.y+'" width="4" height="'+BH+'" rx="2" fill="var(--l-'+lay+',var(--faint))"/>'+
    '<text x="'+(p.x+10)+'" y="'+(p.y+16)+'" class="mono">'+esc(lab.length>25?lab.slice(0,24)+'…':lab)+'</text><text x="'+(p.x+10)+'" y="'+(p.y+31)+'" class="sub">'+esc(sub.length>14?sub.slice(0,13)+'…':sub)+'</text></g>'});
  var hidden=f.n.length-Object.keys(pos).length;
  return '<div class="legend">'+['entry','service','dao','table','dispatch'].map(function(l){return '<span><span class="lay" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--l-'+l+')"></span> '+LAYER[l]+'</span>'}).join('')+'<span>连线字母 = 对表的操作</span></div>'+
    '<div class="diagram"><svg width="'+W+'" height="'+(H+20)+'" viewBox="0 0 '+W+' '+(H+20)+'">'+e+n+'</svg></div>'+(hidden>0||f.more?'<p class="more">图里省略了 '+(hidden+f.more)+' 个更深的节点，完整结构看“调用链大纲”。</p>':'')}
function outline(f){
  var r=depthOf(f),seen={};
  function node(k,depth){var nd=f.n[k];if(!nd)return '';var rep=seen[k];seen[k]=1;var kids=(r.ch[k]||[]);
    var s='<li><span class="lay" style="background:var(--l-'+nd[1]+',var(--faint))"></span>'+esc(nd[0])+(nd[4]?'<span class="cm">'+esc(nd[4])+'</span>':'')+(nd[2]&&nd[1]!=='table'?' <span class="loc">'+esc(nd[2].split('/').pop())+':'+nd[3]+'</span>':'')+(rep&&kids.length?' <span class="cm">（展开见上）</span>':'');
    if(!rep&&kids.length&&depth<14)s+='<ul>'+kids.map(function(e){return e[2]?'<li><span class="lay" style="background:var(--l-table)"></span>'+ops(e[2])+' '+esc(f.n[e[1]][0])+'</li>':node(e[1],depth+1)}).join('')+'</ul>';
    return s+'</li>'}
  return '<div class="outline scroll"><ul>'+node(f.root,0)+'</ul></div>'+(f.more?'<p class="more">还有 '+f.more+' 个节点超出上限没有列出，用 tmh flows '+esc(f.id)+' 在终端查看全部。</p>':'')}
function dataFacts(f,i){
  var h='<h3>读写的表</h3>';var t=Object.keys(f.crud);
  h+=t.length?'<div class="chips">'+t.map(function(x){return '<span class="chip mono">'+ops(f.crud[x])+esc(x)+'</span>'}).join('')+'</div>':'<p class="empty">没有追到数据表。</p>';
  if(f.st.length)h+='<h3>状态变化</h3><table class="tbl"><tr><th>表.字段</th><th>从</th><th>到</th><th>位置</th></tr>'+f.st.map(function(s){return '<tr><td class="mono">'+esc(s[0]+'.'+s[1])+'</td><td>'+esc(s[2].join('、'))+'</td><td><b>'+esc(s[3])+'</b></td><td class="loc">'+esc(s[4].split('/').pop())+':'+s[5]+'</td></tr>'}).join('')+'</table>';
  if(f.ops.length)h+='<h3>数据访问明细</h3><div class="scroll"><table class="tbl"><tr><th>操作</th><th>表</th><th>经由</th></tr>'+f.ops.map(function(o,k){return '<tr><td>'+ops(o[1])+'</td><td class="mono">'+esc(o[0])+'</td><td class="mono">'+esc(o[2])+(o[3]?' <a href="javascript:void 0" data-expand="sql'+k+'">SQL</a><pre class="code" id="sql'+k+'" hidden>'+esc(o[3])+'</pre>':'')+'</td></tr>'}).join('')+'</table></div>';
  if(f.tx.length)h+='<h3>事务</h3>'+f.tx.map(function(t){return '<div class="mono" style="font-size:12.5px">'+esc(t[0])+' '+loc(t[1].split('/').pop(),t[2])+'</div>'}).join('');
  if(f.fx.length)h+='<h3>外部影响</h3>'+f.fx.map(function(x){return '<div><span class="badge b-mid">'+esc(x[0])+'</span> <span class="mono" style="font-size:12.5px">'+esc(x[1])+'</span> '+loc(x[2].split('/').pop(),x[3])+'</div>'}).join('');
  return h}
function ruleFacts(f){
  var h='<h3>校验规则 · '+f.rules.length+'</h3>';
  h+=f.rules.length?'<div class="scroll"><table class="tbl"><tr><th>提示</th><th>条件</th><th>位置</th></tr>'+f.rules.map(function(r){return '<tr><td>'+esc(r[1])+'</td><td class="mono" style="font-size:12px">'+esc(r[0])+'</td><td class="loc">'+esc(r[2].split('/').pop())+':'+r[3]+'</td></tr>'}).join('')+'</table></div>':'<p class="empty">没有发现 if … throw 形式的校验。</p>';
  h+='<h3>静态分析的断点 · '+f.un.length+'</h3><p class="more" style="margin-top:0">这些地方代码在运行时才决定走向（接口多实现、反射、动态表名），是智能体需要推断、人需要确认的地方。</p>';
  h+=f.un.length?f.un.map(function(u){return '<div style="padding:5px 0;border-bottom:1px solid var(--soft)"><span class="mono" style="font-size:12.5px">'+esc(u[0])+'</span> '+loc(u[2]&&u[2].split('/').pop(),u[3])+'<div class="why" style="color:var(--sub);font-size:12.5px">'+esc(u[1])+'</div></div>'}).join(''):'<p class="empty">没有。</p>';
  return h}
window.addEventListener('hashchange',render);render();
})();
"""
