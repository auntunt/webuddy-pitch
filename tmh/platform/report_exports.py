"""Explicit immutable exports. Reads never generate, persist or refresh evidence."""
import base64
import hashlib
import json
import subprocess
from .errors import ApiError
from .store import now

CHUNK = 48 * 1024


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def create_candidate(P, project, row, actor, args):
    """Frozen export of one candidate verification; same tables, segmenting and
    sha receipts as other frozen exports. plan_id is 'candidate:<id>' so read() works
    unchanged; current validity stays a live-view concern, the export is frozen."""
    from .candidates import view
    st = P.store
    fingerprint = hashlib.sha256(encoded(args)).hexdigest()
    with st.lock, st.db:
        st.db.execute('CREATE TABLE IF NOT EXISTS report_exports(id TEXT PRIMARY KEY, project_id INTEGER, plan_id TEXT, actor TEXT, request_id TEXT, fingerprint TEXT, manifest TEXT, UNIQUE(actor,request_id))')
        st.db.execute('CREATE TABLE IF NOT EXISTS report_export_files(export_id TEXT, name TEXT, body BLOB, PRIMARY KEY(export_id,name))')
        st.db.execute('BEGIN IMMEDIATE')
        old = st.db.execute('SELECT * FROM report_exports WHERE actor=? AND request_id=?', (actor, args['request_id'])).fetchone()
        if old:
            if old['fingerprint'] != fingerprint:
                raise ApiError(409, '请求编号已用于其他导出')
            return json.loads(old['manifest'])
        v = view(P, row['id'])
        files = {'candidate.json': encoded(v), 'report.md': candidate_markdown(P, project, row, v).encode()}
        entries = [{'name': n, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(),
                    'chunks': (len(b) + CHUNK - 1) // CHUNK,
                    'chunk_sha256': [hashlib.sha256(b[i:i + CHUNK]).hexdigest() for i in range(0, len(b), CHUNK)]}
                   for n, b in sorted(files.items())]
        export_id = hashlib.sha256(encoded(entries) + fingerprint.encode() + actor.encode()).hexdigest()
        manifest = {'export_id': export_id, 'project': project['key'],
                    'plan_id': 'candidate:%d' % row['id'], 'revision': 1,
                    'candidate_id': row['id'], 'commit': row['commit_sha'],
                    'verification_hash': v.get('verification_hash', ''),
                    'generated_at': now(), 'chunk_bytes': CHUNK, 'files': entries,
                    'current_validity': 'not_checked',
                    'notice': '冻结的保存证据；不触发验证、确认、合并或发布。当前有效性请读取候选当前视图。'}
        st.db.execute('INSERT INTO report_exports VALUES(?,?,?,?,?,?,?)',
                      (export_id, project['id'], 'candidate:%d' % row['id'], actor,
                       args['request_id'], fingerprint, encoded(manifest).decode()))
        st.db.executemany('INSERT INTO report_export_files VALUES(?,?,?)',
                          [(export_id, n, b) for n, b in files.items()])
    return manifest


def candidate_markdown(P, project, row, v):
    """Frozen verification report for one external candidate."""
    lines = ['# 候选验证报告 %s' % row['commit_sha'][:12], '',
             '项目：%s · 候选 #%d · 基线 `%s`' % (project['key'], row['id'], row['base_commit'][:12]),
             '需求摘要：%s' % (v.get('summary') or ''), '']
    try:
        stat = subprocess.run(['git', '-C', str(project['root']), 'diff', '--stat',
                               '--no-ext-diff', row['base_commit'], row['commit_sha']],
                              capture_output=True, timeout=30)
        if stat.returncode == 0 and stat.stdout:
            lines += ['## 改动', '', '```', stat.stdout.decode('utf-8', 'replace').strip(), '```', '']
    except (OSError, subprocess.SubprocessError):
        pass
    lines += ['## 检查', '']
    for cmd in (v.get('verification') or {}).get('commands') or []:
        lines.append('- `%s` → 退出码 %s' % (cmd.get('kind'), cmd.get('exit_code')))
    if not (v.get('verification') or {}).get('commands'):
        lines.append('- 尚未运行隔离验证')
    lines += ['', '## 逐项验收', '']
    if v.get('criteria'):
        results = {r['id']: r for r in (v.get('assessment') or {}).get('results') or []}
        for c in v['criteria']:
            r = results.get(c['id'], {})
            lines.append('- %s：%s — 目标:%s 验证:%s 结论:%s %s' % (
                c['id'], c['text'], c.get('check', ''), r.get('status', 'not_run'),
                r.get('conclusion', ''), r.get('evidence', '')))
    else:
        lines.append('业务符合性：未知（未提供验收标准）')
    gate = v.get('gate_findings') or {}
    if gate.get('blocking') or gate.get('weakening') or gate.get('gate_files'):
        lines += ['', '## 门禁相关变更', '']
        for x in gate.get('weakening', []):
            lines.append('- %s' % x)
        for f in gate.get('tests_deleted', []):
            lines.append('- 删除测试文件 %s' % f)
        for f in gate.get('gate_files', []):
            lines.append('- 构建/CI 配置变更 %s' % f)
        ack = v.get('gate_ack')
        lines.append('操作者确认：%s' % ('%s（%s）' % (ack['author'], ack['reason']) if ack else '无'))
    if v.get('control_points'):
        lines += ['', '## 控制点', '']
        for x in v['control_points']:
            lines.append('- %s：%s — %s' % (x['name'], x['state'], x['why']))
    lines += ['', '## 未验证项', '']
    for x in v.get('missing') or ['无']:
        lines.append('- %s' % x)
    lines += ['', '状态：%s · 证据包 `%s`' % (v.get('state'), (v.get('evidence_hash') or '')[:16])]
    return '\n'.join(lines) + '\n'


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
