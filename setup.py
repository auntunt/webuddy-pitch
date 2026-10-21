"""Copy the canonical repository assets into wheels without duplicating sources."""
from pathlib import Path
import runpy

from setuptools import setup
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parent
resource_files = runpy.run_path(str(ROOT / "tmh" / "resources.py"))["files"]


class BuildPy(build_py):
    def run(self):
        super().run()
        for source, relative in resource_files(ROOT):
            target = Path(self.build_lib) / "tmh" / "_resources" / relative
            self.mkpath(str(target.parent))
            self.copy_file(str(source), str(target))

    def get_outputs(self, include_bytecode=1):
        return super().get_outputs(include_bytecode) + [
            str(Path(self.build_lib) / "tmh" / "_resources" / relative)
            for _, relative in resource_files(ROOT)
        ]


setup(cmdclass={"build_py": BuildPy})
