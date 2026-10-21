"""Offline install pack for intranet machines (内网私有化包).

`tmh offline-pack --out tmh-offline.zip` bundles everything `tmh install` and
`tmh serve` need: the tool itself, templates, skills, sub-agents, the 信创
knowledge base and the docs. The harness has no third-party dependencies, so a
machine with Python 3.8+ needs nothing else. MANIFEST.sha256 lists every file's
hash; `tmh offline-pack --verify <zip>` (or `sha256sum -c MANIFEST.sha256` after
unpacking) checks a copy that came through a USB stick or a file gateway.
"""
from __future__ import annotations

import hashlib
import time
import zipfile
from pathlib import Path

from . import __version__
from .install import HOME, PKG
from . import resources

DIRS = ("tmh",) + resources.DIRECTORIES
FILES = resources.FILES
SKIP = ("__pycache__", ".pyc", ".DS_Store")

README = """# tmh 内网离线安装包 {version}

打包时间 {built}。不需要联网，也不需要 pip 装任何依赖，只要 Python 3.8 以上。

## 1. 校验

    sha256sum -c MANIFEST.sha256          # Linux / 麒麟 / 统信
    python3 tmh.py offline-pack --verify <本压缩包>   # 任何系统，解压前也可用

## 2. 装进项目仓库

    python3 tmh.py install --repo /path/to/项目       # 默认同时装 Claude Code 和 Codex 的配置
    cd /path/to/项目
    python3 .tmh/tool/tmh.py kb build                 # 解析代码，建知识图谱（纯本地）

装好后项目里有 `.tmh/tool/`（工具本体，随仓库走）、`.tmh/knowledge/`（项目知识库）、AGENTS.md / CLAUDE.md、技能和子代理。

## 3. 接内网模型

所有密钥只放在环境变量里，配置文件只写环境变量的名字。

**需求预判 / 群机器人用的转发模型**：任何兼容 OpenAI `/chat/completions` 的内网服务都可以（vLLM、Xinference、
One-API、各家国产模型的私有化网关）。要求支持 `logprobs`，不支持时照样能用，把握度按“中”处理。

    export TMH_ROUTER_BASE_URL=http://10.0.0.8:8000/v1
    export TMH_ROUTER_MODEL=qwen2.5-72b-instruct
    export TMH_ROUTER_KEY=…                  # 没有鉴权可以不设

也可以写进 `.tmh/config.json`：`"router": {{"base_url": "http://10.0.0.8:8000/v1", "model": "qwen2.5-72b-instruct", "key_env": "TMH_ROUTER_KEY"}}`。

**写知识页、分析工单的智能体**：平台调用本机的 Claude Code 或 Codex 命令行。
Codex 在 `~/.codex/config.toml` 里配 `model_providers` 指向内网 OpenAI 兼容地址；
Claude Code 用 `ANTHROPIC_BASE_URL` 指向内网的 Anthropic 兼容网关。两者都不可用时，知识库仍可由人按 `tmh kb next` 领任务撰写。

## 4. 启动运维平台

    export TMH_TOKEN=$(python3 -c "import secrets;print(secrets.token_hex(16))")
    python3 tmh.py serve --project /path/to/项目 --key TOG --host 0.0.0.0

浏览器打开 `http://<本机>:8790/?token=<TMH_TOKEN>`。

## 5. 群机器人（可选）

在 `.tmh/config.json` 的 `"bots"` 里配置钉钉、飞书、企业微信或开放接口，回调地址是
`/bot/dingtalk/<项目代号>`、`/bot/feishu/<项目代号>`、`/bot/wecom/<项目代号>`、`/bot/api/<项目代号>`。
各平台的私有化部署可用 `base_url` 改成内网地址。详细字段见 `tmh/bots.py` 开头的说明。

## 文件清单

{count} 个文件，见 MANIFEST.sha256。
"""


def _files() -> list[tuple[Path, str]]:
    out = []
    for p in sorted(PKG.rglob("*")):
        relative = p.relative_to(PKG)
        if p.is_file() and "_resources" not in relative.parts and not any(s in str(relative) for s in SKIP):
            out.append((p, "tmh/" + relative.as_posix()))
    out.extend(resources.files(HOME))
    return out


def build(out: Path) -> dict:
    files = _files()
    if not files or not (PKG / "cli.py").exists():
        raise RuntimeError("找不到 harness 源文件：请在 harness 检出目录里运行")
    lines, total = [], 0
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.localtime()[:6]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, arc in files:
            b = p.read_bytes()
            total += len(b)
            lines.append("%s  %s" % (hashlib.sha256(b).hexdigest(), arc))
            zi = zipfile.ZipInfo(arc, stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if arc.endswith(".py") and "/" not in arc else 0o644) << 16
            z.writestr(zi, b)
        readme = README.format(version=__version__, built=time.strftime("%Y-%m-%d %H:%M"), count=len(files) + 1).encode("utf-8")
        lines.append("%s  %s" % (hashlib.sha256(readme).hexdigest(), "README-offline.md"))
        z.writestr(zipfile.ZipInfo("README-offline.md", stamp), readme)
        z.writestr(zipfile.ZipInfo("MANIFEST.sha256", stamp), ("\n".join(lines) + "\n").encode("utf-8"))
    return {"out": str(out), "files": len(lines), "bytes": total, "zip_bytes": out.stat().st_size,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def verify(path: Path) -> dict:
    bad, missing, n = [], [], 0
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "MANIFEST.sha256" not in names:
            raise ValueError("压缩包里没有 MANIFEST.sha256")
        for line in z.read("MANIFEST.sha256").decode("utf-8").splitlines():
            if not line.strip():
                continue
            h, arc = line.split("  ", 1)
            n += 1
            if arc not in names:
                missing.append(arc)
            elif hashlib.sha256(z.read(arc)).hexdigest() != h:
                bad.append(arc)
        extra = sorted(names - {l.split("  ", 1)[1] for l in z.read("MANIFEST.sha256").decode("utf-8").splitlines() if l.strip()} - {"MANIFEST.sha256"})
    return {"ok": not (bad or missing or extra), "files": n, "bad": bad, "missing": missing, "extra": extra}
