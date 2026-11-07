"""Actual indexed bytes, rather than checkout labels, define graph provenance."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tmh import graph
from tmh.context_pack import _source

class GraphProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.file=self.root/'refund.py'
        self.file.write_text('def refund(amount):\n    return amount\n')
        self.git('init','-q');self.git('add','.');self.git('-c','user.name=fixture','-c','user.email=f@invalid','commit','-qm','A')
        self.a=self.git('rev-parse','HEAD').strip()
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],text=True)
    def test_old_index_never_borrows_new_checkout_and_source_is_fixed(self):
        graph.build(self.root);self.file.write_text('def renamed(amount):\n    return 0\n')
        self.git('add','refund.py');self.git('-c','user.name=fixture','-c','user.email=f@invalid','commit','-qm','B')
        source=_source(self.root,0)
        self.assertEqual(source['revision'],self.a)
        self.assertEqual(source['index_status'],'stale')
        g=graph.Graph(self.root);self.addCleanup(g.db.close)
        self.assertIn(b'return amount',g.source_bytes('refund.py'))
        self.assertTrue(any(n['name']=='refund' for n in g.nodes('fn')))
        self.assertFalse(any(n['name']=='renamed' for n in g.nodes('fn')))
    def test_dirty_snapshot_delete_rebuild_and_legacy_unknown(self):
        self.file.write_text('def refund(amount):\n    return amount * 2\n');graph.build(self.root)
        g=graph.Graph(self.root);self.addCleanup(g.db.close)
        self.assertTrue(g.provenance()['source_version'].startswith('snapshot:'))
        self.assertIn(b'amount * 2',g.source_bytes('refund.py'))
        g.db.close();self.file.unlink();graph.build(self.root)
        g=graph.Graph(self.root);self.addCleanup(g.db.close)
        self.assertFalse(g.nodes('fn'));g.db.close()
        import sqlite3
        with sqlite3.connect(graph.graph_path(self.root)) as db:db.execute("DELETE FROM meta WHERE k='provenance'")
        source=_source(self.root,0)
        self.assertEqual(source['revision'],'');self.assertEqual(source['index_status'],'unverifiable')
    def test_interrupted_build_does_not_replace_published_index(self):
        graph.build(self.root);old=graph.graph_path(self.root).read_bytes()
        with patch('tmh.graph.git_churn',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):graph.build(self.root)
        self.assertEqual(graph.graph_path(self.root).read_bytes(),old)
