"""Isolated inbound contract: no customer server, model, acceptance or outbound write."""
import concurrent.futures
import json
import unittest
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from tests import test_external_candidates as fixtures
from tmh.platform import external_requirements as E
from tmh.platform.errors import ApiError
from tmh.platform.server import make_handler


class ExternalRequirementsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=fixtures.ExternalCandidateTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.P=self.fixture.P
        self.submitted=[]
        dispatch=patch.object(self.P.flow,'submit',side_effect=lambda p,t:self.submitted.append(t['key']))
        dispatch.start()
        self.addCleanup(dispatch.stop)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.P,token='stdio-fixture-token'))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.thread.join,2)
        self.addCleanup(self.http.shutdown)
        self.endpoint='http://127.0.0.1:'+str(self.http.server_port)

    def web(self,path,body=None):
        request=urllib.request.Request(self.endpoint+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'X-TMH-Token':'stdio-fixture-token','X-TMH':'1','Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    async def test_http_inbound_replay_revision_conflict_and_no_automatic_flow(self):
        path=self.fixture.repo/'.tmh/config.json'
        conf=json.loads(path.read_text());conf['integrations']={'tools':{'fixture-group':{'type':'generic','url':'https://fixture.invalid'}}}
        path.write_text(json.dumps(conf))
        body=dict(source='fixture-group',external_id='SCENE-1',revision='v1',previous_revision='',
            source_url='https://fixture.invalid/SCENE-1',title='Policy update',body='Keep 1250 cents',request_id='external-first')
        url='/api/projects/EXT/external-requirements'
        first=self.web(url,body)
        self.assertEqual(self.web(url,body),first)
        self.assertEqual(first['state'],'draft')
        ticket=self.P.store.ticket(first['ticket'])
        self.assertTrue(ticket['links']['hold'])
        self.assertEqual(self.submitted,[])
        update=dict(body,revision='v2',previous_revision='v1',body='Keep 1300 cents',request_id='external-second')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.web(url,update),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0]['ticket'],first['ticket'])
        self.assertEqual(results[0]['state'],'needs_review')
        self.assertEqual(self.P.store.ticket(first['ticket'])['body'],'Keep 1250 cents')
        self.assertEqual(len([e for e in self.P.store.events(ticket['id']) if e['kind']=='external_requirement_revision']),2)
        with self.assertRaises(ApiError):
            E.sync(self.P,self.fixture.p,'web-fixture',dict(update,request_id='out-of-order'))
        with self.assertRaises(ApiError):
            E.sync(self.P,self.fixture.p,'web-fixture',dict(body,source='unconfigured'))
        self.assertEqual(self.submitted,[])
