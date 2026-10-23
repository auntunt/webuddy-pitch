"""Stored-only projections for personal tool connections.

These are historical records, never inputs to acceptance or recovery. In
particular, null current/ready/pass values mean not checked, not a failed check.
No function here starts processes, probes leases, resolves Git or visits URLs.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .errors import ApiError

NOTICE = '仅提供已保存的历史记录；当前提交、进程、健康、验证及人工决定有效性均未核对。历史 URL 仅为原文，不是可导航的有效预览。'


def rows(store, table, clause='', args=()):
    # Table/clause names are module constants, never client input.
    if not store.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)):
        return []
    return store.q('SELECT * FROM ' + table + (' ' + clause if clause else ''), args)


def saved(path):
    """Keep exact UTF-8 text (including CRLF), even if it is not valid JSON."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return {'historical': True, 'record_status': 'missing', 'raw': '', 'recorded': None}
    except OSError as exc:
        return {'historical': True, 'record_status': 'unreadable', 'error': str(exc), 'recorded': None}
    try:
        raw = content.decode('utf-8')
    except UnicodeError:
        return {'historical': True, 'record_status': 'invalid_utf8', 'encoding': 'base64',
                'raw_base64': base64.b64encode(content).decode('ascii'), 'byte_length': len(content),
                'sha256': hashlib.sha256(content).hexdigest(), 'recorded': None}
    try:
        value = json.loads(raw)
    except ValueError:
        return {'historical': True, 'record_status': 'invalid_json', 'raw': raw, 'recorded': None}
    return {'historical': True, 'record_status': 'stored', 'raw': raw, 'recorded': value}


def saved_lines(path):
    original = saved(path)
    values = []
    valid = original['record_status'] not in ('invalid_utf8', 'unreadable')
    # JSONL delimiters are LF, not Unicode line/paragraph separators inside JSON
    # strings. Keep each original terminator, including CRLF and an absent EOF LF.
    parts = original.get('raw', '').split('\n')
    for index, part in enumerate(parts):
        line = part + ('\n' if index < len(parts) - 1 else '')
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            values.append(value)
            valid = valid and isinstance(value, dict) and isinstance(value.get('kind'), str) and bool(value['kind'])
        except ValueError:
            valid = False
            values.append({'kind': 'unreadable', 'raw': line})
    original['jsonl_status'] = 'complete' if valid else 'not_parsed'
    return original, values


def ticket(P, key, visible_ids):
    value = P.store.ticket(key)
    if not value:
        raise ApiError(404, '没有这个工单')
    if value['project_id'] not in visible_ids:
        raise ApiError(403, '工具连接无权读取此项目')
    return value


def bound_run(P, rid, t=None, visible_ids=None):
    value = P.store.run(rid)
    if not value:
        raise ApiError(404, '没有这个运行')
    if visible_ids is not None and value['project_id'] not in visible_ids:
        raise ApiError(403, '工具连接无权读取此运行')
    if t is not None and (value['ticket_id'] != t['id'] or value['project_id'] != t['project_id']):
        raise ApiError(404, '运行与当前工单或项目不匹配')
    if value['ticket_id']:
        owner = P.store.ticket(value['ticket_id'])
        if not owner or owner['project_id'] != value['project_id']:
            raise ApiError(404, '运行的工单和项目绑定不一致')
    return value


def recheck_history(P, op):
    stored = saved(Path(P.data_dir) / 'verification-operations' / 'runs' / str(op['id']) / 'verification.json')
    recorded = stored.get('recorded')
    binding = recorded.get('recheck_operation') if isinstance(recorded, dict) else None
    status = 'not_checked'
    if binding is not None:
        if not isinstance(binding, dict) or any(key in binding and (type(binding[key]) is not int or binding[key] != op[key])
                                               for key in ('id', 'source_run')):
            raise ApiError(409, '复检历史文件与登记操作或来源运行不匹配')
        if 'id' in binding and 'source_run' in binding:
            status = 'stored_match'
    return {'record': op, 'verification': stored, 'binding_status': status}


