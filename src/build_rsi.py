import sys, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *
from pptx.util import Inches
from pptx.oxml.ns import qn
from lxml import etree

# 「Webuddy 的 RSI 自进化」：一个飞轮。交付 → 验收 → 教训和用例 → 回放打分再上线 → 相似工单少走弯路 → 人手省下来接更多单 → 更多交付。
# 事实与原“越用越准”页一致：40 个评测用例、13 条教训、分数不降才上线、构建不过最多自改 3 轮。
BG = "0E1A2E"
CX, CY, R = 4.4, 4.42, 1.85
NODES = [  # 角度, 名称, 说明, 标签位置
    (-120, "交付工单", "智能体改好代码，构建不过自己重改", "top"),
    (-60, "人工验收", "通过或打回，打回必须写明原因", "top"),
    (0, "记成教训和用例", "打回原因记成教训，典型工单收进评测集", "right"),
    (60, "回放打分再上线", "先拿评测用例回放打分，分数不降才上线", "bottom"),
    (120, "相似工单少走弯路", "教训自动带进相似工单的提示词", "bottom"),
    (180, "人手省下来", "目标是每张单要人改的更少，同样人手接更多项目", "left"),
]


def arc(s, r, a0, a1, color, w, arrow=True):
    pts = []
    n = max(8, int(abs(a1 - a0) / 4))
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((CX + r * math.cos(a), CY + r * math.sin(a)))
    ff = s.shapes.build_freeform(Inches(pts[0][0]), Inches(pts[0][1]), scale=1.0)
    ff.add_line_segments([(Inches(x), Inches(y)) for x, y in pts[1:]], close=False)
    sh = ff.convert_to_shape()
    sh.shadow.inherit = False
    sh.fill.background()
    sh.line.color.rgb = rgb(color)
    sh.line.width = Pt(w)
    if arrow:
        ln = sh.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle"); tail.set("w", "med"); tail.set("len", "med")
    return sh


def rsi_slide(s):
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(BG)
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, "持续改进", size=11, color="7FA6FF", bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, "Webuddy 的 RSI 自进化", size=30, color=WHITE, bold=True)
    text(s, 0.6, 1.45, 12.1, 0.35, "RSI：Recursive Self-Improvement，递归式自我改进。每交付一张单，飞轮就转一圈，下一圈转得更顺。",
         size=12.5, color="9FB0CC")

    # 飞轮：一圈粗轮缘，上面是首尾相接、顺时针的箭头弧
    arc(s, R, 0, 359.9, "17294D", 30, arrow=False)
    gap = math.degrees(0.3 / R)
    angs = [a for a, *_ in NODES]
    for i, a in enumerate(angs):
        b = angs[(i + 1) % len(angs)] + (360 if i == len(angs) - 1 else 0)
        arc(s, R, a + gap, b - gap, "8FB3FF", 2.75)
    # 内圈两段细弧，表示在转
    arc(s, 1.3, -160, -25, "3559C4", 1.25)
    arc(s, 1.3, 20, 155, "3559C4", 1.25)
    box(s, CX - 0.85, CY - 0.85, 1.7, 1.7, "1F4AA8", "8FB3FF", 1.5, shape="oval")
    text(s, CX - 0.85, CY - 0.4, 1.7, 0.8, [[("Webuddy", {"bold": True, "size": 15, "color": WHITE})],
                                            [("RSI 飞轮", {"size": 12, "color": "C9D6F2"})]],
         align="c", anchor="m", lsp=1.2)

    for a, nm, d, pos in NODES:
        nx = CX + R * math.cos(math.radians(a))
        ny = CY + R * math.sin(math.radians(a))
        box(s, nx - 0.17, ny - 0.17, 0.34, 0.34, "8FB3FF", BG, 2.5, shape="oval")
        paras = [[(nm, {"bold": True, "color": WHITE, "size": 14.5})], [(d, {"color": "B7C2D6", "size": 11})]]
        if pos == "top":
            if a < -90:
                text(s, nx - 2.7, ny - 0.95, 2.9, 0.7, paras, align="r", anchor="b", lsp=1.25)
            else:
                text(s, nx - 0.2, ny - 0.95, 2.9, 0.7, paras, align="l", anchor="b", lsp=1.25)
        elif pos == "bottom":
            if a > 90:
                text(s, nx - 2.7, ny + 0.27, 2.9, 0.7, paras, align="r", anchor="t", lsp=1.25)
            else:
                text(s, nx - 0.2, ny + 0.27, 2.9, 0.7, paras, align="l", anchor="t", lsp=1.25)
        elif pos == "right":
            text(s, nx + 0.32, ny - 0.4, 2.0, 0.8, paras, align="l", anchor="m", lsp=1.25)
        else:
            text(s, nx - 2.27, ny - 0.4, 1.95, 0.8, paras, align="r", anchor="m", lsp=1.25)

    # 右侧：每转一圈留下的东西
    x0 = 9.0
    text(s, x0, 2.15, 3.8, 0.4, "飞轮每转一圈，都会留下", size=13, color="9FB0CC")
    y = 2.7
    for big, unit, d in [("40", "个评测用例", "改提示词、换模型之前先回放打分"),
                         ("13", "条教训", "来自验收打回和对照官方修复的复盘"),
                         ("1", "条上线规矩", "回放分数不降，新版本才上线")]:
        line(s, x0, y, 12.73, y, "2C3B57", 0.75)
        text(s, x0, y + 0.12, 3.8, 0.6, [[(big, {"bold": True, "size": 30, "color": WHITE}),
                                         ("  " + unit, {"bold": True, "size": 14, "color": WHITE})]], anchor="m")
        text(s, x0, y + 0.74, 3.8, 0.35, d, size=11.5, color="B7C2D6")
        y += 1.3
    line(s, x0, y, 12.73, y, "2C3B57", 0.75)
    notes(s, "RSI 在这里指工作流层面的自我改进：验收结论变成教训和评测用例，影响之后的提示词和上线决策；不是训练或修改模型本身。"
             "教训来自对照官方修复的复盘。回放时每张单都排除它自己的教训，找全率还要等回放结果。"
             "“人手省下来、接更多项目”是飞轮要达到的目标，目前还没有长期数据能证明。")


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "rsi.pptx"
    prs = new_deck()
    rsi_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
