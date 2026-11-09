"""Install the versioned ERP verification sources into an operator-selected checkout."""
import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('checkout', type=Path)
args = parser.parse_args()
root = args.checkout.resolve()
source = Path(__file__).with_name('overlay')
if not (root / 'jshERP-boot/pom.xml').is_file():
    raise SystemExit('不是 jshERP 工作树')
for file in source.rglob('*'):
    if file.is_file():
        target = root / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
# Keep the real browser/database regression with the project that it verifies.
shutil.copytree(Path(__file__).with_name('business-proof'), root / '.webuddy-tests/business-proof', dirs_exist_ok=True)
# The old compiler configuration disables test compilation; execute the new tests.
pom = root / 'jshERP-boot/pom.xml'
text = pom.read_text(encoding='utf-8')
pom.write_text(text.replace('\t\t\t\t\t<skip>true</skip>\n', ''), encoding='utf-8')
# One amount is still a list of one amount, not a string to iterate character by character.
util = root / 'jshERP-web/src/utils/util.js'
raw = util.read_bytes()
newline = b'\r\n' if b'\r\n' in raw else b'\n'
old = "    if(str.indexOf(',')>-1) {\n      arr = str.split(',')\n    } else {\n      arr = str\n    }".encode().replace(b'\n', newline)
previous = b"    arr = str.split(',')"
new = b"    arr = Array.isArray(str) ? str : str.split(',')"
if old not in raw and previous not in raw and new not in raw:
    raise SystemExit('金额函数已变化，需核对补丁，未自动重写')
util.write_bytes(raw.replace(old, new).replace(previous, new))
ignore = root / '.gitignore'
text = ignore.read_text(encoding='utf-8')
for line in ('**/node_modules/', '**/dist/', '**/target/'):
    if line not in text.splitlines():
        text += '\n' + line + '\n'
ignore.write_text(text, encoding='utf-8')
print('ERP_TEST_SOURCES_INSTALLED', root)
