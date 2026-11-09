"""Run-bound SSH test tools for the coding agent; credentials stay on the host."""
import base64
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = 'tmh.platform'

from . import testbox
from .agents import git
from .store import Store

INSTRUCTION = '''
## 测试机工具（本轮实际测试入口）
本轮已提供 testbox_info 和 testbox_run 工具，通过平台已有SSH连接操作测试机，不需要读取私钥或关闭本机沙箱。
此前“不要启动服务、不要调接口”的限制只适用于本机；在测试机上必须验证本次改动。
先用 testbox_info 确认系统。修改完成后，在代码目录编写可重复运行的测试脚本（Windows使用PowerShell，Linux使用sh），通过testbox_run执行。
脚本应安装本项目需要的依赖、构建并运行测试；涉及应用运行时，启动本次版本的服务，等待健康接口，再检查本次需求涉及的接口/页面。使用隔离测试数据、独立端口，finally/trap清理自己启动的进程，不能碰其他任务或生产数据库。
testbox_run会同步当前HEAD和完整未提交改动，脚本在测试机的本轮工作目录执行。外部依赖/测试数据缺失时返回非零并说明，不得用打印OK代替验证。失败后读回执、修复、再调用；最后一次改动后必须重新测试。
工具的退出码只证明脚本的检查结果，不代表人工验收。最终说明实际检查、结果和未验证项。
'''


def snapshot(workdir):
    git(workdir, 'add', '-A', '-N', '.')
    base = git(workdir, 'rev-parse', 'HEAD').strip()
    patch = subprocess.run(['git', '-C', str(workdir), 'diff', '--binary', 'HEAD'], check=True, capture_output=True).stdout
    return base, patch, hashlib.sha256(base.encode() + b'\0' + patch).hexdigest()


def config_args(data_dir, rid, workdir):
    # Absolute script entry keeps imports independent of the maintained project's PYTHONPATH.
    args = [str(Path(__file__).resolve()), str(Path(data_dir).resolve()), str(rid), str(Path(workdir).resolve())]
    return ['-c', 'mcp_servers.webuddy_testbox.command=' + json.dumps(sys.executable),
            '-c', 'mcp_servers.webuddy_testbox.args=' + json.dumps(args),
            '-c', 'mcp_servers.webuddy_testbox.tool_timeout_sec=1260',
            '-c', 'mcp_servers.webuddy_testbox.tools.testbox_info.approval_mode="approve"',
            '-c', 'mcp_servers.webuddy_testbox.tools.testbox_run.approval_mode="approve"']


TOOLS = [
    {'name': 'testbox_info', 'description': '查看本轮测试机系统、工具与独立工作目录；不返回凭据。',
     'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': True},
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'testbox_run', 'description': '同步本次代码并通过SSH运行测试脚本，返回真实退出码、完整日志和版本绑定回执。',
     'annotations': {'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': True},
     'inputSchema': {'type': 'object', 'properties': {
         'script': {'type': 'string', 'description': '当前代码目录内的测试脚本相对路径，Windows为.ps1，Linux为.sh'},
         'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 1200, 'default': 600}},
         'required': ['script'], 'additionalProperties': False}},
]


def script_command(rel, windows, timeout):
    cmd = ('powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' if windows else 'sh ') + rel
    remote_cmd = cmd
    if windows:
        # An SSH timeout alone leaves Windows children running. A remote watchdog
        # owns this script process tree and terminates it before SSH's deadline.
        token = uuid.uuid4().hex
        wrapper = """$ErrorActionPreference='Stop'
$o=Join-Path $env:TEMP 'tmh-%s.out';$e=Join-Path $env:TEMP 'tmh-%s.err'
$p=$null;$code=1
try {
 $p=Start-Process powershell.exe -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File','%s') -PassThru -RedirectStandardOutput $o -RedirectStandardError $e
 if($p.WaitForExit(%d)){ $p.WaitForExit();$code=$p.ExitCode } else { $code=124;taskkill /PID $p.Id /T /F | Out-Null;Write-Output 'TEST_TIMEOUT' }
} finally {
 if($p -and -not $p.HasExited){taskkill /PID $p.Id /T /F | Out-Null}
 foreach($f in @($o,$e)){if(Test-Path $f){Get-Content -Encoding UTF8 $f;Remove-Item $f -Force}}
}
exit $code
""" % (token, token, rel, timeout * 1000)
        remote_cmd = 'powershell -NoProfile -NonInteractive -EncodedCommand ' + base64.b64encode(wrapper.encode('utf-16-le')).decode()
    return remote_cmd


