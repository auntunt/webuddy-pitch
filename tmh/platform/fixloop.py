"""Changing code for a ticket: per-file agents, a real build and test run, and a diagnosis that sends the work back.

One "修改代码" run goes like this, in its own git worktree:

1. The plan run ends with a machine-readable list of the files to change, including the callers, configuration
   and tests that have to change with them (```tmh-plan {"files": [{"path", "goal"}]}```).
2. Each listed file gets its own agent that may change only that file and sends what it needs from other files
   as messages (```tmh-msg [{"to", "need"}]```). A file that gets a message after it ran runs once more with it;
   a message to a file outside the list brings that file in. Edits an agent makes outside its own file are put back.
   Without a file list the whole change is made by one agent, as before.
3. The project's build and test commands run in the worktree (configured ones first, otherwise detected; they are
   run on the untouched code first, and when that already fails they cannot tell anything and are skipped).
4. A diagnosis agent (the strongest model) reads the change and the results and decides pass or fail. A failed
   build or test is a fail whatever it says. A fail has to name what blocks it (an acceptance criterion missed, with
   the input that goes wrong and where); doubts go to "advisory", and a fail naming nothing is no verdict. The next
   change of the same ticket is diagnosed against the last one's blockers first, and a ticket whose changes keep
   failing is marked as going in circles. On a fail it names the files to revise and what each must do, and
   only those run again, up to `rounds` more times (3; more rounds hardly help). When no build or tests run there
   is one round only. Every change receives a read-only review, including small changes.
   A route may select a different executor; the review records the actual executor and model.

The outcome is kept in runs/<id>/verify.json; a change whose build or tests still fail, or that the diagnosis
says does not solve the ticket, is not committed by the automatic flow.

Settings in <data>/autoflow.json: "check": "" (detect) | "none" | "<command>" | {"<project key>": ...},
"rounds": 3, "check_timeout": 1200, "max_files": 16,
"split_from": 5 (a plan with fewer files is done by one agent: splitting a one- or two-file change only costs
an agent start per file).
After Dev-Primitives / HERMES (arXiv 2610.07832).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import reports, testbox, testbox_mcp
from .agents import (GREENFIELD_EDIT, GREENFIELD_FIX, MODE_TEXT, additional_context_prompt, earlier_session,
                     follow_up, git, learning_context_current, record_session_context,
                     reviewed_delivery_plan, worktree_diff)

FENCE = r"```%s[ \t]*\r?\n(.*?)```"


def _requote(s: str) -> str:
    """Escape the bare quotes models leave inside JSON strings (实现"记住账号"功能): a quote only ends a string before , : } ] or the end."""
    out, inside, i = [], False, 0
    while i < len(s):
        ch = s[i]
        if inside and ch == "\\":
            out.append(s[i:i + 2])
            i += 2
            continue
        if ch == '"':
            if not inside:
                inside = True
            elif re.match(r"\s*(?:[,:}\]]|$)", s[i + 1:]):
                inside = False
            else:
                ch = '\\"'
        out.append(ch)
        i += 1
    return "".join(out)


def loads(block: str):
    try:
        return json.loads(block)
    except ValueError:
        return json.loads(_requote(block))


def fenced(label: str, text: str):
    """The JSON in the last ```<label> block of an agent's answer, or None."""
    m = re.findall(FENCE % re.escape(label), text or "", re.S)
    if m:
        try:
            return loads(m[-1].strip())
        except ValueError:
            return None
    # models sometimes wrap it as ```json {"<label>": {...}}```: the same answer, under the label's own name
    for block in reversed(re.findall(FENCE % "json", text or "", re.S)):
        try:
            j = loads(block.strip())
        except ValueError:
            continue
        if isinstance(j, dict) and isinstance(j.get(label), dict):
            return j[label]
    return None


def clean(text: str) -> str:
    """An answer without its machine-readable blocks."""
    return re.sub(r"```tmh-(plan|msg|diag|report)[ \t]*\n.*?```", "", text or "", flags=re.S).strip()


def rel_path(p) -> str:
    """A file path an agent named, if it is a plain path inside the project ("" otherwise)."""
    p = str(p or "").strip().strip("`").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/") or p.split("/")[0] in (".tmh", ".git"):
        return ""
    return p


def plan_files(text: str, cap: int = 16) -> dict:
    j = fenced("tmh-plan", text)
    files = (j or {}).get("files") if isinstance(j, dict) else None
    out = {}
    for f in files or []:
        if isinstance(f, dict) and rel_path(f.get("path")) and len(out) < cap:
            out[rel_path(f["path"])] = str(f.get("goal") or "").strip()[:600]
    return out


def plan_ac(text: str) -> list:
    """The acceptance criteria a plan names (```tmh-plan {"ac": [...]}```): only those with a criterion and a check."""
    j = fenced("tmh-plan", text)
    out = []
    for a in ((j or {}).get("ac") if isinstance(j, dict) else None) or []:
        if isinstance(a, dict) and str(a.get("text") or "").strip() and str(a.get("check") or "").strip():
            out.append({"id": str(a.get("id") or "A%d" % (len(out) + 1)), "text": str(a["text"]).strip()[:300],
                        "layer": str(a.get("layer") or "").upper()[:2], "check": str(a["check"]).strip()[:300]})
    return out


PRIOR_KEYS = ("blocking", "evidence", "cause", "guide")  # what the next diagnosis checks first
STALL_AFTER = 3  # failed diagnoses in a row on one ticket before asking for a real check instead of another round


def blockers(items) -> list:
    """The blocking items a diagnosis really named: each says which criterion fails and how."""
    return [b for b in items or [] if isinstance(b, dict) and str(b.get("ac") or "").strip() and str(b.get("scenario") or "").strip()]


def settle_fail(diag: dict, said: str) -> tuple:
    """A fail must name what it blocks on. Only diagnoses from before the "blocking" field keep a bare fail."""
    if "blocking" not in diag:
        return said, False
    diag["blocking"] = blockers(diag["blocking"] if isinstance(diag["blocking"], list) else [])
    if said == "fail" and not diag["blocking"]:
        return "unknown", True
    return said, False


PAGE_CHECKS_LATER = """## 之后还有页面实测
这个项目配了页面实测：改动提交到独立分支后，平台会在真实浏览器里逐条实测验收标准并截图，全部通过才会由 AI 验收。所以：
- 页面上实际显示什么、操作后怎样、截图，读代码确认不了的写 unverified；不要因为现在还没有页面实测或截图判不通过，也不要把它列成阻断项；
- 部署、上线、通知这类不在代码里的事由平台流程管，不要因为缺这类记录判不通过；
- 阻断项仍然只写读代码或构建测试能指出的具体失败场景。"""


def settings(data_dir: Path) -> dict:
    conf = {"check": "", "rounds": 3, "check_timeout": 1200, "recheck_timeout": 0, "max_files": 16, "split_from": 5}
    f = Path(data_dir) / "autoflow.json"
    if f.exists():
        try:
            conf.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in conf})
        except ValueError:
            pass
    return conf


