"""应用层: the services people use, each a thin layer over the coding line (orchestra.py) and the knowledge layer.

An app decides three things and nothing more: where its tasks come from, who accepts them, and what it counts.
It puts tasks on the line with `P.flow.submit`, hears verdicts through `P.flow.listen`, and reads the project
through `P.kb`. Adding a service (工单获取, 会议纪要, 报价…) means adding an entry here and its own module; the
line and the knowledge layer do not change.
"""
from __future__ import annotations

APPS = [
    {"key": "ops", "name": "运维服务", "desc": "报单、导入和告警来的问题：定位、修复、验收，统计响应和解决时长。",
     "sources": ["人工报单", "Jira / 禅道导入", "助手会话", "告警和报错日志（alerts.py）"], "home": "#/"},
    {"key": "reform", "name": "重构服务", "desc": "老项目的结构重构、依赖升级、框架迁移、兼容适配：按业务域拆成改造工单，一批验收通过再放下一批。",
     "sources": ["改造计划（reform.py）"], "home": "#/reform"},
]


def app_of(t: dict) -> str:
    """Which service a ticket belongs to: a piece of a reform plan carries links.reform, everything else is 运维."""
    return "reform" if (t.get("links") or {}).get("reform") else "ops"


def wire(P) -> None:
    """Connect the apps that react to verdicts. 运维 needs nothing: its tickets simply end at acceptance; a 大需求
    (epic.py) is 运维 too, its children ordinary tickets, but it listens to move its batches on."""
    from . import epic, reform
    P.flow.listen(reform.listener(P))
    P.flow.listen(epic.listener(P))
    P.flow.start_from(epic.base_for(P))
