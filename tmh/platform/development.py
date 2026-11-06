"""Versioned developer conversations; agent answers never grant human approval."""
import hashlib
import json
from .errors import ApiError
from .store import now

DDL = '''
CREATE TABLE IF NOT EXISTS development_sessions (
 ticket_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, source_hash TEXT NOT NULL,
 payload TEXT NOT NULL, confirmed_by TEXT NOT NULL DEFAULT '', confirmed_digest TEXT NOT NULL DEFAULT '',
 updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS development_events (
 id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL,
 created TEXT NOT NULL, UNIQUE(actor,request_id));
'''


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def schema(store):
    with store.lock:
        store.db.executescript(DDL)
        store.db.commit()


def row(store, tid):
    if not store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='development_sessions'"):
        return None
    return store.one('SELECT * FROM development_sessions WHERE ticket_id=?', (tid,))


def identity(store, tid):
    current = row(store, tid)
    return {'revision': current['revision'], 'digest': digest(json.loads(current['payload'])),
            'confirmed_digest': current['confirmed_digest']} if current else None


def source(store, ticket):
    from .agent_api import _requirement
    return _requirement(ticket, store, include_development=False)


def read(store, ticket):
    current = row(store, ticket['id'])
    if not current:
        return {'ticket': ticket['key'], 'state': 'not_selected', 'revision': 0,
                'next_action': 'development_start'}
    payload = json.loads(current['payload'])
    binding = digest({'source': current['source_hash'], 'revision': current['revision'], 'payload': payload})
    stale = current['source_hash'] != source(store, ticket)
    pending = [q for q in payload['questions'] if q['required'] and not payload['answers'].get(q['id'], {}).get('resolved')]
    confirmed = not stale and current['confirmed_digest'] == binding
    state = 'stale' if stale else 'confirmed' if confirmed else 'clarifying' if pending or not payload['summary'] else 'awaiting_confirmation'
    return {'ticket': ticket['key'], 'revision': current['revision'], 'state': state, 'digest': binding,
            'source_hash': current['source_hash'], 'confirmed_by': current['confirmed_by'] if confirmed else '',
            'payload': payload, 'pending_questions': pending,
            'next_questions': pending[:3], 'next_action': {'stale':'development_propose', 'confirmed':'develop',
            'clarifying':'ask_developer' if payload['summary'] else 'development_propose', 'awaiting_confirmation':'human_terminal_confirm'}[state],
            'instructions': '在Agent终端分批向开发人员提问，展示选项并允许自由回答。不猜测回答；不清楚记resolved=false。全部问题处理后展示完整需求、设计和测试方案，由本人在独立人工终端确认。确认不是业务验收。'}


def require_confirmed(store, ticket):
    if not row(store, ticket['id']):
        return None
    state = read(store, ticket)
    if state['state'] != 'confirmed':
        raise ValueError('该任务已选择终端协作开发，请先由本人确认当前需求、设计和测试方案')
    return state


