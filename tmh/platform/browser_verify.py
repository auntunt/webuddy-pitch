"""Real-app verification ("Prove It Works", after pstack): a change is checked by driving the running application,
not by reading it. For a project with a verification host in <data>/verify-hosts.json, the candidate (a commit, or a
base commit plus a diff) is sent to that host, started there against its own isolated backend, and a Playwright
script written for the ticket's criteria is run in a real browser: one test per criterion, screenshots at each step.

Results per criterion: pass (the test ran and its assertions held), fail (an assertion failed: reproduced on this
version), unverified (anything else: no test, skipped, a step that could not be performed, a timeout, a missing
screenshot). Only `fail` is a reproduced defect; only all-`pass` with screenshots proves the change."""
from __future__ import annotations

import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
from pathlib import Path

CONF = "verify-hosts.json"
TIMEOUT = 1500

HELPERS = r"""import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const md5 = (s) => crypto.createHash('md5').update(s, 'utf8').digest('hex');

function secret() {
  const m = fs.readFileSync(process.env.TMH_JB_YML, 'utf8').match(/signatureSecret:\s*(\S+)/);
  return m ? m[1] : '';
}

// JeecgBoot keeps each captcha in redis under md5(code + checkKey + secret): read it back the same way.
export function captchaFor(checkKey) {
  const s = secret();
  const keys = execFileSync('redis-cli', ['--scan'], { encoding: 'utf8' }).split('\n').filter((k) => /^[0-9a-f]{32}$/.test(k));
  for (const k of keys) {
    const v = execFileSync('redis-cli', ['--raw', 'GET', k], { encoding: 'utf8' }).trim().replace(/^"|"$/g, '');
    if (v.length === 4 && md5(v + checkKey + s) === k) return v;
  }
  return '';
}

export async function login(page, user = 'admin', pass = '123456') {
  const base = process.env.TMH_BASE;
  let checkKey = '';
  page.on('request', (r) => { const m = r.url().match(/randomImage\/([^/?]+)/); if (m) checkKey = m[1]; });
  await page.goto(base + 'user/login');
  await page.locator('form input').first().waitFor({ timeout: 240000 });
  for (let i = 0; i < 60 && !checkKey; i++) await page.waitForTimeout(500);
  await page.waitForTimeout(2000);
  const code = captchaFor(checkKey);
  if (!code) throw new Error('TMH_SETUP captcha not found');
  const inputs = page.locator('form input:visible');
  await inputs.nth(0).fill(user);
  await inputs.nth(1).fill(pass);
  await inputs.nth(2).fill(code);
  await page.getByRole('button', { name: /登\s*录/ }).first().click();
  await page.waitForResponse((r) => /\/sys\/login/.test(r.url()), { timeout: 60000 });
  await page.waitForTimeout(3000);
}

export async function shot(page, testInfo, name) {
  const file = path.join(process.env.TMH_OUT, 'shots', testInfo.title.split(' ')[0] + '-' + name.replace(/[^\w-]/g, '_') + '.png');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file });
  await testInfo.attach(name, { path: file, contentType: 'image/png' });
}
"""

CONFIG = """export default { testDir: '.', testMatch: 'tmh-verify.spec.mjs', timeout: 240000, workers: 1, retries: 0,
  reporter: [['json', { outputFile: process.env.TMH_OUT + '/report.json' }]],
  use: { viewport: { width: 1440, height: 900 } }, outputDir: process.env.TMH_OUT + '/artifacts' };
"""

