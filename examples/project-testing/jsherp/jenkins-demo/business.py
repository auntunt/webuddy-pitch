"""Run the real ERP/browser proof inside the isolated Jenkins demo worker."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

root = Path.cwd()
assets = Path(__file__).resolve().parent
out = root / 'target/business'
out.mkdir(parents=True, exist_ok=True)
subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', '.'], check=True)
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
assert sha == os.environ['CANDIDATE_SHA']
harness = {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in ('business.py', 'serve.py', 'verify.mjs')}
source = sha + ':' + hashlib.sha256(subprocess.check_output(
    ['git', 'diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD'])).hexdigest()
jar = root / 'jshERP-boot/target/jshERP.jar'
env = dict(os.environ, SPRING_DATASOURCE_URL='jdbc:mysql://webuddy-demo-mysql:3306/jsh_erp?useUnicode=true&characterEncoding=utf8&allowMultiQueries=true&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai',
           SPRING_DATASOURCE_USERNAME='root', SPRING_DATASOURCE_PASSWORD='webuddy-isolated-test',
           SPRING_REDIS_HOST='webuddy-demo-redis', SPRING_REDIS_PASSWORD='webuddy-isolated-test', SERVER_PORT='19999')
processes = []
streams = []
def start(args, name, environment=None):
    stream = (out / (name + '.log')).open('wb'); streams.append(stream)
    process = subprocess.Popen(args, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    processes.append(process)
    return process

def ready(url, process):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Service exited: ' + str(process.args))
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200: return
        except (OSError, TimeoutError):
            pass
        time.sleep(.5)
    raise RuntimeError('Readiness timeout: ' + url)

try:
    app = start(['/opt/java8/bin/java', '-Duser.timezone=Asia/Shanghai', '-Xmx768m', '-jar', str(jar)], 'erp', env)
    ready('http://127.0.0.1:19999/jshERP-boot/platformConfig/getPlatform/checkcodeFlag', app)
    proxy = start(['python3', str(assets / 'serve.py')], 'proxy')
    ready('http://127.0.0.1:18980/', proxy)
    chrome = start(['chromium', '--headless', '--no-sandbox', '--disable-dev-shm-usage',
                    '--remote-debugging-port=18982', '--user-data-dir=' + str(out / 'chrome'), 'about:blank'], 'chromium')
    ready('http://127.0.0.1:18982/json', chrome)
    build = {'source': source, 'harness_sha256': harness, 'pid': app.pid,
             'process_start': Path('/proc/' + str(app.pid) + '/stat').read_text().split(' ')[21],
             'jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
             'index_sha256': hashlib.sha256((root / 'jshERP-web/dist/index.html').read_bytes()).hexdigest()}
    (out / 'build.json').write_text(json.dumps(build, indent=2))
    subprocess.run(['node', str(assets / 'verify.mjs')], check=True, timeout=240)
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', '.'], check=True)
    assert harness == {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in harness}, 'Verification scripts changed during run'
finally:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    for stream in streams: stream.close()
