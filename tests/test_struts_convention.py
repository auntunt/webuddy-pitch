"""Struts Convention/Gboat entries: labelled candidates, XML actions, no fabricated traces."""
import tempfile
import unittest
from pathlib import Path

from tmh import codeindex, flow, graph, mapper


class StrutsConventionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def fixture(self):
        self.put('sales/src/main/resources/struts.xml', '<struts><constant name="struts.convention.package.locators.basePackage" value="demo.sales.action" /></struts>')
        self.put('sales/src/main/java/demo/sales/action/SalesAction.java', '''package demo.sales.action;
public class SalesAction extends BaseActionSupport {
 public String execute() { return "list"; }
 public void publish() { audit(); }
 public String getTitle() { return "title"; }
 public void setTitle(String value) { }
 public static String helper() { return "x"; }
 protected String internal() { return "x"; }
 public void withArgument(String value) { }
 public void validate() { }
 private void audit() { }
}''')
        self.put('other/src/main/java/demo/sales/action/OtherAction.java', '''package demo.sales.action;
public class OtherAction {
 public String execute() { return "outside configured module"; }
}''')

    def test_convention_scope_and_public_actions(self):
        self.fixture()
        m = mapper.build_map(self.root)
        entries = [e for e in m['endpoints'] if e['stack'] == 'struts-convention']
        self.assertEqual({e['handler'] for e in entries},
                         {'demo.sales.action.SalesAction.execute', 'demo.sales.action.SalesAction.publish'})
        self.assertTrue(all(e['line'] > 0 and e['limitations'] and e['scope'] for e in entries))
        result = flow.build_flows(self.root, m, codeindex.build_index(self.root))
        self.assertEqual(len(result['flows']), 2)
        self.assertTrue(all(f['kind'] == '约定入口（待核实）' for f in result['flows']))

    def test_explicit_method_and_namespace(self):
        self.put('struts.xml', '<struts><package name="p" namespace="/orders"><action name="save" class="demo.SaveAction" method="persist"/><action name="list" class="demo.SaveAction"/></package></struts>')
        m = mapper.build_map(self.root)
        self.assertEqual([(e['path'], e['handler']) for e in m['endpoints']],
                         [('/orders/save', 'demo.SaveAction.persist'), ('/orders/list', 'demo.SaveAction.execute')])

    def test_no_configuration_no_guessed_entry(self):
        self.put('HelloAction.java', 'public class HelloAction {\n public String execute() { return "ok"; }\n}')
        self.assertEqual(mapper.build_map(self.root)['endpoints'], [])

    def test_duplicate_class_names_not_mistraced(self):
        self.fixture()
        self.put('duplicate/SalesAction.java', 'package other;\npublic class SalesAction {\n public String execute() { return "wrong"; }\n}')
        m = mapper.build_map(self.root)
        result = flow.build_flows(self.root, m, codeindex.build_index(self.root))
        self.assertEqual(result['flows'], [])
        self.assertEqual(len(result['struts_analysis']['ambiguous_candidates']), 2)

    def test_complete_graph_in_temporary_fixture(self):
        self.fixture()
        result = graph.build(self.root, use_cache=False)
        self.assertEqual(result['kinds']['flow'], 2)
        self.assertGreaterEqual(result['domains'], 1)
        self.assertTrue((self.root / '.tmh/map.json').is_file())


if __name__ == '__main__':
    unittest.main()
