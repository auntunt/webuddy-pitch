"""Operator-owned project test contracts and case-level execution evidence."""
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import ApiError
from . import filelock

KINDS = ('setup', 'build', 'static', 'unit', 'integration', 'e2e', 'security', 'performance', 'migration', 'mutation', 'cleanup')
CASE_KINDS = ('unit', 'integration', 'e2e')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read(data_dir):
    path = Path(data_dir) / 'project-tests.json'
    try:
        value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except ValueError as exc:
        raise ApiError(400, '项目测试配置不是有效 JSON，请修复配置文件') from exc
    if not isinstance(value, dict):
        raise ApiError(400, '项目测试配置必须是项目代号到配置的对象')
    return value


def view(data_dir, key):
    profile = _read(data_dir).get(key)
    if profile is not None:
        validate(profile)
    return {'project': key, 'profile': profile, 'revision': digest(profile), 'kinds': list(KINDS)}


def validate(profile):
    if not isinstance(profile, dict) or set(profile) != {'executor', 'stages', 'require_all_criteria'}:
        raise ApiError(400, '测试配置需要 executor、stages 和 require_all_criteria')
    if profile['executor'] not in ('local', 'testbox') or type(profile['require_all_criteria']) is not bool:
        raise ApiError(400, '执行位置必须为 local 或 testbox；逐项覆盖开关必须为布尔值')
    stages = profile['stages']
    if not isinstance(stages, list) or not 1 <= len(stages) <= 32:
        raise ApiError(400, '配置 1 至 32 个检查阶段')
    seen = set()
    for stage in stages:
        if not isinstance(stage, dict) or set(stage) - {'id', 'kind', 'command', 'required', 'timeout', 'depends_on', 'report', 'criteria'}:
            raise ApiError(400, '检查阶段含未知字段')
        name = stage.get('id')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,49}', name) or name in seen:
            raise ApiError(400, '阶段代号须唯一，仅使用字母、数字、短横线和下划线')
        if stage.get('kind') not in KINDS or not isinstance(stage.get('command'), str) or not stage['command'].strip():
            raise ApiError(400, '阶段需要检查类型和实际命令')
        if type(stage.get('required')) is not bool or type(stage.get('timeout')) is not int or not 1 <= stage['timeout'] <= 7200:
            raise ApiError(400, '阶段需要必需开关和 1 至 7200 秒超时')
        deps = stage.get('depends_on', [])
        if not isinstance(deps, list) or any(not isinstance(d, str) or d not in seen for d in deps):
            raise ApiError(400, '依赖只能引用排在前面的阶段')
        report = stage.get('report')
        if report:
            if not isinstance(report, dict) or set(report) != {'format', 'path'} or report['format'] not in ('junit', 'json'):
                raise ApiError(400, '报告需指定 junit/json 格式和路径')
            path = report['path']
            if not isinstance(path, str) or not path or '\\' in path or ':' in path or path.startswith('/') or any(p in ('..', '') for p in path.split('/')):
                raise ApiError(400, '报告必须是工作目录内的相对路径，可用 * 匹配文件名')
        if stage['kind'] in CASE_KINDS and not report:
            raise ApiError(400, '单元、集成和端到端测试必须提供用例报告')
        mapping = stage.get('criteria', {})
        if not isinstance(mapping, dict) or any(not isinstance(k, str) or not k or not isinstance(v, list) or not v or any(not isinstance(c, str) or not c for c in v) for k, v in mapping.items()):
            raise ApiError(400, '验收关联须为“验收项代号: [精确用例 ID]”')
        if mapping and not report:
            raise ApiError(400, '只有用例报告能关联验收项')
        seen.add(name)
    if not any(s['required'] and s['kind'] in CASE_KINDS for s in stages):
        raise ApiError(400, '至少配置一项必需的单元、集成或端到端测试')
    return profile


