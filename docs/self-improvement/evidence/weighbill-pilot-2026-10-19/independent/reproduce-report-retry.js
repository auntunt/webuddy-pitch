const initial={"id": "synthetic-concurrent-record", "created_at": "2026-10-19T08:20:00", "uploader": "synthetic-uploader", "batch_id": "synthetic-batch", "seq_in_batch": 1, "origin_id": "legacy", "origin_name": "厂商", "orig_path": null, "crop_path": null, "sig_path": null, "fields": {"客户名": "隔离测试客户", "序号": "WB202610190001", "日期": "2026-10-19", "入站时间": "08:00", "出站时间": "08:20", "车号": "鲁A12345", "货名": "原料甲", "收费": "", "总重": "11000", "皮重": "10000", "净重": "1000"}, "warnings": [], "weight_ok": 1, "weight_msg": "11000 - 10000 = 1000", "status": "auto_ok", "model": null, "error": null, "seg_model": null, "reviewed_by": null, "reviewed_at": null, "doc_type": "site_in", "doc_type_label": "本场进场", "customer": null, "stage": "submitted", "stage_label": "未审核", "submitted_by": "synthetic-uploader", "submitted_at": "2026-10-19T08:20:00", "approved_by": null, "approved_at": null, "ref_no": "JC-20261019-0001", "voided_by": null, "voided_at": null, "void_reason": null, "flag_note": null, "thumb_path": null, "preview_path": null};
const draft={"fields": {"客户名": "隔离测试客户", "序号": "WB202610190001", "日期": "2026-10-19", "入站时间": "08:00", "出站时间": "08:20", "车号": "鲁A12345", "货名": "甲只想改货名", "收费": "", "总重": "11000", "皮重": "10000", "净重": "1000"}, "doc_type": "site_in", "customer": "", "origin_id": "legacy"};

const assert=require('node:assert/strict');
let cur=structuredClone(initial),busy=false,fetches=[],loadCount=0;
const FIELDS=Object.keys(draft.fields),buttons=['#d-save','#d-approve','#d-next'];
const nodes=Object.fromEntries([...buttons,'#d-st'].map(k=>[k,{disabled:false,textContent:'',className:''}]));
for(const name of ['总重','皮重','净重'])nodes['#form [name='+name+']']={value:draft.fields[name]};
const $=key=>nodes[key],num=value=>Number(value),fmt=String,confirm=()=>true;
const formVals=()=>({...draft.fields,doc_type:draft.doc_type,customer:draft.customer,origin_id:draft.origin_id});
const dirty=()=>!!cur&&FIELDS.some(k=>String(draft.fields[k]??'')!==String(initial.fields[k]??''));
const selected=new Set([cur.id]),all=[initial],stage='submitted';
const nextId=()=>null,load=async()=>{loadCount++},open=()=>{},closeDrawer=()=>{},toast=()=>{};
let outcome='network';
const fetch=async(path,args)=>{fetches.push({path,method:args.method,headers:args.headers,body:JSON.parse(args.body)});
 if(outcome==='network')throw TypeError('Failed to fetch');
 if(outcome==='conflict')return{ok:false,status:409,json:async()=>({error:{code:'Conflict',message:'这张单刚被别人改过'}})};
 return{ok:true,status:200,json:async()=>({...initial,fields:draft.fields})};
};
async function act(kind, goNext) {
  if (!cur || busy) return;
  const g = num($("#form [name=总重]").value), tt = num($("#form [name=皮重]").value), n = num($("#form [name=净重]").value);
  if (kind === "approve" && g !== null && tt !== null && n !== null && Math.abs(g - tt - n) > 1
      && !confirm(`总重 − 皮重 与净重差 ${fmt(g - tt - n)} kg，说明有数字读错了。\n确定已对照纸质磅单，按现在的数字审核通过？`)) { $("#form [name=净重]").focus(); return; }
  if (cur.stage === "approved" && dirty()
      && !confirm("这张已经审核过（可能已经导出给领导）。改了以后会回到「未审核」，要重新审核，修改会记进修改记录。确定要改？")) return;
  busy = true; for (const b of ["#d-save", "#d-approve", "#d-next"]) $(b).disabled = true;
  $("#d-st").className = "stx"; $("#d-st").textContent = "保存中…";
  const id = cur.id, target = goNext ? nextId() : null;
  try {
    if (dirty()) {
      const v = formVals(), fields = {}; for (const k of FIELDS) fields[k] = v[k];
      const r = await fetch("/api/v1/records/" + encodeURIComponent(id), {method: "PATCH", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({fields, doc_type: v.doc_type, customer: v.customer || "", origin_id: v.origin_id || ""})});
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error((body.error && body.error.message) || `HTTP ${r.status}`);
    }
    if (kind === "approve") {
      const res = await approve([id]);
      if (!res.approved.length) throw new Error(res.skipped.map(s => s.reason).join("、") || "没审成");
    }
    toast(kind === "approve" ? "已审核。" : "已保存。");
    cur = null; selected.delete(id);
    await load(true);
    if (target && all.some(x => x.id === target)) open(target);
    else if (goNext) { closeDrawer(true); toast(stage === "submitted" ? "这个范围里的未审核单据都处理完了。" : "已经是最后一条。"); }
    else if (all.some(x => x.id === id)) open(id); else closeDrawer(true);
  } catch (e) {
    $("#d-st").className = "stx bad"; $("#d-st").textContent = `没有成功：${e.message}。修改还在，可以再点一次。`;
  } finally { busy = false; for (const b of ["#d-save", "#d-approve", "#d-next"]) $(b).disabled = false; }
}

(async()=>{
 const originalDraft=JSON.stringify(draft),messages=[];
 await act('save',false);messages.push(nodes['#d-st'].textContent);
 assert.ok(cur);assert.equal(busy,false);assert.ok(buttons.every(k=>!nodes[k].disabled));
 assert.equal(JSON.stringify(draft),originalDraft);assert.equal(loadCount,0);
 assert.ok(messages[0].includes('修改还在，可以再点一次'));
 outcome='conflict';await act('save',false);messages.push(nodes['#d-st'].textContent);
 assert.ok(cur);assert.equal(JSON.stringify(draft),originalDraft);assert.equal(loadCount,0);
 assert.ok(messages[1].includes('修改还在，可以再点一次'));
 outcome='success';await act('save',false);
 assert.equal(fetches.length,3);assert.deepEqual(fetches[0].body,fetches[1].body);assert.deepEqual(fetches[1].body,fetches[2].body);
 assert.equal(fetches[2].body.fields['净重'],'1000');assert.ok(!('version' in fetches[2].body));
 console.log(JSON.stringify({scope:'Actual shipped act() function with isolated DOM/fetch fixtures; not a browser acceptance',network_and_conflict_keep_draft:true,same_full_old_payload_retried:true,refreshes_before_success:0,messages,fetches},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
