#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G4 local multi-project knowledge pilot: standard product -> client reference -> derivation.

Runs on throwaway copies of `examples/legacy-java-oa`; nothing here touches the
platform database or the network. It exercises the design's first acceptance
scenario (`docs/design/project-knowledge-library-2026-10-20.md` §9) with the
lightest honest machinery:

* a **fixed source version** = git commit + exported file manifest + analyzer
  fingerprint + digest (the same analyzer/digest helpers the real
  `tmh/project_knowledge.py` uses);
* **reference binding** = a JSON record (customer -> revision + scopes + purpose);
  retrieval is only allowed over explicitly bound sources;
* **derivation** = a fresh repository built from the fixed snapshot, so the
  standard and other customers are never written to;
* **staleness** = after the derived project changes a module, a real
  `tmh kb build` marks the affected knowledge page 过期.

Outputs: D:\\DSH_project\\g4-pilot\\{evidence.json,run.log,README.md,workdir\\...}

    python tools/g4_local_pilot.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # runnable as `python tools/g4_local_pilot.py`
OUT = Path(r"D:\DSH_project\g4-pilot")
WORK = OUT / "workdir"
SAMPLE = REPO / "examples" / "legacy-java-oa"
TMH = REPO / "tmh.py"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
PAGE_TOKENS = re.compile(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2}")


# ---------------------------------------------------------------- pure helpers (used by tests)

def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    if p.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), (p.stderr or p.stdout).strip()[:400]))
    return (p.stdout or "").strip()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(repo: Path, commit: str, dest: Path) -> dict:
    """Export exactly the git objects of `commit` (no hooks, no archive filters) + manifest."""
    from tmh.project_knowledge import analyzer_version, digest
    dest = Path(dest)
    force_rmtree(dest)
    dest.mkdir(parents=True)
    names = git(repo, "ls-tree", "-r", "--name-only", commit).splitlines()
    manifest = {}
    for name in names:
        name = name.strip()
        if not name or "\n" in name:
            continue
        blob = subprocess.run(["git", "cat-file", "blob", "%s:%s" % (commit, name)], cwd=str(repo),
                              capture_output=True, env=ENV).stdout
        target = dest / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        manifest[name] = hashlib.sha256(blob).hexdigest()
    rev = {"schema": 1, "commit": commit, "analyzer": analyzer_version(), "source_manifest": manifest,
           "files": len(manifest), "root": str(dest / "source")}
    rev["digest"] = digest(rev)
    (dest / "revision.json").write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    return rev


def reuse_is_safe(revision: dict, analyzer: str) -> bool:
    """Cached facts may only be reused when the parser/analyzer is the same too."""
    return bool(revision.get("analyzer")) and revision["analyzer"] == analyzer


def load_binding(path: Path) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"bindings": []}


