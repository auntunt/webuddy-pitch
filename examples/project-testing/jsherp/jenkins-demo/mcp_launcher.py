"""Read-only MCP for this local synthetic demo; not a customer credential setup."""
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
accounts = json.loads((root / 'private/accounts.json').read_text())
repo = Path(__file__).resolve().parents[4]
env = dict(os.environ, WEBUDDY_TOKEN=accounts['reader_password'], PYTHONPATH=str(repo))
os.execve(sys.executable, [sys.executable, '-m', 'tmh.workbench', 'mcp', '--endpoint',
          'http://127.0.0.1:18985', '--agent', 'erp-demo-reader', '--read-only'], env)
