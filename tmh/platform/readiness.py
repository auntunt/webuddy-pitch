"""上线体检: before a client's first ticket, what on this machine would let them down, each with the next step.

Every check looks at the real thing (the agent command on the PATH, the last runs, the project's directory, the
signing key, the disk), never at a setting that only says it should work. "bad" stops a pilot, "warn" makes it
weaker, "ok" is fine; the page lists bad first.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import shlex
import shutil
from datetime import datetime, timedelta
from pathlib import Path

STUCK_H = 2
INTERRUPTED = "平台重启时这个运行被中断"  # what Runner.recover writes  # a run still "running" this long after it started is stuck, not slow


def _item(key: str, label: str, state: str, detail: str, fix: str = "", link: str = "") -> dict:
    return {"key": key, "label": label, "state": state, "detail": detail, "fix": fix, "link": link}


SIGNIN = (
    (re.compile(r"确认是你本人|新电脑|new device|verify (?:it'?s|that it is) you|devices?\b.*(?:confirm|approve)", re.I),
     "这台机器还没确认是账号本人", "打开报错里给的设备确认页（%s），先核对这是你给这个智能体配的服务，再在这台机器上点「是我」，然后重跑失败的运行"),
    (re.compile(r"not logged in|please (?:log|sign) ?in|login required|未登录|请先登录|/login|unauthori[sz]ed|invalid api key|\b401\b", re.I),
     "没登录或登录过期了", "在这台机器上用运行平台的同一个账号执行一次 claude 或 codex 并登录，再重跑失败的运行"),
    (re.compile(r"usage limit|rate limit|quota|额度|exceeded your|insufficient_quota|\b429\b", re.I),
     "额度用完或被限流了", "等额度恢复或换一个账号，再重跑失败的运行"),
)


def signin(text: str) -> tuple:
    """(what is wrong, what a person does) when an agent's output says it cannot sign in or has no quota left."""
    for rx, what, fix in SIGNIN:
        if rx.search(text or ""):
            if "%s" in fix:  # the page to confirm on is whatever the agent's own service named, not one we guess
                m = re.search(r"https?://[^\s\"'<>）)，。]+", text)
                fix = fix % (m.group(0) if m else "地址见运行日志")
            return what, fix
    return ()


def _agents(P) -> list:
    from .agents import available
    ags = available(P.data_dir)
    ok = [a for a in ags if a["available"]]
    if not ok:
        return [_item("agent", "智能体", "bad", "这台机器上找不到 %s 命令" % "、".join(a["name"] for a in ags),
                      "装好 Claude Code 或 Codex 并登录一次，再刷新这页", "#/settings")]
    out = [_item("agent", "智能体", "ok", "命令都在：" + "、".join(a["title"] for a in ok))]
    for a in ok:  # a command on the PATH is not an agent that runs: its own latest run says whether it can sign in
        last = P.store.one("SELECT id, status, substr(output, -1200) AS output, substr(result, 1, 600) AS result FROM runs "
                           "WHERE agent=? AND status IN ('done','failed') AND result != ? ORDER BY id DESC LIMIT 1", (a["name"], INTERRUPTED))
        why = signin(" ".join((last.get("output") or "", last.get("result") or ""))) if last and last["status"] == "failed" else ""
        if why:
            out.append(_item("agent:" + a["name"], a["title"], "bad", "%s 跑不起来（运行 #%d）：%s" % (a["title"], last["id"], why[0]), why[1]))
    # a run the platform cut off by restarting says nothing about the agent; only the end of the log is needed
    runs = P.store.q("SELECT status, substr(output, -400) AS output, substr(result, 1, 400) AS result, ended FROM runs "
                     "WHERE status IN ('done','failed') AND result != ? ORDER BY id DESC LIMIT 5", (INTERRUPTED,))
    if len(runs) >= 3 and all(r["status"] == "failed" for r in runs[:3]):  # the latest three in a row: it is not one bad ticket
        tail = ((runs[0].get("output") or runs[0].get("result") or "").strip().splitlines() or [""])[-1][:160]
        out.append(_item("runs", "最近的运行", "bad", "最近 %d 次连续失败%s" % (sum(1 for _ in itertools.takewhile(lambda r: r["status"] == "failed", runs)), "，最后一次：" + tail if tail else ""),
                         "多半是智能体没登录或额度用完：在这台机器上手动跑一次 claude 或 codex 看提示"))
    elif runs:
        f = sum(1 for r in runs if r["status"] == "failed")
        out.append(_item("runs", "最近的运行", "warn" if f >= 2 else "ok", "最近 %d 次里 %d 次失败" % (len(runs), f)))
    else:
        out.append(_item("runs", "最近的运行", "warn", "还没有跑过", "随便挑一张工单点一次“分析”，确认智能体真的能跑通"))
    cut = (datetime.now() - timedelta(hours=STUCK_H)).strftime("%Y-%m-%d %H:%M:%S")
    stuck = P.store.q("SELECT id FROM runs WHERE status='running' AND started!='' AND started<?", (cut,))
    if stuck:
        out.append(_item("stuck", "卡住的运行", "warn", "%d 个运行开始超过 %d 小时还没结束" % (len(stuck), STUCK_H), "到工单里停掉它们再重跑"))
    return out


