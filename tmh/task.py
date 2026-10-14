"""Requirement / change contracts under .tmh/tasks/.

A contract pins what must change, what must stay the same and how each claim
will be checked, before any code is touched. It doubles as the hand-off record
for the next session or the human reviewer.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config as cfgmod
from .fsutil import git_head
from .report import now

TEMPLATE = """# {tid} {title}

- 类型：{kind}
- 创建：{created} · 基线提交 `{head}`
- 状态：草稿（契约确认前不要改代码）

## 1. 需求原文
{request}

## 2. 要改变的行为
- [ ] （用可观察的输入/输出描述，例如“在 /order/list 页面增加按审批状态筛选”）

## 3. 必须保持不变的行为
- [ ] （老接口签名、报表口径、对外文件格式、权限规则……）

## 4. 验收标准与检查方式
| # | 验收条款 | 检查方式（自动化测试 / 命令 / 人工） | 结果 |
|---|---|---|---|
| A1 |  |  | 未验证 |

## 5. 影响范围（用 tmh where / tmh impact 得到，附 文件:行号）
- 入口：
- 业务逻辑：
- 数据表 / SQL：
- 配置 / 前端：
- 其他调用方：

## 6. 风险、未知项与需要人决定的问题
- [事实] / [推断] / [待确认] 分开写

## 7. 实施计划
1. 先补“保持不变”的特征测试（characterization test），确认在旧代码上通过
2. 再按最小改动实现
3. 运行 `tmh verify`，把结果填回第 4 节

## 8. 验证记录
"""

KINDS = {"feature": "新需求", "migration": "信创改造", "bugfix": "缺陷修复", "refactor": "重构", "upgrade": "升级"}


def tasks_dir(root: Path) -> Path:
    return cfgmod.tmh_dir(root) / "tasks"


def new_task(root: Path, title: str, kind: str = "feature", request: str = "") -> Path:
    d = tasks_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(m.group(1)) for p in d.iterdir() for m in [re.match(r"T(\d+)", p.name)] if m] or [0])
    tid = "T%03d" % n
    slug = re.sub(r"[^\w一-龥]+", "-", title).strip("-")[:40] or "task"
    p = d / ("%s-%s.md" % (tid, slug))
    p.write_text(TEMPLATE.format(tid=tid, title=title, kind=KINDS.get(kind, kind), created=now(),
                                 head=(git_head(root) or "未纳入 git")[:12], request=request or title), encoding="utf-8")
    return p


def list_tasks(root: Path) -> list[dict]:
    d = tasks_dir(root)
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("T*.md")):
        text = p.read_text(encoding="utf-8")
        st = re.search(r"- 状态：(.+)", text)
        out.append({"file": p.relative_to(root).as_posix(), "title": text.splitlines()[0].lstrip("# "), "status": st.group(1).strip() if st else "?"})
    return out
