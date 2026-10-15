"""运维工作拆解树：PPT 和文档共用的唯一数据源。

状态口径：以 2026-10-09 tob-maintenance-harness 代码为准。
  done = 已有（代码已实现，含只在模拟环境测过的）
  part = 部分具备
  gap  = 缺
phase: 1/2/3 = 立项分期；None = 未入期（按试点需要插队）
"""

AS_OF = "2026-10-09"

ROOT = "老项目运维提效"
GOAL = "答得快 · 改得稳 · 翻新看得见"

# kind: work = 工作域（按“谁在做”），base = 底座，cross = 横切能力（无场景层）
BRANCHES = [
    dict(id="A", name="需求接入与现场答复", who="需求 · 实施 · 售前 · 驻场", kind="work", scenes=[
        ("A1", "需求受理", [("A1-1", "原话转工单", "done", None),
                          ("A1-2", "相似工单查重", "done", 1),
                          ("A1-3", "需求变更台账", "part", None)]),
        ("A2", "能不能做", [("A2-1", "可行性自动答复", "done", 1),
                          ("A2-2", "转人工与答案回流", "done", 1)]),
        ("A3", "多久能做", [("A3-1", "工作量区间", "gap", 2)]),
        ("A4", "算不算维保", [("A4-1", "维保范围判断", "gap", None)]),
        ("A5", "业务答疑", [("A5-1", "业务答疑", "done", None)]),
    ]),
    dict(id="B", name="日常需求与功能维护", who="维保开发 · 测试", kind="work", scenes=[
        ("B1", "定位", [("B1-1", "需求定位", "done", None)]),
        ("B2", "方案与影响", [("B2-1", "影响分析", "done", None),
                           ("B2-2", "变更方案与契约", "done", None)]),
        ("B3", "无人化修改", [("B3-1", "智能体修改", "done", None),
                           ("B3-2", "风险分级与自动触发", "gap", 2)]),
        ("B4", "回归与验证", [("B4-1", "验证闸门", "done", None),
                           ("B4-2", "回归清单与表征测试", "gap", 2),
                           ("B4-3", "修复原因留痕", "part", 2),
                           ("B4-4", "部分代码可运行环境", "gap", None)]),
        ("B5", "验收与上线", [("B5-1", "验收说明与变更记录", "part", None),
                           ("B5-2", "补丁跨客户分支传播", "gap", 2)]),
    ]),
    dict(id="C", name="线上问题与数据运维", who="运维 · 值班开发", kind="work", scenes=[
        ("C1", "报错定位", [("C1-1", "报错到业务流", "part", None)]),
        ("C2", "数据修复", [("C2-1", "数据修复脚本", "gap", None)]),
        ("C3", "巡检", [("C3-1", "定时任务与接口巡检", "part", None)]),
    ]),
    dict(id="D", name="重写与技术升级", who="技术负责人 · 架构", kind="work", scenes=[
        ("D1", "现状体检", [("D1-1", "项目体检报告", "done", None)]),
        ("D2", "改造规划", [("D2-1", "按业务流规划改造", "gap", 3),
                          ("D2-2", "信创适配规则", "done", None)]),
        ("D3", "批量改造", [("D3-1", "确定性配方", "gap", 3)]),
        ("D4", "行为对比", [("D4-1", "新旧行为对比", "gap", 3)]),
        ("D5", "进度看板", [("D5-1", "改造进度看板", "part", 3)]),
    ]),
    dict(id="E", name="项目知识与交接", who="全员共用的底座", kind="base", scenes=[
        ("E1", "代码图谱与业务地图", [("E1-1", "代码图谱与业务地图", "done", None)]),
        ("E2", "业务 Wiki", [("E2-1", "业务 Wiki", "done", None)]),
        ("E3", "交接与上手", [("E3-1", "交接包", "part", None),
                           ("E3-2", "新人上手路径", "gap", None),
                           ("E3-3", "交接核对清单", "gap", None)]),
        ("E4", "知识回流", [("E4-1", "知识回流", "done", None),
                          ("E4-2", "AI 改动留痕", "part", None)]),
    ]),
    dict(id="F", name="人机接口", who="横切：一份知识，多个出口", kind="cross", scenes=[
        ("F", "", [("F-1", "平台界面", "done", None),
                   ("F-2", "场景提示词", "done", None),
                   ("F-3", "MCP", "done", None),
                   ("F-4", "CLI（tmh）", "done", None),
                   ("F-5", "群机器人 / 开放 API", "done", 1),
                   ("F-6", "无人化流水线", "part", None),
                   ("F-7", "内网离线包", "done", 1),
                   ("F-8", "跨项目工作台", "gap", None)]),
    ]),
    dict(id="G", name="度量与管理", who="横切：每一步自动记账", kind="cross", scenes=[
        ("G", "", [("G-1", "提效报告与基线", "done", None),
                   ("G-2", "成本与模型", "part", None),
                   ("G-3", "工时自动归集", "gap", 2),
                   ("G-4", "“少找人”统计", "done", 1),
                   ("G-5", "维保价值账单", "part", 2)]),
    ]),
]

STATUS_LABEL = {"done": "已有", "part": "部分", "gap": "缺"}


def modules():
    for b in BRANCHES:
        for sid, sname, mods in b["scenes"]:
            for mid, mname, st, ph in mods:
                yield dict(branch=b["id"], scene=sid, id=mid, name=mname, status=st, phase=ph)


def counts():
    out = {}
    for m in modules():
        c = out.setdefault(m["branch"], {"done": 0, "part": 0, "gap": 0})
        c[m["status"]] += 1
    return out


def scene_count():
    return sum(len(b["scenes"]) for b in BRANCHES if b["kind"] != "cross")


PHASES = [
    dict(n=1, name="答得快", goal="需求人员少找开发",
         gate="试点项目自动答复采纳率达到立项会定的线",
         state="代码已完成，待试点验证"),
    dict(n=2, name="改得稳", goal="不敢改变成敢改、自动改",
         gate="低风险工单无人化后，退回率不高于人工基线",
         state="未开始"),
    dict(n=3, name="翻新看得见", goal="改造进度按业务流可查",
         gate="一个老项目按看板完成一个业务域的翻新",
         state="未开始"),
]

if __name__ == "__main__":
    ms = list(modules())
    tot = {"done": 0, "part": 0, "gap": 0}
    for m in ms:
        tot[m["status"]] += 1
    print(len(ms), tot, scene_count())
    print(counts())
    for p in (1, 2, 3):
        print(p, [m["id"] for m in ms if m["phase"] == p])
