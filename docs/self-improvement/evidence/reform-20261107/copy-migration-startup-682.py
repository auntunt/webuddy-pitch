import hashlib,json,shutil,sqlite3,sys,tempfile
from pathlib import Path
source=Path(sys.argv[1]);sys.path.insert(0,str(source))
from tmh.platform.store import Store
from tmh.platform import reform
from tmh.platform.development import schema

def content(db):
    result={}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        quoted='"'+name.replace('"','""')+'"'
        rows=sorted(json.dumps(list(r),sort_keys=True,default=lambda b:b.hex() if isinstance(b,bytes) else str(b)) for r in db.execute('SELECT * FROM '+quoted))
        result[name]=(len(rows),hashlib.sha256('\n'.join(rows).encode()).hexdigest())
    return result

report=[]
for live in Path('/opt/webuddy/data').rglob('*.db'):
    with tempfile.TemporaryDirectory(prefix='reform-migration-copy-') as tmp:
        root=Path(tmp);target=root/'platform.db'
        src=sqlite3.connect('file:'+str(live)+'?mode=ro',uri=True)
        dest=sqlite3.connect(target);src.backup(dest);src.close()
        assert dest.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        before=content(dest);dest.close()
        if live.name!='platform.db':
            report.append({'database':str(live.relative_to('/opt/webuddy/data')),'integrity':'ok','migration':'not_platform'})
            continue
        originals={}
        folder=live.parent/'reforms'
        if folder.exists():
            (root/'reforms').mkdir()
            for f in folder.glob('*.json'):
                data=f.read_bytes();(root/'reforms'/f.name).write_bytes(data);originals[f.stem]=data
        st=Store(target);schema(st);reform.initialize(root,st)
        plans=0;links=0
        for key,raw in originals.items():
            old=json.loads(raw);new=reform.plans(root,key,include_archived=True)
            assert len(old)==len(new)
            for previous,current in zip(old,new):
                assert all(current[k]==v for k,v in previous.items()),(key,'original field changed')
                assert current['uid'] and current['revision']>=1
                for item in current['items']:
                    if item.get('ticket'):
                        t=st.ticket(item['ticket']);assert t and st.project(t['project_id'])['key']==key
                        assert t['links']['reform']['plan']==previous['id']
                        links+=1
            assert (root/'reforms'/(key+'.json')).read_bytes()==raw
            assert reform.plans(root,key,include_archived=True)==new
            plans+=len(new)
        st.db.close()
        afterdb=sqlite3.connect(target);after=content(afterdb)
        assert all(after[name]==value for name,value in before.items()),'existing table rows changed'
        assert afterdb.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        afterdb.close()
        report.append({'database':str(live.relative_to('/opt/webuddy/data')),'integrity':'ok','original_tables_unchanged':len(before),'plans':plans,'original_ticket_links':links,'legacy_bytes':'unchanged'})
print(json.dumps({'source_commit':'682164e5bc19dc2a49cf493d99ea4edf67893aba','mode':'copies_only_no_live_writes','results':report},ensure_ascii=False,indent=2))
