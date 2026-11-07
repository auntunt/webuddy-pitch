"""Customer distribution allowlist, shared by wheels, project installation and offline packs."""
from pathlib import Path

PKG = Path(__file__).resolve().parent
DIRECTORIES = ("templates", "skills", "agents", "kb")
# New resources require an explicit review; recursively copying these folders is not allowed.
FILES = (
    'tmh.py',
    'pyproject.toml',
    'setup.py',
    'MANIFEST.in',
    'docs/agent-commands.md',
    'docs/customer/README.md',
    'docs/customer/installation.md',
    'docs/customer/knowledge.md',
    'docs/customer/acceptance.md',
    'docs/customer/operating-boundaries.md',
    'agents/code-cartographer.md',
    'agents/impact-analyst.md',
    'agents/independent-verifier.md',
    'agents/kb-writer.md',
    'agents/sql-dialect-converter.md',
    'kb/crypto-sm.md',
    'kb/db-dialects.md',
    'kb/dotnet.md',
    'kb/frontend.md',
    'kb/middleware.md',
    'kb/os-arch.md',
    'skills/acceptance-l2/SKILL.md',
    'skills/acceptance-route/SKILL.md',
    'skills/business-flow/SKILL.md',
    'skills/dotnet-modernize/SKILL.md',
    'skills/knowledge-upkeep/SKILL.md',
    'skills/legacy-feature/SKILL.md',
    'skills/legacy-onboard/SKILL.md',
    'skills/ops-tools/SKILL.md',
    'skills/xinchuang-assess/SKILL.md',
    'skills/xinchuang-migrate/SKILL.md',
    'templates/AGENTS.block.md',
    'templates/CLAUDE.block.md',
    'templates/integration_plugin_example.py',
    'templates/knowledge-README.md',
)
PACKAGE_DIRECTORIES = (".", "integrations", "platform", "probes")
PACKAGE_ASSETS = ("rules/*.json", "platform/*.cjs", "platform/vendor/*.js", "platform/vendor/*LICENSE*")


def root() -> Path:
    bundled = PKG / "_resources"
    return bundled if bundled.is_dir() else PKG.parent


def files(base: Path, strict: bool = True):
    """Yield approved runtime resources, never repository history or user state."""
    for name in FILES:
        path = base / name
        if not path.is_file():
            if not strict:
                continue
            raise FileNotFoundError("missing tmh resource file: %s" % name)
        if path.is_symlink():
            raise ValueError("resource must be a regular file: %s" % name)
        yield path, name


def code_files(base: Path):
    """Product modules and declared runtime assets only; exclude generated resources and caches."""
    paths = set()
    for directory in PACKAGE_DIRECTORIES:
        paths.update((base / directory).glob("*.py"))
    for pattern in PACKAGE_ASSETS:
        paths.update(base.glob(pattern))
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise ValueError("product module must be a regular file: %s" % path.relative_to(base))
        yield path, path.relative_to(base).as_posix()
