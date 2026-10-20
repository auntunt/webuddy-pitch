import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# “应用场景”页的四个版本，供挑选后并入产品介绍 PPT。
OUT = sys.argv[1] if len(sys.argv) > 1 else "scenarios.pptx"
prs = new_deck()

NOW, VAL, OUTL = "now", "val", "out"
SC = {  # 名称: (成熟度, 一句话)
    "需求答复": (NOW, "群里答能不能做"), "缺陷修复": (NOW, "定位、修改、交人验收"),
    "功能扩展": (NOW, "先出方案再实现"), "告警开单": (NOW, "报错日志对到代码"),
    "分批重构": (NOW, "按业务域分批升级"), "提效报告": (NOW, "从工单流程自动统计"),
    "跨语言重写": (VAL, ".NET 改写为 Java"), "历史工单回放": (VAL, "评测找全率"),
    "外部工单导入": (VAL, "Jira、禅道同步"),
    "工单获取": (OUTL, "群聊、邮件整理成单"), "会议纪要": (OUTL, "会议记录转成待办"),
    "报价评估": (OUTL, "按影响范围估工作量"), "回归测试推荐": (OUTL, "按影响范围选用例"),
    "项目交接": (OUTL, "体检报告、新人上手"), "功能模拟": (OUTL, "需求未定先出样子"),
}
LEVELS = [(NOW, "已可用"), (VAL, "验证中"), (OUTL, "展望")]
STYLE = {NOW: (ACCENT, None, WHITE, "DCE4F5"), VAL: (ACCENT_T, None, ACCENT, BODY),
         OUTL: (WHITE, "A9B0BC", MUTED, FAINT)}
STEPS = ["任务受理", "问题定位", "方案规划", "开发执行", "验证审查", "人工验收"]
KB = ["业务地图", "代码证据", "项目知识页", "本地离线"]


def S():
    return blank(prs)


def head(s, sec, t):
    text(s, 0.6, 0.45, 8, 0.3, sec, size=11, color=MUTED, bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, t, size=26, color=INK, bold=True)


def legend(s, y=1.5):
    x = 12.73
    for lv, nm in reversed(LEVELS):
        fill, ln, _, _ = STYLE[lv]
        text(s, x - 0.62, y - 0.03, 0.62, 0.25, nm, size=10, color=MUTED)
        box(s, x - 0.9, y + 0.02, 0.22, 0.16, fill, ln or (None if lv != VAL else None), 0.75,
            dash=lv == OUTL, shape="round", radius=0.2)
        x -= 1.15


def card(s, x, y, w, h, name, size=12, sub=True):
    lv, desc = SC[name]
    fill, ln, tc, dc = STYLE[lv]
    box(s, x, y, w, h, fill, ln, 0.9, dash=lv == OUTL, shape="round", radius=0.12)
    if sub:
        ty = y + max(0.0, (h - 0.6) / 2)
        text(s, x, ty, w, 0.3, name, size=size, color=tc, bold=True, align="c")
        text(s, x, ty + 0.29, w, 0.28, desc, size=size - 3, color=dc, align="c")
    else:
        text(s, x, y, w, h, name, size=size, color=tc, bold=True, align="c", anchor="m")


def base_bars(s, x, y, w, h1=0.62, h2=0.62, gap=0.1, label=True):
    box(s, x, y, w, h1, ACCENT, None, shape="round", radius=0.15)
    text(s, x + 0.2, y, 2.2, h1, "编码智能体编排", size=12, color=WHITE, bold=True, anchor="m")
    text(s, x + 2.4, y, w - 2.6, h1, "   ·   ".join(STEPS), size=10.5, color=ACCENT_T, anchor="m")
    y2 = y + h1 + gap
    box(s, x, y2, w, h2, ACCENT_T, None, shape="round", radius=0.15)
    text(s, x + 0.2, y2, 2.2, h2, "代码知识库", size=12, color=ACCENT, bold=True, anchor="m")
    text(s, x + 2.4, y2, w - 2.6, h2, "   ·   ".join(KB), size=10.5, color=BODY, anchor="m")


