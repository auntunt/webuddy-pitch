"""Was it fixed correctly: the change goes through gates of rising cost, each ending PASS, FAIL or UNKNOWN.

"The build passed" is not "it was fixed". Agents that cannot make a test pass delete the test, add a skip, or
end a command with `|| true`; a fix that compiles may just cut the feature off. So a change is looked at in
order, cheapest first, and every gate writes down what it found:

  changed   there is a real change, not only whitespace
  parse     the changed files still parse (Python, JSON, XML here; other languages are left to the build)
  weaken    no test was weakened: no test file deleted, no assertion removed, no skip / @Ignore / `|| true`
            added, no build flag that skips tests, no coverage threshold lowered
  scope     only the files the plan listed were changed
  path      the product code changed lies on the ticket's business flows
  baseline  the untouched code builds and passes its tests on this machine (otherwise a red build says nothing
            about the change, and green is not proof either)
  build     the build passed
  test      the tests passed
  match     a model compared the change with the acceptance criteria: equivalent / partial / different
            direction / wrong. Always an inference【推断】, never more than that.

UNKNOWN is not PASS: a package with a FAIL or an UNKNOWN is not complete, and an upstream PR is not submitted
while any gate is FAIL. A person can let a gate through with a written reason (the reason goes into the
evidence package next to their name), except a failed build or failed tests, which only a new change can fix.

After Google's six gates for agent-made changes (self-report, whitespace, parse, necessity, build, test),
QQ 音乐's gate files and the PASS / FAIL / UNKNOWN convention, and GitHub's list of CI cheats.
"""
from __future__ import annotations

import ast
import json
import re
import xml.dom.minidom

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
NAMES = {"changed": "有实际改动", "parse": "改后的文件能解析", "weaken": "没有削弱测试", "scope": "没超出方案",
         "path": "落在本单的业务流上", "baseline": "原代码在这台机器上能构建", "build": "构建通过", "test": "测试通过",
         "match": "对照验收标准，改对了【推断】"}
ORDER = list(NAMES)
NOT_WAIVABLE = {"build", "test"}  # a red build or red tests need a new change, not a reason
MATCH = {"equivalent": (PASS, "等价"), "partial": (UNKNOWN, "只改对了一部分"), "different": (FAIL, "方向不同"), "wrong": (FAIL, "改错了")}

TEST_FILE = re.compile(r"(^|/)(src/test|tests?|__tests__|spec)/|(Tests?|Spec|IT)\.(java|cs|kt)$|(_test\.go|\.spec\.[jt]sx?|\.test\.[jt]sx?)$|(^|/)test_[^/]+\.py$")
ASSERT = re.compile(r"\b(assert\w*|expect\s*\(|should\.|verify\s*\(|Assert\.|self\.assert\w+|fail\s*\()", re.I)
SKIP = re.compile(r"@Ignore\b|@Disabled\b|\b(it|describe|test)\.skip\s*\(|\bxit\s*\(|\bxdescribe\s*\(|pytest\.mark\.skip|unittest\.skip|"
                  r"\[Ignore\]|\[Fact\s*\(\s*Skip\s*=|t\.Skip\s*\(|@pytest\.mark\.xfail")
CHEAT = re.compile(r"\|\|\s*true\b|-DskipTests\b|-Dmaven\.test\.skip=true|skipTests\s*>\s*true|\bcontinue-on-error\s*:\s*true|"
                   r"--passWithNoTests\b")
COVERAGE = re.compile(r"(coverage|threshold|minimum|branches|lines|statements|functions)\D{0,40}?(\d+(?:\.\d+)?)", re.I)


def gate(gid: str, state: str, why: str = "", **detail) -> dict:
    g = {"id": gid, "name": NAMES[gid], "state": state, "why": why}
    if detail:
        g["detail"] = detail
    return g


