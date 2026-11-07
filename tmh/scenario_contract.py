"""Scenario materials are versioned task input, never an authorization grant."""
from copy import deepcopy


def string():
    return {'type':'string'}


def lines():
    return {'type':'array','items':string()}


SCHEMA = {'type':'object','additionalProperties':False,'required':[], 'properties':{
    'sources':{'type':'array','items':{'type':'object','additionalProperties':False,
        'required':['id','kind','reference','version'],
        'properties':{k:string() for k in ('id','kind','reference','version')}}},
    'rules':lines(), 'changed_behaviors':lines(), 'regressions':lines(), 'invariants':lines(),
    'modules':lines(), 'external_dependencies':lines(), 'test_data':lines(), 'environment_gaps':lines(),
    'expectation_sources':lines(), 'acceptance_owner':string(), 'excluded':lines(), 'open_questions':lines(),
    'discussions':{'type':'array','items':{'type':'object','additionalProperties':False,
        'required':['question','proposal','reason'],
        'properties':{k:string() for k in ('question','proposal','reason','reported_customer_response','disagreement','impact')}}},
    'suspected_impacts':lines(),
    'conflicts':{'type':'array','items':{'type':'object','additionalProperties':False,
        'required':['source_ids','description','affected_requirements','owner'],
        'properties':{'source_ids':lines(),'description':string(),'affected_requirements':lines(),'owner':string(),'proposed_resolution':string()}}},
}}


def normalize(value):
    from .agent_contract import _validate_value
    _validate_value('scenario',SCHEMA,value)
    sources=value.get('sources',[])
    ids=[s['id'] for s in sources]
    if any(not x.strip() for x in ids) or len(ids)!=len(set(ids)):
        raise ValueError('场景来源编号必须非空且唯一')
    for conflict in value.get('conflicts',[]):
        if len(set(conflict['source_ids']))<2 or set(conflict['source_ids'])-set(ids):
            raise ValueError('冲突必须关联至少两个已登记的不同来源')
    return deepcopy(value)


def recorded(value):
    """Do not promote author-supplied rules or FDE recollections into confirmation."""
    return {'materials':deepcopy(value or {}),'confirmation_status':'not_confirmed_by_this_record',
        'notice':'场景记录是任务材料；客户回复为转述。实际需求确认、技术验证和业务验收分别以原有受权事件为准。'}
