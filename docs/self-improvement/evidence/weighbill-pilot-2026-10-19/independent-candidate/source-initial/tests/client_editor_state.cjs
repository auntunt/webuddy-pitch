// Execute the actual report controller, with a minimal DOM/fetch boundary. No browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('weighbill/static/report.html', 'utf8');
const script = html.split('<script>')[1].split('</script>')[0];
new vm.Script(script); // Entire delivered inline script must parse.
const capture = fs.readFileSync('weighbill/static/capture.html', 'utf8');
new vm.Script(capture.split('<script>')[1].split('</script>')[0]);
new vm.Script(fs.readFileSync('weighbill/static/sw.js', 'utf8'));
const controller = script.slice(script.indexOf('function recordVals('), script.indexOf('\nlet tt0 ='));
const approve = script.slice(script.indexOf('async function approve('), script.indexOf('$("#b-approve").onclick'));
const FIELDS = ['总重', '皮重', '净重', '货名', '备注'];
const base = {id: 'r1', version: 0, stage: 'submitted', doc_type: 'site_in', origin_id: 'legacy', customer: null,
  fields: {'总重':'11000', '皮重':'10000', '净重':'1000', '货名':'old', '备注':'完整备注'}};
const latest = {...base, version: 1, fields: {...base.fields, '净重':'900', '总重':'10900'}};
function harness() {
  const nodes = new Map();
  const $ = s => { if (!nodes.has(s)) nodes.set(s, {value:'', textContent:'', hidden:false, disabled:false, classList:{remove(){}}}); return nodes.get(s); };
  const form = [...FIELDS, 'doc_type','origin_id','customer'].map(name => ({name, value: base.fields[name] ?? base[name] ?? ''}));
  form.find(i=>i.name==='货名').value='A draft';
  for(const i of form) nodes.set(`#form [name=${i.name}]`,i);
  const calls=[], notices=[], queue=[];
  const ctx = {FIELDS, cur: structuredClone(base), snapshot:{...base.fields,doc_type:'site_in',origin_id:'legacy',customer:null},
    conflict:null,busy:false,all:[base],selected:new Set(), $, $$:()=>[], inputs:()=>form,
    val:v=>v==null||String(v).trim()===''?null:String(v).trim(), esc:s=>String(s??''),
    num:v=>Number(v),fmt:String,confirm:()=>true,toast:s=>notices.push(s), liveCheck(){}, nextId:()=>null,
    load:async()=>{},open:()=>{},encodeURIComponent,
    fetch:async (url,opts)=>{calls.push({url,opts});const result=queue.shift();if(result instanceof Error)throw result;if(!result)throw Error('unexpected fetch');return result;}};
  ctx.formVals=()=>Object.fromEntries(form.map(i=>[i.name,ctx.val(i.value)]));
  ctx.dirty=()=>form.some(i=>ctx.val(i.value)!==ctx.snapshot[i.name]);
  vm.createContext(ctx);vm.runInContext(approve+controller,ctx);
  return {ctx,form,calls,notices,queue,$};
}
const response=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(body)});
(async()=>{
  // Real 409 controller path: full draft retained; latest displayed; no blind retry.
  const h=harness();const draft=h.ctx.formVals();
  h.queue.push(response(409,{error:{message:'stale'}}),response(200,latest));
  await h.ctx.act('save',false);
  assert.deepEqual(h.ctx.formVals(),draft);
  assert.equal(h.ctx.cur.version,0);
  assert.equal(h.ctx.conflict.latest.version,1);
  assert.match(h.$('#d-compare').innerHTML,/10900/);
  assert.match(h.$('#d-draft').textContent,/完整备注/);
  await h.ctx.act('save',false);assert.equal(h.calls.length,2);
  // User adopts new weights, explicitly accepts latest version, then saves.
  h.form.find(i=>i.name==='净重').value='900';h.form.find(i=>i.name==='总重').value='10900';
  h.$('#d-confirm-version').onclick();assert.equal(h.ctx.cur.version,1);
  h.queue.push(response(200,{...latest,version:2,fields:{...latest.fields,'货名':'A draft'}}));
  await h.ctx.act('save',false);
  const body=JSON.parse(h.calls[2].opts.body);assert.equal(body.expected_version,1);assert.equal(body.fields['货名'],'A draft');assert.equal(body.fields['净重'],'900');
  assert.equal(h.ctx.conflict,null);
  // Lost ACK and failed GET both preserve draft and block replay.
  const u=harness();u.queue.push(new Error('ACK lost'),response(503,{}));
  await u.ctx.act('save',false);assert.equal(u.ctx.conflict.reviewed,false);assert.equal(u.ctx.conflict.latest,null);
  assert.equal(u.ctx.formVals()['备注'],'完整备注');await u.ctx.act('save',false);assert.equal(u.calls.length,2);
  assert.ok(!u.notices.includes('已保存。'));
  // A successful save must approve exactly its returned version, never a GET'd version.
  const a=harness();a.queue.push(response(200,{...base,version:7,fields:{...base.fields,'货名':'A draft'}}),response(200,{approved:['r1'],skipped:[]}));
  await a.ctx.act('approve',false);assert.equal(JSON.parse(a.calls[1].opts.body).versions.r1,7);assert.ok(a.notices.includes('已审核。'));
  // HTTP failure and per-item conflict must not produce success toast.
  for(const result of [response(403,{error:{message:'forbidden'}}),response(200,{approved:[],skipped:[{id:'r1',code:'Conflict',reason:'stale'}]})]){
    const f=harness();f.form.find(i=>i.name==='货名').value='old';f.queue.push(result,response(200,latest));
    await f.ctx.act('approve',false);assert.ok(!f.notices.includes('已审核。'));assert.ok(f.ctx.conflict);assert.equal(JSON.parse(f.calls[0].opts.body).versions.r1,0);
  }
  console.log('7 editor scenarios passed; report/capture/service-worker scripts parse');
})().catch(e=>{console.error(e);process.exitCode=1;});