def split_diff(diff: str) -> dict:
    """path -> {"added": [...], "removed": [...], "deleted": bool, "new": bool} from a unified git diff."""
    out, cur = {}, None
    for line in (diff or "").splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            cur = out.setdefault(m.group(2), {"added": [], "removed": [], "deleted": False, "new": False})
            continue
        if cur is None:
            continue
        if line.startswith("deleted file mode"):
            cur["deleted"] = True
        elif line.startswith("new file mode"):
            cur["new"] = True
        elif line.startswith("+") and not line.startswith("+++"):
            cur["added"].append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed"].append(line[1:])
    return out


def _bare(lines: list) -> list:
    return sorted(re.sub(r"\s+", "", x) for x in lines if x.strip())


# ---------------------------------------------------------------- the cheap gates (the diff alone)

def changed(files: dict) -> dict:
    if not files:
        return gate("changed", FAIL, "没有改出代码")
    real = [p for p, f in files.items() if f["deleted"] or f["new"] or _bare(f["added"]) != _bare(f["removed"])]
    if not real:
        return gate("changed", FAIL, "只改了空白和换行，没有实际改动")
    return gate("changed", PASS, "%d 个文件有实际改动" % len(real))


def weaken(files: dict) -> dict:
    """Hits that weaken the tests, each as "file: what"."""
    hits = []
    for p, f in files.items():
        is_test = bool(TEST_FILE.search(p))
        if is_test and f["deleted"]:
            hits.append("%s：删除了测试文件" % p)
            continue
        if is_test:
            gone = len([x for x in f["removed"] if ASSERT.search(x)]) - len([x for x in f["added"] if ASSERT.search(x)])
            if gone > 0:
                hits.append("%s：少了 %d 处断言" % (p, gone))
        for x in f["added"]:
            if SKIP.search(x) and not any(SKIP.search(y) for y in f["removed"]):
                hits.append("%s：加了跳过测试（%s）" % (p, x.strip()[:60]))
            elif CHEAT.search(x) and not any(CHEAT.search(y) for y in f["removed"]):
                hits.append("%s：加了让失败也算通过的写法（%s）" % (p, x.strip()[:60]))
        if re.search(r"(jacoco|coverage|codecov|jest\.config|\.nycrc|pytest\.ini|setup\.cfg|pom\.xml|build\.gradle)", p, re.I):
            old = {m.group(1).lower(): float(m.group(2)) for x in f["removed"] for m in [COVERAGE.search(x)] if m}
            for x in f["added"]:
                m = COVERAGE.search(x)
                if m and m.group(1).lower() in old and float(m.group(2)) < old[m.group(1).lower()]:
                    hits.append("%s：覆盖率门槛从 %g 降到 %s" % (p, old[m.group(1).lower()], m.group(2)))
    if hits:
        return gate("weaken", FAIL, "有削弱测试的改动", hits=hits[:12])
    return gate("weaken", PASS, "没有删测试、删断言、加跳过或 `|| true`")


def parse(files: dict, read, build_ok: bool | None) -> dict:
    """Parse the changed files that have a parser here; the rest is left to the build."""
    checked, bad = [], []
    for p, f in files.items():
        if f["deleted"] or not p.endswith((".py", ".json", ".xml")):
            continue
        text = read(p) if read else None
        if text is None:
            continue
        checked.append(p)
        try:
            if p.endswith(".py"):
                ast.parse(text)
            elif p.endswith(".json"):
                json.loads(text)
            else:
                xml.dom.minidom.parseString(text.encode("utf-8"))
        except Exception as e:  # noqa: BLE001 - any parser error is the finding
            bad.append("%s：%s" % (p, str(e).splitlines()[0][:120]))
    if bad:
        return gate("parse", FAIL, "改后的文件解析不了", errors=bad)
    if checked:
        return gate("parse", PASS, "解析了 %d 个文件" % len(checked))
    if build_ok:
        return gate("parse", PASS, "这些文件这里没有解析器，构建通过说明能解析")
    return gate("parse", UNKNOWN, "改的文件这里没有解析器，也没有构建结果")


def scope(beyond: list, planned: bool) -> dict:
    if not planned:
        return gate("scope", UNKNOWN, "方案没有列出要改的文件，判断不了是否超出")
    if beyond:
        return gate("scope", FAIL, "改了方案没列的 %s" % "、".join(beyond[:5]), files=beyond)
    return gate("scope", PASS, "只改了方案列出的文件")