# ---------------------------------------------------------------- 版本 A：三层延伸
s = S()
head(s, "应用场景 · 版本 A", "同一套智能体和知识库，从维保延伸到交付前后的更多环节")
legend(s)
LX, LW, CX, CW = 0.6, 1.5, 2.3, 10.43
label_box(s, LX, 1.95, LW, 3.0, "应用场景", fill=ACCENT_T, size=13, color=ACCENT, bold=True, shape="round")
label_box(s, LX, 5.35, LW, 1.34, "共用底座", fill=ACCENT_T, size=13, color=ACCENT, bold=True, shape="round")
gw = (CW - 0.3) / 3
groups = [(NOW, "已可用"), (VAL, "验证中"), (OUTL, "展望")]
for gi, (lv, nm) in enumerate(groups):
    gx = CX + gi * (gw + 0.15)
    names = [k for k, v in SC.items() if v[0] == lv]
    box(s, gx, 1.95, gw, 3.0, WHITE if lv != OUTL else PANEL, ACCENT_M if lv != OUTL else RULE, 0.9,
        dash=lv == OUTL, shape="round", radius=0.05)
    text(s, gx + 0.15, 2.03, gw - 0.3, 0.3, nm, size=11, color=ACCENT if lv != OUTL else MUTED, bold=True)
    cw, ch = (gw - 0.36) / 2, 0.74
    for j, n in enumerate(names):
        cx = gx + 0.12 + (j % 2) * (cw + 0.12)
        cy = 2.4 + (j // 2) * (ch + 0.1)
        card(s, cx, cy, cw, ch, n)
    line(s, gx + gw / 2, 4.95, gx + gw / 2, 5.15, ACCENT_M, 1.0)
line(s, CX + gw / 2, 5.15, CX + 2 * (gw + 0.15) + gw / 2, 5.15, ACCENT_M, 1.0)
line(s, CX + CW / 2, 5.15, CX + CW / 2, 5.35, ACCENT, 1.0, arrow=True)
base_bars(s, CX, 5.35, CW)

# ---------------------------------------------------------------- 版本 B：以知识库为中心
s = S()
head(s, "应用场景 · 版本 B", "以代码知识库为中心，15 个场景共用同一份项目理解")
legend(s)
BX0, BX1, BY0, BY1 = 4.75, 8.58, 3.35, 6.45
box(s, BX0, BY0, BX1 - BX0, BY1 - BY0, ACCENT_T, None, shape="round", radius=0.08)
box(s, BX0 + 0.25, BY0 + 0.25, BX1 - BX0 - 0.5, 1.45, ACCENT, None, shape="round", radius=0.1)
text(s, BX0 + 0.25, BY0 + 0.38, BX1 - BX0 - 0.5, 0.4, "编码智能体编排", size=15, color=WHITE, bold=True, align="c")
text(s, BX0 + 0.35, BY0 + 0.85, BX1 - BX0 - 0.7, 0.7,
     ["任务受理 · 问题定位 · 方案规划", "开发执行 · 验证审查 · 人工验收"], size=10, color=ACCENT_T, align="c", lsp=1.3)
text(s, BX0, BY0 + 1.95, BX1 - BX0, 0.4, "代码知识库", size=15, color=ACCENT, bold=True, align="c")
text(s, BX0, BY0 + 2.4, BX1 - BX0, 0.5, "业务地图 · 代码证据 · 项目知识页 · 本地离线", size=10, color=BODY, align="c")
now = [k for k, v in SC.items() if v[0] == NOW]
val = [k for k, v in SC.items() if v[0] == VAL]
out = [k for k, v in SC.items() if v[0] == OUTL]
cw, ch = 2.35, 0.66
for i, n in enumerate(now):
    y = 1.95 + i * 0.79
    card(s, 0.6, y, cw, ch, n)
    line(s, 0.6 + cw, y + ch / 2, BX0, BY0 + 0.6 + i * 0.4, ACCENT_M, 0.75)
for i, n in enumerate(out):
    y = 1.95 + i * 0.79
    card(s, 12.73 - cw, y, cw, ch, n)
    line(s, 12.73 - cw, y + ch / 2, BX1, BY0 + 0.6 + i * 0.4, RULE, 0.75, dash=True)
for i, n in enumerate(val):
    tw = 2.1
    x = (BX0 + BX1) / 2 - (3 * tw + 0.3) / 2 + i * (tw + 0.15)
    cw_ = cw
    cw = tw
    card(s, x, 2.15, cw, ch, n)
    line(s, x + cw / 2, 2.15 + ch, min(max(x + cw / 2, BX0 + 0.4), BX1 - 0.4), BY0, ACCENT_M, 0.75)
    cw = cw_

# ---------------------------------------------------------------- 版本 C：老系统生命周期
s = S()
head(s, "应用场景 · 版本 C", "从售前到交接，老系统的每个阶段都有对应的场景")
legend(s)
stages = [("售前", ["需求答复", "报价评估"]), ("需求", ["工单获取", "会议纪要", "功能模拟"]),
          ("开发", ["功能扩展"]), ("测试", ["历史工单回放", "回归测试推荐"]),
          ("运维", ["缺陷修复", "告警开单", "外部工单导入", "提效报告"]),
          ("重构升级", ["分批重构", "跨语言重写"]), ("交接", ["项目交接"])]
n = len(stages)
pitch = 12.13 / n
sy = 5.0
for i, (st, items) in enumerate(stages):
    x = 0.6 + i * pitch
    w = pitch - 0.12
    label_box(s, x, sy, w, 0.45, st, fill=INK, size=12, color=WHITE, bold=True, shape="round")
    if i < n - 1:
        line(s, x + w + 0.01, sy + 0.225, x + pitch - 0.01, sy + 0.225, MUTED, 1.0, arrow=True)
    for j, it in enumerate(items):
        card(s, x, sy - 0.12 - (j + 1) * 0.64, w, 0.56, it, size=11)
base_bars(s, 0.6, 5.7, 12.13, h1=0.55, h2=0.55)

# ---------------------------------------------------------------- 版本 D：角色 × 成熟度
s = S()
head(s, "应用场景 · 版本 D", "每类角色现在能用哪些场景，接下来还能用哪些")
roles = [("售前与实施", ["需求答复"], [], ["报价评估", "会议纪要", "工单获取"]),
         ("开发", ["缺陷修复", "功能扩展", "分批重构"], ["跨语言重写"], ["功能模拟"]),
         ("测试", [], ["历史工单回放"], ["回归测试推荐"]),
         ("运维与驻场", ["告警开单"], ["外部工单导入"], []),
         ("项目经理与管理层", ["提效报告"], [], ["项目交接"])]
cols = [(2.1, "角色"), (4.05, "已可用"), (1.55, "验证中"), (4.43, "展望")]
x0, y0, rh = 0.6, 1.95, 0.8
x = x0
for wdt, nm in cols:
    text(s, x + 0.1, y0, wdt - 0.2, 0.35, nm, size=12, color=INK if nm == "角色" else ACCENT, bold=True)
    x += wdt
line(s, x0, y0 + 0.42, 12.73, y0 + 0.42, INK, 1.0)
for r, (role, *cells) in enumerate(roles):
    y = y0 + 0.55 + r * rh
    text(s, x0 + 0.1, y, 2.1, rh - 0.1, role, size=13, color=INK, bold=True, anchor="m")
    cx = x0 + cols[0][0]
    for ci, items in enumerate(cells):
        for j, it in enumerate(items):
            card(s, cx + 0.1 + j * 1.3, y + 0.08, 1.2, rh - 0.26, it, size=11, sub=False)
        cx += cols[ci + 1][0]
    line(s, x0, y + rh - 0.05, 12.73, y + rh - 0.05, RULE, 0.5)

strip_styles(prs)
prs.save(OUT)
print("saved", OUT)
