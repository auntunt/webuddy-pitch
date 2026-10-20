"""Versioned project knowledge: explicit sources, scoped references and safe reads."""

LIBRARY_CSS = r"""
.lib-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;margin-top:18px}.lib-layout>.card{min-width:0}.lib-wide{grid-column:1/-1}.lib-row{padding:14px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.lib-row:last-child{border:0}.lib-row .row{gap:8px;flex-wrap:wrap}.lib-meta{font-size:12px;line-height:1.8;color:var(--mut);overflow-wrap:anywhere}.lib-code{font-family:var(--mono,monospace);word-break:break-all}.lib-raw{white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;padding:14px;background:var(--soft);font-size:12px}.lib-fields{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.lib-fields>label{flex:1;min-width:160px}.lib-check{display:flex!important;gap:8px;align-items:center;font-weight:400!important}.lib-check input{width:auto!important}.lib-status{min-height:22px;overflow-wrap:anywhere}.lib-error{color:var(--red,#a63a32);white-space:pre-wrap}.lib-section{margin-top:18px;border-top:1px solid var(--line);padding-top:16px}.lib-form{margin-top:14px}.lib-form textarea{min-height:72px}.lib-results{margin-top:16px}.lib-file[hidden],.lib-compare[hidden]{display:none}.lib-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}@media(max-width:800px){.lib-layout{grid-template-columns:minmax(0,1fr)}.lib-wide{grid-column:auto}}
#libWorkspaceDialog .tw{overflow-x:auto}#libWorkspaceDialog table.t{table-layout:fixed;width:100%;min-width:42em}#libWorkspaceDialog th:first-child{width:29%}#libWorkspaceDialog th:nth-child(2),#libWorkspaceDialog td:nth-child(2){width:11em;min-width:11em;word-break:normal;overflow-wrap:normal}#libWorkspaceDialog th:first-child,#libWorkspaceDialog td:first-child,#libWorkspaceDialog th:last-child,#libWorkspaceDialog td:last-child{word-break:normal;overflow-wrap:anywhere}
"""