def act(P, actor, action, body, *, human=False):
    from .agent_api import _ticket
    from ..agent_contract import validate, _validate_value, KEY, REQUEST, DIGEST
    if action == 'confirm':
        if not human:
            raise ApiError(403, 'Agent不能提交人工需求确认')
        if set(body) != {'ticket','revision','digest','request_id'}:
            raise ApiError(400, '确认需要任务、修订、摘要和请求编号')
        try:
            for field, rule in (('ticket',KEY),('digest',DIGEST),('request_id',REQUEST)):
                _validate_value(field,rule,body[field])
        except ValueError as exc:
            raise ApiError(400,str(exc)) from exc
        if type(body['revision']) is not int:
            raise ApiError(400, '修订编号不正确')
    else:
        try:
            body = validate('development_' + action, body)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
    st = P.store
    schema(st)
    fingerprint = digest({'action':action,'body':body})
    with P.runner.lock, st.lock:
        try:
            st.db.execute('BEGIN IMMEDIATE')
            ticket = _ticket(P, body['ticket'])
            if ticket['status'] == 'closed':
                raise ApiError(409, '任务已关闭，请选择进行中的任务')
            receipt = st.one('SELECT * FROM development_events WHERE actor=? AND request_id=?', (actor,body['request_id']))
            if receipt:
                if receipt['fingerprint'] != fingerprint:
                    raise ApiError(409, '请求编号已用于其他内容')
                st.db.commit()
                return dict(read(st,ticket), replayed=True, recorded_revision=receipt['revision'])
            current = row(st,ticket['id'])
            if human and action == 'confirm':
                from .team import assignment
                assignee = assignment(P,ticket)['assignee']
                if assignee and assignee != actor:
                    raise ApiError(403, '请由当前任务负责人确认开发方案')
            if action == 'start':
                if current:
                    st.db.commit()
                    return read(st,ticket)
                if st.one("SELECT id FROM runs WHERE ticket_id=? AND status IN ('running','queued')",(ticket['id'],)):
                    raise ApiError(409, '任务正在执行，请先结束或停止原运行再接管')
                payload = {'summary':'','design':'','test_plan':'','criteria':[], 'questions':[], 'answers':{}}
                revision = 1
                links = dict(ticket.get('links') or {}, hold=True, handwork=True)
                st.db.execute('UPDATE tickets SET links=?,updated=? WHERE id=?',(encode(links),now(),ticket['id']))
            else:
                if not current or current['revision'] != body['revision']:
                    raise ApiError(409, '开发会话已变化，请重新读取；不会覆盖其他人的回答')
                payload = json.loads(current['payload'])
                revision = current['revision']
                if action == 'confirm':
                    state = read(st,ticket)
                    if state['state'] not in ('awaiting_confirmation','confirmed') or state['digest'] != body['digest']:
                        raise ApiError(409, '有未回答问题、来源变化或确认稿已更新，请重新核对')
                    if not payload['design'].strip() or not payload['test_plan'].strip() or not payload['criteria']:
                        raise ApiError(409, '需要完整设计、测试方案和可检查的验收标准')
                    st.db.execute('UPDATE development_sessions SET confirmed_by=?,confirmed_digest=?,updated=? WHERE ticket_id=?',
                                  (actor,state['digest'],now(),ticket['id']))
                elif action == 'propose':
                    ids = [q['id'] for q in body['questions']]
                    if len(set(ids)) != len(ids) or len({c['id'] for c in body['criteria']}) != len(body['criteria']):
                        raise ApiError(400, '问题和验收标准的编号必须唯一')
                    from .signoff import client_ac
                    client_criteria = client_ac(P.data_dir,ticket['key'])
                    proposed = {c['id']:c for c in body['criteria']}
                    if any(c.get('open') or any(proposed.get(c['id'],{}).get(k) != c.get(k) for k in ('text','check')) for c in client_criteria):
                        raise ApiError(409, '开发方案必须保留客户已确认的验收要求；业务规则变更请先更新客户确认')
                    old_questions = {q['id']:q for q in payload['questions']}
                    answers = {q['id']:payload['answers'][q['id']] for q in body['questions']
                               if current['source_hash'] == source(st,ticket) and old_questions.get(q['id']) == q and q['id'] in payload['answers']}
                    payload = {k:body[k] for k in ('summary','design','test_plan','criteria','questions')}
                    payload['answers'] = answers
                    revision += 1
                elif action == 'answer':
                    if current['source_hash'] != source(st,ticket):
                        raise ApiError(409, '任务来源已变化，请先更新分析和问题')
                    questions = {q['id']:q for q in payload['questions']}
                    if len({a['question_id'] for a in body['answers']}) != len(body['answers']):
                        raise ApiError(400, '同一问题不能在一批中重复回答')
                    for answer in body['answers']:
                        if answer['question_id'] not in questions:
                            raise ApiError(400, '回答不属于当前问题集')
                        payload['answers'][answer['question_id']] = dict(answer, actor=actor, via='human_terminal' if human else 'agent_relay')
                    revision += 1
            if action != 'confirm':
                st.db.execute('INSERT OR REPLACE INTO development_sessions VALUES(?,?,?,?,?,?,?)',
                              (ticket['id'],revision,source(st,ticket),encode(payload),'','',now()))
            st.db.execute('INSERT INTO development_events(ticket_id,actor,request_id,fingerprint,revision,action,payload,created) VALUES(?,?,?,?,?,?,?,?)',
                          (ticket['id'],actor,body['request_id'],fingerprint,revision,action,encode(body),now()))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
    return read(st,st.ticket(ticket['id']))
