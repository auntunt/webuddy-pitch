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
    "name": "OpenJDK17U-jdk_x64_windows_hotspot_17.0.21_9.zip",
    "sources": [
        "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.21%2B9/OpenJDK17U-jdk_x64_windows_hotspot_17.0.21_9.zip",
        "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/windows/OpenJDK17U-jdk_x64_windows_hotspot_17.0.21_9.zip",
        "https://mirrors.huaweicloud.com/adoptium/temurin17-binaries/jdk-17.0.21%2B9/OpenJDK17U-jdk_x64_windows_hotspot_17.0.21_9.zip",
    ],
    "algo": "sha256",
    "digest": "98518ecf554465057ee5509462631deeee374bc368c12a411d225cd29381f84b",
    "folder": "jdk-17.0.21+9",
}
MAVEN = {
    "version": "3.9.16",
    "name": "apache-maven-3.9.16-bin.zip",
    "sources": [
        "https://downloads.apache.org/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip",
        "https://mirrors.tuna.tsinghua.edu.cn/apache/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip",
        "https://mirrors.huaweicloud.com/apache/maven/maven-3/3.9.16/binaries/apache-maven-3.9.16-bin.zip",
    ],
    "algo": "sha512",
    "digest": "ed41650d42485cfc243fad22158caf9cbb5dc408ce7a09ddb94dd42a019de929ca43065bfa450612cf12bf78b5cafa3884b96c090de326ff590448c933454af3",
    "folder": "apache-maven-3.9.16",
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


def _fetch(pin: dict, home: Path) -> tuple[Path, str]:
    """Installed folder and where its archive came from: a pre-placed archive, else the first source that answers."""
    target = home / pin["folder"]
    if target.is_dir():
        return target, "已有"
    home.mkdir(parents=True, exist_ok=True)
    placed = home / "downloads" / pin["name"]
    if placed.is_file():
        _verified(placed, pin)
        return _extract(placed, home, pin), "本地预置包"
    archive = home / pin["name"]
    errors = []
    for url in pin["sources"]:
        try:
            with urllib.request.urlopen(url, timeout=120) as resp, archive.open("wb") as out:
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            archive.unlink(missing_ok=True)
            errors.append("%s：%s" % (url.split("/")[2], exc))
            continue
        _verified(archive, pin)
        return _extract(archive, home, pin), url.split("/")[2]
    raise ApiError(409, "下载 %s 失败（已依次尝试官方源与镜像）：%s" % (pin["folder"], "；".join(errors)))


def _extract(archive: Path, home: Path, pin: dict) -> Path:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(home)
    archive.unlink(missing_ok=True)
    return home / pin["folder"]


def prepare(root: Path, home: Path) -> dict:
    """Environment for a task's commands: JAVA_HOME and PATH entries. Reuses an installed toolchain first."""
    env, notes = {}, []
    paths = []
    if "jdk" in needs(root):
        java = shutil.which("java")
        if java:
            notes.append("已有 Java：%s" % java)
        else:
            jdk, source = _fetch(JDK, home)
            env["JAVA_HOME"] = str(jdk)
            paths.append(str(jdk / "bin"))
            notes.append("JDK %s（%s）" % (JDK["version"], "已有" if source == "已有" else "来源：" + source))
    if "maven" in needs(root):
        mvn = shutil.which("mvn")
        if mvn:
            notes.append("已有 Maven：%s" % mvn)
        else:
            maven, source = _fetch(MAVEN, home)
            paths.append(str(maven / "bin"))
            notes.append("Maven %s（%s）" % (MAVEN["version"], "已有" if source == "已有" else "来源：" + source))
    if paths:
        env["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
    return {"env": env, "notes": notes}
