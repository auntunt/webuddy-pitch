"""Built-in coding agents: run Claude Code or Codex against a ticket.

A run is one non-interactive agent invocation in a project directory:

- analyze / plan / kb run in the project itself, read-only for code
  (Claude: only read tools and tmh; Codex: --sandbox read-only; kb may write
  .tmh/knowledge pages).
- fix runs in a git worktree on branch tmh/<KEY> under the platform's data
  folder, never in the user's working copy. The diff is recorded; a person
  accepts it (commit on the branch, ready to merge) or discards it.

The prompt is the ticket plus the slice of the knowledge base `tmh context`
picks for it, so the agent starts from the right flows, tables and code
locations instead of reading the repository.

Agents are configurable in <data>/agents.json, never with keys in it:
{"claude": {"bin": "claude", "args": [], "timeout": 1800},
 "codex": {"bin": "codex", "args": ["-m", "gpt-5-codex"]},
 "my-agent": {"cmd": ["my-agent", "--dir", "{workdir}", "{prompt_file}"], "title": "自研智能体"}}
A custom agent gets {prompt}, {prompt_file}, {workdir}, {mode}, {model} substituted.

Each run can name a model; the person picks it when starting the task. Without one,
the agent's per-mode default applies (planning and code changes on the strongest
model, reading and writing knowledge on the balanced one). An agent's choices and
defaults can be changed in agents.json: "models": [["opus", "Opus"], ...],
"defaults": {"fix": "opus", ...}. "" means whatever the agent itself is set to.
Model credentials come from the environment the server was started in
(see `tmh agent-config` for third-party models).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .store import RUN_MODES, Store, now

BUILTIN = {
    "claude": {"title": "Claude Code", "bin": "claude",
               "models": [["opus", "Opus（最强，适合方案和改码）"], ["sonnet", "Sonnet（均衡，适合分析和写知识页）"], ["haiku", "Haiku（最快最省）"]],
               "defaults": {"plan": "opus", "fix": "opus", "analyze": "sonnet", "kb": "sonnet", "ask": "sonnet",
                            "edit": "sonnet", "diagnose": "opus"}},
    "codex": {"title": "Codex", "bin": "codex",
              "models": [["gpt-5-codex", "GPT-5 Codex"], ["gpt-5", "GPT-5"]], "defaults": {}},
}
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-\[\]/]{0,79}$")  # alias or full id; passed as one argv item


def pick_model(c: dict, mode: str, model) -> str:
    """None → the agent's default for this mode; "" → the agent's own setting; otherwise the id, checked."""
    if model is None or model == "auto":
        return (c.get("defaults") or {}).get(mode, "")
    model = str(model).strip()
    if model and not MODEL_ID.match(model):
        raise ValueError("模型名不合法：%s" % model)
    return model
READ_TOOLS = ["Read", "Grep", "Glob", "LS", "Bash(tmh:*)", "Bash(python3 .tmh/tool/tmh.py:*)",
              "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git blame:*)"]

MODE_TEXT = {
    "analyze": """## 你的任务：分析定位（只读，不要修改任何文件）
1. 先读上面“知识库”部分列出的知识页和业务流；需要时用 `tmh flows <id>`、`tmh impact <类名或表名>`、`tmh context <关键词>` 查，再打开具体代码。
2. 回答：这个工单涉及哪些业务流、哪些表、哪些代码位置；问题最可能的原因或需求要落在哪里。
3. 每条结论标明【核实】（读过代码确认）或【推断】（依据不足），给出 文件:行号。
4. 最后列出还需要人确认的问题。

输出用中文，按这几节：结论（3 句以内）、涉及的业务流与表、代码位置、原因分析、待确认问题。""",
    "plan": """## 你的任务：修改方案（只读，不要修改任何文件）
基于工单和前面的分析结论，给出可以直接照做的修改方案：
1. 要改哪些文件、哪些方法，每处改什么（给 文件:行号）。
2. 影响到哪些业务流和表，会不会改变其他业务流的行为（用 `tmh impact` 核实）。
3. 风险和回退方式。
4. 怎么验证：要跑的测试、要手工检查的业务操作。
5. 验收标准（AC）：每条写清“做到什么算修好”、层级和检查方式。层级：L1 读代码/契约/图谱即可证明；L2 独立环境跑测试或 tmh verify；
   L3 部署到可测环境后回测；L4 要人在真实系统里确认。根因要有证据（文件:行号、日志、复现步骤），只是推测的写“待确认”。
   没有验收标准的方案不会进入自动改代码。

输出用中文，按这几节：方案概要、逐处修改、影响面、风险、验证步骤、验收标准。

最后附上一个机器读的文件清单（文件多时修改代码会按文件分工，每个文件交给一个只改它的智能体）：
只列必须改动的文件：改动本身，以及不跟着改就会出错的调用方、配置和已有测试（用 `tmh impact` 核实，漏掉的文件没人会改）。
看过、确认不用改的文件不要列；不要为了能跑测试去改构建配置（pom.xml、package.json 之类），除非工单本身就是构建问题。
不要新增测试文件，除非验证步骤会真的跑测试、项目里也已有同类测试；建议补的测试写进“验证步骤”给人看。
多数修复只动 1 到 3 个文件，最多 8 个；路径相对项目根目录；新文件也可以列。格式（ac 是第 5 节的验收标准，至少一条）：
```tmh-plan
{"files": [{"path": "src/main/java/.../LeaveService.java", "goal": "这个文件要做到什么（一两句）", "role": "改动|调用方|配置|测试"}],
 "ac": [{"id": "A1", "text": "做到什么算修好", "layer": "L1|L2|L3|L4", "check": "怎么检查"}]}
```""",
    "fix": """## 你的任务：修改代码
你在一个独立的 git 工作树里，改动不会影响任何人的工作目录，由人审阅后再合入。
1. 按工单和前面的方案修改，只改方案列出的文件，改动尽量小，保持原有代码风格；不要顺手重构无关代码。
   不要新增测试文件，除非这次会跑构建测试、项目里也已有同类测试；觉得该补的测试写进最后的说明。
