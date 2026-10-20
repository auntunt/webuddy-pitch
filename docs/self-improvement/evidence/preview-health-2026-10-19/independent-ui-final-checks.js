
const assert=require('node:assert/strict');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nodes={};
class Element {
 constructor(id){this.id=id;this.children=[];this.html='';this.value='';this.hidden=false}
 removeIds(){if(nodes[this.id]===this)delete nodes[this.id];this.children.forEach(n=>n.removeIds())}
 addIds(){nodes[this.id]=this;this.children.forEach(n=>n.addIds())}
 set innerHTML(text){this.children.forEach(n=>n.removeIds());this.children=[];this.html=text;
   for(const m of text.matchAll(/\bid="([^"]+)"/g)){const n=new Element(m[1]);n.parent=this;this.children.push(n);n.addIds()}}
 get innerHTML(){return this.html}
 querySelector(selector){for(const n of this.children){if('#'+n.id===selector)return n;const nested=n.querySelector(selector);if(nested)return nested}return null}
 replaceWith(replacement){const parent=this.parent,index=parent.children.indexOf(this);assert.ok(index>=0);this.removeIds();parent.children[index]=replacement;replacement.parent=parent;replacement.addIds()}
}
const $=s=>nodes[s.slice(1)]||null,S={};let view='t',timers=[],gets=[],posts=[];
function page(key){for(const id of Object.keys(nodes))delete nodes[id];for(const id of ['pvc','ttPv','cm','accNote']){nodes[id]=new Element(id)}S.cur={ticket:{key,links:{}}};view='t'}
const curView=()=>view,clip=(s,n)=>s.slice(0,n),toast=()=>{};
const get=url=>{gets.push(url);return getHandler(url)},post=async(url,body)=>{posts.push({url,body});return{}},setTimeout=fn=>timers.push(fn);
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const settle=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve()};
const stopped={preview:{state:'failed',why:'not ready'},url:'',cmd:'python old.py',branch:'candidate'};
const healthy={preview:{state:'up',commit:'abc'},url:'/pv/APP-1/__commit/abc/',cmd:'python app.py',branch:'candidate',own_address:true};
const starting={...healthy,url:'',preview:{state:'starting',commit:'abc'}};
let getHandler=async url=>url.endsWith('/preview-conf')?{cmd:'python old.py',ready:'/health'}:stopped;
page('APP-1');
const PVL={up:['ok','可以打开'],starting:['info','启动中'],unhealthy:['bad','暂不可用'],checking:['info','待重新核对'],failed:['bad','没起来']};
async function pvLoad(key){const el=$('#pvc'),top=$('#ttPv');if((!el&&!top)||S.cur?.ticket?.key!==key||curView()!=='t')return;
  const seq=S.ticketPreviewSeq=(S.ticketPreviewSeq||0)+1;
  const current=()=>seq===S.ticketPreviewSeq&&S.cur?.ticket?.key===key&&curView()==='t'&&el===$('#pvc')&&top===$('#ttPv');
  let d;try{d=await get('/api/tickets/'+key+'/preview')}catch(e){d={preview:{state:'checking',why:'无法读取预览状态：'+e.message}}}
  if(!current())return;const st=d.preview||{},s=st.state,lb=PVL[s];
  if(top)top.innerHTML=s==='up'&&d.url?`<a class="btn primary" href="${h(d.url)}" target="_blank" rel="noopener">打开预览 ↗</a>`:s==='starting'?'<span class="ev-tag info"><span class="spin"></span> 预览启动中</span>':['unhealthy','checking'].includes(s)?`<span class="ev-tag bad" role="status">预览暂不可用</span><span class="sub">${h(st.why||'请刷新预览状态')}</span>`:'';
  if(!el)return;
  if(!d.branch&&!s){el.hidden=true;return}
  const form=$('#pvF'),editing=form?.querySelector('#pvCmd');
  el.hidden=false;
  el.innerHTML=`<div class="hdr" style="margin-bottom:6px"><h2 class="grow" style="margin:0">预览版本</h2>${lb?`<span class="ev-tag ${lb[0]}">${lb[1]}</span>`:''}</div>
   ${s==='up'?`<div class="sub">这次改动（提交 <code>${h(st.commit)}</code>）正跑在平台上，验收前先亲手试一遍。发出去的签收链接里也有这个入口。${d.own_address?'':'<br>它在浏览器的隔离环境里运行，碰不到平台。直接出页面的程序可以正常用；页面打开后再用脚本取数据的（单页应用）在这里取不到数据，要给预览配一个独立端口。'}</div>
     <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap"><a class="btn primary" href="${h(d.url)}" target="_blank" rel="noopener">打开预览 ↗</a><button class="ghost" id="pvStop">停掉</button><button class="ghost" id="pvGo">重新启动</button></div>`
   :s==='starting'?`<div class="sub"><span class="spin"></span> 正在用 <code>${h(clip(st.cmd||'',80))}</code> 启动 ${h(st.branch||'')}，起来后这里会出现打开按钮。</div><div class="row" style="margin-top:8px"><button class="ghost" id="pvStop">停掉</button></div>`
   :s==='unhealthy'||s==='checking'?`<div class="bad" role="status">${h(st.why||'预览暂不可用，请刷新状态')}</div><p class="sub">健康恢复后可重新打开；本次检查不会重启进程或清除数据。</p><div class="row"><button id="pvRefresh">刷新预览状态</button>${d.cmd?'<button class="ghost" id="pvStop">停掉</button><button class="ghost" id="pvGo">重新启动</button>':''}</div>`
   :s==='failed'?`<div class="bad" style="font-size:13px">${h(st.why||'')}</div>${st.tail?`<details style="margin-top:6px"><summary class="sub">启动日志最后几行</summary><pre class="log" style="max-height:200px;overflow:auto;font-size:12px;white-space:pre-wrap">${h(st.tail)}</pre></details>`:''}<div class="row" style="gap:6px;margin-top:8px"><button class="primary" id="pvGo">再启动一次</button><button class="ghost" id="pvCfg">改启动命令</button></div>`
   :d.cmd?`<div class="sub">还没启动。会用 <code>${h(clip(d.cmd,80))}</code>${d.configured?'':'（按项目结构猜的）'}把这次改动跑起来。</div><div class="row" style="gap:6px;margin-top:8px"><button class="primary" id="pvGo">启动预览</button><button class="ghost" id="pvCfg">改启动命令</button></div>`
   :`<div class="sub">填一条能把这个项目跑起来的命令，以后每次自动改完都会起一个预览，客户在签收页就能点开试。用 <code>{port}</code> 表示端口，<code>{prefix}</code> 表示它挂在哪个路径下（程序要能挂在这个路径下运行，页面里的链接才不会断），只监听 127.0.0.1。</div><div class="row" style="margin-top:8px"><button class="primary" id="pvCfg">填启动命令</button></div>`}
   <div id="pvF"></div>`;
  if(editing)$('#pvF').replaceWith(form);
  const act=a=>post('/api/tickets/'+key+'/preview',{action:a}).then(()=>pvLoad(key)).catch(e=>toast(e.message,6000));
  if($('#pvGo'))$('#pvGo').onclick=()=>act('start');
  if($('#pvStop'))$('#pvStop').onclick=()=>act('stop');
  if($('#pvRefresh'))$('#pvRefresh').onclick=()=>pvLoad(key);
  if($('#pvCfg'))$('#pvCfg').onclick=async()=>{const pk=key.split('-')[0],box=$('#pvF');
    const active=()=>box===$('#pvF')&&S.cur?.ticket?.key===key&&curView()==='t';
    let c={};try{c=await get('/api/projects/'+pk+'/preview-conf')}catch(e){}if(!active())return;
    box.innerHTML=`<div style="margin-top:8px;display:flex;flex-direction:column;gap:6px"><input id="pvCmd" value="${h(c.cmd||c.detected||'')}" placeholder="例如 python3 -m http.server {port} 或 mvn spring-boot:run -Dserver.port={port}">
      <input id="pvReady" value="${h(c.ready||'/')}" placeholder="起来后能打开的路径，默认 /"><div class="row" style="gap:6px"><button class="primary" id="pvSave">保存</button><span class="sub">留空保存就回到按项目结构猜</span></div></div>`;
    $('#pvSave').onclick=async()=>{if(!active())return;try{await post('/api/projects/'+pk+'/preview-conf',{cmd:box.querySelector('#pvCmd').value,ready:box.querySelector('#pvReady').value});if(active()){toast('已保存启动命令');pvLoad(key)}}catch(e){if(active())toast(e.message,6000)}}};
  if(s==='starting')setTimeout(()=>{if(current())pvLoad(key)},4000)}

async function ticketTopWire(d,na){const t=d.ticket,key=t.key;
  if($('#ttIntakeRetry'))$('#ttIntakeRetry').onclick=()=>$('#naIntakeRetry')?.click();
  if($('#ttOk'))$('#ttOk').onclick=()=>{if(ticketSignoffGuard(d))$('#accOk').click()};
  if($('#ttNo'))$('#ttNo').onclick=()=>{const n=$('#accNote');n.scrollIntoView({block:'center',behavior:'smooth'});n.focus();n.placeholder='写明哪里不对，写好后点“验收不通过”';toast('写明哪里不对，再点“验收不通过”',4000)};
  if($('#ttSend'))$('#ttSend').onclick=()=>{if(!ticketSignoffGuard(d))return;const b=$('#pkLink');if(!b)return toast('证据包还没打好，稍等一下');b.click();$('#pkg').scrollIntoView({block:'start',behavior:'smooth'});const nm=S.ttClient;if(nm&&$('#pkS'))$('#pkS').value=nm};
  if($('#ttHw'))$('#ttHw').onclick=()=>{$('#engc').open=true;setTimeout(()=>{const c=$('#hwc');if(c&&!c.hidden)c.scrollIntoView({block:'start',behavior:'smooth'})},300)};
  S.ttClient='';const cid=(t.links||{}).client;
  if(cid)get('/api/clients').then(r=>{const c=r.clients.find(x=>x.id===cid);if(c&&$('#ttCl')){S.ttClient=c.name;$('#ttCl').innerHTML=`<a class="tag" href="#/c/${c.id}">${h(c.name)}</a>`}}).catch(()=>{});
  if($('#ttPv'))await pvLoad(key)}

(async()=>{
 await ticketTopWire(S.cur,{});await nodes.pvCfg.onclick();
 nodes.pvCmd.value='python NEW-unsaved.py --keep-everything';nodes.pvReady.value='/custom-unsaved-health';
 const form=nodes.pvF,commandDraft=nodes.pvCmd,readyDraft=nodes.pvReady,save=nodes.pvSave.onclick;
 nodes.ttPv=new Element('ttPv');await ticketTopWire(S.cur,{});
 assert.equal(nodes.pvF,form);assert.equal(nodes.pvCmd,commandDraft);assert.equal(nodes.pvReady,readyDraft);assert.equal(nodes.pvSave.onclick,save);
 assert.equal(commandDraft.value,'python NEW-unsaved.py --keep-everything');assert.equal(readyDraft.value,'/custom-unsaved-health');
 await save();assert.deepEqual(posts.at(-1),{url:'/api/projects/APP/preview-conf',body:{cmd:commandDraft.value,ready:readyDraft.value}});
 await settle();console.log('PASS retained preview configuration nodes, values, save handler and exact submitted values');
 const requestsBeforeDetachedSave=posts.length;page('APP-2');await save();assert.equal(posts.length,requestsBeforeDetachedSave);
 console.log('PASS detached old form cannot submit against a new ticket');
 page('APP-1');await pvLoad('APP-1');const deferred=later();getHandler=()=>deferred.promise;const pending=nodes.pvCfg.onclick();
 page('APP-2');getHandler=async()=>stopped;await pvLoad('APP-2');const destinationForm=nodes.pvF;deferred.resolve({cmd:'OLD',ready:'/OLD'});await pending;
 assert.equal(nodes.pvF,destinationForm);assert.equal(nodes.pvCmd,undefined);
 console.log('PASS late configuration response cannot fill another ticket');
 page('APP-1');getHandler=async()=>starting;timers=[];gets=[];await ticketTopWire(S.cur,{});
 assert.equal(gets.length,1);assert.equal(timers.length,1);const oldTimer=timers.shift();
 await pvLoad('APP-1');assert.equal(gets.length,2);oldTimer();await settle();assert.equal(gets.length,2);
 getHandler=async()=>healthy;timers.shift()();await settle();assert.equal(gets.length,3);
 for(const id of ['ttPv','pvc'])assert.ok(nodes[id].innerHTML.includes('href="/pv/APP-1/__commit/abc/"'));
 console.log('PASS one initial read, stale startup timer ignored, current startup poll updates both views');
 for(const replacement of ['other-view','same-key-new-dom','different-ticket']){
  page('APP-1');getHandler=async()=>starting;timers=[];await pvLoad('APP-1');const scheduled=timers.shift(),reads=gets.length;
  if(replacement==='other-view')view='deliveries';else page(replacement==='different-ticket'?'APP-2':'APP-1');
  scheduled();await settle();assert.equal(gets.length,reads);
 }
 console.log('PASS startup timers stop after view change, same-key DOM replacement, or another ticket');
})().catch(e=>{console.error(e);process.exitCode=1});