def verification_contract(data_dir, project, rid):
    """Bind test inputs without persisting machine credentials in a report."""
    from .. import config
    from . import project_tests
    conf = settings(data_dir)
    check = conf['check']
    if isinstance(check, dict):
        check = check.get(project['key'], check.get('*', ''))
    return project_tests.digest({
        'commands': config.load(Path(project['root'])).get('commands', {}),
        'check': check, 'timeout': conf['check_timeout'],
        'profile': project_tests.view(data_dir, project['key'])['profile'],
        'testbox': testbox.settings(data_dir),
        'criteria': project_tests.criteria_contract(data_dir, rid),
    })


def verification_outcome(value):
    if value.get('verification_current') is False or value.get('code_changed_during_check') or value.get('interruption') or value.get('interrupted'):
        return 'blocked'
    if any(c.get('verification_state') == 'blocked' for c in value.get('commands', [])):
        return 'blocked'
    if value.get('check') == 'fail' or value.get('verdict') == 'fail':
        return 'repair_required'
    if value.get('check') != 'pass' or value.get('verdict') != 'pass':
        return 'manual_required'
    return 'review_required'


def handover_failure(res: list) -> str:
    """Why the code never reached the test machine ("" when it did): says nothing about the code."""
    bad = [x for x in res if x.get("kind") == "setup" and x.get("exit_code") != 0]
    return "测试机没准备好（%s）：%s" % (bad[0]["command"], str(bad[0].get("tail") or "")[:300]) if bad else ""