2. 不要改 .tmh/ 下的文件，不要提交（commit）、不要推送；不要为了能跑测试去改构建配置（pom.xml、package.json 之类）。
3. 能编译或有测试时，跑一下相关的部分。
4. 结束时用中文说明：改了哪些文件、为什么这样改、怎么验证、还有什么没做。""",
    "ask": """## 你的任务：回答上面的问题（只读，不要修改任何文件）
你是这个项目的闭环助手，回答维护人员关于工单、业务和代码的问题。
1. 先查知识库：用 `tmh context <关键词>`、`tmh flows <id>`、`tmh impact <类名或表名>`，需要时再打开具体代码。
2. 回答格式固定，三段：
   **结论与边界**：一两句直接回答，并说清楚哪些还不能确定（比如缺日志、缺复现信息）；
   **依据**：最多 5 条，最关键的放前面，每条写成 `文件:行号`、业务流 id（flow:…）、表（tbl:…）或知识页 id，并标【核实】或【推断】；
   **下一步**：一两条具体建议（补什么信息、查哪里、是否值得起草工单）。
3. 找不到依据时，只回答“未检索到依据”，并说明查了哪些地方，不要凭经验补一个结论；根因没查实时写“待确认”，不要把排查方向写成已证实的原因。
4. 不要声称做过你没做的事（比如已合并、已测试、已验收）；需要人做的事写成建议。
5. 简短，中文，不超过 300 字，不贴大段代码和日志。""",
    "edit": """## 你的任务：只修改一个文件
你是负责 `{target}` 这一个文件的智能体，和其他文件的智能体一起完成上面的工单。你在一个独立的 git 工作树里。
目标文件：`{target}`
1. 只改这个文件（不存在就新建）。别的文件需要配合时，不要自己去改，写在最后的消息里交给它的负责方。
2. 改动尽量小，保持原有风格；不要改 .tmh/ 下的文件，不要提交（commit）；不要为了能跑测试去改构建配置。
   这个文件是新的测试文件、而这次不跑构建测试时，不要写它，在说明里写清楚该测什么就行。
3. 可以读任何文件来确认调用方、被调用方的写法。
4. 结束时先用一两句中文说明你改了什么（没改就说为什么不用改），
   再附上发给其他文件的要求（接口变了、调用方要跟着改、配置或测试要补等；没有就写 []）：
```tmh-msg
[{"to": "相对路径", "need": "对方要做到什么"}]
```""",
    "diagnose": """## 你的任务：诊断这次修改（只读，不要修改任何文件）
你在修改后的工作树里。上面是工单、修改方案、本轮的改动和构建测试结果。判断工单是否真的解决了：
1. 要求的行为实现了吗？只是绕过了表面症状吗？
2. 构建、测试有没有失败，有没有引入新问题？跨文件的改动彼此一致吗（签名、调用、配置）？
3. 没解决时，指出证据、最可能的原因、该改哪些文件（路径相对项目根目录）以及每个文件要做到什么，还有本轮漏掉的文件。
4. 逐条对照方案里的验收标准，判断这次改动和工单要的是什么关系：equivalent（等价，每条都做到了）、partial（只做到一部分）、
   different（方向不同，改了别的地方或别的行为）、wrong（改错了，或者是靠删功能、跳过测试绕过去的）。这只是推断，在 match_why 里写依据。
构建或测试失败时不能判定通过。最后输出：
```tmh-diag
{"verdict": "pass 或 fail", "match": "equivalent / partial / different / wrong", "match_why": "对照验收标准的依据", "evidence": "失败的证据", "cause": "原因", "files": [{"path": "相对路径", "goal": "要做到什么"}], "guide": "下一轮怎么改"}
```""",
    "kb": """## 你的任务：撰写知识页
1. 运行 `tmh kb next --page {target}` 领取页面，按它给出的说明阅读代码并填写页面（只改 .tmh/knowledge/ 下的这个页面）。
2. 写完运行 `tmh kb done {target}` 校验，按提示修正直到通过。
3. 不要修改业务代码。最后用中文概括这个页面写了什么、有哪些【推断】需要人确认。""",
}


KB_MANY = """## 你的任务：撰写知识页（这次一共几页，都在同一个代码文件里）
要写的页面：
{targets}

