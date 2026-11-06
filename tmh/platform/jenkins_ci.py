"""Read Jenkins Git-plugin build identities, never build parameters or agent verdicts."""
import re
from urllib.parse import quote


def checks(get, connection, config, commit):
    repository = connection.get('repositories', {}).get(config['repository'], {})
    remotes = repository.get('remote_urls')
    jobs = repository.get('jobs', {})
    if not isinstance(remotes, list) or not remotes or any(not isinstance(v, str) or not v for v in remotes):
        raise ValueError('Jenkins repository remote identities are not registered')
    result = []
    for name in config['required_checks']:
        segments = jobs.get(name)
        if (not isinstance(segments, list) or not segments
                or any(not isinstance(s, str) or not s or s in ('.', '..') for s in segments)):
            raise ValueError('Jenkins required job is not registered')
        path = ''.join('/job/' + quote(s, safe='') for s in segments)
        tree = 'lastBuild[number],builds[number,result,building,actions[_class,remoteUrls,lastBuiltRevision[SHA1]]]'
        payload = get(path + '/api/json?tree=' + quote(tree, safe=','))
        if not isinstance(payload, dict) or not isinstance(payload.get('builds'), list) or 'lastBuild' not in payload:
            raise ValueError('Incomplete Jenkins build list')
        builds = payload['builds']
        if not builds:
            if payload['lastBuild'] is not None:
                raise ValueError('Jenkins latest build is missing')
            result.append({'name': name, 'state': 'missing', 'runs': []})
            continue
        if len(builds) > 100:
            raise ValueError('Jenkins build window exceeded')
        numbers = [b.get('number') for b in builds if isinstance(b, dict)]
        if (len(numbers) != len(builds) or any(type(n) is not int or n <= 0 for n in numbers)
                or numbers != sorted(set(numbers), reverse=True)
                or not isinstance(payload['lastBuild'], dict)
                or type(payload['lastBuild'].get('number')) is not int
                or payload['lastBuild']['number'] != numbers[0]):
            raise ValueError('Jenkins build window identity mismatch')
        selected = None
        unknown = False
        for build in builds:
            if type(build.get('building')) is not bool or 'result' not in build or not isinstance(build.get('actions'), list):
                raise ValueError('Incomplete Jenkins build')
            scm = [a for a in build['actions'] if isinstance(a, dict)
                   and a.get('_class') == 'hudson.plugins.git.util.BuildData'
                   and isinstance(a.get('remoteUrls'), list) and any(v in remotes for v in a['remoteUrls'])]
            if not scm:
                # A newer queued/checkout-failed build must not be hidden by an
                # older green build whose SHA happens to match.
                unknown = True
                break
            revisions = []
            for action in scm:
                revision_data = action.get('lastBuiltRevision')
                if not isinstance(revision_data, dict):
                    raise ValueError('Jenkins SCM revision is missing or malformed')
                revision = revision_data.get('SHA1')
                if (not all(v in remotes for v in action['remoteUrls'])
                        or not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision)):
                    raise ValueError('Jenkins SCM identity cannot be verified')
                revisions.append(revision)
            if commit in revisions:
                if any(r != commit for r in revisions):
                    raise ValueError('Jenkins checked out multiple revisions of the target repository')
                selected = build
                break
        state = ('blocked' if unknown else 'missing') if selected is None else (
            'pass' if not selected['building'] and selected['result'] == 'SUCCESS' else 'blocked')
        runs = [] if selected is None else [{'id': selected['number'], 'status': 'running' if selected['building'] else 'completed',
            'conclusion': selected['result'], 'commit': commit,
            'url': connection['url'].rstrip('/') + path + '/' + str(selected['number']) + '/'}]
        result.append({'name': name, 'state': state, 'runs': runs,
                       'message': '较新构建缺少可核对的Git插件记录' if unknown else
                                  '最近100次构建中没有当前仓库和提交' if selected is None else ''})
    return result
