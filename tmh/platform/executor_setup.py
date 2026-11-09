"""Executor discovery, dedicated credential homes and connection probes.

Three separations that must not blur: agents.json holds non-secret per-install
fields (bin, environment); executor-secrets.json holds raw API keys (POSIX
0600, Windows ACL current user + SYSTEM); executor-homes/<name>/ holds a
dedicated CODEX_HOME/CLAUDE_CONFIG_DIR generated from the non-secret fields.
Secret values are never returned by scan/view APIs, never on argv, never in
run output or prompts."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import ApiError

ENV_VARS = ("CODEX_HOME", "CLAUDE_CONFIG_DIR")
SECRET_FIELDS = {"codex": ("base_url", "api_key", "model", "wire_api"),
                 "claude": ("base_url", "api_key", "model"),
                 "cursor": ("api_key",)}
_ENV_KEY = lambda name: "WEBUDDY_KEY_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()
_BIN = re.compile(r"[\w./\\: ~+()\-]{0,500}")
_ABS = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\|~[\\/]|~)")

MARKER = "TMH_OK"


def validate_bin(value):
    if not isinstance(value, str) or not _BIN.fullmatch(value):
        raise ApiError(400, "填写命令名或路径（支持中文和括号）；留空自动查找，不支持命令参数或脚本")


def validate_environment(value):
    if not isinstance(value, dict) or set(value) - set(ENV_VARS):
        raise ApiError(400, "配置目录只允许 CODEX_HOME 与 CLAUDE_CONFIG_DIR")
    for key, path in value.items():
        if not isinstance(path, str) or not _ABS.match(path.strip()):
            raise ApiError(400, "%s 必须是绝对路径" % key)


def secrets_path(data_dir):
    return Path(data_dir) / "executor-secrets.json"


def load_secrets(data_dir):
    path = secrets_path(data_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _restrict(path):
    if sys.platform == "win32":
        me = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command",
                             "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],
                            capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                        "*" + me + ":F", "*S-1-5-18:F"], capture_output=True, check=True)
    else:
        path.chmod(0o600 if path.is_file() else 0o700)


def _write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    _restrict(path)


def save_secrets(data_dir, entries):
    _write_private(secrets_path(data_dir), json.dumps(entries, ensure_ascii=False, indent=1) + "\n")


def secrets_set(data_dir, name):
    return name in load_secrets(data_dir)


def set_secret(data_dir, name, engine, fields):
    """Store per-executor connection fields; generate the dedicated home for
    codex/claude. Returns the non-secret `environment` to persist in agents.json."""
    if engine not in SECRET_FIELDS:
        raise ApiError(400, "这个执行器不支持连接配置")
    if not isinstance(fields, dict):
        raise ApiError(400, "连接配置必须是对象")
    unknown = set(fields) - set(SECRET_FIELDS[engine])
    if unknown:
        raise ApiError(400, "不认识的配置项：" + ",".join(sorted(unknown)))
    if any(not isinstance(v, str) for v in fields.values()):
        raise ApiError(400, "连接配置必须是文本")
    fields = {k: v.strip() for k, v in fields.items() if str(v or "").strip()}
    secrets = load_secrets(data_dir)
    environment = {}
    home = Path(data_dir) / "executor-homes" / name
    if engine == "codex":
        old = _codex_home(home)
        previous = {k: old.get(k, "") for k in ("base_url", "model", "wire_api")}
        previous["api_key"] = (secrets.get(name, {}).get("env") or {}).get(_ENV_KEY(name), "")
        fields = {**previous, **fields}
        if not fields.get("api_key") or not fields.get("base_url"):
            raise ApiError(400, "Codex 连接需要 API 地址和密钥")
        wire = fields.get("wire_api") or "responses"
        if wire not in ("responses", "chat"):
            raise ApiError(400, "wire_api 只能是 responses 或 chat")
        model = fields.get("model") or ""
        cfg = home / "config.toml"
        text = cfg.read_text(encoding="utf-8-sig") if cfg.exists() else ""
        text = _toml_update(text, "", {"model_provider": name, **({"model": model} if model else {})})
        text = _toml_update(text, "model_providers." + name,
                            {"name": name, "base_url": fields["base_url"], "wire_api": wire, "env_key": _ENV_KEY(name)})
        _write_private(cfg, text)
        secrets[name] = {"env": {_ENV_KEY(name): fields["api_key"]}}
        environment["CODEX_HOME"] = str(home)
    elif engine == "claude":
        cfg = home / "settings.json"
        settings = json.loads(cfg.read_text(encoding="utf-8-sig")) if cfg.exists() else {}
        env = dict(settings.get("env") or {})
        if fields.get("base_url"):
            env["ANTHROPIC_BASE_URL"] = fields["base_url"]
        if fields.get("api_key"):
            env["ANTHROPIC_AUTH_TOKEN"] = fields["api_key"]
        if fields.get("model"):
            env["ANTHROPIC_MODEL"] = fields["model"]
        if not env:
            raise ApiError(400, "Claude 连接需要至少一项配置")
        _write_private(home / "settings.json", json.dumps({**settings, "env": env}, ensure_ascii=False, indent=1) + "\n")
        secrets[name] = {}
        environment["CLAUDE_CONFIG_DIR"] = str(home)
    else:  # cursor
        if not fields.get("api_key"):
            raise ApiError(400, "Cursor 连接需要 API Key")
        secrets[name] = {"env": {"CURSOR_API_KEY": fields["api_key"]}}
    save_secrets(data_dir, secrets)
    return environment


def spawn_env(data_dir, name, conf_entry):
    """Extra env for the agent child: configured config dirs + secret env vars."""
    out = dict(conf_entry.get("environment") or {})
    out.update((load_secrets(data_dir).get(name) or {}).get("env") or {})
    return out


def _version(exe):
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        line = (result.stdout or result.stderr).strip().splitlines()
        return (line[0] if line else "")[:120]
    except (OSError, subprocess.SubprocessError):
        return ""


def _which(names, extra_dirs):
    found = []
    for name in names:
        p = shutil.which(name)
        if p:
            found.append(p)
    suffixes = {".cmd", ".exe", ".bat"} if os.name == "nt" else {""}
    for d in extra_dirs:
        for name in names:
            for suffix in (suffixes or {""}):
                p = Path(d) / (name + suffix)
                if p.is_file():
                    found.append(str(p))
    seen = []
    for p in found:
        if p not in seen:
            seen.append(p)
    return seen


def _codex_candidates():
    dirs = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            dirs.append(Path(appdata) / "npm")
            dirs += sorted(Path(appdata).glob("npm/node_modules/@openai/codex/*/bin/codex*.exe"))
            dirs += sorted(Path(appdata).glob("npm/node_modules/@openai/codex/**/codex-win32-x64/codex.exe"))
    else:
        dirs += [Path.home() / ".local/bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin")]
    files = [str(p) for p in dirs if p.is_file()]
    dirs = [str(p) for p in dirs if p.is_dir()]
    return _which(["codex"], dirs) + files


def _cursor_candidates():
    dirs, files = [], []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            for cand in (Path(local) / "cursor-agent" / "agent.cmd",
                         Path(local) / "Programs" / "cursor-agent" / "agent.cmd"):
                if cand.is_file():
                    files.append(str(cand))
            dirs.append(str(Path(local) / "cursor-agent"))
            dirs.append(str(Path(local) / "Programs"))
    else:
        dirs += [str(Path.home() / ".local/bin"), "/usr/local/bin", "/opt/homebrew/bin"]
    return _which(["agent", "cursor-agent"], dirs) + files


def _toml_update(text, section, values):
    lines, current, remaining = [], "", dict(values)
    found = not section
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if current == section:
                lines.extend(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in remaining.items())
                remaining.clear()
            current = stripped.strip("[] ")
            found = found or current == section
        if current == section and "=" in line and line.split("=", 1)[0].strip() in values:
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                lines.append(key + " = " + json.dumps(remaining.pop(key), ensure_ascii=False))
        else:
            lines.append(line)
    if remaining:
        if section and not found:
            lines += ["", "[" + section + "]"]
        lines.extend(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in remaining.items())
    return "\n".join(lines) + "\n"


def _toml_value(text, key, section=""):
    current = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            current = line.strip("[] ")
        elif "=" in line and current == section and line.split("=", 1)[0].strip() == key:
            value = line.split("=", 1)[1].strip()
            if value.startswith('"'):
                try:
                    return json.JSONDecoder().raw_decode(value)[0]
                except ValueError:
                    return ""
            if value.startswith("'"):
                return value[1:].split("'", 1)[0]
            return value.split("#", 1)[0].strip()
    return ""


def _codex_home(home):
    cfg = Path(home) / "config.toml"
    info = {"home": str(home), "exists": Path(home).is_dir()}
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8-sig", errors="replace")
        info["model"] = _toml_value(text, "model")
        provider = _toml_value(text, "model_provider")
        info["model_provider"] = provider
        for key in ("base_url", "wire_api", "env_key"):
            info[key] = _toml_value(text, key, "model_providers." + provider) if provider else ""
    info["auth_present"] = (Path(home) / "auth.json").is_file()
    return info


def _claude_home(home):
    cfg = Path(home) / "settings.json"
    info = {"home": str(home), "exists": Path(home).is_dir()}
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
            info["model"] = (data.get("env") or {}).get("ANTHROPIC_MODEL") or data.get("model", "")
            info["base_url"] = (data.get("env") or {}).get("ANTHROPIC_BASE_URL", "")
            info["token_set"] = bool((data.get("env") or {}).get("ANTHROPIC_AUTH_TOKEN"))
        except ValueError:
            info["configuration_error"] = "settings.json 不是有效 JSON"
    info["credentials_present"] = (Path(home) / ".credentials.json").is_file() or info.get("token_set", False)
    return info


def scan():
    """Local-only executor discovery; non-secret fields and booleans only."""
    codex = {"executables": _codex_candidates()}
    if codex["executables"]:
        codex["version"] = _version(codex["executables"][0])
    codex.update(_codex_home(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    claude_dirs = [str(Path(os.environ["APPDATA"]) / "npm")] if sys.platform == "win32" and os.environ.get("APPDATA") else \
        [str(Path.home() / ".local/bin"), "/usr/local/bin", "/opt/homebrew/bin"]
    claude = {"executables": _which(["claude"], claude_dirs)}
    if claude["executables"]:
        claude["version"] = _version(claude["executables"][0])
    claude.update(_claude_home(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))
    cursor = {"executables": _cursor_candidates()}
    if cursor["executables"]:
        cursor["version"] = _version(cursor["executables"][0])
    cursor["api_key_set"] = bool(os.environ.get("CURSOR_API_KEY"))
    if cursor["executables"]:
        try:
            status = subprocess.run([cursor["executables"][0], "status"], capture_output=True,
                                    text=True, timeout=15)
            out = (status.stdout + status.stderr).lower()
            cursor["logged_in"] = status.returncode == 0 and "logged in" in out and "not" not in out.split("logged in")[0][-10:]
        except (OSError, subprocess.SubprocessError):
            cursor["logged_in"] = False
    return {"codex": codex, "claude": claude, "cursor": cursor}


CURSOR_FAILURES = [
    (r"Workspace Trust Required",
     "项目工作区尚未信任", "在该项目目录交互运行一次 agent，确认信任后再重试"),
    (r"Sandbox mode is enabled but not available",
     "Cursor 沙箱模式不可用", "Webuddy 已传 --sandbox disabled；检查是否有外部配置覆盖了它"),
    (r"uv_os_get_passwd",
     "Cursor 无法读取 Windows 用户信息",
     "请在普通用户桌面会话中启动 Webuddy，不要在受限/服务会话中运行"),
    (r"Not logged in|unauthenticated|Authentication required",
     "Cursor 未登录", "在 Webuddy 运行的同一 Windows 账号执行 `agent login`，或在设置里填写 Cursor API Key"),
    (r"Failed to load models",
     "Cursor 模型列表获取失败", "检查 Cursor API Key 与网络；或在智能体设置里直接填写模型名"),
]


def cursor_failure(text):
    """(what, fix) when output matches a known Cursor failure, else ()."""
    for pattern, what, fix in CURSOR_FAILURES:
        if re.search(pattern, text or ""):
            return what, fix
    return ()


def probe(engine, exe, env, timeout=45, model="", profile=""):
    with tempfile.TemporaryDirectory(prefix="tmh-probe-") as workdir:
        return _probe(engine, exe, env, timeout, model, profile, Path(workdir))


def _probe(engine, exe, env, timeout, model, profile, workdir):
    """One no-tools request; PASS only when the exact marker is returned."""
    prompt = "Reply with exactly %s. Do not use tools, read files, or modify files." % MARKER
    if engine == "cursor":
        cmd = [exe, "--trust", "--print", "--output-format", "stream-json", "--sandbox", "disabled", "--mode", "ask"]
        stdin = prompt
    elif engine == "codex":
        cmd = [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--json"] + (["--profile", profile] if profile else [])
        stdin = None
    else:  # claude
        cmd = [exe, "-p", "--output-format", "json", "--allowedTools", ""]
        stdin = None
    if model:
        cmd += ["--model", model]
    report = {"ok": False, "command": cmd + (["<prompt>"] if engine != "cursor" else []),
              "model": model, "profile": profile}
    if engine != "cursor":
        cmd.append(prompt)
    try:
        result = subprocess.run(cmd, input=stdin, cwd=str(workdir), env=env,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {**report, "error": "连接测试超时（%d 秒）" % timeout}
    except OSError as exc:
        return {**report, "error": "无法启动执行器：%s" % exc}
    out = (result.stdout or "") + (result.stderr or "")
    answer, failed = "", False
    for line in (result.stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") in ("error", "turn.failed"):
            failed = True
        if event.get("type") == "result":
            failed = failed or bool(event.get("is_error")) or event.get("subtype", "success") != "success"
            answer = event.get("result", "")
        elif engine == "codex" and event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                answer = item.get("text", "")
    ok = result.returncode == 0 and not failed and isinstance(answer, str) and answer.strip() == MARKER
    report["returncode"] = result.returncode
    if ok:
        report["ok"] = True
    else:
        excerpt = re.sub(r"(sk-[A-Za-z0-9_\-]{8,}|wbt_[A-Za-z0-9_.\-]{8,}|[A-Za-z0-9_\-]{24,})", "***", out)
        report["error_excerpt"] = excerpt.strip()[-400:]
        known = cursor_failure(out)
        if known:
            report["reason"], report["fix"] = known
    return report