先把它们共用的代码读一遍，再逐页完成：
1. 对每一页运行 `tmh kb next --page <页面 id>`（例如 `tmh kb next --page {first}`）领取，按它给出的说明填写页面（只改 .tmh/knowledge/ 下的这些页面）。
2. 每页写完就运行 `tmh kb done <页面 id>` 校验，按提示修正直到通过，再写下一页。
3. 不要修改业务代码。最后用中文逐页概括写了什么、有哪些【推断】需要人确认。"""


def load_config(data_dir: Path) -> dict:
    p = Path(data_dir) / "agents.json"
    conf = {k: dict(v) for k, v in BUILTIN.items()}
    if p.exists():
        try:
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                conf.setdefault(k, {}).update(v)
        except ValueError:
            pass
    return conf


def available(data_dir: Path) -> list:
    out = []
    for name, c in load_config(data_dir).items():
        exe = (c.get("cmd") or [c.get("bin", name)])[0]
        out.append({"name": name, "title": c.get("title", name), "available": bool(shutil.which(exe)),
                    "custom": "cmd" in c, "models": c.get("models") or [], "defaults": c.get("defaults") or {}})
    return out


# ---------------------------------------------------------------- provenance
def trailers(r: dict, t: dict | None, reviewer: str | None) -> str:
    """Git trailers that say, in the commit itself, that an agent wrote the change and who let it in: the
    Linux kernel's Assisted-by form (agent:model, then the tool), the ticket and run it came from, and the
    evidence package a client can check. A person is named only when one reviewed it."""
    one = lambda v: re.sub(r"[\s:]+", "-", str(v or "").strip())  # noqa: E731 - agent:model is one token in this form
    model = one(r.get("model"))
    out = ["Assisted-by: %s%s webuddy" % (one(r["agent"]), ":" + model if model else "")]
    from .signoff import human
    if reviewer and human(reviewer):  # only a person reviews; system, 告警 or an agent adopting is not a review
        out.append("Reviewed-by: %s" % reviewer)
    if t:
        out.append("Ticket: %s" % t["key"])
        out.append("Evidence: /e/%s" % t["key"])
    out.append("Webuddy-Run: %d" % r["id"])
    return "\n".join(re.sub(r"[\r\n]+", " ", x) for x in out)


# ---------------------------------------------------------------- prompt

def build_prompt(store: Store, project: dict, ticket: dict | None, mode: str, target: str = "", question: str = "", history: list | None = None) -> str:
    root = Path(project["root"])
    out = ["你在维护项目「%s」（目录 %s）。这个项目接入了 tmh：业务知识库在 %s，"
           "查业务流、表和影响面用 `python3 %s <子命令> --repo %s`（下文写作 `tmh <子命令>`）。"
           % (project["name"], root, root / ".tmh" / "knowledge", root / ".tmh" / "tool" / "tmh.py", root), ""]
    if ticket:
        tl = {"bug": "缺陷", "feature": "需求", "change": "变更", "question": "咨询", "ops": "运维"}
        out += ["# 工单 %s：%s" % (ticket["key"], ticket["title"]),
                "类型：%s；优先级：%s；报告人：%s" % (tl.get(ticket["type"], ticket["type"]), ticket["priority"], ticket.get("reporter") or "-"), ""]
        if ticket.get("body"):
            out += ["## 描述", ticket["body"].strip()[:4000], ""]
        ext = ticket.get("external") or {}
        if ext.get("key"):
            out += ["外部工单：%s %s %s" % (ext.get("system", ""), ext["key"], ext.get("url", "")), ""]
        flows = (ticket.get("links") or {}).get("flows") or []
        if flows:
            out += ["## 已关联的业务流", "、".join(flows), ""]
        evs = store.events(ticket["id"]) if ticket.get("id") else []  # an eval case is a ticket without a history
        comments = [e for e in evs if e["kind"] == "comment"][-6:]
        if comments:
            out.append("## 讨论")
            out += ["- %s（%s）：%s" % (c["author"] or "-", c["ts"][5:16], c["body"].strip()[:600]) for c in comments]
            out.append("")
        rejects = [e for e in evs if e["kind"] == "reject"][-3:]
        if rejects:
            out.append("## 验收没通过（之前提交的改动被退回，这次必须解决下面的问题）")
            out += ["- %s（%s）：%s" % (e["author"] or "-", e["ts"][5:16], e["body"].strip()[:800]) for e in rejects]
            out.append("")
        clash = [e for e in evs if e["kind"] == "conflict"][-1:]
        if clash and mode == "fix":
            d = clash[0].get("data") or {}
            out.append("## 这是一次冲突重做（上一版已经验收通过，但合不进主干）")
            out.append(clash[0]["body"].strip()[:800])
            if d.get("branch"):
                out.append("上一版的改动在分支 %s，可以用 `git diff %s^1 %s` 或 `git show %s` 看它改了什么；在当前代码上做出同样的效果，不要扩大范围。"
                           % (d["branch"], d["branch"], d["branch"], d["branch"]))
            out.append("")
        prior = [r for r in store.runs(ticket_id=ticket["id"]) if r["status"] == "done" and r["mode"] in ("analyze", "plan") and r["result"]] if ticket.get("id") else []
        for r in prior[:2][::-1]:
            out += ["## 之前的%s结论（%s，%s）" % (dict(RUN_MODES)[r["mode"]], r["agent"], r["ended"][5:16]), r["result"].strip()[:3000], ""]
        if mode != "ask":
            from .learn import held_out, lessons_text, note_held, note_nomatch, note_used, relevant
            try:
                ls = relevant(store.path.parent, project["key"], ticket, " ".join(r["result"] for r in prior[:2]), root=root)
                if ticket.get("id"):  # an eval case is not a real ticket: nothing about it is counted
                    if ls and held_out(store.path.parent, ticket.get("key") or ""):
                        note_held(store.path.parent, ticket, ls)  # the comparison group: like the others, minus the cards
                        ls = []
                    elif not ls:
                        note_nomatch(store.path.parent, ticket)
                out.append(lessons_text(ls))
                if ticket.get("id"):  # an eval case is not a real ticket: its prompts do not count as using a card
                    note_used(store.path.parent, ticket, ls, mode)
            except OSError:
                pass
        query = "%s %s %s %s" % (ticket["title"], search_words(ticket.get("body") or "")[:600], " ".join(flows), question)
        out.append(knowledge(root, query))
        out.append("")
    elif question:
        out += [knowledge(root, question), ""]
    if history:
        out.append("## 之前的对话")
        out += ["- %s：%s" % ("问" if m["role"] == "user" else "答", m["body"].strip()[:500]) for m in history[-6:]]
        out.append("")
    if question:
        out += ["## 问题", question.strip()[:2000], ""]
    if mode == "kb" and len(target.split()) > 1:  # several small pages of one source file in one run (see survey.py)
        out.append(KB_MANY.replace("{targets}", "\n".join("- " + t for t in target.split())).replace("{first}", target.split()[0]))
    else:
        out.append(MODE_TEXT[mode].replace("{target}", target or "<页面 id>"))
    return "\n".join(out)


def knowledge(root: Path, query: str, budget: int = 6000) -> str:
    from ..graph import graph_path
    if not graph_path(root).exists():
        return "（这个项目还没有知识库。直接按工单描述在代码里定位；建议之后运行 tmh kb build。）"
    from ..context import build_context
    return build_context(root, query, budget).replace("# 与“", "# 知识库：与“", 1)


# ---------------------------------------------------------------- commands

def command(conf: dict, agent: str, mode: str, prompt: str, prompt_file: Path, workdir: Path, last_msg: Path, tool: str = "",
            model: str = "", resume: str = "") -> list:
    """The agent's command line. `resume` continues that agent session (the prompt then only carries what is new);
    a custom "cmd" takes it as {resume}."""
    c = conf.get(agent)
    if not c:
        raise ValueError("没有这个智能体：%s" % agent)
    if "cmd" in c:
        sub = {"{prompt}": prompt, "{prompt_file}": str(prompt_file), "{workdir}": str(workdir), "{mode}": mode, "{model}": model,
               "{resume}": resume}
        return [sub.get(a, a) for a in c["cmd"]]
    exe = c.get("bin", agent)
    extra = list(c.get("args") or [])
    if model:  # the model picked for this run wins over one fixed in agents.json args
        for flag in ("--model", "-m"):
            while flag in extra:
                i = extra.index(flag)
                del extra[i:i + 2]
        extra = (["--model", model] if agent == "claude" else ["-m", model]) + extra
    if agent == "claude":
        read = READ_TOOLS + (["Bash(python3 %s:*)" % tool] if tool else [])
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose"] + (["--resume", resume] if resume else [])  # prompt on stdin
        if mode in ("fix", "edit"):
            cmd += ["--permission-mode", "acceptEdits", "--allowedTools", ",".join(read + ["Edit", "Write", "MultiEdit"])]
        elif mode == "kb":
            cmd += ["--permission-mode", "acceptEdits", "--allowedTools", ",".join(read + ["Edit", "Write"])]
        else:
            cmd += ["--allowedTools", ",".join(read), "--disallowedTools", "Edit,Write,MultiEdit,NotebookEdit"]
        return cmd + extra
    if agent == "codex":
        sandbox = "workspace-write" if mode in ("fix", "edit", "kb") else "read-only"
        return [exe, "exec", "--sandbox", sandbox, "--skip-git-repo-check", "-C", str(workdir),
                "--output-last-message", str(last_msg)] + extra + (["resume", resume] if resume else []) + [prompt]
    raise ValueError("智能体 %s 没有配置 cmd" % agent)


class StreamParser:
    """Turns an agent's stdout into readable log lines and picks out the final answer."""

    def __init__(self, agent: str):
        self.agent = agent
        self.result = ""
        self.text = []
        self.session = ""  # the agent's own session id, to continue it in the next step

    def feed(self, line: str) -> str:
        if self.agent != "claude":
            self.text.append(line)
            m = None if self.session else re.match(r"\s*session id:\s*(\S+)", line)
            if m:
                self.session = m.group(1)
            return line
        s = line.strip()
        if not s.startswith("{"):
            return line
        try:
            ev = json.loads(s)
        except ValueError:
            return line
        t = ev.get("type")
        if t == "assistant":
            out = []
            for b in (ev.get("message") or {}).get("content") or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append(b["text"].rstrip() + "\n")
                    self.text.append(b["text"])
                elif b.get("type") == "tool_use":
                    out.append("▸ %s %s\n" % (b.get("name"), _brief(b.get("input"))))
            return "".join(out)
        if t == "result":
            self.result = ev.get("result") or ""
            cost = ev.get("total_cost_usd")
            return "— 结束：%s，%d 轮%s\n" % ("成功" if not ev.get("is_error") else "出错", ev.get("num_turns") or 0,
                                         "，约 $%.2f" % cost if cost else "")
        if t == "system" and ev.get("subtype") == "init":
            self.session = ev.get("session_id") or self.session
            return "— 启动 %s（模型 %s）\n" % (ev.get("cwd", ""), ev.get("model", ""))
        return ""

    def final(self) -> str:
        if self.result:
            return self.result
        if self.agent == "claude":
            return self.text[-1] if self.text else ""
        return "".join(self.text)[-6000:]


