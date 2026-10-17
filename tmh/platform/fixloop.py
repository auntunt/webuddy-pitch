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
   build or test is a fail whatever it says. On a fail it names the files to revise and what each must do, and
   only those run again, up to `rounds` more times (3; more rounds hardly help). When no build or tests run there
   is one round only, and the diagnosis is made only for a change split across files; a small change goes
   straight to a person.

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
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import testbox
from .agents import MODE_TEXT, build_prompt, earlier_session, follow_up, git, worktree_diff

FENCE = r"```%s[ \t]*\n(.*?)```"


def fenced(label: str, text: str):
    """The JSON in the last ```<label> block of an agent's answer, or None."""
    m = re.findall(FENCE % re.escape(label), text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m[-1].strip())
    except ValueError:
        return None


def clean(text: str) -> str:
    """An answer without its machine-readable blocks."""
    return re.sub(r"```tmh-(plan|msg|diag)[ \t]*\n.*?```", "", text or "", flags=re.S).strip()


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


def settings(data_dir: Path) -> dict:
    conf = {"check": "", "rounds": 3, "check_timeout": 1200, "max_files": 16, "split_from": 5}
    f = Path(data_dir) / "autoflow.json"
    if f.exists():
        try:
            conf.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in conf})
        except ValueError:
            pass
    return conf


