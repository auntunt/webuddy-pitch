"""Complete diff review shared by automatic changes and manual re-review."""
from __future__ import annotations

import hashlib
import re

from .store import now


PART_SIZE = 14000


def parts(diff):
    # Keep each file together when possible. A large file is split without
    # dropping even a character; the part header identifies its source file.
    result = []
    for block in re.split(r'(?m)(?=^diff --git )', diff):
        if not block:
            continue
        header = block.split('\n', 1)[0]
        for start in range(0, len(block), PART_SIZE):
            result.append((header, block[start:start + PART_SIZE]))
    return result


def review(loop, diff, commands, skip, previous):
    from .fixloop import settle_fail, git
    base = git(loop.wt, 'rev-parse', 'HEAD').strip()
    batches = parts(diff)
    records, answers = [], []
    for index, (header, text) in enumerate(batches, 1):
        prompt = ('审查分批 %d/%d：%s\n仅对本批及其调用关系形成结论；可只读查看工作树核对上下文。'
                  '不要修改代码或把代码阅读当作实测。不相关验收项不填入 ac，不能以未阅读部分推断通过。\n'
                  '阻断问题须写明文件、行号、触发条件和实际影响，区分本次引入与既有问题；安全边界、权限和数据写入优先检查。'
                  '复审仅追踪尚未解决的问题及新差异，不重复已解决项，不以风格建议阻断交付。\n'
                  '重新核对本批影响到的新需求、旧功能和不变约束，在 scope 中分别用 new、regression、invariants 数组记录验收项编号和依据；缺少检查写入 gaps，不得推断已覆盖。\n'
                  % (index, len(batches), header)) + text
        answer = loop.diagnose_part(prompt, commands, skip, previous)
        verdict, vague = settle_fail(answer, str(answer.get('verdict') or '').lower())
        if verdict not in ('pass', 'fail') or getattr(loop, 'failed_call', False):
            verdict = 'unknown'
        answer['vague_fail'] = vague
        answer['verdict'] = verdict
        answers.append(answer)
        records.append({'part': index, 'file': header, 'characters': len(text),
                        'sha256': hashlib.sha256(text.encode()).hexdigest(), 'verdict': verdict})
        if getattr(loop, 'failed_call', False):
            break
    same_base = git(loop.wt, 'rev-parse', 'HEAD').strip() == base
    complete = same_base and bool(batches) and len(records) == len(batches) and all(x['verdict'] != 'unknown' for x in records)
    binary = 'GIT binary patch' in diff or bool(re.search(r'(?m)^Binary files .* differ$', diff))
    verdict = ('fail' if any(a['verdict'] == 'fail' for a in answers) else
               'pass' if complete and not binary else 'unknown')
    result = dict(answers[0]) if len(answers) == 1 else {}
    if len(answers) > 1:
        for key in ('match', 'match_why', 'evidence', 'cause', 'guide', 'text'):
            result[key] = '\n\n'.join('第 %d 批：%s' % (i, a[key]) for i, a in enumerate(answers, 1) if a.get(key))
        for key in ('blocking', 'advisory', 'files', 'prior'):
            result[key] = [item for a in answers for item in (a[key] if isinstance(a.get(key), list) else [])]
        result['scope'] = {'batches': [a.get('scope', {}) for a in answers]}
        criteria = {}
        for a in answers:
            for item in a.get('ac') or []:
                if isinstance(item, dict) and item.get('id'):
                    criteria.setdefault(item['id'], []).append(item)
        result['ac'] = []
        for key, items in criteria.items():
            status = 'fail' if any(x.get('result') == 'fail' for x in items) else 'pass' if complete and all(x.get('result') == 'pass' for x in items) else 'unverified'
            result['ac'].append({'id': key, 'result': status, 'evidence': '\n'.join(str(x.get('evidence') or x.get('why') or '') for x in items)})
    result['vague_fail'] = any(a.get('vague_fail') for a in answers)
    result['verdict'] = verdict
    reviewer = getattr(loop, 'agents', {}).get('diagnose', loop.agent)
    uncovered = ['第 %d 批 %s：%s' % (i, header, '未送审' if i > len(records) else '未形成有效结论')
                 for i, (header, _) in enumerate(batches, 1) if i > len(records) or records[i-1]['verdict'] == 'unknown']
    if binary:
        uncovered.append('二进制内容需专门验证')
    if not same_base:
        uncovered.append('审查期间基准版本变化')
    result['review'] = {'writer_kind': 'human' if hasattr(loop, 'writer') and loop.writer != loop.agent else 'agent', 'writer': getattr(loop, 'writer', loop.agent), 'reviewer': reviewer, 'model': loop.models['diagnose'],
                        'different_executor': reviewer != getattr(loop, 'writer', loop.agent), 'created': now(),
                        'base': base,
                        'diff_sha256': hashlib.sha256(diff.encode()).hexdigest(),
                        'complete': complete and not binary, 'total_parts': len(batches), 'parts': records,
                        'uncovered': uncovered}
    return result


def manual(loop, runner, source, operation, commands, skip, diff):
    """Use the existing supervised operation; never append to the coding run."""
    from .agents import load_config
    from .agent_routes import resolve, step_agent, route
    from .fixloop import recheck_operations
    conf = load_config(runner.data_dir)
    old = operation.get('previous_verification') or {}
    writer = source['agent']
    selected = writer if writer in conf else ((old.get('diagnosis') or {}).get('review') or {}).get('reviewer') or old.get('reviewer') or route(runner.data_dir, loop.p).get('agent', '')
    reviewer = resolve(runner.data_dir, loop.p, step_agent(runner.data_dir, loop.p, 'diagnose', selected))
    if reviewer not in conf:
        raise ValueError('没有这个审查执行器：' + reviewer)
    executor = recheck_operations(runner).runner
    loop.agent, loop.agents = source['agent'], {'diagnose': reviewer}
    loop.models = {'diagnose': (conf[reviewer].get('defaults') or {}).get('diagnose', '')}
    loop.n, loop.failed_call = 0, False
    # Read the actual ticket/plan context, not the operation adapter's limited Store.
    loop.st, loop.r, loop.rid = runner.store, runner, source['id']
    loop.prompt = source.get('prompt') or ''
    loop.writer = writer if writer in conf else source['author']
    plans = [r for r in runner.store.runs(ticket_id=loop.t['id']) if r['mode'] == 'plan' and r['status'] == 'done'] if loop.t else []
    loop.plan = plans[0]['result'] if plans else ''
    loop.say = lambda message: executor.store.append_output(operation['id'], message + '\n')

    def call(mode, prompt):
        if resolve(runner.data_dir, loop.p, reviewer) != reviewer:
            raise ValueError('审查执行器授权已变化')
        from .project_library import require_run_current
        require_run_current(runner.store, loop.p, source['id'])
        loop.n += 1
        code, output = executor.invoke(operation['id'], loop.p, loop.t, reviewer, conf, 'diagnose',
                                       prompt, loop.wt, loop.models['diagnose'], '-review-%d' % loop.n)
        loop.failed_call = loop.failed_call or code != 0
        return output

    loop.call = call
    return loop.diagnose(diff, commands, skip, None)
