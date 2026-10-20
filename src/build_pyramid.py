import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 「前景」倒金字塔：上宽下窄，从通用的 AI harness 到各领域 harness，再到具体能力。
# 三种状态：已实测（实心蓝）、平台已支持但未实测（蓝框）、规划（灰色虚线）。

DONE, READY, PLAN = "done", "ready", "plan"
CHIP = {DONE: (ACCENT, None, WHITE), READY: (WHITE, ACCENT, ACCENT), PLAN: (WHITE, "A9B0BC", MUTED)}

OPS = [("Java 修改", DONE), (".NET 修改", PLAN), ("Go 修改", PLAN), ("Python 修改", PLAN)]
REF = [("跨语言重写", DONE), ("结构重构", READY), ("依赖升级", READY), ("框架迁移", READY), ("兼容适配", READY)]
MORE_L = ["接口适配", "信创适配", "数据迁移"]
MORE_R = ["资源维护", "测试补全", "安全整改"]

CX = 4.55
Y0, H, G = 1.75, 1.68, 0.09
W_TOP, W_BOT = 7.9, 4.0
TOTAL_H = 3 * H + 2 * G


def width_at(y):
    return W_TOP - (W_TOP - W_BOT) * (y - Y0) / TOTAL_H


def edges(y):
    w = width_at(y)
    return CX - w / 2, CX + w / 2


def trap(s, y, h, f0=0.0, f1=1.0, fill=ACCENT, ln=None, dash=False, gap=0.045):
    """倒梯形一层；f0/f1 按比例截取这一层的一段，段与段之间留一道缝。"""
    (lt, rt), (lb, rb) = edges(y), edges(y + h)
    at = lambda f, l, r: l + (r - l) * f
    g0 = gap if f0 > 0 else 0
    g1 = gap if f1 < 1 else 0
    pts = [(at(f0, lt, rt) + g0, y), (at(f1, lt, rt) - g1, y),
           (at(f1, lb, rb) - g1, y + h), (at(f0, lb, rb) + g0, y + h)]
    sh = poly(s, pts, fill=fill, line=ln, lw=1.0)
    if dash:
        style_shape(sh, fill, ln, 1.0, True)
    return pts


def mid_x(y, f):
    l, r = edges(y)
    return l + (r - l) * f


def chip(s, x, y, w, name, st):
    fill, ln, tc = CHIP[st]
    box(s, x, y, w, 0.4, fill, ln, 0.9, dash=st == PLAN, shape="round", radius=0.3)
    text(s, x, y, w, 0.4, name, size=11, color=tc, bold=st != PLAN, align="c", anchor="m")


# 深色底的倒金字塔：底座最亮，往上颜色渐浅，表示从平台一层层长出去。每格只放一项。
BG = "0E1A2E"
C_BASE, C_MID, C_TOP = "3D6FE0", "1F3D7A", "182B4D"
T_MID, T_TOP = WHITE, "C9D6F2"
C_GREY, T_GREY = "C3C8D1", "3A4456"   # 浅灰：还没做完的 harness

HARNESS = ["运维", "重构", "接口适配", "资源维护"]
ABILITY = ["Java\n.NET", "Go\nPython", "跨语言\n重写", "框架\n迁移",
           "新旧系统\n对接", "协议\n转换", "环境\n配置", "服务\n巡检"]


def cells(s, y, labels, fill, color, size, bold=False, gap=0.05, grey=()):
    n = len(labels)
    for i, nm in enumerate(labels):
        f0, f1 = i / n, (i + 1) / n
        g = i in grey
        trap(s, y, H, f0, f1, fill=C_GREY if g else fill, gap=gap)
        x = mid_x(y + H / 2, (f0 + f1) / 2)
        w = width_at(y + H) / n - 0.15
        text(s, x - w / 2, y, w, H, nm, size=size, color=T_GREY if g else color, bold=bold, align="c", anchor="m")


def pyramid_slide(s):
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(BG)
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, "前景", size=11, color="7FA6FF", bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, "Road Map", size=26, color=WHITE, bold=True)

    yt = Y0
    ym = Y0 + H + G
    yb = ym + H + G
    cells(s, yt, [a.split("\n") for a in ABILITY], C_TOP, T_TOP, 10.5)
    cells(s, ym, [[h, "harness"] for h in HARNESS], C_MID, T_MID, 13, bold=True, grey=(2, 3))
    trap(s, yb, H, fill=C_BASE)
    text(s, CX - 2, yb + 0.35, 4, 0.45, "企业 AI 平台", size=20, color=WHITE, bold=True, align="c")
    text(s, CX - 2, yb + 0.85, 4, 0.5, ["代码知识库 · 智能体编排", "自动检查 · 人工验收"], size=10.5, color="DCE6FF", align="c")

    # 右侧：分三个阶段的路线图
    STAGES = [("现在", "平台和两个 harness 已经能用", ["企业 AI 平台：代码知识库、智能体编排、自动检查、人工验收",
                                                  "运维：Java 缺陷修复，在 40 个开源 issue 上实测",
                                                  "重构：.NET 改写 Java，在 RealWorld 上实测"]),
              ("下一步", "把已有的两个 harness 做扎实", ["运维补上 .NET、Go、Python 代码修改",
                                                    "重构补跑接口测试，实测框架迁移和依赖升级",
                                                    "在一个客户项目上试点，拿到提效基线"]),
              ("之后", "在同一个平台上长出新的 harness", ["接口适配：新旧系统对接、协议转换",
                                                     "资源维护：环境配置、服务巡检"])]
    RX = 8.7
    line(s, RX + 0.09, 2.15, RX + 0.09, 5.75, "2C3B57", 1.5)
    for i, ((when, head_, items), ry) in enumerate(zip(STAGES, [1.95, 4.0, 5.55])):
        col = "7FA6FF" if i == 0 else ("4F6FB8" if i == 1 else "3A4A66")
        box(s, RX, ry + 0.1, 0.18, 0.18, col, None, shape="oval")
        text(s, RX + 0.4, ry, 3.65, 0.35, [[(when + "  ", {"bold": True, "color": WHITE, "size": 15}),
                                          (head_, {"color": "B7C2D6", "size": 11})]], anchor="m")
        text(s, RX + 0.4, ry + 0.42, 3.65, 1.5, ["· " + t for t in items], size=10.5, color="9FB0CC", lsp=1.3,
             space_after=2)

    notes(s, "这一页是路线图，右侧三个阶段里“下一步”和“之后”是计划，没有时间承诺。从下往上看：最下面是企业 AI 平台，往上是各领域 harness，最上面每格是一项具体能力，每个 harness 上方两格。"
             "现状要讲清楚：运维和重构已经在做，接口适配和资源维护还没开发。"
             "实测过的是 Java 代码修改（JeecgBoot 40 张开源工单）和跨语言重写（.NET 版 RealWorld 改写为 Java，"
             "8 部分里 7 部分编译通过，19 个接口做出 18 个）；框架迁移平台里能建计划，还没有真实项目跑过；"
             ".NET、Go、Python 修改，以及接口适配、资源维护下面的四项，都还没开发。")


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "pyramid.pptx"
    prs = new_deck()
    pyramid_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
