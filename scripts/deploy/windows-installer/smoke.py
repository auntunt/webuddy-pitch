"""One installer round trip with synthetic, isolated per-user state."""
import http.cookiejar
import urllib.parse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

installer, work = map(lambda p: Path(p).resolve(), sys.argv[1:])
work.mkdir(parents=True, exist_ok=True)
app = work / '中文 安装目录' / 'Webuddy'
local = work / 'user'
state = local / 'Webuddy'
state.mkdir(parents=True)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
config = json.dumps({'host': '127.0.0.1', 'port': port, 'data_dir': str(state / 'data'), 'environment': {'WEBUDDY_LAN_SIGNUP': 'admin'}})
(state / 'config.json').write_text(config, encoding='utf-8')
(state / 'keep.txt').write_text('persistent-user-data', encoding='utf-8')
env = dict(os.environ, LOCALAPPDATA=str(local), PYTHONUTF8='1')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def install():
    subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=',
                    '/DIR=' + str(app), '/LOG=' + str(work / 'install.log')], env=env, check=True, timeout=240)

def command(action):
    subprocess.run([str(app / 'runtime/python/python.exe'), '-B', str(app / 'desktop.py'), action], env=env, check=True, timeout=90)

def check():
    with opener.open('http://127.0.0.1:%s/next/' % port, timeout=10) as r:
        assert r.status == 200
    with opener.open('http://127.0.0.1:%s/api/meta' % port, timeout=10) as r:
        meta = json.load(r)
        assert meta['user'] == 'installer-pilot' and meta['operator_authenticated']
    assert (state / 'config.json').read_text(encoding='utf-8') == config
    assert (state / 'keep.txt').read_text() == 'persistent-user-data'

install()
try:
    command('start')
    base = 'http://127.0.0.1:%s' % port
    request = urllib.request.Request(base + '/register', data=urllib.parse.urlencode({
        'username': 'installer-pilot', 'password': 'installer-pilot-password', 'next': '/next/',
    }).encode(), headers={'Origin': base, 'Content-Type': 'application/x-www-form-urlencoded'})
    with opener.open(request, timeout=10) as r:
        assert r.url.endswith('/next/')
    check()
    command('stop')
    install()
    command('start')
    check()
finally:
    command('stop')
assert (app / 'unins000.exe').is_file()
subprocess.run([str(app / 'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], env=env, check=True, timeout=120)
assert (state / 'keep.txt').read_text() == 'persistent-user-data'
assert (state / 'config.json').read_text(encoding='utf-8') == config
receipt = {'installer': installer.name, 'sha256': hashlib.file_digest(installer.open('rb'), 'sha256').hexdigest(),
           'bytes': installer.stat().st_size, 'installation': 'passed', 'start_restart': 'passed',
           'registered_account_survives_restart': 'passed', 'upgrade_preserves_config': 'passed', 'uninstall_preserves_data': 'passed',
           'cursor_live_model': 'not_tested', 'credentials_included': False}
(work / 'receipt.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