class FixLoop:
    def __init__(self, runner, rid, project, ticket, agent, conf, model, explicit, prompt, wt):
        self.r, self.st, self.rid = runner, runner.store, rid
        self.p, self.t, self.agent, self.conf = project, ticket, agent, conf
        self.wt, self.prompt = Path(wt), prompt
        self.set = settings(runner.data_dir)
        d = conf[agent].get("defaults") or {}
        self.models = {"fix": model, "edit": model if explicit else d.get("edit", model), "diagnose": model if explicit else d.get("diagnose", model)}
        from .agent_routes import step_agent
        self.agents = {m: step_agent(runner.data_dir, project, m, agent) for m in ("edit", "diagnose")}
        for m, other in self.agents.items():
            if other != agent:  # another engine: its own model for this step, never the main agent's
                if other not in conf:
                    raise ValueError("没有这个智能体：%s" % other)
                self.models[m] = (conf[other].get("defaults") or {}).get(m, "")
        self.n = 0
        self.ok = False  # at least one agent call finished normally
        self.failed_call = False
        self.notes = {}  # file -> what its agent said it did
        self.sid = ""  # the session of the agent making the whole change, continued in the next round
        self.brought = set()  # files the per-file agents asked to bring in
        tb = testbox.settings(runner.data_dir)
        self.box = testbox.TestBox(tb, runner.data_dir) if tb else None  # builds run on the test machine
        from .agents import engine_name
        from . import project_tests
        profile = project_tests.view(runner.data_dir, project['key'])['profile']
        self.remote_testing = not profile and bool(self.box) and engine_name(agent, conf[agent]) == 'codex' and 'cmd' not in conf[agent]
        self.base = git(self.wt, "rev-parse", "HEAD").strip()
        self.nobuild = ""  # said to every agent when the platform runs no build or tests this time
        self.log = []  # one line per round

    # ------------------------------------------------------------ plumbing
    def say(self, s: str) -> None:
        self.st.append_output(self.rid, "— %s\n" % s)

    def cancelled(self) -> bool:
        return self.st.run(self.rid)["status"] == "cancelled" or bool(self.r.stop_reason(self.rid)) or getattr(self, "failed_call", False)

    def call(self, mode: str, prompt: str, resume: str = "", fresh: str = "") -> str:
        if not learning_context_current(self.st, self.r.data_dir, self.p, self.st.run(self.rid), running=True):
            raise ValueError("学习输入或继承会话的采用、来源或授权已变化；当前冻结修复提示词已停止，请重新启动任务")
        self.n += 1
        agent = getattr(self, "agents", {}).get(mode, self.agent)
        code, out = self.r.invoke(self.rid, self.p, self.t, agent, self.conf, mode, prompt, self.wt, self.models[mode], "-%d" % self.n,
                                  resume, fresh)
        if mode == "fix":  # the next round of a whole change continues this session
            f = self.r.data_dir / "runs" / str(self.rid) / ("session-%d.txt" % self.n)
            self.sid = f.read_text(encoding="utf-8").strip() if f.exists() else ""
        self.ok = self.ok or code == 0
        self.failed_call = self.failed_call or code != 0
        return out or ""

    def context(self) -> str:
        if not hasattr(self, "_ctx"):
            full = self.prompt if (self.t or {}).get("links", {}).get("delivery") else additional_context_prompt(self.st, self.r.data_dir, self.p, self.t, self.rid, "fix")
            instruction = GREENFIELD_FIX if GREENFIELD_FIX in full else MODE_TEXT["fix"]
            self._ctx = full[:full.rfind(instruction)].rstrip() if instruction in full else full
        from . import project_tests
        profile = project_tests.view(getattr(self.r, "evidence_root", self.r.data_dir), self.p["key"])["profile"]
        contract = "\n\n## 项目测试契约（平台独立执行）\n按以下命令和报告格式维护实际测试；关联的用例 ID 须精确匹配。不得用空报告、跳过或假结果代替断言。\n" + json.dumps(profile, ensure_ascii=False) if profile else ""
        return self._ctx + contract

    def dirty(self) -> dict:
        """Changed files in the worktree -> their bytes (None for a deleted file)."""
        out = {}
        raw = git(self.wt, "status", "--porcelain", "-z", "--untracked-files=all")
        items = raw.split("\0")
        i = 0
        while i < len(items):
            it = items[i]
            i += 1
            if len(it) < 4:
                continue
            if it[0] in "RC":  # a rename is followed by its old name
                i += 1
            path = it[3:]
            f = self.wt / path
            out[path] = f.read_bytes() if f.is_file() else None
        return out

    def keep_to(self, own: str, before: dict) -> list:
        """Put back what an agent changed outside its own file."""
        after = self.dirty()
        back = []
        for path in set(after) | set(before):
            if path == own or after.get(path, b"\0clean") == before.get(path, b"\0clean"):
                continue
            f = self.wt / path
            if path in before:
                if before[path] is None:
                    f.unlink(missing_ok=True)
                else:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(before[path])
            elif git(self.wt, "ls-files", "--", path).strip():
                git(self.wt, "checkout", "HEAD", "--", path)
            else:
                f.unlink(missing_ok=True)
            back.append(path)
        if back:
            self.say("%s 的智能体改了别的文件，已撤回：%s（要改别的文件请发消息给它的负责方）" % (own, "、".join(sorted(back)[:5])))
        return back

    # ------------------------------------------------------------ checks
    def commands(self, goals: dict | None = None) -> tuple[list, str]:
        """[(kind, command)] to build and test the change, or ([], why not)."""
        from .. import config as cfgmod
        from ..verify import detect_commands
        from . import project_tests
        profile = project_tests.view(getattr(self.r, "evidence_root", self.r.data_dir), self.p["key"])["profile"]
        if profile:
            project_tests.validate(profile)
            return [("test", "project-tests:" + project_tests.digest(profile))], ""
        v = self.set.get("check")
        if isinstance(v, dict):
            v = v.get(self.p["key"], v.get("*", ""))
        if v in ("none", False):
            return [], "设置为不跑构建测试"
        if self.box:  # built on the test machine: the configured command, or compiling what the plan touches
            if isinstance(v, str) and v.strip():
                return [("check", v.strip())], ""
            try:
                given = cfgmod.load(Path(self.p["root"])).get("commands") or {}
            except Exception:  # noqa: BLE001
                given = {}
            if given.get("build") or given.get("test"):
                return [(k, given[k]) for k in ("build", "test") if given.get(k)], ""
            return testbox.build_commands(self.wt, list(goals or {}))
        if isinstance(v, str) and v.strip():
            return [("check", v.strip())], ""
        try:
            cfg = cfgmod.load(Path(self.p["root"]))
        except Exception:  # noqa: BLE001
            cfg = {}
        given = cfg.get("commands") or {}
        found, where = detect_commands(self.wt), ""
        if not any(found.values()):  # backend/ + frontend/ layouts: the first sub-folder that builds on its own
            for d in sorted(x for x in self.wt.iterdir() if x.is_dir() and not x.name.startswith(".")):
                sub = detect_commands(d)
                if any(sub.values()):
                    found, where = sub, d.name
                    break
        seq, missing = [], []
        for k in ("build", "test"):
            if given.get(k):
                seq.append((k, given[k]))
            elif found.get(k):
                exe = shlex.split(found[k])[0]
                if exe.startswith("./") and (self.wt / where / exe).exists() or shutil.which(exe):
                    seq.append((k, ("cd %s && %s" % (shlex.quote(where), found[k])) if where else found[k]))
                else:
                    missing.append(exe)
        seq += [("check", c) for c in given.get("extra_checks") or []]
        if not seq:
            return [], ("本机没有 %s" % "、".join(missing)) if missing else "项目里没找到构建或测试命令（可在 .tmh/config.json 的 commands 里配置）"
        return seq, ""

    def execute(self, seq: list, untouched: bool = False) -> list:
        """Run the build commands on the change, or with `untouched` on the commit without it (the working tree may
        already hold the change, as when a finished change is built again)."""
        if seq and seq[0][1].startswith("project-tests:"):
            from . import project_tests
            try:
                profile = project_tests.view(getattr(self.r, "evidence_root", self.r.data_dir), self.p["key"])["profile"]
                if not profile or seq[0][1] != "project-tests:" + project_tests.digest(profile):
                    raise ValueError("测试配置已变化，请重新验证")
                result = project_tests.execute(self, profile)
                if project_tests.view(getattr(self.r, "evidence_root", self.r.data_dir), self.p["key"])["revision"] != project_tests.digest(profile):
                    raise ValueError("测试期间配置已变化，请重新验证")
                return result + (self.execute(seq[1:]) if len(seq) > 1 else [])
            except (ValueError, OSError) as exc:
                return [{"kind": "test", "command": "项目测试", "exit_code": 1, "seconds": 0, "output": str(exc), "verification_state": "blocked"}]
        if self.box:
            git(self.wt, "add", "-A", "-N", ".")
            patch = b"" if untouched else subprocess.run(["git", "-C", str(self.wt), "diff", "--binary", "HEAD"], capture_output=True).stdout
            return self.box.run(self.p["key"], Path(self.p["root"]), self.base, patch, seq,
                                int(self.set.get("check_timeout") or 1200), self.say)
        if untouched and git(self.wt, "status", "--porcelain", check=False).strip():
            clean = self.r.data_dir / "worktrees" / ("base-%s" % self.rid)
            git(self.wt, "worktree", "remove", "--force", str(clean), check=False)
            git(self.wt, "worktree", "add", "--detach", "-f", str(clean), "HEAD")
            try:
                return self._local(seq, clean)
            finally:
                git(self.wt, "worktree", "remove", "--force", str(clean), check=False)
        return self._local(seq, self.wt)

    def _local(self, seq: list, where: Path) -> list:
        out = []
        base, diff = git(where, "rev-parse", "HEAD").strip(), worktree_diff(where)
        for kind, cmd in seq:
            if self.r.stop_reason(self.rid):
                break
            self.say("构建测试：%s" % cmd)
            t0 = time.time()
            shell = (subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe")]) + ' /d /s /c "' + cmd + '"'
                     if os.name == "nt" else ["/bin/sh", "-c", cmd])
            r, folder = self.r.run_command(self.rid, shell, where,
                timeout=float(self.set.get("check_timeout") or 1200), kind="check:" + kind)
            code, text = r.returncode, r.output
            res = {"kind": kind, "command": cmd, "exit_code": code, "seconds": round(time.time() - t0, 1),
                   "tail": "\n".join(text.strip().splitlines()[-60:]), "output": text,
                   "reason": r.reason, "evidence": str(folder.relative_to(getattr(self.r, "evidence_root", self.r.data_dir))), "cleanup": r.cleanup}
            if code in (124, 127) or r.reason in ("timeout", "cancelled"):
                res['verification_state'] = 'blocked'
            if git(where, "rev-parse", "HEAD").strip() != base or worktree_diff(where) != diff:
                res.update(exit_code=1, verification_state="blocked", code_changed=True,
                           output=text + "\n检查期间代码变化，本轮结果无效")
                code = 1
            out.append(res)
            self.say("%s，%s 秒" % ("通过" if code == 0 else "失败（退出码 %s）" % code, res["seconds"]))
            if code != 0:
                break
        return out

    def baseline(self, seq: list) -> str:
        """Run the commands on the untouched code once per commit: "" when they pass, otherwise why they can't be used."""
        if seq and seq[0][1].startswith("project-tests:"):
            import copy
            import tempfile
            clean = Path(tempfile.mkdtemp(prefix="baseline-", dir=self.r.data_dir)) / "source"
            git(self.wt, "worktree", "add", "--detach", str(clean), self.base)
            baseline_loop = copy.copy(self)
            baseline_loop.wt = clean
            try:
                res = baseline_loop.execute(seq)
                self.baseline_result = {"base": self.base, "commands": res,
                    "state": "pass" if res and all(x["exit_code"] == 0 for x in res) else "fail"}
            finally:
                git(self.wt, "worktree", "remove", "--force", str(clean), check=False)
                clean.parent.rmdir()
            # A new requirement may legitimately fail on the original code.
            # Keep that observation, and still run the candidate's checks.
            return ""
        seq = [x for x in seq if testbox.runs_on(self.wt, x[1], "HEAD")]  # a module the change creates has nothing to build yet
        if not seq:
            return ""
        head = git(self.wt, "rev-parse", "HEAD").strip()
        # "untouched": records from before the baseline was always built without the change (a rebuilt change's
        # own failure was once kept as the commit's) are not reused
        key = hashlib.sha1(json.dumps([head, seq, "untouched", testbox.settings(self.r.data_dir), self.set.get("check_timeout")]).encode()).hexdigest()[:16]
        f = self.r.data_dir / "checks" / ("%s-%s.json" % (self.p["key"], key))
        res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if res and not any(x.get("kind") == "setup" for x in res):  # an old record of a failed hand-over says nothing about the code
            self.say("原代码的构建测试结果沿用之前的记录")
        else:
            self.say("先在没改过的代码上跑一遍构建测试，确认这台机器能跑通")
            res = self.execute(seq, untouched=True)
            if not self.r.stop_reason(self.rid) and not any(x.get("kind") == "setup" for x in res):  # interruption says nothing about baseline code
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        self.baseline_result = {"base": head, "commands": res, "state": "pass" if res and all(x["exit_code"] == 0 for x in res) else "fail"}
        bad = [x for x in res if x["exit_code"] != 0]
        if bad and bad[0].get("kind") == "setup":
            return handover_failure(bad)
        return "原代码在这台机器上跑 `%s` 就失败（退出码 %s）" % (bad[0]["command"], bad[0]["exit_code"]) if bad else ""

    # ------------------------------------------------------------ the steps
    def feedback_text(self, diag: dict | None) -> str:
        if not diag:
            return ""
        L = ["## 上一轮诊断：还没解决"]
        for k, n in (("evidence", "证据"), ("cause", "原因"), ("guide", "这一轮怎么改")):
            if diag.get(k):
                L.append("%s：%s" % (n, str(diag[k])[:1500]))
        return "\n".join(L) + "\n\n"

    def whole(self, diag) -> None:
        """One agent makes the whole change. It continues the session that analysed and planned the ticket (or, in a
        later round, its own session), so it does not read the code all over again."""
        instruction = GREENFIELD_FIX if GREENFIELD_FIX in self.prompt else MODE_TEXT["fix"]
        full = self.prompt.replace(instruction, self.feedback_text(diag) + self.nobuild + instruction)
        # Delivery inputs are versioned. Always send the full reviewed packet, including retry evidence.
        delivery = (self.t or {}).get("links", {}).get("delivery")
        sid, prev = ("", None) if delivery else ((self.sid, None) if self.sid else earlier_session(self.st, self.r.data_dir, self.t, self.agent, "fix"))
        if prev and sid:
            record_session_context(self.r.data_dir, self.rid, prev["id"])
        if sid and (prev or self.sid):
            where = ("现在到了可以修改的独立 git 工作树 %s（分支从工单针对的代码版本开出，和刚才看的代码相同），只在这里改。" % self.wt)
            short = (follow_up(self.st, self.t, prev, "fix", where) if prev else
                     "# 再改一轮\n\n" + self.feedback_text(diag) + "还是在 %s 里改。\n\n" % self.wt + MODE_TEXT["fix"])
            short = short.replace(MODE_TEXT["fix"], self.nobuild + MODE_TEXT["fix"], 1) if self.nobuild else short
            self.say("由一个智能体完成整个改动（接着%s的会话）" % ("方案" if prev and prev["mode"] == "plan" else "上一轮" if not prev else "分析"))
            # Session reuse is a performance choice, not permission to omit the current contract.
            out = self.call("fix", short + "\n\n## 本轮完整任务（以当前资料为准）\n" + full, resume=sid, fresh=full)
        else:
            self.say("由一个智能体完成整个改动")
            out = self.call("fix", full)
        self.notes["（整体）"] = clean(out)[:2000]

    def collaborate(self, goals: dict, diag) -> None:
        active = dict(goals)
        inbox = {p: [] for p in active}
        seen = {}
        cap = int(self.set.get("max_files") or 16)
        fb = self.feedback_text(diag)
        for turn in (1, 2):
            todo = list(active) if turn == 1 else [p for p in active if len(inbox[p]) > seen.get(p, -1)]
            if turn == 2 and todo:
                self.say("把其他文件发来的要求交给 %s 再改一次" % "、".join(todo[:6]))
            for path in todo:  # may grow while it runs: a message can bring in a new file
                if self.cancelled():
                    return
                if turn == 2 and len(inbox[path]) <= seen.get(path, -1):
                    continue
                seen[path] = len(inbox[path])
                ask = ("## 你负责的目标\n%s\n\n" % active[path]) if active[path] else ""
                if inbox[path]:
                    ask += "## 其他文件发来的要求\n" + "\n".join("- " + m for m in inbox[path]) + "\n\n"
                self.say("改 %s（%s）" % (path, self.models["edit"] or "默认模型"))
                before = self.dirty()
                instruction = GREENFIELD_EDIT if GREENFIELD_FIX in self.prompt else MODE_TEXT["edit"]
                out = self.call("edit", self.context() + "\n\n" + fb + self.nobuild + ask + instruction.replace("{target}", path))
                if self.cancelled():
                    return  # Preserve even incomplete edits for inspection and a new run.
                self.keep_to(path, before)
                self.notes[path] = clean(out)[:800]
                for m in fenced("tmh-msg", out) or []:
                    to = rel_path(m.get("to")) if isinstance(m, dict) else ""
                    if not to or to == path or not str(m.get("need") or "").strip():
                        continue
                    if to not in active:
                        if len(active) >= cap:
                            self.say("%s 要求 %s 配合，但这次涉及的文件已到上限 %d 个，没有再加" % (path, to, cap))
                            continue
                        active[to], inbox[to] = "", []
                        self.brought.add(to)
                        self.say("%s 需要 %s 配合，把它也加进来" % (path, to))
                        todo.append(to)
                    inbox[to].append("%s：%s" % (path, str(m["need"]).strip()[:600]))

    def diagnose(self, diff: str, res: list, skip: str, prev: dict | None) -> dict:
        from .code_review import review
        return review(self, diff, res, skip, prev)

    def diagnose_part(self, diff: str, res: list, skip: str, prev: dict | None) -> dict:
        L = [self.context(), "", "## 本轮改动", "```diff", diff, "```", "", "## 构建测试"]
        if res:
            for x in res:
                L += ["`%s`：%s（%s 秒）" % (x["command"], "通过" if x["exit_code"] == 0 else "失败，退出码 %s" % x["exit_code"], x["seconds"])]
                if x["exit_code"] != 0:
                    L += ["```", x["tail"][-4000:], "```"]
        else:
            L.append("没有跑：%s。只能读代码判断。" % skip)
        if prev:
            L += ["", "## 上一轮的诊断", json.dumps({k: prev.get(k) for k in PRIOR_KEYS if prev.get(k)}, ensure_ascii=False)[:2500]]
        else:
            earlier = next(((rid, v) for rid, v in self.earlier_fixes()[:1] if (v.get("diagnosis") or {}).get("verdict") == "fail"), None)
            if earlier:
                L += ["", "## 这张工单上一次修改（#%d）的诊断" % earlier[0],
                      json.dumps({k: earlier[1]["diagnosis"].get(k) for k in PRIOR_KEYS if earlier[1]["diagnosis"].get(k)}, ensure_ascii=False)[:2500]]
        acs = self.criteria()
        if acs:
            L += ["", "## 逐条核对的验收标准"] + ["- %s：%s" % (a["id"], a["text"]) for a in acs]
        from . import browser_verify
        if browser_verify.conf(self.r.data_dir, self.p["key"]):
            L += ["", PAGE_CHECKS_LATER]
        L += ["", MODE_TEXT["diagnose"]]
        self.say("诊断这一轮的改动（%s）" % (self.models["diagnose"] or "默认模型"))
        out = self.call("diagnose", "\n".join(L))
        out, fixed = reports.repair("diagnose", out, lambda ask: self.call("diagnose", ask))
        if fixed:
            self.say("诊断没按格式给出结论块，已让它按原回答补上")
        d = fenced("tmh-diag", out)
        d = d if isinstance(d, dict) else {}
        if "blocking" not in d and isinstance(d.get("blocking_issues"), list):
            d["blocking"] = d.pop("blocking_issues")
        d["text"] = clean(out)[:1500]
        if fixed:
            d["format_repaired"] = True
        return d

    def criteria(self) -> list:
        """What the change is accepted against: the criteria the client confirmed, else the plan's."""
        from .signoff import client_ac
        from . import project_tests
        data = getattr(self.r, "evidence_root", self.r.data_dir)
        if project_tests.view(data, self.p['key'])['profile']:
            return project_tests.criteria_contract(data, getattr(self, 'source_run', self.rid))['criteria']
        return (client_ac(data, self.t["key"]) if self.t else []) or plan_ac(getattr(self, "plan", "") or "")

    def earlier_fixes(self) -> list:
        """Earlier finished change runs of this ticket with their verification, newest first."""
        if not self.t:
            return []
        return [(r["id"], _verification(self.r.data_dir, r["id"])) for r in self.st.runs(ticket_id=self.t["id"])
                if r["mode"] == "fix" and r["status"] == "done" and r["id"] < self.rid]

    # ------------------------------------------------------------ the loop
    def run(self) -> tuple[int, str]:
        plan = ""
        if self.t:
            if (self.t.get("links") or {}).get("delivery"):
                try:
                    plan = reviewed_delivery_plan(self.st, self.t)["result"]
                except ValueError as e:
                    return 1, str(e)
            else:
                done = [r for r in self.st.runs(ticket_id=self.t["id"]) if r["mode"] == "plan" and r["status"] == "done"]
                plan = self.st.run(done[0]["id"])["result"] if done else ""
        self.plan = plan
        round_evidence = []
        goals = plan_files(plan, int(self.set.get("max_files") or 16))
        seq, skip = self.commands(goals)
        contract = verification_contract(self.r.data_dir, self.p, self.rid)
        if seq:
            why = self.baseline(seq)
            if why:
                seq, skip = [], why
        if seq and self.box:
            self.nobuild = ("## 构建和测试由平台在测试机上跑\n这台机器上没有构建环境。不要尝试编译、跑测试、启动服务或调接口，也不要为此去改构建配置；"
                            "改完后平台会在测试机上编译（%s），没通过的话会把报错发给你再改。\n\n" % "；".join(c for _, c in seq))
        if not seq:
            self.say("未配置固定构建命令：%s" % skip)
            # otherwise every agent finds out for itself that there is no maven/node/docker here, a third of its commands
            self.nobuild = ("## 这次不跑构建和测试\n%s。不要尝试编译、跑测试、启动服务或调接口（mvn、gradle、npm、java、docker、curl 等），"
                            "也不要为此去改构建配置；只靠读代码确认改动正确，没能验证的写进最后的说明。\n\n" % skip)
        if self.remote_testing:
            self.nobuild = testbox_mcp.INSTRUCTION + '\n固定构建命令仍由平台复核；测试机执行失败须修复后重测。\n'
        rounds = max(0, int(self.set.get("rounds") if self.set.get("rounds") is not None else 3))
        diag, res, verdict, files, vague = None, [], "unknown", [], False
        split = len(goals) >= int(self.set.get("split_from") or 0)
        # No repeated speculative fix rounds without execution evidence, but every
        # completed change receives one read-only code review.
        if not seq and not self.remote_testing:
            rounds = 0
        if goals and split:
            self.say("按方案分工修改 %d 个文件：%s" % (len(goals), "、".join(goals)))
        elif goals:
            self.say("方案只涉及 %d 个文件（%s），由一个智能体改完，不分工" % (len(goals), "、".join(goals)))
        for rnd in range(rounds + 1):
            if self.cancelled():
                break
            self.say("第 %d 轮" % (rnd + 1))
            if rnd == 0:
                targets = goals
            else:
                targets = {}
                for f in (diag or {}).get("files") or []:
                    if isinstance(f, dict) and rel_path(f.get("path")):
                        targets[rel_path(f["path"])] = str(f.get("goal") or "").strip()[:600]
                if not targets and goals:  # the diagnosis named no file: the planned ones look again
                    targets = {p: "" for p in goals}
            if targets and split:
                self.collaborate(targets, diag)
                if self.remote_testing and not self.cancelled():
                    self.call('fix', self.context() + testbox_mcp.INSTRUCTION + '\n各文件修改已完成。现在编写/更新测试脚本并执行测试机验证；不要更改业务代码，失败原因交给下一轮修复。')
            else:
                self.whole(diag)
            if self.cancelled():
                break
            diff = worktree_diff(self.wt)
            files = sorted(set(re.findall(r"(?m)^diff --git a/(\S+) b/", diff)))
            if not diff.strip():
                self.log.append("第 %d 轮：没有改出代码" % (rnd + 1))
                break
            if not seq and not goals and self.box and rnd == 0:
                # the plan named no files: what to compile on the test machine is known only now, from the change
                late, why = self.commands({f: "" for f in files})
                why = why or (self.baseline(late) if late else "")
                if late and not why:
                    seq, skip = late, ""
                    self.say("方案没列文件，按改动的文件在测试机上构建测试：%s" % "；".join(c for _, c in seq))
                elif why:
                    skip = why
            candidate_base = git(self.wt, "rev-parse", "HEAD").strip()
            res = self.execute(seq) if seq else []
            if self.cancelled():
                break
            lost = handover_failure(res)
            if lost:
                self.say(lost + "；不是代码的问题，这一轮按没跑构建处理")
                skip, res = lost, []
            if self.remote_testing:
                res.append(testbox_mcp.latest_result(self.r.data_dir, self.rid, self.wt))
            broke = any(x["exit_code"] != 0 for x in res)
            diag = self.diagnose(diff, res, skip, diag)
            candidate_changed = worktree_diff(self.wt) != diff or git(self.wt, "rev-parse", "HEAD").strip() != candidate_base
            contract_changed = verification_contract(self.r.data_dir, self.p, self.rid) != contract
            if candidate_changed or contract_changed:
                diag["verdict"] = "unknown"
                diag["review"].update(complete=False, uncovered=["审查期间代码变化，请重新验证"])
            round_evidence.append({"round": rnd + 1, "base": candidate_base, "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
                "verification_contract": contract, "commands": res, "diagnosis": diag,
                "invalidated": candidate_changed or contract_changed,
                "impact": {"changed_files": files, "planned_files": list(goals), "repair_targets": list(targets)},
                "scope": {"criteria": plan_ac(plan), "declared": (fenced("tmh-plan", plan) or {}).get("scope", {}),
                          "reviewed": diag.get("scope", {}), "coverage_basis": "configured_checks"}})
            if candidate_changed or contract_changed:
                skip = "验证期间代码或检查契约变化，请重新验证"
                break
            said = str(diag.get("verdict", "")).lower()
            said, vague = settle_fail(diag, said)
            vague = vague or diag.get("vague_fail", False)
            if vague:  # a fail that names nothing it blocks on cannot send the work back
                self.say("诊断判了不通过，但没有列出阻断项，按没有给出结论处理，留给人看")
            diag["verdict"] = said
            # Commands prove their own checks, not a missing model diagnosis. Keep timeout/unreadable
            # reviews unknown even when compilation/tests are green; never invent an implementation verdict.
            verdict = "fail" if broke or said == "fail" else ("pass" if said == "pass" else "unknown")
            self.log.append("第 %d 轮：改了 %d 个文件；%s；诊断%s" % (
                rnd + 1, len(files), ("构建测试" + ("失败" if broke else "通过")) if res else "没跑构建测试",
                "认为已解决" if verdict == "pass" else "未给出结论" if verdict == "unknown" else "认为还没解决" + ("：" + str(diag.get("cause"))[:120] if diag.get("cause") else "")))
            self.say(self.log[-1])
            if verdict != "fail" or any(x.get("verification_state") == "blocked" for x in res):
                break
        check = ("fail" if any(x["exit_code"] != 0 for x in res) else "pass") if res else "skip"
        # changed although the plan did not list them (a file another file's agent asked to bring in is not)
        beyond = [f for f in files if goals and f not in goals and f not in self.brought]
        if beyond:
            self.say("超出方案：改了方案没列的 %s" % "、".join(beyond[:6]))
        out = {"check": check, "skip": skip if check == "skip" else "", "verdict": verdict, "rounds": len(self.log), "beyond_plan": beyond,
               "split": bool(goals) and split, "files": files, "commands": res, "remote_test_required": self.remote_testing,
               "diagnosis": {k: (diag or {}).get(k) for k in ("verdict", "match", "match_why", "evidence", "cause", "guide",
                                                                "blocking", "advisory", "prior", "ac", "review", "scope")}}
        out.update(verification_contract=contract, baseline=getattr(self, "baseline_result", {"base": self.base, "state": "not_run", "commands": []}),
                   round_evidence=round_evidence)
        if round_evidence:
            out.update(checked_base=round_evidence[-1]["base"], checked_diff=diff, scope=round_evidence[-1]["scope"])
            if round_evidence[-1]["invalidated"]:
                out.update(check="fail", verdict="unknown", verification_current=False, skip=skip)
        if (diag or {}).get("format_repaired"):
            out["diagnosis"]["format_repaired"] = True
        if vague and verdict == "unknown":
            out["vague_fail"] = True
        if (diag or {}).get("verdict") == "fail":
            streak = 1
            for _, v in self.earlier_fixes():
                if str((v.get("diagnosis") or {}).get("verdict") or "").lower() != "fail":
                    break
                streak += 1
            if streak >= STALL_AFTER:
                out["stalled"] = streak
        stopped = self.r.stop_reason(self.rid) if hasattr(self.r, "stop_reason") else ""
        if stopped:
            out.update(stopped_reason=stopped, verdict="unknown", interrupted=True)
        out['outcome'] = verification_outcome(out)
        if out['outcome'] in ('repair_required', 'blocked', 'manual_required'):
            out['manual_reason'] = '验证受阻，补齐条件后重新验证' if out['outcome'] == 'blocked' else '达到本轮停止条件，保留代码和证据等待处理'
        (self.r.data_dir / "runs" / str(self.rid) / "verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return (124 if stopped == "timeout" else 125 if stopped else 0 if self.ok and not getattr(self, "failed_call", False) else 1), self.summary(out, diag)

    def summary(self, v: dict, diag) -> str:
        head = {"pass": "构建测试通过", "fail": "构建测试没通过", "skip": "没有跑构建测试（%s）" % v["skip"]}[v["check"]]
        head += "，诊断" + {"pass": "认为已解决", "fail": "认为还没解决", "unknown": "没有给出结论"}[v["verdict"]]
        L = ["验证：%s（%d 轮）" % (head, v["rounds"]), ""]
        if v.get("beyond_plan"):
            L += ["**超出方案：** 改了方案没列的 %s，请重点看。" % "、".join("`%s`" % f for f in v["beyond_plan"][:8]), ""]
        if self.log:
            L += ["## 每一轮"] + ["- " + x for x in self.log] + [""]
        if v.get("stalled"):
            L += ["**在兜圈子：** 这张工单连续 %d 次修改，诊断都没通过。再让 AI 按诊断改大概率还会冒出新问题，"
                  "建议先实测（预览）或由人定方向。" % v["stalled"], ""]
        blocking = [b for b in (diag or {}).get("blocking") or [] if isinstance(b, dict)]
        if blocking and v["verdict"] == "fail":
            L += ["## 阻断项"] + ["- %s：%s（%s）" % (b.get("ac") or "", b.get("scenario") or "", b.get("where") or "") for b in blocking] + [""]
        if diag and v["verdict"] != "pass" and (diag.get("cause") or diag.get("guide")):
            L += ["## 还差什么", str(diag.get("cause") or ""), str(diag.get("guide") or ""), ""]
        advisory = [str(a) for a in (diag or {}).get("advisory") or [] if a]
        if advisory:
            L += ["## 建议（不影响结论）"] + ["- " + a for a in advisory[:8]] + [""]
        said = [a for a in (diag or {}).get("ac") or [] if isinstance(a, dict) and a.get("id")]
        if said:
            word = {"pass": "通过", "fail": "没通过", "unverified": "没法确认"}
            L += ["## 逐条验收"] + ["- %s：%s（%s）" % (a["id"], word.get(str(a.get("result") or "").lower(), "没给结论"), a.get("how") or "")
                                    for a in said[:12]] + [""]
        if self.notes:
            L.append("## 改了什么")
            for f, n in self.notes.items():
                if n:
                    L += ["**%s**" % f if f != "（整体）" else "", n, ""]
        if diag and diag.get("text"):
            L += ["## 诊断说明", diag["text"]]
        return "\n".join(x for x in L if x is not None).strip()


def _verification(data_dir: Path, rid: int) -> dict:
    f = Path(data_dir) / "runs" / str(rid) / "verify.json"
    try:
        value = json.loads(f.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _project_tests_current(data_dir, rid, value):
    from . import project_tests
    issue = project_tests.current_issue(data_dir, rid, value)
    if not issue and value.get("verification_contract"):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect((Path(data_dir) / "platform.db").resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            project = db.execute("SELECT p.* FROM projects p JOIN runs r ON r.project_id=p.id WHERE r.id=?", (rid,)).fetchone()
        try:
            if not project or verification_contract(data_dir, dict(project), rid) != value["verification_contract"]:
                issue = "测试命令、执行环境配置或验收契约已变化，请重新验证"
        except (OSError, ValueError) as exc:
            issue = "无法读取当前检查契约，请修复配置后重新验证：%s" % exc
    if issue:
        return {"check": "unknown", "verdict": "unknown", "commands": [], "diagnosis": {},
                "verification_current": False, "outcome": "blocked", "skip": issue, "previous_current_verification": value}
    return value


def verified(data_dir: Path, rid: int) -> dict:
    """A previous pass is historical as soon as a newer verification begins."""
    v = _verification(data_dir, rid)
    from .recheck_operations import read_status
    try:
        operation = read_status(data_dir, rid)
    except (OSError, ValueError) as exc:
        operation = {"status": "blocked", "result": str(exc), "can_retry": False}
    if not operation:
        return _project_tests_current(data_dir, rid, v)
    bound = v.get("recheck_operation") or {}
    current = (isinstance(bound, dict) and bound.get("id") == operation.get("id")
               and bound.get("source_run") == rid and operation.get("source_run") == rid
               and (operation.get("lifecycle") or {}).get("finished") is True
               and operation.get("can_retry") is True and operation.get("status") in ("done", "failed")
               and (v.get("check") != "pass" or (operation.get("status") == "done" and operation.get("exit_code") == 0)))
    if current:
        # A copied or later edited verify.json cannot inherit a sealed operation.
        try:
            artifact = json.loads((Path(data_dir) / "verification-operations" / "runs" / str(operation["id"]) / "verification.json").read_text(encoding="utf-8"))
            source = operation.get("source") or {}
            digest = source.get("diff_sha256") or source.get("diffhash")
            current = (artifact == v and source.get("run") == rid
                       and source.get("source_commit", source.get("commit")) == v.get("checked_commit")
                       and source.get("base") == v.get("checked_base")
                       and digest == hashlib.sha256(v.get("checked_diff", "").encode("utf-8")).hexdigest())
        except (OSError, ValueError, TypeError, AttributeError):
            current = False
    if current:
        return _project_tests_current(data_dir, rid, dict(v, verification_current=True))
    return {"check": "unknown", "verdict": "unknown", "commands": [], "diagnosis": {},
            "verification_current": False, "skip": "新的重新验证尚未完成或停止证据不完整，旧结论仅作历史记录",
            "recheck_operation": {"id": operation.get("id"), "status": operation.get("status"), "result": operation.get("result", "")},
            "previous_current_verification": v}


def recheck_operations(runner):
    from .recheck_operations import Operations
    with runner.lock:
        if not hasattr(runner, "rechecks"):
            runner.rechecks = Operations(runner.store, runner.data_dir)
        return runner.rechecks


def start_recheck(runner, rid, by=""):
    r = runner.store.run(rid)
    if not r or r["mode"] != "fix" or r["status"] != "done" or not r["diff"]:
        raise ValueError("这次运行没有可以重新验证的改动")
    if r["decision"] and not r["decision"].startswith("accepted:"):
        raise ValueError("这次改动已经放弃了")
    config = settings(runner.data_dir)
    from .project_library import project_guard, require_run_current
    p = runner.store.project(r['project_id'])
    with project_guard(runner.store, p, execution=True):
        require_run_current(runner.store, p, rid)
        previous = verified(runner.data_dir, rid)
        op = recheck_operations(runner).start(rid, by, float(config.get("recheck_timeout") or config.get("check_timeout") or 1200))
        op["previous_verification"] = previous
        return op


def recheck(runner, rid: int, *, allow_running: bool = False, operation=None, by="", kind="tests") -> dict:
    if kind not in ("tests", "review", "all"):
        raise ValueError("验证类型只能是 tests、review 或 all")
    # Handwork invokes this inside its already-active run and shared budget.
    if allow_running:
        return _recheck(runner, rid, allow_running=True)
    operations = recheck_operations(runner)
    operation = operation or start_recheck(runner, rid, by)
    oid = operation["id"]
    folder = operations.runner.data_dir / "runs" / str(oid)
    from .crash_recovery import _original_bytes
    before = runner.data_dir / "runs" / str(rid) / "verify.json"
    try:
        if before.exists():
            _original_bytes(folder / "verification.before.json", before.read_bytes())
        v = _recheck(runner, rid, operation=operation, kind=kind)
        result = "测试：" + {"pass": "通过", "fail": "失败", "skip": "未执行"}[v["check"]]
        if kind in ("review", "all"):
            result += "；AI Review：" + {"pass": "通过", "fail": "发现阻断问题"}.get((v.get("diagnosis") or {}).get("verdict"), "未形成结论")
        operations.finish(oid, 1 if v["check"] == "fail" else 0, result)
        return verified(runner.data_dir, rid)
    except BaseException as exc:
        try:
            operations.runner.store.append_output(oid, "\n重新验证执行失败：%s\n" % exc)
            if oid in operations.runner.owners:
                operations.finish(oid, 1, "重新验证执行失败：%s" % exc)
        except BaseException as sealing_error:
            try:
                operations.runner.store.append_output(oid, "\n重新验证封存失败：%s\n" % sealing_error)
            except Exception:
                pass  # retain the initiating error; unfinished evidence remains blocked
        raise


def _recheck(runner, rid: int, *, allow_running: bool = False, operation=None, kind="tests") -> dict:
    """Build an earlier change again without changing it: the same baseline and build the fix loop runs, on the
    change as it stands (its worktree, or for an adopted change its commit). Overwrites the run's verify.json and
    returns it. The diagnosis stays as it was for unchanged code. If someone corrects the worktree after the
    model finished, preserve the old evidence but invalidate its diagnosis and refresh the visible diff."""
    st = runner.store
    r = st.run(rid)
    if not r or r["mode"] != "fix":
        raise ValueError("只有修改代码的运行可以重新验证")
    if r["status"] != "done" and not (allow_running and r["status"] == "running"):
        raise ValueError("这次运行没有正常结束，没有可验证的改动")
    if not r["diff"]:
        raise ValueError("这次运行没有改出代码")
    p = st.project(r["project_id"])
    root = Path(p["root"])
    t = st.ticket(r["ticket_id"]) if r["ticket_id"] else None
    temp, sha = None, ""
    from .candidates import for_run
    external = for_run(st, rid)
    if external:
        # External registration is not adoption. Check the exact submitted
        # commit against its explicit base in a disposable verification tree.
        sha = external["commit_sha"]
        parent = external["base_commit"]
        if git(root, "rev-parse", external["ref"]).strip() != sha:
            raise ValueError("外部候选固定引用发生变化")
        temp = wt = (recheck_operations(runner).runner.data_dir if operation else runner.data_dir) / "worktrees" / ("candidate-%d" % (operation["id"] if operation else rid))
        git(root, "worktree", "add", "--detach", str(wt), parent)
        change = subprocess.run(["git", "-C", str(root), "diff", "--binary", "--no-ext-diff", "--no-textconv", parent, sha], capture_output=True, check=True).stdout
        try:
            subprocess.run(["git", "-C", str(wt), "apply", "--whitespace=nowarn", "-"], input=change, check=True, capture_output=True)
        except BaseException:
            git(root, "worktree", "remove", "--force", str(wt), check=False)
            raise
    elif not r["decision"]:
        wt = Path(r["workdir"])
        if not wt.is_dir():
            raise ValueError("改动的工作树已经不在了")
    elif r["decision"].startswith("accepted:"):
        from .preview import _commit
        sha = _commit(root, r["decision"].rsplit("@", 1)[-1])
        if not sha:
            raise ValueError("已采纳的提交不存在或短提交号不唯一，不能改为验证其他版本")
        parent = git(root, "rev-parse", sha + "^").strip()
        temp = wt = (recheck_operations(runner).runner.data_dir if operation else runner.data_dir) / "worktrees" / ("recheck-%d" % (operation["id"] if operation else rid))
        git(root, "worktree", "remove", "--force", str(wt), check=False)
        git(root, "worktree", "add", "--detach", "-f", str(wt), parent)
        change = subprocess.run(["git", "-C", str(root), "diff", "--binary", parent, sha], capture_output=True, check=True).stdout
        subprocess.run(["git", "-C", str(wt), "apply", "--whitespace=nowarn", "-"], input=change, check=True, capture_output=True)
    else:
        raise ValueError("这次改动已经放弃了")
    fl = FixLoop.__new__(FixLoop)
    executor = recheck_operations(runner).runner if operation else runner
    fl.r, fl.st, fl.rid, fl.p, fl.t, fl.wt = executor, executor.store, operation["id"] if operation else rid, p, t, wt
    fl.source_run = rid
    fl.set = settings(runner.data_dir)
    plans = [x for x in st.runs(ticket_id=t["id"]) if x["mode"] == "plan" and x["status"] == "done"] if t else []
    fl.plan = st.run(plans[0]["id"])["result"] if plans else ""
    tb = testbox.settings(runner.data_dir)
    fl.box = testbox.TestBox(tb, runner.data_dir) if tb else None
    fl.base = git(wt, "rev-parse", "HEAD").strip()
    checked_diff = worktree_diff(wt)
    contract = verification_contract(runner.data_dir, p, rid)
    changed = checked_diff != r["diff"]
    if operation:
        recheck_operations(runner).bind(operation["id"], {"run": rid, "decision": r["decision"], "commit": sha,
            "base": fl.base, "workdir": str(wt), "diff": checked_diff, "kind": kind,
            "diff_sha256": hashlib.sha256(checked_diff.encode("utf-8")).hexdigest()})
    try:
        diagnosis = None
        if kind == "review":
            old = operation.get("previous_verification") or {}
            old_base = old.get("checked_base") or ((old.get("diagnosis") or {}).get("review") or {}).get("base")
            current = not changed and old_base == fl.base and old.get("verification_contract") == contract and old.get("verification_current") is not False and old.get("check") in ("pass", "fail", "skip")
            files = sorted(set(re.findall(r"(?m)^diff --git a/(\S+) b/", checked_diff)))
            res = old.get("commands", []) if current else []
            check = old["check"] if current else "skip"
            skip = old.get("skip", "") if current else "代码已变化或旧测试无效，请重新运行测试"
        else:
            fl.say("重新验证（不改代码）：在%s上构建这次的改动" % ("测试机" if fl.box else "本机"))
            files = sorted(set(re.findall(r"(?m)^diff --git a/(\S+) b/", worktree_diff(wt))))
            seq, skip = fl.commands({f: "" for f in files})
            res = []
            if seq:
                why = fl.baseline(seq)
                if why:
                    seq, skip = [], why
            remote_receipt = None
            if _verification(runner.data_dir, rid).get('remote_test_required'):
                receipts = sorted((runner.data_dir / 'runs' / str(rid) / 'testbox').glob('*.json'))
                if not fl.box or not receipts:
                    raise ValueError('本次改动需要测试机验证；测试机配置或测试脚本回执缺失')
                remote_receipt = json.loads(receipts[-1].read_text(encoding='utf-8'))
                script = remote_receipt['script']
                script_path = (wt / script).resolve()
                if not script_path.is_relative_to(wt.resolve()) or not script_path.is_file():
                    raise ValueError('本次版本缺少测试脚本，不能只以编译通过代替测试机验证')
                seq.append(('test', testbox_mcp.script_command(script, fl.box._detect() == 'windows', max(1, min(1170, int(fl.set.get('check_timeout') or 1200) - 30)))))
            if seq:
                res = fl.execute(seq)
                if remote_receipt and res and res[-1]['kind'] == 'test':
                    res[-1]['command'] = remote_receipt['command']
                lost = handover_failure(res)
                if lost:
                    skip, res = lost, []
            check = ("fail" if any(x["exit_code"] != 0 for x in res) else "pass") if res else "skip"
        if kind in ("review", "all"):
            from .code_review import manual
            diagnosis = manual(fl, runner, r, operation, res, skip, checked_diff)
        final_diff = worktree_diff(wt)
        stale = final_diff != checked_diff or git(wt, "rev-parse", "HEAD").strip() != fl.base
        contract_changed = verification_contract(runner.data_dir, p, rid) != contract
        if stale:
            check = "fail"
    finally:
        if temp:
            git(root, "worktree", "remove", "--force", str(temp), check=False)
    v = _verification(runner.data_dir, rid)
    # Keep every superseded check, including a failed temporary test mutation followed
    # by a clean rerun. Its diff/output/diagnosis must not disappear when current fields refresh.
    previous = dict(v)
    history = list(previous.pop("previous_verifications", []))
    if previous:
        history.append({"diff": r["diff"], "verification": previous})
    if changed or stale or contract_changed or v.get("verification_contract") != contract:
        v.update(verdict="unknown", diagnosis={},
                 diagnosis_invalidated="代码或检查契约已变化，旧诊断不再适用于当前改动")
        v.pop("stalled", None)  # counted from the old diagnosis
        v.pop("vague_fail", None)
        # An adopted run represents the immutable commit. Tests may edit its temporary
        # checkout, but those edits are neither adopted nor part of that run's visible diff.
        st.update_run(rid, diff=checked_diff if temp else final_diff)
    v.update({"verification_contract": contract,
              "baseline": getattr(fl, "baseline_result", v.get("baseline") if v.get("verification_contract") == contract and v.get("baseline") else {"base": fl.base, "state": "not_run", "commands": []}),
              "test_reuse": {"reused": kind == "review" and current, "reason": "代码、基准和检查契约一致" if kind == "review" and current else "本轮未复用测试"},
              "check": check, "skip": skip if check == "skip" else "", "commands": res,
              "files": files, "code_changed_during_check": stale, "checked_commit": sha, "checked_base": fl.base,
              "checked_diff": checked_diff, "previous_verifications": history,
              "rechecked": time.strftime("%Y-%m-%d %H:%M:%S")})
    if stale:
        v["after_check_diff"] = final_diff
        v["diagnosis_invalidated"] = "代码在重新验证期间变化，当前结果不能证明新改动；请重新验证"
    else:
        v.pop("after_check_diff", None)  # the previous value remains in previous_verifications
    if diagnosis is not None and not stale and not contract_changed:
        v["diagnosis"] = diagnosis
        v["verdict"] = "fail" if check == "fail" or diagnosis["verdict"] == "fail" else diagnosis["verdict"]
        v.pop("diagnosis_invalidated", None)
        v.pop("vague_fail", None)
        v.pop("stalled", None)
    if contract_changed:
        v.update(check="fail", verdict="unknown", diagnosis={}, verification_current=False,
                 skip="验证期间检查契约变化，请重新验证")
    v['scope'] = {"declared": (fenced("tmh-plan", fl.plan) or {}).get("scope", {}),
                  "reviewed": (v.get("diagnosis") or {}).get("scope", {}), "changed_files": files,
                  "coverage_basis": "configured_checks"}
    v['verification_current'] = not contract_changed
    v["verification_kind"] = kind
    v.pop("diagnosis_dropped", None)
    (runner.data_dir / "runs" / str(rid)).mkdir(parents=True, exist_ok=True)  # a change taken from a branch has no run folder yet
    if operation:
        from .supervised_process import _atomic_json
        stopped = executor.stop_reason(operation["id"])
        if stopped:
            v.update(check="fail", verdict="unknown", diagnosis={}, interruption=stopped)
        v.update(recheck_operation={"id": operation["id"], "source_run": rid}, verification_current=not contract_changed)
        v['outcome'] = verification_outcome(v)
        _atomic_json(executor.data_dir / "runs" / str(operation["id"]) / "verification.json", v)
        _atomic_json(runner.data_dir / "runs" / str(rid) / "verify.json", v)
    else:
        v['outcome'] = verification_outcome(v)
        (runner.data_dir / "runs" / str(rid) / "verify.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    fl.say("重新验证：%s" % {"pass": "构建通过", "fail": "构建没通过", "skip": "没有跑构建（%s）" % skip}[v["check"]])
    return v