def run_verification(P, run, path):
    stored = saved(path)
    recorded = stored.get('recorded')
    binding = recorded.get('recheck_operation') if isinstance(recorded, dict) else None
    stored['binding_status'] = 'not_checked'
    if binding is not None:
        if not isinstance(binding, dict):
            raise ApiError(409, '运行验证历史的复检来源格式不匹配')
        if 'source_run' in binding and (type(binding['source_run']) is not int or binding['source_run'] != run['id']):
            raise ApiError(409, '运行验证历史与来源运行不匹配')
        if 'id' in binding:
            if type(binding['id']) is not int or binding['id'] <= 0:
                raise ApiError(409, '运行验证历史的复检编号无效')
            found = rows(P.store, 'verification_operations', 'WHERE id=?', (binding['id'],))
            if found:
                if any(found[0][key] != expected for key, expected in
                       (('source_run', run['id']), ('project_id', run['project_id']), ('ticket_id', run['ticket_id']))):
                    raise ApiError(409, '运行验证历史与复检登记归属不匹配')
                if 'source_run' in binding:
                    stored['binding_status'] = 'stored_match'
    # Older, missing-operation and previous_verifications records are historical;
    # never recursively replace their earlier operation IDs with the latest ID.
    return stored


def run_history(P, run):
    folder = Path(P.data_dir) / 'runs' / str(run['id'])
    operations = rows(P.store, 'verification_operations',
                      'WHERE source_run=? AND project_id=? AND ticket_id IS ? ORDER BY id',
                      (run['id'], run['project_id'], run['ticket_id']))
    return {'historical': True, 'run': dict(run),
            'verification': run_verification(P, run, folder / 'verify.json'),
            'lifecycle': saved(folder / 'lifecycle.json'),
            'rechecks': [recheck_history(P, op) for op in operations]}


def run_get(P, rid, since, visible_ids):
    run = bound_run(P, rid, visible_ids=visible_ids)
    history = run_history(P, run)
    return dict(run, output=run['output'][since:], output_len=len(run['output']),
                ticket_key=(P.store.ticket(run['ticket_id']) or {}).get('key', '') if run['ticket_id'] else '',
                history=history, verification=None, recheck=None, lifecycle=None,
                verification_status='not_checked', lifecycle_status='not_checked',
                can_retry=None, retry_status='not_checked', execution=False, notice=NOTICE)


def probes(P, t, cid=None):
    if not rows(P.store, 'harness_probe_runs', 'LIMIT 1'):
        return []
    values = P.store.q('SELECT h.* FROM harness_probe_runs h JOIN code_candidates c ON c.id=h.candidate_id '
                      'JOIN runs r ON r.id=c.run_id WHERE c.ticket_id=? AND r.ticket_id=? AND r.project_id=? '
                      + ('AND c.id=? ' if cid is not None else '') + 'ORDER BY h.id',
                      (t['id'], t['id'], t['project_id']) + ((cid,) if cid is not None else ()))
    result = []
    for value in values:
        try:
            source = json.loads(value['source'])
        except (ValueError, TypeError):
            raise ApiError(409, '探测历史来源不能核对所属工单') from None
        expected = {'candidate_id': value['candidate_id'], 'ticket_id': t['id'],
                    'project_id': t['project_id'], 'ticket': t['key']}
        if not isinstance(source, dict) or any(type(source.get(key)) is not type(want) or source.get(key) != want
                                               for key, want in expected.items()):
            raise ApiError(409, '探测历史来源与候选、工单或项目不匹配')
        # Check ownership before opening any historical artifact. A stored result
        # may itself contradict the row, so validate its declared source too.
        stored = saved(Path(P.data_dir) / 'harness-probes' / str(value['id']) / 'result.json')
        recorded = stored.get('recorded')
        if isinstance(recorded, dict) and 'source' in recorded and recorded['source'] != source:
            raise ApiError(409, '探测结果与登记来源不匹配')
        result.append({'historical': True, 'record': value, 'result': stored})
    return result


