"""Tab-local comment drafts. No automatic transmission and no attachment serialization."""

DRAFT_JS = r"""
function commentDraftActor(){return Array.from((S.meta?.login?S.meta.user:S.user||S.meta?.user)||'我').slice(0,40).join('')}
function commentDraftScope(d){return JSON.stringify([...(S.meta?.access?.tenant?.id?[S.meta.access.tenant.id]:[]),S.meta?.data_dir||'',S.meta?.login?S.meta.user:S.user||S.meta?.user||'',d.project.id,d.project.key,d.ticket.id,d.ticket.key,d.ticket.created])}
function commentDraftOpen(scope,storage,cache){
  if(cache.has(scope))return cache.get(scope);
  const e={key:'tmh.comment.v1:'+scope,record:{version:1,body:'',revision:0,pending:null},busy:false,error:'',blocked:false,storage};
  try{const raw=storage.getItem(e.key);if(raw!==null){
    const r=JSON.parse(raw),p=r?.pending;
    if(r?.version!==1||typeof r.body!=='string'||!Number.isSafeInteger(r.revision)||r.revision<0||
      (p!==null&&(!p||typeof p.body!=='string'||!p.body.trim()||typeof p.request_id!=='string'||!p.request_id||!Number.isSafeInteger(p.revision)||p.revision<0||p.revision>r.revision)))throw Error('草稿格式无法识别');
    e.record=r;
  }}catch(err){e.error='无法读取已有草稿，原记录未覆盖。请保留此页并复制当前文字。';e.blocked=true}
  cache.set(scope,e);return e;
}
function commentDraftSave(e){
  if(e.blocked)return false;
  try{if(e.record.body||e.record.pending)e.storage.setItem(e.key,JSON.stringify(e.record));else e.storage.removeItem(e.key);
    e.error='';return true;
  }catch(err){e.error='未能保存草稿。请先复制文字，避免刷新或关闭页面；存储恢复后可再次发送。';return false}
}
function commentDraftChange(e,body){if(e.record.body!==body){e.record.body=body;e.record.revision++;}return commentDraftSave(e)}
function commentDraftBegin(e,id){
  if(!e.record.pending){if(!e.record.body.trim())return null;e.record.pending={request_id:id,body:e.record.body,revision:e.record.revision};}
  return commentDraftSave(e)?e.record.pending:null;
}
function commentDraftComplete(e,pending){
  if(e.record.pending?.request_id!==pending.request_id)return false;
  if(e.record.revision===pending.revision&&e.record.body===pending.body)e.record.body='';
  e.record.pending=null;commentDraftSave(e);return true;
}
function ticketCommentWire(d){
  const scope=commentDraftScope(d),user=commentDraftActor(),workspace=S.meta?.data_dir||S.meta?.workspace||'',key=d.ticket.key,input=$('#cm'),button=$('#cb'),notice=$('#cmDraft'),pendingView=$('#cmPending');
  S.commentDrafts??=new Map();let storage;
  try{storage=sessionStorage}catch(err){storage={getItem(){throw err}}}
  const e=commentDraftOpen(scope,storage,S.commentDrafts);
  const current=()=>$('#cm')===input&&input.isConnected&&S.cur?.ticket?.key===key&&commentDraftScope(d)===scope&&commentDraftActor()===user;
  const paint=()=>{if(!current())return;
    button.disabled=e.busy;button.textContent=e.busy?'正在发送…':e.record.pending?'确认上次发送':'评论';
    notice.textContent=e.error||(e.record.pending?'上次发送结果待确认。点击确认后核对原评论，不会发送下方新写的草稿。':e.record.body?'评论草稿已保存在本标签页，刷新后可恢复。':'评论草稿自动保存在本标签页，不会自动发送。');
    notice.className=e.error?'na warn':'sub';pendingView.hidden=!e.record.pending;
    if(e.record.pending)pendingView.textContent=e.record.pending.body;
  };
  input.value=e.record.body;input.oninput=()=>{if(!current())return;commentDraftChange(e,input.value);paint()};
  S.commentDraftView={entry:e,current,refresh:()=>{if(current()){input.value=e.record.body;paint()}},
    failed:()=>{if(current())notice.textContent=(e.error?e.error+' ':'')+e.message+' 原评论已保留，可点击“确认上次发送”安全重试。';},
    sent:async()=>{if(!current())return;toast(e.record.body?'上一条评论已发送；新写的草稿已保留。':'评论已发送');
      const refresh=S.ticketRefresh;
      if(typeof refresh==='function')try{await refresh()}catch(err){if(current())notice.textContent='评论已发送，讨论列表暂未更新；刷新后查看。'+(e.error||'')}
    }};paint();
  button.onclick=async()=>{
    if(!current()||e.busy)return;
    commentDraftChange(e,input.value);
    let pending;
    try{pending=commentDraftBegin(e,e.record.pending?.request_id||crypto.randomUUID())}catch(err){e.error='无法建立发送回执，请先复制草稿并刷新后再试。';paint();return}
    if(!pending){paint();return}
    e.busy=true;paint();let sent=false;
    try{
      const r=await post('/api/tickets/'+encodeURIComponent(key)+'/comments',{body:pending.body,request_id:pending.request_id,expected_author:user,expected_workspace:workspace});
      if(r?.ok!==true||r.request_id!==pending.request_id||!r.event_id)throw Error('服务器未返回匹配的评论回执，请确认上次发送。');
      commentDraftComplete(e,pending);sent=true;
    }catch(err){e.message='发送结果未确认：'+err.message;}
    finally{e.busy=false;const view=S.commentDraftView;if(view?.entry===e)view.refresh();}
    const view=S.commentDraftView;if(view?.entry!==e||!view.current())return;
    if(sent)await view.sent();else view.failed();
  };
}
window.addEventListener('beforeunload',event=>{
  // Only warn for an actual persistence failure; successful drafts survive a reload.
  if(Array.from(S.commentDrafts?.values()||[]).some(e=>e.error&&(e.record.body||e.record.pending))){event.preventDefault();event.returnValue=''}
});
"""
