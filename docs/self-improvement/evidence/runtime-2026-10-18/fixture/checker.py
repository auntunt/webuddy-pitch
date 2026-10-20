import sys,time,os,signal,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
mode=sys.argv[1]
print("SYNTHETIC local checker, not a model or customer approval",flush=True)
if mode != 'fix':
 print('No model action'); sys.exit(0)
p=Path('app.py'); before=p.read_text(); print('Before: '+before,flush=True)
if 'VALUE = 0' in before:
 p.write_text('VALUE = 1\n')
 Path('retained-note.txt').write_text('SYNTHETIC partially completed work, retain on retry\n')
 print('Partial edit retained; starting an owned child that ignores TERM',flush=True)
 child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
 (root/'child.pid').write_text(str(child.pid))
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 while True: time.sleep(1)
assert 'VALUE = 1' in before and Path('retained-note.txt').exists(), 'Recovery lost code'
p.write_text('VALUE = 2\n')
print('Recovery read VALUE=1 and retained-note.txt, then completed VALUE=2',flush=True)