def ticket_preview(P, t):
    from . import preview
    # This file is shared across projects: malformed content must not silently
    # look absent, and its entire raw contents must never be disclosed here.
    try:
        state = json.loads(preview._state_file(P.data_dir).read_bytes().decode('utf-8'))
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError, UnicodeError):
        raise ApiError(409, '共享预览历史无法读取或解析，当前记录不可核对') from None
    if not isinstance(state, dict):
        raise ApiError(409, '共享预览历史格式无法核对')
    recorded = state.get(t['key'], {})
    if not isinstance(recorded, dict):
        raise ApiError(409, '预览历史记录格式无法核对')
    if recorded.get('run_id') is not None:
        bound_run(P, recorded['run_id'], t)
    if recorded.get('candidate_id') is not None:
        found = rows(P.store, 'code_candidates', 'WHERE id=? AND ticket_id=?', (recorded['candidate_id'], t['id']))
        if not found:
            raise ApiError(404, '预览历史与当前工单不匹配')
        bound_run(P, found[0]['run_id'], t)
    # A ticket's latest preview may belong to a later candidate. Ownership is
    # checked above; no claim is made that it verifies the requested candidate.
    return {'historical': True, 'scope': 'ticket', 'ticket_id': t['id'], 'project_id': t['project_id'],
            'binding_status': 'not_checked', 'recorded': recorded}


def candidate(P, cid, visible_ids):
    found = rows(P.store, 'code_candidates', 'WHERE id=?', (cid,))
    if not found:
        raise ApiError(404, '没有这个外部候选')
    row = found[0]
    t = ticket(P, row['ticket_id'], visible_ids)
    run = bound_run(P, row['run_id'], t)
    recorded_preview = ticket_preview(P, t)
    assessments = rows(P.store, 'candidate_assessments', 'WHERE candidate_id=? ORDER BY id', (cid,))
    decisions = rows(P.store, 'candidate_decisions', 'WHERE candidate_id=? ORDER BY id', (cid,))
    team = []
    if decisions and rows(P.store, 'candidate_team_decisions', 'LIMIT 1'):
        team = P.store.q('SELECT d.* FROM candidate_team_decisions d JOIN candidate_decisions c ON c.id=d.decision_id WHERE c.candidate_id=? ORDER BY d.decision_id', (cid,))
    history = {'historical': True, 'candidate': dict(row), 'run': run_history(P, run),
               'assessments': assessments, 'decisions': decisions, 'team_decisions': team,
               'merges': rows(P.store, 'candidate_merges', 'WHERE candidate_id=?', (cid,)),
               'ticket_preview': recorded_preview,
               'harness_probes': probes(P, t, cid)}
    return {'id': cid, 'ticket': t['key'], 'ticket_id': t['id'], 'project_id': t['project_id'],
            'project': P.store.project(t['project_id'])['key'], 'run_id': run['id'],
            'author': row['agent'], 'base_commit': row['base_commit'], 'commit': row['commit_sha'],
            'ref': row['ref'], 'requirement_hash': row['requirement_hash'],
            'criteria': json.loads(row['criteria']), 'summary': row['summary'],
            'state': 'not_checked', 'current': None, 'verification_status': 'not_checked',
            'verification': None, 'verification_passed': None, 'verification_hash': '',
            'preview': {'state': 'not_checked'}, 'preview_ready': None, 'preview_hash': '',
            'preview_url': '', 'preview_entry_path': '', 'assessment': None, 'harness_probe': None,
            'technical_acceptance': None, 'ready_for_human': None, 'human_decision': None,
            'human_accepted': None, 'evidence_hash': '', 'blocked': None, 'missing': None,
            'history': history, 'execution': False, 'notice': NOTICE}


