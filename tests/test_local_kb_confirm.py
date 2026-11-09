"""Account-free KB confirmation: loopback-only browser POST, local-operator actor."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from tmh import kb
from tmh.platform import login, server


class LocalKbConfirmTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.P = NS(data_dir=self.base, tenant_context=None, project=lambda key: {'key': key}, root=lambda p: self.base)
        self.request = NS(user='unverified-display-name', body={'id': 'dom:test', 'note': 'manually reviewed'},
            h=NS(_who='', client_address=('127.0.0.1', 50000),
                 server=NS(server_address=('127.0.0.1', 8790)),
                 headers={'Host': '127.0.0.1:8790', 'Origin': 'http://127.0.0.1:8790',
                          'Sec-Fetch-Site': 'same-origin', 'X-TMH': '1'}))

    def rejected(self, req, accounts=False, platform=None):
        with patch.object(login, 'has_accounts', return_value=accounts), patch.object(kb, 'confirm') as write:
            with self.assertRaises(server.ApiError) as caught:
                server.api_kb_confirm(platform or self.P, req, 'TEST')
            self.assertEqual(caught.exception.code, 403)
            write.assert_not_called()

    def test_local_confirmation_recorded_as_local_operator(self):
        with patch.object(login, 'has_accounts', return_value=False), patch.object(kb, 'confirm') as write:
            self.assertEqual(server.api_kb_confirm(self.P, self.request, 'TEST'), {'ok': True})
        actor = write.call_args.args[2]
        self.assertTrue(actor.startswith('本机操作者('))
        self.assertNotEqual(actor, self.request.user)
        self.assertEqual(write.call_args.args[1], 'dom:test')
        self.assertEqual(write.call_args.args[3], 'manually reviewed')

    def test_rejections(self):
        self.rejected(self.request, accounts=True)
        self.rejected(self.request, platform=NS(**dict(vars(self.P), tenant_context=object())))
        for key, value in [('Origin', 'https://external.example'), ('Origin', ''),
                           ('Sec-Fetch-Site', 'cross-site'), ('X-TMH', ''),
                           ('X-Webuddy-Agent', '1'), ('X-Forwarded-For', '127.0.0.1'),
                           ('Forwarded', 'for=127.0.0.1')]:
            req = copy.deepcopy(self.request)
            req.h.headers[key] = value
            self.rejected(req)
        for field, value in [('client_address', ('192.168.1.2', 1234)),
                             ('server', NS(server_address=('10.1.72.82', 8790)))]:
            req = copy.deepcopy(self.request)
            setattr(req.h, field, value)
            self.rejected(req)
        req = copy.deepcopy(self.request)
        req.body['by'] = 'someone-else'
        self.rejected(req)
        req = copy.deepcopy(self.request)
        req.user = 'agent:test'
        self.rejected(req)
        req = copy.deepcopy(self.request)
        req.h.client_address = ('10.1.72.99', 1234)
        self.rejected(req)
        req.h.client_address = ('127.0.0.1', 1234)
        req.h.headers.update(Host='10.1.72.82:8790', Origin='http://10.1.72.82:8790')
        self.rejected(req)

    def test_lan_listener_still_allows_loopback_browser(self):
        req = copy.deepcopy(self.request)
        req.h.server.server_address = ('0.0.0.0', 8790)
        with patch.object(login, 'has_accounts', return_value=False), patch.object(kb, 'confirm') as write:
            self.assertEqual(server.api_kb_confirm(self.P, req, 'TEST'), {'ok': True})
            write.assert_called_once()

    def test_personal_login_actor_unchanged(self):
        req = copy.deepcopy(self.request)
        req.h._who = 'signed-in-user'
        with patch.object(login, 'has_accounts', return_value=True), patch.object(kb, 'confirm') as write:
            server.api_kb_confirm(self.P, req, 'TEST')
            self.assertEqual(write.call_args.args[2], 'signed-in-user')

    def test_missing_page_still_404(self):
        with patch.object(login, 'has_accounts', return_value=False), \
                patch.object(kb, 'confirm', side_effect=KeyError('missing')):
            with self.assertRaises(server.ApiError) as caught:
                server.api_kb_confirm(self.P, self.request, 'TEST')
            self.assertEqual(caught.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
