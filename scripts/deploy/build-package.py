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
        paths = ['tmh', *resources['DIRECTORIES'], *resources['FILES']]
        archive = work / 'source.zip'
        with archive.open('wb') as output:
            subprocess.run(['git', 'archive', '--format=zip', commit, *paths], cwd=root,
                           stdout=output, check=True)
        source = work / 'source'
        with zipfile.ZipFile(archive) as package:
            package.extractall(source)
        wheels = work / 'wheels'
        subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels),
                        str(source)], check=True)
        wheel, = wheels.glob('*.whl')
        with zipfile.ZipFile(wheel) as package:
            for asset in ('tmh/platform/vendor/pele.global.js', 'tmh/platform/vendor/pele-LICENSE',
                          'tmh/platform/project_test_runner.cjs'):
                assert package.read(asset) == (source / asset).read_bytes(), asset
        manifest = dict(source_commit=commit, wheel=wheel.name,
                        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), bytes=wheel.stat().st_size)
        destination.mkdir(parents=True)
        shutil.copy2(wheel, destination / wheel.name)
        (destination / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(manifest, output=str(destination)), indent=2))


if __name__ == '__main__':
    main()