class Bridge:
    def __init__(self, data_dir, rid, workdir):
        self.data_dir, self.rid, self.workdir = Path(data_dir), int(rid), Path(workdir).resolve()
        self.store = Store(self.data_dir / 'platform.db')
        self.conf = testbox.settings(self.data_dir)
        if not self.conf:
            raise ValueError('尚未配置测试机')
        self.box = testbox.TestBox(self.conf, self.data_dir)

    def active(self):
        run = self.store.run(self.rid)
        if not run or run['status'] != 'running' or run['mode'] != 'fix' or Path(run['workdir']).resolve() != self.workdir:
            raise ValueError('当前运行已停止或工作目录不匹配，不能继续操作测试机')
        return run

    def call(self, name, args):
        run = self.active()
        key = 'run-%s-%s' % (hashlib.sha256(str(self.data_dir.resolve()).encode()).hexdigest()[:12], self.rid)
        if name == 'testbox_info':
            result = self.box.check()
            result['workdir'] = self.box.dir + '/work/' + key
            return result
        if name != 'testbox_run':
            raise ValueError('没有这个工具')
        script = args.get('script')
        timeout = args.get('timeout', 600)
        if not isinstance(script, str) or not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 1200:
            raise ValueError('脚本或超时时间不正确')
        path = (self.workdir / script).resolve()
        if not path.is_relative_to(self.workdir) or not path.is_file():
            raise ValueError('脚本必须是本次代码目录内的文件')
        rel = path.relative_to(self.workdir).as_posix()
        # Script paths are inserted into a remote shell command, never accept shell syntax.
        import re
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', rel):
            raise ValueError('测试脚本路径只支持英文字母、数字、点、横线、下划线和目录分隔符')
        windows = self.box._detect() == 'windows'
        if path.suffix != ('.ps1' if windows else '.sh'):
            raise ValueError('Windows需要.ps1脚本，Linux需要.sh脚本')
        if git(self.workdir, 'check-ignore', '--', rel, check=False).strip():
            raise ValueError('测试脚本被Git忽略，无法随代码同步')
        base, patch, fingerprint = snapshot(self.workdir)
        cmd = ('powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' if windows else 'sh ') + rel
        remote_cmd = script_command(rel, windows, timeout)
        folder = self.data_dir / 'runs'  / str(self.rid) / 'testbox'
        folder.mkdir(parents=True, exist_ok=True)
        receipt = {'id': uuid.uuid4().hex, 'run': self.rid, 'base': base, 'snapshot': fingerprint,
                   'script': rel, 'command': cmd, 'started': time.time(), 'state': 'running'}
        target = folder / (str(time.time_ns()) + '.json')
        import fcntl
        with (folder / 'execution.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('本轮测试机操作仍在执行，请等待回执') from exc
            target.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
            self.store.append_output(self.rid, '\n— 测试机执行：' + cmd + '\n')
            results = self.box.run(key, self.workdir, base, patch, [('test', remote_cmd)], timeout + 30)
        for result in results:
            if result['kind'] == 'test':
                result['command'] = cmd
        receipt.update(state='done', results=results, seconds=time.time()-receipt['started'],
                       stale=snapshot(self.workdir)[2] != fingerprint)
        target.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
        self.active()
        self.store.append_output(self.rid, '— 测试机返回：%s；回执 %s\n' %
                                ('通过' if not receipt['stale'] and all(x['exit_code'] == 0 for x in results) else '未通过', receipt['id']))
        return receipt


def latest_result(data_dir, rid, workdir):
    files = sorted((Path(data_dir) / 'runs' / str(rid) / 'testbox').glob('*.json'))
    if not files:
        return {'kind': 'test', 'command': '测试机运行验证', 'exit_code': 1, 'seconds': 0, 'tail': '尚未通过testbox_run执行本次版本的测试脚本', 'where': '测试机'}
    receipt = json.loads(files[-1].read_text(encoding='utf-8'))
    if receipt['state'] != 'done' or receipt['snapshot'] != snapshot(workdir)[2] or receipt.get('stale'):
        return {'kind': 'test', 'command': '测试机运行验证', 'exit_code': 1, 'seconds': 0, 'tail': '测试未完成或代码已变化，需要重新调用testbox_run', 'where': '测试机'}
    results = receipt['results']
    return {'kind': 'test', 'command': receipt['command'], 'exit_code': next((x['exit_code'] for x in results if x['exit_code']), 0),
            'seconds': receipt['seconds'], 'tail': '\n'.join(x['tail'] for x in results), 'where': '测试机', 'receipt': receipt['id']}


def serve(bridge):
    for line in sys.stdin:
        try:
            m = json.loads(line)
            if 'id' not in m:
                continue
            method, params = m['method'], m.get('params') or {}
            if method == 'initialize':
                result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'webuddy-testbox', 'version': '1.0'}}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                try:
                    value = bridge.call(params['name'], params.get('arguments') or {})
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': False}
                except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    result = {'content': [{'type': 'text', 'text': str(exc)}], 'isError': True}
            elif method == 'ping':
                result = {}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': m['id'], 'error': {'code': -32601, 'message': 'method not found'}}), flush=True)
                continue
            print(json.dumps({'jsonrpc': '2.0', 'id': m['id'], 'result': result}, ensure_ascii=False), flush=True)
        except (ValueError, KeyError, TypeError):
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'invalid request'}}), flush=True)


if __name__ == '__main__':
    serve(Bridge(*sys.argv[1:]))