def _projects(P) -> list:
    ps = P.store.projects()
    if not ps:
        return [_item("project", "项目", "bad", "还没有接入项目", "在“设置 → 项目”里添加客户代码所在的目录", "#/settings")]
    out = []
    for p in ps:
        root = Path(p["root"])
        if not root.is_dir():
            out.append(_item("project:" + p["key"], "项目 %s" % p["key"], "bad", "目录 %s 不存在" % root, "检查目录是否挂载，或在设置里改成正确的位置", "#/settings"))
            continue
        if not (root / ".git").exists():
            ts = P.store.tickets(project_id=p["id"], limit=2000)
            if ts and all((t.get("links") or {}).get("upstream") for t in ts):
                out.append(_item("project:" + p["key"], "项目 %s" % p["key"], "ok", "跟踪上游 PR 的项目，代码在上游仓库，不需要本地 git"))
                continue
            out.append(_item("project:" + p["key"], "项目 %s" % p["key"], "warn", "%s 不是 git 仓库" % root, "改动和证据要靠 git 提交追溯：在目录里 git init 并提交一次"))
            continue
        try:
            kb = P.kb.kb_overview(p) or {}
        except Exception:  # noqa: BLE001 - a broken knowledge base is itself the finding
            kb = {}
        if not kb.get("built"):
            out.append(_item("project:" + p["key"], "项目 %s" % p["key"], "warn", "知识库还没建，分析只能靠临时读代码，又慢又容易漏",
                             "到 工程 › 知识库 按引导建知识库", "#/kb"))
        else:
            out.append(_item("project:" + p["key"], "项目 %s" % p["key"], "ok", "目录、git、知识库都在"))
    return out


def _flow(P) -> list:
    conf = P.flow.autoflow()
    if not conf.get("on"):
        return [_item("auto", "自动处理", "warn", "关着：新工单要人手点才开始分析", "需要的话把数据目录里 autoflow.json 的 on 改成 true")]
    return [_item("auto", "自动处理", "ok", "开着：新工单会自动分析%s" % ("、出方案并改代码" if conf.get("fix") else ""))]


def _evidence(P) -> list:
    from .. import sign
    from .signoff import edir
    fp = sign.ready(edir(P.data_dir))
    if fp:
        return [_item("sign", "证据包签名", "ok", "导出带签名，指纹 %s" % fp)]
    return [_item("sign", "证据包签名", "warn", "这台机器签不了名，导出的证据包证明不了是谁导出的",
                  "装 Python 的 cryptography 包，或 OpenSSH 8.2 以上的 ssh-keygen，然后重启平台")]


def _access(P) -> list:
    from .login import load_users
    users = load_users(P.data_dir)
    if users:
        return [_item("login", "登录", "ok", "已开账号登录，%d 个账号" % len(users))]
    return [_item("login", "登录", "warn", "没有账号：只能本机或带令牌访问，签收记录里看不出是谁操作的",
                  "用 tmh user add 给每个人建账号")]


def _disk(P) -> list:
    try:
        free = shutil.disk_usage(P.data_dir).free / 2 ** 30
    except OSError:
        return []
    st = "bad" if free < 1 else "warn" if free < 5 else "ok"
    return [_item("disk", "磁盘", st, "数据目录所在磁盘还剩 %.1f GB" % free, "" if st == "ok" else "清理旧的工作树（worktrees/）或换更大的盘：写不进数据库时所有操作都会失败")]


