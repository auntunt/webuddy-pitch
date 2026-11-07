"""Content identity of indexed source; never infer an old index from current HEAD."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .fsutil import iter_files, rel


def snapshot(root):
    files={}
    for p in iter_files(root):
        if p.is_symlink() or not p.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('索引源码包含符号链接，不能核对项目内来源：'+rel(root,p))
        files[rel(root,p)]=p.read_bytes()
    return files


def digest(files):
    return hashlib.sha256(json.dumps({p:hashlib.sha256(b).hexdigest() for p,b in sorted(files.items())},sort_keys=True).encode()).hexdigest()


def metadata(root, files):
    def git(*args):
        try:
            result=subprocess.run(['git','-C',str(root),*args],capture_output=True,timeout=15)
            return result.stdout.decode().strip() if result.returncode==0 else None
        except (OSError,subprocess.SubprocessError):
            return None
    head=git('rev-parse','--verify','HEAD') or ''
    dirty=git('status','--porcelain','--untracked-files=all','--','.',':(exclude).tmh')
    content=digest(files)
    parser=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
    return {'source_version':head if head and dirty=='' else 'snapshot:'+content,'git_commit':head,
            'snapshot_sha256':content,'parser_version':parser,'generated_at':datetime.now(timezone.utc).isoformat(),
            'index_revision':hashlib.sha256((content+parser).encode()).hexdigest(),
            'scope':'repository text candidates; build/VCS/cache directories excluded', 'file_count':len(files)}
