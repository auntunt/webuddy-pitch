"""Personal, limited tool grants. Secrets live only in the current response/DOM."""


def page():
    return HTML


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的工具连接 · Webuddy</title><style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#182b38;background:#f5f6f8;font-size:15px}*{box-sizing:border-box}body{margin:0}header{background:white;border-bottom:1px solid #dbe1e7;padding:20px max(24px,calc((100vw - 1120px)/2));display:flex;gap:24px;align-items:center}a{color:#195e70}main{max-width:1120px;margin:32px auto;padding:0 24px}h1{font-size:30px;margin:0 0 12px}h2{font-size:19px;margin:0 0 16px}p{line-height:1.75;margin:10px 0}.muted{color:#526473}.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;margin-top:24px}.panel{background:white;border:1px solid #dbe1e7;border-radius:12px;padding:24px;min-width:0}label{display:block;margin:16px 0 7px;font-weight:600}input,select,textarea,button{font:inherit}input:not([type=checkbox]),select,textarea{width:100%;padding:11px;border:1px solid #9cabb7;border-radius:5px;min-width:0}input[type=checkbox]{width:18px;height:18px;flex-shrink:0}button,.button{min-height:42px;padding:9px 15px;border:1px solid #bdc9d1;background:white;border-radius:6px;cursor:pointer;color:#182b38}.primary{background:#195e70;border-color:#195e70;color:white}button:disabled{opacity:.55;cursor:default}.row{border-top:1px solid #e2e7eb;padding:16px 0;overflow-wrap:anywhere}.row:first-child{border:0;padding-top:0}.row h3{font-size:16px;margin:0}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.check{display:flex;gap:10px;align-items:flex-start;font-weight:400}.note{padding:14px 16px;background:#eaf1f3;border-radius:7px;overflow-wrap:anywhere}.error{color:#9e2d22}.badge{display:inline-block;border:1px solid #d4dfe5;border-radius:5px;padding:3px 7px;margin:6px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}textarea{min-height:132px;resize:vertical}#notice{margin:18px 0;white-space:pre-wrap;overflow-wrap:anywhere}#secret{margin-top:24px;border:2px solid #195e70}#projects{max-height:320px;overflow:auto}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #428aa0;outline-offset:3px}[hidden]{display:none!important}@media(max-width:760px){.layout{grid-template-columns:1fr}main{margin-top:24px;padding:0 16px}.panel{padding:18px}header{padding:16px}h1{font-size:25px}}
</style></head><body><header><strong>Webuddy</strong><a id="back">返回工作台</a></header><main>
<h1>我的工具连接</h1><p class="muted">让自己的 Claude、Cursor 或命令行读取获准资料、记录工作进展。每个连接都有明确的项目范围和有效期。</p>
<p class="note">此连接不启动服务端模型、构建或预览，也不能替人确认知识、验收或关单。工具名称只用于辨认连接，所有操作仍归属于授权成员。连接状态以最近一次读回为准，使用时服务器会再次核验权限。</p>
<div id="notice" role="status" aria-live="polite">正在核对个人身份与项目权限…</div>
<div id="pending" class="note" hidden><p>上次操作的结果尚未确认。请用原请求核对，避免重复创建连接。</p><button id="retry">核对原请求</button></div>
<section id="secret" class="panel" hidden><h2>保存这份连接凭据</h2><p>凭据仅在本次响应中显示。请保存到自己的电脑，不要发送到聊天、提交到代码库或交给其他成员。切换页面、每 15 秒重新核对身份或刷新列表时会清除本页凭据，请及时下载。未保存时需撤销该连接并重新创建。</p><textarea id="credential" readonly aria-label="连接凭据 JSON" spellcheck="false" autocomplete="off"></textarea><div class="actions"><button id="download" class="primary">下载凭据文件</button><button id="dismiss">已保存，清除页面凭据</button></div><pre id="guide"></pre></section>
<div class="layout"><section class="panel"><h2>授权一个工具连接</h2><form id="create"><label for="label">连接名称</label><input id="label" maxlength="80" required placeholder="例如：我的 Claude 工作电脑" autocomplete="off"><label for="scope">允许的操作</label><select id="scope"><option value="read">只读：任务、知识和已有回执</option><option value="content">协作：另可创建待办、记录消息</option></select><label for="days">有效期</label><select id="days"><option value="1">1 天</option><option value="7" selected>7 天</option><option value="30">30 天</option></select><label>可访问项目</label><div id="projects"></div><p class="muted">权限减少、成员移除、密码重置或主动撤销后，旧凭据失效；恢复权限不会复活旧连接。</p><button id="submit" class="primary" disabled>创建限定范围的连接</button></form></section>
<section class="panel"><h2>已授权的连接</h2><p id="identity" class="muted"></p><div id="connections"></div><button id="refresh">刷新列表</button></section></div></main>
<script>
const initialPath=location.pathname, initialOrigin=location.origin;
const base=initialPath.match(/^\/t\/[A-Za-z0-9_-]+(?=\/|$)/)?.[0]||'', tenant=base.split('/')[2]||'';
const $=s=>document.querySelector(s), h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let context='',owner='',pending=null,busy=false,credential=null,credentialBinding=null,directorySnapshot=null,locked=false,storageKey='',ready=false,epoch=0,loadVersion=0,sensitiveEpoch=0,identityVersion=0;
$('#back').href=base+'/';
function notice(text,error=false){$('#notice').textContent=text;$('#notice').className=error?'error':''}
function clearSecret(){credential=null;credentialBinding=null;$('#credential').value='';$('#guide').textContent='';$('#secret').hidden=true;$('#download').disabled=true}
function invalidateSensitive(){
  const hadCredential=!!credential;sensitiveEpoch++;clearSecret();
  if(hadCredential)notice('页面凭据已清除。若尚未保存，请撤销该连接并重新创建。'+(pending?' 原请求记录仍需核对。':''),!!pending);
}
function setBusy(value){
  busy=value;
  $('#submit').disabled=locked||value||!ready||!!pending||!!credential;
  $('#retry').disabled=locked||value||!pending||!!credential;
  $('#refresh').disabled=locked||value;
  $('#download').disabled=locked||value||!ready||!credential;
  for(const button of document.querySelectorAll('[data-revoke]'))button.disabled=locked||value||!ready||!!pending;
}
function pendingView(){$('#pending').hidden=locked||!pending;setBusy(busy)}
function lock(message){
  locked=true;ready=false;epoch++;context='';owner='';pending=null;directorySnapshot=null;
  clearSecret();$('#projects').replaceChildren();$('#connections').replaceChildren();$('#identity').textContent='';$('#label').value='';
  pendingView();notice(message+' 请返回工作台重新登录或读取权限。',true);
}
function live(version=epoch){
  if(location.pathname!==initialPath||location.origin!==initialOrigin){if(!locked)lock('当前组织页面已变化。');return false}
  return !locked&&version===epoch;
}
async function request(method,path,body){
  const version=epoch;
  if(!live(version))throw Error('当前页面身份已失效');
  const headers={'X-TMH':'1'};
  if(context)headers['X-Webuddy-Context']=context;
  if(body)headers['Content-Type']='application/json';
  const response=await fetch(base+path,{method,headers,credentials:'same-origin',body:body?JSON.stringify(body):undefined});
  if(!live(version))throw Error('已忽略旧页面的响应');
  let result;
  try{result=await response.json()}catch(error){throw Error('服务器回执不完整，请核对原请求。')}
  if(!live(version))throw Error('已忽略旧页面的响应');
  if(!response.ok){
    if(response.status===401||['context_changed','membership_revoked','identity_revoked','tenant_disabled'].includes(result?.code))lock(result?.error||'权限已变化。');
    throw Error(result?.error||'请求失败，请核对后重试。');
  }
  return result;
}
async function verifyIdentity({withinWrite=false}={}){
  if(withinWrite)clearSecret();else invalidateSensitive();
  const attempt=++identityVersion,version=epoch;
  const meta=await request('GET','/api/meta'),access=meta?.access;
  if(attempt!==identityVersion||!live(version))return false;
  if(!access?.user||!access?.context_token||access.tenant?.id!==tenant){lock('无法确认当前组织的个人身份。');return false}
  if(owner&&access.user!==owner||context&&access.context_token!==context){lock('成员或项目权限已变化。');return false}
  owner=access.user;context=access.context_token;storageKey='webuddy.tool.pending:'+JSON.stringify([base,owner]);
  return true;
}
function validPending(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||typeof value.request_id!=='string'||!value.request_id.match(/^[A-Za-z0-9_.:-]{1,128}$/))return false;
  const keys=value.action==='create'?['action','label','project_ids','scope','expires_days','request_id']:value.action==='revoke'?['action','connection_id','request_id']:[];
  if(Object.keys(value).length!==keys.length||Object.keys(value).some(key=>!keys.includes(key)))return false;
  if(value.action==='revoke')return typeof value.connection_id==='string'&&/^[a-f0-9]{32}$/.test(value.connection_id);
  return typeof value.label==='string'&&!!value.label.trim()&&value.label.length<=120&&['read','content'].includes(value.scope)&&Number.isInteger(value.expires_days)&&value.expires_days>=1&&value.expires_days<=30&&Array.isArray(value.project_ids)&&value.project_ids.length>0&&value.project_ids.every(id=>Number.isSafeInteger(id)&&id>0)&&new Set(value.project_ids).size===value.project_ids.length;
}
function readPending(){
  const saved=sessionStorage.getItem(storageKey);
  if(saved!==null){
    let value;try{value=JSON.parse(saved)}catch(error){throw Error('本机原请求记录无法读取；已阻止新操作，请保留记录并检查浏览器存储。')}
    if(!validPending(value))throw Error('本机原请求记录不完整；已阻止新操作，请保留记录并检查浏览器存储。');
    if(pending&&JSON.stringify(value)!==JSON.stringify(pending))throw Error('本机存在不同的未确认请求；已阻止覆盖，请先核对原请求。');
    pending=value;
  }
}
function persist(body){
  if(!validPending(body))throw Error('操作内容不完整，尚未提交。');
  const original=JSON.stringify(body);
  pending=JSON.parse(original);pendingView();
  const saved=sessionStorage.getItem(storageKey);
  if(saved!==null&&saved!==original)throw Error('本机已有不同原请求，不能覆盖。');
  sessionStorage.setItem(storageKey,original);
  if(sessionStorage.getItem(storageKey)!==original)throw Error('未能保存原请求，尚未提交。');
}
function cleared(){
  sessionStorage.removeItem(storageKey);
  if(sessionStorage.getItem(storageKey)!==null)throw Error('原请求记录未清除。');
  pending=null;pendingView();
}
function sameProjects(left,right){
  const valid=ids=>Array.isArray(ids)&&ids.length>0&&ids.every(id=>Number.isSafeInteger(id)&&id>0)&&new Set(ids).size===ids.length;
  return valid(left)&&valid(right)&&JSON.stringify([...left].sort((a,b)=>a-b))===JSON.stringify([...right].sort((a,b)=>a-b));
}
function activeConnection(item,body){
  return !!item&&item.user===owner&&item.tenant===tenant&&item.label===body.label.trim()&&item.scope===body.scope&&sameProjects(item.project_ids,body.project_ids)&&item.active===true&&item.status==='active'&&Number.isSafeInteger(item.expires_at)&&item.expires_at>Date.now()/1000;
}
function confirmedConnection(item,body,data){
  // Bind the secret to the actual latest row, not just list-level identity.
  // This is a readback snapshot; the server still authorizes each later use.
  if(!live()||!ready||data!==directorySnapshot||data?.user!==owner||data?.context_token!==context||!Array.isArray(data?.connections))throw Error('当前连接列表尚未确认，请核对原请求。');
  const rows=data.connections.filter(row=>row?.id===item.id);
  if(rows.length!==1||!activeConnection(item,body)||!activeConnection(rows[0],body)||rows[0].expires_at!==item.expires_at)throw Error('当前列表未确认原连接仍然有效，连接可能已撤销、过期或范围已变化，请核对原请求。');
}
function showCredential(token,item,body,data){
  confirmedConnection(item,body,data);
  credentialBinding={item,body,data};
  credential={schema:1,endpoint:initialOrigin+base,token};$('#credential').value=JSON.stringify(credential,null,2);$('#secret').hidden=false;
  $('#guide').textContent='在自己的终端导入下载的 JSON（下列文件名可替换）：\nmkdir -p ~/.config/webuddy\nwebuddy connect --stdin --save-to ~/.config/webuddy/my-tool.json < webuddy-credential.json\nwebuddy --credential-file ~/.config/webuddy/my-tool.json status\n确认导入成功后，删除下载目录中的临时凭据文件。';
  setBusy(busy);
}
function render(data){
  $('#identity').textContent='当前成员：'+owner+' · 只显示本人授权的连接';
  const selected=new Set([...document.querySelectorAll('[name=project]:checked')].map(node=>node.value));
  $('#projects').innerHTML=data.projects.map(project=>`<label class="check"><input type="checkbox" name="project" value="${h(project.id)}" data-role="${h(project.role)}" ${selected.has(String(project.id))?'checked':''}><span>${h(project.name)} · ${h(project.key)}${project.role==='viewer'?'（只读）':''}</span></label>`).join('')||'<p class="muted">尚无获准项目，请联系组织管理员。</p>';
  const statuses={active:'有效',revoked:'已撤销',expired:'已过期',invalidated:'权限已失效'};
  $('#connections').innerHTML=data.connections.map(connection=>`<article class="row"><h3>${h(connection.label)}</h3><span class="badge">${h(statuses[connection.status]||connection.status)}</span><p>${connection.scope==='content'?'内容协作':'只读'} · 项目 ${h(connection.project_ids.join('、'))}</p><p class="muted">有效至 ${h(new Date(connection.expires_at*1000).toLocaleString())}</p>${connection.active?`<button data-revoke="${h(connection.id)}">撤销连接</button>`:''}</article>`).join('')||'<p class="muted">尚未创建连接。</p>';
  for(const button of document.querySelectorAll('[data-revoke]'))button.onclick=()=>start({action:'revoke',connection_id:button.dataset.revoke,request_id:crypto.randomUUID()});
}
async function load({withinWrite=false}={}){
  if(withinWrite)clearSecret();else invalidateSensitive();
  const version=++loadVersion,identityEpoch=epoch;directorySnapshot=null;ready=false;setBusy(busy);
  try{
    if(!await verifyIdentity({withinWrite:true})||version!==loadVersion||!live(identityEpoch))return false;
    const data=await request('GET','/api/tool-connections');
    if(version!==loadVersion||!live(identityEpoch))return false;
    if(data?.user!==owner||data?.context_token!==context){lock('身份已变化。');return false}
    if(!Array.isArray(data.projects)||!Array.isArray(data.connections))throw Error('连接列表回执不完整。');
    readPending();render(data);directorySnapshot=data;ready=true;pendingView();return data;
  }catch(error){
    if(version===loadVersion&&live(identityEpoch)){ready=false;pendingView();notice('暂不能确认连接状态。请刷新列表后再操作。'+error.message,true)}
    return false;
  }
}
function validateReceipt(result,body){
  const item=result?.connection;
  if(!item||item.user!==owner||item.tenant!==tenant||typeof item.id!=='string'||!item.id.match(/^[a-f0-9]{32}$/)||result.connection_id!==item.id||typeof result.replayed!=='boolean')throw Error('操作回执不完整或身份不匹配，请核对原请求。');
  if(body.action==='create'){
    if(item.label!==body.label.trim()||item.scope!==body.scope||!sameProjects(item.project_ids,body.project_ids))throw Error('连接范围与原请求不匹配，请核对原请求。');
    if(result.replayed){if(result.token!==undefined||result.credential_unavailable!==true)throw Error('重试回执不完整，请继续核对原请求。')}
    else if(!activeConnection(item,body)||typeof result.token!=='string'||!new RegExp('^wbt_'+item.id+'\\.[A-Za-z0-9_-]{43}$').test(result.token))throw Error('凭据回执不完整或连接已失效，请核对原请求。');
  }else if(item.id!==body.connection_id||item.active!==false||item.status!=='revoked'||result.token!==undefined)throw Error('撤销回执与原请求不匹配，请核对原请求。');
}
async function submitPending(){
  if(!pending||busy||locked)return;
  if(credential){notice('请先保存并清除页面凭据，再核对原请求。',true);return}
  if(!ready){notice('请先刷新列表确认当前连接状态，再核对原请求。',true);return}
  const version=epoch,displayVersion=sensitiveEpoch,original=JSON.parse(JSON.stringify(pending));setBusy(true);
  try{
    persist(original);
    if(!await verifyIdentity({withinWrite:true}))return;
    const result=await request('POST','/api/tool-connections',original);
    validateReceipt(result,original);
    // Keep the secret out of DOM/download until all identity and list readbacks
    // finish. A focus/blur/recheck during this POST invalidates its display epoch.
    const data=await load({withinWrite:true});
    if(!data||!await verifyIdentity({withinWrite:true})||!live(version))return;
    if(result.token)confirmedConnection(result.connection,original,data);
    if(result.token&&displayVersion===sensitiveEpoch)showCredential(result.token,result.connection,original,data);
    let cleanupFailed=false;
    try{cleared()}catch(error){cleanupFailed=true}
    const message=cleanupFailed?'操作已完成，但本机未能清除重试记录。请先核对原请求；若尚未保存凭据，请撤销该连接并重新创建。':result.credential_unavailable?'原创建已完成，但凭据不会再次显示。请在列表中撤销该连接，再重新创建。':result.token?(credential?'连接已创建。请及时保存凭据；重新核对身份时会清除页面凭据。':'操作已完成，但页面或身份核验已变化，本次凭据未显示。请在列表中撤销该连接并重新创建。'):'操作已完成。';
    notice(message,cleanupFailed||!!result.token&&!credential);
  }catch(error){
    if(live(version)){ready=false;pendingView();notice(error.message+' 原请求已保留，请核对后重试。',true)}
  }finally{setBusy(false)}
}
async function start(body){
  if(!live())return;
  if(credential){notice('请先保存并清除页面凭据，再创建或撤销连接。',true);return}
  if(busy)return;
  if(pending){notice('原操作结果尚未核对，请先核对原请求。',true);return}
  if(!ready){notice('请先刷新列表确认连接状态，当前尚未提交新操作。',true);return}
  try{persist(body)}catch(error){ready=false;pendingView();notice('无法保存原请求，尚未提交。请检查浏览器存储后核对原请求。'+error.message,true);return}
  return submitPending();
}
$('#create').onsubmit=event=>{
  event.preventDefault();const ids=[...document.querySelectorAll('[name=project]:checked')];
  if(!ids.length){notice('请选择至少一个获准项目。',true);return}
  if($('#scope').value==='content'&&ids.some(node=>node.dataset.role==='viewer')){notice('只读项目不能授权内容写入。请修改项目选择或改为只读连接。',true);return}
  return start({action:'create',label:$('#label').value,scope:$('#scope').value,project_ids:ids.map(node=>Number(node.value)),expires_days:Number($('#days').value),request_id:crypto.randomUUID()});
};
$('#retry').onclick=async()=>{if(credential){notice('请先保存并清除页面凭据，再核对原请求。',true);return}if(!busy&&await load())return submitPending()};
$('#refresh').onclick=()=>load();
$('#dismiss').onclick=()=>{const hadCredential=!!credential;clearSecret();setBusy(busy);if(hadCredential&&!locked&&!pending&&ready)notice('页面凭据已清除。可在列表管理连接。')};
$('#download').onclick=()=>{
  if(!credential||!live()||!ready||busy)return;
  try{if(!credentialBinding)throw Error('缺少连接核对记录');confirmedConnection(credentialBinding.item,credentialBinding.body,credentialBinding.data)}catch(error){clearSecret();setBusy(busy);notice('连接状态已变化或凭据已过期，页面凭据已清除。请刷新列表核对原连接。',true);return}
  try{const url=URL.createObjectURL(new Blob([JSON.stringify(credential,null,2)+'\n'],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='webuddy-credential.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){notice('凭据下载未完成，请保留页面并复制完整凭据到自己的本地文件。',true)}
};
async function checkIdentity(){
  invalidateSensitive();
  if(busy||!live())return;
  const wasReady=ready,version=loadVersion;ready=false;setBusy(busy);
  try{if(await verifyIdentity({withinWrite:true})&&version===loadVersion){ready=wasReady;setBusy(busy)}}catch(error){if(!locked){ready=false;setBusy(busy);notice('暂不能确认当前身份，页面凭据已清除。请刷新列表；未保存凭据时需撤销该连接并重新创建。',true)}}
}
const identityWatch=setInterval(checkIdentity,15000);
window.addEventListener('focus',checkIdentity);
window.addEventListener('blur',invalidateSensitive);
document.addEventListener('visibilitychange',()=>{if(document.hidden)invalidateSensitive()});
window.addEventListener('pagehide',()=>{clearInterval(identityWatch);lock('当前页面已离开。')});
window.addEventListener('beforeunload',event=>{if(credential){event.preventDefault();event.returnValue='连接凭据尚在页面，请先保存。'}});
load().then(ok=>{if(ok&&!pending)notice('身份已核对。可以为自己的工具授权。')});
</script></body></html>'''
