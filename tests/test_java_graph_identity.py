import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from tmh import graph
from tmh.flow import FlowBuilder


class JavaIdentityTest(unittest.TestCase):
    def test_duplicate_types_overloads_and_nested_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {
                'a/Service.java': 'package a; public class Service { public void run(String s) { save(s); } public void run(String[] s) { remove(s); } }',
                'b/Service.java': 'package b; public class Service { public void run(int n) { other(n); } }',
                'a/Worker.java': 'package a; public class Worker { public void act(int n) { one(n); } public void act(String n) { two(n); } }',
                'a/Outer.java': 'package a; class Outer { class Inner { void call() {} } }',
            }
            for name, source in sources.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            result = graph.build(root, use_cache=False)
            with sqlite3.connect(graph.graph_path(root)) as db:
                declarations = db.execute("SELECT id,file,data FROM nodes WHERE kind='declaration'").fetchall()
                self.assertEqual(len(declarations), 6)
                self.assertEqual(len({row[0] for row in declarations}), 6)
                self.assertTrue(any('a.Outer.Inner' in row[0] for row in declarations))
                self.assertTrue(any('String[] s' in row[0] for row in declarations))
                self.assertEqual(db.execute("SELECT count(*) FROM nodes WHERE id='fn:Service.run'").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM nodes WHERE kind='fn' AND name='run'").fetchone()[0], 2)
            self.assertEqual(len(result['diagnostics']), 4)
            builder = FlowBuilder(root)
            self.assertIsNone(builder._class('Service'))
            trace = builder.trace('Worker', 'act')
            self.assertTrue(trace['unresolved'])
            self.assertEqual(len(trace['nodes']), 1)
            self.assertEqual(trace['data_ops'], [])
