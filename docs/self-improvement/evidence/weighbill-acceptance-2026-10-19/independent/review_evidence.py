"""Read-only independent evidence review; writes only this independent folder.

No service construction, browser, POST, application write, restart or registration.
"""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
HERE=OUT.parent
ROOT=HERE.parents[1]
OLD=ROOT/'data/weighbill-pilot-20261019'
SHA='ab9601e305bf9efdf908554174c56ca101194405'
checks=[]
inputs={}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path):
    raw=path.read_bytes();inputs[str(path)]=dict(bytes=len(raw),sha256=sha(raw));return json.loads(raw)
def save(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def require(name,condition,detail=None):
    result={'name':name,'passed':bool(condition)}
    if detail is not None:result['detail']=detail
    checks.append(result)
    if not condition:raise AssertionError(json.dumps(result,ensure_ascii=False))
def git(repo,*args):return subprocess.check_output(['git',*args],cwd=repo)
def capture(name,args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    save(name,{'args':args,'exit_code':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()})
    require(name+'_exit',p.returncode==0)
    return p.stdout.decode()
def by_id(snapshot):return {r['id']:r for r in snapshot['records']}
def history(snapshot,rid):return snapshot['history'][rid]
transcript=[]
def get(state,path):
    conn=http.client.HTTPConnection('127.0.0.1',state['port'],timeout=10)
    try:
        conn.request('GET',state['prefix']+path)
        response=conn.getresponse();raw=response.read()
        transcript.append({'method':'GET','url':'http://127.0.0.1:'+str(state['port'])+state['prefix']+path,
                           'status':response.status,'headers':dict(response.getheaders()),
                           'body_base64':base64.b64encode(raw).decode(),'body_bytes':len(raw),'body_sha256':sha(raw)})
        require('GET '+path,response.status==200)
        return raw
    finally:conn.close()
def ro_rows(path,queries):
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        return {label:[dict(r) for r in db.execute(query,args)] for label,(query,args) in queries.items()}
    finally:db.close()

try:
    starting=read(HERE/'starting-version.json')
    candidate_before=read(HERE/'candidate-before.json')
    candidate_live=read(OUT/'candidate-live.json')
    state=read(ROOT/'data/product-workbench/previews/state.json')['WBILL-1'];save('preview-state-read.json',state)
    require('same_fixed_candidate',candidate_live['id']==4 and candidate_live['commit']==SHA and candidate_live['run_id']==10 and candidate_live['current'] and not candidate_live['blocked'])
    require('verification_is_current',candidate_live['verification_passed'] and candidate_live['verification']['verification_current'] and candidate_live['verification']['checked_commit']==SHA)
    require('same_verification_binding',candidate_live['verification_hash']==candidate_before['verification_hash'])
    require('same_preview_binding',candidate_live['preview_ready'] and candidate_live['preview_hash']==candidate_before['preview_hash'])
    require('same_requirement_criteria',candidate_live['requirement_hash']==candidate_before['requirement_hash'] and candidate_live['criteria']==candidate_before['criteria'])
    require('no_human_signature',not candidate_live['human_accepted'] and candidate_live['human_decision'] is None)
    require('same_preview_process_identity',state['pid']==starting['preview_pid']==candidate_before['preview']['pid'] and state['commit_full']==SHA and state['started']==candidate_before['preview']['started'])
    cwd=capture('process-cwd.json',['/usr/sbin/lsof','-a','-p',str(state['pid']),'-d','cwd','-Fn'])
    require('actual_cwd_is_fixed_preview',('n'+state['dir']+'\n') in cwd)
    capture('process-command.json',['/bin/ps','-p',str(state['pid']),'-o','pid=,ppid=,lstart=,command='])

    repo=Path(state['root']);worktree=Path(state['dir'])
    require('clone_and_serving_HEAD',git(repo,'rev-parse','HEAD').decode().strip()==SHA and git(worktree,'rev-parse','HEAD').decode().strip()==SHA)
    require('clone_and_serving_tracked_clean',not git(repo,'status','--porcelain','--untracked-files=no').strip() and not git(worktree,'status','--porcelain','--untracked-files=no').strip())
    tracked=git(worktree,'ls-files','-z').decode().split('\0');manifest={}
    for name in tracked:
        if not name:continue
        actual=(worktree/name).read_bytes();expected=git(worktree,'show',SHA+':'+name)
        manifest[name]={'actual_sha256':sha(actual),'commit_sha256':sha(expected),'equal':actual==expected}
    save('serving-source-files.json',manifest)
    require('all_tracked_preview_bytes_match_commit',all(v['equal'] for v in manifest.values()),{'files':len(manifest)})
    rendered=get(state,'/report');expected=git(worktree,'show',SHA+':weighbill/static/report.html').decode().replace('__WB_BASE_PATH__',state['prefix']).encode()
    require('actual_HTTP_page_matches_fixed_source',rendered==expected,{'sha256':sha(rendered),'bytes':len(rendered)})

    names=['before-resume','after-reconciled-save','after-approval','after-stale-approval']
    snapshots={n:read(HERE/('preview-'+n+'.json')) for n in names}
    initial=read(OLD/'preview-before-browser.json');old_conflict=read(OLD/'preview-after-a-conflict.json')
    require('snapshots_use_same_prefix_and_commit',all(s['commit']==SHA and s['prefix']==state['prefix'] and s['port']==state['port'] for s in [initial,old_conflict,*snapshots.values()]))
    require('resume_continues_prior_conflict_state',snapshots['before-resume']['records']==old_conflict['records'] and snapshots['before-resume']['history']==old_conflict['history'])
    rid='wbill-preview-1';before,saved,approved,stale=[by_id(snapshots[n])[rid] for n in names]
    require('record_versions_and_stages',[(r['version'],r['stage']) for r in [before,saved,approved,stale]]==[(1,'submitted'),(2,'submitted'),(3,'approved'),(3,'approved')])
    expected_fields=dict(before['fields'],货名='双人协作核对后的原料',备注='A 的完整草稿：保留货名修改与备注；重量需采用 B 已核对的新值。')
    require('save_retains_exact_A_draft_and_B_weights',saved['fields']==expected_fields and [saved['fields'][k] for k in ['总重','皮重','净重']]==['10900','10000','900'])
    require('approval_changes_only_approval_fields', {k:v for k,v in approved.items() if k not in ['version','stage','stage_label','approved_by','approved_at']}=={k:v for k,v in saved.items() if k not in ['version','stage','stage_label','approved_by','approved_at']})
    hs=[history(snapshots[n],rid) for n in names]
    require('append_only_exact_history',len(hs[0])==1 and len(hs[1])==2 and len(hs[2])==3 and hs[1][:-1]==hs[0] and hs[2][:-1]==hs[1])
    require('save_history_is_only_intended_fields',hs[1][-1]['action']=='修改' and hs[1][-1]['detail']['changes']=={'货名':[before['fields']['货名'],saved['fields']['货名']],'备注':[before['fields']['备注'],saved['fields']['备注']]})
    require('approval_has_real_domain_history',hs[2][-1]['action']=='审核通过' and hs[2][-1]['actor']==approved['approved_by']=='本地验收员' and hs[2][-1]['at']==approved['approved_at'])
    require('stale_approval_no_record_history_or_event_side_effect',snapshots['after-approval']==snapshots['after-stale-approval'])
    untouched={}
    for other in ['wbill-preview-2','wbill-preview-3']:
        reference=by_id(initial)[other];untouched[other]=all(by_id(s)[other]==reference and history(s,other)==[] for s in [old_conflict,*snapshots.values()])
    require('other_two_records_untouched',all(untouched.values()),untouched)

    records=json.loads(get(state,'/api/v1/records?stage=&voided=all'))['records']
    histories={r['id']:json.loads(get(state,'/api/v1/records/'+r['id']+'/history'))['history'] for r in records}
    health=json.loads(get(state,'/api/v1/health'))
    save('live-HTTP-snapshot.json',{'records':records,'history':histories,'health':health})
    require('live_records_and_history_match_browser_final',records==snapshots['after-stale-approval']['records'] and histories==snapshots['after-stale-approval']['history'])
    require('explicit_synthetic_no_OCR_boundary',health['capabilities']['ingest'] is False and health['checks']['vision']['configured'] is False and health['checks']['record_store']['ok'])
    db_path=Path(health['checks']['record_store']['path'])
    require('only_dedicated_preview_database',db_path==OLD/'preview-data/ledger.db')
    db=ro_rows(db_path,{'records':('SELECT * FROM records ORDER BY id',()),'history':('SELECT * FROM history ORDER BY seq',())})
    save('live-SQLite-rows.json',db)
    require('SQLite_has_exact_three_records',len(db['records'])==3 and {x['id'] for x in db['records']}=={x['id'] for x in records})
    by={r['id']:r for r in records}
    for row in db['records']:
        view=by[row['id']]
        for key in ['version','stage','approved_by','approved_at','reviewed_by','reviewed_at']:
            require('SQLite '+row['id']+' '+key,row[key]==view[key])
        require('SQLite '+row['id']+' fields',json.loads(row['fields'])==view['fields'])
    stored_histories={r['id']:[] for r in records}
    for h in db['history']:stored_histories[h['record_id']].append({k:json.loads(h[k]) if k=='detail' else h[k] for k in ['at','actor','action','detail']})
    require('SQLite_full_history_equals_HTTP',stored_histories==histories)
    platform=ro_rows(ROOT/'data/product-workbench/platform.db',{
        'candidate':('SELECT * FROM code_candidates WHERE id=?',(4,)),
        'decisions':('SELECT * FROM candidate_decisions WHERE candidate_id=?',(4,)),
        'assessments':('SELECT * FROM candidate_assessments WHERE candidate_id=? ORDER BY id',(4,))})
    save('platform-candidate-readonly-rows.json',platform)
    require('no_operator_decision_in_database',platform['decisions']==[])
    require('candidate_database_binding',platform['candidate'][0]['commit_sha']==SHA and platform['candidate'][0]['requirement_hash']==candidate_live['requirement_hash'])
    marker=read(OLD/'preview-data/webuddy-preview.json');images=[]
    for item in marker['records']:
        path=OLD/'preview-data'/item['original_key'];raw=path.read_bytes()
        images.append({'id':item['id'],'path':str(path),'bytes':len(raw),'sha256':sha(raw),'matches':len(raw)==item['bytes'] and sha(raw)==item['original_sha256']})
    save('synthetic-originals-readonly.json',images);require('synthetic_originals_unchanged',all(x['matches'] for x in images))
    timeline=read(HERE/'browser-timeline.json')
    save('browser-timeline-reviewed.json',timeline)
    require('browser_explicit_reconciliation_visible','已核对版本 1' in timeline[0]['dom'])
    require('browser_successful_save_visible','- status: 已保存。' in timeline[1]['dom'])
    require('browser_separate_approval_visible','- status: 已审核。' in timeline[2]['dom'])
    require('browser_stale_page_shows_conflict_not_approval','记录版本已变化' in timeline[4]['dom'] and '最新版本 3 · 已审核' in timeline[4]['dom'] and '- status: 已审核。' not in timeline[4]['dom'])
    require('browser_refresh_retains_approved_row','已审核 1' in timeline[6]['dom'] and '双人协作核对后的原料' in timeline[6]['dom'] and saved['fields']['备注'] in timeline[6]['dom'])
    require('read_did_not_change_preview_identity',read(ROOT/'data/product-workbench/previews/state.json')['WBILL-1']==state)
except Exception:
    save('failure.json',{'traceback':traceback.format_exc()});print(traceback.format_exc());raise
finally:
    save('http-transcript.json',transcript)
    save('inputs-manifest.json',inputs)
    save('checks.json',{'passed':sum(c['passed'] for c in checks),'total':len(checks),'checks':checks})
    print(json.dumps({'passed':sum(c['passed'] for c in checks),'total':len(checks),'checks':checks},ensure_ascii=False,indent=2))
