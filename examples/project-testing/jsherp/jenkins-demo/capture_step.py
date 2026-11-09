"""Capture one operator-issued command without a shell; not an acceptance verdict."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', required=True)
    parser.add_argument('--actor', required=True, help='Operator label, not authenticated identity')
    parser.add_argument('--actor-type', choices=['human', 'agent'], required=True)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or args.timeout <= 0:
        parser.error('a command and a positive timeout are required')
    now = lambda: datetime.now(timezone.utc).isoformat()
    folder = args.output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    record = {'schema': 1, 'label': args.label, 'actor': args.actor, 'actor_type': args.actor_type,
              'identity_verified': False, 'method': 'terminal_command', 'started_at': now(),
              'cwd': str(Path.cwd()), 'command': command, 'state': 'running', 'acceptance': False}
    receipt = folder / 'step.json'
    receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    code = 1
    try:
        with (folder / 'stdout.bin').open('wb') as stdout, (folder / 'stderr.bin').open('wb') as stderr:
            try:
                result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout, check=False)
                code = result.returncode
                record.update(state='completed', exit_code=code)
            except subprocess.TimeoutExpired:
                code = 124
                record.update(state='timeout', exit_code=None)
            except OSError as error:
                record.update(state='launch_failed', exit_code=None, error=str(error))
    finally:
        record['ended_at'] = now()
        record['artifacts'] = {name: {'bytes': (folder/name).stat().st_size,
            'sha256': hashlib.sha256((folder/name).read_bytes()).hexdigest()}
            for name in ('stdout.bin','stderr.bin') if (folder/name).exists()}
        receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(folder)
    return code


if __name__ == '__main__':
    sys.exit(main())
