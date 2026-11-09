"""Build environment for a task: detect what the project needs, reuse what is installed, and download pinned
portable toolchains without admin rights when they are missing. A failed download is reported, never a pass.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .errors import ApiError

JDK = {
    "version": "17.0.21+9",
    "url": "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.21%2B9/OpenJDK17U-jdk_x64_windows_hotspot_17.0.21_9.zip",
    "algo": "sha256",
    "digest": "98518ecf554465057ee5509462631deeee374bc368c12a411d225cd29381f84b",
    "folder": "jdk-17.0.21+9",
}
MAVEN = {
    "version": "3.9.9",
    "url": "https://downloads.apache.org/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.zip",
    "algo": "sha512",
    "digest": "8beac8d11ef208f1e2a8df0682b9448a9a363d2ad13ca74af43705549e72e74c9378823bf689287801cbbfc2f6ea9596201d19ccacfdfb682ee8a2ff4c4418ba",
    "folder": "apache-maven-3.9.9",
}


def needs(root: Path) -> set[str]:
    """Which toolchains the project needs, from its own build files."""
    out = set()
    if (root / "pom.xml").exists() or (root / "mvnw").exists() or (root / "mvnw.cmd").exists():
        out |= {"jdk", "maven"}
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists() or (root / "gradlew").exists():
        out.add("jdk")
    if (root / "package.json").exists():
        out.add("node")
    return out


def _verified(path: Path, pin: dict) -> None:
    h = hashlib.new(pin["algo"])
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != pin["digest"]:
        path.unlink(missing_ok=True)
        raise ApiError(409, "下载的%s校验失败，已丢弃" % pin["folder"])


def _fetch(pin: dict, home: Path) -> Path:
    target = home / pin["folder"]
    if target.is_dir():
        return target
    home.mkdir(parents=True, exist_ok=True)
    archive = home / (pin["folder"] + ".zip")
    if not archive.exists():
        try:
            with urllib.request.urlopen(pin["url"], timeout=120) as resp, archive.open("wb") as out:
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            archive.unlink(missing_ok=True)
            raise ApiError(409, "下载 %s 失败：%s" % (pin["folder"], exc)) from exc
    _verified(archive, pin)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(home)
    archive.unlink()
    return target


def prepare(root: Path, home: Path) -> dict:
    """Environment for a task's commands: JAVA_HOME and PATH entries. Reuses an installed toolchain first."""
    env, notes = {}, []
    paths = []
    if "jdk" in needs(root):
        java = shutil.which("java")
        if java:
            notes.append("已有 Java：%s" % java)
        else:
            jdk = _fetch(JDK, home)
            env["JAVA_HOME"] = str(jdk)
            paths.append(str(jdk / "bin"))
            notes.append("已下载 JDK %s" % JDK["version"])
    if "maven" in needs(root):
        mvn = shutil.which("mvn")
        if mvn:
            notes.append("已有 Maven：%s" % mvn)
        else:
            maven = _fetch(MAVEN, home)
            paths.append(str(maven / "bin"))
            notes.append("已下载 Maven %s" % MAVEN["version"])
    if paths:
        env["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
    return {"env": env, "notes": notes}