def save(data_dir, key, body):
    if not isinstance(body, dict) or set(body) != {'revision', 'profile'}:
        raise ApiError(400, '需要当前版本和测试配置')
    profile = validate(body['profile'])
    folder = Path(data_dir)
    with (folder / '.project-tests.lock').open('a+b') as lock:
        filelock.try_lock(lock, blocking=True)
        raw = _read(folder)
        if digest(raw.get(key)) != body['revision']:
            raise ApiError(409, '项目测试配置已变化，请重新打开后编辑')
        raw[key] = profile
        fd, name = tempfile.mkstemp(prefix='.project-tests-', dir=folder)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, folder / 'project-tests.json')
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return view(folder, key)


def cases(raw, format):
    if format == 'junit':
        root = ET.fromstring(raw)
        if root.tag not in ('testsuite', 'testsuites'):
            raise ValueError('JUnit 根节点必须为 testsuite/testsuites')
        result = []
        for node in root.iter('testcase'):
            name = node.get('name')
            if not name:
                raise ValueError('JUnit 用例缺少名称')
            status = 'fail' if node.find('failure') is not None or node.find('error') is not None else 'skip' if node.find('skipped') is not None else 'pass'
            case = {'id': (node.get('classname', '') + '::' + name).lstrip(':'), 'status': status}
            for prop in node.findall('./properties/property'):
                field = prop.get('name', '')
                if field in ('webuddy.input', 'webuddy.expected', 'webuddy.actual'):
                    case[field.split('.')[1]] = prop.get('value') if prop.get('value') is not None else prop.text or ''
            result.append(case)
        for suite in root.iter():
            if suite.tag not in ('testsuite', 'testsuites'):
                continue
            nodes = list(suite.iter('testcase'))
            counts = {'tests': len(nodes), 'failures': sum(n.find('failure') is not None for n in nodes),
                      'errors': sum(n.find('error') is not None for n in nodes),
                      'skipped': sum(n.find('skipped') is not None for n in nodes)}
            for name, count in counts.items():
                if suite.get(name) is not None and int(suite.get(name)) != count:
                    raise ValueError('JUnit 汇总与逐项结果不一致：' + name)
    else:
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get('cases'), list):
            raise ValueError('JSON 报告需要 cases 数组')
        result = value['cases']
        if any(not isinstance(c, dict) or not isinstance(c.get('id'), str) or not c['id'] or c.get('status') not in ('pass', 'fail', 'skip') for c in result):
            raise ValueError('每个用例需要 id 和 pass/fail/skip 状态')
    if not result:
        raise ValueError('报告为零用例')
    if len({c['id'] for c in result}) != len(result):
        raise ValueError('报告中用例 ID 重复')
    return result


