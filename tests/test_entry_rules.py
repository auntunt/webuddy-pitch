"""Inheritance tracing, entry coverage audit, and model-detected entry rules."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh import codeindex, entry_rules, flow, mapper


class Fixture:
    def __init__(self, root: Path):
        self.root = root

    def put(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return self


def three_level(root):
    """Action → AuditService extends BaseService → BaseDao (SQL lives in the grandparent's method)."""
    f = Fixture(root)
    f.put('struts.xml', '<struts><package namespace="/w"><action name="go" class="demo.AuditAction" method="run"/></package></struts>')
    f.put('demo/AuditAction.java', 'package demo;\npublic class AuditAction {\n private AuditService s = new AuditService();\n public String run() { s.audit(); return "ok"; }\n}')
    f.put('demo/AuditService.java', 'package demo;\npublic class AuditService extends BaseService {\n public void audit() { dao.insert("x"); this.tag(); }\n}')
    f.put('demo/BaseService.java', 'package demo;\npublic class BaseService {\n protected BaseDao dao = new BaseDao();\n protected void tag() { dao.touch(); }\n}')
    f.put('demo/BaseDao.java', 'package demo;\npublic class BaseDao {\n public void insert(String x) { j.execute("INSERT INTO AUDIT_LOG (x) VALUES (?)"); }\n public void touch() { j.execute("UPDATE AUDIT_LOG SET y=1"); }\n}')
    return f


class InheritanceTraceTest(unittest.TestCase):
    def test_db_ops_in_grandparent_class_are_traced(self):
        with tempfile.TemporaryDirectory() as folder:
            three_level(Path(folder))
            res = flow.build_flows(Path(folder), mapper.build_map(Path(folder)), codeindex.build_index(Path(folder)))
            self.assertEqual(len(res['flows']), 1)
            f = res['flows'][0]
            self.assertIn('AUDIT_LOG', f['crud'])
            self.assertEqual(set(f['crud']['AUDIT_LOG']), {'C', 'U'})
            keys = [n['key'] for n in f['nodes']]
            self.assertIn('BaseDao.insert', keys)
            self.assertIn('BaseService.tag', keys)

    def test_field_declared_in_parent_resolves(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Fixture(Path(folder))
            f.put('struts.xml', '<struts><package namespace="/w"><action name="go" class="demo.A" method="run"/></package></struts>')
            f.put('demo/A.java', 'package demo;\npublic class A {\n private Svc svc = new Svc();\n public String run() { svc.doIt(); return "ok"; }\n}')
            f.put('demo/Svc.java', 'package demo;\npublic class Svc extends Mid {\n public void doIt() { dao.insert("x"); }\n}')
            f.put('demo/Mid.java', 'package demo;\npublic class Mid {\n protected BaseDao dao = new BaseDao();\n protected A svc = new A();\n}')
            f.put('demo/BaseDao.java', 'package demo;\npublic class BaseDao {\n public void insert(String x) { j.execute("INSERT INTO T1 (x) VALUES (?)"); }\n}')
            res = flow.build_flows(Path(folder), mapper.build_map(Path(folder)), codeindex.build_index(Path(folder)))
            self.assertIn('T1', res['flows'][0]['crud'])


class CoverageAuditTest(unittest.TestCase):
    def test_uncovered_entry_classes_listed_by_module(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            three_level(root)
            Fixture(root).put('other/demo/GhostAction.java', 'package demo;\npublic class GhostAction extends ActionSupport {\n public String execute() { return "x"; }\n}')
            Fixture(root).put('mod2/demo/TimerJob.java', 'package demo;\npublic class TimerJob extends Job {\n public void run() { }\n}')
            Fixture(root).put('mod2/demo/PlainPojo.java', 'package demo;\npublic class PlainPojo {\n public int x;\n}')
            res = flow.build_flows(root, mapper.build_map(root), codeindex.build_index(root))
            cov = res['entry_coverage']
            names = {u['name'] for u in cov['uncovered']}
            self.assertIn('GhostAction', names)
            self.assertIn('TimerJob', names)
            self.assertNotIn('PlainPojo', names)
            self.assertNotIn('AuditAction', names)  # covered by the flow
            self.assertEqual(cov['total'], len(cov['uncovered']))
            self.assertEqual(cov['per_module'].get('other'), 1)
            self.assertEqual(cov['per_module'].get('mod2'), 1)


class RuleValidationTest(unittest.TestCase):
    def test_valid_document(self):
        rules = entry_rules.validate_document({'framework': 'Struts2', 'rules': [
            {'class_pattern': r'^com\.example\..*Action$', 'extends': 'ActionSupport',
             'method_visibility': 'public', r'method_pattern': r'^do\w+$', 'url_template': '/x/{m}', 'reason': 'Convention 命名'}]})
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]['extends'], 'ActionSupport')

    def test_rejections(self):
        for doc in (['x'], {'rules': []}, {'framework': 1, 'rules': []},
                    {'framework': 'f', 'rules': 'x'},
                    {'framework': 'f', 'rules': [{}]},
                    {'framework': 'f', 'rules': [{'class_pattern': '.*', 'reason': 'too broad'}]},
                    {'framework': 'f', 'rules': [{r'class_pattern': r'^com\.x\.[A-Z', 'reason': 'bad regex'}]},
                    {'framework': 'f', 'rules': [{'class_pattern': '^a$', 'reason': ''}]},
                    {'framework': 'f', 'rules': [{'class_pattern': '^a$', 'reason': 'r', 'shell': 'rm -rf'}]},
                    {'framework': 'f', 'rules': [{'class_pattern': '^a$', 'reason': 'r', 'method_visibility': 'private'}]},
                    {'framework': 'f', 'rules': [{'class_pattern': '^a$', 'reason': 'r'}] * 31}):
            with self.assertRaises(ValueError, msg=str(doc)[:60]):
                entry_rules.validate_document(doc)


class ApplyAndDetectTest(unittest.TestCase):
    def test_stored_rules_create_labelled_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            three_level(root)
            Fixture(root).put('demo/RestEndpoint.java', 'package demo;\npublic class RestEndpoint {\n public String handle() { j.execute("SELECT 1 FROM T2"); return "x"; }\n}')
            (root / '.tmh').mkdir(exist_ok=True)
            (root / '.tmh' / 'entry-rules.json').write_text(json.dumps({
                'framework': 'Fixture', 'rules': [{'class_pattern': r'Endpoint$', 'method_pattern': '^handle$',
                'reason': 'fixture rule'}], 'model': 'stub', 'detected_at': 't', 'input_sha256': 'x'}))
            res = flow.build_flows(root, mapper.build_map(root), codeindex.build_index(root))
            kinds = {f['kind'] for f in res['flows']}
            self.assertIn('模型识别入口（待核实）', kinds)
            labelled = next(f for f in res['flows'] if f['kind'] == '模型识别入口（待核实）')
            self.assertIn('T2', labelled['crud'])
            names = {u['name'] for u in res['entry_coverage']['uncovered']}
            self.assertNotIn('RestEndpoint', names)  # now covered

    def test_detect_with_stubbed_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            three_level(root)
            Fixture(root).put('demo/GhostAction.java', 'package demo;\npublic class GhostAction extends ActionSupport {\n public String execute() { return "x"; }\n}')
            reply = json.dumps({'framework': 'Struts', 'rules': [
                {'class_pattern': r'^demo\.GhostAction$', 'extends': 'ActionSupport',
                 'method_pattern': '^execute$', 'reason': 'name + base'}]})
            conf = {'ready': True, 'model': 'stub-model'}
            result = entry_rules.detect(root, conf, chat=lambda c, s, t: reply)
            self.assertEqual(result['rules'], 1)
            self.assertEqual(result['model'], 'stub-model')
            self.assertEqual(result['coverage_before'], 1)
            self.assertEqual(result['coverage_after'], 0)
            stored = json.loads((root / '.tmh' / 'entry-rules.json').read_text())
            self.assertEqual(stored['model'], 'stub-model')
            self.assertTrue(stored['input_sha256'])

    def test_detect_rejects_invalid_and_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            three_level(root)
            with self.assertRaises(ValueError):
                entry_rules.detect(root, {'ready': False})
            with self.assertRaises(ValueError):
                entry_rules.detect(root, {'ready': True, 'model': 'm'},
                                   chat=lambda c, s, t: json.dumps({'framework': 'f', 'rules': [{'class_pattern': '.*', 'reason': 'x'}]}))
            self.assertFalse((root / '.tmh' / 'entry-rules.json').exists())

    def test_detect_endpoint_route(self):
        from types import SimpleNamespace as NS
        from tmh.platform import server
        P = NS(data_dir=Path(tempfile.mkdtemp()), tenant_context=None,
               project=lambda k: {'key': k, 'root': '/nonexistent', 'id': 1})
        req = NS(user='demo', body={}, h=NS(_who='', headers={}, client_address=('127.0.0.1', 1),
                                            server=NS(server_address=('127.0.0.1', 1))))
        with patch('tmh.platform.llm.conf', return_value={'ready': False}):
            with self.assertRaises(server.ApiError):
                server.api_entries_detect(P, req, 'K')


if __name__ == '__main__':
    unittest.main()
