// Independent execution of the shipped report controller; minimal DOM/fetch,
// explicitly not a browser or network acceptance.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const path=process.argv[2],out=process.argv[3];
const html=fs.readFileSync(path,'utf8'),script=html.split('<script>')[1].split('</script>')[0];
const controller=script.slice(script.indexOf('function recordVals('),script.indexOf('\nlet tt0 ='));
const approve=script.slice(script.indexOf('async function approve('),script.indexOf('/* ---------- 磅差'));
const initial={id:'r1',version:0,stage:'submitted',doc_type:'site_in',origin_id:'legacy',customer:null,fields:{'总重':'11000','皮重':'10000','净重':'1000','货名':'old','备注':'完整草稿'}};
const fresh={...initial,version:1,fields:{...initial.fields,'总重':'10900','净重':'900'}};
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>structuredClone(body)});
function pending(){let resolve,reject;return{promise:new Promise((res,rej)=>{resolve=res;reject=rej}),get resolve(){return resolve},get reject(){return reject}};}
function make(){
 const nodes=new Map(),notices=[],calls=[],queue=[],confirms=[],adopt=[];
 const node=()=>({value:'',hidden:false,disabled:false,textContent:'',innerHTML:'',className:'',classList:{add(){},remove(){},toggle(){}}});
 const $=s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)};
 const fields=Object.keys(initial.fields),form=[...fields,'doc_type','origin_id','customer'].map(name=>({...node(),name,value:initial.fields[name]??initial[name]??''}));
 for(const f of form)nodes.set(`#form [name=${f.name}]`,f);
 form.find(f=>f.name==='货名').value='A edit';
 const ctx={FIELDS:fields,cur:structuredClone(initial),snapshot:{...initial.fields,doc_type:'site_in',origin_id:'legacy',customer:null},conflict:null,busy:false,
  all:[structuredClone(initial)],selected:new Set(['r1']),$, $$:s=>s==='[data-latest-field]'?adopt:[],inputs:()=>form,
  val:v=>v==null||String(v).trim()===''?null:String(v).trim(),num:Number,fmt:String,esc:s=>String(s??''),
  confirm:s=>{confirms.push(s);return true},toast:s=>notices.push(s),liveCheck(){},nextId:()=>null,
  load:async()=>{ctx.loads++},loads:0,open:id=>ctx.opens.push(id),opens:[],drawSel(){},
  fetch:async(url,options)=>{calls.push({url,options:options?JSON.parse(JSON.stringify(options)):null});const x=queue.shift();if(x instanceof Error)throw x;if(!x)throw Error('unexpected fetch '+url);return await x;},encodeURIComponent};
 ctx.formVals=()=>Object.fromEntries(form.map(f=>[f.name,ctx.val(f.value)]));
 ctx.dirty=()=>!!ctx.cur&&form.some(f=>ctx.val(f.value)!==ctx.snapshot[f.name]);
 vm.createContext(ctx);vm.runInContext(approve+controller,ctx);
 return{ctx,form,$,notices,calls,queue,confirms,adopt};
}
const results=[];
async function run(name,fn){const h=make();try{await fn(h);results.push({name,passed:true,calls:h.calls,notices:h.notices,confirms:h.confirms});}catch(e){results.push({name,passed:false,error:e.stack,calls:h.calls,notices:h.notices,confirms:h.confirms});}}
(async()=>{
 await run('conflict_requires_explicit_confirm_and_preserves_full_draft',async h=>{
  const draft=h.ctx.formVals();h.queue.push(response(409,{error:{message:'stale'}}),response(200,fresh));
  await h.ctx.act('save',false);assert.deepEqual(h.ctx.formVals(),draft);assert.equal(h.ctx.cur.version,0);
  assert.equal(h.ctx.conflict.latest.version,1);await h.ctx.act('save',false);assert.equal(h.calls.length,2);
  h.ctx.confirm=()=>false;h.$('#d-confirm-version').onclick();assert.equal(h.ctx.cur.version,0);assert.equal(h.ctx.conflict.reviewed,false);
  h.ctx.confirm=()=>true;h.form.find(f=>f.name==='净重').value='900';h.form.find(f=>f.name==='总重').value='10900';h.$('#d-confirm-version').onclick();
  assert.equal(h.ctx.cur.version,1);h.queue.push(response(200,{...fresh,version:2,fields:{...fresh.fields,'货名':'A edit'}}));await h.ctx.act('save',false);
  const saved=JSON.parse(h.calls[2].options.body);assert.equal(saved.expected_version,1);assert.equal(saved.fields['净重'],'900');assert.equal(saved.fields['货名'],'A edit');
 });
 await run('lost_ack_and_latest_read_failure_cannot_replay',async h=>{
  const draft=h.ctx.formVals();h.queue.push(new TypeError('Failed to fetch'),response(503,{}));await h.ctx.act('save',false);
  assert.equal(h.ctx.conflict.latest,null);assert.deepEqual(h.ctx.formVals(),draft);await h.ctx.act('approve',true);await h.ctx.act('save',false);
  assert.equal(h.calls.length,2);assert.equal(h.ctx.loads,0);assert.equal(h.ctx.opens.length,0);assert.ok(!h.notices.includes('已保存。'));assert.ok(h.form.every(f=>!f.disabled));
 });
 await run('malformed_success_ack_does_not_approve',async h=>{
  h.queue.push(response(200,{id:'wrong',version:7}),response(200,fresh));await h.ctx.act('approve',true);
  assert.equal(h.calls.length,2);assert.equal(h.calls[1].options,null);assert.ok(h.ctx.conflict);assert.ok(!h.notices.includes('已审核。'));
 });
 await run('save_then_approve_uses_exact_save_ack_version',async h=>{
  h.queue.push(response(200,{...initial,version:5,fields:{...initial.fields,'货名':'A edit'}}),response(200,{approved:['r1'],skipped:[]}));await h.ctx.act('approve',false);
  assert.equal(JSON.parse(h.calls[0].options.body).expected_version,0);assert.equal(JSON.parse(h.calls[1].options.body).versions.r1,5);assert.equal(h.calls.length,2);assert.ok(h.notices.includes('已审核。'));
 });
 await run('partial_batch_reports_skipped',async h=>{
  const second={...initial,id:'r2',version:4};h.ctx.all.push(second);h.ctx.selected.add('r2');
  h.queue.push(response(200,{approved:['r1'],skipped:[{id:'r2',code:'Conflict',reason:'newer revision'}]}));await h.$('#b-approve').onclick();
  const b=JSON.parse(h.calls[0].options.body);assert.deepEqual(b.versions,{r1:0,r2:4});assert.ok(h.notices.some(s=>s.includes('已审核 1 张')&&s.includes('1 张没审')));assert.equal(h.ctx.selected.size,0);
 });
 await run('rejected_approval_keeps_draft_and_cannot_advance',async h=>{
  h.form.find(f=>f.name==='货名').value='old';h.ctx.nextId=()=> 'r2';
  h.queue.push(response(200,{approved:[],skipped:[{id:'r1',code:'Conflict',reason:'newer revision'}]}),response(200,fresh));await h.ctx.act('approve',true);
  assert.ok(h.ctx.conflict);assert.equal(h.ctx.opens.length,0);assert.equal(h.ctx.loads,0);assert.ok(!h.notices.includes('已审核。'));
 });
 await run('late_latest_success_does_not_touch_new_record',async h=>{
  const req=pending();h.queue.push(req.promise);const showing=h.ctx.showConflict('first conflict');
  const other={draft:{},latest:null,reviewed:false};h.ctx.cur={...initial,id:'r2'};h.ctx.conflict=other;
  req.resolve(response(200,fresh));await showing;assert.equal(h.ctx.conflict,other);assert.equal(other.latest,null);
 });
 // This is a regression assertion, not a fabricated failure response: two
 // independently fetched snapshots may complete in the opposite order.
 await run('older_latest_response_must_not_replace_confirmed_newer_view',async h=>{
  h.ctx.conflict={draft:h.ctx.formVals(),latest:null,reviewed:false};
  const first=pending(),second=pending();h.queue.push(first.promise,second.promise);
  const a=h.ctx.readLatest(),b=h.ctx.readLatest();
  const newest={...fresh,version:2,fields:{...fresh.fields,'净重':'800','总重':'10800'}};
  second.resolve(response(200,newest));await b;h.$('#d-confirm-version').onclick();assert.equal(h.ctx.cur.version,2);
  first.resolve(response(200,fresh));await a;
  assert.equal(h.ctx.conflict.latest.version,2,'late older response replaced the displayed/latest snapshot after newer version was confirmed');
 });
 const report={scope:'actual shipped functions with isolated DOM/fetch; no real browser claim',source_sha256:crypto.createHash('sha256').update(html).digest('hex'),passed:results.filter(r=>r.passed).length,total:results.length,results};
 fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(results.some(r=>!r.passed))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1});