def candidate_list(P, args, visible_ids):
    t = ticket(P, args['ticket'], visible_ids)
    values = []
    if rows(P.store, 'code_candidates', 'LIMIT 1'):
        # Project scope and source-run relationships precede pagination.
        values = P.store.q('SELECT c.id FROM code_candidates c JOIN runs r ON r.id=c.run_id '
                          'WHERE c.ticket_id=? AND r.ticket_id=? AND r.project_id=? AND c.id>? ORDER BY c.id LIMIT ?',
                          (t['id'], t['id'], t['project_id'], args['after'], args['limit'] + 1))
    selected = values[:args['limit']]
    return {'items': [candidate(P, row['id'], visible_ids) for row in selected],
            'has_more': len(values) > args['limit'], 'next_after': selected[-1]['id'] if selected else args['after']}


def ticket_get(P, key, visible_ids):
    from . import project_library, signoff, team
    from .agent_api import _tool_preview, _requirement
    from .. import config
    t = ticket(P, key, visible_ids)
    p = P.store.project(t['project_id'])
    runs = P.store.q('SELECT * FROM runs WHERE ticket_id=? AND project_id=? ORDER BY id DESC', (t['id'], p['id']))
    refs = project_library.reference_state(P.store, p)
    inputs = project_library._binding_values(refs)
    candidates = rows(P.store, 'code_candidates', 'WHERE ticket_id=? ORDER BY id DESC', (t['id'],))
    candidates = [r for r in candidates if any(run['id'] == r['run_id'] for run in runs)]
    evidence_original, evidence = saved_lines(signoff.epath(P.data_dir, t['key']))
    # A requirement digest is not safe to issue when its stored contract cannot
    # be decoded. Keep those bytes available above rather than pretending empty.
    requirement = None
    if evidence_original['jsonl_status'] == 'complete':
        requirement = _requirement(t, P.store, reference_inputs=inputs, contract_records=evidence)
    return {'ticket': t, 'project': p, 'events': P.store.events(t['id']), 'runs': runs,
            'team_assignment': team.assignment(P, t), 'history': {'historical': True,
                'runs': [run_history(P, run) for run in runs],
                'evidence': evidence, 'evidence_original': evidence_original},
            'intake_recovery': None, 'plain_state': None, 'auto_next': None,
            'evidence': None, 'package': None, 'epic': None, 'parent': None,
            'repository': {'root': p['root'], 'head': '', 'head_status': 'not_checked',
                           'commands': config.load(Path(p['root'])).get('commands') or {}},
            'preview': _tool_preview(P, t), 'evidence_state': {'verification_status': 'not_checked'},
            'knowledge': {'workflow': project_library.profile(P.store, p)['workflow'], 'references': refs,
                          'references_hash': project_library.digest(inputs),
                          'search': {'operation': 'library_search', 'project': p['key']},
                          'read': {'operation': 'library_read', 'project': p['key']}},
            'requirement_hash': requirement, 'requirement_status': 'stored_inputs' if requirement else 'not_checked',
            'harness_library': {'project': p['key'], 'verification_status': 'not_checked',
                                'history': probes(P, t), 'automatic_policy_changes': False},
            'external_candidates': candidates, 'verification_status': 'not_checked',
            'execution': False, 'notice': NOTICE}


def library_get(P, p):
    from . import project_library as library
    st = P.store
    derivations = rows(st, 'project_derivations', 'WHERE project_id=?', (p['id'],))
    return {'project': p, 'profile': library.profile(st, p),
            'sources': rows(st, 'project_sources', 'WHERE project_id=? ORDER BY id', (p['id'],)),
            'revisions': [dict(r, commit=r['commit_sha'], summary=json.loads(r['summary']),
                               history={'historical': True, 'record': dict(r)},
                               recorded_status=r['status'], runtime_status='not_checked', historical=True)
                          for r in rows(st, 'knowledge_revisions', 'WHERE project_id=? ORDER BY seq DESC', (p['id'],))],
            'references': library.reference_state(st, p),
            'derivation': derivations[0] if derivations else None,
            'grants': rows(st, 'knowledge_grants', 'WHERE source_project=? ORDER BY target_project', (p['id'],)),
            'runtime_status': 'not_checked', 'execution': False, 'notice': NOTICE}
