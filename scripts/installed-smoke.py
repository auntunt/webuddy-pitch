"""Exercise an installed distribution from outside its source checkout.

Run with Python's isolated mode: python -I -X utf8 scripts/installed-smoke.py TARGET.
TARGET is the directory produced by pip install --target. No external service,
model, existing project or platform data is used.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            timeout=90)
    print(result.stdout, end="", flush=True)
    if result.returncode:
        raise RuntimeError("installed command failed (%d): %s" % (result.returncode, args))


def main():
    installed = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(installed))
    import tmh

    module = Path(tmh.__file__).resolve()
    module.relative_to(installed)  # refuse a checkout/global-package false positive
    print("installed module: %s" % module, flush=True)
    bootstrap = (
        "import sys; sys.path.insert(0, sys.argv.pop(1)); "
        "from tmh.cli import main; raise SystemExit(main())"
    )
    # -I ignores PYTHONUTF8/PYTHONIOENCODING, including on Windows runners.
    isolated = [sys.executable, "-I", "-X", "utf8"]
    cli = isolated + ["-c", bootstrap, str(installed)]
    with tempfile.TemporaryDirectory(prefix="tmh-installed-smoke-") as folder:
        outside = Path(folder)
        project = outside / "project with spaces"
        project.mkdir()
        original = "# Existing project notes\nKeep this content.\n"
        (project / "AGENTS.md").write_text(original, encoding="utf-8")
        run(cli + ["--version"], outside)
        workbench = bootstrap.replace("from tmh.cli", "from tmh.workbench")
        run(isolated + ["-c", workbench, str(installed), "--help"], outside)
        run(cli + ["install", "--repo", str(project)], outside)
        from tmh import resources
        assets = list(resources.files(resources.root()))
        for source, _ in assets:
            source.resolve().relative_to(installed)
        tool = project / ".tmh" / "tool" / "tmh.py"
        # The copied tool must work, and be able to refresh itself without
        # deleting its own code or depending on the original checkout.
        run(isolated + [str(tool), "install", "--repo", str(project)], outside)
        run(isolated + [str(tool), "--version"], outside)
        assert (project / "AGENTS.md").read_text(encoding="utf-8").startswith(original)
        for source, relative in assets:
            assert (tool.parent / "tmh" / "_resources" / relative).read_bytes() == source.read_bytes(), relative
        assert (project / ".tmh/docs/agent-commands.md").is_file()
        assert (project / ".agents/skills/legacy-feature/SKILL.md").is_file()

        archive = outside / "offline.zip"
        run(cli + ["offline-pack", "--out", str(archive)], outside)
        run(cli + ["offline-pack", "--verify", str(archive)], outside)
        unpacked = outside / "unpacked"
        with zipfile.ZipFile(archive) as package:
            for source, relative in assets:
                assert package.read(relative) == source.read_bytes(), relative
            package.extractall(unpacked)
        run(isolated + [str(unpacked / "tmh.py"), "install",
             "--repo", str(outside / "offline project")], outside)
    print("installed smoke: PASS (origin, CLI, install, refresh, complete resources, offline install)")


if __name__ == "__main__":
    main()