class Timing:
    """Where one agent process spent its time, read off its output as it streams: starting up (up to its first
    reply, which includes connecting), running commands (as the agent reports them), hooks (between "hook: X" and
    "hook: X Completed"), reconnecting (from the line before a run of "Reconnecting" lines to the line after it), and
    the rest, which is the model thinking and the network."""
    REPLY = re.compile(r"^(codex|thinking|exec)$|^\{\"type\":\"(assistant|user)\"")
    CMD = re.compile(r"^ (?:succeeded|exited -?\d+|failed) in ([\d.]+)(ms|s)\b")
    BUSY = re.compile(r"at capacity|overloaded|rate.?limit|too many requests|\b(429|503|529)\b|stream disconnected", re.I)

    def __init__(self, resume: str = ""):
        self.t0 = time.time()
        self.first = None
        self.cmd = self.hooks = 0.0
        self.commands = 0
        self.open = {}
        self.tokens = None
        self.want_tokens = False
        self.resumed = bool(resume)
        self.last = self.t0
        self.reconnects = 0
        self.reconnect = 0.0
        self.rc_from = None
        self.busy = False

    def feed(self, line: str) -> None:
        prev, now_ = self.last, time.time()
        self.last = now_
        s = line.rstrip("\n")
        if s.startswith("ERROR") and self.BUSY.search(s):
            self.busy = True
        if "Reconnecting" in s:
            self.reconnects += 1
            if self.rc_from is None:
                self.rc_from = prev
            return
        if self.rc_from is not None:
            self.reconnect += now_ - self.rc_from
            self.rc_from = None
        if self.first is None and self.REPLY.match(s):
            self.first = now_
        if s == "exec":
            self.commands += 1
        m = self.CMD.match(s)
        if m:
            self.cmd += float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
        h = re.match(r"^hook: (\w+)( Completed| Failed)?$", s)
        if h:
            q = self.open.setdefault(h.group(1), [])
            if not h.group(2):
                q.append(now_)
            elif q:
                self.hooks += now_ - q.pop(0)
        if self.want_tokens:
            self.want_tokens = False
            if re.match(r"^[\d,]+$", s.strip()):
                self.tokens = int(s.strip().replace(",", ""))
        elif s.strip() == "tokens used":
            self.want_tokens = True

    def done(self) -> dict:
        total = max(0.0, self.last - self.t0)
        startup = max(0.0, (self.first or self.last) - self.t0)
        return {"seconds": round(total, 1), "startup": round(startup, 1), "commands": self.commands, "command_seconds": round(self.cmd, 1),
                "hook_seconds": round(self.hooks, 1), "model_seconds": round(max(0.0, total - startup - self.cmd - self.hooks), 1),
                "tokens": self.tokens, "resumed": self.resumed, "busy": self.busy, "reconnects": self.reconnects, "reconnect_seconds": round(self.reconnect, 1)}


