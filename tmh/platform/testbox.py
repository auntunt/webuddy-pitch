"""A test machine: a separate computer the platform builds and tests changes on, reached over SSH.

The agents never touch it. After an agent has changed the code, the platform sends the change there, applies it
on the same commit the ticket is pinned to, runs the build and the tests, and hands the result back to the agent.
The machine may start empty: `check` lists what it has, `install` puts the missing tools (Git, JDK, Maven, Node
and pnpm) as unpacked archives under its folder, without administrator rights and without touching the system.

Settings, in <data>/autoflow.json:
    "testbox": {"host": "user@43.153.76.85", "port": 12022, "dir": "C:/tmh-runner"}
Only key login is used (BatchMode): the platform never sends or keeps a password. Windows machines run PowerShell,
others sh; which one is found out on the first contact.

On the machine, <dir>/repos/<project> is a clone of the project and <dir>/work/<project> the one working copy the
builds run in (kept between runs, so Maven's and pnpm's downloads and the compiled classes are reused). One build
per project at a time.
"""
from __future__ import annotations

import base64
import json
import re
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .agents import git

LOCKS: dict[str, threading.Lock] = {}
_guard = threading.Lock()

# unpacked into <dir>/tools by `install`; versions pinned so every machine builds alike
TOOLS = {
    "git": ("MinGit-2.47.1-64-bit.zip", "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/MinGit-2.47.1-64-bit.zip"),
    "java": ("jdk17.zip", "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"),
    "mvn": ("apache-maven-3.9.9-bin.zip", "https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.zip"),
    "node": ("node-v20.18.0-win-x64.zip", "https://nodejs.org/dist/v20.18.0/node-v20.18.0-win-x64.zip"),
}
PROBES = {"git": "git --version", "java": "java -version", "mvn": "mvn -v", "node": "node -v", "pnpm": "pnpm -v", "docker": "docker --version"}


def settings(data_dir: Path) -> dict:
    try:
        v = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("testbox")
    except (OSError, ValueError):
        v = None
    if not isinstance(v, dict) or not v.get("host"):
        return {}
    return {"host": str(v["host"]), "port": int(v.get("port") or 0), "dir": str(v.get("dir") or "").rstrip("/\\"),
            "timeout": int(v.get("timeout") or 1800)}


