"""Project-scoped saved views of the existing graph, not a second graph engine."""
import base64
import hashlib
import json
from pathlib import Path
from .errors import ApiError
from .store import now

NOTICE = '静态索引与检索关联；不证明完整调用链、测试覆盖或业务验收。'
RELATIONS = {'calls':'静态调用','handles':'静态入口','reads':'静态读取','writes':'静态写入',
             'step':'流程级关联','uses':'流程级数据关联','contains':'静态包含','effect':'静态外部调用'}


def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def exists(st):return bool(st.one("SELECT name FROM sqlite_master WHERE name='code_maps'"))


def load(st, project, map_id):
    row=st.one('SELECT body FROM code_maps WHERE id=? AND project_id=?',(map_id,project['id'])) if exists(st) else None
    if not row:raise ApiError(404,'没有这个项目的地图')
    return json.loads(row['body'])


def create(P, project, actor, args):
    from ..graph import Graph,graph_path
    from ..context import search
    fingerprint=hashlib.sha256(encoded(args).encode()).hexdigest()
    if exists(P.store):
        old=P.store.one('SELECT id,fingerprint FROM code_maps WHERE actor=? AND request_id=?',(actor,args['request_id']))
        if old:
            if old['fingerprint']!=fingerprint:raise ApiError(409,'请求号已用于另一份地图')
            return view(load(P.store,project,old['id']))
    root=P.kb.root(project)
    if not graph_path(root).is_file():raise ApiError(409,'知识索引尚未构建，请先由项目负责人构建')
    g=Graph(root)
    try:
        provenance=g.provenance()
        if provenance['index_status']=='unverifiable':raise ApiError(409,'旧索引没有来源身份，请先重建知识库')
        hits=search(root,args['question'],limit=100)
        from .. import kb
        registry=kb.load_registry(root)
        knowledge=[];knowledge_sources={}
        for _,hit in hits:
            if hit.get('type')!='page':continue
            path=kb.page_path(root,hit['id'])
            if not path.is_file():continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ApiError(409,'知识来源越出项目')
            raw=path.read_bytes()
            knowledge_sources[path.relative_to(root).as_posix()]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'base64':base64.b64encode(raw).decode()}
            knowledge.append({'id':hit['id'],'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'record':registry.get(hit['id'],{}),'authority':'历史知识引用；采用状态由现有知识确认机制另行核对'})
        ids=[]
        for _,hit in hits:
            if g.node(hit['id']) and hit['id'] not in ids:ids.append(hit['id'])
        visited=set()
        if args.get('from_map'):
            prior=load(P.store,project,args['from_map'])
            if prior['provenance']['index_revision']!=provenance['index_revision']:
                raise ApiError(409,'原地图索引已变化，请明确生成新地图，不能替换历史来源')
            visited=set(prior.get('visited',[]))|set(prior.get('unknown_nodes',[]))|{n['id'] for n in prior['nodes']}
            ids=[n for n in dict.fromkeys(prior['unexpanded']+ids) if n not in visited]
        seeds=ids[:args.get('limit',30)]
        edges=[]
        for nid in seeds:
            for edge in g.out(nid)+g.inn(nid):
                if edge['kind'] not in RELATIONS:continue
                edges.append(dict(edge,basis='static_parser',meaning=RELATIONS[edge['kind']]))
                for related in (edge['src'],edge['dst']):
                    if related not in ids and related not in visited:ids.append(related)
        candidates=ids[:args.get('limit',30)]
        nodes=[g.node(n) for n in candidates];nodes=[n for n in nodes if n]
        chosen={n['id'] for n in nodes}
        sources=dict(knowledge_sources)
        for node in nodes:
            path=node.get('file')
            if path and path not in sources:
                try:
                    raw=g.source_bytes(path)
                    sources[path]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'base64':base64.b64encode(raw).decode()}
                except (ValueError,FileNotFoundError) as exc:sources[path]={'unavailable':str(exc)}
        # Search may have opened another graph: never publish a mixed index revision.
        latest=Graph(root)
        try:
            if latest.meta().get('provenance',{}).get('index_revision')!=provenance['index_revision']:
                raise ApiError(409,'检索期间索引变化，请重试')
        finally:latest.db.close()
        value={'revision':1,'created_by':actor,'request_id':args['request_id'],'project':project['key'],'question':args['question'],'provenance':provenance,
               'knowledge_references':knowledge,'visited':sorted(visited),'nodes':nodes,'relations':list({encoded(e):e for e in edges if e['src'] in chosen and e['dst'] in chosen}.values()),
               'unknown_nodes':[n for n in candidates if n not in chosen],'unexpanded':ids[len(candidates):],'sources':sources,'created_at':now(),
               'explanation_basis':'现有关键词检索与一层静态关系；没有调用模型或推测业务顺序',
               'notice':NOTICE,'from_map':args.get('from_map'),'coverage':'局部范围；全仓相关内容总数未知'}
        fingerprint=hashlib.sha256(encoded(args).encode()).hexdigest()
        st=P.store
        with st.lock,st.db:
            st.db.execute('CREATE TABLE IF NOT EXISTS code_maps(id TEXT PRIMARY KEY,project_id INTEGER,actor TEXT,request_id TEXT,fingerprint TEXT,body TEXT,UNIQUE(actor,request_id))')
            old=st.db.execute('SELECT id,fingerprint FROM code_maps WHERE actor=? AND request_id=?',(actor,args['request_id'])).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise ApiError(409,'请求号已用于另一份地图')
                return view(load(st,project,old['id']))
            value['id']='map'+hashlib.sha256((encoded(value)+actor+args['request_id']).encode()).hexdigest()[:32]
            st.db.execute('INSERT INTO code_maps VALUES(?,?,?,?,?,?)',(value['id'],project['id'],actor,args['request_id'],fingerprint,encoded(value)))
        return view(value)
    finally:g.db.close()


def view(value):
    return {**{k:v for k,v in value.items() if k!='sources'},'source_files':{p:{k:v for k,v in s.items() if k!='base64'} for p,s in value['sources'].items()},
            'current_applicability':'not_checked','deep_link':'#/maps/'+value['project']+'/'+value['id']}


def execute(P, project, actor, op, args):
    if op=='map_create':return create(P,project,actor,args)
    if op=='maps_list':
        clause=' AND actor=? AND request_id=?' if args.get('request_id') else ''
        params=[project['id']]+([actor,args['request_id']] if args.get('request_id') else [])+[args.get('limit',20)+1,args.get('after',0)]
        rows=P.store.q('SELECT body FROM code_maps WHERE project_id=?'+clause+' ORDER BY rowid DESC LIMIT ? OFFSET ?',params) if exists(P.store) else []
        count=args.get('limit',20)
        return {'items':[{k:v[k] for k in ('id','revision','question','created_at','provenance')} for v in (json.loads(r['body']) for r in rows[:count])],
                'next_after':args.get('after',0)+count if len(rows)>count else None}
    if args.get('node_id') and args.get('knowledge_id'):raise ApiError(400,'一次只读取一个源码节点或知识来源')
    value=load(P.store,project,args['map_id'])
    if not args.get('node_id') and not args.get('knowledge_id'):
        from . import reform
        linked=[{'plan_id':p['id'],'revision':p['revision'],'title':p['title'],'source_version':p.get('source_version'),
                 'tasks':[i['ticket'] for i in p['items'] if i.get('ticket')],
                 'deep_link':'#/projects/'+project['key']+'/reforms/'+p['id']} for p in reform.plans(P.data_dir,project['key'],include_archived=True,store=P.store)
                 if any(r['map_id']==value['id'] for r in p.get('map_refs',[]))]
        return dict(view(value),linked_plans=linked)
    if args.get('knowledge_id'):
        knowledge=next((k for k in value.get('knowledge_references',[]) if k['id']==args['knowledge_id']),None)
        node=dict(id=knowledge['id'],file=knowledge['path'],line=1,label=knowledge['record'].get('title',knowledge['id']),authority=knowledge['authority'],source_version='knowledge:'+knowledge['sha256']) if knowledge else None
    else:
        node=next((n for n in value['nodes'] if n['id']==args['node_id']),None)
    if node is None:raise ApiError(404,'节点不在这份固定地图中')
    source=value['sources'].get(node.get('file'),{})
    if 'base64' not in source:return {'node':node,'source_status':'unavailable','reason':source.get('unavailable','节点没有源码位置'),'provenance':value['provenance']}
    raw=base64.b64decode(source['base64'])
    if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ApiError(409,'保存源码校验失败')
    # The original encoding remains available in the frozen source. Decode visibly.
    try:text=raw.decode('utf-8');encoding='utf-8'
    except UnicodeError:
        try:text=raw.decode('gb18030');encoding='gb18030'
        except UnicodeError:raise ApiError(409,'源码编码无法核对，不以替换字符冒充原文')
    lines=text.splitlines(keepends=True);start=args.get('line') or max(1,node.get('line') or 1);limit=args.get('limit',60)
    return {'map_id':value['id'],'revision':1,'node':node,'provenance':value['provenance'],'file_sha256':source['sha256'],
            'encoding':encoding,'line':start,'total_lines':len(lines),'text':''.join(lines[start-1:start-1+limit]),
            'next_line':start+limit if start-1+limit<len(lines) else None,'source_status':'saved_snapshot'}


def validate_refs(store,project,refs):
    from ..agent_contract import REFORM_FIELDS,_validate_value
    try:_validate_value('map_refs',REFORM_FIELDS['map_refs'],refs)
    except ValueError as exc:raise ApiError(400,str(exc)) from exc
    for ref in refs:
        value=load(store,project,ref['map_id'])
        if ref['revision']!=value['revision']:raise ApiError(409,'地图修订不匹配')
        if not set(ref['nodes']).issubset({n['id'] for n in value['nodes']}):raise ApiError(400,'选中节点不属于固定地图')
    return refs


def context(store,project,refs,budget=6000):
    """Actual injected selection receipt; history is never silently current."""
    from ..index_source import snapshot,digest
    validate_refs(store,project,refs)
    current=digest(snapshot(Path(project['root'])))
    receipt={'mode':'code_maps','maps':[],'used':0,'omissions':[]}
    texts=[]
    for ref in refs:
        value=load(store,project,ref['map_id'])
        status='current' if current==value['provenance']['snapshot_sha256'] else 'stale'
        selected=[n for n in value['nodes'] if n['id'] in ref['nodes']]
        item={'map_id':value['id'],'revision':value['revision'],'source_version':value['provenance']['source_version'],
              'index_revision':value['provenance']['index_revision'],'selected':ref['nodes'],'injected':[],
              'applicability':status,'unexpanded':value['unexpanded'],
              'knowledge_references_not_injected':[{'id':k['id'],'sha256':k['sha256'],'reason':'地图知识原文只供追溯；任务知识仍经过现有采用与授权过滤'} for k in value.get('knowledge_references',[])]}
        receipt['maps'].append(item)
        if status!='current':
            receipt['omissions'].append({'map_id':value['id'],'reason':'候选源码与固定地图不一致；重新分析后再使用'})
            texts.append('地图 '+value['id']+' 来源已变化，未注入旧节点为当前事实。')
            continue
        for node in selected:
            entry=encoded({'map_id':value['id'],'revision':value['revision'],'source_version':value['provenance']['source_version'],
                'node':node,'relations':[e for e in value['relations'] if node['id'] in (e['src'],e['dst'])],'notice':NOTICE})
            if receipt['used']+len(entry)>budget:
                receipt['omissions'].append({'map_id':value['id'],'node':node['id'],'reason':'上下文预算未展开'})
                continue
            texts.append(entry);receipt['used']+=len(entry);item['injected'].append(node['id'])
    return '\n'.join(texts),receipt
