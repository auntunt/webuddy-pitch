"""Human observations of one exact AI review, separate from business signoff."""
import hashlib
import json
from .errors import ApiError
from .store import now


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def snapshot(verification):
    if (verification or {}).get('diagnosis_invalidated') or (verification or {}).get('verification_current') is False:
        return None
    diagnosis = (verification or {}).get('diagnosis') or {}
    review = diagnosis.get('review')
    if not review:
        return None
    findings = []
    for kind in ('blocking', 'advisory'):
        for index, item in enumerate(diagnosis.get(kind) or []):
            findings.append({'id': kind + ':' + str(index), 'kind': kind, 'detail': item})
    return {'binding': digest(diagnosis), 'base': review['base'], 'diff_sha256': review['diff_sha256'],
            'created': review['created'], 'findings': findings}


def view(P, run, verification):
    current = snapshot(verification)
    rows = P.store.q('SELECT * FROM review_feedback WHERE run_id=? ORDER BY id DESC', (run['id'],))
    for row in rows:
        row['current'] = bool(current and row['binding'] == current['binding'])
    return {'snapshot': current, 'records': rows}


def save(P, run, actor, body):
    from .fixloop import verified
    from .signoff import human
    if not human(actor):
        raise ApiError(403, 'Review效果由人工记录，不能由执行器代填')
    if run['mode'] != 'fix' or run['status'] != 'done':
        raise ApiError(409, '完成的修改运行才能记录Review效果')
    if not isinstance(body, dict) or set(body) != {'request_id','binding','minutes','findings','missed','note'}:
        raise ApiError(400, '需要审查版本、实际分钟数、问题判断和记录说明')
    if not isinstance(body['request_id'], str) or not 1 <= len(body['request_id']) <= 100:
        raise ApiError(400, '记录请求标识无效')
    if type(body['minutes']) is not int or not 0 <= body['minutes'] <= 1440:
        raise ApiError(400, '实际复核时间须为0至1440的整数分钟')
    if not isinstance(body['note'], str) or not body['note'].strip() or len(body['note']) > 4000:
        raise ApiError(400, '请填写实际复核范围与说明；0分钟也须说明原因')
    if not isinstance(body['missed'], list) or any(not isinstance(x,str) or not x.strip() or len(x)>2000 for x in body['missed']):
        raise ApiError(400, '人工另行发现的问题须逐条填写')
    if not isinstance(body['findings'], list):
        raise ApiError(400, '问题判断格式无效')
    identity = digest(body)
    with P.store.lock:
        old = P.store.one('SELECT * FROM review_feedback WHERE run_id=? AND actor=? AND request_id=?', (run['id'],actor,body['request_id']))
        if old:
            if old['payload_digest'] != identity:
                raise ApiError(409, '同一请求不能更换记录内容')
            return old
        current = snapshot(verified(P.data_dir, run['id']))
        if not current or body['binding'] != current['binding']:
            raise ApiError(409, 'AI Review已变化，请重新打开后记录')
        expected = {f['id'] for f in current['findings']}
        seen = set()
        for finding in body['findings']:
            if (not isinstance(finding,dict) or set(finding)!={'id','verdict','reason'} or
                not isinstance(finding['id'],str) or
                finding['id'] not in expected or finding['id'] in seen or
                finding['verdict'] not in ('valid','false_positive','unassessed') or
                not isinstance(finding['reason'],str) or len(finding['reason'])>2000 or
                (finding['verdict']!='unassessed' and not finding['reason'].strip())):
                raise ApiError(400, '逐项判断须对应原问题，已判断项需要依据')
            seen.add(finding['id'])
        if seen != expected:
            raise ApiError(400, '每条AI问题都须保留判断，未判断请选待核实')
        data = dict(body, snapshot=current)
        rid = P.store.x('INSERT INTO review_feedback(run_id,project_id,actor,request_id,binding,payload_digest,created,data) VALUES(?,?,?,?,?,?,?,?)',
                        (run['id'],run['project_id'],actor,body['request_id'],current['binding'],identity,now(),json.dumps(data,ensure_ascii=False)))
        return P.store.one('SELECT * FROM review_feedback WHERE id=?',(rid,))


def summary(P, project_id):
    from .fixloop import verified
    rows=P.store.q('SELECT * FROM review_feedback WHERE project_id=? ORDER BY id DESC',(project_id,))
    selected=[];seen=set();bindings={}
    for row in rows:
        key=(row['run_id'],row['actor'])
        if key in seen:continue
        if row['run_id'] not in bindings:
            bindings[row['run_id']]=snapshot(verified(P.data_dir,row['run_id']))
        current=bindings[row['run_id']]
        if current and row['binding']==current['binding']:
            selected.append(row);seen.add(key)
    counts={'valid':0,'false_positive':0,'unassessed':0}
    for row in selected:
        for item in row['data']['findings']:counts[item['verdict']]+=1
    assessed=counts['valid']+counts['false_positive']
    return dict(counts,observations=len(selected),runs=len({r['run_id'] for r in selected}),
                minutes=sum(r['data']['minutes'] for r in selected) if selected else None,
                missed=sum(len(r['data']['missed']) for r in selected),
                valid_rate=round(counts['valid']/assessed*100,1) if assessed else None,
                saved_minutes=None, records=selected)
