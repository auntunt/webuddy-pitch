"""Fixed independent D assertion; no model, tools or knowledge mutation."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tmh.platform import learning_eval as E


def evaluate(value):
    if not isinstance(value,dict) or set(value)!={'case','output','input_sha256'}:
        raise ValueError('fixed complete D input required')
    if not isinstance(value['output'],str): raise ValueError('complete native text required')
    return dict(schema='native-d-assertion-result-v1',input_sha256=value['input_sha256'],
                passed=E.check(value['case'],value['output']),scope='new-task-output-assertions-only')


if __name__=='__main__':print(json.dumps(evaluate(json.load(sys.stdin)),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
