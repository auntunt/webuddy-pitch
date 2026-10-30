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

HELPERS = r"""import { test as base, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export { expect };

// the app is up only once its loading screen is gone and the network is quiet; until then nothing on the page proves anything
export async function ready(page) {
  try {
    await page.waitForLoadState('networkidle', { timeout: 240000 });
    await page.waitForFunction(() => !document.querySelector('.app-loading') && document.body.innerText.trim().length > 0, null, { timeout: 240000 });
  } catch (e) {
    throw new Error('TMH_SETUP page did not finish loading: ' + e.message);
  }
}

// a step the criterion itself does not ask about (the page is there, a button to reach it): not finding it is the script's fault
export async function anchor(locator, what = '') {
  try {
    await expect(locator).toBeVisible({ timeout: 30000 });
  } catch (e) {
    throw new Error('TMH_ANCHOR ' + what + ': ' + e.message);
  }
}

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const goto = page.goto.bind(page);
    page.goto = async (url, opts) => { const r = await goto(url, opts); await ready(page); return r; };
    await use(page);
    // a failed test leaves what the page really showed, so a wrong locator can be told from a real defect
    if (testInfo.status !== testInfo.expectedStatus) {
      let seen = '';
      const ways = [
        () => page.locator('body').ariaSnapshot({ timeout: 10000 }),
        async () => JSON.stringify(await page.accessibility.snapshot({ interestingOnly: true }), null, 1),
        () => page.locator('body').innerText({ timeout: 10000 }),
      ];
      for (const way of ways) {
        try { seen = await way(); } catch (e) { seen = ''; }
        if (seen) break;
      }
      const file = path.join(process.env.TMH_OUT, 'shots', testInfo.title.split(' ')[0] + '-page.txt');
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, seen.slice(0, 6000));
    }
  },
});

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
  await ready(page);
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

WARM = """import { chromium } from '@playwright/test';
import { ready } from './tmh-helpers.mjs';

// a cold dev server compiles and re-optimizes on first visits (and reloads the page): let that settle before any test looks
export default async function () {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    for (let i = 0; i < 2; i++) {
      await page.goto(process.env.TMH_BASE + 'user/login', { timeout: 240000 });
      await ready(page);
      await page.waitForTimeout(5000);
    }
  } finally {
    await browser.close();
  }
}
"""

CONFIG = """export default { testDir: '.', testMatch: 'tmh-verify.spec.mjs', timeout: 240000, workers: 1, retries: 0,
  globalSetup: './tmh-warm.mjs',
  reporter: [['json', { outputFile: process.env.TMH_OUT + '/report.json' }]],
  use: { viewport: { width: 1440, height: 900 } }, outputDir: process.env.TMH_OUT + '/artifacts' };
"""

DRIVER = r"""set -u
J=$1; BASE=$2; PORT=$3; PFX=$4; APP=$5; API=$6; YML=$7
export PATH=~/.local/bin:$PATH
D=~/pv/verifier/jobs/$J; OUT=$D/out; mkdir -p $OUT; cd $D
say() { echo "{\"setup\": \"$1\"}" > $OUT/report.json; }
finish() { [ -n "${VP:-}" ] && kill -- -$VP 2>/dev/null; git -C ~/pv/base worktree remove --force $D/src >/dev/null 2>&1
  git -C ~/pv/base update-ref -d refs/tmh/$J >/dev/null 2>&1; tar cz -C $OUT .; rm -rf $D; exit 0; }
if [ -f in.bundle ]; then
  git -C ~/pv/base fetch -q $D/in.bundle "+refs/tmh-verify/$J:refs/tmh/$J" >&2 || { say "candidate bundle did not fetch"; finish; }
fi
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
- ESM：`import { test, expect, anchor, login, shot } from './tmh-helpers.mjs';`（这里的 `page.goto` 会等页面加载完）
- 只为最后列出的验收标准写 test（工单正文里其他「必须保持」之类的条目由自动测试证明，不要写）。每条一个 test，标题以编号开头，例如 `test('A1 取消后恢复原值', async ({ page }, testInfo) => { ... })`。
- 先 `await login(page);`（已处理验证码，登录后在首页），再用 `page.goto(process.env.TMH_BASE + '路由')` 或点菜单进入要测的页面。路由从仓库代码里查；`TMH_BASE` 已以 `/` 结尾，路由不要再加开头的 `/`；登录页是 `TMH_BASE + 'user/login'`。
- 进入页面后先 `shot` 一张，再做任何断言：没截到页面就失败的，不能算标准没做到。
- 像用户一样操作（点击、输入、选择），每个关键步骤后 `await shot(page, testInfo, '步骤名');`。
- 标准本身没问到的前置条件（页面已经出来、要点的按钮在），用 `await anchor(定位, '说明')`，不用 `expect`：找不到算脚本问题，不算标准没做到。
- 断言某样东西「不存在 / 不再显示」之前，先用 `anchor` 确认同一页面上一个本来就该在的元素可见，证明页面已经加载出来。
- Ant Design 的两个汉字按钮会显示成「登 录」这样中间带空格：按钮名用正则，如 `getByRole('button', { name: /登\\s*录/ })`。
- 页面上常有隐藏的同类元素（比如登录页里隐藏的注册、手机登录表单）：优先 `getByRole` / `getByText(..., { exact: true })`，定位输入框等元素时加 `:visible` 或限定在可见的表单里，保证只命中一个。
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
    if not m:
        return ""
    # the helpers' `test` waits for the page to load on every goto: a spec written against the bare one still gets it
    return re.sub(r"""(import\s*\{[^}]*\}\s*from\s*)(['"])@playwright/test\2""", r"\1'./tmh-helpers.mjs'", m.group(1)).strip() + "\n"


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
        shots = {n: b for n, b in sorted(files.items()) if n.startswith(a["id"] + "-") and n.endswith(".png")} if last else {}
        seen = files.get(a["id"] + "-page.txt", b"").decode("utf-8", "replace") if last else ""
        status = last.get("status") or "skipped"
        msg = re.sub(r"\x1b\[[0-9;]*m", "", ((last.get("error") or {}).get("message") or ""))[:600]
        if status == "passed" and shots:
            res, how = "pass", "页面上实测通过（%d 张截图）" % len(shots)
        elif status == "passed":
            res, how = "unverified", "测试通过但没有截图，不算证明"
        elif status == "failed" and "TMH_ANCHOR" in msg:
            res, how = "unverified", "实测脚本的前置步骤没找到要的元素：" + msg
        elif status == "failed" and "strict mode violation" in msg:
            res, how = "unverified", "实测脚本的定位命中了多个元素：" + msg
        elif status == "failed" and re.search(r"\bexpect\(", msg) and "TMH_SETUP" not in msg and not shots:
            res, how = "unverified", "实测脚本在截下页面之前就断言失败，看不到页面实际是什么样：" + msg
        elif status == "failed" and re.search(r"\bexpect\(", msg) and "TMH_SETUP" not in msg:
            res, how = "fail", "页面上实测没做到：" + msg
        elif status == "skipped":
            res, how = "unverified", "这条标准没法在页面上验证"
        else:
            res, how = "unverified", "实测没能执行完（%s）：%s" % (status, msg)
        out.append({"id": a["id"], "result": res, "how": how, "shots": shots, "page": seen})
    return out


