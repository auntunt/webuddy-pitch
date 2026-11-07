"""Readable saved evidence export; no invented live gate or human verdict."""
import json


def evidence_sections(packet):
    """Render structured saved checks only; raw text is never promoted to a verdict."""
    rows=['','## 版本与独立结论',
          '当前有效性：'+packet.get('current_validity','not_checked')+'（未作实时核验）',
          '代码审查：见保存的审查记录；工程门禁：未实时核对；业务验收：仅以已记录的授权决定为准。']
    for candidate in packet.get('candidates',[]):
        rows.extend(['','候选：'+str(candidate.get('commit') or '未记录')+'；基线：'+str(candidate.get('base_commit') or '未记录'),
                     '验收标准绑定：'+str(candidate.get('requirement_hash') or '未记录')])
        for criterion in candidate.get('criteria',[]):
            rows.append('- 要求：'+json.dumps(criterion,ensure_ascii=False)+'；当前覆盖状态：无法核对，请对照下列保存检查。')
    pending=[(packet.get('runs',[]),'runs',False)]
    found=0
    while pending:
        value,path,invalid=pending.pop()
        if isinstance(value,list):
            pending.extend((v,path+'/'+str(i),invalid) for i,v in reversed(list(enumerate(value))))
        elif isinstance(value,dict):
            invalid=invalid or value.get('invalidated') is True
            if isinstance(value.get('criterion_evidence'),dict):
                found+=1
                rows.extend(['','## 已保存逐项检查', '依据位置：'+path,
                    '代码身份：'+json.dumps(value.get('code_identity','未记录'),ensure_ascii=False),
                    '标准修订：'+str(value.get('criteria_digest') or '未记录')+'；配置修订：'+str(value.get('profile_digest') or '未记录'),
                    '环境：'+str(value.get('environment') or '未记录')])
                stages={v['id']:v for v in value.get('stages',[]) if isinstance(v,dict) and 'id' in v}
                for criterion in value.get('criteria',[]):
                    if not isinstance(criterion,dict):
                        rows.append('要求：'+str(criterion)+'；结构化依据未记录');continue
                    cid=str(criterion.get('id',''))
                    proofs=value['criterion_evidence'].get(cid,[])
                    rows.extend(['','### '+cid+' '+str(criterion.get('criterion') or criterion.get('text') or '要求正文未记录'),
                        '预期依据来源：'+str(criterion.get('source') or criterion.get('expectation_source') or '未记录')])
                    if not proofs:rows.append('结论：未覆盖；没有已记录的对应检查。')
                    for proof in proofs:
                        stage=stages.get(proof.get('stage'),{})
                        status='已失效' if invalid else {'pass':'保存检查通过（当前有效性待核对）','fail':'失败','blocked':'受阻','skip':'未执行','unverified':'无法核对'}.get(stage.get('status') if stage.get('status')!='pass' else proof.get('status'),'无法核对')
                        rows.extend(['方法：实测记录；步骤：'+str(stage.get('command') or '未记录'),
                            '结论：'+status+'；原因：'+str(stage.get('error') or '未记录'),
                            '原始证据：'+path+'/stages/'+str(proof.get('stage'))])
                        cases={c['id']:c for c in stage.get('cases',[]) if isinstance(c,dict) and 'id' in c}
                        for case_id in proof.get('cases',[]):
                            case=cases.get(case_id,{})
                            rows.extend(['用例：'+case_id,'输入：'+str(case.get('input','未记录')),
                                         '预期：'+str(case.get('expected','未记录')),'实际：'+str(case.get('actual','未记录'))])
            for key,child in value.items():
                if key not in ('raw','output','result','diff') and isinstance(child,(dict,list)):
                    pending.append((child,path+'/'+key,invalid))
    if not found:rows.extend(['','## 逐项检查缺口','尚无可解析的逐项实测记录；原始报告和历史审查仍在附件中，不据此推断通过。'])
    return rows


def markdown(packet, *, include_raw=True):
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
    text.extend(evidence_sections(packet))
    text.extend(['','## 用量与费用'])
    for row in packet['consumption']:
        text.extend(['- 运行 #'+str(row['run_id'])+'：'+row['usage_source']+'；实际费用未知。'])
    if not packet['consumption']:
        text.append('暂无运行用量记录，费用未知。')
    text.extend(['','## 下一步',packet['next_step'],'',
        '逐项实测、Review、确认稿和人工决定请查下列完整原始记录；未记录不等于通过。',
        '', '## 完整结构化依据'])
    if not include_raw:
        return '\n'.join(text[:-2])+ '\n完整原始依据见同一导出清单中的 JSON 附件。\n'
    raw=json.dumps(packet,ensure_ascii=False,indent=2)
    # User-supplied backticks must not close the full original-data appendix.
    fence='`'*(max([len(part) for part in __import__('re').findall(r'`+',raw)] or [2])+1)
    text.extend([fence+'json',raw,fence,''])
    return '\n'.join(text)
