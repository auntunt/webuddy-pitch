"""Runtime assets shared by source checkouts, wheels and vendored tools."""
from pathlib import Path


PKG = Path(__file__).resolve().parent
DIRECTORIES = ("templates", "skills", "agents", "kb")
FILES = (
    "tmh.py", "pyproject.toml", "setup.py", "MANIFEST.in", "README.md", "docs/platform.md",
    "docs/knowledge-base.md", "docs/integrations.md", "docs/acceptance.md",
    "docs/evidence-flow.md", "docs/agent-commands.md", "docs/dead-ends.md",
    "docs/self-improvement/verification-preview-health-2026-10-19.md",
    "docs/self-improvement/verification-runtime-2026-10-18.md",
    "docs/self-improvement/verification-external-candidate-2026-10-19.md",
    "docs/self-improvement/verification-harness2-2026-10-19.md",
    "scripts/rsi/provider_transport.py",
)


def root() -> Path:
    bundled = PKG / "_resources"
    return bundled if bundled.is_dir() else PKG.parent


def files(base: Path):
    """Yield every required asset, failing before installation if one is absent."""
    for name in DIRECTORIES:
        directory = base / name
        if not directory.is_dir():
            raise FileNotFoundError("missing tmh resource directory: %s" % directory)
        for path in sorted(directory.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != ".DS_Store":
                yield path, path.relative_to(base).as_posix()
    for name in FILES:
        path = base / name
        if not path.is_file():
            raise FileNotFoundError("missing tmh resource file: %s" % path)
        yield path, name