def path(res: dict | None) -> dict:
    if not res:
        return gate("path", UNKNOWN, "没有入口路径检查结果")
    if res.get("ok"):
        return gate("path", PASS, "改动的代码都在本单关联的业务流上")
    if res.get("off"):
        return gate("path", FAIL, res.get("why") or "有代码改动不在关联业务流上")
    return gate("path", UNKNOWN, res.get("why") or "判断不了改动是否落在业务流上")


# ---------------------------------------------------------------- the dear gates (from the fix loop's verify.json)

def checks(v: dict) -> list:
    """baseline, build and test from what the fix loop ran."""
    cmds = v.get("commands") or []
    skip = str(v.get("skip") or "")
    if skip.startswith(("原代码", "测试机没准备好")):
        base = gate("baseline", UNKNOWN, skip[:200])
    elif cmds:
        base = gate("baseline", PASS, "原代码先构建测试过一遍，能跑通")
    else:
        base = gate("baseline", UNKNOWN, "没有跑构建测试" + ("：" + skip[:160] if skip else ""))
    out = [base]
    for kind, gid in (("build", "build"), ("test", "test")):
        mine = [c for c in cmds if c.get("kind") in (kind, "check")] if kind == "build" else [c for c in cmds if c.get("kind") == "test"]
        if kind == "build" and not mine and any(c.get("kind") == "test" for c in cmds):
            mine = [c for c in cmds if c.get("kind") == "test"]  # a test run builds first
        bad = [c for c in mine if c.get("exit_code") != 0]
        if bad:
            out.append(gate(gid, FAIL, "`%s` 失败（退出码 %s）" % (bad[0].get("command", ""), bad[0].get("exit_code"))))
        elif mine:
            out.append(gate(gid, PASS, "`%s` 通过" % mine[-1].get("command", "")))
        else:
            out.append(gate(gid, UNKNOWN, "没有跑" + ("测试" if kind == "test" else "构建")))
    return out


def match(diag: dict | None) -> dict:
    d = diag or {}
    m = str(d.get("match") or "").lower()
    if m in MATCH:
        st, word = MATCH[m]
        return gate("match", st, "%s【推断】%s" % (word, ("：" + str(d.get("match_why"))[:200]) if d.get("match_why") else ""), judged=m)
    return gate("match", UNKNOWN, "没有对照验收标准的判定")


# ---------------------------------------------------------------- all of it

def evaluate(diff: str, v: dict, path_res: dict | None, planned: bool, read=None) -> list:
    """Every gate for one change, in order of cost."""
    files = split_diff(diff)
    cs = checks(v or {})
    build_ok = next((g["state"] == PASS for g in cs if g["id"] == "build" and g["state"] != UNKNOWN), None)
    return [changed(files), parse(files, read, build_ok), weaken(files), scope(list((v or {}).get("beyond_plan") or []), planned),
            path(path_res)] + cs + [match((v or {}).get("diagnosis"))]


def waived(gates: list, waivers: dict) -> list:
    """Gates with a person's written reason applied (a failed build or test cannot be waived)."""
    out = []
    for g in gates:
        w = (waivers or {}).get(g["id"])
        if g["state"] != PASS and w and not (g["id"] in NOT_WAIVABLE and g["state"] == FAIL):
            g = dict(g, state=PASS, waived={"by": w.get("by", ""), "reason": w.get("reason", ""), "was": g["state"]})
        out.append(g)
    return out


def overall(gates: list) -> str:
    states = {g["state"] for g in gates}
    return FAIL if FAIL in states else UNKNOWN if UNKNOWN in states else PASS


def summary(gates: list) -> str:
    bad = [g for g in gates if g["state"] != PASS]
    if not bad:
        return "%d 道验证门全部通过" % len(gates)
    return "；".join("%s %s：%s" % ("没过" if g["state"] == FAIL else "未知", g["name"], g["why"]) for g in bad)
