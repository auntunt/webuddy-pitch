"""G5: graph artifacts record their source; stale and legacy states are honest."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh import graph


class GraphProvenanceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="webuddy-prov-")
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        subprocess.run(["git", "-C", str(self.repo), "init", "-b", "main"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "F"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "f@f"], check=True)
        (self.repo / "a.py").write_text("VALUE = 1\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-m", "base"],
                       check=True, capture_output=True)
        graph.build(self.repo, use_cache=False)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_artifacts_record_source(self):
        for name in ("map.json", "flows.json"):
            data = json.loads((self.repo / ".tmh" / name).read_text())
            self.assertEqual(data["provenance"]["git_commit"], self.git("rev-parse", "HEAD"))
            self.assertTrue(data["provenance"]["index_revision"])
            self.assertTrue(data["provenance"]["generated_at"])
            self.assertTrue(data["provenance"]["snapshot_sha256"])
        g = graph.Graph(self.repo)
        prov = g.provenance()
        self.assertEqual(prov["index_status"], "current")
        g.db.close()

    def test_moved_head_is_stale(self):
        (self.repo / "a.py").write_text("VALUE = 2\n")
        subprocess.run(["git", "-C", str(self.repo), "commit", "-am", "move"], capture_output=True)
        g = graph.Graph(self.repo)
        prov = g.provenance()
        self.assertEqual(prov["index_status"], "stale")
        self.assertNotEqual(prov["git_commit"], self.git("rev-parse", "HEAD"))
        g.db.close()

    def test_legacy_without_provenance_is_unverifiable(self):
        # the graph db is read-only; a legacy artifact is a meta without provenance
        g = graph.Graph(self.repo)
        g.meta = lambda: {}
        prov = g.provenance()
        self.assertEqual(prov["index_status"], "unverifiable")
        self.assertTrue(prov.get("reason"))
        g.db.close()


if __name__ == "__main__":
    unittest.main()
