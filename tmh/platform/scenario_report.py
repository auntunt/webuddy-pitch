"""Readable saved evidence export; no invented live gate or human verdict."""
import json


def markdown(packet):
    ticket=packet['ticket']
    text=['# '+ticket['key']+' '+ticket['title'],'',
        '生成时间：'+packet['generated_at'],'',
        '本报告读取保存记录；未执行当前版本有效性检查。检查执行、工程门禁和业务验收是三个独立结论。',
        '', '## 需求与范围', ticket.get('body') or '未记录', '', '## 场景与来源']
    scenario=packet.get('scenario')
    if scenario:
        text.extend([scenario.get('notice','关联计划不可用'),''])
        material=scenario.get('materials',{})
        for key,label in [('source_version','固定源版本'),('revision','场景修订'),('target_environment','验证环境')]:
            text.append(label+'：'+str(scenario.get(key) or '未记录'))
        for key,label in [('rules','业务规则材料'),('changed_behaviors','新增或改变的行为'),
                          ('regressions','旧功能回归'),('invariants','必须保持的约束'),
                          ('suspected_impacts','推测影响（待核对）'),('test_data','测试数据'),
                          ('expectation_sources','独立预期来源'),('environment_gaps','环境缺口'),
                          ('open_questions','待澄清问题'),('excluded','排除范围')]:
            text.extend(['','### '+label])
            text.extend(['- '+line for line in material.get(key,[])] or ['未记录'])
        text.extend(['','验收负责人（材料登记）：'+(material.get('acceptance_owner') or '尚未指定'),'','### 来源'])
        text.extend(['- '+source['id']+' · '+source['kind']+' · '+source['version']+' · '+source['reference']
                     for source in material.get('sources',[])] or ['未记录'])
        for conflict in material.get('conflicts',[]):
            text.extend(['','待核对冲突：'+conflict['description'],
                         '来源：'+', '.join(conflict['source_ids'])+'；处理人：'+(conflict['owner'] or '尚未指定')])
    else:
        text.append('未关联场景记录；不推断范围完整。')
    text.extend(['','## 用量与费用'])
    for row in packet['consumption']:
        text.extend(['- 运行 #'+str(row['run_id'])+'：'+row['usage_source']+'；实际费用未知。'])
    if not packet['consumption']:
        text.append('暂无运行用量记录，费用未知。')
    text.extend(['','## 下一步',packet['next_step'],'',
        '逐项实测、Review、确认稿和人工决定请查下列完整原始记录；未记录不等于通过。',
        '', '## 完整结构化依据'])
    raw=json.dumps(packet,ensure_ascii=False,indent=2)
    # User-supplied backticks must not close the full original-data appendix.
    fence='`'*(max([len(part) for part in __import__('re').findall(r'`+',raw)] or [2])+1)
    text.extend([fence+'json',raw,fence,''])
    return '\n'.join(text)
