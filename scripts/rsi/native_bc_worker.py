"""Fixed, tool-free assertion worker. Private input, never model instructions."""
import json
from pathlib import Path
import sys

# Only this fixed source tree is used; there are no caller paths or imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tmh.platform import learning_eval as E


def evaluate(value):
    from scripts.rsi import trial_preparation as L
    L.fields(value, {'cases', 'thresholds'})
    rows=[]
    for case in value['cases']:
        L.fields(case, {'input_sha256','validator','expected','forbidden','baseline','candidate'})
        for side in ('baseline','candidate'):
            if not isinstance(case[side],str):raise ValueError('complete text required')
        rows.append({'input_sha256':case['input_sha256'],
                     'baseline':E.check(case,case['baseline']), 'candidate':E.check(case,case['candidate'])})
    t=value['thresholds']
    L.fields(t,{'min_pairs','min_improvement','require_candidate_all','allow_regressions'})
    counts={s:sum(r[s] for r in rows) for s in ('baseline','candidate')}
    regressions=[r['input_sha256'] for r in rows if r['baseline'] and not r['candidate']]
    passed=(len(rows)>=t['min_pairs'] and not regressions and counts['candidate']==len(rows)
            and counts['candidate']-counts['baseline']>=t['min_improvement'])
    return {'schema':'native-bc-assertions-v1','cases':rows,'counts':counts,'regressions':regressions,'passed':passed,
            'scope':'presealed-output-assertions-only'}


if __name__=='__main__':
    print(json.dumps(evaluate(json.load(sys.stdin)),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