BUSY_WAITS = (30, 90, 180)  # seconds to wait before each retry when the model service says it is busy
BUSY_AGAIN = "刚才因为模型服务繁忙中断了。请接着完成上面的任务，按原来的要求给出最终答案。"


def timing_text(t: dict) -> str:
    return "用时 %d 秒%s：启动 %d 秒，模型 %d 秒，命令 %d 条共 %.1f 秒，钩子 %.1f 秒%s%s" % (
        t["seconds"], "（接着上一步的会话）" if t.get("resumed") else "", t["startup"], t["model_seconds"], t["commands"],
        t["command_seconds"], t["hook_seconds"],
        "，重连 %d 次共 %d 秒（已算在启动和模型里）" % (t["reconnects"], t["reconnect_seconds"]) if t.get("reconnects") else "",
        "，%s token" % format(t["tokens"], ",") if t.get("tokens") else "")


def _brief(inp) -> str:
    if not isinstance(inp, dict):
        return ""
    for k in ("command", "file_path", "pattern", "path", "url"):
        if inp.get(k):
            return str(inp[k])[:160]
    return json.dumps(inp, ensure_ascii=False)[:160]


# ---------------------------------------------------------------- git

def git(cwd: Path, *args, check=True) -> str:
    r = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or "git %s 失败" % args[0])
    return r.stdout


def is_git(root: Path) -> bool:
    return shutil.which("git") is not None and subprocess.run(["git", "-C", str(root), "rev-parse", "--git-dir"],
                                                              capture_output=True).returncode == 0


_TEMPLATE_END = re.compile(r"(?m)^.*(友情提示|温馨提示|提问须知|Before submitting|Checklist).*$")


def search_words(body: str) -> str:
    """The part of a ticket body worth searching the knowledge base with: an issue template's headings, images,
    links and closing advice only pull in unrelated pages."""
    m = _TEMPLATE_END.search(body)
    if m and m.start() > 0:
        body = body[:m.start()]
    body = re.sub(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)|https?://\S+", " ", body)
    body = re.sub(r"(?m)^\s*#+\s*[^\n]{0,20}[：:]?\s*$", " ", body)  # bare template headings such as "##### 版本号："
    return re.sub(r"\s+", " ", body).strip()


CONTINUES = {"plan": ("analyze",), "fix": ("plan", "analyze")}  # a step continues the session of the step before it


def max_agents(data_dir: Path) -> int:
    """How many agent runs may go at once (autoflow.json "max_agents"; 0 means no limit)."""
    try:
        return max(0, int(json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("max_agents", 4)))
    except (OSError, ValueError, TypeError):
        return 4


def continue_on(data_dir: Path) -> bool:
    """Whether a ticket's steps continue one agent session (autoflow.json "resume", on unless set false)."""
    try:
        return json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("resume", True) is not False
    except (OSError, ValueError):
        return True


def earlier_session(store, data_dir: Path, ticket: dict | None, agent: str, mode: str) -> tuple[str, dict | None]:
    """The agent session this step can continue: that of the ticket's latest finished step it follows (plan after
    analyze, the change after the plan), run by the same agent. ('', None) when there is none."""
    if not ticket or not ticket.get("id") or mode not in CONTINUES or not continue_on(data_dir):
        return "", None
    for r in sorted(store.runs(ticket_id=ticket["id"]), key=lambda r: r["id"], reverse=True):
        if r["status"] == "done" and r["agent"] == agent and r["mode"] in CONTINUES[mode]:
            f = Path(data_dir) / "runs" / str(r["id"]) / "session.txt"
            return (f.read_text(encoding="utf-8").strip(), r) if f.exists() else ("", None)
    return "", None


def follow_up(store, ticket: dict, prev: dict, mode: str, where: str) -> str:
    """The prompt for a step that continues the previous step's session: only where the code is now, what people
    added since, and the new task."""
    L = ["# 接着做下一步：%s" % dict(RUN_MODES)[mode], "",
         "工单 %s 的上一步（%s）就在这个会话里，上面读过的代码、知识库和结论都还算数，不用重新读一遍；只在需要时打开新的文件。" % (
             ticket["key"], dict(RUN_MODES)[prev["mode"]]), where, ""]
    new = [e for e in store.events(ticket["id"]) if e["kind"] in ("comment", "reject") and e["ts"] > (prev.get("ended") or "")]
    if new:
        L += ["## 上一步之后补充的信息"] + ["- %s（%s）：%s" % (e["author"] or "-", e["ts"][5:16], e["body"].strip()[:800]) for e in new[-6:]] + [""]
    return "\n".join(L) + "\n" + MODE_TEXT[mode]


def code_at(ticket: dict | None) -> str:
    """The commit a ticket is pinned to (links.code_at): it is about the code as it was then, not the current code.
    Used to replay real tickets on the version they were reported against."""
    return str(((ticket or {}).get("links") or {}).get("code_at") or "")


def pinned_view(data_dir: Path, project: dict, rid: int, commit: str, ticket: dict | None = None) -> Path:
    """A detached, throwaway checkout of `commit` for a read-only step (analyze, plan, ask) of a pinned ticket.
    A ticket's steps get it at the same path each time, so a step that continues the previous step's session
    finds the files where that session read them."""
    wt = Path(data_dir) / "worktrees" / ("view-%s" % ticket["key"] if ticket and ticket.get("key") else "view-r%d" % rid)
    wt.parent.mkdir(parents=True, exist_ok=True)
    if wt.exists():  # left over from a step that was cut short
        git(Path(project["root"]), "worktree", "remove", "--force", str(wt), check=False)
    git(Path(project["root"]), "worktree", "add", "--detach", str(wt), commit)
    return wt