DRIVER = r"""set -u
J=$1; BASE=$2; PORT=$3; PFX=$4; APP=$5; API=$6; YML=$7
export PATH=~/.local/bin:$PATH
D=~/pv/verifier/jobs/$J; OUT=$D/out; mkdir -p $OUT; cd $D
say() { echo "{\"setup\": \"$1\"}" > $OUT/report.json; }
finish() { [ -n "${VP:-}" ] && kill -- -$VP 2>/dev/null; git -C ~/pv/base worktree remove --force $D/src >/dev/null 2>&1; tar cz -C $OUT .; rm -rf $D; exit 0; }
[ -f in.bundle ] && git -C ~/pv/base fetch -q in.bundle "+HEAD:refs/tmh/$J" >&2
git -C ~/pv/base worktree add -f --detach $D/src $BASE >&2 || { say "base commit not on host"; finish; }
cd $D/src
if [ -s $D/patch.diff ]; then git apply --whitespace=nowarn $D/patch.diff >&2 || { say "patch does not apply"; finish; }; fi
cd $APP
if cmp -s package.json ~/pv/base/$APP/package.json && cmp -s pnpm-lock.yaml ~/pv/base/$APP/pnpm-lock.yaml; then
  ln -s ~/pv/base/$APP/node_modules node_modules
else
  pnpm install --prefer-offline >&2 || { say "dependency install failed"; finish; }
fi
VITE_PUBLIC_PATH=$PFX/ VITE_GLOB_API_URL=$PFX/jeecgboot VITE_USE_MOCK=false VITE_PROXY="[[\"$PFX/jeecgboot\",\"$API\"]]" \
  setsid pnpm exec vite --host 127.0.0.1 --port $PORT --strictPort > $OUT/app.log 2>&1 < /dev/null &
VP=$!
for i in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT$PFX/)" = 200 ] && break; sleep 2; done
[ "$i" = 120 ] && { say "app did not start"; finish; }
cd $D && TMH_BASE=http://127.0.0.1:$PORT$PFX/ TMH_OUT=$OUT TMH_JB_YML=$D/src/$YML timeout 1200 npx playwright test -c playwright.config.mjs >&2
[ -f $OUT/report.json ] || say "verifier produced no report"
finish
"""

SPEC_RULES = """写一个 Playwright 实测脚本，在真实运行的应用里逐条验证下面的验收标准。只输出一个代码块，标记为 ```tmh-spec。

脚本要求：
- ESM：`import { test, expect } from '@playwright/test';` 和 `import { login, shot } from './tmh-helpers.mjs';`
- 每条验收标准一个 test，标题以编号开头，例如 `test('A1 取消后恢复原值', async ({ page }, testInfo) => { ... })`。
- 先 `await login(page);`（已处理验证码，登录后在首页），再用 `page.goto(process.env.TMH_BASE + '路由')` 或点菜单进入要测的页面。路由从仓库代码里查。
- 像用户一样操作（点击、输入、选择），每个关键步骤后 `await shot(page, testInfo, '步骤名');`。
- 用 `expect(...)` 断言这条标准能看到的结果；断言失败表示“实测没做到”，所以只断言标准本身要求的东西。
- 不 mock 接口，不改数据库，不写 `page.evaluate` 改组件状态。没法在页面上验证的标准写成 `test.skip('A2 ...', ...)` 并在注释里写原因。
"""


def conf(data_dir: Path, key: str) -> dict | None:
    f = Path(data_dir) / CONF
    try:
        c = (json.loads(f.read_text(encoding="utf-8")).get("projects") or {}).get(key)
    except (OSError, ValueError):
        return None
    return c if isinstance(c, dict) and c.get("ssh") and c.get("app") else None


def spec_prompt(t: dict, acs: list, diff: str) -> str:
    L = [SPEC_RULES, "工单：%s" % t.get("title", ""), (t.get("body") or "")[:2000], "", "验收标准："]
    L += ["- %s %s" % (a["id"], a.get("text", "")) for a in acs]
    L += ["", "这次的改动（已经应用在被测版本上）：", "```diff", diff[:30000], "```"]
    return "\n".join(L)


def spec_from(out: str) -> str:
    m = re.search(r"```tmh-spec\s*\n(.*?)```", out or "", re.S)
    return m.group(1).strip() + "\n" if m else ""


def _walk(suite: dict):
    for s in suite.get("specs") or []:
        yield s
    for child in suite.get("suites") or []:
        yield from _walk(child)


