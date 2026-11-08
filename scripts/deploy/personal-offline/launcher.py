"""Owner-only AI profile bootstrap. Existing Cursor and global client homes are untouched."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def restrict(folder):
    if os.name == 'nt':
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-Command',
            '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], capture_output=True, text=True, check=True)
        sid = result.stdout.strip()
        if not re.fullmatch(r'S-1-(?:\d+-)+\d+', sid):
            raise ValueError('Cannot determine current Windows account SID')
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r',
            '*'+sid+':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '/T', '/Q'], capture_output=True, check=True)
    else:
        folder.chmod(0o700)


def prepare(root, local):
    manifest = json.loads((root/'PERSONAL.json').read_text(encoding='utf-8'))
    profile_id = manifest['profile_id']
    if not re.fullmatch(r'[a-f0-9]{32}', profile_id):
        raise ValueError('Invalid personal profile identity')
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Missing or unsafe personal package file')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Personal package integrity check failed: '+name)
    destination = local/'Webuddy'/'personal-ai'/profile_id
    ready = destination/'READY.json'
    if not ready.exists():
        if destination.exists():
            raise ValueError('Incomplete AI profile exists; preserve it and inspect before retrying')
        destination.mkdir(parents=True, mode=0o700)
        restrict(destination)
        for source in (root/'profiles').rglob('*'):
            if source.is_file():
                target = destination/source.relative_to(root/'profiles')
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(source, target)
                if os.name != 'nt':
                    target.chmod(0o600)
        environment = json.loads((destination/'environment.json').read_text(encoding='utf-8'))
        environment.update(CODEX_HOME=str(destination/'codex'), CLAUDE_CONFIG_DIR=str(destination/'claude'))
        # No HOME, APPDATA or CURSOR_* override: use the target device's Cursor login.
        config = destination/'runtime-config.json'
        config.write_text(json.dumps({'environment':environment}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        ready.write_text(json.dumps({'profile_id':profile_id,'cursor':'reuse_target_device_login'})+'\n', encoding='utf-8')
        if os.name != 'nt':
            config.chmod(0o600)
            ready.chmod(0o600)
    if json.loads(ready.read_text(encoding='utf-8'))['profile_id'] != profile_id:
        raise ValueError('AI profile identity mismatch')
    return destination/'runtime-config.json'


def main():
    if os.name != 'nt':
        raise ValueError('This personal runtime supports Windows x64 only')
    root = Path(__file__).resolve().parent
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
    config = prepare(root, local)
    argv = sys.argv[1:] or ['start']
    if argv[0] not in ('start','check','tool'):
        raise ValueError('Use start, check, or tool <name> <arguments>')
    env = os.environ.copy()
    # The private profile selects AI credentials, while business data keeps its existing default/environment.
    if env.get('WEBUDDY_CONFIG'):
        existing = json.loads(Path(env['WEBUDDY_CONFIG']).read_text(encoding='utf-8-sig'))
        private = json.loads(config.read_text(encoding='utf-8'))
        existing['environment'] = dict(existing.get('environment',{}), **private['environment'])
        merged = config.with_name('merged-runtime-config.json')
        merged.write_text(json.dumps(existing, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        config = merged
    program = root/'program'/'Webuddy'
    return subprocess.call([str(program/'runtime/python/python.exe'), '-B', str(program/'launcher.py'),
                           '--config', str(config), *argv], cwd=program, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError):
        # Do not print auth file contents, provider URLs, credentials or native subprocess output.
        print('Personal startup failed. Check program integrity, private profile permissions and external configuration.', file=sys.stderr)
        raise SystemExit(1)