def collect(profile, envelope, folder, criteria):
    """Parse actual reports independently of the command's exit status."""
    results, proofs = [], {}
    if len(envelope['stages']) != len(profile['stages']):
        raise ValueError('执行回执阶段数不匹配')
    for stage, record in zip(profile['stages'], envelope['stages']):
        if record['id'] != stage['id']:
            raise ValueError('执行回执阶段身份不匹配')
        item = {k: record[k] for k in ('id', 'exit_code', 'seconds', 'error')}
        item.update(kind=stage['kind'], required=stage['required'], command=stage['command'], cases=[],
                    execution_status=record.get('execution_status', 'completed' if record['exit_code'] == 0 else 'failed'),
                    failure_kind=record.get('failure_kind', ''))
        log = base64.b64decode(record['log'], validate=True)
        (folder / (stage['id'] + '.log')).write_bytes(log)
        item['log_sha256'] = hashlib.sha256(log).hexdigest()
        item['output'] = log.decode('utf-8', 'replace')
        item['status'] = 'pass' if record['exit_code'] == 0 and not record['error'] else 'fail'
        item['report_valid'] = not bool(stage.get('report'))
        if stage.get('report'):
            try:
                if not record.get('reports'):
                    raise ValueError(record.get('report_error') or '缺少报告')
                item['reports'] = []
                for index, source in enumerate(record['reports']):
                    raw = base64.b64decode(source['raw'], validate=True)
                    artifact = stage['id'] + '-' + str(index) + ('.xml' if stage['report']['format'] == 'junit' else '.json')
                    (folder / artifact).write_bytes(raw)
                    item['reports'].append({'path': artifact, 'source': source['path'], 'sha256': hashlib.sha256(raw).hexdigest()})
                if record.get('report_error'):
                    raise ValueError(record['report_error'])
                for artifact in item['reports']:
                    item['cases'].extend(cases((folder / artifact['path']).read_bytes(), stage['report']['format']))
                if len({c['id'] for c in item['cases']}) != len(item['cases']):
                    raise ValueError('多个报告中的用例 ID 重复')
                item['report_valid'] = True
                if any(c['status'] != 'pass' for c in item['cases']):
                    item['status'] = 'fail'
                    item['error'] = '报告有失败或跳过用例'
            except (ValueError, ET.ParseError) as exc:
                item.update(status='fail', error=str(exc))
                if not item['failure_kind']:
                    item.update(execution_status='blocked', failure_kind='report')
        item['dependencies_valid'] = all(next(r for r in results if r['id'] == dep)['status'] == 'pass' for dep in stage.get('depends_on', []))
        if stage['kind'] != 'cleanup' and not item['dependencies_valid']:
            item.update(status='fail', error=item['error'] or '依赖阶段未通过，本阶段结果不能用于交付', failure_kind='dependency')
        indexed = {c['id']: c['status'] for c in item['cases']}
        for criterion, ids in stage.get('criteria', {}).items():
            passed = not envelope['code_changed'] and item['exit_code'] == 0 and not record['error'] and item['report_valid'] and item['dependencies_valid'] and all(indexed.get(i) == 'pass' for i in ids)
            proofs.setdefault(criterion, []).append({'stage': stage['id'], 'cases': ids, 'status': 'pass' if passed else 'unverified'})
        results.append(item)
    missing = [str(c['id']) for c in criteria if not proofs.get(str(c['id'])) or any(p['status'] != 'pass' for p in proofs[str(c['id'])])]
    ok = not envelope['code_changed'] and all(s['status'] == 'pass' for s in results if s['required']) and (not profile['require_all_criteria'] or bool(criteria) and not missing)
    return {'status': 'pass' if ok else 'fail', 'code_changed': envelope['code_changed'], 'code_identity': envelope['code_identity'], 'stages': results, 'criterion_evidence': proofs, 'uncovered_criteria': missing,
            'require_all_criteria': profile['require_all_criteria'], 'criteria_digest': digest(criteria), 'criteria': criteria, 'profile_digest': digest(profile)}


