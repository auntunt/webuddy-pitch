"""Exercise private Git -> real Jenkins -> isolated Git merge; never business signoff."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.parse
import urllib.request

BASE = '75a9311d5bd485e7fe0701c042520831aa1fa44c'
FEATURE = '4172462acc9fce18f023aa88c0d229b9212ebe8d'
REMOTE = 'ssh://git@127.0.0.1:12222/repos/erp.git'
JOB = '/job/erp-verification'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--exercise', required=True)
    p.add_argument('action', choices=['prepare', 'trigger', 'collect', 'merge'])
    p.add_argument('--version', choices=['baseline', 'candidate'])
    args = p.parse_args()
    if not args.exercise.replace('-', '').isalnum():
        p.error('exercise must contain only letters, digits and hyphens')
    root = args.root.resolve()
    out = root / 'proof' / args.exercise
    out.mkdir(exist_ok=True)
    repo = root / args.exercise
    state_file = out / 'state.json'
    env = dict(os.environ, GIT_SSH_COMMAND='ssh -i "' + str(root/'private/git-client') +
               '" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="' +
               str(root/'private/known_hosts') + '"')

    def git(*cmd):
        return subprocess.check_output(['git', '-C', str(repo), *cmd], env=env, text=True).strip()

    def api(path, data=None, reader=False):
        accounts = json.loads((root/'private/accounts.json').read_text())
        user = accounts['reader_user' if reader else 'admin_user']
        secret = (root/'jenkins/secrets/webuddy-demo/reader-token').read_text().strip() if reader else accounts['admin_password']
        headers = {'Authorization': 'Basic ' + base64.b64encode((user+':'+secret).encode()).decode(),
                   'Content-Type': 'application/x-www-form-urlencoded'}
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=str(root/'private/ca.crt'))),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        origin = 'https://127.0.0.1:18443'
        if data is not None:
            crumb = json.load(opener.open(urllib.request.Request(origin+'/crumbIssuer/api/json', headers=headers), timeout=30))
            headers[crumb['crumbRequestField']] = crumb['crumb']
        with opener.open(urllib.request.Request(origin+path, data=data, headers=headers), timeout=30) as r:
            return r.read(), dict(r.headers)

    def write(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    if args.action == 'prepare':
        if repo.exists() or state_file.exists():
            raise RuntimeError('Exercise already exists; do not overwrite')
        subprocess.run(['git', 'clone', '--no-hardlinks', str(root/'erp'), str(repo)], env=env, check=True)
        main_branch = 'rehearsal/'+args.exercise+'/main'
        feature_branch = 'rehearsal/'+args.exercise+'/refund'
        git('checkout', '-b', main_branch, BASE)
        git('push', REMOTE, main_branch)
        git('checkout', '-b', feature_branch, FEATURE)
        (repo/'WEBUDDY-REHEARSAL.md').write_text(
            '# Isolated workflow rehearsal\n\n'
            'Not customer rules or human acceptance.\n'
            'Cash sales returns require a trimmed 5–200 code-point reason.\n'
            'Reject invalid input without inserting a document; preserve account amounts, reread, duplicate rejection and authentication.\n'
            'Excluded: inventory approval and financial posting.\n'
            'Expected results come from the controller-owned exercise policy, not the implementation output.\n')
        git('add', 'WEBUDDY-REHEARSAL.md')
        git('-c', 'user.name=Webuddy rehearsal agent', '-c', 'user.email=rehearsal@localhost',
            'commit', '-m', 'Record isolated refund workflow design and acceptance scope')
        candidate = git('rev-parse', 'HEAD')
        git('push', REMOTE, feature_branch)
        write('state.json', dict(schema=1, exercise=args.exercise, baseline=BASE, candidate=candidate,
              main_branch=main_branch, feature_branch=feature_branch, remote=REMOTE,
              actor='agent', simulated=True, business_accepted=False, production_deployed=False))
        (out/'change.patch').write_text(git('diff', '--binary', BASE, candidate))
        print(json.dumps({'exercise':args.exercise,'baseline':BASE,'candidate':candidate,'remote':REMOTE}))
        return

    state = json.loads(state_file.read_text())
    if args.action == 'trigger':
        if not args.version: p.error('--version is required')
        record = out/(args.version+'-queue.json')
        if record.exists(): raise RuntimeError('Already queued; query existing receipt, do not trigger twice')
        sha = state[args.version]
        # Reserve the local receipt before sending. Unknown response remains unknown.
        write(record.name, dict(commit=sha, status='requesting', started=datetime.now(timezone.utc).isoformat()))
        _, headers = api(JOB+'/buildWithParameters', urllib.parse.urlencode({'CANDIDATE_SHA':sha}).encode())
        queue = headers.get('Location')
        if not queue: raise RuntimeError('Missing queue receipt; inspect Jenkins before retrying')
        write(record.name, dict(commit=sha, queue=queue, status='queued'))
        print(json.dumps({'version':args.version,'sha':sha,'queue':queue}))
    elif args.action == 'collect':
        if not args.version: p.error('--version is required')
        q = json.loads((out/(args.version+'-queue.json')).read_text())
        if 'build' not in q:
            payload = json.loads(api(urllib.parse.urlsplit(q['queue']).path+'api/json', reader=True)[0])
            if not payload.get('executable'):
                print(json.dumps({'status':'queued','cancelled':payload.get('cancelled',False)}));return
            q['build']=payload['executable']['number'];write(args.version+'-queue.json',q)
        n=q['build']; result=json.loads(api(JOB+'/'+str(n)+'/api/json',reader=True)[0])
        if result['building']:
            print(json.dumps({'build':n,'status':'running'}));return
        shas=[a.get('lastBuiltRevision',{}).get('SHA1') for a in result['actions'] if 'lastBuiltRevision' in a]
        if shas != [q['commit']]:raise RuntimeError('Jenkins SCM SHA mismatch')
        write(args.version+'-build.json', result)
        (out/(args.version+'-console.log')).write_bytes(api(JOB+'/'+str(n)+'/consoleText',reader=True)[0])
        artifacts=[]
        for a in result['artifacts']:
            rel=Path(a['relativePath'])
            if '..' in rel.parts or rel.is_absolute():raise RuntimeError('Invalid artifact path')
            # Retain all reports and original screenshots, leave compiled archives in Jenkins.
            if rel.suffix not in ('.json','.xml','.png','.log'):continue
            path=out/args.version/rel;path.parent.mkdir(parents=True,exist_ok=True)
            raw=api(JOB+'/'+str(n)+'/artifact/'+urllib.parse.quote(rel.as_posix()),reader=True)[0];path.write_bytes(raw)
            artifacts.append(dict(path=rel.as_posix(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        write(args.version+'-artifacts.json',artifacts)
        print(json.dumps({'build':n,'result':result['result'],'sha':q['commit'],'artifacts':len(artifacts)}))
    else:
        # This is an explicitly isolated Git exercise, NOT a platform human approval.
        if not (out/'candidate-build.json').exists():
            raise RuntimeError('No completed candidate CI receipt; merge refused')
        result=json.loads((out/'candidate-build.json').read_text())
        shas=[a.get('lastBuiltRevision',{}).get('SHA1') for a in result['actions'] if 'lastBuiltRevision' in a]
        if result['building'] or result['result']!='SUCCESS' or shas != [state['candidate']]:
            raise RuntimeError('Exact candidate CI is not successful; merge refused')
        if git('status','--porcelain'):raise RuntimeError('Working copy changed; merge refused')
        current=git('ls-remote',REMOTE,'refs/heads/'+state['main_branch']).split()[0]
        if current != state['baseline']:raise RuntimeError('Exercise main moved; query instead of repeating merge')
        git('checkout',state['main_branch']);git('merge','--ff-only',state['candidate'])
        git('push',REMOTE,state['main_branch'])
        actual=git('ls-remote',REMOTE,'refs/heads/'+state['main_branch']).split()[0]
        assert actual==state['candidate']
        write('merge.json',dict(commit=actual,build=result['number'],branch=state['main_branch'],
              actor='agent-simulated-git-operator',simulated=True,pushed=True,deployed=False,
              human_review=False,business_accepted=False,ended=datetime.now(timezone.utc).isoformat()))
        print(json.dumps({'exercise_merge':actual,'pushed':True,'deployed':False,'human_review':False}))


if __name__ == '__main__':main()
