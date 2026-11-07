import sys,hashlib,xml.etree.ElementTree as E,json,urllib.error
from pathlib import Path
sys.path.insert(0,'/tmp');from webuddy_demo_http import api,ROOT
try:api('/job/erp-verification/config.xml',reader=True)
except urllib.error.HTTPError as e:assert e.code==403;reader_status=e.code
else:raise AssertionError('reader unexpectedly reads job configuration')
raw,_=api('/job/erp-verification/config.xml')
x=E.fromstring(raw);script=x.find('definition/script').text
assert script==Path('examples/project-testing/jsherp/jenkins-demo/Jenkinsfile').read_text()
p=ROOT/'proof/git-workflow-20261107';(p/'job-definition.xml').write_bytes(raw)
(p/'controller.json').write_text(json.dumps({'script_sha256':hashlib.sha256(script.encode()).hexdigest(),'matches_versioned_jenkinsfile':True,'reader_configuration_status':reader_status,'configuration_read_actor':'isolated Jenkins administrator'},indent=2))
print('ACTUAL_JENKINS_DEFINITION_MATCH; reader configuration denied 403')