class FixLoop:
    def __init__(self, runner, rid, project, ticket, agent, conf, model, explicit, prompt, wt):
        self.r, self.st, self.rid = runner, runner.store, rid
        self.p, self.t, self.agent, self.conf = project, ticket, agent, conf
        self.wt, self.prompt = Path(wt), prompt
        self.set = settings(runner.data_dir)
        d = conf[agent].get("defaults") or {}
        self.models = {"fix": model, "edit": model if explicit else d.get("edit", model), "diagnose": model if explicit else d.get("diagnose", model)}
        self.n = 0
        self.ok = False  # at least one agent call finished normally
        self.notes = {}  # file -> what its agent said it did
        self.sid = ""  # the session of the agent making the whole change, continued in the next round
        self.brought = set()  # files the per-file agents asked to bring in
        tb = testbox.settings(runner.data_dir)
        self.box = testbox.TestBox(tb, runner.data_dir) if tb else None  # builds run on the test machine
        self.base = git(self.wt, "rev-parse", "HEAD").strip()
        self.nobuild = ""  # said to every agent when the platform runs no build or tests this time
        self.log = []  # one line per round

    # ------------------------------------------------------------ plumbing
    def say(self, s: str) -> None:
        self.st.append_output(self.rid, "— %s\n" % s)

    def cancelled(self) -> bool:
        return self.st.run(self.rid)["status"] == "cancelled"

    def call(self, mode: str, prompt: str, resume: str = "", fresh: str = "") -> str:
        self.n += 1
        code, out = self.r.invoke(self.rid, self.p, self.t, self.agent, self.conf, mode, prompt, self.wt, self.models[mode], "-%d" % self.n,
                                  resume, fresh)
        if mode == "fix":  # the next round of a whole change continues this session
            f = self.r.data_dir / "runs" / str(self.rid) / ("session-%d.txt" % self.n)
            self.sid = f.read_text(encoding="utf-8").strip() if f.exists() else ""
        self.ok = self.ok or code == 0
        return out or ""

    def context(self) -> str:
        if not hasattr(self, "_ctx"):
            full = build_prompt(self.st, self.p, self.t, "fix")
            self._ctx = full[:full.rfind(MODE_TEXT["fix"])].rstrip() if MODE_TEXT["fix"] in full else full
        return self._ctx

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
        for kind, cmd in seq:
            self.say("构建测试：%s" % cmd)
            t0 = time.time()
            try:
                r = subprocess.run(cmd, shell=True, cwd=str(where), capture_output=True, text=True, errors="replace",
                                   timeout=int(self.set.get("check_timeout") or 1200))
                code, text = r.returncode, r.stdout + "\n" + r.stderr
            except subprocess.TimeoutExpired:
                code, text = -1, "超时（%s 秒）" % self.set.get("check_timeout")
            res = {"kind": kind, "command": cmd, "exit_code": code, "seconds": round(time.time() - t0, 1),
                   "tail": "\n".join(text.strip().splitlines()[-60:])}
            out.append(res)
            self.say("%s，%s 秒" % ("通过" if code == 0 else "失败（退出码 %s）" % code, res["seconds"]))
            if code != 0:
                break
        return out

    def baseline(self, seq: list) -> str:
        """Run the commands on the untouched code once per commit: "" when they pass, otherwise why they can't be used."""
        seq = [x for x in seq if testbox.runs_on(self.wt, x[1], "HEAD")]  # a module the change creates has nothing to build yet
        if not seq:
            return ""
        head = git(self.wt, "rev-parse", "HEAD").strip()
        # "untouched": records from before the baseline was always built without the change (a rebuilt change's
        # own failure was once kept as the commit's) are not reused
        key = hashlib.sha1(json.dumps([head, seq, "untouched"]).encode()).hexdigest()[:16]
        f = self.r.data_dir / "checks" / ("%s-%s.json" % (self.p["key"], key))
        res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if res and not any(x.get("kind") == "setup" for x in res):  # an old record of a failed hand-over says nothing about the code
            self.say("原代码的构建测试结果沿用之前的记录")
        else:
            self.say("先在没改过的代码上跑一遍构建测试，确认这台机器能跑通")
            res = self.execute(seq, untouched=True)
            if not any(x.get("kind") == "setup" for x in res):  # only what the code did is worth keeping for the next ticket
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        bad = [x for x in res if x["exit_code"] != 0]
        if bad and bad[0].get("kind") == "setup":
            return "测试机没准备好（%s）：%s" % (bad[0]["command"], str(bad[0].get("tail") or "")[:300])
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
        full = self.prompt.replace(MODE_TEXT["fix"], self.feedback_text(diag) + self.nobuild + MODE_TEXT["fix"])
        sid, prev = (self.sid, None) if self.sid else earlier_session(self.st, self.r.data_dir, self.t, self.agent, "fix")
        if sid and (prev or self.sid):
            where = ("现在到了可以修改的独立 git 工作树 %s（分支从工单针对的代码版本开出，和刚才看的代码相同），只在这里改。" % self.wt)
            short = (follow_up(self.st, self.t, prev, "fix", where) if prev else
                     "# 再改一轮\n\n" + self.feedback_text(diag) + "还是在 %s 里改。\n\n" % self.wt + MODE_TEXT["fix"])
            short = short.replace(MODE_TEXT["fix"], self.nobuild + MODE_TEXT["fix"], 1) if self.nobuild else short
            self.say("由一个智能体完成整个改动（接着%s的会话）" % ("方案" if prev and prev["mode"] == "plan" else "上一轮" if not prev else "分析"))
            out = self.call("fix", short, resume=sid, fresh=full)
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
                out = self.call("edit", self.context() + "\n\n" + fb + self.nobuild + ask + MODE_TEXT["edit"].replace("{target}", path))
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
        L = [self.context(), "", "## 本轮改动", "```diff", diff[:14000] + ("\n…（后面省略）" if len(diff) > 14000 else ""), "```", "", "## 构建测试"]
        if res:
            for x in res:
                L += ["`%s`：%s（%s 秒）" % (x["command"], "通过" if x["exit_code"] == 0 else "失败，退出码 %s" % x["exit_code"], x["seconds"])]
                if x["exit_code"] != 0:
                    L += ["```", x["tail"][-4000:], "```"]
        else:
            L.append("没有跑：%s。只能读代码判断。" % skip)
        if prev:
            L += ["", "## 上一轮的诊断", json.dumps({k: prev.get(k) for k in ("cause", "guide")}, ensure_ascii=False)[:1500]]
        L += ["", MODE_TEXT["diagnose"]]
        self.say("诊断这一轮的改动（%s）" % (self.models["diagnose"] or "默认模型"))
        out = self.call("diagnose", "\n".join(L))
        d = fenced("tmh-diag", out)
        d = d if isinstance(d, dict) else {}
        d["text"] = clean(out)[:1500]
        return d

    # ------------------------------------------------------------ the loop
    def run(self) -> tuple[int, str]:
        plan = ""
        if self.t:
            done = [r for r in self.st.runs(ticket_id=self.t["id"]) if r["mode"] == "plan" and r["status"] == "done"]
            plan = self.st.run(done[0]["id"])["result"] if done else ""
        goals = plan_files(plan, int(self.set.get("max_files") or 16))
        seq, skip = self.commands(goals)
        if seq:
            why = self.baseline(seq)
            if why:
                seq, skip = [], why
        if seq and self.box:
            self.nobuild = ("## 构建和测试由平台在测试机上跑\n这台机器上没有构建环境。不要尝试编译、跑测试、启动服务或调接口，也不要为此去改构建配置；"
                            "改完后平台会在测试机上编译（%s），没通过的话会把报错发给你再改。\n\n" % "；".join(c for _, c in seq))
        if not seq:
            self.say("不跑构建测试：%s" % skip)
            # otherwise every agent finds out for itself that there is no maven/node/docker here, a third of its commands
            self.nobuild = ("## 这次不跑构建和测试\n%s。不要尝试编译、跑测试、启动服务或调接口（mvn、gradle、npm、java、docker、curl 等），"
                            "也不要为此去改构建配置；只靠读代码确认改动正确，没能验证的写进最后的说明。\n\n" % skip)
        rounds = max(0, int(self.set.get("rounds") if self.set.get("rounds") is not None else 3))
        diag, res, verdict, files = None, [], "unknown", []
        split = len(goals) >= int(self.set.get("split_from") or 0)
        # Without a build or tests nothing new is learnt after the first round: a diagnosis that can only read the
        # code guesses, and the next round acts on the guess (it widened changes and cost a quarter of an hour).
        # So one round; a large change still gets one reading-only review, a small one goes straight to a person.
        if not seq:
            rounds = 0
        review = bool(seq) or split
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
            else:
                self.whole(diag)
            if self.cancelled():
                break
            diff = worktree_diff(self.wt)
            files = sorted(set(re.findall(r"(?m)^diff --git a/(\S+) b/", diff)))
            if not diff.strip():
                self.log.append("第 %d 轮：没有改出代码" % (rnd + 1))
                break
            res = self.execute(seq) if seq else []
            broke = any(x["exit_code"] != 0 for x in res)
            if not review:
                self.log.append("第 %d 轮：改了 %d 个文件；没跑构建测试，改动不大，不另做诊断，交给人验收" % (rnd + 1, len(files)))
                self.say(self.log[-1])
                break
            diag = self.diagnose(diff, res, skip, diag)
            said = str(diag.get("verdict", "")).lower()
            # a failed build or test is a fail whatever the diagnosis says; without a readable verdict the commands decide
            verdict = "fail" if broke or said == "fail" else ("pass" if said == "pass" or res else "unknown")
            self.log.append("第 %d 轮：改了 %d 个文件；%s；诊断%s" % (
                rnd + 1, len(files), ("构建测试" + ("失败" if broke else "通过")) if res else "没跑构建测试",
                "认为已解决" if verdict == "pass" else "认为还没解决" + ("：" + str(diag.get("cause"))[:120] if diag.get("cause") else "")))
            self.say(self.log[-1])
            if verdict != "fail":
                break
        check = ("fail" if any(x["exit_code"] != 0 for x in res) else "pass") if res else "skip"
        # changed although the plan did not list them (a file another file's agent asked to bring in is not)
        beyond = [f for f in files if goals and f not in goals and f not in self.brought]
        if beyond:
            self.say("超出方案：改了方案没列的 %s" % "、".join(beyond[:6]))
        out = {"check": check, "skip": skip if check == "skip" else "", "verdict": verdict, "rounds": len(self.log), "beyond_plan": beyond,
               "split": bool(goals) and split, "files": files, "commands": res,
               "diagnosis": {k: (diag or {}).get(k) for k in ("verdict", "match", "match_why", "evidence", "cause", "guide")}}
        (self.r.data_dir / "runs" / str(self.rid) / "verify.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return (0 if self.ok else 1), self.summary(out, diag)

    def summary(self, v: dict, diag) -> str:
        head = {"pass": "构建测试通过", "fail": "构建测试没通过", "skip": "没有跑构建测试（%s）" % v["skip"]}[v["check"]]
        head += "，诊断" + {"pass": "认为已解决", "fail": "认为还没解决", "unknown": "没有给出结论"}[v["verdict"]]
        L = ["验证：%s（%d 轮）" % (head, v["rounds"]), ""]
        if v.get("beyond_plan"):
            L += ["**超出方案：** 改了方案没列的 %s，请重点看。" % "、".join("`%s`" % f for f in v["beyond_plan"][:8]), ""]
        if self.log:
            L += ["## 每一轮"] + ["- " + x for x in self.log] + [""]
        if diag and v["verdict"] != "pass" and (diag.get("cause") or diag.get("guide")):
            L += ["## 还差什么", str(diag.get("cause") or ""), str(diag.get("guide") or ""), ""]
        if self.notes:
            L.append("## 改了什么")
            for f, n in self.notes.items():
                if n:
                    L += ["**%s**" % f if f != "（整体）" else "", n, ""]
        if diag and diag.get("text"):
            L += ["## 诊断说明", diag["text"]]
        return "\n".join(x for x in L if x is not None).strip()


def verified(data_dir: Path, rid: int) -> dict:
    f = Path(data_dir) / "runs" / str(rid) / "verify.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recheck(runner, rid: int) -> dict:
    """Build an earlier change again without changing it: the same baseline and build the fix loop runs, on the
    change as it stands (its worktree, or for an adopted change its commit). Overwrites the run's verify.json and
    returns it. The diagnosis stays as it was: one made without a build result may still name something the build
    cannot see (a missing endpoint compiles fine), so a change it judged unsolved still waits for a person."""
    st = runner.store
    r = st.run(rid)
    if not r or r["mode"] != "fix":
        raise ValueError("只有修改代码的运行可以重新验证")
    if r["status"] != "done":
        raise ValueError("这次运行没有正常结束，没有可验证的改动")
    if not r["diff"]:
        raise ValueError("这次运行没有改出代码")
    p = st.project(r["project_id"])
    root = Path(p["root"])
    t = st.ticket(r["ticket_id"]) if r["ticket_id"] else None
    temp = None
    if not r["decision"]:
        wt = Path(r["workdir"])
        if not wt.is_dir():
            raise ValueError("改动的工作树已经不在了")
    elif r["decision"].startswith("accepted:"):
        sha = r["decision"].rsplit("@", 1)[-1]
        parent = git(root, "rev-parse", sha + "^").strip()
        temp = wt = runner.data_dir / "worktrees" / ("recheck-%d" % rid)
        git(root, "worktree", "remove", "--force", str(wt), check=False)
        git(root, "worktree", "add", "--detach", "-f", str(wt), parent)
        change = subprocess.run(["git", "-C", str(root), "diff", "--binary", parent, sha], capture_output=True).stdout
        subprocess.run(["git", "-C", str(wt), "apply", "--whitespace=nowarn", "-"], input=change, check=True, capture_output=True)
    else:
        raise ValueError("这次改动已经放弃了")
    fl = FixLoop.__new__(FixLoop)
    fl.r, fl.st, fl.rid, fl.p, fl.t, fl.wt = runner, st, rid, p, t, wt
    fl.set = settings(runner.data_dir)
    tb = testbox.settings(runner.data_dir)
    fl.box = testbox.TestBox(tb, runner.data_dir) if tb else None
    fl.base = git(wt, "rev-parse", "HEAD").strip()
    try:
        fl.say("重新验证（不改代码）：在%s上构建这次的改动" % ("测试机" if fl.box else "本机"))
        files = sorted(set(re.findall(r"(?m)^diff --git a/(\S+) b/", worktree_diff(wt))))
        seq, skip = fl.commands({f: "" for f in files})
        res = []
        if seq:
            why = fl.baseline(seq)
            if why:
                seq, skip = [], why
        if seq:
            res = fl.execute(seq)
        check = ("fail" if any(x["exit_code"] != 0 for x in res) else "pass") if res else "skip"
    finally:
        if temp:
            git(root, "worktree", "remove", "--force", str(temp), check=False)
    v = verified(runner.data_dir, rid)
    v.update({"check": check, "skip": skip if check == "skip" else "", "commands": res,
              "rechecked": time.strftime("%Y-%m-%d %H:%M:%S")})
    v.pop("diagnosis_dropped", None)
    (runner.data_dir / "runs" / str(rid)).mkdir(parents=True, exist_ok=True)  # a change taken from a branch has no run folder yet
    (runner.data_dir / "runs" / str(rid) / "verify.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    fl.say("重新验证：%s" % {"pass": "构建通过", "fail": "构建没通过", "skip": "没有跑构建（%s）" % skip}[check])
    return v