def results(report: dict, acs: list, files: dict) -> list:
    """One entry per criterion: result, what happened, and the screenshots (name -> bytes) of its test."""
    by_id = {}
    for suite in report.get("suites") or []:
        for spec in _walk(suite):
            m = re.match(r"^\s*(A\d+)\b", spec.get("title") or "")
            if m:
                by_id.setdefault(m.group(1), spec)
    out = []
    for a in acs:
        spec = by_id.get(a["id"])
        if not spec:
            out.append({"id": a["id"], "result": "unverified", "how": "实测脚本没有覆盖这条标准", "shots": {}})
            continue
        runs = [r for tst in spec.get("tests") or [] for r in tst.get("results") or []]
        last = runs[-1] if runs else {}
        shots = {n: b for n, b in sorted(files.items()) if n.startswith(a["id"] + "-")} if last else {}
        status = last.get("status") or "skipped"
        msg = re.sub(r"\x1b\[[0-9;]*m", "", ((last.get("error") or {}).get("message") or ""))[:600]
        if status == "passed" and shots:
            res, how = "pass", "页面上实测通过（%d 张截图）" % len(shots)
        elif status == "passed":
            res, how = "unverified", "测试通过但没有截图，不算证明"
        elif status == "failed" and re.search(r"\bexpect\(", msg) and "TMH_SETUP" not in msg:
            res, how = "fail", "页面上实测没做到：" + msg
        elif status == "skipped":
            res, how = "unverified", "这条标准没法在页面上验证"
        else:
            res, how = "unverified", "实测没能执行完（%s）：%s" % (status, msg)
        out.append({"id": a["id"], "result": res, "how": how, "shots": shots})
    return out


def overall(items: list) -> str:
    if any(i["result"] == "fail" for i in items):
        return "fail"
    return "pass" if items and all(i["result"] == "pass" for i in items) else "unverified"


def _ssh(c: dict, remote: str, data: bytes | None = None, timeout: int = 120) -> tuple[int, bytes]:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-p", str(c.get("port") or 22), c["ssh"], remote]
    try:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, b""
    return p.returncode, p.stdout


