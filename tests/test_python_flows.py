"""Real AST and graph behavior on the archived BOOTV2 source, never imported/executed."""
import tempfile
import unittest
from pathlib import Path

from tmh import codeindex, flow, graph, mapper, query

BOOTV2 = Path(__file__).resolve().parents[1] / 'docs/self-improvement/evidence/runtime-2026-10-18/bootv2/candidate/app.py'


class PythonFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-python-flow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def boot(self):
        self.write('app.py', BOOTV2.read_text(encoding='utf-8'))
        return flow.build_flows(self.root)

    def test_bootv2_dispatchers_reach_real_local_calls_and_sql(self):
        result = self.boot()
        self.assertEqual(len(result['flows']), 2)
        by = {f['handler'].rsplit('.', 1)[-1]: f for f in result['flows']}
        self.assertEqual(set(by), {'do_GET', 'do_POST'})
        for method, helper in [('do_GET', 'get'), ('do_POST', 'post')]:
            f = by[method]
            keys = {n['key'] for n in f['nodes']}
            for name in (method, helper, 'edit_id', 'edit_page'):
                self.assertIn('py:app.py::make_server.Handler.' + name, keys)
            self.assertIn('ITEMS', f['crud'])
            self.assertTrue(all(n['end_line'] >= n['line'] for n in f['nodes'] if n['file']))
        self.assertEqual(by['do_GET']['crud']['ITEMS'], 'R')
        self.assertEqual(by['do_POST']['crud']['ITEMS'], 'CRU')

    def test_dispatcher_is_not_an_invented_edit_url(self):
        self.boot()
        m = mapper.build_map(self.root)
        self.assertEqual(len(m['endpoints']), 2)
        for endpoint in m['endpoints']:
            self.assertEqual(endpoint['scope'], 'dispatcher')
            self.assertIsNone(endpoint['url'])
            self.assertNotIn('/edit', endpoint['path'])
        for f in flow.build_flows(self.root)['flows']:
            self.assertEqual(f['scope'], 'dispatcher')
            self.assertIn('具体 URL', f['limitations'])

    def test_graph_has_python_file_methods_calls_and_table_edges(self):
        self.boot()
        built = graph.build(self.root, use_cache=False)
        g = graph.Graph(self.root)
        self.addCleanup(g.db.close)
        self.assertIsNotNone(g.node('file:app.py'))
        self.assertIsNotNone(g.node('fn:py:app.py::make_server.Handler.edit_page'))
        self.assertIsNotNone(g.node('tbl:ITEMS'))
        self.assertEqual(len(g.nodes('flow')), 2)
        self.assertEqual(g.node('file:app.py')['data']['analysis_status'], 'parsed')
        self.assertEqual(built['diagnostics'], [])

    def test_same_names_in_modules_and_classes_never_cross_link(self):
        template = '''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        return self.read()
    def read(self):
        return {value!r}
class Other:
    def read(self):
        return 'unreachable'
server = HTTPServer(('localhost', 0), Handler)
'''
        self.write('a.py', template.format(value='a'))
        self.write('pkg/a.py', template.format(value='b'))
        result = flow.build_flows(self.root)
        self.assertEqual(len(result['flows']), 2)
        for f in result['flows']:
            self.assertTrue(all(n['file'] == f['file'] for n in f['nodes'] if n['file']))
            self.assertFalse(any('Other' in n['key'] for n in f['nodes']))
            self.assertEqual(len(f['nodes']), 2)

    def test_invalid_python_is_unknown_in_map_flow_and_graph(self):
        self.write('broken.py', 'def broken(:\n')
        for result in (codeindex.build_index(self.root), mapper.build_map(self.root), flow.build_flows(self.root)):
            self.assertTrue(any(d['file'] == 'broken.py' and d['status'] == 'unknown' and d['kind'] == 'parse'
                                for d in result['diagnostics']))
        graph.build(self.root, use_cache=False)
        g = graph.Graph(self.root)
        self.addCleanup(g.db.close)
        self.assertEqual(g.node('file:broken.py')['data']['analysis_status'], 'unknown')

    def test_dynamic_sql_and_calls_are_unresolved_without_fake_tables(self):
        self.write('app.py', '''import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with sqlite3.connect('x.db') as db:
            db.execute('SELECT * FROM ' + self.table)
            db.execute('SELECT id FROM actual WHERE id=?', (1,))
        getattr(self, self.operation)()
server = HTTPServer(('localhost', 0), Handler)
''')
        f = flow.build_flows(self.root)['flows'][0]
        self.assertEqual(f['crud'], {'ACTUAL': 'R'})
        self.assertTrue(any('SQL' in u['why'] for u in f['unresolved']))
        self.assertTrue(any('动态' in u['why'] for u in f['unresolved']))

    def test_nested_unreachable_function_is_not_a_dispatcher_step(self):
        self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