def make_worktree(data_dir: Path, project: dict, ticket: dict | None, rid: int, base: str = "") -> tuple[Path, str]:
    root = Path(project["root"])
    if not is_git(root):
        raise RuntimeError("项目目录不是 git 仓库，修改代码需要在独立工作树里进行。请先在项目目录执行：git init && git add -A && git commit -m 基线")
    if subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode != 0:
        raise RuntimeError("项目的 git 仓库还没有任何提交，修改代码要从一个基线提交开始。请先在项目目录执行：git add -A && git commit -m 基线")
    name = "%s-r%d" % (ticket["key"] if ticket else project["key"], rid)
    branch = "tmh/" + name
    wt = Path(data_dir) / "worktrees" / name
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "-b", branch, str(wt), base or "HEAD")
    return wt, branch


def worktree_diff(wt: Path) -> str:
    git(wt, "add", "-A", "-N", ".")
    return git(wt, "diff", "HEAD")


# ---------------------------------------------------------------- runner

class Runner:
    def __init__(self, store: Store, data_dir: Path):
        self.store = store
        self.data_dir = Path(data_dir)
        self.procs = {}
        self.after = {}  # run id -> callback(run) once it finished successfully
        self.charge = None  # callback(run) for every successful run: usage points
        self.lock = threading.Lock()
        self.slots = threading.Condition()  # at most max_agents agent runs at once; the rest wait their turn
        self.busy = set()
        self.waiting = []  # (priority, run id)

    def start(self, project: dict, ticket: dict | None, agent: str, mode: str, author: str, target: str = "", then=None,
              question: str = "", history: list | None = None, session_id=None, batch: str = "", model=None, base: str = "") -> dict:
        if mode not in dict(RUN_MODES):
            raise ValueError("未知模式：%s" % mode)
        conf = load_config(self.data_dir)
        if agent not in conf:
            raise ValueError("没有这个智能体：%s" % agent)
        explicit = model not in (None, "auto")  # a model the person picked applies to every step of the run
        model = pick_model(conf[agent], mode, model)
        if mode == "kb" and not target:
            raise ValueError("撰写知识页需要指定页面 id")
        if mode == "ask" and not question.strip():
            raise ValueError("问题是空的")
        prompt = build_prompt(self.store, project, ticket, mode, target, question, history)
        run = self.store.create_run(project["id"], ticket["id"] if ticket else None, agent, mode, author, prompt, target or question[:200],
                                     session_id=session_id, batch=batch, model=model)
        if ticket and mode != "ask":  # assistant questions don't move or clutter the ticket
            self.store.event(ticket["id"], author, "run", "让 %s%s %s" % (conf[agent].get("title", agent), "（%s）" % model if model else "", dict(RUN_MODES)[mode]),
                             {"run": run["id"], "agent": agent, "mode": mode, "model": model})
            if ticket["status"] == "new" and mode in ("analyze", "plan"):
                self.store.update_ticket(ticket["id"], author, status="analyzing")
            elif ticket["status"] in ("new", "analyzing", "confirm") and mode == "fix":
                self.store.update_ticket(ticket["id"], author, status="doing")
        if then:
            self.after[run["id"]] = then
        th = threading.Thread(target=self._run, args=(run["id"], project, ticket, agent, mode, prompt, conf, model, explicit, base), daemon=True)
        th.start()
        return self.store.run(run["id"])

    def _run(self, rid, project, ticket, agent, mode, prompt, conf, model="", explicit=False, base=""):
        """Waits for a free slot (ticket steps go before knowledge pages), then runs."""
        if mode == "ask" or not self._take(rid, mode):  # a question someone is waiting on never queues
            if mode != "ask":
                return
            return self._go(rid, project, ticket, agent, mode, prompt, conf, model, explicit, base)
        try:
            self._go(rid, project, ticket, agent, mode, prompt, conf, model, explicit, base)
        finally:
            with self.slots:
                self.busy.discard(rid)
                self.slots.notify_all()

    def _take(self, rid, mode) -> bool:
        """Wait for a slot; False when the run was cancelled meanwhile. max_agents in autoflow.json (default 4, 0 = no limit)."""
        item = (1 if mode == "kb" else 0, rid)
        with self.slots:
            self.waiting.append(item)
            try:
                while True:
                    if self.store.run(rid)["status"] == "cancelled":
                        return False
                    limit = max_agents(self.data_dir)
                    if (not limit or len(self.busy) < limit) and min(self.waiting) == item:
                        self.busy.add(rid)
                        return True
                    self.slots.wait(5)
            finally:
                self.waiting.remove(item)
                self.slots.notify_all()

    def _go(self, rid, project, ticket, agent, mode, prompt, conf, model="", explicit=False, base=""):
        st = self.store
        rdir = self.data_dir / "runs" / str(rid)
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "prompt.md").write_text(prompt, encoding="utf-8")
        workdir = Path(project["root"])
        pin, view = code_at(ticket), None
        if pin and mode != "fix":
            try:
                workdir = view = pinned_view(self.data_dir, project, rid, pin, ticket)
            except RuntimeError as e:
                st.update_run(rid, status="failed", ended=now(), result="工单指定的代码版本 %s 取不出来：%s" % (pin[:10], e))
                self._finish_event(ticket, rid, agent, mode, "failed", str(e))
                return
        if pin:
            prompt = prompt.replace("（目录 %s）" % project["root"], "（这张工单针对的是 %s 版本的代码，代码在 %s，只看这里；知识库和 tmh 工具仍在 %s）"
                                    % (pin[:10], "{workdir}", project["root"]), 1)
        if mode == "fix":
            try:
                workdir, branch = make_worktree(self.data_dir, project, ticket, rid, base or pin)
            except (RuntimeError, ValueError) as e:
                st.update_run(rid, status="failed", ended=now(), result=str(e))
                self._finish_event(ticket, rid, agent, mode, "failed", str(e))
                return
            st.append_output(rid, "— 在独立工作树 %s（分支 %s%s）里修改\n" % (workdir, branch, "，接着被退回的分支 " + base if base else ""))
        prompt = prompt.replace("{workdir}", str(workdir))
        st.update_run(rid, status="running", started=now(), workdir=str(workdir))
        try:
            if mode == "fix":
                from .fixloop import FixLoop
                code, result = FixLoop(self, rid, project, ticket, agent, conf, model, explicit, prompt, workdir).run()
            else:
                sid, prev = earlier_session(st, self.data_dir, ticket, agent, mode)
                if sid:
                    code, result = self.invoke(rid, project, ticket, agent, conf, mode, follow_up(st, ticket, prev, mode, "代码仍在 %s。" % workdir),
                                               workdir, model, resume=sid, fresh=prompt)
                else:
                    code, result = self.invoke(rid, project, ticket, agent, conf, mode, prompt, workdir, model)
        finally:
            if view:
                git(Path(project["root"]), "worktree", "remove", "--force", str(view), check=False)
        cancelled = st.run(rid)["status"] == "cancelled"
        f = {"ended": now(), "exit_code": code, "result": (result or "").strip()}
        if mode == "fix":
            try:
                f["diff"] = worktree_diff(workdir)
            except RuntimeError as e:
                f["diff"] = ""
                st.append_output(rid, "— 读取改动失败：%s\n" % e)
        if not cancelled:
            f["status"] = "done" if code == 0 else "failed"
            if code != 0 and not f["result"]:
                f["result"] = "智能体退出码 %s，详见运行日志" % code
        status = "cancelled" if cancelled else f["status"]
        owns = getattr(self.after.get(rid), "owns_status", False)  # a follow-up that decides the next status itself
        if ticket and status == "done" and mode in ("analyze", "plan") and not owns:  # before the run reads as done, so nobody sees a half state
            t = st.ticket(ticket["id"])
            if t["status"] == "analyzing":
                st.update_ticket(t["id"], agent, status="confirm")
        st.update_run(rid, **f)
        self._finish_event(ticket, rid, agent, mode, status, f["result"], bool(f.get("diff")))
        if self.charge and status == "done":
            try:
                self.charge(st.run(rid))
            except Exception as e:  # noqa: BLE001
                st.append_output(rid, "— 记录点数失败：%s\n" % e)
        cb = self.after.pop(rid, None)
        if cb and (status == "done" or getattr(cb, "always", False)):  # an "always" follow-up also hears about failures
            try:
                cb(st.run(rid))
            except Exception as e:  # noqa: BLE001 - a follow-up must not break the run record
                st.append_output(rid, "— 后续任务启动失败：%s\n" % e)

    def invoke(self, rid, project, ticket, agent, conf, mode, prompt, workdir, model="", tag="", resume="", fresh="") -> tuple[int, str]:
        """One agent process for run `rid`: its output streams into the run log; returns (exit code, final answer).
        `mode` sets the permissions (fix/edit may write, the rest only read); `tag` names the prompt files of a sub-step.
        `resume` continues that agent session with `prompt` (only what is new); if it cannot be continued, the step
        starts over in a new session with `fresh`, the full prompt. The session id and a time breakdown are kept
        next to the prompt (session<tag>.txt, timing<tag>.json)."""
        rdir = self.data_dir / "runs" / str(rid)
        rdir.mkdir(parents=True, exist_ok=True)
        if resume and "cmd" in (conf.get(agent) or {}) and "{resume}" not in conf[agent]["cmd"]:  # a custom command that cannot continue
            prompt, resume = fresh or prompt, ""
        code, result, parser, timing = self._spawn(rid, project, ticket, agent, conf, mode, prompt, workdir, model, tag, resume)
        if resume and code != 0 and not (result or "").strip() and fresh and not timing.get("busy") and not self.store.run(rid)["status"] == "cancelled":
            self.store.append_output(rid, "— 接着上一步的会话没有成功，改为新开一个会话\n")
            code, result, parser, timing = self._spawn(rid, project, ticket, agent, conf, mode, fresh, workdir, model, tag, "")
        for wait in BUSY_WAITS:  # the model service was busy: wait, then pick the same session up where it stopped
            if code == 0 or not timing.get("busy") or self.store.run(rid)["status"] == "cancelled":
                break
            self.store.append_output(rid, "— %s\n— 模型服务繁忙，%d 秒后重试\n" % (timing_text(timing), wait))
            if not self._pause(rid, wait):
                break
            sid = parser.session or resume
            again = (BUSY_AGAIN, sid, fresh or prompt) if sid else (fresh or prompt, "", "")
            code, result, parser, timing = self._spawn(rid, project, ticket, agent, conf, mode, again[0], workdir, model, tag, again[1])
            if again[1] and code != 0 and not (result or "").strip() and not timing.get("busy"):
                self.store.append_output(rid, "— 接着上一步的会话没有成功，改为新开一个会话\n")
                code, result, parser, timing = self._spawn(rid, project, ticket, agent, conf, mode, again[2], workdir, model, tag, "")
        if parser.session:
            (rdir / ("session%s.txt" % tag)).write_text(parser.session, encoding="utf-8")
        (rdir / ("timing%s.json" % tag)).write_text(json.dumps(timing, ensure_ascii=False), encoding="utf-8")
        self.store.append_output(rid, "— %s\n" % timing_text(timing))
        return code, result

    def _pause(self, rid, seconds) -> bool:
        """Sleep, but give up early (False) if the run is cancelled meanwhile."""
        end = time.time() + seconds
        while time.time() < end:
            if self.store.run(rid)["status"] == "cancelled":
                return False
            time.sleep(min(2.0, max(0.0, end - time.time())))
        return True

    def _spawn(self, rid, project, ticket, agent, conf, mode, prompt, workdir, model, tag, resume):
        st = self.store
        rdir = self.data_dir / "runs" / str(rid)
        pf, lm = rdir / ("prompt%s.md" % tag), rdir / ("last-message%s.md" % tag)
        pf.write_text(prompt, encoding="utf-8")
        if lm.exists():
            lm.unlink()
        parser, clock = StreamParser(agent), Timing(resume)
        try:
            cmd = command(conf, agent, mode, prompt, pf, workdir, lm, str(Path(project["root"]) / ".tmh" / "tool" / "tmh.py"), model, resume)
        except ValueError as e:
            st.append_output(rid, "— %s\n" % e)
            return 2, str(e), parser, clock.done()
        stdin_prompt = agent == "claude" and "cmd" not in conf[agent]
        timeout = int(conf[agent].get("timeout") or 1800)
        env = dict(os.environ, TMH_RUN=str(rid), TMH_TICKET=ticket["key"] if ticket else "")
        tool = Path(project["root"]) / ".tmh" / "tool"
        if tool.is_dir():  # let the agent call `python3 -m tmh` / imports work inside a worktree too
            env["PYTHONPATH"] = str(tool) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            p = subprocess.Popen(cmd, cwd=str(workdir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.PIPE if stdin_prompt else subprocess.DEVNULL, env=env, text=True, encoding="utf-8", errors="replace", bufsize=1)
        except OSError as e:
            msg = "启动 %s 失败：%s。确认已安装并能在终端里运行 %s。" % (agent, e, cmd[0])
            st.append_output(rid, "— %s\n" % msg)
            return 127, msg, parser, clock.done()
        if stdin_prompt:
            try:
                p.stdin.write(prompt)
                p.stdin.close()
            except OSError:
                pass
        with self.lock:
            self.procs[rid] = p
        killer = threading.Timer(timeout, p.kill)
        killer.start()
        buf, last = [], time.time()
        try:
            for line in p.stdout:
                clock.feed(line)
                s = parser.feed(line)
                if s:
                    buf.append(s)
                if buf and (time.time() - last > 0.4 or len(buf) > 50):
                    st.append_output(rid, "".join(buf))
                    buf, last = [], time.time()
            p.wait()
        finally:
            killer.cancel()
            p.stdout.close()
            if buf:
                st.append_output(rid, "".join(buf))
            with self.lock:
                self.procs.pop(rid, None)
        result = parser.final()
        if lm.exists() and lm.read_text(encoding="utf-8").strip():
            result = lm.read_text(encoding="utf-8")
        return p.returncode, result, parser, clock.done()

    def _finish_event(self, ticket, rid, agent, mode, status, result, has_diff=False):
        if not ticket or mode == "ask":
            return
        word = {"done": "完成", "failed": "失败", "cancelled": "已取消"}[status]
        extra = "，产生了代码改动，等待审阅" if has_diff else ("，没有产生代码改动" if mode == "fix" and status == "done" else "")
        self.store.event(ticket["id"], agent, "run-" + status, "%s%s%s" % (dict(RUN_MODES)[mode], word, extra),
                         {"run": rid, "agent": agent, "mode": mode, "summary": (result or "")[:400]})
        self.store.touch(ticket["id"])

    def cancel(self, rid: int, author: str) -> dict:
        r = self.store.run(rid)
        if not r or r["status"] not in ("queued", "running"):
            raise ValueError("这个运行已经结束")
        self.store.update_run(rid, status="cancelled", ended=now())
        with self.lock:
            p = self.procs.get(rid)
        if p:
            p.terminate()
        return self.store.run(rid)

    def decide(self, rid: int, decision: str, author: str) -> dict:
        """accept: commit the worktree on its branch (ready to merge) and drop the worktree; discard: drop both."""
        r = self.store.run(rid)
        if not r or r["mode"] != "fix":
            raise ValueError("只有修改代码的运行需要审阅")
        if r["status"] in ("queued", "running"):
            raise ValueError("还在运行，结束后再审阅")
        if r["decision"]:
            raise ValueError("已经%s过了" % ("采纳" if r["decision"].startswith("accept") else "放弃"))
        wt = Path(r["workdir"])
        p = self.store.project(r["project_id"])
        root = Path(p["root"])
        t = self.store.ticket(r["ticket_id"]) if r["ticket_id"] else None
        branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip() if wt.is_dir() else ""
        if decision == "accept":
            if not r["diff"]:
                raise ValueError("没有改动可以采纳")
            git(wt, "add", "-A")
            auto = author == "自动流转"
            msg = "%s %s\n\n由 %s 修改，%s（tmh 运行 #%d）" % (t["key"] if t else p["key"], t["title"] if t else "", r["agent"],
                                                       "自动提交，待人工合并验收" if auto else author + " 审阅采纳", rid)
            msg += "\n\n" + trailers(r, t, None if auto else author)
            git(wt, "-c", "user.name=tmh", "-c", "user.email=tmh@localhost", "commit", "-q", "-m", msg)
            sha = git(wt, "rev-parse", "--short", "HEAD").strip()
            git(root, "worktree", "remove", "--force", str(wt))
            self.store.update_run(rid, decision="accepted:%s@%s" % (branch, sha))
            if t:
                self.store.event(t["id"], author, "adopt", ("自动提交了代码改动：分支 %s（提交 %s），主干没动，合并后验收" if auto else
                                                             "采纳了代码改动：分支 %s（提交 %s），合并到主干后即可验证") % (branch, sha),
                                 {"run": rid, "branch": branch, "commit": sha})
                if t["status"] in ("doing", "confirm", "analyzing", "new"):
                    self.store.update_ticket(t["id"], author, status="verify")
        elif decision == "discard":
            if wt.is_dir():
                git(root, "worktree", "remove", "--force", str(wt), check=False)
            if branch.startswith("tmh/"):
                git(root, "branch", "-D", branch, check=False)
            self.store.update_run(rid, decision="discarded")
            if t:
                self.store.event(t["id"], author, "discard", "放弃了这次代码改动", {"run": rid})
        else:
            raise ValueError("decision 只能是 accept 或 discard")
        return self.store.run(rid)

    def recover(self) -> None:
        """Runs left 'running' by a previous server process can no longer finish."""
        for r in self.store.q("SELECT id FROM runs WHERE status IN ('queued','running')"):
            self.store.update_run(r["id"], status="failed", ended=now(), result="平台重启时这个运行被中断")
