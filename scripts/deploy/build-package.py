"""Build only canonical runtime sources from a fixed Git commit in a fresh directory."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import zipfile
from customer_audit import require_clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD', help='Fixed commit to package; working changes are excluded')
    parser.add_argument('--out', default='dist', help='Parent of the new commit-specific output directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options',
                                      args.ref + '^{commit}'], cwd=root, text=True).strip()
    destination = Path(args.out).resolve() / commit[:12]
    if destination.exists():
        raise SystemExit('Output already exists; keep it and choose a different --out: ' + str(destination))
    with tempfile.TemporaryDirectory(prefix='webuddy-package-') as folder:
        work = Path(folder)
        resource_code = subprocess.check_output(['git', 'show', commit + ':tmh/resources.py'], cwd=root)
        resource_file = work / 'resources.py'
        resource_file.write_bytes(resource_code)
        resources = runpy.run_path(str(resource_file))
        # Read Git blobs directly: archive attributes and host line-ending settings
        # must not change the customer source snapshot.
        entries = subprocess.check_output(['git', 'ls-tree', '-rz', commit], cwd=root).split(b'\0')
        tree = {}
        for entry in entries:
            if entry:
                header, name = entry.split(b'\t', 1)
                tree[name.decode('utf-8')] = header.split()
        import fnmatch
        paths = set(resources['FILES'])
        directories = {'tmh' if name == '.' else 'tmh/' + name for name in resources['PACKAGE_DIRECTORIES']}
        for name in tree:
            if name.endswith('.py') and str(Path(name).parent).replace('\\', '/') in directories:
                paths.add(name)
            if any(fnmatch.fnmatchcase(name, 'tmh/' + pattern) for pattern in resources['PACKAGE_ASSETS']):
                paths.add(name)
        source = work / 'source'
        for name in sorted(paths):
            mode, kind, blob = tree[name]
            if mode not in (b'100644', b'100755') or kind != b'blob':
                raise ValueError('Customer source must be a regular Git blob: ' + name)
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', 'cat-file', 'blob', blob.decode()], cwd=root))
            target.chmod(int(mode, 8))
        wheels = work / 'wheels'
        subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels),
                        str(source)], check=True)
        wheel, = wheels.glob('*.whl')
        with zipfile.ZipFile(wheel) as package:
            for asset in ('tmh/platform/vendor/pele.global.js', 'tmh/platform/vendor/pele-LICENSE',
                          'tmh/platform/project_test_runner.cjs'):
                assert package.read(asset) == (source / asset).read_bytes(), asset
        audit = require_clean(wheel, resources['FILES'])
        manifest = dict(source_commit=commit, distribution='customer', resources=list(resources['FILES']), wheel=wheel.name,
                        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), bytes=wheel.stat().st_size)
        destination.mkdir(parents=True)
        shutil.copy2(wheel, destination / wheel.name)
        (destination / 'content-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
        (destination / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(manifest, output=str(destination)), indent=2))


if __name__ == '__main__':
    main()
