"""Original event anchors survive local projection damage; preserve red fixtures."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tmh.platform.store import Store
from tests.test_rsi_trial_preparation import M, contract, receipt, h


class TrialIntegrityTests(unittest.TestCase):
    def setUp(self):
        saved=os.environ.get('RSI_INTEGRITY_EVIDENCE_DIR')
        if saved:
            self.root=Path(saved)/self._testMethodName;self.root.mkdir(parents=True,exist_ok=False)
        else:
            self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.addCleanup(self.tmp.cleanup)
        self.preserve=bool(saved)
        self.store=Store(self.root/'store.db');self.addCleanup(self.store.db.close)
        self.ledger=M.Ledger(self.store,wall_us=lambda:1000)
        self.c=contract();self.key=self.ledger.create(self.c)
        if self.preserve:(self.root/'contract.json').write_text(M.encoded(self.c))

    def snapshot(self,name):
        values={t:self.store.q('SELECT * FROM '+t+' ORDER BY rowid') for t in ['rsi_prepare_pools','rsi_prepare_attempts','rsi_prepare_holdouts','rsi_prepare_events']}
        if self.preserve:(self.root/(name+'.json')).write_text(M.encoded(values))
        return values

    def tearDown(self):
        if self.preserve:
            self.snapshot('final')
            db=sqlite3.connect(self.root/'final.sqlite')
            try:self.store.db.backup(db)
            finally:db.close()

    def orphan(self):
        self.ledger.consume_holdout(self.key);self.snapshot('before-damage')
        self.store.x('DELETE FROM rsi_prepare_pools WHERE pool=?',(self.key,))
        self.store.x('DELETE FROM rsi_prepare_holdouts WHERE pool=?',(self.key,))
        self.snapshot('after-damage')

    def settled(self):
        self.ledger.reserve(self.key,'request','propose',10,10)
        token=self.ledger.intent(self.key,'request')['intent']
        self.ledger.settle(self.key,'request',token,receipt());self.snapshot('before-damage')
        return token

    def test_orphan_original_consume_event_prevents_same_scope_reuse(self):
        self.orphan();c=copy.deepcopy(self.c);c['root_family']='replacement';other=self.ledger.create(c)
        before=self.snapshot('before-retry')
        with self.assertRaises(M.Conflict):self.ledger.consume_holdout(other)
        self.assertEqual(self.snapshot('after-retry'),before)

    def test_known_orphan_other_scope_does_not_block_unrelated_consumption(self):
        self.orphan();c=copy.deepcopy(self.c);c['root_family']='other-scope';c['project_id']=2
        other=self.ledger.create(c)
        self.assertTrue(self.ledger.consume_holdout(other))
        self.assertFalse(self.ledger.consume_holdout(other))

    def test_receipt_only_damage_rejects_original_settlement_replay(self):
        token=self.settled();row=self.store.one('SELECT receipt FROM rsi_prepare_attempts WHERE pool=?',(self.key,));value=json.loads(row['receipt']);value['accounted_micro_cny']=0
        self.store.x('UPDATE rsi_prepare_attempts SET receipt=? WHERE pool=?',(M.encoded(value),self.key))
        before=self.snapshot('before-replay')
        with self.assertRaises(M.Conflict):self.ledger.settle(self.key,'request',token,receipt())
        self.assertEqual(self.snapshot('after-replay'),before)

    def test_receipt_and_hash_damage_rejects_matching_changed_input(self):
        token=self.settled();value=dict(receipt(provider_charge_micro_cny=71),accounted_micro_cny=71,cost_source='provider_receipt',pricing_sha256=self.c['price']['reference_sha256'])
        self.store.x('UPDATE rsi_prepare_attempts SET receipt=?,receipt_hash=? WHERE pool=?',(M.encoded(value),M.digest(value),self.key))
        before=self.snapshot('before-replay')
        with self.assertRaises(M.Conflict):self.ledger.settle(self.key,'request',token,receipt(provider_charge_micro_cny=71))
        self.assertEqual(self.snapshot('after-replay'),before)

    def test_legacy_duplicate_projection_cannot_dispatch_terminal(self):
        self.orphan();c=copy.deepcopy(self.c);c['root_family']='old-unsafe-projection';other=self.ledger.create(c)
        scope=M.digest([c['tenant_id'],c['project_id']])
        for row in c['holdout_cases']:
            self.store.x('INSERT INTO rsi_prepare_holdouts VALUES(?,?,?,?)',(scope,row['input_sha256'],other,row['source_family']))
        consume={'candidate_sha256':c['candidate_sha256'],'cases':c['holdout_cases']}
        self.store.x('INSERT INTO rsi_prepare_events(pool,request_id,kind,payload,payload_hash) VALUES(?,?,?,?,?)',(other,'','consume_holdout',M.encoded(consume),M.digest(consume)))
        before=self.snapshot('before-reserve')
        with self.assertRaises(M.Conflict):self.ledger.reserve(other,'baseline','baseline',10,10)
        self.assertEqual(self.snapshot('after-reserve'),before)
        body={'phase':'baseline','input_limit':10,'output_limit':10,'reserved_micro_cny':300,'contract_hash':M.digest(c)}
        self.store.x("INSERT INTO rsi_prepare_attempts VALUES(?,?,?,?,'reserved','','','')",(other,'legacy',M.encoded(body),M.digest(body)))
        self.store.x('INSERT INTO rsi_prepare_events(pool,request_id,kind,payload,payload_hash) VALUES(?,?,?,?,?)',(other,'legacy','reserve',M.encoded(body),M.digest(body)))
        before=self.snapshot('before-intent')
        with self.assertRaises(M.Conflict):self.ledger.intent(other,'legacy')
        self.assertEqual(self.snapshot('after-intent'),before)

    def test_intact_settlement_replay_remains_read_only_and_idempotent(self):
        token=self.settled();before=self.snapshot('before-replay')
        self.assertEqual(self.ledger.settle(self.key,'request',token,receipt()),'settled')
        self.assertEqual(self.snapshot('after-replay'),before)

    def test_unknown_late_receipt_still_settles_without_reopening_pool(self):
        self.ledger.reserve(self.key,'request','propose',10,10);token=self.ledger.intent(self.key,'request')['intent'];self.ledger.cancel(self.key,'request')
        self.assertEqual(self.ledger.settle(self.key,'request',token,receipt()),'settled')
        self.assertTrue(self.ledger.inspect(self.key)['blocked'])
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key,'replacement','retry',10,10)
