import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_settings as settings, agents, server, tenant_policy
from tmh.platform.errors import ApiError
from tests.test_tenant_policy import Context
from tmh.platform.store import Store


class AgentSettingsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'agents.json'
        self.path.write_text(json.dumps({'custom': {'title':'Original','cmd':['private-command','private-value'],
                                                  'env': {'TOKEN': 'private-secret'}}}))

    def body(self, name='codex'):
        return {'name': name, 'revision': settings.view(self.root)['revision'],
                'config': {'title':'Configured','models':[['model-x','Model X']],
                           'defaults':{'fix':'model-x'},'timeout':90}}

    def test_safe_projection_and_preserve_unedited_fields(self):
        data = settings.view(self.root)
        self.assertNotIn('private-', json.dumps(data))
        body = self.body('custom')
        settings.save(self.root, body)
        c = json.loads(self.path.read_text())['custom']
        self.assertEqual(c['cmd'], ['private-command','private-value'])
        self.assertEqual(c['env']['TOKEN'], 'private-secret')
        self.assertEqual(c['run_timeout'],90)
        self.assertEqual(agents.pick_model(agents.load_config(self.root)['custom'],'fix',None),'model-x')

    def test_new_codex_alias_and_clear_profile(self):
        body=self.body('team-codex');body['config']['profile']='team'
        settings.save(self.root, body)
        c=agents.load_config(self.root)['team-codex']
        self.assertEqual(c['engine'],'codex');self.assertEqual(c['profile'],'team')
        body=self.body('team-codex');body['config']['profile']=''
        settings.save(self.root,body)
        self.assertNotIn('profile',agents.load_config(self.root)['team-codex'])

    def test_stale_write_rejected_and_invalid_values_do_not_mutate(self):
        old=self.body();settings.save(self.root,self.body())
        with self.assertRaises(ApiError) as error:settings.save(self.root,old)
        self.assertEqual(error.exception.code,409)
        for changes in ({'cmd':['sh']},{'timeout':True},{'defaults':{'fix':'unknown'}},
                        {'models':[['x','X'],['x','Again']]},{'profile':'../secret'}):
            before=self.path.read_bytes();body=self.body();body['config'].update(changes)
            with self.assertRaises(ApiError):settings.save(self.root,body)
            self.assertEqual(before,self.path.read_bytes())

    def test_invalid_existing_file_not_overwritten(self):
        self.path.write_text('{broken')
        with self.assertRaises(ApiError):settings.view(self.root)
        self.assertEqual(self.path.read_text(),'{broken')

    def test_tenant_admin_can_read_but_only_host_owner_can_write(self):
        store=Store(self.root/'platform.db');self.addCleanup(store.db.close)
        ctx=Context(self.root);ctx.tenant_id='default';P=SimpleNamespace(store=store,data_dir=self.root,tenant_context=ctx)
        tenant_policy.authorize(P,'GET','/api/agent-settings',{}, {},'admin')
        for actor in ('admin','alice','reader'):
            with self.assertRaises(ApiError):tenant_policy.authorize(P,'POST','/api/agent-settings',{},self.body(),actor)
        tenant_policy.authorize(P,'POST','/api/agent-settings',{},self.body(),'owner')
        ctx.trusted_host=lambda:False
        req=SimpleNamespace(user='owner',body=self.body(),h=SimpleNamespace(_who='owner',headers={}))
        with self.assertRaises(ApiError):server.api_agent_settings_save(P,req)
        ctx.trusted_host=lambda:True
        self.assertTrue(server.api_agent_settings_save(P,req)['can_edit'])
        req.h.headers={'X-Webuddy-Agent':'bot'}
        with self.assertRaises(ApiError):server.api_agent_settings_save(P,req)
