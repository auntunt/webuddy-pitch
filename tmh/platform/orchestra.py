"""编排层: the line every coding task goes through, whichever app it came from.

The platform has three layers. The knowledge layer (knowledge.py, over kb/graph) knows what a project is: business
domains, flows, tables, code evidence. This layer knows how to get a change right: an agent locates the task in the
code, drafts a plan, edits file by file in its own worktree, builds and tests, diagnoses, commits on the task's own
branch and waits for a person; a rejected automatic change is redone with the reason; acceptance turns into lessons
and eval cases (learn.py). The apps on top (运维 with its alerts, 重构 with its plans, later others) only decide where
tasks come from, who accepts them and what is counted.

What an app may use, and nothing else:
  submit(project, ticket)                        put a task on the line
  accepted(project, ticket, passed, note, by)    a person's verdict (the API's acceptance route calls it)
  take_over / resume / next_step / catch_up      people taking a task off the line and handing it back
  listen(fn)                                     hear every verdict: fn(project, ticket, verdict) -> dict | None, with
                                                 verdict = {passed, note, by, redo, gave_up}; gave_up says why nothing
                                                 will redo a rejected task automatically ("" when something will)
  start_from(fn)                                 say where a ticket's change starts, asked each time one starts:
                                                 fn(project, ticket) -> commit, "" for the main line, or None
  links.later                                    an app holds a ticket off the line (why, in words): no step starts on it
                                                 until the app removes it, and its verdicts only go to the listeners
  BY                                             the author name the line writes events under
The line reads the knowledge layer (related flows) and never calls into an app.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path


class Orchestra:
    FILE_LINE = re.compile(r"([\w./\\-]+\.(?:java|cs|xml|sql|jsp|aspx|cshtml|config|properties|yml|yaml|vb|js|ts|vue|kt|py)):(\d+)")

    def __init__(self, store, runner, data_dir: Path, knowledge):
        self.store, self.runner, self.data_dir, self.knowledge = store, runner, Path(data_dir), knowledge
        self.listeners = []
        self.on_release = []  # fn(project, ticket, release) after a change is merged and given a version
        self.bases = []  # fn(project, ticket) -> commit | "" (the main line) | None (no opinion): where a change starts
        self.committed = []  # fn(project, ticket id, run id) after a change was committed unattended
        self.rechecking = set()  # legacy in-process notification only; durable operations own the lease

    @property
    def rechecks(self):
        from .fixloop import recheck_operations
        return recheck_operations(self.runner)

    def listen(self, fn) -> None:
        self.listeners.append(fn)

    def start_from(self, fn) -> None:
        self.bases.append(fn)

    def agent(self, conf: dict | None = None, project: dict | None = None) -> str:
        """The agent the line would use now ("" when none is available on this machine)."""
        return self._flow_agent(conf or self.autoflow(), project)

    def root(self, p: dict) -> Path:
        return Path(p["root"])

    # Every new ticket, however it arrives (form, import, assistant, a client's chat), runs the same line without
    # anyone pressing a button: link the business it touches, let an agent locate it in the code, draft the change,
    # make it in a worktree and commit it on the ticket's own branch (tmh/<KEY>-r<run>), then wait for a person to
    # merge and accept it. The main branch and the person's working copy are never touched. A person can take over
    # at any step (links.hold) and hand it back later; a change that is large or edits existing tests is left for
    # review instead of committed. Settings in <data>/autoflow.json:
    # {"on": true, "agent": "codex", "plan": true, "fix": true, "commit": true, "max_lines": 400, "assignee": ""}.
    # max_lines may also be per project: {"JB": 400, "RW": 20000, "*": 400}.
    BY = "自动流转"
    FLOW_BY = BY
    TEST_GLOBS = ["**/test/**", "**/tests/**", "**/__tests__/**", "**/test_*.py", "**/*_test.*", "**/*.test.*", "**/*.spec.*"]

    def autoflow(self) -> dict:
        conf = {"on": True, "agent": "", "plan": True, "fix": True, "commit": True, "max_lines": 400, "assignee": "", "refix": 2, "holdout": 0.1}
        f = self.data_dir / "autoflow.json"
        if f.exists():
            try:
                conf.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in conf})
            except ValueError:
                pass
        from . import release
        conf["merge"] = release.settings(self.data_dir)["merge"]  # derived, for the pages: say "merged automatically" only when it is
        if getattr(self, "tenant_context", None) is not None:
            conf.update(on=False, merge=False)
        return conf

    def submit(self, p: dict, t: dict, wait: bool = False) -> None:
        """A task enters the line. Returns at once (wait=True blocks until the first step has been started)."""
        th = threading.Thread(target=self._intake, args=(p, t), daemon=True)
        th.start()
        if wait:
            th.join()

    def _flow_agent(self, conf: dict, project: dict | None = None) -> str:
        from .agents import available
        from .agent_routes import resolve
        agents = [a["name"] for a in available(self.data_dir) if a["available"]]
        fallback = conf.get("agent") if conf.get("agent") in agents else (agents[0] if agents else "")
        return resolve(self.data_dir, project, fallback=fallback)

    def _intake(self, p: dict, t: dict) -> None:
        st, by = self.store, self.BY
        conf = self.autoflow()
        if not self.switched_on(conf, p) or self.mine(t["id"]):  # a person claimed it (我来写) before the line got to it
            return
        try:
            rel = self.knowledge.related(p, "%s %s" % (t["title"], (t.get("body") or "")[:400]), limit=3)
        except Exception:  # noqa: BLE001 - no knowledge base yet is not a reason to stop the flow
            rel = {"flows": []}
        links = dict((st.ticket(t["id"]) or t).get("links") or {})  # not the copy it was submitted with: a client may be on it since
        have = list(links.get("flows") or [])
        add = [f for f in rel["flows"] if f["id"] not in have][:max(0, 3 - len(have))]
        if add:
            links["flows"] = have + [f["id"] for f in add]
            st.update_ticket(t["id"], by, links=links)
        if conf.get("assignee") and not t.get("assignee"):
            st.update_ticket(t["id"], by, assignee=conf["assignee"])
        st.event(t["id"], by, "intake", "自动受理" + ("：关联业务 " + "、".join(f["name"] or f["trigger"] for f in add) if add else "：知识库里没有找到明确对应的业务流"),
                 {"flows": [f["id"] for f in add]})
        self._flow_analyze(p, t["id"], conf)

    def switched_on(self, conf: dict, project) -> bool:
        """Whether the automatic line runs for this project: "on" is true/false for all, or a list of project keys."""
        v = conf.get("on")
        if not isinstance(v, (list, tuple)):
            return bool(v)
        p = project if isinstance(project, dict) else self.store.project(project)
        return bool(p) and p["key"] in v

    def held(self, tid: int) -> bool:
        return bool((self.store.ticket(tid).get("links") or {}).get("hold"))

    def mine(self, tid: int) -> bool:
        """A person writes this one (我来写): the line does not even analyse it."""
        return bool((self.store.ticket(tid).get("links") or {}).get("handwork"))

    def _flow_stop(self, tid: int, why: str) -> None:
        st = self.store
        if st.ticket(tid)["status"] in ("new", "analyzing", "confirm"):
            st.update_ticket(tid, self.BY, status="doing")
        st.event(tid, self.BY, "flow", why)

    def _flow_analyze(self, p: dict, tid: int, conf: dict) -> None:
        st, by = self.store, self.BY
        if self.mine(tid):  # claimed (我来写) while the line was getting to it
            return
        try:
            agent = self._flow_agent(conf, p)
        except ValueError as exc:
            self._flow_stop(tid, str(exc))
            return
        if not agent:
            return self._flow_stop(tid, "本机没有可用的智能体，跳过自动分析，直接转人工处理")

        def analysed(run):
            cur = st.ticket(tid)
            if self.held(tid) or cur["status"] not in ("new", "analyzing", "confirm"):
                return  # someone already took it further by hand
            res = run.get("result") or ""
            if run["status"] != "done":
                return self._flow_stop(tid, "自动分析没有完成，转人工处理")
            cited = [f for f in re.findall(r"flow:[A-Za-z0-9_.\-]*[A-Za-z0-9_]", res)]
            if cited:
                lk = dict(cur.get("links") or {})
                lk["flows"] = list(dict.fromkeys((lk.get("flows") or []) + cited))[:8]
                st.update_ticket(tid, by, links=lk)
            refs = len(self.FILE_LINE.findall(res))
            st.update_ticket(tid, by, status="doing")
            go = refs and conf.get("plan") and not self.held(tid)
            st.event(tid, by, "flow", ("已定位到 %d 处代码，进入处理中%s" % (refs, "，接着起草修改方案" if go else "")) if refs
                     else "分析没有找到代码证据，进入处理中，需要人工补充信息", {"refs": refs})
            if go:
                self._flow_plan(p, tid, conf, agent)
        analysed.always = analysed.owns_status = True
        try:
            self.runner.start(p, st.ticket(tid), agent, "analyze", by, then=analysed)
        except ValueError as e:
            self._flow_stop(tid, "自动分析没有启动（%s），转人工处理" % e)

    def _flow_plan(self, p: dict, tid: int, conf: dict, agent: str) -> None:
        st, by = self.store, self.BY

        def planned(run):
            if self.held(tid) or st.ticket(tid)["status"] != "doing":
                return
            if run["status"] != "done":
                return st.event(tid, by, "flow", "自动起草修改方案没有完成，等人处理")
            from .fixloop import plan_ac
            if conf.get("fix") and not plan_ac(run.get("result") or ""):  # no acceptance criteria, no implementation
                return st.event(tid, by, "flow", "方案里没有验收标准（AC），不进入自动改代码；补上验收标准后由人决定是否改", {"run": run["id"]})
            if conf.get("fix"):
                st.event(tid, by, "flow", "修改方案已出，接着在独立分支上改代码")
                self._flow_fix(p, tid, conf, agent)
        planned.always = True
        try:
            self.runner.start(p, st.ticket(tid), agent, "plan", by, then=planned)
        except ValueError as e:
            st.event(tid, by, "flow", "自动起草方案没有启动（%s），等人处理" % e)

    def _flow_fix(self, p: dict, tid: int, conf: dict, agent: str, base: str = "") -> None:
        st, by = self.store, self.BY
        if not base:  # a ticket can name the commit its change must start from: an app says so now, else links.base
            from . import learn
            t = st.ticket(tid)
            want = None
            for fn in self.bases:
                try:
                    want = fn(p, t)
                except Exception as e:  # noqa: BLE001 - an app's trouble must not stop the change
                    st.event(tid, by, "flow", "没能问到这次改动从哪开始（%s），用工单记下的起点" % e)
                if want is not None:
                    break
            if want is None:
                want = (t.get("links") or {}).get("base") or ""
            base = want if want and learn._resolve(self.root(p), want) else ""

        def fixed(run):
            if self.held(tid) or st.ticket(tid)["status"] != "doing":
                return  # taken over: the change waits for review like any other
            self._flow_commit(p, tid, conf, run)
        fixed.always = True
        try:
            self.runner.start(p, st.ticket(tid), agent, "fix", by, then=fixed, base=base)
        except ValueError as e:
            st.event(tid, by, "flow", "自动改代码没有启动（%s），等人处理" % e)

    def _flow_commit(self, p: dict, tid: int, conf: dict, run: dict) -> None:
        st, by = self.store, self.BY
        if run["status"] != "done":
            return st.event(tid, by, "flow", "自动改代码没有完成，等人处理")
        if not run.get("diff"):
            return st.event(tid, by, "flow", "智能体没有改出代码，等人看方案后处理")
        why = self.fix_gate(p, run["diff"], conf, run["id"])
        if why or not conf.get("commit"):
            return st.event(tid, by, "flow", "改动已生成，%s，留给人审阅后再提交" % (why or "设置为不自动提交"), {"run": run["id"]})
        try:
            self.runner.decide(run["id"], "accept", by)
        except (ValueError, RuntimeError) as e:
            return st.event(tid, by, "flow", "自动提交改动失败（%s），留给人审阅" % e, {"run": run["id"]})
        for fn in self.committed:
            try:
                fn(p, tid, run["id"])
            except Exception as e:  # noqa: BLE001 - the commit stands; what follows waits for a person
                st.event(tid, by, "flow", "改动已自动提交，后续处理没做成（%s），留给人验收" % e, {"run": run["id"]})

    def accepted(self, p: dict, t: dict, passed: bool, note: str, by: str) -> dict:
        """A person's verdict on a task: keep what it teaches, send a rejected automatic change back to be redone,
        and tell every app that listens (for instance a reform plan moving on to its next wave)."""
        from . import learn
        later = (t.get("links") or {}).get("later")
        out = {} if later else learn.on_accept(self, p, t, passed, note, by)
        conf = self.autoflow()

        def tell(gave_up: str = "") -> dict:
            v = {"passed": passed, "note": note, "by": by, "redo": bool(out.get("refix")), "gave_up": gave_up}
            for fn in self.listeners:
                try:
                    out.update(fn(p, t, v) or {})
                except Exception as e:  # noqa: BLE001 - an app's trouble must not undo the verdict
                    self.store.event(t["id"], self.BY, "flow", "验收结果没能通知到%s（%s）" % (getattr(fn, "app", "应用"), e))
            return out
        if later:  # an app's own ticket the line never worked on (a feature's parent): nothing to learn, merge or redo here
            return tell()
        if passed:
            out["release"] = self._ship(p, t, conf, by)
            return tell()
        if not self.switched_on(conf, p) or self.held(t["id"]):
            return tell("有人接手，不自动重改" if self.switched_on(conf, p) else "自动处理没开，不自动重改")
        ad, _ = learn._adopted(self.store, t["id"])
        if not ad:
            return tell("改动不是自动提交的，由改的人返工")  # nothing automatic was sent back: whoever made the change reworks it
        n = sum(1 for e in self.store.events(t["id"]) if e["kind"] == "reject")
        if n > int(conf.get("refix") or 0):
            self.store.event(t["id"], self.BY, "flow", "已经退回 %d 次，不再自动重改，转人工处理" % n)
            return tell("已经退回 %d 次，自动重改用完" % n)
        try:
            agent = self._flow_agent(conf, p)
        except ValueError as exc:
            return tell(str(exc))
        if not agent:
            return tell("没有可用的智能体，不自动重改")
        root = self.root(p)
        base = ad.get("branch") if ad.get("branch") and learn._resolve(root, ad["branch"]) else ""
        self.store.event(t["id"], self.BY, "flow", "验收没通过，带着退回原因重新修改（第 %d 次）%s" % (n, "，接着分支 " + base if base else ""))
        self._flow_fix(p, t["id"], conf, agent, base)
        out["refix"] = True
        return tell()

    def ship_again(self, p: dict, t: dict, by: str) -> dict:
        """A person fixed what held the merge up (a dirty checkout, a lock): try again."""
        if (t.get("links") or {}).get("later"):
            raise ValueError("这张工单不在自动处理线上，没有要合并的改动")
        evs = self.store.events(t["id"])
        last = lambda *kinds: max([e["id"] for e in evs if e["kind"] in kinds] or [0])
        if t["status"] != "closed" or last("accept") < max(last("adopt"), last("reject")):
            raise ValueError("只有最近一次改动验收通过、之后没被退回的工单可以合并")
        if last("release") > last("adopt"):
            raise ValueError("这次改动已经合并过了")
        return self._ship(p, t, self.autoflow(), by)

    def _ship(self, p: dict, t: dict, conf: dict, by: str) -> dict:
        """Accepted: merge the change into the main line and give it a version. A conflict goes back to the agent to
        redo on the current main line; anything else that stops the merge is said on the ticket for a person."""
        from . import release
        try:
            r = release.ship(self, p, t, by)
        except Exception as e:  # noqa: BLE001 - the verdict stands whatever happens to the merge
            r = {"state": "waiting", "why": "合并时出错：%s" % e}
        st = self.store
        if r["state"] == "merged":
            st.event(t["id"], self.BY, "release", "已合并进主干 %s，版本 %s（提交 %s）" % (r["main"], r["version"], r["commit"]),
                     {"version": r["version"], "tag": r["tag"], "commit": r["commit"]})
            for fn in self.on_release:  # the standing preview of the main line follows the new version
                try:
                    fn(p, t, r)
                except Exception as e:  # noqa: BLE001 - the merge stands whatever a listener does
                    st.event(t["id"], self.BY, "flow", "新版本已合并，但后续处理没做成（%s）" % e)
        elif r["state"] == "conflict":
            st.update_ticket(t["id"], self.BY, status="doing")
            n = 1 + sum(1 for e in st.events(t["id"]) if e["kind"] in ("reject", "conflict"))  # this one counts too, as a rejection does
            st.event(t["id"], self.BY, "conflict", "验收通过的改动（%s）和主干 %s 上后来的改动冲突，冲突的文件：%s。要在最新的主干上重做同样的改动，行为和验收通过的那版保持一致"
                     % (r["branch"], r["main"], "、".join(r["files"]) or "（没列出）"), {"branch": r["branch"], "files": r["files"]})
            try:
                agent = self._flow_agent(conf, p) if self.switched_on(conf, p) and conf.get("fix") else ""
            except ValueError as exc:
                st.event(t["id"], self.BY, "flow", str(exc))
                agent = ""
            if agent and not self.held(t["id"]) and n <= int(conf.get("refix") or 0):
                st.event(t["id"], self.BY, "flow", "交回智能体在最新的主干上重做这次改动，做完再验收")
                from .agents import git
                self._flow_fix(p, t["id"], conf, agent, git(self.root(p), "rev-parse", r["main"]).strip())
            else:
                why = ("有人接手" if self.held(t["id"]) else "重做次数用完了（%d 次）" % (n - 1) if agent else
                       "自动处理没开" if not (self.switched_on(conf, p) and conf.get("fix")) else "没有可用的智能体")
                st.event(t["id"], self.BY, "flow", "%s，需要有人在最新的主干上重做，或手动合并分支 %s" % (why, r["branch"]))
        elif r["state"] in ("waiting", "none"):
            st.event(t["id"], self.BY, "flow", ("验收通过了，还没合并进主干：%s。处理好后在工单上点“重试合并”" if r["state"] == "waiting" else
                                                "验收通过了，没有自动合并：%s") % r["why"], {"release": r["state"]})
        return r

    def recheck(self, rid: int, by: str, wait: bool = False) -> dict:
        """Build a finished change again without redoing it (after the build setup was fixed, say). In the background
        unless `wait`; when the build passes and the ticket is still on the automatic line, the change is committed
        as if its own run had just passed; a failed build leaves it for a person."""
        from .fixloop import recheck, start_recheck
        r = self.store.run(rid)
        if not r or r["mode"] != "fix":
            raise ValueError("只有修改代码的运行可以重新验证")
        if rid in self.rechecking:
            raise ValueError("这次改动正在重新验证")
        if r["status"] != "done" or not r["diff"] or (r["decision"] and not r["decision"].startswith("accepted:")):
            raise ValueError("这次运行没有可以重新验证的改动")
        operation = start_recheck(self.runner, rid, by)
        self.rechecking.add(rid)
        tid = r["ticket_id"]

        def go():
            try:
                v = recheck(self.runner, rid, operation=operation, by=by)
            except Exception as e:  # noqa: BLE001
                if tid:
                    self.store.event(tid, by, "flow", "重新验证没做成（%s）" % e, {"run": rid})
                return {"error": str(e)}
            finally:
                self.rechecking.discard(rid)
            run = self.store.run(rid)
            said = {"pass": "构建通过", "fail": "构建没通过", "skip": "没有跑构建（%s）" % v.get("skip")}.get(v["check"], v.get("skip") or "当前验证尚未完整结束")
            if tid:
                self.store.event(tid, by, "flow", "重新验证了运行 #%d 的改动（没改代码）：%s" % (rid, said), {"run": rid, "check": v["check"]})
                conf = self.autoflow()
                t = self.store.ticket(tid)
                if v["check"] == "pass" and not run["decision"] and self.switched_on(conf, run["project_id"]) and not self.held(tid) and t["status"] == "doing":
                    self._flow_commit(self.store.project(run["project_id"]), tid, conf, run)
            return v
        if wait:
            return go()
        try:
            threading.Thread(target=go, daemon=True).start()
        except BaseException as exc:
            self.rechecking.discard(rid)
            self.rechecks.finish(operation["id"], 125, "重新验证未能启动：%s" % exc)
            raise
        return {"started": True, "run": rid, "operation": operation["id"]}

    def fix_gate(self, p: dict, diff: str, conf: dict, rid: int | None = None) -> str:
        """Why a change should wait for a person instead of being committed unattended ("" when it need not)."""
        from .. import config as cfgmod
        from .fixloop import verified
        v = verified(self.data_dir, rid) if rid else {}
        if v.get("verification_current") is False:
            return "当前重新验证尚未有效完成，先检查停止回执或重新验证"
        if v.get("check") == "fail":
            bad = [c for c in v.get("commands") or [] if c.get("exit_code")]
            return "%d 轮修改后构建测试仍没通过（%s）" % (v.get("rounds") or 0, bad[0]["command"] if bad else "构建测试")
        if v.get("vague_fail"):
            return "诊断判了不通过但没说清阻断项，留给人看"
        if v.get("verdict") == "fail":
            return "诊断认为还没解决（%s）" % str((v.get("diagnosis") or {}).get("cause") or "见运行结果")[:80]
        if v.get("beyond_plan"):
            return "改了方案没列的文件 %s" % "、".join(v["beyond_plan"][:3])
        from ..fsutil import match_any
        try:
            globs = list(cfgmod.load(Path(p["root"])).get("protected") or [])
        except Exception:  # noqa: BLE001
            globs = []
        globs += self.TEST_GLOBS
        lines = sum(1 for x in diff.splitlines() if x[:1] in "+-" and not x.startswith(("+++", "---")))
        cap = conf.get("max_lines")
        if isinstance(cap, dict):  # {"<project key>": n}: one platform serving projects with different limits
            cap = cap.get(p.get("key", ""), cap.get("*"))
        cap = int(cap) if cap not in (None, "") else 400
        if lines > cap:
            return "改动 %d 行，超过自动提交上限 %d 行" % (lines, cap)
        touched, gone = [], []
        for part in re.split(r"(?m)^(?=diff --git )", diff):
            m = re.match(r"diff --git a/(\S+) b/", part)
            if not m:
                continue
            if re.search(r"(?m)^deleted file mode", part):
                gone.append(m.group(1))
            elif not re.search(r"(?m)^new file mode", part) and match_any(m.group(1), globs):
                touched.append(m.group(1))
        if gone:
            return "删除了文件 %s" % "、".join(gone[:3])
        if touched:
            return "改了已有的测试或受保护文件 %s" % "、".join(touched[:3])
        return ""

    def verification_wait(self, rid: int) -> dict:
        """Read-only next action; a completed implementation is not a current verification."""
        from .fixloop import verified
        from .recheck_operations import read_status
        if verified(self.data_dir, rid).get("verification_current") is not False:
            return {}
        try:
            op = read_status(self.data_dir, rid) or {}
        except (OSError, ValueError):
            op = {}
        life = op.get("lifecycle") if isinstance(op.get("lifecycle"), dict) else {}
        recovery = life.get("recovery") if isinstance(life.get("recovery"), dict) else {}
        blocked = (recovery.get("state") == "blocked" or
                   (not op.get("owner_active") and op.get("status") in ("done", "failed", "cancelled", "blocked") and op.get("blocked")))
        running = not blocked and (op.get("status") in ("queued", "running") or life.get("finished") is False)
        why = ("正在重新验证，等待本次检查完成；旧结果已失效" if running else
               "重新验证已中断，旧结果已失效；请查看记录后重新验证" if op.get("can_retry") is True else
               "旧验证结果已失效；请检查停止回执，当前不能采纳或签收")
        return {"state": "doing" if running else "you", "status": "running" if running else "failed" if op.get("can_retry") else "blocked",
                "why": why, "run": rid, "operation": op.get("id")}

    def take_over(self, t: dict, hold: bool, who: str) -> dict:
        """A person takes the ticket off the automatic line, or hands it back so it carries on from where it stopped."""
        st = self.store
        links = dict(t.get("links") or {})
        if bool(links.get("hold")) == hold:
            return t
        if hold:
            links["hold"] = who
        else:
            links.pop("hold", None)
            links.pop("handwork", None)
        t = st.update_ticket(t["id"], who, links=links)
        st.event(t["id"], who, "flow", "人工接管：自动处理暂停，正在跑的步骤跑完后不再接着往下走" if hold else "交回自动处理")
        if not hold:
            self.resume(st.project(t["project_id"]), t)
        return st.ticket(t["id"])

    def next_step(self, t: dict, conf: dict | None = None, retry: bool = False) -> tuple[str, dict | None]:
        """Which automatic step an open ticket is waiting for ("" when none: done, taken over, running, or needs a person).
        A step that failed or was cancelled stops the line; with `retry` (a person handing the ticket on) it is run again."""
        conf = conf or self.autoflow()
        lk = t.get("links") or {}
        if not self.switched_on(conf, t["project_id"]) or lk.get("hold") or lk.get("later") or t["status"] not in ("new", "analyzing", "confirm", "doing"):
            return "", None
        runs = [r for r in self.store.runs(ticket_id=t["id"]) if r["mode"] in ("analyze", "plan", "fix")]
        if retry:
            runs = [r for r in runs if r["status"] not in ("failed", "cancelled")]
        if any(r["status"] in ("queued", "running") for r in runs):
            return "", None
        last = {}
        for r in sorted(runs, key=lambda r: r["id"]):
            last[r["mode"]] = r
        fx, pl, an = last.get("fix"), last.get("plan"), last.get("analyze")
        if fx and fx["status"] == "done" and not fx["decision"] and not (pl and pl["id"] > fx["id"]):
            fx = self.store.run(fx["id"])  # the list leaves out the diff
            return ("commit", fx) if fx["diff"] and not self.fix_gate(self.store.project(t["project_id"]), fx["diff"], conf, fx["id"]) else ("", None)
        if pl and pl["status"] == "done" and not (fx and fx["id"] > pl["id"]):
            return ("fix", pl) if conf.get("fix") else ("", None)
        if an and an["status"] == "done" and not (pl and pl["id"] > an["id"]):
            return ("plan", an) if conf.get("plan") and self.FILE_LINE.findall(an["result"] or "") else ("", None)
        if not an or an["status"] != "done":
            return "analyze", None
        return "", None

    def resume(self, p: dict, t: dict) -> str:
        """Carry an open ticket on from its last finished step. Returns the step started ("" for none)."""
        conf = self.autoflow()
        step, run = self.next_step(self.store.ticket(t["id"]), conf, retry=True)
        if step == "commit":
            self._flow_commit(p, t["id"], conf, run)
            return step
        agent = self._flow_agent(conf, p)
        if not step or not agent:
            return ""
        if step == "analyze":
            self._flow_analyze(p, t["id"], conf)
            return step
        if t["status"] != "doing":
            self.store.update_ticket(t["id"], self.BY, status="doing")
        (self._flow_fix if step == "fix" else self._flow_plan)(p, t["id"], conf, agent)
        return step

    # Tickets that were there before the automatic flow (or came in while it was off) wait until someone hands them
    # over; then they go through one or two at a time so a backlog does not start dozens of agents at once.
    def waiting(self, p: dict | None) -> list:
        conf = self.autoflow()
        if not conf.get("on"):
            return []
        ps = [p] if p else self.store.projects()
        out = []
        for x in ps:
            for t in self.store.tickets(x["id"]):
                if (t["status"] in ("new", "analyzing", "confirm", "doing") and not (t.get("links") or {}).get("open_ac")
                        and self.next_step(t, conf)[0]):  # criteria still 待确认 are not swept up by "hand all over"
                    out.append(t)
        return out

    def catch_up(self, p: dict | None, who: str) -> int:
        todo = [t["id"] for t in self.waiting(p)]
        if not todo:
            return 0
        if getattr(self, "_catching", None) and self._catching.is_alive():
            self._queue = list(dict.fromkeys(self._queue + todo))
            return len(todo)
        self._queue = todo
        for tid in todo:
            self.store.event(tid, who, "flow", "交给自动处理（已有工单排队，同时最多 %d 张）" % self.PARALLEL)

        def work():
            st = self.store
            while self._queue:
                busy = st.one("SELECT COUNT(*) n FROM runs WHERE author=? AND status IN ('queued','running')", (self.BY,))["n"]
                if busy >= self.PARALLEL:
                    time.sleep(2)
                    continue
                t = st.ticket(self._queue.pop(0))
                if t:
                    try:
                        self.resume(st.project(t["project_id"]), t)
                    except Exception as e:  # noqa: BLE001 - one bad ticket must not stop the rest
                        st.event(t["id"], self.BY, "flow", "自动处理没有启动：%s" % e)
                time.sleep(1)  # let the step register as running before counting again
        self._catching = threading.Thread(target=work, daemon=True)
        self._catching.start()
        return len(todo)
    PARALLEL = 2