LIBRARY_JS = r"""
const LIB={sequence:0,view:null,drafts:new Map(),pending:new Set(),registrationBusy:false};
const libPath=key=>'/api/projects/'+encodeURIComponent(key);
const libState=s=>({queued:'等待构建',building:'正在构建',ready:'可供引用',failed:'构建失败',cancelled:'已取消'}[s]||s);
const libText=value=>typeof value==='string'?value:JSON.stringify(value??'');
function libraryOperatorField(id){return S.meta?.operator_authenticated===true?'':`<label class="lib-meta">独立操作者凭据（未登录帐号时需要）<input class="full" type="password" id="${id}" autocomplete="off" spellcheck="false"></label><div class="sub">仅随本次管理操作发送，不保存到浏览器草稿；已登录帐号无需填写。</div>`}
function libraryOperationHeaders(c,body,dialogInput){
  const sensitive=['configure','add_source','grant','revoke','derive','maintain'].includes(body.action)||(body.action==='reference'&&body.grant===true);
  if(!sensitive||S.meta?.operator_authenticated===true)return{};
  const field=dialogInput?.value?dialogInput:c.root.querySelector('#libOperator'),value=field?.value||'';
  if(!value)return{};field.value='';return{'X-Webuddy-Operator-Token':value};
}
function libraryOpen(key){setProj(key);if(location.hash==='#/library')render();else location.hash='#/library'}
function libraryCurrent(c){return LIB.view===c&&S.proj===c.key&&curView()==='library'&&$('#libPage')===c.root&&c.root.isConnected}
function libraryNotice(c,message,error=false){if(!libraryCurrent(c))return;const node=c.root.querySelector('#libNotice');node.textContent=message;node.className='lib-status '+(error?'lib-error':'sub')}
function libraryDraft(c,id){const node=c.root.querySelector('#'+id);if(Object.hasOwn(c.draft,id)){
  if(node.type==='checkbox')node.checked=c.draft[id];else node.value=c.draft[id];
}const save=()=>{c.draft[id]=node.type==='checkbox'?node.checked:node.value};node.addEventListener('input',save);node.addEventListener('change',save);return node}
function libraryRevisionOptions(revisions){return '<option value="">选择固定知识版本</option>'+revisions.filter(r=>r.status==='ready').map(r=>`<option value="${h(r.id)}">${h(r.commit)} · ${h(r.created||r.id)}</option>`).join('')}
function libraryReferenceSignature(data){return JSON.stringify((data.references||[]).map(r=>[r.id,r.revision_id,r.scopes,r.purpose,r.available,r.reason]))}
function libraryClearCompare(c){c.compareSequence++;const box=c.root.querySelector('#libCompare');box.hidden=true;box.innerHTML='';return c.compareSequence}
function libraryClearSearch(c,message){c.searchSequence++;c.fileSequence++;libraryClearCompare(c);c.search=null;const box=c.root.querySelector('#libResults');box.innerHTML='';c.root.querySelector('#libFile').hidden=true;c.root.querySelector('#libSearchGo').disabled=false;c.root.querySelector('#libSearchStatus').textContent=message||''}
async function vLibrary(){
  const key=S.proj,sequence=++LIB.sequence,route=location.hash;
  let data;try{data=await get(libPath(key)+'/library')}catch(error){if(sequence===LIB.sequence&&S.proj===key&&location.hash===route)throw error;return}
  if(sequence!==LIB.sequence||S.proj!==key||location.hash!==route||curView()!=='library')return;
  if(!LIB.drafts.has(key))LIB.drafts.set(key,{});
  $('#main').innerHTML=`<div id="libPage"><div class="hdr"><h1 class="grow">知识与引用</h1><button id="libRefresh">更新状态</button></div>
  <p class="sub">项目资料按固定提交保存。检索只使用当前项目和明确绑定的来源，来源知识不代表当前项目已经验收。</p>
  <div class="form">${libraryOperatorField('libOperator')}</div>
  <div id="libNotice" class="lib-status sub" role="status" aria-live="polite"></div><div class="lib-layout">
  <section class="card"><h2>项目与来源</h2><div id="libProject"></div><details class="lib-section"><summary>项目角色与工作流</summary>
  <form id="libProfileForm" class="form lib-form"><label class="lib-check"><input id="libProduct" type="checkbox">标品项目</label><label class="lib-check"><input id="libReference" type="checkbox">可作为参考项目</label>
  <label>工作流<select id="libWorkflow"><option value="reference">仅供知识查阅</option><option value="development">开发与维护</option></select></label><div class="sub">角色可以组合。仅供查阅时禁止执行；开始维护请从下方已发布版本创建独立工作区。</div><div><button id="libProfileSave">保存设置</button></div></form></details></section>
  <section class="card"><h2>固定知识版本</h2><form id="libBuildForm" class="form lib-form"><label>Git 提交、标签或分支<input class="full" id="libCommit" value="HEAD" placeholder="HEAD"></label><div><button id="libBuild" class="primary">构建固定快照</button></div><div class="sub">只静态读取已提交的代码与文档，不执行项目脚本。未提交改动不进入固定版本。</div></form><div id="libRevisions"></div></section>
  <section class="card lib-wide"><h2>参考项目</h2><p class="sub">每个来源独立保留项目、版本和模块范围。新增来源不会自动包含它所引用的其他项目。</p><div id="libReferences"></div>
  <form id="libReferenceForm" class="form lib-section"><div class="lib-fields"><label>来源项目<select id="libSource"><option value="">选择已有项目</option>${S.projects.filter(p=>p.key!==key).map(p=>`<option value="${h(p.key)}">${h(p.key)} · ${h(p.name)}</option>`).join('')}</select></label><label>固定版本<select id="libSourceRevision" disabled><option value="">先选择来源项目</option></select></label></div>
  <div id="libSourceStatus" class="sub lib-status" role="status"></div><div class="grid2"><label>引用模块范围（每行一个相对路径）<textarea class="full" id="libScopes" placeholder="src/approval\ndocs/workflow"></textarea><span class="sub">留空表示整个固定快照；填写目录时仅包含该目录及其子目录。</span></label><label>引用用途<textarea class="full" id="libPurpose" placeholder="例如：参考审批规则与接口设计"></textarea></label></div>
  <label class="lib-check"><input type="checkbox" id="libGrant">我有权允许此来源向当前项目共享上述范围，并明确授权</label><div class="sub">已有授权可以直接引用；超出授权的范围需要明确允许。项目角色不会自动授予共享权限。</div><div><button id="libReferenceAdd" class="primary">添加固定引用</button></div></form></section>
  <section class="card lib-wide"><h2>查阅项目知识</h2><form id="libSearchForm" class="lib-fields"><label>代码、业务或文档关键词<input class="full" id="libQuery" placeholder="输入关键词"></label><button id="libSearchGo" class="primary">检索</button></form><div id="libSearchStatus" class="sub lib-status" role="status"></div><div id="libResults" class="lib-results"></div>
  <section id="libFile" class="lib-file lib-section" hidden></section><section id="libCompare" class="lib-compare lib-section" hidden></section></section></div></div>`;
  const c={key,root:$('#libPage'),draft:LIB.drafts.get(key),data,refreshSequence:0,searchSequence:0,fileSequence:0,compareSequence:0,sourceSequence:0,refSignature:libraryReferenceSignature(data),busy:new Set()};LIB.view=c;
  c.root.querySelector('#libProduct').checked=(data.profile.roles||[]).includes('product');c.root.querySelector('#libReference').checked=(data.profile.roles||[]).includes('reference');
  c.root.querySelector('#libWorkflow').value=data.profile.workflow;
  // Enabling development requires the explicit, baseline-bound maintenance action.
  c.root.querySelector('#libWorkflow').disabled=data.profile.workflow==='reference';
  for(const id of ['libCommit','libSource','libScopes','libPurpose','libQuery'])libraryDraft(c,id);
  libraryPaint(c,data);
  c.root.querySelector('#libRefresh').onclick=()=>libraryRefresh(c);
  c.root.querySelector('#libProfileForm').onsubmit=e=>{e.preventDefault();const roles=[];if(c.root.querySelector('#libProduct').checked)roles.push('product');if(c.root.querySelector('#libReference').checked)roles.push('reference');return libraryAction(c,{action:'configure',roles,workflow:c.root.querySelector('#libWorkflow').value},c.root.querySelector('#libProfileSave'),'项目设置已保存')};
  c.root.querySelector('#libBuildForm').onsubmit=e=>{e.preventDefault();return libraryAction(c,{action:'build',commit:c.root.querySelector('#libCommit').value.trim()||'HEAD'},c.root.querySelector('#libBuild'),'构建已登记，状态将在此处更新')};
  c.root.querySelector('#libSource').onchange=()=>libraryLoadSource(c);c.root.querySelector('#libSourceRevision').onchange=()=>{c.draft.libSourceRevision=c.root.querySelector('#libSourceRevision').value;c.root.querySelector('#libGrant').checked=false};
  c.root.querySelector('#libScopes').addEventListener('input',()=>{c.root.querySelector('#libGrant').checked=false});
  c.root.querySelector('#libReferenceForm').onsubmit=e=>{e.preventDefault();const revision=c.root.querySelector('#libSourceRevision').value;if(!revision||c.sourceKey!==c.root.querySelector('#libSource').value)return libraryNotice(c,'请先选择来源项目的可用固定版本。',true);const body={action:'reference',revision_id:revision,scopes:c.root.querySelector('#libScopes').value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),purpose:c.root.querySelector('#libPurpose').value.trim(),grant:c.root.querySelector('#libGrant').checked};return libraryAction(c,body,c.root.querySelector('#libReferenceAdd'),'固定引用已添加',()=>{c.root.querySelector('#libGrant').checked=false})};
  c.root.querySelector('#libSearchForm').onsubmit=e=>{e.preventDefault();return librarySearch(c,0)};
  if(c.root.querySelector('#libSource').value)await libraryLoadSource(c);
  if(libraryCurrent(c))poll(()=>libraryRefresh(c),5000,'page');
}
function libraryPaint(c,data){
  if(!libraryCurrent(c))return;const previous=c.data;c.data=data;const workflow=c.root.querySelector('#libWorkflow');workflow.disabled=data.profile.workflow==='reference';if(previous.profile.workflow!==data.profile.workflow)workflow.value=data.profile.workflow;
  c.root.querySelector('#libProject').innerHTML=`<b>${h(data.project.key)} · ${h(data.project.name)}</b><div class="lib-meta">${data.profile.workflow==='reference'?'仅供知识查阅':'开发与维护'} · ${(data.profile.roles||[]).map(x=>h(({product:'标品',reference:'参考项目'})[x]||x)).join('、')||'普通项目'}<br>当前项目目录：<span class="lib-code">${h(data.project.root)}</span></div>${(data.sources||[]).map(s=>`<div class="lib-meta">固定来源 ${h(s.id)}：<span class="lib-code">${h(s.root)}</span></div>`).join('')}${data.derivation?`<div class="lib-section lib-meta">派生自 ${h(data.derivation.source_project)}<br>基线 <span class="lib-code">${h(data.derivation.commit)}</span><br>知识版本 ${h(data.derivation.revision_id)}</div>`:''}`;
  c.root.querySelector('#libRevisions').innerHTML=(data.revisions||[]).map(r=>`<article class="lib-row"><div class="row"><b>${h(libState(r.status))}</b><span class="sub">${h(r.stage||'')} · ${h(r.created||'')}</span></div><div class="lib-meta">提交 <span class="lib-code">${h(r.commit)}</span><br>知识版本 <span class="lib-code">${h(r.id)}</span></div>${r.summary?`<div class="lib-meta">清单 ${h(r.summary.files??'待统计')} · 排除 ${h(r.summary.excluded??'待统计')} · 已索引 ${h(r.summary.indexed??'待统计')} · 耗时 ${h(r.summary.seconds??'待统计')} 秒</div>`:''}${r.error?`<pre class="lib-error">${h(r.error)}</pre>`:''}<div class="lib-actions">${['queued','building'].includes(r.status)?`<button data-lib-action="cancel" data-revision="${h(r.id)}">取消构建</button>`:''}${['failed','cancelled'].includes(r.status)?`<button data-lib-action="resume" data-revision="${h(r.id)}">继续构建</button>`:''}${r.status==='ready'?`<button data-lib-action="compare" data-revision="${h(r.id)}">比较当前代码</button><button data-lib-action="derive" data-revision="${h(r.id)}">派生客户项目</button>${data.profile.workflow==='reference'?`<button data-lib-action="maintain" data-revision="${h(r.id)}">开始维护本项目</button>`:''}`:''}</div></article>`).join('')||'<p class="sub">尚未构建固定快照。选择提交后开始构建。</p>';
  c.root.querySelector('#libReferences').innerHTML=(data.references||[]).map(r=>`<article class="lib-row"><div class="row"><b>${h(r.source_project)} · ${h(r.source_name)}</b><div class="lib-actions"><button data-lib-action="compare" data-revision="${h(r.revision_id)}" ${r.available===false?'data-lib-unavailable="1" disabled':''}>比较当前代码</button><button data-lib-remove="${h(r.id)}">移除引用</button></div></div><div class="lib-meta">提交 <span class="lib-code">${h(r.commit)}</span><br>知识版本 ${h(r.revision_id)}<br>范围：${r.scopes?.length?r.scopes.map(h).join('、'):'整个固定快照'}<br>用途：${h(r.purpose||'未填写')}<br>参考资料，当前项目适用性待核对</div>${r.available===false?`<p class="lib-error">来源不可用：${h(r.reason||'共享授权已撤销或范围已改变')}。请重新获得授权或明确移除引用。</p>`:''}</article>`).join('')||'<p class="sub">尚未绑定参考来源。可以分别添加两个或更多来源。</p>';
  c.root.querySelectorAll('[data-lib-action]').forEach(button=>{const action=button.dataset.libAction,revision=button.dataset.revision;button.onclick=()=>{if(button.disabled)return;if(['derive','maintain'].includes(action))return libraryWorkspace(c,action,revision);return libraryAction(c,{action,revision_id:revision},button,action==='cancel'?'取消请求已记录':action==='resume'?'已继续构建':'代码比较已更新',action==='compare'?r=>libraryCompare(c,r):null)}});
  c.root.querySelectorAll('[data-lib-remove]').forEach(button=>{button.onclick=()=>{if(button.disabled)return;return libraryAction(c,{action:'remove_reference',binding_id:button.dataset.libRemove},button,'引用已移除')}});
  librarySyncButtons(c);
}
function librarySyncButtons(c){c.root.querySelectorAll('[data-lib-action]').forEach(b=>{b.disabled=b.dataset.libUnavailable==='1'||LIB.pending.has(c.key+':'+b.dataset.libAction+':'+b.dataset.revision)});c.root.querySelectorAll('[data-lib-remove]').forEach(b=>{b.disabled=LIB.pending.has(c.key+':remove_reference:'+b.dataset.libRemove)})}
async function libraryRefresh(c){
  if(!libraryCurrent(c))return;const sequence=++c.refreshSequence;
  try{const data=await get(libPath(c.key)+'/library');if(!libraryCurrent(c)||sequence!==c.refreshSequence)return;
    const signature=libraryReferenceSignature(data);if(signature!==c.refSignature){c.refSignature=signature;libraryClearSearch(c,'引用集合已变化，请重新检索以核对当前来源。')}
    libraryPaint(c,data);
  }catch(error){if(libraryCurrent(c)&&sequence===c.refreshSequence)libraryNotice(c,'暂时无法更新状态：'+error.message,true)}
}
async function libraryAction(c,body,button,message,onSuccess){
  if(!libraryCurrent(c))return;const token=c.key+':'+body.action+':'+(body.revision_id||body.binding_id||'');if(LIB.pending.has(token))return;
  // A comparison belongs to the latest requested source and reference scope.
  const compareSequence=body.action==='compare'?libraryClearCompare(c):null,current=()=>libraryCurrent(c)&&(compareSequence===null||compareSequence===c.compareSequence);
  LIB.pending.add(token);button.disabled=true;librarySyncButtons(c);libraryNotice(c,'正在处理…');
  try{const result=await post(libPath(c.key)+'/library',body,libraryOperationHeaders(c,body));if(!current())return;
    libraryNotice(c,message);if(onSuccess)onSuccess(result);await libraryRefresh(c);return result;
  }catch(error){if(current())libraryNotice(c,error.message,true)}finally{LIB.pending.delete(token);if(libraryCurrent(c)){button.disabled=false;librarySyncButtons(c)}}
}
async function libraryLoadSource(c){
  if(!libraryCurrent(c))return;const select=c.root.querySelector('#libSourceRevision'),status=c.root.querySelector('#libSourceStatus'),key=c.root.querySelector('#libSource').value,sequence=++c.sourceSequence;
  c.sourceKey='';c.root.querySelector('#libGrant').checked=false;select.disabled=true;select.innerHTML='<option value="">'+(key?'正在读取版本…':'先选择来源项目')+'</option>';status.textContent='';if(!key)return;
  try{const data=await get(libPath(key)+'/library');if(!libraryCurrent(c)||sequence!==c.sourceSequence||key!==c.root.querySelector('#libSource').value)return;
    c.sourceKey=key;select.innerHTML=libraryRevisionOptions(data.revisions||[]);select.disabled=false;if((data.revisions||[]).some(r=>r.status==='ready'&&r.id===c.draft.libSourceRevision))select.value=c.draft.libSourceRevision;
    status.textContent=(data.revisions||[]).some(r=>r.status==='ready')?'仅能引用这里明确选择的版本。':'此来源还没有可用固定快照，请先进入该项目构建。';
  }catch(error){if(libraryCurrent(c)&&sequence===c.sourceSequence)status.textContent='来源不可用：'+error.message}
}
async function librarySearch(c,offset,queryOverride){
  if(!libraryCurrent(c))return;const query=queryOverride??c.root.querySelector('#libQuery').value.trim();if(!query)return libraryNotice(c,'请输入检索关键词。',true);
  const sequence=++c.searchSequence,button=c.root.querySelector('#libSearchGo'),status=c.root.querySelector('#libSearchStatus');button.disabled=true;status.textContent='正在检索明确绑定的来源…';c.root.querySelector('#libResults').innerHTML='';c.fileSequence++;c.root.querySelector('#libFile').hidden=true;
  try{const result=await get(libPath(c.key)+'/knowledge/search?q='+encodeURIComponent(query)+'&limit=20&offset='+offset);if(!libraryCurrent(c)||sequence!==c.searchSequence)return;
    c.search={query,...result};c.fileSequence++;c.root.querySelector('#libFile').hidden=true;
    status.textContent=`“${query}”共 ${result.total} 条；当前 ${result.items.length?result.offset+1:0}–${result.offset+result.items.length} 条。`+(result.unavailable?.length?' 部分来源不可用：'+result.unavailable.map(libText).join('；'):'');
    c.root.querySelector('#libResults').innerHTML=result.items.map((item,index)=>`<article class="lib-row"><b>${h(item.title||item.id)}</b><div class="lib-meta">${h(item.source_project)} · ${h(item.source_name)} · ${h(({current:'当前项目',reference:'参考来源'})[item.relation]||item.relation||'当前项目')}<br>提交 <span class="lib-code">${h(item.commit)}</span><br>知识版本 ${h(item.revision_id)}<br>${h(item.path)}${item.line?':'+h(item.line):''} · ${h(item.kind)}<br>适用性：${h(libText(item.applicability||'待核对'))}</div><pre class="lib-raw">${h(item.excerpt)}</pre>${item.excerpt_truncated?'<p class="sub">这里只展示前 600 个字符的片段；下方完整原文保留全部内容。</p>':''}<button data-lib-file="${index}">打开该版本完整原文</button></article>`).join('')+(result.items.length?'':'<p class="sub">当前范围没有命中。未绑定来源不会参与检索。</p>')+`<div class="lib-actions"><button id="libPrev" ${result.offset<=0?'disabled':''}>上一页</button><button id="libNext" ${result.offset+result.items.length>=result.total?'disabled':''}>下一页</button></div>`;
    c.root.querySelectorAll('[data-lib-file]').forEach(b=>{b.onclick=()=>libraryFile(c,result.items[Number(b.dataset.libFile)])});
    c.root.querySelector('#libPrev').onclick=()=>librarySearch(c,Math.max(0,result.offset-result.limit),query);c.root.querySelector('#libNext').onclick=()=>librarySearch(c,result.offset+result.limit,query);
  }catch(error){if(libraryCurrent(c)&&sequence===c.searchSequence)status.textContent='检索失败：'+error.message}finally{if(libraryCurrent(c)&&sequence===c.searchSequence)button.disabled=false}
}
async function libraryFile(c,item){
  if(!libraryCurrent(c))return;const sequence=++c.fileSequence,box=c.root.querySelector('#libFile');box.hidden=false;box.innerHTML='<p class="sub">正在读取固定版本原文…</p>';
  try{const result=await get(libPath(c.key)+'/knowledge/file?revision_id='+encodeURIComponent(item.revision_id)+'&path='+encodeURIComponent(item.path));if(!libraryCurrent(c)||sequence!==c.fileSequence)return;
    if(result.revision_id!==item.revision_id||result.path!==item.path||result.commit!==item.commit||result.source_project!==item.source_project)throw Error('原文来源与所选检索结果不一致，请重新检索。');
    if(!['utf-8','base64'].includes(result.encoding)||(result.encoding==='base64'&&(!/^[A-Za-z0-9+/]*={0,2}$/.test(result.content)||result.content.length%4)))throw Error('原文件编码无法识别，未进行转码。');
    box.innerHTML=`<h3>完整原文 · ${h(result.path)}</h3><div class="lib-meta">来源 ${h(result.source_project)} · 知识版本 ${h(result.revision_id)}<br>提交 <span class="lib-code">${h(result.commit)}</span><br>SHA-256 <span class="lib-code">${h(result.sha256)}</span></div>${result.encoding==='base64'?`<p class="sub">此文件保留为原始字节。下方展示完整 Base64 编码，可下载原文件。</p><a class="btn" download="${h(result.path.split('/').pop())}" href="data:application/octet-stream;base64,${h(result.content)}">下载原始文件</a>`:''}<pre class="lib-raw">${h(result.content)}</pre>`;
  }catch(error){if(libraryCurrent(c)&&sequence===c.fileSequence)box.innerHTML='<p class="lib-error">无法读取原文：'+h(error.message)+'</p>'}
}
function libraryCompare(c,result){if(!libraryCurrent(c))return;const box=c.root.querySelector('#libCompare');box.hidden=false;box.innerHTML=`<h3>与当前代码比较</h3><div class="lib-meta">固定基线 <span class="lib-code">${h(result.base_commit)}</span><br>当前提交 <span class="lib-code">${h(result.current_commit)}</span></div><p>${h(result.note||'')}</p>${result.changed?.length?`<div class="tw"><table class="t"><tr><th>状态</th><th>路径</th></tr>${result.changed.map(x=>`<tr><td>${h(x.status)}</td><td>${h(x.path)}</td></tr>`).join('')}</table></div>`:'<p class="sub">未发现已提交文件差异。</p>'}${result.unknown?.length?'<p class="lib-error">仍有未知影响：</p><pre class="lib-raw">'+h(result.unknown.map(libText).join('\n'))+'</pre>':''}`}
function libraryWorkspace(c,action,revision){
  if(!libraryCurrent(c))return;const fixed=c.data.revisions.find(r=>r.id===revision&&r.status==='ready');if(!fixed)return;
  const derive=action==='derive';modal(`<div id="libWorkspaceDialog"><h2>${derive?'派生客户项目':'开始维护本项目'}</h2><p>${derive?'创建新的项目身份和独立工作区，保留标品来源与固定基线。':'保留当前项目身份、知识和历史，创建独立可写工作区。原来源和已发布版本继续保留。'}</p><p>来源任务、验收和验证记录会完整归档为来源历史；知识需要在本项目重新确认。</p><p class="lib-meta">来源 ${h(c.key)}<br>代码基线 <span class="lib-code">${h(fixed.commit)}</span><br>知识版本 ${h(revision)}</p><form id="libWorkspaceForm" class="form">${derive?'<label>新项目代号<input class="full" id="libDerivedKey" required placeholder="CLIENTA"></label><label>新项目名称<input class="full" id="libDerivedName" required placeholder="客户甲项目"></label>':''}${libraryOperatorField('libWorkspaceOperator')}<p class="sub">此操作不启动智能体、合并代码或部署应用。</p><div><button id="libWorkspaceGo" class="primary">${derive?'创建客户项目':'创建维护工作区'}</button></div><div id="libWorkspaceStatus" role="status" class="lib-status"></div></form></div>`);
  const dialog=$('#libWorkspaceDialog'),button=$('#libWorkspaceGo'),status=$('#libWorkspaceStatus'),current=()=>libraryCurrent(c)&&$('#libWorkspaceDialog')===dialog&&!$('#modal').hidden;
  $('#libWorkspaceForm').onsubmit=async e=>{e.preventDefault();if(!current())return;const token=c.key+':'+action+':'+revision;if(LIB.pending.has(token))return;
    const body={action,revision_id:revision};if(derive){body.key=$('#libDerivedKey').value.trim();body.name=$('#libDerivedName').value.trim();if(!body.key||!body.name){status.textContent='请填写新项目代号和名称。';return}}
    LIB.pending.add(token);button.disabled=true;status.textContent='正在创建独立工作区…';
    try{const result=await post(libPath(c.key)+'/library',body,libraryOperationHeaders(c,body,$('#libWorkspaceOperator')));if(!current())return;
      // The mutation has succeeded: show its receipt before any fallible refresh,
      // so a list-read failure cannot offer a second workspace creation.
      S.projects=S.projects.filter(p=>p.key!==result.project.key).concat(result.project);paintSel();
      dialog.innerHTML=`<h2>${derive?'客户项目已创建':'本项目已进入维护'}</h2><p>${h(result.project.key)} · ${h(result.project.name)}</p><p class="lib-meta">来源提交 <span class="lib-code">${h(result.source_commit||fixed.commit)}</span><br>原始导入提交 <span class="lib-code">${h(result.import_commit||result.commit)}</span><br>工作区提交 <span class="lib-code">${h(result.commit)}</span></p>${result.initialization?.length?`<details open><summary>工作区初始化记录（完整）</summary><div class="tw"><table class="t"><tr><th>来源路径</th><th>处理</th><th>归档位置</th></tr>${result.initialization.map(x=>`<tr><td>${h(x.path)}</td><td>${h(({archive_source_history:'完整归档为来源历史',requires_current_project_confirmation:'需要本项目重新确认'})[x.action]||x.action)}</td><td>${h(x.destination||'')}</td></tr>`).join('')}</table></div></details>`:''}<button id="libWorkspaceOpen" class="primary">打开${derive?'客户项目':'本项目'}</button><div id="libWorkspaceRefresh" class="lib-status sub"></div>`;
      $('#libWorkspaceOpen').onclick=()=>{if(!current())return;closeModal();libraryOpen(result.project.key)};
      try{const projects=await get('/api/projects');if(!current())return;S.projects=projects;paintSel()}catch(error){if(current())$('#libWorkspaceRefresh').textContent='项目已创建，列表暂未刷新：'+error.message}
      await libraryRefresh(c);
    }catch(error){if(current())status.textContent=error.message}finally{LIB.pending.delete(token);if(current())button.disabled=false}
  };
}
function libraryRegisterProject(){
  modal(`<div id="libRegisterDialog"><h2>登记已有项目</h2><form id="libRegisterForm" class="form"><label>项目目录（本机绝对路径）<input class="full" id="pr" required placeholder="/Users/me/workspace/product"></label><div class="row"><label>代号（工单编号前缀）<input id="pk" required placeholder="OA" size="8"></label><label class="grow">名称<input class="full" id="pn" placeholder="OA 标品"></label></div><div class="row"><label class="lib-check"><input type="checkbox" id="libRegisterProduct">标品项目</label><label class="lib-check"><input type="checkbox" id="libRegisterReference">参考项目</label></div><label>工作流<select id="libRegisterWorkflow"><option value="development">开发与维护</option><option value="reference">仅供知识查阅</option></select></label><p class="sub">登记不会执行来源脚本。查阅项目可构建固定知识版本，之后通过“开始维护”创建独立工作区；角色不授予跨项目共享权限。</p><div><button class="primary" id="pa">登记项目</button></div><div id="libRegisterStatus" class="lib-status" role="status"></div></form></div>`);
  const dialog=$('#libRegisterDialog'),button=$('#pa'),status=$('#libRegisterStatus'),project=S.proj,route=location.hash,current=()=>$('#libRegisterDialog')===dialog&&!$('#modal').hidden&&S.proj===project&&location.hash===route;
  button.disabled=LIB.registrationBusy;
  $('#pr').oninput=()=>{const name=$('#pr').value.split('/').filter(Boolean).pop()||'';if(!$('#pk').dataset.t)$('#pk').value=name.replace(/[^A-Za-z0-9]/g,'').slice(0,3).toUpperCase()};$('#pk').oninput=()=>$('#pk').dataset.t=1;
  $('#libRegisterForm').onsubmit=async e=>{e.preventDefault();if(!current()||LIB.registrationBusy)return;const roles=[];if($('#libRegisterProduct').checked)roles.push('product');if($('#libRegisterReference').checked)roles.push('reference');
    const body={root:$('#pr').value.trim(),key:$('#pk').value.trim(),name:$('#pn').value.trim(),roles,workflow:$('#libRegisterWorkflow').value};if(!body.root||!body.key){status.textContent='请填写项目目录和代号。';return}
    LIB.registrationBusy=true;button.disabled=true;status.textContent='正在登记…';
    try{const result=await post('/api/projects',body);if(!current())return;S.projects=S.projects.filter(p=>p.key!==result.key).concat(result);closeModal();libraryOpen(result.key)}catch(error){if(current())status.textContent=error.message}finally{LIB.registrationBusy=false;const next=$('#pa');if($('#libRegisterDialog')&&next)next.disabled=false}
  };
}
"""
