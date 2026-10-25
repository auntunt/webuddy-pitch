"""Verify native evidence at the existing human decision gate; never execute it.

The private producer publishes a distinct native_evaluate job. Public job views
contain hashes/counts only; full captures and oracles stay in the owner-only seal.
No ordinary job or caller assertion can acquire native provenance here.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from . import learning, learn, lesson_context, supervised_process as SP
from .errors import ApiError

KIND = 'native_evaluate'
SCHEMA = 'native-learning-job-v1'
EVENT = 'native_learning_job'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def require(value):
    if not value:
        raise ApiError(409, '原生评测来源、原件或确切版本已失效')


def strict(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result); result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: require(False))


def private_file(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and not before.st_mode & 0o077 and before.st_nlink == 1)
        raw = stream.read(); after = os.fstat(stream.fileno())
        require(identity(before) == identity(after))
    return raw


def identity(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def folder(P, job_id):
    require(isinstance(job_id, str) and re.fullmatch(r'NJ[0-9a-f]{40}', job_id))
    path = Path(P.data_dir).resolve()/'native-learning'/job_id
    for parent in (path.parent, path):
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077)
    require(path.resolve() == path)
    return path


def event(P, root, kind):
    rows = P.store.q('SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind=?', (root, kind))
    require(len(rows) == 1)
    value = strict(rows[0]['payload']); require(digest(value) == rows[0]['payload_hash'])
    return value


@contextmanager
def snapshot(P):
    # Preserve SQLite -> lesson acquisition even for callers without a transaction.
    with P.store.lock:
        own = not P.store.db.in_transaction
        if own: P.store.db.execute('SAVEPOINT native_learning_read')
        try:
            with learn.ledger_lock(P.data_dir, create=False): yield
        finally:
            if own: P.store.db.execute('RELEASE native_learning_read')


def verify(P, p, job, *, reason=None, adopted=False, followup_request=''):
    """Read-only original proof. Only its one registered D may extend frontier."""
    from . import learning_decisions as D, learning_eval as E
    with snapshot(P):
        require(job.get('kind') == KIND and job.get('status') == 'passed')
        raw_job = P.store.one('SELECT * FROM learning_jobs WHERE id=? AND project_id=?', (job['id'], p['id']))
        require(raw_job and raw_job['kind'] == KIND and raw_job['status'] == 'passed')
        require(all(job.get(k) == raw_job[k] for k in E.CAPTURE_IDENTITY))
        options = strict(raw_job['options']); reference = options['native_evaluation']
        require(job['options'] == options and reference['schema'] == SCHEMA)
        root = reference['root_pool']; publication = event(P, root, EVENT)
        require(publication['job_id'] == job['id'] and publication['job_sha256'] == digest(raw_job))
        raw = private_file(folder(P, job['id'])/'evidence.json')
        require(hashlib.sha256(raw).hexdigest() == publication['evidence_sha256'])
        proof = strict(raw)
        require(proof['schema'] == SCHEMA and proof['root_pool'] == root)
        require(proof['verifier_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        schema={v['name']:v['sql'] for v in P.store.q("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'rsi_prepare_%'")}
        require(schema == proof['ledger_schema'])
        pool = P.store.one('SELECT * FROM rsi_prepare_pools WHERE pool=?', (root,)); require(pool and not pool['blocked'])
        c = strict(pool['contract']); require(digest(c) == pool['contract_hash'] == proof['contract_sha256'])
        original = event(P, root, 'create')
        require(original == dict(contract=c, generation=pool['generation'], created_us=pool['created_us']))
        require(c['schema'] == 'trial-finite-provider-v7' and c['limits']['max_total_tokens'] is None)
        require(root == digest([c['tenant_id'], c['project_id'], c['root_family']]) and c['project_id'] == p['id'])
        tenant = getattr(getattr(P, 'tenant_context', None), 'tenant_id', None)
        require(tenant == c['tenant_id'] and P.store.project(p['id']) == p)
        report = event(P, root, 'native_bc_report'); registration = event(P, root, 'native_bc_registration')
        require(digest(report) == reference['native_report_sha256'] == proof['native_report_sha256'])
        require(report['registration_sha256'] == digest(registration) and report['assertions']['passed'] is True)
        require(registration['model'] == c['model'] and registration['application_commit'] == c['application_commit'])
        require(registration['spec']['contract_sha256'] == digest(c))
        evaluation_intent = event(P, root, 'native_bc_evaluation_intent')
        require(evaluation_intent['fingerprint'] == report['fingerprint'] == digest([registration,report['frontier'],report['origins']]))
        require(report['contract_sha256'] == digest(c) and report['frontier'] == proof['frontier'] and proof['observations']['thresholds'] == registration['spec']['thresholds'])
        rows = P.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? ORDER BY request_id', (root,))
        reservations=P.store.q("SELECT request_id,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='reserve'",(root,))
        require(len(reservations)==len(rows) and {v['request_id'] for v in reservations}=={v['request_id'] for v in rows})
        for attempt in rows:
            anchors=[v for v in reservations if v['request_id']==attempt['request_id']]
            require(len(anchors)==1 and anchors[0]['payload_hash']==attempt['body_hash']==digest(strict(attempt['body'])))
            require(strict(anchors[0]['payload'])==strict(attempt['body']))
            if attempt['intent']:
                intents=P.store.q("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='intent'",(root,attempt['request_id']))
                require(len(intents)==1 and digest(strict(intents[0]['payload']))==intents[0]['payload_hash'])
                require(strict(intents[0]['payload'])=={'intent':attempt['intent'],'body_hash':attempt['body_hash']})
        isolations={}
        for row in P.store.q("SELECT kind,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind IN ('isolation_intent','isolation_finished') ORDER BY id",(root,)):
            value=strict(row['payload']);require(digest(value)==row['payload_hash'])
            execution=value['execution_id']
            if row['kind']=='isolation_intent':
                require(execution not in isolations);isolations[execution]=None
            else:
                require(execution in isolations and isolations[execution] is None);isolations[execution]=value['status']
        require(all(value=='evaluated' for value in isolations.values()))

        original_rows = {r['request_id']:r['stored_attempt_sha256'] for r in proof['frontier']}
        extras = [r for r in rows if r['request_id'] not in original_rows]
        require(len(rows)-len(extras) == len(original_rows))
        require(type(c['limits']['calls']) is int and len(rows) <= c['limits']['calls'])
        for row in rows:
            if row['request_id'] in original_rows: require(digest(row) == original_rows[row['request_id']])
        if extras:
            require(followup_request and len(extras) == 1 and extras[0]['request_id'] == followup_request)
            follow = event(P, root, 'native_d_registration'); body = strict(extras[0]['body'])
            require(follow['job_id'] == job['id'] and follow['request_id'] == followup_request)
            require(follow['native_report_sha256'] == reference['native_report_sha256'] and body['phase'] == 'followup')
            require(body['contract_hash'] == digest(c) and extras[0]['state'] in {'reserved','intent','settled'})
        else:
            require(not followup_request or event(P, root, 'native_d_registration')['request_id'] == followup_request)
        for item in proof['artifacts']:
            path = Path(item['path']); require(path.is_absolute() and path.resolve() == path)
            raw_file = path.read_bytes(); require(len(raw_file) == item['bytes'] and hashlib.sha256(raw_file).hexdigest() == item['sha256'])
        credential = proof['credential_identity']; st = Path(credential['path']).lstat()
        require(stat.S_ISREG(st.st_mode) and not st.st_mode & 0o077 and st.st_uid == os.getuid() and identity(st) == credential['identity'])
        require(len(proof['supervised']) == len(proof['frontier'])+1)
        require(proof['supervised'][-1]['owner'] == evaluation_intent['owner'] and proof['supervised'][-1]['receipt_sha256'] == report['evaluator_receipt_sha256'])
        provider_text = {}
        original_by_id = {r['request_id']:r for r in rows if r['request_id'] in original_rows}
        for original, supervised in zip(proof['frontier'],proof['supervised'][:-1]):
            row = original_by_id[original['request_id']]; body = strict(row['body'])
            require(supervised['owner']['token'] == row['intent'] and supervised['owner']['run_id'] == digest([root,row['request_id']]))
            source_folder = Path(supervised['folder']).parent
            request_raw = (source_folder/'request.bin').read_bytes(); profile_raw = (source_folder/'profile.json').read_bytes()
            require(hashlib.sha256(profile_raw).hexdigest() == c['provider_binding']['profile_sha256'])
            require(body['material_sha256'] == digest([hashlib.sha256(profile_raw).hexdigest(),hashlib.sha256(request_raw).hexdigest()]))
            metadata, response_raw = (Path(supervised['folder'])/'output.bin').read_bytes().split(b'\n',1)
            metadata = strict(metadata); response = strict(response_raw); profile = strict(profile_raw)
            require(metadata['status'] == 200 and metadata['protocol'] == profile['protocol'])
            require(metadata['request_sha256'] == hashlib.sha256(request_raw).hexdigest() and metadata['transport_sha256'] == c['provider_binding']['code_sha256']['transport'])
            require(response['model'] == c['model']['response_model'] and hashlib.sha256(response_raw).hexdigest() == original['response_sha256'])
            if profile['protocol'] == 'messages':
                require(response['type']=='message' and response['role']=='assistant' and response['stop_reason']=='end_turn' and len(response['content'])==1 and response['content'][0]['type']=='text')
                text = response['content'][0]['text']
            else:
                require(profile['protocol']=='responses' and response['object']=='response' and response['status']=='completed')
                messages = [v for v in response['output'] if v['type']=='message']
                require(len(messages)==1 and messages[0]['role']=='assistant' and messages[0]['status']=='completed' and len(messages[0]['content'])==1 and messages[0]['content'][0]['type']=='output_text')
                text = messages[0]['content'][0]['text']
            require(isinstance(text,str)); provider_text[row['request_id']] = (text,strict(request_raw),profile['protocol'])
        captures_by_hash = {hashlib.sha256(encoded(v).encode()).hexdigest():v for v in proof['captures']}
        for spec, observed in zip(registration['spec']['cases'], proof['observations']['cases']):
            require(all(observed[k]==spec[k] for k in ('input_sha256','validator','expected','forbidden')))
            common = captures_by_hash[spec['input_sha256']]
            for side in ('baseline','candidate'):
                origins = [o for o in report['origins'] if o['input_sha256']==spec['input_sha256'] and o['arm']==side]
                require(len(origins)==1)
                text, request, protocol = provider_text[origins[0]['request_id']]
                require(text == observed[side] and request['tools']==[])
                policy = request['system' if protocol=='messages' else 'instructions']
                require(hashlib.sha256(policy.encode()).hexdigest() == (c['baseline_sha256'] if side=='baseline' else report['candidate_sha256']))
                require(request['messages' if protocol=='messages' else 'input'] == [{'role':'user','content':common['prompt']}])
        for item in proof['supervised']:
            receipt = SP.read_receipt(Path(item['folder']), item['owner'])
            require(receipt and digest(receipt) == item['receipt_sha256'] and receipt['returncode'] == 0
                    and receipt['cleanup']['complete'] and receipt['cleanup']['reaped'] and not receipt['cleanup']['remaining_group'])
        for value in proof['captures']:
            source = value['source']; require(source['project'] == p and source['binding'] == learning.binding(P, p))
            ticket = source['ticket']; require(ticket is None or P.store.ticket(ticket['id']) == ticket)
            for meta in source['context']:
                if meta.get('mode') == 'learning_lessons': require(lesson_context.current(P.store, p, meta['block']))
        r = learning.revision(P, p, job['current_revision_id'])
        require(r == proof['revision'] and r['kind'] == 'lesson')
        require(hashlib.sha256(strict(r['content'])['fix'].encode()).hexdigest() == report['candidate_sha256'])
        require(D.adopted_current(P, p, r) if adopted else learning.revision_current(P, p, r))
        observations = proof['observations']; checked = []
        for case in observations['cases']:
            checked.append(dict(input_sha256=case['input_sha256'], baseline=E.check(case,case['baseline']), candidate=E.check(case,case['candidate'])))
        require(checked == report['assertions']['cases'] and all(x['candidate'] for x in checked))
        if reason is not None:
            ref = strict(reason)
            require(set(ref) == {'schema','root_pool','native_report_sha256','reason'} and ref['schema'] == 'native-bc-decision-reference-v1')
            require(ref['root_pool'] == root and ref['native_report_sha256'] == reference['native_report_sha256'] and isinstance(ref['reason'],str) and bool(ref['reason'].strip()))
        return proof
