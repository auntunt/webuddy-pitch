"""Per-repository harness configuration stored in <repo>/.tmh/config.json."""
from __future__ import annotations

import json
from pathlib import Path

TMH_DIR = ".tmh"

# Recognised values. "unknown" means "not decided yet": rules that depend on the
# value still run so nothing is silently hidden.
CHOICES = {
    "db": ["unknown", "oracle", "mysql", "sqlserver", "postgresql", "dm8", "kingbase", "opengauss", "gaussdb", "oceanbase", "gbase", "shentong"],
    "appserver": ["unknown", "tomcat", "weblogic", "websphere", "jboss", "iis", "tongweb", "apusic", "bes", "inforsuite", "kestrel"],
    "os": ["unknown", "windows", "linux", "kylin", "uos", "openeuler"],
    "arch": ["unknown", "x86_64", "arm64", "loongarch64", "mips64"],
    "crypto": ["none", "sm"],
    "mq": ["unknown", "ibmmq", "activemq", "rabbitmq", "kafka", "rocketmq", "tonglinkq"],
    "cache": ["unknown", "redis", "tongrds", "other"],
    "browser": ["unknown", "ie", "chromium"],
    "jdk": ["unknown", "oracle", "openjdk", "bisheng", "kona", "dragonwell", "loongson"],
}

DEFAULT_CONFIG = {
    "version": 1,
    "project": {"name": "", "description": ""},
    "source": {"db": "unknown", "appserver": "unknown", "os": "unknown", "arch": "x86_64"},
    "target": {
        "db": "unknown", "appserver": "unknown", "os": "kylin", "arch": "unknown",
        "crypto": "none", "mq": "unknown", "cache": "unknown", "browser": "chromium", "jdk": "unknown",
    },
    "commands": {"build": "", "test": "", "extra_checks": []},
    "protected": [
        "**/src/test/**", "**/*Test.java", "**/*Tests.java", "**/*Tests.cs", "**/*.Tests/**", "**/*.UnitTests/**",
        ".tmh/config.json", ".tmh/baseline.json", ".claude/settings.json",
    ],
    "allow_protected_edits": False,
    "allow_db_cli": False,
    # Ops tools (Jira, Jenkins, GitLab, 禅道, SonarQube …). Credentials are env-var names only.
    "integrations": {"tools": {}, "defaults": {}, "agent_writes": False},
    "scan": {"exclude": ["**/vendor/**", "**/*.min.js", "**/static/lib/**", "**/wwwroot/lib/**"], "disabled_rules": []},
}


def tmh_dir(root: Path) -> Path:
    return root / TMH_DIR


def load(root: Path) -> dict:
    p = tmh_dir(root) / "config.json"
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if p.exists():
        user = json.loads(p.read_text(encoding="utf-8"))
        _merge(cfg, user)
    return cfg


def save(root: Path, cfg: dict) -> Path:
    d = tmh_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def _merge(base: dict, over: dict) -> None:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def lookup(cfg: dict, dotted: str) -> str:
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return "unknown"
        cur = cur[part]
    return str(cur)