def _build(P) -> list:
    """Will a change be built and tested before a person sees it? The test machine's last check if one is set,
    otherwise whether this machine can run the project's own build and test commands."""
    from .fixloop import settings as fl
    from .testbox import settings as tb
    v = fl(P.data_dir).get("check")
    if v in ("none", False):
        return [_item("build", "构建和测试", "warn", "设置为不跑构建测试：改动不经过编译就交给人验收", "去掉 autoflow.json 里的 \"check\": \"none\"")]
    box = tb(P.data_dir)
    if box:
        try:
            last = json.loads((Path(P.data_dir) / "testbox-check.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = None
        where = "测试机 %s" % box.get("host", "")
        if not last:
            return [_item("build", "构建和测试", "warn", "%s 还没体检过" % where, "在下面“测试机”里点“体检”", "#/settings")]
        if not last.get("ok", True) or last.get("error"):
            return [_item("build", "构建和测试", "bad", "%s 上次体检连不上：%s" % (where, str(last.get("error", ""))[:160]),
                          "检查 SSH 密钥和网络，再点“体检”", "#/settings")]
        if last.get("missing"):
            return [_item("build", "构建和测试", "warn", "%s 缺 %s" % (where, "、".join(last["missing"])), "在下面“测试机”里装上缺的工具", "#/settings")]
        return [_item("build", "构建和测试", "ok", "改动先在%s编译和测试（%s 体检通过）" % (where, str(last.get("at", ""))[:16]))]
    if isinstance(v, str) and v.strip():
        return [_item("build", "构建和测试", "ok", "在本机运行设置的检查命令：%s" % v.strip()[:80])]
    from .. import config as cfgmod
    from ..verify import detect_commands
    out = []
    for p in P.store.projects():
        root = Path(p["root"])
        if not root.is_dir():
            continue
        try:
            given = cfgmod.load(root).get("commands") or {}
        except Exception:  # noqa: BLE001
            given = {}
        found = {k: given.get(k) or detect_commands(root).get(k) for k in ("build", "test")}
        cmds = [c for c in found.values() if c]
        missing = sorted({shlex.split(c)[0] for c in cmds if not shlex.split(c)[0].startswith("./") and not shutil.which(shlex.split(c)[0])})
        label = "构建和测试 %s" % p["key"]
        if not cmds:
            out.append(_item("build:" + p["key"], label, "warn", "认不出这个项目怎么构建和测试，改动不经过编译就交给人验收",
                             "在项目的 .tmh 配置里写上 build 和 test 命令，或设置测试机"))
        elif missing:
            out.append(_item("build:" + p["key"], label, "warn", "本机缺 %s，构建和测试跑不了" % "、".join(missing), "在这台机器上装好，或设置测试机", "#/settings"))
        else:
            out.append(_item("build:" + p["key"], label, "ok", "在本机构建和测试：%s" % "；".join(cmds)[:120]))
    return out


def _links(P) -> list:
    """Links that leave the platform (to a chat, to a client's sign page) need an address people outside can open."""
    if os.environ.get("TMH_PUBLIC_URL") or getattr(P, "public_url", ""):
        return [_item("url", "对外地址", "ok", "发给客户的链接用 %s" % (os.environ.get("TMH_PUBLIC_URL") or P.public_url))]
    return [_item("url", "对外地址", "warn", "还不知道平台的对外地址：发进群里的预览和签收链接可能是内网地址",
                  "启动前设置环境变量 TMH_PUBLIC_URL（例如 https://webuddy.example.com），或先从对外地址登录一次")]


def _git(P) -> list:
    import subprocess
    try:
        v = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return [_item("git", "git", "bad", "这台机器上没有 git", "装上 git：改动、合并、版本都靠它")]
    m = re.search(r"(\d+)\.(\d+)", v)
    if m and (int(m.group(1)), int(m.group(2))) < (2, 38):
        return [_item("git", "git", "warn", "git 版本 %s.%s 较旧：合并前没法先在旁边试合，只能直接在项目目录里合，冲突时再撤回" % m.groups(),
                      "升级到 git 2.38 或更新")]
    return [_item("git", "git", "ok", v.strip())]


CHECKS = (_agents, _projects, _flow, _evidence, _access, _disk, _build, _links, _git)


def check(P) -> dict:
    items = []
    for fn in CHECKS:
        try:
            items += fn(P)
        except Exception as e:  # noqa: BLE001 - one broken check must not hide the others
            items.append(_item(fn.__name__.strip("_"), fn.__name__.strip("_"), "warn", "检查没做完：%s" % e))
    order = {"bad": 0, "warn": 1, "ok": 2}
    items.sort(key=lambda x: order[x["state"]])
    n = {s: sum(1 for x in items if x["state"] == s) for s in order}
    return {"items": items, "counts": n,
            "summary": "有 %d 项会挡住试点" % n["bad"] if n["bad"] else "可以开始试点%s" % ("，另有 %d 项建议改进" % n["warn"] if n["warn"] else "")}
