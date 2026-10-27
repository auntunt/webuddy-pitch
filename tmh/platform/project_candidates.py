"""Register a personally produced fixed candidate without granting host execution."""
from __future__ import annotations

import json
from pathlib import Path

from .. import evidence
from ..agent_contract import validate
from . import candidates, project_artifact, signoff, team
from .agent_api import _requirement
from .project_library import run_current
from .store import now


def criteria(P,ticket):
    """Use full already-confirmed requirements; never invent missing criteria."""
    try:
        records=signoff.records(P.data_dir,ticket['key'])
        if not evidence.check(records)[0]:
            return None
        record=evidence.latest(records,'intake')
    except (OSError,ValueError):
        return None
    if not record or not signoff.human(record.get('by')) or not isinstance(record.get('data'),dict):
        return None
    raw=record['data'].get('ac')
    if not isinstance(raw,list) or not raw or len(raw)>100:
        return None
    values=[]
    for item in raw:
        if not isinstance(item,dict) or item.get('open'):
            return None
        values.append({key:item.get(key) for key in ('id','text','check')})
    if len({str(item['id']) for item in values})!=len(values):
        return None
    return values


def register(P, rid, authority, job, binding, proposal, summary, current_source):
    st=P.store;run=st.run(rid);ticket=st.ticket(run['ticket_id']);project=st.project(run['project_id'])
    values=criteria(P,ticket)
    if not values:
        return None
    artifact=proposal['candidate'];base=artifact['base_commit'];commit=artifact['commit']
    try:
        validated=validate('candidate_submit',{'ticket':ticket['key'],'base_commit':base,'commit':commit,
            'requirement_hash':binding['requirement_hash'],'criteria':values,'summary':summary,
            'request_id':'member-run-'+str(rid)})
    except ValueError:
        return None
    candidates.schema(st)
    identity={'ticket':ticket['id'],'base':base,'commit':commit,'requirement':binding['requirement_hash'],
              'configuration':binding['configuration_hash'],'criteria':validated['criteria']}
    fingerprint=candidates._hash(dict(identity,project_root=project['root']))
    folder=Path(artifact['artifact_dir'])
    journal=folder/'install.json'
    intended={'schema':1,'run':rid,'fingerprint':fingerprint,'base_commit':base,'commit':commit}
    def write_journal(state):
        temp=folder/'install.json.tmp'
        temp.write_text(json.dumps(dict(intended,state=state),ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(journal)
    with authority.platform.tenant_context.registry.authorization_guard(), candidates.guard(P,ticket['id']):
        if not authority.current(job) or current_source(base) is not True or not authority.current(job):
            raise ValueError('登记候选前授权、需求或来源已变化')
        existing=st.one('SELECT id,run_id FROM code_candidates WHERE fingerprint=?',(fingerprint,))
        if existing:
            if existing['run_id']==rid:return existing['id']
            return None  # Do not reattribute someone else's existing candidate.
        if journal.exists():
            saved=json.loads(journal.read_text(encoding='utf-8'))
            if any(saved.get(k)!=v for k,v in intended.items()):
                raise ValueError('候选登记回执不一致，请先核对')
        else:
            write_journal('prepared')
        installed=project_artifact.install(authority.image,Path(project['root']),folder,artifact,fingerprint,
                                            cancel=lambda:not authority.current(job))
        if not authority.current(job) or current_source(base) is not True or not authority.current(job):
            raise ValueError('候选引用已准备但授权或来源发生变化，请先核对原回执')
        patch=(folder/'change.patch').read_bytes().decode('utf-8','strict')
        with st.lock:
            try:
                st.db.execute('BEGIN IMMEDIATE')
                current=st.ticket(ticket['id']);current_project=st.project(project['id']);active=st.run(rid)
                links=(current or {}).get('links') or {}
                assignment={k:v for k,v in team.assignment(P,current).items() if k in ('assignee','reviewer','revision')} if current else None
                if (not current or current_project['root']!=project['root'] or current['status']=='closed' or
                        links.get('delivery') or links.get('later') or not links.get('hold') or
                        assignment!=binding['assignment'] or _requirement(current,st)!=binding['requirement_hash'] or
                        candidates.configuration(P,current_project)!=binding['configuration_hash'] or
                        not active or active['status']!='running' or active['author']!=authority.principal or
                        active['project_id']!=project['id'] or active['ticket_id']!=ticket['id'] or
                        not run_current(st,current_project,rid)):
                    raise ValueError('候选登记期间工单、责任或来源已变化')
                if st.one("SELECT id FROM runs WHERE ticket_id=? AND status IN ('queued','running') AND id<>?",(ticket['id'],rid)):
                    raise ValueError('工单已有其他运行，不能登记此候选')
                stamp=now()
                cid=st.db.execute('''INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,
                    requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (ticket['id'],rid,authority.principal,base,commit,
                    binding['requirement_hash'],binding['configuration_hash'],candidates._json(validated['criteria']),
                    summary,fingerprint,installed['ref'],str(folder),stamp)).lastrowid
                st.db.execute("UPDATE runs SET status='done',ended=?,exit_code=0,result=?,diff=? WHERE id=?",
                              (stamp,summary,patch,rid))
                st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'candidate',?,?)",
                              (ticket['id'],stamp,authority.principal,'登记个人固定代码候选，等待独立验证',
                               candidates._json({'candidate':cid,'run':rid,'commit':commit})))
                st.db.execute('UPDATE tickets SET updated=? WHERE id=?',(stamp,ticket['id']))
                st.db.commit()
            except BaseException:
                st.db.rollback()
                raise
        try:write_journal('registered')
        except OSError:pass  # The committed candidate remains authoritative and replayable.
        return cid
