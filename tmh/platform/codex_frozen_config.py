"""Private source binding and public configuration for an isolated Codex parent.

This is not an admission switch or an executable launcher. A trusted carrier
keeps the upstream credential and exposes only its fixed local Responses route.
The original user config is never copied into the worker's CODEX_HOME.
"""
import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-\[\]/]{0,79}")
MAX_CONFIG_BYTES = 8 * 1024 * 1024
LOCAL_BASE = "http://127.0.0.1:48671/v1"
PUBLIC_KEY = "webuddy-public-placeholder"
OVERLAY_FIELDS = {"model", "model_provider", "approval_policy", "model_reasoning_effort"}
PROVIDER_FIELDS = {"name", "base_url", "wire_api", "env_key", "experimental_bearer_token",
                   "requires_openai_auth", "supports_websockets", "supports_standalone_web_search", "http_headers"}
ACTOR_HEADER = "x-openai-actor-authorization"


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read(directory, name, owner_uid):
    """Read a whole private regular file through the already opened home FD."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != owner_uid or stat.S_IMODE(before.st_mode) & 0o077):
            raise ValueError("isolated Codex configuration must be owner-only regular files")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_CONFIG_BYTES + 1)
        after = os.fstat(fd)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if (len(raw) > MAX_CONFIG_BYTES or len(raw) != before.st_size
                or identity(before) != identity(after) or identity(after) != identity(current)):
            raise ValueError("isolated Codex configuration changed or exceeds the complete-file limit")
        return raw
    finally:
        os.close(fd)


def _toml(raw):
    try:
        import tomllib
    except ImportError:
        raise ValueError("isolated Codex configuration requires the installed Python TOML reader") from None
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        # Parser diagnostics may quote a source line containing a credential.
        raise ValueError("invalid private Codex configuration") from None


def _name(value, pattern, label):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("invalid isolated Codex " + label)
    return value


class FrozenConfig:
    """Host-only parsed sources. Export binding(), never this object's internals."""

    def __init__(self, home, profile, requested_model="", environment=None, source_owner_uid=None):
        self._source_owner_uid = os.geteuid() if source_owner_uid is None else source_owner_uid
        if (type(self._source_owner_uid) is not int or self._source_owner_uid < 0
                or os.geteuid() not in (0, self._source_owner_uid)):
            raise ValueError("trusted configuration owner required")
        self.home = Path(home)
        if not self.home.is_absolute() or ".." in self.home.parts:
            raise ValueError("trusted absolute Codex configuration home required")
        self.profile = _name(profile, PROFILE, "profile")
        self.requested_model = requested_model
        if not isinstance(requested_model, str):
            raise ValueError("invalid isolated Codex model")
        if requested_model:
            _name(requested_model, MODEL, "model")
        directory = os.open(str(self.home), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory)
            if info.st_uid != self._source_owner_uid or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("untrusted Codex configuration directory")
            base_raw = _read(directory, "config.toml", self._source_owner_uid)
            overlay_raw = _read(directory, self.profile + ".config.toml", self._source_owner_uid)
            current = self.home.lstat()
            if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("Codex configuration directory replaced")
        finally:
            os.close(directory)
        base, overlay = _toml(base_raw), _toml(overlay_raw)
        # Support the existing independent profile, without guessing at arbitrary
        # official merge semantics for hooks, MCP, project config or provider tables.
        if set(overlay) - OVERLAY_FIELDS or overlay.get("approval_policy", "never") != "never":
            raise ValueError("unsupported isolated Codex profile fields")
        self.model = _name(requested_model or overlay.get("model", base.get("model")), MODEL, "model")
        self.provider = _name(overlay.get("model_provider", base.get("model_provider")), PROFILE, "provider")
        providers = base.get("model_providers")
        provider = providers.get(self.provider) if isinstance(providers, dict) else None
        if not isinstance(provider, dict) or set(provider) - PROVIDER_FIELDS:
            raise ValueError("unsupported isolated Codex provider configuration")
        for flag in ("requires_openai_auth", "supports_websockets", "supports_standalone_web_search"):
            if flag in provider and type(provider[flag]) is not bool:
                raise ValueError("invalid isolated provider capability type")
        if provider.get("requires_openai_auth", False):
            raise ValueError("isolated provider cannot acquire external OpenAI authentication")
        headers = provider.get("http_headers", {})
        if (type(headers) is not dict or len(headers) > 1
                or any(not isinstance(name, str) or name.lower() != ACTOR_HEADER
                       or not isinstance(value, str) or not value or value.strip() != value
                       or any(ord(c) < 32 or ord(c) > 126 for c in value)
                       for name, value in headers.items())):
            raise ValueError("unsupported isolated host-only provider headers")
        self._host_headers = {ACTOR_HEADER: value for value in headers.values()}
        if provider.get("wire_api") != "responses":
            raise ValueError("isolated Codex requires the configured Responses provider")
        endpoint = provider.get("base_url")
        if not isinstance(endpoint, str) or any(ord(c) < 33 or ord(c) == 127 for c in endpoint):
            raise ValueError("isolated Codex requires an explicit upstream endpoint")
        try:
            url = urlsplit(endpoint)
            valid = (url.scheme == "https" and bool(url.hostname) and not url.username
                     and not url.password and not url.query and not url.fragment
                     and url.path == "/v1" and url.port in (None, 443))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("unsupported isolated Codex upstream endpoint")
        self._provider = dict(provider)
        self._endpoint = endpoint
        self._reasoning = overlay.get("model_reasoning_effort", base.get("model_reasoning_effort"))
        if self._reasoning is not None and (not isinstance(self._reasoning, str) or self._reasoning not in ("none", "minimal", "low", "medium", "high", "xhigh")):
            raise ValueError("unsupported isolated Codex reasoning setting")
        self._credential = self._credential_from(os.environ if environment is None else environment)
        self._sources = [{"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                         for name, raw in (("config.toml", base_raw), (self.profile + ".config.toml", overlay_raw))]

    def binding(self):
        """Public identity, with no source text, credential, home or raw provider."""
        value = {"schema": "codex-isolated-config-v1", "profile": self.profile,
                 "source_owner_uid": self._source_owner_uid,
                 "model": self.model, "provider": self.provider, "sources": self._sources,
                 "worker_config_sha256": hashlib.sha256(self.worker_config()).hexdigest(),
                 "isolation_changes": ["private-home", "generated-config", "no-hooks-mcp-memory", "fixed-gateway"]}
        return json.loads(_encoded(value))

    def assert_current(self, environment=None):
        current = FrozenConfig(self.home, self.profile, self.requested_model, environment, self._source_owner_uid)
        if current.binding() != self.binding() or not hmac.compare_digest(current._credential, self._credential):
            raise ValueError("frozen Codex configuration changed; do not switch or retry")

    def _credential_from(self, environment):
        provider = self._provider
        env_key, inline = provider.get("env_key"), provider.get("experimental_bearer_token")
        if env_key is not None and (not isinstance(env_key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_key)):
            raise ValueError("invalid isolated Codex credential source")
        # Ambiguous precedence must not silently select a different credential.
        if bool(env_key) == bool(inline):
            raise ValueError("isolated Codex requires exactly one explicit host credential source")
        key = environment.get(env_key) if env_key else inline
        if not isinstance(key, str) or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("isolated Codex host credential unavailable")
        return key

    def upstream(self, environment):
        """Trusted host broker only; never serialize this result into run evidence."""
        self.assert_current(environment)
        result = {"endpoint": self._endpoint + "/responses", "key": self._credential}
        if self._host_headers:
            result["headers"] = dict(self._host_headers)
        return result

    def worker_config(self):
        """A complete generated policy; no original config/auth file is copied."""
        lines = ["model = " + json.dumps(self.model), 'model_provider = "webuddy_isolated"',
                 'approval_policy = "never"', 'default_permissions = "webuddy_frozen_v1"',
                 'web_search = "disabled"']
        if self._reasoning is not None:
            lines.append("model_reasoning_effort = " + json.dumps(self._reasoning))
        # Exact 0.162.1 fields: the provider-hosted web tool defaults to cached,
        # independently of the local network sandbox. The isolated profile
        # explicitly disables unused remote/extension discovery as well.
        lines.extend(['[mcp_servers]', '[plugins]', '[features]',
                      'apps = false', 'enable_mcp_apps = false', 'plugins = false',
                      'remote_plugin = false', 'image_generation = false',
                      'browser_use = false', 'browser_use_external = false', 'computer_use = false',
                      'skill_mcp_dependency_install = false', 'tool_suggest = false', 'recommended_plugins = false',
                      '[model_providers.webuddy_isolated]', 'name = "Webuddy isolated route"',
                      'base_url = "' + LOCAL_BASE + '"', 'wire_api = "responses"',
                      'requires_openai_auth = false', 'supports_websockets = false',
                      'supports_standalone_web_search = false',
                      'env_key = "WEBUDDY_ISOLATED_PUBLIC_KEY"', '[shell_environment_policy]',
                      'inherit = "none"', '[permissions.webuddy_frozen_v1.filesystem]',
                      '":minimal" = "read"', '":workspace_roots" = "read"',
                      '"/opt/official" = "read"', '"/input" = "read"',
                      '"/work/home/.codex" = "deny"', '"/proc" = "deny"',
                      '[permissions.webuddy_frozen_v1.network]', 'enabled = false'])
        return ("\n".join(lines) + "\n").encode("utf-8")


def worker_environment():
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/work/home",
            "CODEX_HOME": "/work/home/.codex", "TMPDIR": "/work/tmp",
            "PYTHONDONTWRITEBYTECODE": "1", "WEBUDDY_ISOLATED_PUBLIC_KEY": PUBLIC_KEY}


def worker_command():
    # The generated named permissions profile is authoritative. Ordinary
    # agents.command() inserts --sandbox read-only and must not build this argv.
    return ["/usr/bin/node", "/opt/official/bin/codex.js", "exec", "--strict-config", "--ignore-rules",
            "--skip-git-repo-check", "--ephemeral", "--json", "--color", "never", "-C", "/work", "-"]
