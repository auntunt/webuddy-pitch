from pathlib import Path
import json, xml.etree.ElementTree as ET
base=Path('/private/tmp/webuddy-scenario-20261107/windows-audit')
result=[]
for path in sorted(base.glob('*/summary.json')):
    data=json.loads(path.read_text())
    assert data['commit']=='cf6143bee2778cc14f09c0857ae45c57438b83bd'
    rows=[]
    for row in data['results']:
        stem=row['module'].replace('/','__').replace('::','__').removesuffix('.py')
        xml=path.parent/(stem+'.xml')
        counts={key:0 for key in ('tests','failures','errors','skipped')}
        diagnostics=[]
        if xml.exists():
            root=ET.parse(xml)
            for suite in root.iter('testsuite'):
                for key in counts:counts[key]+=int(suite.get(key,'0'))
            for case in root.iter('testcase'):
                for tag in ('failure','error','skipped'):
                    for node in case.findall(tag):diagnostics.append({'case':case.get('name'),'kind':tag,'message':node.get('message')})
        rows.append(dict(row,counts=counts,diagnostics=diagnostics))
    result.append({'artifact':path.parent.name,'commit':data['commit'],'python':data['python'],'shard':data['shard'],'started':data['started'],'expected_units':len(data['discovered'][data['shard']::8]),'completed_units':len(rows),'rows':rows})
Path('/private/tmp/webuddy-scenario-20261107/windows-audit-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
for version in ('3.11','3.13'):
    parts=[r for r in result if r['artifact'].startswith('windows-'+version+'-')]
    rows=[row for p in parts for row in p['rows']]
    print(version,'shards',len(parts),'units',len(rows),'nonzero',sum(r['exit_code']!=0 for r in rows),'timeout',sum(r['timed_out'] for r in rows),'junit', {k:sum(r['counts'][k] for r in rows) for k in ('tests','failures','errors','skipped')})