def criteria_contract(data_dir, rid):
    """Resolve the same effective acceptance contract for execution and freshness checks."""
    import sqlite3
    from contextlib import closing
    from .signoff import client_ac
    from .fixloop import plan_ac
    with closing(sqlite3.connect((Path(data_dir) / 'platform.db').resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT t.id, t.num, t.links, t.title, t.body, t.type, t.priority, t.reporter, t.external, p.key FROM runs r LEFT JOIN tickets t ON t.id=r.ticket_id JOIN projects p ON p.id=r.project_id WHERE r.id=?', (rid,)).fetchone()
        if row is None:
            raise ValueError('无法确认验收标准所属运行')
        if row['id'] is None:
            return {'source': 'none', 'version': '', 'criteria': []}
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='development_sessions'").fetchone():
            session = db.execute('SELECT * FROM development_sessions WHERE ticket_id=?',(row['id'],)).fetchone()
            if session:
                payload = json.loads(session['payload'])
                from .development import digest as development_digest
                binding = development_digest({'source':session['source_hash'],'revision':session['revision'],'payload':payload})
                if not session['confirmed_digest'] or session['confirmed_digest'] != binding:
                    raise ValueError('终端开发需求尚未确认或已经变化')
                client = client_ac(data_dir, row['key'] + '-' + str(row['num']))
                discussion = [dict(event) for event in db.execute("SELECT * FROM events WHERE ticket_id=? AND kind IN ('comment','reject','conflict') ORDER BY id",(row['id'],))]
                version = digest({'confirmed':binding,'ticket':dict(row),'client':client,'discussion':discussion})
                return {'source':'development','version':version,'criteria':payload['criteria']}
        confirmed = client_ac(data_dir, row['key'] + '-' + str(row['num']))
        if confirmed:
            return {'source': 'client', 'version': digest(confirmed), 'criteria': confirmed}
        links = json.loads(row['links'])
        if links.get('delivery'):
            plan = db.execute("SELECT id,result FROM runs WHERE id=? AND ticket_id=? AND mode='plan' AND status='done' AND exit_code=0", (links.get('delivery_plan_run'), row['id'])).fetchone()
            if plan is None:
                raise ValueError('交付绑定的方案不再有效')
        else:
            plan = db.execute("SELECT id,result FROM runs WHERE ticket_id=? AND mode='plan' AND status='done' ORDER BY id DESC LIMIT 1", (row['id'],)).fetchone()
        if plan is None:
            return {'source': 'none', 'version': '', 'criteria': []}
        return {'source': 'plan', 'version': str(plan['id']) + ':' + digest(plan['result']), 'criteria': plan_ac(plan['result'])}


def execute(loop, profile):
    from .agents import git
    data = Path(getattr(loop.r, 'evidence_root', loop.r.data_dir))
    token = uuid.uuid4().hex
    folder = Path(loop.r.data_dir) / 'runs' / str(loop.rid) / 'project-tests' / token
    folder.mkdir(parents=True)
    contract = criteria_contract(data, getattr(loop, 'source_run', loop.rid))
    criteria = contract['criteria']
    plan = {'stages': profile['stages'], 'nonce': token}
    if profile['executor'] == 'local':
        plan['artifact_dir'] = str(folder / 'raw')
    adapter = Path(__file__).with_name('project_test_runner.cjs').read_bytes()
    plan_bytes = json.dumps(plan).encode()
    (folder / 'runner.cjs').write_bytes(adapter)
    (folder / 'plan.json').write_bytes(plan_bytes)
    timeout = sum(s['timeout'] for s in profile['stages']) + 120
    base = git(loop.wt, 'rev-parse', 'HEAD').strip()
    git(loop.wt, 'add', '-A', '-N', '.')
    patch = subprocess.run(['git', '-C', str(loop.wt), 'diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD'], capture_output=True, check=True).stdout
    if profile['executor'] == 'testbox':
        if not loop.box:
            raise ValueError('项目要求测试机，但尚未配置测试机')
        names = []
        try:
            for content, suffix in ((adapter, '.cjs'), (plan_bytes, '.json')):
                name, error = loop.box._send(content, suffix)
                if error:
                    raise ValueError(error)
                names.append(name)
            win = loop.box._detect() == 'windows'
            home = '%USERPROFILE%' if win else '$HOME'
            command = ('' if win else 'setsid ') + 'node "%s/%s" "%s/%s"' % (home, names[0], home, names[1])
            key = 'suite-' + digest(str(data.resolve()))[:12] + '-' + token
            result = loop.box.run(key, Path(loop.p['root']), base, patch, [('test', command)], timeout, loop.say)[0]
        finally:
            if names:
                body = ';'.join("Remove-Item (Join-Path $HOME '%s') -Force" % n for n in names) if loop.box.os == 'windows' else 'rm -f ' + ' '.join('"$HOME/%s"' % n for n in names)
                loop.box.script(body)
    else:
        process, receipt = loop.r.run_command(loop.rid, ['node', str(folder / 'runner.cjs'), str(folder / 'plan.json')], loop.wt, timeout=timeout, kind='project-tests')
        result = {'exit_code': process.returncode, 'output': process.output, 'tail': process.output}
    output = result.get('output', '')
    (folder / 'transport.txt').write_text(output, encoding='utf-8')
    marker = 'TMH_PROJECT_TESTS_' + token + ':'
    lines = [line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
    if result['exit_code'] != 0 or len(lines) != 1:
        raise ValueError('项目测试执行器未完成：' + (result.get('tail') or str(result['exit_code'])))
    envelope = json.loads(base64.b64decode(lines[0], validate=True))
    identity_mismatch = envelope['code_identity'] != base + ':' + hashlib.sha256(patch).hexdigest()
    envelope['code_changed'] = envelope['code_changed'] or identity_mismatch
    report = collect(profile, envelope, folder, criteria)
    if identity_mismatch:
        report['identity_error'] = '执行机代码与申请版本不一致'
    report['criteria_contract'] = contract
    report.update(source_run=getattr(loop, 'source_run', loop.rid), project=loop.p['key'], ticket=loop.t['key'] if loop.t else '', executor=profile['executor'], base=base, diff_sha256=hashlib.sha256(patch).hexdigest(), evidence=str(folder.relative_to(data)))
    if profile['executor'] == 'testbox':
        report['remote_workspace'] = loop.box.dir + '/work/' + key
        report['remote_artifacts'] = envelope['artifact_dir']
    (folder / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    blocked = report['code_changed'] or any(s['required'] and s['execution_status'] == 'blocked' and s['failure_kind'] != 'dependency' for s in report['stages'])
    return [{'kind': 'test', 'command': '项目测试：' + ' → '.join(s['id'] for s in profile['stages']),
             'exit_code': 0 if report['status'] == 'pass' else 1, 'seconds': sum(s['seconds'] for s in report['stages']),
             'output': '\n'.join(s['id'] + ': ' + s['status'] + (' · ' + s['error'] if s['error'] else '') for s in report['stages']),
             'project_tests': report, 'verification_state': 'passed' if report['status'] == 'pass' else 'blocked' if blocked else 'failed'}]


def current_issue(data_dir, rid, verification):
    import sqlite3
    from contextlib import closing
    profiles = _read(data_dir)
    reports = [c['project_tests'] for c in verification.get('commands', []) if c.get('project_tests')]
    if not profiles and not reports:
        return ''
    path = Path(data_dir) / 'platform.db'
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT p.key FROM projects p JOIN runs r ON r.project_id=p.id WHERE r.id=?', (rid,)).fetchone()
    if not row:
        return '无法确认项目测试归属'
    key = row[0]
    profile = profiles.get(key)
    if profile is not None:
        validate(profile)
    if profile and not reports:
        return '项目已配置测试，但此版本没有对应测试报告，请重新验证'
    for report in reports:
        if report.get('source_run') != rid:
            return '项目测试报告属于其他运行'
        if report['project'] != key or report['profile_digest'] != digest(profile):
            return '项目测试配置已变化，请重新验证'
        try:
            contract = criteria_contract(data_dir, rid)
        except ValueError as exc:
            return str(exc)
        if report.get('criteria_contract') != contract:
            return '验收标准内容、来源或方案版本已变化，请重新运行项目测试'
        folder = Path(data_dir) / report['evidence']
        if not folder.resolve().is_relative_to(Path(data_dir).resolve()):
            return '项目测试证据路径无效'
        try:
            saved = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            if saved != report:
                return '项目测试记录与原始回执不一致'
            for stage in report['stages']:
                if hashlib.sha256((folder / (stage['id'] + '.log')).read_bytes()).hexdigest() != stage['log_sha256']:
                    return '项目测试日志已变化'
                for artifact in stage.get('reports', []):
                    if hashlib.sha256((folder / artifact['path']).read_bytes()).hexdigest() != artifact['sha256']:
                        return '项目测试报告已变化'
        except (OSError, ValueError):
            return '项目测试原始证据缺失或不可读'
    return ''


def artifact(data_dir, rid, stage_id, name):
    from .fixloop import _verification
    value = _verification(data_dir, rid)
    for command in value.get('commands', []):
        report = command.get('project_tests')
        if not report or report.get('source_run') != rid:
            continue
        for stage in report['stages']:
            if stage['id'] != stage_id:
                continue
            for entry in stage.get('reports', []):
                if entry['path'] != name:
                    continue
                root = Path(data_dir).resolve()
                folder = (root / report['evidence']).resolve()
                path = (folder / name).resolve()
                if not folder.is_relative_to(root) or not path.is_relative_to(folder):
                    raise ApiError(409, '报告路径无效')
                try:
                    raw = path.read_bytes()
                except OSError as exc:
                    raise ApiError(404, '原始报告不存在') from exc
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ApiError(409, '原始报告内容已变化')
                return {'name': name, 'sha256': entry['sha256'], 'base64': base64.b64encode(raw).decode(), 'text': raw.decode('utf-8', 'replace')}
    raise ApiError(404, '本次运行没有该报告')
