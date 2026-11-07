"""Inbound requirement receipts. External status never drives acceptance or execution."""
import hashlib
import json
from .errors import ApiError
from .store import now


def initialize(store):
    with store.lock,store.db:
        store.db.executescript('''
CREATE TABLE IF NOT EXISTS external_requirement_bindings(
 project_id INTEGER NOT NULL,source TEXT NOT NULL,external_id TEXT NOT NULL,
 revision TEXT NOT NULL,ticket_id INTEGER NOT NULL,payload_hash TEXT NOT NULL,
 PRIMARY KEY(project_id,source,external_id));
CREATE TABLE IF NOT EXISTS external_requirement_receipts(
 project_id INTEGER NOT NULL,source TEXT NOT NULL,actor TEXT NOT NULL,request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL,result TEXT NOT NULL,
 PRIMARY KEY(project_id,source,actor,request_id));
''')


def sync(P,project,actor,body):
    required={'source','external_id','revision','previous_revision','source_url','title','body','request_id'}
    if not isinstance(body,dict) or set(body)!=required or any(not isinstance(body[k],str) for k in required):
        raise ApiError(400,'请提供完整的外部来源、编号、修订、上一修订、链接、标题、正文和请求号')
    if any(not body[k].strip() for k in ('source','external_id','revision','title','request_id')):
        raise ApiError(400,'来源、编号、修订、标题和请求号不能为空')
    from ..integrations import tools
    if body['source'] not in tools(P.root(project)):
        raise ApiError(409,'请先登记项目的外部系统配置；不会连接未登记来源')
    encoded=json.dumps(body,ensure_ascii=False,sort_keys=True)
    fingerprint=hashlib.sha256(encoded.encode()).hexdigest()
    st=P.store
    with st.lock,st.db:
        st.db.execute('BEGIN IMMEDIATE')
        key=(project['id'],body['source'],actor,body['request_id'])
        old=st.one('SELECT * FROM external_requirement_receipts WHERE project_id=? AND source=? AND actor=? AND request_id=?',key)
        if old:
            if old['fingerprint']!=fingerprint: raise ApiError(409,'请求号已用于其他内容')
            return json.loads(old['result'])
        binding_key=(project['id'],body['source'],body['external_id'])
        binding=st.one('SELECT * FROM external_requirement_bindings WHERE project_id=? AND source=? AND external_id=?',binding_key)
        if (binding['revision'] if binding else '')!=body['previous_revision']:
            raise ApiError(409,'外部修订冲突；先读取上次回执，不覆盖或重复建单')
        if binding and binding['revision']==body['revision']:
            raise ApiError(409,'修订编号未变化；原意重试请复用请求号')
        if binding:
            t=st.ticket(binding['ticket_id'])
            if not t or t['project_id']!=project['id']: raise ApiError(409,'外部关联归属不一致')
            state='needs_review'
        else:
            t=st._create_ticket_in_tx(project['id'],body['title'],actor,body=body['body'],
                links={'hold':actor,'external_requirement':{'source':body['source'],'id':body['external_id']}},
                external={'system':body['source'],'key':body['external_id'],'url':body['source_url'],'revision':body['revision']})
            state='draft'
        st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'external_requirement_revision',?,?)",
            (t['id'],now(),actor,'外部需求已记录；不自动执行或改变验收状态',encoded))
        st.db.execute('INSERT INTO external_requirement_bindings VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,source,external_id) DO UPDATE SET revision=excluded.revision,payload_hash=excluded.payload_hash',
            (*binding_key,body['revision'],t['id'],fingerprint))
        result={'ticket':t['key'],'source':body['source'],'external_id':body['external_id'],'revision':body['revision'],
            'state':state,'request_id':body['request_id'],'execution':False,'outbound_callback':False,
            'link':'#/t/'+t['key'],'next_step':'由项目负责人核对来源修订；后续修订原文在任务记录中，不自动覆盖已确认需求。'}
        st.db.execute('INSERT INTO external_requirement_receipts VALUES(?,?,?,?,?,?)',(*key,fingerprint,json.dumps(result,ensure_ascii=False)))
        return result
