"""Explicit immutable exports. Reads never generate, persist or refresh evidence."""
import base64
import hashlib
import json
from .errors import ApiError
from .store import now

CHUNK = 48 * 1024


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def create(P, project, plan, actor, args):
    from .reform_api import report
    from . import reform
    from .scenario_report import markdown
    st=P.store
    fingerprint=hashlib.sha256(encoded(args)).hexdigest()
    with st.lock, st.db:
        st.db.execute('CREATE TABLE IF NOT EXISTS report_exports(id TEXT PRIMARY KEY, project_id INTEGER, plan_id TEXT, actor TEXT, request_id TEXT, fingerprint TEXT, manifest TEXT, UNIQUE(actor,request_id))')
        st.db.execute('CREATE TABLE IF NOT EXISTS report_export_files(export_id TEXT, name TEXT, body BLOB, PRIMARY KEY(export_id,name))')
        st.db.execute('BEGIN IMMEDIATE')
        plan=reform.plan(P.data_dir,project['key'],plan['id'],store=st)
        old=st.db.execute('SELECT * FROM report_exports WHERE actor=? AND request_id=?',(actor,args['request_id'])).fetchone()
        if old:
            if old['fingerprint']!=fingerprint:raise ApiError(409,'请求编号已用于其他导出')
            return json.loads(old['manifest'])
        if plan['revision']!=args['expected_revision']:raise ApiError(409,'计划修订已变化，请重新核对再生成报告')
        value=report(P,project,plan,render=False)
        children=value.pop('child_evidence')
        files={}
        summaries=[]
        for child in children:
            name=child['ticket']['key']+'.json'
            files[name]=encoded(child)
            summaries.append({'ticket':child['ticket']['key'],'file':name,'conclusions':child['conclusions']})
        value['child_evidence_files']=summaries
        files['plan.json']=encoded(value)
        # The reading edition refers to originals instead of embedding them repeatedly.
        files['report.md']=(markdown(value,include_raw=False)+'\n'+ '\n'.join(markdown(c,include_raw=False) for c in children)).encode()
        entries=[{'name':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'chunks':(len(body)+CHUNK-1)//CHUNK,'chunk_sha256':[hashlib.sha256(body[i:i+CHUNK]).hexdigest() for i in range(0,len(body),CHUNK)]} for name,body in sorted(files.items())]
        export_id=hashlib.sha256(encoded(entries)+fingerprint.encode()+actor.encode()).hexdigest()
        manifest={'export_id':export_id,'project':project['key'],'plan_id':plan['id'],'revision':plan['revision'],
                  'generated_at':now(),'chunk_bytes':CHUNK,'files':entries,'current_validity':'not_checked',
                  'notice':'冻结的保存证据；不触发验证、确认、合并或发布。保留至项目数据归档；不随读取自动清理。'}
        st.db.execute('INSERT INTO report_exports VALUES(?,?,?,?,?,?,?)',(export_id,project['id'],plan['id'],actor,args['request_id'],fingerprint,encoded(manifest).decode()))
        st.db.executemany('INSERT INTO report_export_files VALUES(?,?,?)',[(export_id,n,b) for n,b in files.items()])
    return manifest


def read(P, project, plan, args):
    st=P.store
    if not st.one("SELECT name FROM sqlite_master WHERE type='table' AND name='report_exports'"):
        raise ApiError(404,'尚未生成此报告')
    row=st.one('SELECT * FROM report_exports WHERE id=? AND project_id=? AND plan_id=?',(args['export_id'],project['id'],plan['id']))
    if not row:raise ApiError(404,'没有这个项目的报告')
    manifest=json.loads(row['manifest'])
    if not args.get('file'):return manifest
    entry=next((f for f in manifest['files'] if f['name']==args['file']),None)
    if entry is None:raise ApiError(404,'没有这个附件')
    offset=args.get('offset',0)
    if not 0<=offset<max(1,entry['bytes']) or offset%CHUNK:raise ApiError(400,'分段偏移不正确')
    # SQLite slices the immutable BLOB; no entire attachment crosses HTTP.
    row=st.one('SELECT substr(body,?,?) AS segment FROM report_export_files WHERE export_id=? AND name=?',(offset+1,CHUNK,args['export_id'],args['file']))
    if row is None:raise ApiError(409,'导出附件缺失')
    body=bytes(row['segment'])
    if len(body)!=min(CHUNK,entry['bytes']-offset):raise ApiError(409,'导出附件长度异常')
    if body and hashlib.sha256(body).hexdigest()!=entry['chunk_sha256'][offset//CHUNK]:raise ApiError(409,'导出附件校验失败；原清单保持，请核对存储')
    return {'export_id':args['export_id'],'file':args['file'],'offset':offset,'bytes':len(body),
            'sha256':hashlib.sha256(body).hexdigest(),'file_sha256':entry['sha256'],'total_bytes':entry['bytes'],
            'next_offset':offset+len(body) if offset+len(body)<entry['bytes'] else None,'data_base64':base64.b64encode(body).decode()}
