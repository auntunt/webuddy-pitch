"""Read-only MCP for this local synthetic demo; not a customer credential setup."""
import argparse
import json
import os
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('root',type=Path)
parser.add_argument('--port',type=int,default=18985)
args=parser.parse_args()
if not 1 <= args.port <= 65535:parser.error('invalid port')
root=args.root.resolve()
accounts = json.loads((root / 'private/accounts.json').read_text())
repo = Path(__file__).resolve().parents[4]
env = dict(os.environ, WEBUDDY_TOKEN=accounts['reader_password'], PYTHONPATH=str(repo))
os.execve(sys.executable, [sys.executable, '-m', 'tmh.workbench', 'mcp', '--endpoint',
          'http://127.0.0.1:'+str(args.port), '--agent', 'erp-demo-reader', '--read-only'], env)
