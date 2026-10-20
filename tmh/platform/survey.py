"""Full-project analysis: let local agents write the whole knowledge base, a few pages at a time.

One survey per project. It
1. builds (or incrementally refreshes) the knowledge graph,
2. starts N workers; each takes the next page from the `tmh kb next` queue (business flows
   first, then tables, domains and the overview, so summaries flow upward) and runs the
   agent on it in "kb" mode, which writes the page and passes `tmh kb done`. Small business
   flows from the same source file go to one run together (up to GROUP): the agent reads that
   file once instead of once per page, which is most of a page's time,
3. stops when the queue is empty, the page limit is reached, or someone presses stop,
4. regenerates the business map report.

A survey that is still running is written to <data>/surveys.json, so when the platform restarts
(an update, a crash) it picks up where it was instead of silently stopping.

Every page is an ordinary run (see agents.Runner), so its log, prompt and result show up
under 智能体运行 like any other. The survey itself only keeps progress in memory.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from .agents import max_agents
from .store import now

_SAVE = threading.Lock()


GROUP = 4  # flow pages of one source file written in one run


class Survey:
    def __init__(self, platform, project: dict, agent: str, parallel: int, limit: int, author: str, scope: str = "all", model=None):
        self.P = platform
        self.project = project
        self.root = Path(project["root"])
        self.agent = agent
        self.model = model  # None: the agent's default for knowledge pages
        self.parallel = max(1, min(int(parallel or 1), 6))
        self.limit = max(0, int(limit or 0))
        self.author = author
        self.scope = "top" if scope == "top" else "all"  # top: only business domains and the overview
        self.state = "starting"  # starting | building | running | stopping | done | stopped | failed
        self.started, self.ended = now(), ""
        self.batch = "KB-" + time.strftime("%m%d-%H%M%S")  # groups this survey's page runs under 智能体运行
        self.log = []
        self.active = {}  # worker -> {"page", "run"}
        self.finished = []  # {"page", "run", "ok", "title"}
        self.taken = set()
        self.lock = threading.Lock()
        self.claim_lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.hit_limit = False  # stopped because this round's page limit was reached, not because the queue is empty
        self.resumed = False

    # ------------------------------------------------------------ surviving a restart
    @staticmethod
    def _file(platform) -> Path:
        return Path(platform.data_dir) / "surveys.json"

    def _save(self, running: bool) -> None:
        f = self._file(self.P)
        with _SAVE:
            try:
                d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            except (OSError, ValueError):
                d = {}
            key = str(self.project["id"])
            if running:
                left = max(0, self.limit - len(self.finished)) if self.limit else 0
                d[key] = {"agent": self.agent, "model": self.model, "parallel": self.parallel, "scope": self.scope,
                          "author": self.author, "limit": left, "unlimited": not self.limit}
            else:
                d.pop(key, None)
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def resume_all(cls, platform) -> None:
        """Start again every survey the last platform process left running."""
        f = cls._file(platform)
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except (OSError, ValueError):
            return
        for pid, c in d.items():
            p = next((x for x in platform.store.projects() if str(x["id"]) == pid), None)
            if not p or (not c.get("unlimited") and not c.get("limit")):
                continue
            sv = cls(platform, p, c["agent"], c.get("parallel", 2), 0 if c.get("unlimited") else c["limit"], c.get("author", ""),
                     c.get("scope", "all"), c.get("model"))
            sv.resumed = True
            platform.surveys[p["id"]] = sv
            sv.start()

    # ------------------------------------------------------------ state
    def say(self, text: str) -> None:
        with self.lock:
            self.log.append("%s %s" % (time.strftime("%H:%M:%S"), text))
            del self.log[:-200]

    def view(self) -> dict:
        from .. import kb
        reg = kb.load_registry(self.root)
        with self.lock:
            return {"state": self.state, "scope": self.scope, "agent": self.agent, "model": self.model, "parallel": self.parallel, "limit": self.limit,
                    "author": self.author, "batch": self.batch, "started": self.started, "ended": self.ended,
                    "active": [dict(v, worker=k) for k, v in sorted(self.active.items())],
                    "finished": list(self.finished[::-1]), "log": list(self.log[-40:]),
                    "hit_limit": self.hit_limit, "resumed": self.resumed,
                    "ok": sum(1 for f in self.finished if f["ok"]), "failed": sum(1 for f in self.finished if not f["ok"]),
                    "pending": (len(self._todo_top()) if self.scope == "top" else len(kb.pending(self.root, reg))) if reg else None,
                    "coverage": kb.coverage(reg) if reg else None}

    @property
    def busy(self) -> bool:
        return self.state in ("starting", "building", "running", "stopping")

    def start(self) -> None:
        self._save(True)
        threading.Thread(target=self._main, daemon=True).start()

    def stop(self) -> None:
        if self.busy:
            self.state = "stopping"
            self.stop_flag.set()
            self.say("收到停止：正在写的页面写完就停，不再领新页面")

    # ------------------------------------------------------------ work
    def _main(self) -> None:
        from .. import kb
        try:
            self.state = "building"
            (self.root / ".tmh").mkdir(exist_ok=True)
            if self.resumed:
                self.say("平台重启前这次分析还没写完，自动接着写")
            kb.release_claims(self.root, "tmh-w")  # pages a stopped process had taken would otherwise wait out their lease
            self.say("构建知识图谱（增量，只重新解析改过的文件）…")
            t0 = time.time()
            r = kb.build(self.root)
            self.P.kb.forget(self.project["id"])
            left = len(self._todo_top()) if self.scope == "top" else len(kb.pending(self.root, kb.load_registry(self.root)))
            self.say("知识图谱就绪：%d 个节点，%.0f 秒；本次范围（%s）待写 %d 页" % (r["graph"]["nodes"], time.time() - t0, "业务域和总览" if self.scope == "top" else "全部", left))
            if self.stop_flag.is_set():
                return self._end("stopped")
            self.state = "running"
            cap = max_agents(self.P.data_dir)
            if cap and self.parallel > cap:
                self.say("并行 %d 超过了同时运行的智能体上限 %d（设置 → 自动处理），实际最多同时写 %d 页；工单的步骤优先" % (self.parallel, cap, cap))
            ws = [threading.Thread(target=self._worker, args=("w%d" % (i + 1),), daemon=True) for i in range(self.parallel)]
            for i, w in enumerate(ws):
                w.start()
                time.sleep(1.5 if i < len(ws) - 1 else 0)  # stagger: don't hit the queue and the model at once
            for w in ws:
                w.join()
            if self.finished and any(f["ok"] for f in self.finished):
                self._report()
            self._end("stopped" if self.stop_flag.is_set() else "done")
        except Exception as e:  # noqa: BLE001 - surfaced in the page, not swallowed
            self.say("出错：%s" % e)
            traceback.print_exc()
            self._end("failed")

    def _end(self, state: str) -> None:
        self.state, self.ended = state, now()
        ok = sum(1 for f in self.finished if f["ok"])
        self.say({"done": "全项目分析结束", "stopped": "已停止", "failed": "全项目分析中断"}[state] +
                 "：写成 %d 页，失败 %d 页" % (ok, len(self.finished) - ok))
        if state == "done" and self.hit_limit:
            self.say("这是本次上限 %d 页，不是全部写完；剩下的页面点“继续全项目分析”接着写" % self.limit)
        self._save(False)

    def _claim(self, who: str) -> tuple[list, str]:
        """Next pages for this worker: ([page, ...], '') or ([], reason) where reason is 'wait', 'empty' or 'limit'."""
        from .. import kb
        with self.lock:
            used = len(self.finished) + sum(len(a["pages"]) for a in self.active.values())
            if self.limit and used >= self.limit:
                self.hit_limit = True
                return [], "limit"
            room = self.limit - used if self.limit else GROUP
        if self.scope == "top":
            pid, why = self._claim_top(who)
            return ([pid] if pid else []), why
        r = kb.next_jobs(self.root, n=1, who="tmh-" + who)
        for pid in r["jobs"]:
            if pid not in self.taken:
                self.taken.add(pid)
                return [pid] + self._siblings(who, pid, min(room, GROUP) - 1), ""
        if r["remaining"] == 0:
            return [], "empty"
        return [], "wait"

    def _siblings(self, who: str, pid: str, n: int) -> list:
        """Other unwritten flow pages from the same source file as this one, claimed for the same run."""
        from .. import kb
        from ..graph import Graph
        if n <= 0 or not pid.startswith("flow:"):
            return []
        g = Graph(self.root)
        node = g.node(pid)
        if not node or not node.get("file"):
            return []
        reg = kb.load_registry(self.root)
        busy = kb.claimed(self.root)
        out = []
        for other in kb.pending(self.root, reg):
            if len(out) >= n:
                break
            if other == pid or other in self.taken or not other.startswith("flow:") or busy.get(other, "tmh-" + who) != "tmh-" + who:
                continue
            o = g.node(other)
            if o and o.get("file") == node["file"]:
                kb.next_jobs(self.root, n=1, who="tmh-" + who, only=other)
                self.taken.add(other)
                out.append(other)
        return out

    def _todo_top(self) -> list:
        from .. import kb
        reg = kb.load_registry(self.root)
        def open_(pid):
            r = reg.get(pid)
            return r is not None and not r.get("orphan") and (r.get("stale") or r.get("status", kb.STATUS_NEW) == kb.STATUS_NEW)
        return [p for p in sorted(reg) if p.startswith("dom:") and open_(p)] + (["index"] if open_("index") else [])

    def _claim_top(self, who: str) -> tuple[str, str]:
        """Business-map mode: domains straight from their facts (flow pages need not exist), the overview last."""
        from .. import kb
        todo = [p for p in self._todo_top() if p not in self.taken]
        if not todo:
            return "", "empty"
        pid = todo[0]
        if pid == "index":
            with self.lock:
                if self.active:  # the overview summarises the domains still being written
                    return "", "wait"
        kb.next_jobs(self.root, n=1, who="tmh-" + who, only=pid)
        self.taken.add(pid)
        return pid, ""

    def _worker(self, who: str) -> None:
        from .. import kb
        idle = 0
        while not self.stop_flag.is_set():
            with self.claim_lock:
                pids, why = self._claim(who)
                if pids:
                    with self.lock:
                        self.active[who] = {"page": " ".join(pids), "pages": pids, "run": None}
            if not pids:
                if why in ("empty", "limit"):
                    if why == "limit":
                        self.say("%s：已达到本次上限 %d 页" % (who, self.limit))
                    return
                # Remaining pages wait for pages others are still writing (a domain waits for its flows).
                with self.lock:
                    others = bool(self.active)
                if not others:
                    idle += 1
                    if idle > 2:
                        self.say("%s：剩下的页面都在等前面失败的页面，先停在这里" % who)
                        return
                if self.stop_flag.wait(5):
                    return
                continue
            idle = 0
            target = " ".join(pids)
            self.say("%s 开始写 %s" % (who, "、".join(pids)))
            try:
                run = self.P.runner.start(self.project, None, self.agent, "kb", self.author, target, batch=self.batch, model=self.model)
            except ValueError as e:
                self.say("%s 启动失败：%s" % (who, e))
                with self.lock:
                    self.active.pop(who, None)
                    self.finished += [{"page": pid, "run": None, "ok": False, "title": "", "why": str(e)} for pid in pids]
                self.stop_flag.set()
                return
            with self.lock:
                self.active[who]["run"] = run["id"]
            while True:
                r = self.P.store.run(run["id"])
                if r["status"] not in ("queued", "running"):
                    break
                time.sleep(2)
            regs = kb.load_registry(self.root)
            with self.lock:
                self.active.pop(who, None)
            for pid in pids:
                reg = regs.get(pid, {})
                # a page counts when it passed `tmh kb done`, even if the run died on a later page of the group
                ok = reg.get("status") not in (None, kb.STATUS_NEW) and not reg.get("stale") and (r["status"] == "done" or len(pids) > 1)
                why = "" if ok else ("智能体%s" % {"failed": "运行失败", "cancelled": "被取消"}.get(r["status"], "没有通过 tmh kb done 校验"))
                with self.lock:
                    self.finished.append({"page": pid, "run": run["id"], "ok": ok, "title": reg.get("title", ""), "why": why})
                self.say("%s %s %s%s" % (who, "写成" if ok else "未完成", pid, "" if ok else "（%s）" % why))
            if not self.stop_flag.is_set():
                self._save(True)  # a restart resumes with what is left of the limit
            self.P.kb.forget(self.project["id"])
            if r["status"] == "failed" and len({f["run"] for f in self.finished}) <= self.parallel and not any(f["ok"] for f in self.finished):
                self.say("第一批页面就失败了，先停下，看一下运行日志再继续")
                self.stop_flag.set()
                return

    def _report(self) -> None:
        try:
            from .. import explorer
            from ..cli import _load_flows
            explorer.write(self.root, _load_flows(self.root))
            self.say("已刷新业务全景报告")
        except Exception as e:  # noqa: BLE001
            self.say("刷新业务全景报告失败：%s" % e)