class TestBox:
    def __init__(self, conf: dict, data_dir: Path):
        self.c = conf
        self.data_dir = Path(data_dir)
        self.os = ""  # "windows" | "posix", found on first contact
        self.dir = conf.get("dir") or ""

    # ------------------------------------------------------------ talking to it
    OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", "-o", "StrictHostKeyChecking=accept-new"]

    def _ssh(self, remote: str, data: bytes | None = None, timeout: int = 120) -> tuple[int, str]:
        # no port: the one in ~/.ssh/config for this host (an alias like "laptop" carries its own), else 22
        cmd = ["ssh"] + (["-p", str(self.c["port"])] if self.c.get("port") else []) + self.OPTS + [self.c["host"], remote]
        try:
            r = subprocess.run(cmd, input=data if data is not None else b"", capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return -1, "超时（%s 秒）" % timeout
        except OSError as e:
            return 127, "本机没有 ssh：%s" % e
        text = (r.stdout + b"\n" + r.stderr).decode("utf-8", "replace").strip()
        if r.returncode == 255:
            text = "连不上测试机（%s%s）：%s" % (self.c["host"], ":%s" % self.c["port"] if self.c.get("port") else "", text[-400:])
        return r.returncode, text

    def _send(self, data: bytes, suffix: str) -> tuple[str, str]:
        """Copy `data` to a new file in the machine's home folder with scp: (its name, "") or ("", why not).
        Not through a script's stdin: Windows OpenSSH does not always pass the end of stdin on, and a PowerShell
        reading to the end then waits until the timeout (and keeps the file open, so the next try collides with it)."""
        name = "tmh-%s%s" % (uuid.uuid4().hex[:12], suffix)
        fd, local = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            cmd = ["scp", "-q"] + (["-P", str(self.c["port"])] if self.c.get("port") else []) + self.OPTS + [local, "%s:%s" % (self.c["host"], name)]
            try:
                r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=self.c.get("timeout") or 1800)
            except subprocess.TimeoutExpired:
                return "", "scp 超时（%s 秒，%d 字节）" % (self.c.get("timeout") or 1800, len(data))
            except OSError as e:
                return "", "本机没有 scp：%s" % e
            if r.returncode != 0:
                return "", "scp 退出码 %s：%s" % (r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace").strip()[-600:])
            return name, ""
        finally:
            try:
                os.unlink(local)
            except OSError:
                pass

    def _detect(self) -> str:
        if not self.os:
            code, out = self._ssh("echo %OS%")
            if code == 255 or code == -1 or code == 127:
                raise RuntimeError(out)
            self.os = "windows" if "Windows_NT" in out else "posix"
            if not self.dir:
                self.dir = "C:/tmh-runner" if self.os == "windows" else "~/tmh-runner"
        return self.os

    def script(self, body: str, data: bytes | None = None, timeout: int = 120) -> tuple[int, str]:
        """Run a script on the machine: PowerShell on Windows (with the tools under <dir>/tools on the PATH), sh elsewhere."""
        if self._detect() == "windows":
            pre = ("$ErrorActionPreference='Continue';$ProgressPreference='SilentlyContinue';"
                   "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$D='%s';"
                   "$T=Join-Path $D 'tools';if(Test-Path $T){Get-ChildItem $T -Directory|ForEach-Object{"
                   "$env:Path=$_.FullName+';'+$_.FullName+'\\bin;'+$_.FullName+'\\cmd;'+$env:Path};"
                   "$j=Get-ChildItem $T -Directory -Filter 'jdk*'|Select-Object -First 1;if($j){$env:JAVA_HOME=$j.FullName}}\n" % self.dir)
            enc = base64.b64encode((pre + body).encode("utf-16-le")).decode()
            return self._ssh("powershell -NoProfile -NonInteractive -EncodedCommand " + enc, data, timeout)
        pre = 'D=%s; T="$D/tools"; for x in "$T"/*; do [ -d "$x" ] && PATH="$x/bin:$x:$PATH"; done; export PATH\n' % self.dir
        return self._ssh("sh -c " + _sh_quote(pre + body), data, timeout)

    # ------------------------------------------------------------ what it has
    def check(self) -> dict:
        """{"os", "dir", "tools": {name: version or ""}, "missing": [...], "error"}"""
        try:
            win = self._detect() == "windows"
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}
        lines = []
        for name, probe in PROBES.items():
            if win:
                # take all the output first: cutting the pipe early (Select-Object -First 1) kills cmd and the exit code reads -1
                lines.append("$a=@(cmd /c '%s 2>&1');$c=$LASTEXITCODE;$o=($a|Select-Object -First 1);Write-Output ('@@%s='+$(if($c -eq 0){$o}else{''}))" % (probe, name))
            else:  # the probe's own exit code decides, not head's
                lines.append('o=$(%s 2>&1) && echo "@@%s=$(printf \'%%s\\n\' "$o" | head -1)" || echo "@@%s="' % (probe, name, name))
        code, out = self.script("\n".join(lines), timeout=90)
        tools = {}
        for m in re.finditer(r"(?m)^@@(\w+)=(.*)$", out):
            tools[m.group(1)] = m.group(2).strip()
        need = ["git", "java", "mvn", "node", "pnpm"]
        return {"ok": True, "os": self.os, "dir": self.dir, "tools": tools, "missing": [n for n in need if not tools.get(n)]}

    def install(self, which: list | None = None) -> dict:
        """Unpack the missing tools under <dir>/tools (Windows). Downloads happen on the test machine itself."""
        if self._detect() != "windows":
            return {"ok": False, "error": "自动安装目前只支持 Windows 测试机；Linux 请用系统的包管理器装 git、openjdk-17、maven、nodejs，再 npm i -g pnpm"}
        have = self.check()
        want = [n for n in list(TOOLS) + ["pnpm"] if n in (which or have.get("missing") or [])]
        done, log = [], []
        for n in want:
            if n == "pnpm":  # needs node, which comes before it
                body = "npm install -g pnpm@9.15.0 --prefix (Join-Path $T 'pnpm') 2>&1;exit $LASTEXITCODE"
            else:
                fn, url = TOOLS[n]
                body = ("New-Item -ItemType Directory -Force $T|Out-Null;$z=Join-Path $env:TEMP '%s';"
                        "Invoke-WebRequest -UseBasicParsing -Uri '%s' -OutFile $z;"
                        "$dst=Join-Path $T '%s';Expand-Archive -Force $z $dst;"
                        "$in=Get-ChildItem $dst -Directory;if(($in|Measure-Object).Count -eq 1 -and -not (Test-Path (Join-Path $dst 'bin')) -and -not (Test-Path (Join-Path $dst 'cmd'))){"
                        "Get-ChildItem $in[0].FullName|Move-Item -Destination $dst;Remove-Item $in[0].FullName};Remove-Item $z;Write-Output ok" % (fn, url, "jdk17" if n == "java" else n))
            code, out = self.script(body, timeout=1800)
            log.append("%s：%s" % (n, "装好了" if code == 0 else "失败：" + out[-300:]))
            if code == 0:
                done.append(n)
        return {"ok": True, "installed": done, "log": log, "check": self.check()}

    # ------------------------------------------------------------ the code
    def _lock(self, key: str) -> threading.Lock:
        with _guard:
            return LOCKS.setdefault(key, threading.Lock())

    def prepare(self, key: str, repo: Path, base: str) -> str:
        """Make sure the machine's clone of project `key` has commit `base` and its working copy sits on it. "" or why not."""
        win = self._detect() == "windows"
        r, w = "%s/repos/%s" % (self.dir, key), "%s/work/%s" % (self.dir, key)
        has = "git -C '%s' cat-file -e '%s^{commit}'" % (r, base)
        code, _ = self.script(has + ("; exit $LASTEXITCODE" if win else ""), timeout=60)
        if code != 0:
            url = git(repo, "remote", "get-url", "origin", check=False).strip()
            if url.startswith(("https://", "http://")):  # a public origin: let the machine fetch it itself
                body = ("if(-not (Test-Path '{r}')){{git clone --no-checkout '{u}' '{r}' 2>&1}};git -C '{r}' fetch origin '{b}' 2>&1;{h};exit $LASTEXITCODE" if win else
                        "[ -d '{r}' ] || git clone --no-checkout '{u}' '{r}' 2>&1; git -C '{r}' fetch origin '{b}' 2>&1; {h}").format(r=r, u=url, b=base, h=has)
                code, out = self.script(body, timeout=self.c["timeout"])
            if code != 0:  # send the history up to the commit (once; later only what is new)
                ref = "refs/tmh-send/" + base  # a bundle carries refs, not bare commits
                git(repo, "update-ref", ref, base)
                try:
                    bundle = subprocess.run(["git", "-C", str(repo), "bundle", "create", "-", ref], capture_output=True).stdout
                finally:
                    git(repo, "update-ref", "-d", ref, check=False)
                if not bundle:
                    return "打包代码失败"
                # a fresh temp name each time: a fixed one collides with a file a scanner or an earlier run still holds
                name, why = self._send(bundle, ".bundle")
                if why:
                    return "把代码传到测试机失败（%d 字节）：%s" % (len(bundle), why)
                body = ("$f=Join-Path $HOME '{n}';if(-not (Test-Path '{r}')){{git init -q '{r}'}};"
                        "git -C '{r}' fetch -q $f '{ref}:{ref}' 2>&1;$c=$LASTEXITCODE;Remove-Item $f -Force -ErrorAction SilentlyContinue;"
                        "if($c -ne 0){{Write-Output ('git fetch exit '+$c);exit $c}};{h};exit $LASTEXITCODE" if win else
                        "f=\"$HOME/{n}\"; [ -d '{r}' ] || git init -q '{r}'; git -C '{r}' fetch -q \"$f\" '{ref}:{ref}' 2>&1; c=$?; rm -f \"$f\"; "
                        "[ $c -eq 0 ] || {{ echo \"git fetch exit $c\"; exit $c; }}; {h}").format(r=r, ref=ref, h=has, n=name)
                code, out = self.script(body, timeout=self.c["timeout"])
                if code != 0:
                    return "把代码传到测试机失败（退出码 %s）：%s" % (code, out[-1500:])
        body = ("if(-not (Test-Path '{w}')){{git -C '{r}' worktree add --detach -f '{w}' '{b}' 2>&1}};"
                "git -C '{w}' checkout -q -f --detach '{b}' 2>&1;git -C '{w}' clean -q -fd -e node_modules -e target 2>&1;exit $LASTEXITCODE" if win else
                "[ -d '{w}' ] || git -C '{r}' worktree add --detach -f '{w}' '{b}' 2>&1; git -C '{w}' checkout -q -f --detach '{b}' 2>&1 && "
                "git -C '{w}' clean -q -fd -e node_modules -e target 2>&1").format(r=r, w=w, b=base)
        code, out = self.script(body, timeout=600)
        return "" if code == 0 else "测试机上切换代码失败（退出码 %s）：%s" % (code, out[-1500:])

    def run(self, key: str, repo: Path, base: str, patch: bytes, seq: list, timeout: int, say=None) -> list:
        """Apply `patch` on `base` in the machine's working copy and run [(kind, command)] there, in order, stopping
        at the first failure. Returns the results in the shape the fix loop uses."""
        say = say or (lambda s: None)
        with self._lock(key):
            why = self.prepare(key, repo, base)
            if why:
                return [{"kind": "setup", "command": "准备测试机", "exit_code": -2, "seconds": 0, "tail": why}]
            win = self.os == "windows"
            w = "%s/work/%s" % (self.dir, key)
            if patch.strip():
                name, why = self._send(patch, ".patch")
                if why:
                    return [{"kind": "setup", "command": "把改动传到测试机", "exit_code": -2, "seconds": 0, "tail": why}]
                body = ("$f=Join-Path $HOME '{n}';"
                        "git -C '{w}' apply --whitespace=nowarn $f 2>&1;$c=$LASTEXITCODE;Remove-Item $f -Force -ErrorAction SilentlyContinue;exit $c" if win else
                        "f=\"$HOME/{n}\"; git -C '{w}' apply --whitespace=nowarn \"$f\" 2>&1; c=$?; rm -f \"$f\"; exit $c").format(w=w, n=name)
                code, out = self.script(body, timeout=120)
                if code != 0:
                    return [{"kind": "setup", "command": "在测试机上应用改动", "exit_code": code, "seconds": 0, "tail": out[-2000:]}]
            res = []
            for kind, cmd in seq:
                say("在测试机上构建测试：%s" % cmd)
                t0 = time.time()
                body = ("Set-Location '{w}';cmd /c '{c} 2>&1';exit $LASTEXITCODE" if win else "cd '{w}' && {c} 2>&1").format(w=w, c=cmd.replace("'", "''") if win else cmd)
                code, out = self.script(body, timeout=timeout)
                x = {"kind": kind, "command": cmd, "exit_code": code, "seconds": round(time.time() - t0, 1),
                     "tail": "\n".join(out.strip().splitlines()[-60:]), "where": "测试机"}
                res.append(x)
                say("%s，%s 秒" % ("通过" if code == 0 else "失败（退出码 %s）" % code, x["seconds"]))
                if code != 0:
                    break
            return res