def factory():
    def hidden():
        return 'not called'
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            return visible()
    def visible():
        return 'called'
    return HTTPServer(('localhost', 0), Handler)
''')
        f = flow.build_flows(self.root)['flows'][0]
        self.assertIn('py:app.py::factory.visible', {n['key'] for n in f['nodes']})
        self.assertNotIn('py:app.py::factory.hidden', {n['key'] for n in f['nodes']})
        self.assertNotIn('py:app.py.factory', {n['key'] for n in f['nodes']})

    def test_shadowed_function_and_duplicate_defs_are_not_guessed(self):
        self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
def task():
    return 'first'
def task():
    return 'second'
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        task()
        helper = self.choose()
        helper()
    def helper(self):
        return 'not selected'
server = HTTPServer(('localhost', 0), Handler)
''')
        f = flow.build_flows(self.root)['flows'][0]
        self.assertFalse(any(n['key'].endswith(('.task', '.helper')) for n in f['nodes']))
        self.assertGreaterEqual(len(f['unresolved']), 2)

    def test_static_local_import_alias_resolves_to_exact_module(self):
        self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
from service import read as fetch
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        return fetch()
server = HTTPServer(('localhost', 0), Handler)
''')
        self.write('service.py', 'def read():\n    return 7\n')
        self.write('other.py', 'def read():\n    return 8\n')
        f = flow.build_flows(self.root)['flows'][0]
        self.assertIn('py:service.py.read', {n['key'] for n in f['nodes']})
        self.assertNotIn('py:other.py.read', {n['key'] for n in f['nodes']})

    def test_cached_rebuild_matches_uncached_python_graph(self):
        self.boot()
        a = graph.build(self.root, use_cache=True)
        b = graph.build(self.root, use_cache=True)
        self.assertEqual(a['flows'], b['flows'])
        self.assertEqual(a['diagnostics'], b['diagnostics'])
        self.assertGreater(b['cached'], 0)

    def test_unregistered_and_custom_server_names_do_not_create_entries(self):
        for registration in ('', "HTTPServer(('localhost', 0), Handler)"):
            with self.subTest(registration=registration):
                self.write('app.py', '''from http.server import BaseHTTPRequestHandler
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        return 'not registered'
def HTTPServer(*args):
    return None
''' + registration)
                self.assertEqual(flow.build_flows(self.root)['flows'], [])
                self.assertTrue(codeindex.build_index(self.root)['classes'])

    def test_method_replaced_by_instance_or_class_assignment_is_not_guessed(self):
        for change in ('    def __init__(self):\n        self.read = choose()\n', ''):
            with self.subTest(change=change):
                self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        return self.read()
    def read(self):
        return 'original'
''' + change + ('' if change else 'Handler.read = choose()\n') + "HTTPServer(('localhost',0), Handler)\n")
                f = flow.build_flows(self.root)['flows'][0]
                self.assertNotIn('py:app.py::Handler.read', {n['key'] for n in f['nodes']})
                self.assertTrue(any(u['call'] == 'self.read' for u in f['unresolved']))

    def test_unknown_decorator_cannot_prove_a_registered_handler_callable(self):
        self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    @replace_with_another_function
    def do_GET(self):
        return 'not necessarily executed'
HTTPServer(('localhost',0), Handler)
''')
        result = flow.build_flows(self.root)
        self.assertEqual(result['flows'], [])
        self.assertTrue(any(d['kind'] == 'entry' for d in result['diagnostics']))

    def test_python_navigation_returns_real_definitions_and_table_users(self):
        self.boot()
        found = query.where(self.root, ['edit_page'])
        self.assertTrue(any(row['file'] == 'app.py' for row in found))
        result = query.impact(self.root, 'ITEMS')
        self.assertIn('app.py', result['table_users'])

    def test_unknown_class_decorator_cannot_prove_the_registered_handler(self):
        self.write('app.py', '''from http.server import BaseHTTPRequestHandler, HTTPServer
@replace_entire_class
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        return 'original class may not be registered'
HTTPServer(('localhost', 0), Handler)
''')
        result = flow.build_flows(self.root)
        self.assertEqual(result['flows'], [])
        self.assertTrue(any(d['kind'] == 'entry' for d in result['diagnostics']))


if __name__ == '__main__':
    unittest.main()
