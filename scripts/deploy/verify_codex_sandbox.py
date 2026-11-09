"""Offline checks of Codex's real Linux sandbox; no model or business data."""
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile


def verify():
    with tempfile.TemporaryDirectory(prefix='webuddy-sandbox-check-', dir=Path.home()) as folder:
        root = Path(folder)
        work, home = root / 'workspace', root / 'codex'
        work.mkdir()
        home.mkdir()
        (home / 'config.toml').write_text('[permissions.inspect]\nextends = ":read-only"\n'
                                        '[permissions.change]\nextends = ":workspace"\n')
        env = dict(os.environ, CODEX_HOME=str(home))
        source = work / 'input.txt'
        source.write_text('SANDBOX_INPUT')
        outside = root / 'outside.txt'
        outside.write_text('OUTSIDE_UNCHANGED')
        (work / 'escape').symlink_to(outside)
        subprocess.run(['git', 'init', '-q', str(work)], check=True)
        git_config = work / '.git/config'
        original_git = git_config.read_bytes()
        results = []

        def run(name, profile, code):
            result = subprocess.run(['codex', 'sandbox', '-P', profile, '-C', str(work), '--',
                                     'python3', '-c', code], env=env, capture_output=True, text=True, timeout=30)
            if result.returncode or result.stdout.strip() != 'CHECK_OK':
                raise RuntimeError(f'{name}: exit={result.returncode}\n{result.stdout}\n{result.stderr}')
            results.append(name)

        run('read_input', 'inspect', "from pathlib import Path; assert Path('input.txt').read_text()=='SANDBOX_INPUT'; print('CHECK_OK')")
        run('workspace_write', 'change', "from pathlib import Path; Path('output.txt').write_text('WORKSPACE_OK'); print('CHECK_OK')")
        assert (work / 'output.txt').read_text() == 'WORKSPACE_OK'
        for name, profile, path in [('readonly_write_denied', 'inspect', source),
                                    ('outside_write_denied', 'change', outside),
                                    ('symlink_escape_denied', 'change', work / 'escape'),
                                    ('git_metadata_write_denied', 'change', git_config)]:
            run(name, profile, f'''from pathlib import Path
try:
    Path({str(path)!r}).write_text('MUST_NOT_WRITE')
except OSError as error:
    assert error.errno in ({errno.EACCES},{errno.EPERM},{errno.EROFS}), error
else:
    raise AssertionError('write escaped sandbox')
print('CHECK_OK')''')
        assert source.read_text() == 'SANDBOX_INPUT'
        assert outside.read_text() == 'OUTSIDE_UNCHANGED'
        assert git_config.read_bytes() == original_git
        for family, address, name in [(socket.AF_INET, ('127.0.0.1', 0), 'tcp_network_denied'),
                                      (socket.AF_UNIX, str(root / 'listener.sock'), 'unix_socket_denied')]:
            with socket.socket(family) as listener:
                listener.bind(address)
                listener.listen(4)
                destination = listener.getsockname()
                with socket.socket(family) as control:
                    control.connect(destination)
                run(name, 'change', f'''import socket
try:
    with socket.socket({int(family)}) as client:
        client.settimeout(1)
        client.connect({destination!r})
except OSError:
    pass
else:
    raise AssertionError('network escaped sandbox')
print('CHECK_OK')''')
        run('unprivileged_and_seccomp_active', 'change', "from pathlib import Path; s=Path('/proc/self/status').read_text(); d=dict(line.split(':',1) for line in s.splitlines() if ':' in line); assert int(d['CapEff'].strip(),16)==0; assert d['Seccomp'].strip()=='2'; print('CHECK_OK')")
        print(json.dumps({'passed': len(results), 'checks': results}, ensure_ascii=False))


if __name__ == '__main__':
    verify()