def build_commands(repo: Path, files: list) -> tuple[list, str]:
    """Compile-only commands for the changed files, as the test machine runs them from the project root:
    Maven modules holding changed Java files (with what they need), and the type check of a changed frontend.
    Returns ([(kind, command)], why none)."""
    mods, roots, fronts = [], set(), set()
    # a pom.xml the plan creates counts as there: a Maven project written from nothing is compiled too
    planned = {(repo / f).parent for f in files if f.replace("\\", "/").rsplit("/", 1)[-1] == "pom.xml"}
    for f in files:
        p = (repo / f).parent
        if f.endswith((".java", ".xml", ".yml", ".yaml", ".properties")):
            pom = _up(repo, p, "pom.xml", planned)
            if pom is not None:
                top = pom
                while top != repo and ((top.parent / "pom.xml").exists() or top.parent in planned):
                    top = top.parent
                roots.add(top)
                mods.append((top, pom))
        elif f.endswith((".ts", ".tsx", ".vue", ".js")):
            pk = _up(repo, p, "package.json")
            if pk is not None:
                fronts.add(pk)
    seq = []
    for top in sorted(roots):
        pl = sorted({str(m.relative_to(top)).replace("\\", "/") for t, m in mods if t == top and m != top})
        where = str(top.relative_to(repo)).replace("\\", "/")
        cmd = "mvn -B -q compile -DskipTests" + (" -pl %s -am" % ",".join(pl) if pl else "")
        seq.append(("build", ("cd %s && %s" % (where, cmd)) if where != "." else cmd))
    for pk in sorted(fronts):
        try:
            pj = json.loads((pk / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dev = dict(pj.get("dependencies") or {}, **(pj.get("devDependencies") or {}))
        scripts = pj.get("scripts") or {}
        where = str(pk.relative_to(repo)).replace("\\", "/")
        check = "pnpm run type:check" if "type:check" in scripts else ("pnpm exec vue-tsc --noEmit" if "vue-tsc" in dev else ("pnpm exec tsc --noEmit" if "typescript" in dev else ""))
        if check:
            seq.append(("build", ("cd %s && " % where if where != "." else "") + "pnpm install --prefer-offline && " + check))
    return seq, ("" if seq else "改动里没有能在测试机上编译检查的文件（Java 模块或带类型检查的前端）")


def _up(repo: Path, p: Path, name: str, planned: set = frozenset()):
    while True:
        if (p / name).exists() or p in planned:
            return p
        if p == repo or p.parent == p:
            return None
        p = p.parent


def runs_on(repo: Path, cmd: str, rev: str = "") -> bool:
    """Whether a build command from build_commands can run on this tree as it is (or, with `rev`, on that commit of
    it): not when its module (or the frontend) is one the change is about to create."""
    m = re.match(r"cd (\S+) && ", cmd)
    where = m.group(1).strip("/") + "/" if m else ""
    need = "pom.xml" if "mvn " in cmd else "package.json" if "pnpm " in cmd else ""
    if not need:
        return True
    if rev:
        return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", "%s:%s%s" % (rev, where, need)], capture_output=True).returncode == 0
    return (repo / where / need).exists()


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"
