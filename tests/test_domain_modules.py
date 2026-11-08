"""Convention candidates keep their source-module boundary in domain clustering."""
import json
import tempfile
import unittest
from pathlib import Path

from tmh import domains


def flow(key, module):
    return {'id': key, 'scope': 'source-backed-action-candidate', 'kind': '约定入口（待核实）',
            'file': module + '/src/Action.java', 'handler': key + '.execute',
            'crud': {'SHARED_TABLE': ['U']}, 'nodes': []}


class DomainModuleTest(unittest.TestCase):
    def test_shared_tables_do_not_merge_modules(self):
        flows = [flow('statistics', 'statistic'), flow('data', 'exchange-data'), flow('publish', 'publish')]
        groups, keys = domains.cluster(flows, {})
        self.assertEqual(len(groups), 3)
        self.assertEqual({f['id']: m for f, m in zip(flows, ('statistic', 'exchange-data', 'publish'))}, keys)

    def test_assign_uses_module_groups(self):
        flows = [flow('statistics', 'statistic'), flow('data', 'exchange-data'), flow('publish', 'publish')]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p = domains.domains_path(root)
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'domains': {}, 'assign': {}}), encoding='utf-8')
            result = domains.assign(root, flows, {}, [])
            self.assertEqual(len(result['domains']), 3)
            self.assertEqual(result['domains']['statistic']['flows'], ['statistics'])

    def test_plain_flows_cluster_as_before(self):
        f = {'id': 'a', 'kind': '接口', 'handler': 'Order.save', 'crud': {'ORDERS': ['C']}, 'nodes': []}
        groups, keys = domains.cluster([f], {})
        self.assertEqual(groups, [['a']])
        self.assertEqual(keys, {'a': 'order'})


if __name__ == '__main__':
    unittest.main()