SCRIPT_FAULT = ("实测没能执行完", "实测脚本的定位命中了多个元素", "实测脚本的前置步骤没找到要的元素", "实测脚本在截下页面之前")


def repairable(items: list) -> bool:
    """A first script is a draft: any criterion it did not pass (other than the app not coming up) earns one review of the script."""
    return any(i["result"] != "pass" and "TMH_SETUP" not in i["how"] for i in items)


QUOTED = re.compile(r"[「“\"']([^」”\"']{2,40})[」”\"']")


def keeps(spec: str, fixed: str, acs: list) -> bool:
    """A reviewed script may change how it finds things, never what it checks: every quoted term of a criterion the draft checked stays."""
    return all(q in fixed for a in acs for q in QUOTED.findall(a.get("text") or "") if q in spec)


def repair_prompt(spec: str, items: list) -> str:
    L = ["下面这个 Playwright 实测脚本在真实应用里跑过一次，有的标准没通过。逐条对照「页面实际内容」判断：",
         "- 页面实际已经做到了标准，是脚本的定位、等待、步骤或对页面结构的假设错了：修脚本；",
         "- 页面实际确实没做到标准：这条 test 一字不改。",
         "每条 test 检查的内容和标准要求保持不变，不许删掉、跳过或放松断言，不许改成检查别的东西。"
         "只输出完整脚本，一个 ```tmh-spec 代码块。", "",
         SPEC_RULES, "原脚本：", "```js", spec, "```", "", "每条标准的结果："]
    for i in items:
        L.append("- %s %s：%s" % (i["id"], i["result"], i["how"][:600]))
        if i.get("page"):
            L += ["  页面实际内容（无障碍树）：", "  ```", i["page"][:3000], "  ```"]
    return "\n".join(L)


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
               "tmh-helpers.mjs": HELPERS.encode("utf-8"), "tmh-warm.mjs": WARM.encode("utf-8"), "playwright.config.mjs": CONFIG.encode("utf-8"),
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
                    elif name.endswith((".png", "-page.txt")) and "/shots/" in "/" + m.name.lstrip("./"):
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


def full_sha(root: Path, commit: str) -> str:
    """The full id of `commit` (evidence keeps short ids); empty unless it names exactly that commit."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        return ""
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", commit + "^{commit}"],
                         capture_output=True, text=True, check=False).stdout.strip()
    return out if re.fullmatch(r"[0-9a-f]{40}", out) and out.startswith(commit) else ""


def _job(p: dict, rid: int, bind: dict) -> str:
    return "%s-r%d-%s" % (p["key"].lower(), rid, bind["spec_sha256"][:8])


def verify(P, p: dict, t: dict, rid: int, acs: list, *, commit: str = "", ask=None) -> dict:
    """Drive the real app for run `rid` (its committed `commit`, else its worktree's base plus its diff)."""
    c = conf(P.data_dir, p["key"])
    if not c:
        return {"result": "unverified", "why": "这个项目没有配真实验证环境", "ac": []}
    run = P.store.run(rid)
    wt = Path(run.get("workdir") or "")
    if commit:
        base, diff = full_sha(Path(p["root"]), commit), ""
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
    report, files = run_remote(c, Path(p["root"]), base, diff, spec, _job(p, rid, bind), 23100 + rid % 800)
    items = results(report, acs, files)
    why = str(report.get("setup") or "")
    if not why and repairable(items):
        fixed = spec_from((ask or _ask)(P, p, t, repair_prompt(spec, items)))
        if fixed and fixed != spec and keeps(spec, fixed, acs):
            bind = dict(binding(base, diff, fixed), repaired_from=bind["spec_sha256"])
            report, files = run_remote(c, Path(p["root"]), base, diff, fixed, _job(p, rid, bind), 23100 + rid % 800)
            items = results(report, acs, files)
            why = str(report.get("setup") or "")
    result = "unverified" if why else overall(items)
    _record(P, t, rid, items, result, bind, why)
    return dict(bind, result=result, why=why, ac=items)
