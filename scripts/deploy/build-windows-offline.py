"""Build an immutable Windows x64 runtime ZIP from a fixed Webuddy wheel and pinned official payloads."""
import argparse
import csv
from email.parser import BytesParser
import io
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from customer_audit import require_clean

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def payloads(lock, cache, offline):
    for name, row in lock.items():
        path = cache / row['filename']
        if not path.exists():
            if offline:
                raise ValueError('Missing cached payload: ' + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(path.suffix + '.partial')
            with urllib.request.urlopen(row['url'], timeout=120) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            if digest(partial) != row['sha256']:
                raise ValueError('Download checksum mismatch: ' + name)
            partial.rename(path)
        if digest(path) != row['sha256']:
            raise ValueError('Cached payload checksum mismatch: ' + name)
    return {name: cache / row['filename'] for name, row in lock.items()}


def unzip(archive, destination):
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            if not (destination / info.filename).resolve().is_relative_to(destination.resolve()):
                raise ValueError('Unsafe archive member: ' + info.filename)
        package.extractall(destination)


def check_windows_dependencies(archives):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    environment = dict(implementation_name='cpython', implementation_version='3.14.10',
                       os_name='nt', platform_machine='AMD64', platform_release='10',
                       platform_system='Windows', platform_version='10.0',
                       python_full_version='3.14.10', platform_python_implementation='CPython',
                       python_version='3.14', sys_platform='win32')
    metadata = {}
    for archive in archives:
        with zipfile.ZipFile(archive) as package:
            info = BytesParser().parsebytes(package.read(next(n for n in package.namelist() if n.endswith('.dist-info/METADATA'))))
        metadata[canonicalize_name(info['Name'])] = info
    extras = {'tmh-harness': {'mcp', 'server'}}
    changed = True
    while changed:
        changed = False
        for name, info in metadata.items():
            for requirement in info.get_all('Requires-Dist', []):
                r = Requirement(requirement)
                if r.marker and not any(r.marker.evaluate(dict(environment, extra=e)) for e in {'', *extras.get(name, set())}):
                    continue
                target = canonicalize_name(r.name)
                if target not in metadata or metadata[target]['Version'] not in r.specifier:
                    raise ValueError('Missing/incompatible Windows dependency: ' + name + ' -> ' + requirement)
                requested = set(r.extras) - extras.get(target, set())
                if requested:
                    extras.setdefault(target, set()).update(requested)
                    changed = True


def install_wheel(archive, packages, scripts):
    relocated = {}
    record = None
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split('/')
            if parts[0].endswith('.data'):
                if len(parts) < 3 or parts[1] != 'scripts':
                    raise ValueError('Unsupported wheel installation scheme: ' + info.filename)
                target = scripts.joinpath(*parts[2:])
                base = scripts
                relocated[info.filename] = '../../Scripts/' + '/'.join(parts[2:])
            else:
                target = packages / info.filename
                base = packages
            if not target.resolve().is_relative_to(base.resolve()) or target.exists():
                raise ValueError('Unsafe or duplicate wheel member: ' + info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(info))
            if info.filename.endswith('.dist-info/RECORD'):
                record = target
    if relocated:
        rows = list(csv.reader(io.StringIO(record.read_text(encoding='utf-8'))))
        for row in rows:
            row[0] = relocated.get(row[0], row[0])
        with record.open('w', encoding='utf-8', newline='') as output:
            csv.writer(output).writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wheel-release', type=Path, required=True, help='Directory from build-package.py')
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--sevenzip', default='7zz', help='7-Zip command or absolute executable path')
    p.add_argument('--cache-only', action='store_true', help='Forbid all downloads')
    p.add_argument('--out', type=Path, required=True, help='New output directory; never overwritten')
    args = p.parse_args()
    if args.out.exists():
        p.error('Output already exists; use a new directory')
    release = json.loads((args.wheel_release / 'release.json').read_text())
    if release.get('distribution') != 'customer':
        raise ValueError('A newly built customer wheel is required')
    def specification(name):
        return subprocess.check_output(['git', 'show', release['source_commit'] + ':scripts/deploy/windows-offline/' + name], cwd=HERE.parents[1])
    lock_bytes = specification('payloads.lock.json')
    lock = json.loads(lock_bytes)
    wheel = args.wheel_release / release['wheel']
    if digest(wheel) != release['sha256']:
        raise ValueError('Webuddy wheel checksum mismatch')
    files = payloads(lock, args.cache.resolve(), args.cache_only)
    with tempfile.TemporaryDirectory(prefix='webuddy-windows-') as temp:
        root = Path(temp) / 'Webuddy'
        root.mkdir()
        unzip(files['python'], root / 'runtime/python')
        for name in ('codex', 'claude'):
            destination = root / 'tools' / name
            destination.mkdir(parents=True)
            with tarfile.open(files[name]) as package:
                package.extractall(destination, filter='data')
        for name, filename in [('codex-wrapper', 'codex'), ('claude-code-wrapper', 'claude')]:
            destination = root / 'licenses' / filename
            destination.mkdir(parents=True)
            with tarfile.open(files[name]) as package:
                for member in package:
                    if member.isfile() and Path(member.name).name in ('README.md', 'LICENSE.md'):
                        (destination / Path(member.name).name).write_bytes(package.extractfile(member).read())
        shutil.copy2(files['codex-license'], root / 'licenses/codex/LICENSE')
        git = root / 'tools/git'
        subprocess.run([args.sevenzip, 'x', '-y', '-o' + str(git), str(files['git'])], check=True, stdout=subprocess.DEVNULL)
        unzip(files['node'], root / 'tools/node')
        packages = root / 'runtime/python/Lib/site-packages'
        wheels = [str(path) for key, path in files.items() if key.startswith('wheel:')]
        archives = [wheel, *map(Path, wheels)]
        check_windows_dependencies(archives)
        for archive in archives:
            install_wheel(archive, packages, root / 'runtime/python/Scripts')
        (root / 'runtime/python/python314._pth').write_text('python314.zip\n.\nLib/site-packages\nimport site\n', newline='\n')
        for filename in ('launcher.py', 'webuddy.cmd', 'start.cmd', 'check.cmd', 'config.example.json', 'README.txt'):
            (root / filename).write_bytes(specification(filename))
        (root / 'payloads.lock.json').write_bytes(lock_bytes)
        release.update(target='windows-x86_64', python=lock['python']['version'],
                       tools=dict(codex='tools/codex/package/vendor/x86_64-pc-windows-msvc/bin/codex.exe',
                                  claude='tools/claude/package/claude.exe', git='tools/git/cmd/git.exe',
                                  node='tools/node/node-' + lock['node']['version'] + '-win-x64/node.exe'))
        (root / 'release.json').write_text(json.dumps(release, indent=2) + '\n', newline='\n')
        manifest = {f.relative_to(root).as_posix(): digest(f) for f in sorted(root.rglob('*'), key=lambda p: p.relative_to(root).as_posix()) if f.is_file()}
        (root / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', newline='\n')
        args.out.mkdir(parents=True)
        archive = args.out / ('Webuddy-customer-windows-x64-' + release['source_commit'][:12] + '.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for file in sorted(root.rglob('*'), key=lambda p: p.relative_to(root).as_posix()):
                if file.is_file():
                    output.write(file, 'Webuddy/' + file.relative_to(root).as_posix())
        audit = require_clean(archive, release['resources'])
        (args.out / 'content-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
        receipt = dict(distribution='customer', source_commit=release['source_commit'], bundle=archive.name, sha256=digest(archive),
                       bytes=archive.stat().st_size, files=len(manifest), windows_validation='pending')
        (args.out / 'bundle.json').write_text(json.dumps(receipt, indent=2) + '\n')
        (args.out / 'README.txt').write_bytes(specification('README.txt'))
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
