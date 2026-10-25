"""Full shipped evaluator replay (simulated UID/Path), plus explicit Linux tests."""
import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import platform
from types import SimpleNamespace
import unittest

import test_rsi_registered_isolation as I
from scripts.rsi import registered_isolation as X, registered_trial as R, trial_preparation as L


def nested(value,depth=40):
    for i in range(depth):value={'depth':i,'items':[None,'完整\r\n😀',value]}
    return value


def replay(candidate,oracle,role='evaluator',oracle_raw=None):
    """No SETUP/Launcher: these modules are data/UID projections, not OS proof."""
    files={'/input/candidate.json':L.encoded({'blocks':candidate}).encode(),
           '/input/oracle.json':oracle_raw if oracle_raw is not None else L.encoded({'expected_blocks':oracle,'secret_canary':'PRIVATE_'+'x'*64}).encode()}
    class VirtualPath:
        def __init__(self,path):self.path=path
        def read_bytes(self):return files[self.path]
        def read_text(self):return self.read_bytes().decode()
    modules={'os':SimpleNamespace(getuid=lambda:508102),'json':json,'socket':SimpleNamespace(),
             'sys':SimpleNamespace(argv=['worker',role]),'time':SimpleNamespace(),'hashlib':hashlib,'pathlib':SimpleNamespace(Path=VirtualPath)}
    def importing(name,*unused,**kwargs):return modules[name]
    scope=dict(vars(builtins));scope['__import__']=importing
    out,err=io.StringIO(),io.StringIO();code=0
    try:
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):exec(compile(X.WORKER,'shipped-WORKER','exec'),{'__builtins__':scope})
    except SystemExit as error:code=error.code
    return code,json.loads(out.getvalue()),err.getvalue(),files


class TypedWorkerReplayTests(unittest.TestCase):
    def check(self,left,right,expected):
        code,value,stderr,files=replay(left,right)
        self.assertEqual(code,0);self.assertEqual(stderr,'');self.assertIs(value['verdict'],expected)
        self.assertEqual(value['schema'],'oracle-exact-blocks-v2')
        self.assertEqual(value['candidate_sha256'],R.sha(files['/input/candidate.json']))

    def test_nested_true_is_not_integer_one(self):
        self.check([{'type':'text','text':'全文','extra':nested(True)}],[{'type':'text','text':'全文','extra':nested(1)}],False)

    def test_nested_false_is_not_integer_zero(self):
        self.check([{'type':'text','text':'全文','extra':nested(False)}],[{'type':'text','text':'全文','extra':nested(0)}],False)

    def test_same_complete_deep_blocks_preserve_long_text_and_null(self):
        blocks=[{'type':'text','text':('全文\r\n😀 '*5000)+'尾部','extra':nested({'enabled':True,'count':1,'null':None})}]
        self.check(blocks,copy.deepcopy(blocks),True)

    def test_object_key_order_is_irrelevant(self):
        self.check([{'type':'text','text':'same','extra':{'a':True,'b':[False,1,None]}}],
                   [{'extra':{'b':[False,1,None],'a':True},'text':'same','type':'text'}],True)

    def test_array_order_and_extra_fields_are_not_ignored(self):
        self.check([{'type':'text','text':'same','extra':[True,False]}],[{'type':'text','text':'same','extra':[False,True]}],False)
        self.check([{'type':'text','text':'same','extra':1}],[{'type':'text','text':'same'}],False)

    def test_integer_and_float_representations_are_distinct(self):
        self.check([{'type':'text','text':'same','number':1}],[{'type':'text','text':'same','number':1.0}],False)
        self.check([{'type':'text','text':'same','number':-0.0}],[{'type':'text','text':'same','number':0.0}],False)

    def test_same_parsed_finite_float_representation_is_equal(self):
        self.check([{'type':'text','text':'same','number':1e0}],[{'type':'text','text':'same','number':1.0}],True)

    def test_changed_text_and_wrong_json_type_are_not_equal(self):
        self.check([{'type':'text','text':'same'}],[{'type':'text','text':'different'}],False)
        self.check([{'type':'text','text':'same','extra':'1'}],[{'type':'text','text':'same','extra':1}],False)

    def test_malformed_oracle_and_wrong_role_keep_fixed_error_boundary(self):
        for kwargs in ({'oracle_raw':b'{BROKEN PRIVATE_'},{'role':'not-allowed'},
                       {'oracle_raw':b'{"expected_blocks":[NaN],"secret_canary":"PRIVATE_"}'}):
            with self.subTest(kwargs=kwargs):
                code,value,stderr,files=replay([],[],**kwargs)
                self.assertEqual(code,1);self.assertEqual(value,{'schema':'fixed-worker-error-v1'});self.assertEqual(stderr,'')


@unittest.skipUnless(platform.system()=='Linux' and hasattr(os,'geteuid') and os.geteuid()==0 and os.environ.get('RSI_RUN_KERNEL_FIXTURE')=='1',
                     'explicit temporary root-owned Linux typed evaluator fixture')
class TypedEvaluatorKernelTests(unittest.TestCase):
    def setUp(self):
        self.base=I.RegisteredIsolationKernelTests('test_actual_two_identities_public_input_and_independent_oracle')
        self.base.setUp();self.addCleanup(self.base.doCleanups);self.c=self.base.c
        (self.c.root/'typed-evaluator-test-identity.json').write_text(json.dumps({'test':self.id()}))

    def typed_run(self,left,right):
        self.c.response['content'][0]['text']=('原始正文\r\n😀 '*2000)+'完整尾部'
        self.c.response['content'][0]['extra']=nested(left)
        blocks=copy.deepcopy(self.c.response['content']);blocks[0]['extra']=nested(right)
        oracle=dict(self.base.oracle,expected_blocks=blocks);path=self.c.root/'typed-oracle';path.mkdir(mode=0o700)
        catalog=R.Catalog(path);self.addCleanup(catalog.close);oh=catalog.admit('input','plan-one',oracle)
        self.base.oracle=oracle;self.base.launcher.oracles=catalog
        self.base.admit(oracle_sha256=oh)
        result=self.base.dispatch();(self.c.root/'typed-evaluator-result.json').write_text(L.encoded(result))
        self.assertEqual(result['isolated_execution'],'evaluated');self.assertEqual(result['oracle_evaluation'],'completed')
        self.assertEqual(self.c.count,1);self.base.original_receipts(result)
        item=self.c.ledger.snapshot(self.c.key,'delivery-one')['attempt'];self.assertEqual(item['state'],'settled')
        candidate_root=self.base.launcher.root/result['execution_id']/'candidate-root/input/public.json'
        sent=json.loads(candidate_root.read_bytes());self.assertEqual(sent['native_response'],self.c.response)
        return result

    def test_real_deep_true_vs_one_is_false(self):self.assertIs(self.typed_run(True,1)['verdict'],False)
    def test_real_deep_false_vs_zero_is_false(self):self.assertIs(self.typed_run(False,0)['verdict'],False)
    def test_real_identical_long_full_blocks_are_true(self):self.assertIs(self.typed_run({'a':True,'b':1},{'b':1,'a':True})['verdict'],True)
