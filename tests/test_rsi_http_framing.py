"""Actual loopback framing plus real supervisor historical-receipt controls."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import unittest

import test_rsi_provider_adapter as F
from scripts.rsi import provider_adapter as P
from scripts.rsi import trial_preparation as L
from tmh.platform import supervised_process as SP


@unittest.skipUnless(os.name == 'posix', 'supervised private-fd transport requires POSIX')
class HTTPFramingTests(unittest.TestCase):
    def fixture(self):
        case = F.ProviderAdapterTests('test_success_full_raw_cache_accounting_and_no_credential_artifact')
        try:case.setUp()
        except BaseException:
            case.doCleanups();raise
        self.addCleanup(case.doCleanups)
        return case

    def exchange(self, lengths=None, *, transfer=None, expected='unknown', chunked=False, keep_open=False):
        c = self.fixture();body=json.dumps(F.native(),ensure_ascii=False).encode()
        values = lengths(len(body)) if callable(lengths) else lengths
        headers=[('Content-Type','application/json')]
        headers += [('Content-Length',value) for value in (values or [])]
        if transfer is not None:headers.append(('Transfer-Encoding',transfer))
        headers.append(('Connection','keep-alive' if keep_open else 'close'))
        wire_body=(f'{len(body):X}\r\n'.encode()+body+b'\r\n0\r\n\r\n') if chunked else body
        wire=b'HTTP/1.1 200 OK\r\n'+b''.join((k+': '+v+'\r\n').encode('latin1') for k,v in headers)+b'\r\n'+wire_body
        (c.root/'response-wire.bin').write_bytes(wire)
        def handle(handler):
            received=handler.rfile.read(int(handler.headers['Content-Length']))
            with c.lock:
                c.count+=1;c.requests.append(received);c.auth_ok.append(handler.headers.get('x-api-key')==c.secret)
            c.seen.set()
            try:
                handler.wfile.write(wire);handler.wfile.flush()
                if keep_open:c.release.wait(10)
            except (BrokenPipeError,ConnectionResetError):pass
            handler.close_connection=True
        c.server.RequestHandlerClass.do_POST=handle
        result=c.dispatch()
        self.assertEqual(result['state'],expected)
        self.assertEqual(result['response_complete'],expected=='settled')
        folder=Path(result['evidence'])
        receipt=SP.read_receipt(folder/'transport')
        self.assertEqual(receipt['returncode'],0 if expected=='settled' else 70)
        raw=(folder/'transport/output.bin').read_bytes().split(b'\n',1)[1]
        self.assertEqual(raw,body if expected=='settled' and chunked else wire_body)
        self.assertEqual(c.auth_ok,[True]);self.assertEqual(c.count,1)
        snap=c.ledger.inspect(c.key)
        self.assertEqual(snap['totals'],{'calls':1,'billed_tokens':11 if expected=='settled' else 120,'cost_micro_cny':130 if expected=='settled' else 1400})
        self.assertEqual(snap['blocked'],expected=='unknown')
        replay=c.dispatch();self.assertEqual(replay['state'],expected);self.assertFalse(replay['new_dispatch'])
        self.assertEqual(c.count,1)
        if expected=='unknown':
            try:reconciled=c.adapter.reconcile(c.key,'one')
            except ValueError:reconciled={'state':'rejected'}
            self.assertEqual(reconciled['state'],'unknown')
            with self.assertRaises(L.Conflict):c.dispatch('retry','retry')
            self.assertEqual(c.ledger.inspect(c.key)['totals'],snap['totals'])
        return c

    def test_valid_single(self):self.exchange(lambda n:[str(n)],expected='settled')
    def test_identical_duplicate(self):self.exchange(lambda n:[str(n),str(n)],expected='settled')
    def test_identical_comma_list_keepalive(self):self.exchange(lambda n:[f'{n}, {n}'],expected='settled',keep_open=True)
    def test_invalid_non_numeric(self):self.exchange(['not-a-number'])
    def test_invalid_signed(self):self.exchange(lambda n:['+'+str(n)])
    def test_conflicting_valid_first(self):self.exchange(lambda n:[str(n),str(n+17)])
    def test_conflicting_long_first(self):self.exchange(lambda n:[str(n+17),str(n)])
    def test_short_declared_body(self):self.exchange(lambda n:[str(n+17)])
    def test_conflicting_comma_list(self):self.exchange(lambda n:[f'{n}, {n+17}'])
    def test_empty_negative_and_underscored_lengths(self):
        for values in [[''],['-1'],['3_94']]:
            with self.subTest(values=values):self.exchange(values)
    def test_close_delimited(self):self.exchange(expected='settled')
    def test_chunked_only(self):self.exchange(transfer='chunked',chunked=True,expected='settled')
    def test_transfer_and_length_ambiguous(self):self.exchange(lambda n:[str(n)],transfer='chunked',chunked=True)
    def test_unknown_transfer_coding(self):self.exchange(transfer='gzip')

    def historical(self, lengths, *, settled=True):
        c=self.fixture();contract=copy.deepcopy(c.ledger.snapshot(c.key)['contract'])
        contract['root_family']+='-historical'
        contract['provider_binding']['code_sha256']={'ledger':'1'*64,'adapter':'2'*64,'transport':'3'*64}
        profile=copy.deepcopy(c.profile);profile['contract_sha256']=L.digest(P._base(contract))
        profile_raw=L.encoded(profile).encode();ph=hashlib.sha256(profile_raw).hexdigest()
        contract['provider_binding']['profile_sha256']=ph
        key=c.ledger.create(contract);request='historical'
        wire=L.encoded({'model':profile['model']['requested_model'],'system':c.system,'messages':c.messages,'max_tokens':20,'stream':False,'service_tier':'standard_only'}).encode()
        c.ledger.reserve(key,request,'propose',100,20,material_sha256=L.digest([ph,hashlib.sha256(wire).hexdigest()]))
        intent=c.ledger.intent(key,request)['intent']
        folder=c.adapter._folder(key,request);folder.mkdir(mode=0o700)
        c.adapter._seal(folder,'profile.json',profile_raw);c.adapter._seal(folder,'request.bin',wire)
        body=json.dumps(F.native(),ensure_ascii=False).encode()
        meta={'schema':'messages-text-transport-v1','status':200,'headers':[['Content-Length',v] for v in lengths(len(body))],
              'transport_sha256':'3'*64,'request_sha256':hashlib.sha256(wire).hexdigest()}
        raw=json.dumps(meta).encode()+b'\n'+body
        # Controlled legacy exit-0 ORIGINAL fixture, not a real provider call or
        # an attestation that this emitter is an old deployed transport binary.
        child="import sys,base64;sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read()));sys.stdout.buffer.flush()"
        result=SP.run_supervised([sys.executable,'-I','-c',child],folder=folder/'transport',owner=c.adapter._owner(key,request,intent),
                                 env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},stdin=base64.b64encode(raw),timeout=3)
        self.assertEqual(result.returncode,0);self.assertTrue(result.cleanup['complete'])
        if settled:
            self.assertEqual(c.ledger.settle(key,request,intent,{'provider_request_id':'msg_local_fixture','response_model':'fixture-response-v1',
                'input_tokens':9,'cached_input_tokens':2,'output_tokens':2,'provider_charge_micro_cny':None,'raw_response_sha256':hashlib.sha256(body).hexdigest()}),'settled')
        else:c.ledger.unknown(key,request,intent,'synthetic_interrupted_settlement')
        originals=c.store.q("SELECT * FROM rsi_prepare_events WHERE pool=? AND kind='settled'",(key,))
        before_raw=(folder/'transport/output.bin').read_bytes()
        return c,key,request,originals,before_raw

    def test_original_zero_exit_invalid_headers_quarantine_old_settlement(self):
        for lengths in [lambda n:['not-a-number'],lambda n:['+'+str(n)],lambda n:[str(n),str(n+17)]]:
            c,key,req,old,raw=self.historical(lengths)
            try:result=c.adapter.reconcile(key,req)
            except ValueError:result={'state':'rejected_without_quarantine'}
            self.assertEqual(result['state'],'unknown')
            self.assertFalse(result['response_complete'])
            self.assertEqual(c.ledger.inspect(key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
            self.assertTrue(c.ledger.inspect(key)['blocked'])
            self.assertEqual(c.store.q("SELECT * FROM rsi_prepare_events WHERE pool=? AND kind='settled'",(key,)),old)
            self.assertEqual((c.adapter._folder(key,req)/'transport/output.bin').read_bytes(),raw)
            count=len(c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,)))
            self.assertEqual(c.adapter.reconcile(key,req)['state'],'unknown')
            self.assertEqual(len(c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,))),count)
            self.assertEqual(c.count,0)

    def test_original_zero_exit_unknown_stays_held(self):
        c,key,req,old,raw=self.historical(lambda n:[str(n+17),str(n)],settled=False)
        try:result=c.adapter.reconcile(key,req)
        except ValueError:result={'state':'rejected'}
        self.assertEqual(result['state'],'unknown')
        self.assertEqual(c.ledger.inspect(key)['totals']['cost_micro_cny'],1400)
        self.assertEqual(c.count,0)

    def test_quarantine_nonce_and_original_settlement_fences_are_atomic(self):
        c,key,req,old,raw=self.historical(lambda n:['not-a-number'])
        token=c.ledger.snapshot(key,req)['attempt']['intent']
        before=c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,))
        with self.assertRaises(L.Conflict):c.ledger.invalidate_framing(key,req,'wrong-nonce')
        self.assertEqual(c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,)),before)
        c.store.x('UPDATE rsi_prepare_attempts SET receipt=?,receipt_hash=? WHERE pool=? AND request_id=?',('{}',L.digest({}),key,req))
        damaged=c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(key,))
        with self.assertRaises(L.Conflict):c.ledger.invalidate_framing(key,req,token)
        self.assertEqual(c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(key,)),damaged)
        self.assertEqual(c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,)),before)
        self.assertEqual(c.store.q('SELECT blocked FROM rsi_prepare_pools WHERE pool=?',(key,))[0]['blocked'],0)

    def test_concurrent_original_reconciliation_quarantines_once(self):
        c,key,req,old,raw=self.historical(lambda n:[str(n),str(n+17)])
        gate=threading.Barrier(3);results=[];errors=[]
        def work():
            try:
                gate.wait(3);results.append(c.adapter.reconcile(key,req))
            except BaseException as error:errors.append(type(error).__name__)
        threads=[threading.Thread(target=work) for _ in range(2)]
        for t in threads:t.start()
        gate.wait(3)
        for t in threads:t.join(5)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(errors,[])
        self.assertEqual([v['state'] for v in results],['unknown','unknown'])
        self.assertEqual(c.ledger.inspect(key)['totals']['cost_micro_cny'],1400)
        self.assertEqual(len(c.store.q("SELECT * FROM rsi_prepare_events WHERE pool=? AND kind='unknown'",(key,))),1)
        self.assertEqual(c.store.q("SELECT * FROM rsi_prepare_events WHERE pool=? AND kind='settled'",(key,)),old)
        self.assertEqual(c.count,0)

    def test_known_bad_framing_cannot_be_settled_by_a_late_direct_callback(self):
        for was_settled in [False,True]:
            with self.subTest(prior_settlement=was_settled):
                c,key,req,old,raw=self.historical(lambda n:['not-a-number'],settled=was_settled)
                token=c.ledger.snapshot(key,req)['attempt']['intent']
                self.assertEqual(c.adapter.reconcile(key,req)['state'],'unknown')
                before=c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,))
                response=raw.split(b'\n',1)[1]
                receipt={'provider_request_id':'msg_local_fixture','response_model':'fixture-response-v1','input_tokens':9,
                         'cached_input_tokens':2,'output_tokens':2,'provider_charge_micro_cny':None,'raw_response_sha256':hashlib.sha256(response).hexdigest()}
                with self.assertRaises(L.Conflict):c.ledger.settle(key,req,token,receipt)
                self.assertEqual(c.ledger.inspect(key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
                self.assertTrue(c.ledger.inspect(key)['blocked'])
                self.assertEqual(c.store.q('SELECT * FROM rsi_prepare_events WHERE pool=?',(key,)),before)

    def test_valid_historical_version_is_not_approved_by_new_parser(self):
        c,key,req,old,raw=self.historical(lambda n:[str(n)])
        with self.assertRaises(L.Conflict):c.adapter.reconcile(key,req)
        self.assertEqual(c.ledger.inspect(key)['totals']['cost_micro_cny'],130)
        self.assertEqual(c.count,0)


class FramingPolicyTests(unittest.TestCase):
    def test_decimal_normalization_and_zero(self):
        self.assertEqual(P.validate_framing([('Content-Length','0004,\t4'),('content-length',' 04 ')],4),('length',4))
        self.assertEqual(P.validate_framing([('Content-Length','0')],0),('length',0))
        self.assertEqual(P.validate_framing([],0),('close',None))
        self.assertEqual(P.validate_framing([('Transfer-Encoding',' Chunked\t')],4),('chunked',None))

    def test_every_original_value_must_be_an_identical_ascii_decimal(self):
        for value in ['+4','-4','4_0','','4,','4,5','４','٤','4\r\n','NaN',str(2**63)]:
            with self.subTest(value=value),self.assertRaises(ValueError):P.validate_framing([('Content-Length',value)],4)
        self.assertEqual(P.validate_framing([('Content-Length',str(2**63-1))]),('length',2**63-1))
        for size in [True,-1,3,5]:
            with self.subTest(size=size),self.assertRaises(ValueError):P.validate_framing([('Content-Length','4')],size)

    def test_transfer_policy_and_header_shape(self):
        for headers in [[('Transfer-Encoding','gzip')],[('Transfer-Encoding','chunked, chunked')],
                        [('Transfer-Encoding','chunked'),('Transfer-Encoding','chunked')],
                        [('Transfer-Encoding','chunked'),('Content-Length','4')],
                        [('Transfer-Encoding','')],None,{},[['Content-Length']],[(1,'4')],[('Bad Name','4')],[('X','bad\nfield')]]:
            with self.subTest(headers=headers),self.assertRaises(ValueError):P.validate_framing(headers,4)
