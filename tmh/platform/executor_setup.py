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
_BIN = re.compile(r"[A-Za-z0-9_./\\: ~+\-]{1,500}")
_ABS = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\|~[\\/]|~)")

MARKER = "TMH_OK"


def validate_bin(value):
    if not isinstance(value, str) or not value.strip() or not _BIN.fullmatch(value):
        raise ApiError(400, "执行命令只能包含路径、字母、数字、点、横线和空格")


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
                            capture_output=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
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
    unknown = set(fields) - set(SECRET_FIELDS[engine])
    if unknown:
        raise ApiError(400, "不认识的配置项：" + ",".join(sorted(unknown)))
    fields = {k: v.strip() for k, v in fields.items() if str(v or "").strip()}
    secrets = load_secrets(data_dir)
    environment = {}
    home = Path(data_dir) / "executor-homes" / name
    if engine == "codex":
        if not fields.get("api_key") or not fields.get("base_url"):
            raise ApiError(400, "Codex 连接需要 API 地址和密钥")
        wire = fields.get("wire_api") or "responses"
        if wire not in ("responses", "chat"):
            raise ApiError(400, "wire_api 只能是 responses 或 chat")
        model = fields.get("model") or ""
        lines = ['model_provider = "%s"' % name]
        if model:
            lines.insert(0, 'model = "%s"' % model)
        lines += ["", "[model_providers.%s]" % name, 'name = "%s"' % name,
                  'base_url = "%s"' % fields["base_url"], 'wire_api = "%s"' % wire,
                  'env_key = "%s"' % _ENV_KEY(name)]
        _write_private(home / "config.toml", "\n".join(lines) + "\n")
        secrets[name] = {"env": {_ENV_KEY(name): fields["api_key"]}}
        environment["CODEX_HOME"] = str(home)
    elif engine == "claude":
        env = {}
        if fields.get("base_url"):
            env["ANTHROPIC_BASE_URL"] = fields["base_url"]
        if fields.get("api_key"):
            env["ANTHROPIC_AUTH_TOKEN"] = fields["api_key"]
        if fields.get("model"):
            env["ANTHROPIC_MODEL"] = fields["model"]
        if not env:
            raise ApiError(400, "Claude 连接需要至少一项配置")
        _write_private(home / "settings.json", json.dumps({"env": env}, ensure_ascii=False, indent=1) + "\n")
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
        result = subprocess.run([exe, "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=15)
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
    dirs += [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and "codex" in d.lower()]
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


def _toml_value(text, key, section=""):
    current = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            current = line.strip("[] ")
        elif "=" in line and (not section or current == section):
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
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
        bearer = _toml_value(text, "experimental_bearer_token", "model_providers." + provider) if provider else ""
        info["auth_present"] = bool(bearer) or bool(info["env_key"] and os.environ.get(info["env_key"])) or (Path(home) / "auth.json").is_file()
    else:
        info["auth_present"] = (Path(home) / "auth.json").is_file()
    return info


def _claude_home(home):
    cfg = Path(home) / "settings.json"
    info = {"home": str(home), "exists": Path(home).is_dir()}
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
            info["model"] = data.get("model", "")
            info["base_url"] = (data.get("env") or {}).get("ANTHROPIC_BASE_URL", "")
            info["token_set"] = bool((data.get("env") or {}).get("ANTHROPIC_AUTH_TOKEN"))
        except ValueError:
            info["configuration_error"] = "settings.json 不是有效 JSON"
    info["credentials_present"] = (Path(home) / ".credentials.json").is_file() or info.get("token_set", False)
    return info


def scan():
    """Local-only executor discovery; non-secret fields and booleans only."""
    from . import agents
    launched = agents.executable("codex", {})
    codex = {"executables": [launched] if Path(launched).is_file() else _codex_candidates()}
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
                                    encoding="utf-8", errors="replace", timeout=15)
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


def probe(engine, exe, env, timeout=120):
    """One no-tools request; PASS only when the exact marker is returned."""
    workdir = Path(tempfile.mkdtemp(prefix="tmh-probe-"))
    prompt = "Reply with exactly %s. Do not use tools, read files, or modify files." % MARKER
    if engine == "cursor":
        cmd = [exe, "--trust", "--print", "--output-format", "stream-json", "--sandbox", "disabled", "--mode", "ask"]
        stdin = prompt
    elif engine == "codex":
        cmd = [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check", prompt]
        stdin = None
    else:  # claude
        cmd = [exe, "-p", prompt, "--allowedTools", ""]
        stdin = None
    report = {"ok": False, "command": [cmd[0]] + cmd[1:-1] + (["<prompt>"] if engine != "cursor" else [])}
    try:
        result = subprocess.run(cmd, input=stdin, cwd=str(workdir), env=env,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {**report, "error": "连接测试超时（%d 秒）" % timeout}
    except OSError as exc:
        return {**report, "error": "无法启动执行器：%s" % exc}
    out = (result.stdout or "") + (result.stderr or "")
    ok = result.returncode == 0 and MARKER in result.stdout
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
