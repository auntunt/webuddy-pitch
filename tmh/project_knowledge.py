"""Build a versioned, local knowledge snapshot without executing project code.

This worker is launched by the platform's process supervisor. Git objects, not
checkout filters or archive attributes, define the source. Each finished phase
has an atomic checkpoint; the immutable publication is owned by the caller.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import time

FORMAT = 1
SECRET_SUFFIXES = {'.key', '.pem', '.p12', '.pfx', '.crt', '.cer', '.jks', '.keystore'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def atomic(path, value):
    import uuid
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def safe_path(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('无效的相对路径')
    path = PurePosixPath(name)
    if path.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')) or ':' in name:
        raise ValueError('路径必须是来源内的相对路径')
    if any(x.casefold() == '.git' for x in path.parts):
        raise ValueError('不能读取 Git 元数据')
    return path


def excluded(name):
    p = PurePosixPath(name)
    parts = [x.casefold() for x in p.parts]
    if p.suffix.casefold() in SECRET_SUFFIXES or p.name.casefold() in {'id_rsa', 'id_ed25519', 'id_ecdsa', '.env'} or p.name.casefold().startswith('.env.'):
        return '凭据或证书文件不进入知识库'
    if any(x in ('secrets', 'credentials', '.ssh') for x in parts):
        return '凭据目录不进入知识库'
    if len(parts) > 1 and parts[0] == '.tmh' and parts[1] in ('cache', 'tool'):
        return '派生缓存/工具不作为源知识读取'
    return ''


def git_env():
    # A caller's worktree/index/config overrides must not change the chosen
    # source; a partial clone must never turn a local read into a network fetch.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='',
               GIT_NO_REPLACE_OBJECTS='1', GIT_ATTR_NOSYSTEM='1', GIT_OPTIONAL_LOCKS='0')
    return env


def git(repo, *args, raw=False, timeout=60, input=None):
    r = subprocess.run(['git', '--no-pager', '-c', 'core.fsmonitor=false', '-C', str(repo), *args],
                       capture_output=True, timeout=timeout, env=git_env(), input=input)
    if r.returncode:
        raise ValueError('Git 读取失败：' + r.stderr.decode('utf-8', 'replace'))
    return r.stdout if raw else r.stdout.decode('utf-8', 'strict').strip()


def analyzer_version():
    root = Path(__file__).parent
    names = sorted(p.name for p in root.glob('*.py'))
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})


def verify_files(root, manifest):
    for name, entry in manifest.items():
        path = Path(root).joinpath(*safe_path(name).parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('快照文件缺失或路径变化：' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('快照文件内容变化：' + name)


def export(repo, commit, root, folder):
    entries, ignored = [], []
    for record in git(repo, 'ls-tree', '-rz', '--full-tree', commit, raw=True).split(b'\0'):
        if not record:
            continue
        meta, filename = record.split(b'\t', 1)
        mode, kind, oid = meta.split()
        name = filename.decode('utf-8', 'strict')
        safe_path(name)
        reason = excluded(name)
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            reason = '符号链接/子模块/特殊文件尚不支持，未跟随读取'
        if reason:
            ignored.append({'path': name, 'reason': reason})
        else:
            entries.append((name, oid, mode))
    # Spool rather than materializing every repository blob in Python memory.
    with (folder / 'objects.bin').open('w+b') as spool:
        proc = subprocess.run(['git', '-C', str(repo), 'cat-file', '--batch'],
                              input=b''.join(oid + b'\n' for _, oid, _ in entries),
                              stdout=spool, stderr=subprocess.PIPE, timeout=180, env=git_env())
        if proc.returncode:
            raise ValueError(proc.stderr.decode('utf-8', 'replace'))
        spool.seek(0)
        manifest = {}
        root.mkdir(parents=True, exist_ok=True)
        folded = set()
        for name, oid, mode in entries:
            if name.casefold() in folded:
                raise ValueError('当前快照存储不支持仅大小写不同的路径：' + name)
            folded.add(name.casefold())
            header = spool.readline().split()
            if len(header) != 3 or header[0] != oid or header[1] != b'blob':
                raise ValueError('源对象与固定版本不一致：' + name)
            data = spool.read(int(header[2]))
            if len(data) != int(header[2]) or spool.read(1) != b'\n':
                raise ValueError('源对象不完整：' + name)
            path = root.joinpath(*safe_path(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                raise ValueError('拒绝写入符号链接：' + name)
            path.write_bytes(data)
            path.chmod(0o755 if mode == b'100755' else 0o644)
            manifest[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'blob': oid.decode(),
                              'size': len(data), 'mode': mode.decode()}
        if spool.read(1):
            raise ValueError('Git 输出包含未绑定的数据')
    (folder / 'objects.bin').unlink()
    return manifest, ignored


def make_index(root, original, path, manifest):
    from .context import terms
    from .fsutil import is_text_candidate, read_text, SKIP_DIRS
    from .graph import Graph
    from . import kb
    db = sqlite3.connect(path)
    unindexed, count = [], 0
    try:
        db.executescript('DROP TABLE IF EXISTS documents; DROP TABLE IF EXISTS terms; '
                        'CREATE TABLE documents(id INTEGER PRIMARY KEY,kind TEXT,title TEXT,path TEXT,line INT,body TEXT); '
                        'CREATE TABLE terms(term TEXT,doc_id INT, PRIMARY KEY(term,doc_id));')

        def add(kind, title, name, line, body):
            nonlocal count
            cur = db.execute('INSERT INTO documents(kind,title,path,line,body) VALUES(?,?,?,?,?)', (kind, title, name, line, body))
            db.executemany('INSERT INTO terms VALUES(?,?)', ((t, cur.lastrowid) for t in set(terms(title + ' ' + name + ' ' + body))))
            count += 1

        for name in manifest:
            path = original / name
            if any(x in SKIP_DIRS or x.startswith('.') for x in PurePosixPath(name).parts[:-1]):
                unindexed.append({'path': name, 'reason': '生成目录/隐藏目录，仅保留原文，不作为代码正文索引'})
                continue
            body = read_text(path) if is_text_candidate(path) else None
            if body is None:
                unindexed.append({'path': name, 'reason': '二进制、未支持编码/类型或超过解析单文件上限；原始字节保留'})
                continue
            add('document' if path.suffix.lower() in ('.md', '.txt', '.rst') else 'source', name, name, 1, body)
        g = Graph(root)
        try:
            for n in g.nodes():
                if n['file'] and n['file'] in manifest and n['kind'] in ('fn', 'cls', 'flow', 'ep', 'tbl'):
                    add(n['kind'], n['label'] or n['name'], n['file'], n['line'], json.dumps(n['data'], ensure_ascii=False))
        finally:
            g.db.close()
        for name, record in kb.load_registry(root).items():
            p = kb.page_path(root, name)
            if p.is_file():
                add('knowledge', record.get('title') or name, '@knowledge/' + p.relative_to(kb.kdir(root)).as_posix(), 1, p.read_text(encoding='utf-8'))
        db.execute('CREATE INDEX doc_path ON documents(path)')
        db.commit()
    finally:
        db.close()
    return count, unindexed


def build(folder):
    """Only a supervisor launches this function; no user-supplied command runs."""
    from . import kb
    from .config import load
    folder = Path(folder).resolve()
    request = json.loads((folder / 'request.json').read_text())
    actual_analyzer = analyzer_version()
    if request['analyzer'] != actual_analyzer:
        raise ValueError('分析器与固定输入不一致，请新建知识版本')
    original, root = folder / 'source', folder / 'analysis'
    checkpoint = folder / 'checkpoint.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if state and state.get('identity') != digest(request):
        raise ValueError('构建检查点不属于本次固定输入')
    state['identity'] = digest(request)
    started = time.monotonic()

    def save(stage, **values):
        state.update(stage=stage, **values)
        atomic(checkpoint, state)
        print(stage, flush=True)

    if not state.get('exported'):
        save('export')
        if original.exists():
            shutil.rmtree(original)
        manifest, ignored = export(request['root'], request['commit'], original, folder)
        if any(name.casefold() == '@knowledge' or name.casefold().startswith('@knowledge/') for name in manifest):
            raise ValueError('来源使用保留命名空间 @knowledge，无法无歧义发布')
        atomic(folder / 'source-manifest.json', manifest)
        save('exported', exported=True, excluded=ignored)
    manifest = json.loads((folder / 'source-manifest.json').read_text())
    verify_files(original, manifest)
    if analyzer_version() != actual_analyzer:
        raise ValueError('构建期间分析器发生变化，拒绝发布')
    if not state.get('analyzed'):
        save('analyze')
        # Generated facts never overwrite the exact Git originals. An
        # interrupted analysis restarts this phase from those originals.
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(original, root)
        # Copy only the trusted previous parser DB, never its registry or human decisions.
        previous = request.get('previous_cache')
        cache = root / '.tmh/cache/parse.db'
        if previous and not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(Path(previous).as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(cache)) as dst:
                src.backup(dst)
                # Across snapshots, identical stat metadata is not evidence
                # of identical content; force ParseCache's content-hash path.
                dst.execute("UPDATE entries SET stat='' ")
                dst.commit()
        result = kb.build(root)
        save('analyzed', analyzed=True, analysis=result, configuration_hash=digest(load(root)))
    save('index')
    count, unindexed = make_index(root, original, folder / 'index.db', manifest)
    # kb.build refreshes committed knowledge pages as well; code evidence must
    # retain the exact original bytes. Keep the generated KB separately.
    knowledge = {}
    for p in (root / '.tmh/knowledge').rglob('*'):
        if p.is_file():
            knowledge['@knowledge/' + p.relative_to(kb.kdir(root)).as_posix()] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size}
    verify_files(original, manifest)
    summary = {'files': len(manifest), 'excluded': len(state['excluded']), 'indexed': count,
               'seconds': round(time.monotonic() - started, 3), 'analysis': state['analysis'],
               'unindexed': unindexed, 'exclusions': state['excluded']}
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        summary['peak_rss_bytes'] = rss if sys.platform == 'darwin' else rss * 1024
    except (ImportError, AttributeError):
        # Windows has no `resource` module; the snapshot stays valid, only the
        # peak-memory field is unknown. Missing measurement must not fail a build.
        summary['peak_rss_bytes'] = None
        summary['peak_rss_note'] = '当前平台不提供 peak RSS 计量（resource 模块不可用）'
    summary['history'] = '静态快照不读取来源 Git 历史；churn 不作为知识证据'
    if analyzer_version() != actual_analyzer:
        raise ValueError('构建期间分析器发生变化，拒绝发布')
    result = {'schema': FORMAT, 'commit': request['commit'], 'analyzer': actual_analyzer,
              'configuration_hash': state['configuration_hash'], 'source_manifest': manifest,
              'knowledge_manifest': knowledge, 'original': original.name, 'summary': summary,
              'index_sha256': hashlib.sha256((folder / 'index.db').read_bytes()).hexdigest()}
    result['digest'] = digest(result)
    atomic(folder / 'result.json', result)
    save('complete')


if __name__ == '__main__':
    build(sys.argv[1])