def _tar(entries: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def run_remote(c: dict, repo: Path, base: str, diff: str, spec: str, job: str, port: int) -> tuple[dict, dict]:
    """Run `spec` against base+diff on the verification host. Returns (playwright json report, files by name)."""
    code, head = _ssh(c, "git -C ~/pv/base rev-parse HEAD")
    entries = {"patch.diff": diff.encode("utf-8"), "tmh-verify.spec.mjs": spec.encode("utf-8"),
               "tmh-helpers.mjs": HELPERS.encode("utf-8"), "playwright.config.mjs": CONFIG.encode("utf-8"),
               "driver.sh": DRIVER.encode("utf-8")}
    have = head.decode().strip()
    if code != 0 or not re.fullmatch(r"[0-9a-f]{40}", have):
        return {"setup": "verification host unreachable"}, {}
    if have != base:
        ref = "refs/tmh-verify/" + job
        subprocess.run(["git", "-C", str(repo), "update-ref", ref, base], check=True)
        try:
            b = subprocess.run(["git", "-C", str(repo), "bundle", "create", "-", ref, "^" + have] if _known(repo, have)
                               else ["git", "-C", str(repo), "bundle", "create", "-", ref], capture_output=True, check=True).stdout
        finally:
            subprocess.run(["git", "-C", str(repo), "update-ref", "-d", ref])
        entries["in.bundle"] = b
    prefix = "/pv/verify/" + job
    remote = "mkdir -p ~/pv/verifier/jobs/%s && tar xz -C ~/pv/verifier/jobs/%s && bash ~/pv/verifier/jobs/%s/driver.sh %s" % (
        job, job, job, " ".join(shlex.quote(str(x)) for x in (job, base, port, prefix, c["app"], c.get("api", ""), c.get("yml", ""))))
    code, out = _ssh(c, remote, _tar(entries), timeout=TIMEOUT)
    files, report = {}, {}
    try:
        with tarfile.open(fileobj=io.BytesIO(out), mode="r:gz") as tf:
            for m in tf.getmembers():
                if m.isfile():
                    data = tf.extractfile(m).read()
                    name = Path(m.name).name
                    if name == "report.json":
                        report = json.loads(data.decode("utf-8") or "{}")
                    elif name.endswith(".png") and "/shots/" in "/" + m.name.lstrip("./"):
                        files[name] = data
    except (tarfile.TarError, ValueError, EOFError):
        return {"setup": "verifier returned nothing (exit %s)" % code}, {}
    return report, files


def _known(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"], capture_output=True).returncode == 0


def binding(base: str, diff: str, spec: str) -> dict:
    return {"base": base, "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            "spec_sha256": hashlib.sha256(spec.encode("utf-8")).hexdigest()}


BY = "AI 验收"
ASK_S = 900


def _ask(P, p: dict, t: dict, prompt: str) -> str:
    """The criteria-to-script step goes to the project's diagnose agent (the one that did not write the change)."""
    import time
    from .agent_routes import step_agent
    agent = step_agent(P.data_dir, p, "diagnose", "") or P.flow.autoflow().get("agent") or "claude"
    r = P.runner.start(p, t, agent, "ask", BY, question=prompt)
    end = time.monotonic() + ASK_S
    while time.monotonic() < end:
        run = P.store.run(r["id"])
        if run["status"] not in ("queued", "running", "starting"):
            return (run.get("result") or run.get("output") or "") if run["status"] == "done" else ""
        time.sleep(3)
    return ""


def _record(P, t: dict, rid: int, items: list, result: str, bind: dict, why: str) -> None:
    import base64
    from . import signoff
    for i in items:
        for name, data in list(i["shots"].items())[-3:]:
            signoff.attach(P, t, BY, i["id"], "%s：%s（%s）" % (i["result"], i["how"][:300], name),
                           "data:image/png;base64," + base64.b64encode(data).decode())
    said = {"pass": "页面实测全部通过", "fail": "页面实测复现了问题", "unverified": "页面实测没能证明"}[result]
    P.store.event(t["id"], BY, "verify", "%s%s" % (said, "（%s）" % why if why else ""),
                  dict(bind, run=rid, result=result, ac=[{k: i[k] for k in ("id", "result", "how")} for i in items]))


def verify(P, p: dict, t: dict, rid: int, acs: list, *, commit: str = "", ask=None) -> dict:
    """Drive the real app for run `rid` (its committed `commit`, else its worktree's base plus its diff)."""
    c = conf(P.data_dir, p["key"])
    if not c:
        return {"result": "unverified", "why": "这个项目没有配真实验证环境", "ac": []}
    run = P.store.run(rid)
    wt = Path(run.get("workdir") or "")
    if commit:
        base, diff = commit, ""
    elif wt.is_dir():
        base = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
        diff = run.get("diff") or ""
    else:
        base, diff = "", ""
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        return {"result": "unverified", "why": "找不到被测版本", "ac": []}
    spec = spec_from((ask or _ask)(P, p, t, spec_prompt(t, acs, run.get("diff") or "")))
    bind = binding(base, diff, spec)
    if not spec:
        items = results({}, acs, {})
        _record(P, t, rid, items, "unverified", bind, "没有写出实测脚本")
        return dict(bind, result="unverified", why="没有写出实测脚本", ac=items)
    job = "%s-r%d-%s" % (p["key"].lower(), rid, bind["spec_sha256"][:8])
    report, files = run_remote(c, Path(p["root"]), base, diff, spec, job, 23100 + rid % 800)
    items = results(report, acs, files)
    why = str(report.get("setup") or "")
    result = "unverified" if why else overall(items)
    _record(P, t, rid, items, result, bind, why)
    return dict(bind, result=result, why=why, ac=items)
