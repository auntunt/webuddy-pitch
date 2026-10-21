"""G4 local pilot invariants (`tools/g4_local_pilot.py` pure helpers).

These tests keep the *mechanism* honest without needing the full example repo:
a fixed revision must not move when the source HEAD moves, cache reuse needs the
same analyzer, retrieval never merges two sources' same-named pages, derivation
never writes to the source, and only explicitly bound sources are searchable.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("TMH_UNDERSTAND", "rules")

TOOLS = REPO / "tools" / "g4_local_pilot.py"
_spec = importlib.util.spec_from_file_location("g4_local_pilot", TOOLS)
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)

PAGE = """---
id: flow:get-leave-list
title: {title}
status: 已确认
---
# {title}

{summary}
"""


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    if p.returncode != 0:
        raise AssertionError("command failed: %s\n%s" % (" ".join(cmd), (p.stdout + p.stderr)[-500:]))
    return p.stdout


def tiny_repo(root: Path, title: str, summary: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "src" / "LeaveService.java").write_text("class LeaveService {}\n", encoding="utf-8")
    kb = root / ".tmh" / "knowledge" / "flows"
    kb.mkdir(parents=True)
    (kb / "get-leave-list.md").write_text(PAGE.format(title=title, summary=summary), encoding="utf-8")
    run(["git", "init", "-q"], root)
    run(["git", "add", "-A"], root)
    run(["git", "-c", "user.name=t", "-c", "user.email=t@local", "commit", "-q", "-m", "one"], root)
    return root


class G4LocalPilotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g4pilot-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_fixed_revision_does_not_move_when_source_head_moves(self):
        repo = tiny_repo(self.tmp / "std", "请假列表", "原始说明")
        commit_a = pilot.git(repo, "rev-parse", "HEAD")
        rev = pilot.snapshot(repo, commit_a, self.tmp / "snap")
        (repo / "src" / "LeaveService.java").write_text("class LeaveService { int v2; }\n", encoding="utf-8")
        run(["git", "-c", "user.name=t", "-c", "user.email=t@local", "commit", "-q", "-am", "two"], repo)
        commit_b = pilot.git(repo, "rev-parse", "HEAD")
        self.assertNotEqual(commit_a, commit_b)
        kept = json.loads((self.tmp / "snap" / "revision.json").read_text(encoding="utf-8"))
        self.assertEqual(kept["commit"], commit_a)
        self.assertEqual(kept["digest"], rev["digest"])
        self.assertEqual(kept["source_manifest"], rev["source_manifest"])
        # the snapshot's bytes are the old commit's bytes, not the new HEAD's
        self.assertNotIn("int v2", (Path(rev["root"]) / "src" / "LeaveService.java").read_text(encoding="utf-8"))

    def test_cache_reuse_requires_same_analyzer(self):
        repo = tiny_repo(self.tmp / "std2", "审批", "说明")
        rev = pilot.snapshot(repo, pilot.git(repo, "rev-parse", "HEAD"), self.tmp / "snap2")
        self.assertTrue(pilot.reuse_is_safe(rev, rev["analyzer"]))
        self.assertFalse(pilot.reuse_is_safe(rev, rev["analyzer"] + "-changed"))
        self.assertFalse(pilot.reuse_is_safe({"analyzer": ""}, "x"))

    def test_retrieval_keeps_two_sources_separate_and_only_bound_sources(self):
        a = tiny_repo(self.tmp / "oa", "审批通过", "OA：写审批日志")
        b = tiny_repo(self.tmp / "crm", "审批通过", "CRM：生成合同版本")
        sources = [{"label": "OA", "root": str(a), "commit": "c1", "revision": "r1"},
                   {"label": "CRM", "root": str(b), "commit": "c2", "revision": ""}]
        hits = pilot.search_sources(sources, "审批")
        self.assertEqual({h["source"] for h in hits}, {"OA", "CRM"})
        self.assertTrue(all(h["commit"] for h in hits))
        by_source = {h["source"]: h for h in hits}
        self.assertEqual(by_source["OA"]["page"], by_source["CRM"]["page"])  # same page id...
        self.assertNotEqual(by_source["OA"]["source"], by_source["CRM"]["source"])  # ...but never merged
        # only the bound sources are searched: dropping CRM removes it entirely
        only_oa = pilot.search_sources(sources[:1], "审批")
        self.assertEqual({h["source"] for h in only_oa}, {"OA"})

    def test_derivation_never_writes_to_the_source(self):
        repo = tiny_repo(self.tmp / "std3", "审批", "说明")
        rev = pilot.snapshot(repo, pilot.git(repo, "rev-parse", "HEAD"), self.tmp / "snap3")
        before = pilot.tree_hashes(repo)
        derived = self.tmp / "derived"
        __import__("shutil").copytree(Path(rev["root"]), derived)
        (derived / "src" / "LeaveService.java").write_text("class LeaveService { int changed; }\n", encoding="utf-8")
        self.assertEqual(pilot.tree_hashes(repo), before)
        self.assertNotEqual(pilot.sha256_file(derived / "src" / "LeaveService.java"),
                            pilot.sha256_file(repo / "src" / "LeaveService.java"))

    def test_binding_only_accepts_explicit_records(self):
        binding = self.tmp / "bindings.json"
        rev = {"digest": "d" * 64, "commit": "c" * 40, "analyzer": "a", "root": str(self.tmp)}
        pilot.bind(binding, "CLIENT", rev, ["src"], "参考审批")
        doc = pilot.load_binding(binding)
        self.assertEqual(len(doc["bindings"]), 1)
        self.assertEqual(doc["bindings"][0]["customer"], "CLIENT")
        self.assertEqual(doc["bindings"][0]["scopes"], ["src"])
        # rebinding the same revision is idempotent, a new revision is a new binding
        pilot.bind(binding, "CLIENT", rev, ["src"], "参考审批")
        self.assertEqual(len(pilot.load_binding(binding)["bindings"]), 1)
        pilot.bind(binding, "CLIENT", dict(rev, digest="e" * 64), ["src"], "参考审批")
        self.assertEqual(len(pilot.load_binding(binding)["bindings"]), 2)


if __name__ == "__main__":
    unittest.main()
