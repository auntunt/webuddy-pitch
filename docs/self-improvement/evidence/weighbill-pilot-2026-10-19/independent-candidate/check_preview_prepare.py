"""Verify the synthetic preview launcher exclusively in temporary directories."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import traceback

sys.dont_write_bytecode=True
repo=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
sys.path.insert(0,str(repo))
from fastapi.testclient import TestClient
from weighbill.http_api import create_app
from weighbill.ports import RecordQuery
spec=importlib.util.spec_from_file_location('independent_preview',repo/'tools/webuddy_preview.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PREFIX='/pv/INDEPENDENT-2/__commit/'+'c'*40
results=[]

def tree(p):
    return {str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}
def run(name,fn):
    with tempfile.TemporaryDirectory(prefix='wb-preview-independent-') as tmp:
        try: detail=fn(Path(tmp));r={'name':name,'passed':True,'detail':detail}
        except Exception:r={'name':name,'passed':False,'traceback':traceback.format_exc()}
    results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)

def new_and_restart(root):
    p=root/'dedicated';svc=m.prepare(p,PREFIX);records=svc.store.query(RecordQuery(limit=None));assert len(records)==3
    marker=json.loads((p/'webuddy-preview.json').read_text());assert marker['ocr_available'] is False
    assert svc.vision.describe()['configured'] is False
    client=TestClient(create_app(svc));record=records[0]
    r=client.patch(PREFIX+'/api/v1/records/'+record.id,json={'expected_version':record.version,'fields':{'备注':'retained on restart'}},headers={'X-Portal-User':'reviewer-A'})
    assert r.status_code==200,r.text
    histories={x.id:svc.history(x.id) for x in records};view=svc.record_view(svc.get(record.id))
    checked=[]
    for item in marker['records']:
        raw=client.get(PREFIX+'/files/'+item['original_key']);assert raw.status_code==200
        assert len(raw.content)==item['bytes'] and hashlib.sha256(raw.content).hexdigest()==item['original_sha256']
        checked.append({'id':item['id'],'bytes':len(raw.content),'sha256':hashlib.sha256(raw.content).hexdigest()})
    marker_before=(p/'webuddy-preview.json').read_bytes();client.close()
    restarted=m.prepare(p,PREFIX)
    assert restarted.record_view(restarted.get(record.id))==view
    assert {x.id:restarted.history(x.id) for x in records}==histories
    assert (p/'webuddy-preview.json').read_bytes()==marker_before
    assert len(restarted.store.query(RecordQuery(limit=None)))==3
    assert restarted.vision.calls==[]
    return {'saved_response':r.json(),'marker':marker,'raw_images_verified':checked,'same_record_and_history_after_restart':True,'vision_calls':restarted.vision.calls}

def reject_nonpreview(root):
    p=root/'occupied';p.mkdir();(p/'sentinel-business-like.txt').write_text('synthetic sentinel: must remain identical')
    before=tree(p)
    try:m.prepare(p,PREFIX)
    except ValueError as e:reason=str(e)
    else:raise AssertionError('accepted existing non-preview directory')
    assert tree(p)==before
    return {'rejection':reason,'unchanged_files':before}

def reject_symlink(root):
    target=root/'target';target.mkdir();(target/'sentinel').write_text('untouched');alias=root/'alias';alias.symlink_to(target,target_is_directory=True)
    before=tree(target)
    try:m.prepare(alias,PREFIX)
    except ValueError as e:reason=str(e)
    else:raise AssertionError('accepted symlink data directory')
    assert tree(target)==before
    return {'rejection':reason,'unchanged_files':before}

def reject_marker(root):
    p=root/'wrong-marker';p.mkdir();(p/'webuddy-preview.json').write_text('{"kind":"something-else"}')
    before=tree(p)
    try:m.prepare(p,PREFIX)
    except ValueError as e:reason=str(e)
    else:raise AssertionError('accepted incorrect marker')
    assert tree(p)==before
    return {'rejection':reason,'unchanged_files':before}

for name,fn in [('new_synthetic_originals_and_restart',new_and_restart),('existing_nonpreview_rejected',reject_nonpreview),('symlink_root_rejected',reject_symlink),('incorrect_marker_rejected',reject_marker)]:run(name,fn)
report={'scope':'dedicated TemporaryDirectory only; no original project data or config accessed',
        'source_sha256':hashlib.sha256((repo/'tools/webuddy_preview.py').read_bytes()).hexdigest(),
        'passed':sum(x['passed'] for x in results),'total':len(results),'results':results}
(out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
raise SystemExit(0 if all(x['passed'] for x in results) else 1)
