"""Seed an isolated fixture for the /next/ frontend e2e: git repo + platform data.

Creates tests/e2e/.runtime/{repo,data}: a multi-module Python repo with real tests,
a registered project, one ticket with a confirmed development contract, an
assignment to the serve user, and three verified candidates (wrong / gate-blocked /
correct). Idempotent: removes .runtime first. Sample-only, never customer data.
"""
import getpass
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RUNTIME = Path(__file__).resolve().parent / ".runtime"
REPO = RUNTIME / "repo"
DATA = RUNTIME / "data"
USER = "e2e-user"


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def build_repo():
    shutil.rmtree(RUNTIME, ignore_errors=True)
    REPO.mkdir(parents=True)
    DATA.mkdir(parents=True)
    git("init", "-b", "main")
    git("config", "user.name", "E2E"); git("config", "user.email", "e@e")
    (REPO / "rules.py").write_text("TAX_RATE = 0.10\n")
    (REPO / "service.py").write_text('from rules import TAX_RATE\n\ndef total(price):\n    return round(price * (1 + TAX_RATE), 2)\n')
    (REPO / "export.py").write_text('from service import total\n\ndef render(price):\n    return "TOTAL=%.2f" % total(price)\n')
    (REPO / "tests").mkdir()
    (REPO / "tests/test_flow.py").write_text(
        'import unittest\nfrom rules import TAX_RATE\nfrom export import render\n'
        'class F(unittest.TestCase):\n'
        ' def test_propagates(self):\n  self.assertEqual(render(100), "TOTAL=%.2f" % round(100*(1+TAX_RATE),2))\n')
    (REPO / ".gitignore").write_text("__pycache__/\n")
    (REPO / ".tmh").mkdir()
    (REPO / ".tmh/config.json").write_text(json.dumps({"commands": {
        "build": sys.executable + " -m py_compile rules.py service.py export.py",
        "test": sys.executable + " -m unittest discover -s tests -v"}}))
    git("add", "."); git("commit", "-m", "baseline")
    return git("rev-parse", "HEAD")


def seed(base):
    from tmh.platform import agent_api, candidates, development, team
    from tmh.platform.server import Platform, Req

    P = Platform(DATA, user=USER)
    P.store.add_project("E2E", "E2E sample", str(REPO))

    def call(op, args, actor="writer"):
        h = {"X-Webuddy-Execution": "1", "X-Webuddy-Agent": actor}
        return agent_api.dispatch(P, Req(SimpleNamespace(headers=h), {}, args, USER), op)

    ticket = call("ticket_create", {"project": "E2E", "title": "Propagate tax rate to export",
                                    "body": "Export must reflect the configured rate.", "request_id": "t1"})["ticket"]
    criteria = [{"id": "A1", "text": "render uses configured rate", "check": "test_propagates passes"}]

    team.schema(P)
    t = P.store.ticket(ticket["key"])
    P.store.update_ticket(t["id"], USER, assignee=USER)
    P.store.db.execute(
        "INSERT INTO ticket_team(ticket_id,reviewer,revision,updated,updated_by) VALUES(?,?,?,?,?)",
        (t["id"], "e2e-reviewer", 1, "2026-01-01 00:00:00", USER))
    P.store.db.commit()

    development.act(P, USER, "start", {"ticket": ticket["key"], "request_id": "ds1"})
    development.act(P, USER, "propose", {"ticket": ticket["key"], "revision": 1,
        "summary": "导出金额必须使用配置的税率", "design": "export 经由 service 取值",
        "test_plan": "unittest 从配置推导期望值", "criteria": criteria,
        "questions": [], "request_id": "d1"})
    state = development.read(P.store, P.store.ticket(ticket["key"]))
    development.act(P, USER, "confirm",
                    {"ticket": ticket["key"], "revision": state["revision"],
                     "digest": state["digest"], "request_id": "dc1"}, human=True)
    state = development.read(P.store, P.store.ticket(ticket["key"]))
    development.act(P, USER, "execution",
                    {"ticket": ticket["key"], "revision": state["revision"],
                     "digest": state["digest"], "mode": "local", "request_id": "ex1"}, human=True)
    req = call("ticket_get", {"ticket": ticket["key"]})

    def submit(commit, tag):
        return call("candidate_submit", {"ticket": ticket["key"], "base_commit": base, "commit": commit,
            "requirement_hash": req["requirement_hash"], "criteria": criteria,
            "summary": "e2e %s" % tag, "request_id": "submit-%s" % tag})["candidate_id"]

    def verify(cid):
        call("candidate_verify", {"candidate_id": cid, "request_id": "verify-%d" % cid})
        rid = call("candidate_get", {"candidate_id": cid})["run_id"]
        for _ in range(300):
            st = P.flow.rechecks.status(rid) or {}
            if st.get("ended") and not st.get("running"):
                break
            time.sleep(1)
        return candidates.view(P, cid)

    ids = {}
    # wrong candidate: export ignores configured rate
    git("checkout", "-q", "main")
    (REPO / "rules.py").write_text("TAX_RATE = 0.20\n")
    (REPO / "export.py").write_text('def render(price):\n    return "TOTAL=%.2f" % round(price * 1.10, 2)\n')
    git("commit", "-am", "wrong")
    ids["wrong"] = submit(git("rev-parse", "HEAD"), "wrong")
    verify(ids["wrong"])

    # tamper candidate: deletes the failing assertion
    (REPO / "tests/test_flow.py").write_text(
        'import unittest\nclass F(unittest.TestCase):\n def test_propagates(self): pass\n')
    git("commit", "-am", "weakens")
    ids["tampered"] = submit(git("rev-parse", "HEAD"), "tampered")
    verify(ids["tampered"])

    # correct candidate: export goes through service
    (REPO / "service.py").write_text('from rules import TAX_RATE\n\ndef total(price):\n    return round(price * (1 + TAX_RATE), 2)\n')
    (REPO / "export.py").write_text('from service import total\n\ndef render(price):\n    return "TOTAL=%.2f" % total(price)\n')
    (REPO / "tests/test_flow.py").write_text(
        'import unittest\nfrom rules import TAX_RATE\nfrom export import render\n'
        'class F(unittest.TestCase):\n'
        ' def test_propagates(self):\n  self.assertEqual(render(100), "TOTAL=%.2f" % round(100*(1+TAX_RATE),2))\n')
    git("commit", "-am", "correct")
    good = git("rev-parse", "HEAD")
    ids["good"] = submit(good, "good")
    verify(ids["good"])

    # a doc-only commit for the UI resolve→submit flow to register fresh
    (REPO / "README.md").write_text("isolated e2e sample\n")
    git("add", "README.md")
    git("commit", "-m", "doc")
    doc = git("rev-parse", "HEAD")

    meta = {"ticket": ticket["key"], "project": "E2E", "base": base, "good": good, "doc": doc, "ids": ids,
            "user": USER, "data": str(DATA), "repo": str(REPO)}
    (RUNTIME / "fixture.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    return meta


def main():
    base = build_repo()
    seed(base)


if __name__ == "__main__":
    main()
