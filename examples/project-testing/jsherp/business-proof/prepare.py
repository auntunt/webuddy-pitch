"""Build and bind the isolated ERP runtime before executing its browser regression."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def output(args):
    return subprocess.check_output(args, text=True).strip()

def identity():
    run(['git', 'add', '-A', '-N', '.'])
    patch = subprocess.check_output(['git', 'diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD'])
    return output(['git', 'rev-parse', 'HEAD']) + ':' + hashlib.sha256(patch).hexdigest()

initial = identity()
folder = root / 'target/business'
folder.mkdir(parents=True, exist_ok=True)
settings = folder / 'maven-settings.xml'
settings.write_text('<settings><mirrors><mirror><id>central-release</id><mirrorOf>*</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>')
# The named MySQL/Redis containers are the dedicated fixtures described in README.md.
for name in ('webuddy-erp-mysql', 'webuddy-erp-redis'):
    assert output(['docker', 'inspect', '--format', '{{.State.Running}}', name]) == 'true', name
run(['docker', 'run', '--rm', '--name', 'webuddy-erp-build-verified', '--network', 'webuddy-erp-proof', '-v', str(root)+':/workspace', '-v', 'webuddy-erp-maven-cache:/root/.m2', '-v', str(settings)+':/tmp/settings.xml:ro', '-w', '/workspace', 'maven:3.9-eclipse-temurin-8', 'mvn', '-s', '/tmp/settings.xml', '-B', '-f', 'jshERP-boot/pom.xml', '-Dmaven.test.failure.ignore=false', '-DfailIfNoTests=true', 'package'])
run(['npm', 'run', 'build'], cwd=root/'jshERP-web')
assert identity() == initial, 'Source changed during build'
jar = root / 'jshERP-boot/target/jshERP.jar'
existing = subprocess.run(['docker', 'inspect', 'webuddy-erp-app'], capture_output=True, text=True)
if existing.returncode == 0:
    mounts = json.loads(existing.stdout)[0]['Mounts']
    assert any(m['Destination']=='/app/jshERP.jar' and Path(m['Source']).resolve()==jar.resolve() for m in mounts), 'Existing app is not this isolated checkout'
    run(['docker', 'stop', 'webuddy-erp-app'])
    run(['docker', 'rm', 'webuddy-erp-app'])
container = output(['docker', 'run', '-d', '--name', 'webuddy-erp-app', '--network', 'webuddy-erp-proof', '-p', '127.0.0.1:19999:9999', '-v', str(jar)+':/app/jshERP.jar:ro', '-e', 'TZ=Asia/Shanghai', '-e', 'SPRING_DATASOURCE_URL=jdbc:mysql://webuddy-erp-mysql:3306/jsh_erp?useUnicode=true&characterEncoding=utf8&allowMultiQueries=true&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai', '-e', 'SPRING_DATASOURCE_USERNAME=root', '-e', 'SPRING_DATASOURCE_PASSWORD=webuddy-isolated-test', '-e', 'SPRING_REDIS_HOST=webuddy-erp-redis', '-e', 'SPRING_REDIS_PASSWORD=webuddy-isolated-test', 'maven:3.9-eclipse-temurin-8', 'java', '-Duser.timezone=Asia/Shanghai', '-Xmx768m', '-jar', '/app/jshERP.jar'])
(folder/'build.json').write_text(json.dumps({'source':initial, 'container':container, 'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(), 'index_sha256':hashlib.sha256((root/'jshERP-web/dist/index.html').read_bytes()).hexdigest()},indent=2))
print('ERP_RUNTIME_BOUND', initial)