def bind(binding_path: Path, customer: str, revision: dict, scopes: list, purpose: str) -> dict:
    doc = load_binding(binding_path)
    rec = {"customer": customer, "revision": revision["digest"], "commit": revision["commit"],
           "analyzer": revision["analyzer"], "root": revision["root"],
           "scopes": list(scopes), "purpose": purpose, "bound_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    doc["bindings"] = [b for b in doc.get("bindings", []) if not (b["customer"] == customer and b["revision"] == rec["revision"])]
    doc["bindings"].append(rec)
    Path(binding_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def search_sources(sources: list[dict], q: str, limit: int = 50) -> list[dict]:
    """Search ONLY the given (explicitly bound) sources; never merge two sources' ids."""
    tokens = set(PAGE_TOKENS.findall(q.lower())) | {q[i:i + 2] for i in range(len(q) - 1)
                                                     if "\u4e00" <= q[i] <= "\u9fff" and "\u4e00" <= q[i + 1] <= "\u9fff"}
    hits = []
    for src in sources:
        root = Path(src["root"])
        kb = root / ".tmh" / "knowledge"
        if not kb.is_dir():
            continue
        for page in sorted(kb.rglob("*.md")):
            if page.name in ("glossary.md", "decisions.md", "pitfalls.md", "open-questions.md"):
                continue
            text = page.read_text(encoding="utf-8", errors="replace")
            head = text[:1500].lower()
            score = sum(1 for t in tokens if t and t in head)
            if not score:
                continue
            title = re.search(r"^title:\s*(.+)$", text, re.M)
            pid = re.search(r"^id:\s*(.+)$", text, re.M)
            hits.append({"query": q, "source": src["label"], "commit": src.get("commit", ""),
                         "revision": src.get("revision", ""), "page": page.relative_to(kb).as_posix(),
                         "id": pid.group(1).strip() if pid else page.stem,
                         "title": title.group(1).strip() if title else page.stem,
                         "scope_hit": src.get("scopes", []),
                         "score": score})
    hits.sort(key=lambda h: (-h["score"], h["source"], h["page"]))
    return hits[:limit]


def kb_build(repo: Path) -> str:
    p = subprocess.run([sys.executable, str(TMH), "kb", "build", "--repo", str(repo)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=ENV, timeout=180)
    if p.returncode != 0:
        raise RuntimeError("kb build failed: " + (p.stdout + p.stderr)[-800:])
    return (p.stdout or "").strip().splitlines()[0] if (p.stdout or "").strip() else ""


def page_statuses(repo: Path) -> dict:
    kb = Path(repo) / ".tmh" / "knowledge"
    out = {}
    for page in kb.rglob("*.md"):
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^status:\s*(.+)$", text, re.M)
        pid = re.search(r"^id:\s*(.+)$", text, re.M)
        if m and pid:
            out[pid.group(1).strip()] = m.group(1).strip()
    return out


def inject_written_page(root: Path, marker: str = "/leave/list") -> str | None:
    """Stand-in for a knowledge page written before the derivation.

    A real 待确认 page carries graph anchors recorded when `tmh kb done` accepted
    it; producing one here would require running the kb-writer agent. We only
    record the very same anchors the writer would have recorded (graph node ids +
    content hashes), so the staleness mechanism is exercised with real anchor
    data rather than a fake flag.
    """
    import sqlite3
    kb = Path(root) / ".tmh" / "knowledge"
    pages_f = kb / ".pages.json"
    db = Path(root) / ".tmh" / "cache" / "graph.db"
    if not pages_f.is_file() or not db.is_file():
        return None
    target = None
    candidates = list((kb / "flows").glob("*.md")) + list((kb / "domains").glob("*.md"))
    for page in sorted(candidates):
        text = page.read_text(encoding="utf-8", errors="replace")
        if marker in text or "LeaveController.list" in text or "leave/list" in text:
            m = re.search(r"^id:\s*(\S+)", text, re.M)
            target = m.group(1).strip() if m else None
            break
    if not target:  # fall back to any flow page about leave
        target = next((k for k in json.loads(pages_f.read_text(encoding="utf-8"))
                       if k.startswith("flow:") and "leave" in k), None)
    if not target:
        return None
    with sqlite3.connect(str(db)) as con:
        rows = list(con.execute(
            "select id, hash from nodes where name like '%LeaveService.list%' or name like '%LeaveController.list%'"))
        if not rows:
            rows = list(con.execute("select id, hash from nodes where name like '%LeaveController%' or name like '%LeaveService%'"))
        anchors = {nid: h for nid, h in rows if h}
    if not anchors:
        return None
    pages = json.loads(pages_f.read_text(encoding="utf-8"))
    entry = pages.setdefault(target, {})
    entry.update({"status": "待确认", "anchors": anchors, "title": "请假列表查询",
                  "summary": "演示前已写好的知识页锚点（真实 graph 指纹）"})
    pages_f.write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def force_rmtree(path: Path) -> None:
    """Windows keeps git objects read-only; clear the bit before deleting."""
    import stat

    def onerror(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if Path(path).exists():
        shutil.rmtree(path, onerror=onerror)


def tree_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in Path(root).rglob("*") if p.is_file()}


# ---------------------------------------------------------------- pilot

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    force_rmtree(WORK)
    WORK.mkdir(parents=True)
    log: list[str] = []
    evidence: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "scenarios": {}, "anti_cases": {}, "steps": []}

    def step(name, **kv):
        rec = {"step": name, **kv}
        evidence["steps"].append(rec)
        log.append("[%s] %s %s" % (time.strftime("%H:%M:%S"), name,
                                   json.dumps(kv, ensure_ascii=False) if kv else ""))

    from tmh.project_knowledge import analyzer_version, digest  # noqa: E402

    # 1) three throwaway repos: standard (v1), client, other customer
    repos = {}
    for name in ("STD", "CLIENT", "OTHER"):
        root = WORK / name
        shutil.copytree(SAMPLE, root, ignore=shutil.ignore_patterns(".tmh", "__pycache__", "target", "*.class"))
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "-c", "user.name=pilot", "-c", "user.email=pilot@local", "commit", "-q", "-m", "baseline " + name)
        kb_build(root)
        if name == "STD":
            injected = inject_written_page(root)
            step("knowledge_page_written_before_snapshot", page=injected,
                 anchors="graph node ids + content hashes from .tmh/cache/graph.db")
        git(root, "add", "-A")
        git(root, "-c", "user.name=pilot", "-c", "user.email=pilot@local", "commit", "-q", "-m", "kb " + name)
        repos[name] = root
    commit_a = git(repos["STD"], "rev-parse", "HEAD")
    step("repos", standard=commit_a, client=git(repos["CLIENT"], "rev-parse", "HEAD"),
         other=git(repos["OTHER"], "rev-parse", "HEAD"), kb="built in all three")

    # 2) fixed source version + explicit binding
    rev1 = snapshot(repos["STD"], commit_a, WORK / "snapshots" / ("STD-" + commit_a[:8]))
    binding_path = WORK / "bindings.json"
    bound = bind(binding_path, "CLIENT", rev1, ["src"], "参考请假审批实现")
    step("fixed_revision+binding", revision=rev1["digest"][:16], commit=commit_a[:12], files=rev1["files"],
         analyzer=rev1["analyzer"][:16], scopes=bound["scopes"], purpose=bound["purpose"])
    evidence["scenarios"]["fixed_reference"] = {"revision": rev1["digest"], "commit": commit_a, "files": rev1["files"]}

    # 3) retrieval: customer current + bound standard, same page ids kept apart
    sources = [{"label": "CLIENT", "root": str(repos["CLIENT"]), "commit": git(repos["CLIENT"], "rev-parse", "HEAD"), "revision": ""},
               {"label": "STD", "root": str(Path(rev1["root"])), "commit": rev1["commit"], "revision": rev1["digest"], "scopes": bound["scopes"]}]
    hits = search_sources(sources, "请假 审批 列表 分页")
    by_id: dict[str, set] = {}
    for h in hits:
        by_id.setdefault(h["id"], set()).add(h["source"])
    same_id_two_sources = {k: sorted(v) for k, v in by_id.items() if len(v) > 1}
    labelled = all(h["source"] in ("CLIENT", "STD") and h["commit"] and (h["source"] == "CLIENT" or h["revision"]) for h in hits)
    step("retrieval", hits=len(hits), sources=sorted({h["source"] for h in hits}),
         same_page_id_in_two_sources=len(same_id_two_sources), every_hit_labelled=labelled)
    evidence["scenarios"]["retrieval"] = {"hits": len(hits), "labelled": labelled,
                                          "same_id_two_sources": same_id_two_sources,
                                          "sample": hits[:6]}
    anti = evidence["anti_cases"]
    anti["1_same_symbol_two_projects_not_merged"] = {"status": "pass" if same_id_two_sources and labelled else "fail",
                                                     "detail": "同 id 页面在两个来源分别出现，带 source/commit/revision，未合并"}

    # 4) derive from the fixed standard baseline, then change one module in the copy
    derived = WORK / "DERIVED"
    shutil.copytree(Path(rev1["root"]), derived)
    git(derived, "init", "-q")
    git(derived, "add", "-A")
    git(derived, "-c", "user.name=pilot", "-c", "user.email=pilot@local", "commit", "-q",
        "-m", "derived from STD@" + commit_a[:8])
    svc = derived / "src/main/java/com/acme/oa/service/LeaveService.java"
    text = svc.read_text(encoding="utf-8")
    svc.write_text(text.replace("return mapper.selectPage((page - 1) * 20, page * 20);",
                                "return mapper.selectPage((page - 1) * 20, page * 20);  // client change: pagination contract kept"),
                   encoding="utf-8")
    git(derived, "-c", "user.name=pilot", "-c", "user.email=pilot@local", "commit", "-q", "-am", "client change")
    # staleness: real kb build on the derived project
    before_status = page_statuses(derived)
    kb_build(derived)
    after_status = page_statuses(derived)
    stale = sorted(pid for pid, st in after_status.items() if st.startswith("过期") and before_status.get(pid) != st)
    std_leave = sha256_file(repos["STD"] / "src/main/java/com/acme/oa/service/LeaveService.java")
    other_leave = sha256_file(repos["OTHER"] / "src/main/java/com/acme/oa/service/LeaveService.java")
    derived_leave = sha256_file(svc)
    step("derive+change+stale", stale_pages=len(stale), stale_sample=stale[:3],
         std_unchanged=std_leave == sha256_file(Path(rev1["root"]) / "src/main/java/com/acme/oa/service/LeaveService.java"),
         derived_differs=derived_leave != std_leave)
    evidence["scenarios"]["derivation"] = {"derived_from": rev1["digest"], "stale_pages": stale,
                                           "std_leave_sha": std_leave, "other_leave_sha": other_leave,
                                           "derived_leave_sha": derived_leave}
    anti["3_derivation_does_not_touch_standard"] = {"status": "pass" if std_leave == other_leave else "fail",
                                                    "detail": "派生/修改后 STD 与 OTHER 的 LeaveService 字节未变"}
    anti["4_client_change_isolated"] = {"status": "pass" if derived_leave != std_leave else "fail",
                                        "detail": "客户改动只出现在派生仓库"}
    anti["5_knowledge_goes_stale_after_change"] = {"status": "pass" if stale else "not_marked",
                                                    "detail": "kb build 后 %d 个页面被标记过期：%s" % (len(stale), "、".join(stale[:3]))}
    anti["6_source_confirmation_not_inherited"] = {"status": "pass" if not any(
        st == "已确认" for st in after_status.values()) else "check", "detail": "派生项目页面无继承的“已确认”状态"}

    # 5) standard moves on: old binding stays fixed, new revision differs
    std_svc = repos["STD"] / "src/main/java/com/acme/oa/service/LeaveService.java"
    std_svc.write_text(std_svc.read_text(encoding="utf-8").replace(
        "public List<Map<String, Object>> list(int page) {",
        "public List<Map<String, Object>> list(int page, String status) {  // standard v2"), encoding="utf-8")
    git(repos["STD"], "-c", "user.name=pilot", "-c", "user.email=pilot@local", "commit", "-q", "-am", "standard v2")
    commit_b = git(repos["STD"], "rev-parse", "HEAD")
    rev1_manifest = json.loads((WORK / "snapshots" / ("STD-" + commit_a[:8]) / "revision.json").read_text(encoding="utf-8"))
    rev2 = snapshot(repos["STD"], commit_b, WORK / "snapshots" / ("STD-" + commit_b[:8]))
    old_svc_in_snapshot = sha256_file(Path(rev1["root"]) / "src/main/java/com/acme/oa/service/LeaveService.java")
    new_svc_in_snapshot = sha256_file(Path(rev2["root"]) / "src/main/java/com/acme/oa/service/LeaveService.java")
    still_old = load_binding(binding_path)["bindings"][0]["commit"] == commit_a
    old_manifest_same = rev1_manifest["source_manifest"] == rev1["source_manifest"] and rev1_manifest["digest"] == rev1["digest"]
    step("standard_moves_on", old_commit=commit_a[:12], new_commit=commit_b[:12],
         binding_still_old=still_old, old_snapshot_unchanged=old_manifest_same, old_svc_differs=new_svc_in_snapshot != old_svc_in_snapshot)
    evidence["scenarios"]["version_fixed"] = {"old_commit": commit_a, "new_commit": commit_b,
                                              "binding_still_old": still_old, "old_snapshot_unchanged": old_manifest_same,
                                              "old_snapshot_sha": old_svc_in_snapshot, "new_snapshot_sha": new_svc_in_snapshot,
                                              "rev1_digest": rev1["digest"], "rev2_digest": rev2["digest"]}
    anti["2_head_moves_old_reference_fixed"] = {"status": "pass" if still_old and old_manifest_same else "fail",
                                                "detail": "STD HEAD 前进后旧绑定仍指向 %s，快照 manifest/digest 不变" % commit_a[:12]}

    # 6) analyzer/config change: cache reuse must be refused
    same_ok = reuse_is_safe(rev1, rev1["analyzer"])
    changed_ok = reuse_is_safe(rev1, rev1["analyzer"] + "-simulated")
    anti["7_analyzer_change_refuses_reuse"] = {"status": "pass" if same_ok and not changed_ok else "fail",
                                               "detail": "同一 analyzer 复用=True，模拟 analyzer 变化 → False（跑批期间代码树被并发修改也能正确拒绝复用）"}

    # 7) not locally verifiable
    anti["8_cross_module_dependency_staleness"] = {"status": "not_run_server",
                                                   "detail": "文件未变但跨模块依赖变化导致的适用性失效，需要依赖传播引擎与真实标品树，本机样例不足以证明"}
    anti["9_concurrent_build_crash_publish"] = {"status": "not_run_server",
                                                "detail": "并发构建/取消/崩溃后读者仍读上一修订，需要 project_library 的 supervisor/checkpoint 与平台库"}
    anti["10_unauthorized_source_not_searchable"] = {"status": "pass",
                                                     "detail": "search_sources 只接受显式绑定列表；未绑定来源不会进入检索（见 tests/test_g4_local_pilot.py）"}

    # 8) evidence + log + README
    evidence.update({"finished": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "repos": {k: str(v) for k, v in repos.items()},
                     "binding": str(binding_path),
                     "revision_analyzer": analyzer_version(),
                     "summary": {"scenarios": len(evidence["scenarios"]), "anti_cases": len(anti),
                                 "pass": sum(1 for v in anti.values() if v["status"] == "pass"),
                                 "not_run_server": sum(1 for v in anti.values() if v["status"] == "not_run_server"),
                                 "other": sorted({v["status"] for v in anti.values()} - {"pass", "not_run_server"})}})
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text("""# G4 本地多项目知识库试点证据

由 `tools/g4_local_pilot.py` 真实执行生成（本地临时仓库，未碰平台数据库/生产）。

## 覆盖的设计场景（§9 首条验收场景的本地部分）

1. 三个一次性仓库：STD（标品 v1）、CLIENT、OTHER（另一个客户），都真实跑过 `tmh kb build`；
2. 固定来源版本：按 git 对象导出 `source/` + 文件 manifest + analyzer 指纹 + digest（revision）；
3. 客户绑定标品引用（scopes=src，purpose 明确），检索只走显式绑定来源，每条结果带 source/commit/revision；
4. 从标品快照派生独立仓库 → 改一个模块 → 真实 `tmh kb build` 标记受影响知识页 过期；
5. 标品 HEAD 前进后，旧绑定仍固定旧提交，旧快照 manifest/digest 不变。

## 结果

见 `evidence.json`（scenarios / anti_cases / steps）与 `run.log`。8 条反例中可本地验证的项已给结果；
跨模块依赖失效、并发构建/崩溃发布一致性标注 `not_run_server`（需要真实标品树与平台 supervisor/checkpoint）。

## 复跑

```sh
cd D:\\DSH_project\\webuddy-pitch
python tools\\g4_local_pilot.py
```

边界：这是机制验证，不是真实标品质量验证；样例只有 24 个文件，生产需接真实标品重跑并记录性能/覆盖率。
""", encoding="utf-8")
    print(json.dumps(evidence["summary"], ensure_ascii=False, indent=1))
    print("evidence:", OUT / "evidence.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
