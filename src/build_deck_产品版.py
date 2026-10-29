import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *
from PIL import Image

# 面向甲方的产品介绍版：先看产品干活，再看实测，最后讲原理。产品名 Webuddy。
OUT = sys.argv[1] if len(sys.argv) > 1 else "deck.pptx"
NAME = "Webuddy"
TOTAL = 21
prs = new_deck()

NAVY = "0E1A2E"      # 深色页底
NAVY_2 = "1A2942"
SKY = "7FA6FF"       # 深色页上的强调
IMG = os.path.join(HERE, "img")

SERVICES = [
    ("需求答复", "能不能做 · 多久能做", "一期已完成，待试点"),
    ("日常维护", "故障定位 · 缺陷修复", "可提供，人审后采纳"),
    ("功能扩展", "功能开发 · 接口集成", "可提供，人审后采纳"),
    ("系统重构", "业务域拆分 · 分批推进", "可提供，按业务域分批推进"),
    ("系统升级", "依赖升级 · 信创适配", "可提供，按业务域分批推进"),
]
DISPATCH = ["任务分类", "影响评估", "能力调配", "人工确认"]
AGENTS = [
    ("任务受理", "关联业务与代码", "工单、涉及的业务域", "需求人员确认范围"),
    ("问题定位", "找到相关代码位置", "可行性结论、代码位置与依据", "—"),
    ("方案规划", "拆分改动与步骤", "变更方案、影响清单", "开发审方案"),
    ("开发执行", "按文件分工改代码", "独立分支上的改动", "—"),
    ("验证审查", "构建测试与诊断", "构建、测试、诊断结果", "不通过自动重改，最多 3 轮"),
    ("人工验收", "通过交付 · 退回重改", "改动说明、验收要点", "人验收，主干由人合入"),
]
KNOW = [
    ("业务地图", "业务域 · 业务流 · 数据表"),
    ("代码证据", "入口 · 调用链 · 文件行号"),
    ("项目知识页", "人工确认 · 持续更新"),
    ("本地离线", "代码不出内网 · 支持国产模型"),
]
FUTURE = ["工单获取", "会议纪要", "报价评估"]



def S(dark=False):
    s = blank(prs)
    if dark:
        s.background.fill.fore_color.rgb = rgb(NAVY)
    return s


def pic(s, name, x, y, w=None, h=None, frame=True):
    path = os.path.join(IMG, name + ".png")
    iw, ih = Image.open(path).size
    if w is None:
        w = h * iw / ih
    h = w * ih / iw
    if frame:
        box(s, x - 0.06, y - 0.06, w + 0.12, h + 0.12, "EEF1F6", "D5DBE6", 0.75, shape="round", radius=0.02)
    s.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    return w, h


def pin(s, x, y, n, color=ACCENT):
    label_box(s, x - 0.17, y - 0.17, 0.34, 0.34, str(n), fill=color, size=11, color=WHITE, bold=True, shape="oval")


def kicker(s, t, dark=False):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, t, size=11, color=SKY if dark else ACCENT, bold=True)


def title(s, t, dark=False, y=0.78, size=26):
    text(s, 0.6, y, 12.1, 0.9, t, size=size, color=WHITE if dark else INK, bold=True, lsp=1.1)


def pnum(s, n, dark=False):
    text(s, 11.9, 7.0, 0.83, 0.3, "%02d" % n, size=9, color="5C6B84" if dark else FAINT, align="r")


def note(s, t, dark=False):
    # 页面底部不放补充说明；来源和注意事项放进演讲者备注
    notes(s, t)


def point(s, x, y, w, n, head, body, dark=False):
    pin(s, x + 0.17, y + 0.17, n)
    text(s, x + 0.5, y, w - 0.5, 0.35, head, size=14, color=WHITE if dark else INK, bold=True)
    text(s, x + 0.5, y + 0.38, w - 0.5, 0.8, body, size=11, color="B7C2D6" if dark else BODY, lsp=1.3)


def callout(s, ix, iy, iw, ih, fb, label, lx, lw=3.6, side="r", sub=None, via=None):
    """在截图上框出 fb=(fx0, fy0, fx1, fy1) 的区域，用一条水平线引到 lx 处的标签。"""
    x0, y0 = ix + iw * fb[0], iy + ih * fb[1]
    x1, y1 = ix + iw * fb[2], iy + ih * fb[3]
    box(s, x0, y0, x1 - x0, y1 - y0, None, ACCENT, 1.5, shape="round", radius=0.08)
    cy = (y0 + y1) / 2
    if via:
        # 折线引出：从框的上/下边中点走到 y=via[1]，或在框内 y=via[1] 处水平引出
        kind, vy = via
        if kind == "at":
            line(s, x1, vy, lx - 0.08, vy, ACCENT, 1.0)
        else:
            mx = (x0 + x1) / 2
            line(s, mx, y0 if kind == "up" else y1, mx, vy, ACCENT, 1.0)
            line(s, mx, vy, lx - 0.08, vy, ACCENT, 1.0)
        paras = [[(label, {"bold": True, "color": INK})]]
        if sub:
            paras.append([(sub, {"color": MUTED, "size": 11})])
        text(s, lx, vy - 0.17, lw, 0.9, paras, size=13, align="l", lsp=1.25)
        return
    if side == "r":
        line(s, x1, cy, lx - 0.08, cy, ACCENT, 1.0)
        tx, al = lx, "l"
    else:
        line(s, lx + 0.08, cy, x0, cy, ACCENT, 1.0)
        tx, al = lx - lw, "r"
    paras = [[(label, {"bold": True, "color": INK})]]
    if sub:
        paras.append([(sub, {"color": MUTED, "size": 11})])
    text(s, tx, cy - 0.17, lw, 0.9, paras, size=13, align=al, lsp=1.25)


def F(crop, b):
    """原截图上的像素框 b 换算成裁剪图里的比例。crop 是裁剪框。"""
    cx0, cy0, cx1, cy1 = crop
    w, h = cx1 - cx0, cy1 - cy0
    return ((b[0] - cx0) / w, (b[1] - cy0) / h, (b[2] - cx0) / w, (b[3] - cy0) / h)


# 截图裁剪框（原图 1600×1000，见 截图-新/）
CROP = {"board": (44, 145, 1556, 995), "detail": (44, 378, 836, 820), "assistant": (1217, 160, 1600, 740),
        "plan": (44, 375, 1556, 1235), "report": (44, 150, 1556, 905),
        "rplan": (44, 140, 1556, 950), "rlist": (44, 140, 1556, 630), "rdetail": (44, 280, 1556, 945)}


def section(s, t, dark=False):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, t, size=11, color=SKY if dark else MUTED, bold=True)


# ---------------------------------------------------------------- 1 封面
s = S()
# 右侧一整块蓝底，两张真实界面截图压在色块边缘、出血到页面外
box(s, 8.1, 0, 13.333 - 8.1, 7.5, ACCENT, None)
for name, x, y, w in [("plan", 6.55, 1.0, 7.6), ("detail", 5.75, 4.4, 4.3)]:
    path = os.path.join(IMG, name + ".png")
    iw, ih = Image.open(path).size
    p_ = s.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(w * ih / iw))
    p_.line.color.rgb = rgb("C9D2E3")
    p_.line.width = Pt(0.75)
pass  # 去掉小字：text(s, 0.8, 2.15, 4.8, 0.35, "产品介绍", size=13, color=ACCENT, bold=True)
text(s, 0.8, 2.55, 5.0, 1.0, NAME, size=48, color=INK, bold=True)
text(s, 0.8, 3.75, 4.9, 0.9, "老系统维保：需求答复、缺陷修复、分批重构", size=17, color=BODY, lsp=1.3)
line(s, 0.8, 4.5, 1.4, 4.5, ACCENT, 2.25)
text(s, 0.8, 6.55, 4, 0.3, "2026 年 10 月", size=10, color=MUTED)

# ---------------------------------------------------------------- 2 问题（研究数据 + 一线原话）
s = S()
section(s, "问题")
title(s, "老系统的知识只在少数人脑子里，开发一半以上的时间在读代码")
# 上：一个开发的工作时间，一根条
text(s, 0.6, 1.9, 6, 0.3, "一个开发的工作时间里", size=12, color=MUTED)
BX, BW, BY, BH = 0.6, 12.13, 2.25, 0.58
box(s, BX, BY, BW, BH, PANEL, None)
box(s, BX, BY, BW * 0.58, BH, ACCENT, None)
text(s, BX + 0.2, BY, 5, BH, [[("58%", {"bold": True, "size": 20}), ("  在读懂代码", {"size": 14})]],
     color=WHITE, anchor="m")
text(s, BX + BW * 0.58 + 0.2, BY, 4.5, BH, "其余 42%", size=12, color=MUTED, anchor="m")
text(s, 0.6, BY + BH + 0.1, 8, 0.3, "78 名开发、3,148 个工时的现场观测", size=10, color=FAINT)

# 下左：研究数据，每个数字配一个小图形；下右：一线原话
LX, GW, LTX = 0.6, 1.9, 2.8
RX, RW = 8.15, 4.58
HY = 3.6
text(s, LX, HY, 4, 0.3, "研究数据", size=11, color=MUTED, bold=True)
text(s, RX, HY, 4, 0.3, "一线原话", size=11, color=MUTED, bold=True)
line(s, LX, HY + 0.38, LX + 7.1, HY + 0.38, INK, 1.0)
line(s, RX, HY + 0.38, RX + RW, HY + 0.38, INK, 1.0)
RY, RS = HY + 0.55, 0.95


def mini_bar(x, y, frac):
    box(s, x, y, GW, 0.22, PANEL, None)
    box(s, x, y, GW * frac, 0.22, ACCENT, None)


stats = [("47%", " 的开发每天至少花 30 分钟回答别人的问题，七成半重复回答过同一个问题"),
         ("23 分钟", "：被打断一次，平均要这么久才回到原来的任务"),
         ("65%", " 的热门开源项目，走掉 1 到 2 个人就会陷入危机")]
for i, (v, t) in enumerate(stats):
    y = RY + i * RS
    gy = y + 0.22
    if i == 1:
        box(s, LX, gy, GW * 0.28, 0.22, INK, None)
        box(s, LX + GW * 0.28, gy, GW * 0.44, 0.22, GAP_T, None)
        box(s, LX + GW * 0.72, gy, GW * 0.28, 0.22, INK, None)
        line(s, LX + GW * 0.28, gy - 0.12, LX + GW * 0.28, gy + 0.34, GAP, 1.25)
    else:
        mini_bar(LX, gy, 0.47 if i == 0 else 0.65)
    text(s, LTX, y, 4.9, 0.75, [[(v, {"bold": True, "color": INK}), (t, {})]], size=12.5, color=BODY, lsp=1.4, anchor="m")
    if i < 2:
        line(s, LX, y + RS - 0.08, LX + 7.1, y + RS - 0.08, RULE, 0.75)

quotes = ["问报表字段怎么算，经理只说“自己看代码”。",
          "花两周修好的金额精度 bug，被重构“简化”回去，单测全过。",
          "售前判断不了方案能不能落地，只能去问技术，否则容易乱报价。"]
for i, q in enumerate(quotes):
    y = RY + i * RS
    text(s, RX, y, RW, 0.75, q, size=13.5, color=INK, lsp=1.4, anchor="m")
    if i < 2:
        line(s, RX, y + RS - 0.08, RX + RW, y + RS - 0.08, RULE, 0.75)
notes(s, "研究数据来源：Xia 等，ICSE 2018（58%）；Stack Overflow 开发者调查 2024（47%）；"
         "Gloria Mark，经 Fast Company 报道（23 分钟）；arXiv 1604.06766（65%）。"
         "一线原话从 V2EX 上 36 条公开讨论中选取，均为转述，分别对应：知识只在人脑子里、不敢改、承诺先于评估。")
pnum(s, 2)

# ---------------------------------------------------------------- 总述：运维和重构两套流程
from build_flows import flows_slide
s = S()
flows_slide(s)
pnum(s, 3)

# ---------------------------------------------------------------- 4 工单看板
s = S()
section(s, "运维 · 工单看板")
title(s, "看板上能看到每张工单停在哪一步、在等谁处理")
IX, IY, IW = 0.6, 1.85, 7.4
_, IH = pic(s, "board", IX, IY, w=IW, frame=False)
c = CROP["board"]
callout(s, IX, IY, IW, IH, F(c, (52, 152, 1548, 296)), "四项比率按项目实时计算", 8.6, lw=4.13,
        sub="闭环完成率、分析覆盖率、改动采纳率、知识库覆盖率")
callout(s, IX, IY, IW, IH, F(c, (930, 755, 1030, 880)), "待确认：技术负责人确认方案", 8.6)
callout(s, IX, IY, IW, IH, F(c, (570, 755, 670, 880)), "待验证：验收人验收", 2.75, lw=2.0, side="l")
text(s, 8.6, 3.5, 4.1, 1.2, "其余四个状态由智能体推进：分析定位、在独立分支上修改、构建与测试、验收通过后归档。",
     size=12, color=BODY, lsp=1.4)
note(s, "截图为示例项目数据：40 张开源工单已由智能体改完，其中 35 张在等人工验收，所以闭环完成率还是 0%。")
tracker(s, 0, 0)
pnum(s, 4)

# ---------------------------------------------------------------- 5 需求答复
s = S()
section(s, "运维 · 需求答复")
title(s, "实施人员问的需求问题，当场就能拿到带代码位置的答复")
box(s, 0.6, 1.95, 5.0, 1.45, PANEL, None, shape="round", radius=0.08)
text(s, 0.85, 2.05, 4.6, 0.3, "实施人员提问", size=11, color=MUTED)
text(s, 0.85, 2.38, 4.6, 0.9, "“用户管理能不能按部门批量导出用户？现在系统做到哪一步了？”", size=15, color=INK,
     bold=True, lsp=1.3)
text(s, 0.6, 3.75, 4.9, 1.6, "答不了的问题转给对应的开发；开发的答复写回知识库，同类问题下次直接答。",
     size=13, color=BODY, lsp=1.45)
IY, IH = 1.9, 4.85
c = CROP["assistant"]
IW = IH * (c[2] - c[0]) / (c[3] - c[1])
IX = 12.73 - IW
pic(s, "assistant", IX, IY, w=IW, frame=False)
callout(s, IX, IY, IW, IH, F(c, (1228, 288, 1592, 432)), "结论写明边界", IX - 0.3, lw=3.4, side="l",
        sub="只给出相关位置，不替人判断能不能做")
callout(s, IX, IY, IW, IH, F(c, (1266, 462, 1588, 736)), "依据列出接口、读写的表和代码文件", IX - 0.3, lw=3.4,
        side="l")
tracker(s, 0, 1)
pnum(s, 5)

# ---------------------------------------------------------------- 6 缺陷修复
s = S()
section(s, "运维 · 缺陷修复")
title(s, "缺陷由智能体定位和修改，人只确认方案、做验收")
flow = [("受理", False), ("定位", False), ("确认方案", True), ("修改", False), ("验证", False), ("验收", True)]
fx, fw, fg = 0.6, 1.88, 0.17
for i, (t, human) in enumerate(flow):
    x = fx + i * (fw + fg)
    label_box(s, x, 1.85, fw, 0.55, t, fill=ACCENT if human else PANEL, size=14,
              color=WHITE if human else INK, bold=True, shape="round")
    if i < 5:
        line(s, x + fw + 0.02, 2.125, x + fw + fg - 0.02, 2.125, MUTED, 1.0, arrow=True)
IX, IY, IH = 0.6, 2.85, 3.6
c = CROP["detail"]
IW = IH * (c[2] - c[0]) / (c[3] - c[1])
pic(s, "detail", IX, IY, w=IW, frame=False)
LX = IX + IW + 0.55
callout(s, IX, IY, IW, IH, F(c, (108, 424, 824, 516)), "根因分开标出【核实】和【推断】", LX, lw=12.73 - LX,
        sub="核实：读代码确认过；推断：模型的判断")
callout(s, IX, IY, IW, IH, F(c, (112, 572, 464, 602)), "验收前可见核实、推断各几条，涉及几处代码", LX,
        lw=12.73 - LX)
callout(s, IX, IY, IW, IH, F(c, (112, 688, 824, 804)), "验收不通过须写明原因，智能体据此重改", LX, lw=12.73 - LX)
text(s, LX, 6.15, 12.73 - LX, 0.8, "智能体只在独立分支上修改，验证不通过时自动重改，最多 3 轮；合入主干由人操作。",
     size=12, color=MUTED, lsp=1.4)
tracker(s, 0, 2)
pnum(s, 6)

# ---------------------------------------------------------------- 8 一张工单的经过（见 build_story.py；机器图版本留在 build_principle.py）
from build_story import story_slide
s = S()
story_slide(s)
tracker(s, 0, 3)
pnum(s, 7)

# ---------------------------------------------------------------- 重构 · 改造计划
s = S()
section(s, "重构 · 改造计划")
title(s, "一个改造目标进来，平台先按业务域拆成几块，牵连少的先做")
IX, IY, IW = 0.6, 1.95, 7.9
c = CROP["rplan"]
IH = IW * (c[3] - c[1]) / (c[2] - c[0])
pic(s, "rplan", IX, IY, w=IW, frame=False)
callout(s, IX, IY, IW, IH, F(c, (56, 390, 1100, 475)), "写清改造目标和不能变的东西", 8.95,
        sub="例如对外接口路径、返回格式、表结构都不变", via=("at", 3.6))
callout(s, IX, IY, IW, IH, F(c, (900, 545, 1050, 890)), "每块列出涉及的业务流和数据表", 8.95,
        sub="来自平台对整个项目的分析", via=("down", 6.3))
callout(s, IX, IY, IW, IH, F(c, (1296, 545, 1352, 890)), "按牵连高低排先后", 8.95,
        sub="和其他块共用的表越少，越先做")
callout(s, IX, IY, IW, IH, F(c, (1376, 390, 1540, 418)), "先放出公共的先导部分", 8.95,
        sub="验收通过后，自动放出下一批", via=("up", 2.3))
notes(s, "截图是在示例项目（JeecgBoot）上建的一个依赖升级计划：Spring Boot 2.7 升级到 3.x，拆成先导部分加 6 个业务域。"
         "这个计划还没有放出工单，截图只用来说明计划长什么样。真实跑完的计划见下一页。")
tracker(s, 1, 0)
pnum(s, 8)

# ---------------------------------------------------------------- 7 重构与升级
s = S()
section(s, "重构 · 分批推进")
title(s, "重构按业务域一批批做，每批验收通过才继续")
IX, IY, IW = 0.6, 1.95, 7.9
c = CROP["plan"]
IH = IW * (c[3] - c[1]) / (c[2] - c[0])
pic(s, "plan", IX, IY, w=IW, frame=False)
callout(s, IX, IY, IW, IH, F(c, (56, 630, 1534, 672)), "对外接口与原系统保持一致", 8.95,
        sub="路径、状态码和 JSON 字段都是验收标准")
callout(s, IX, IY, IW, IH, F(c, (1190, 776, 1250, 1126)), "按与其他域共用表的多少排序", 8.95,
        sub="先做公共骨架，再从牵连最少的域做起")
callout(s, IX, IY, IW, IH, F(c, (64, 1140, 662, 1230)), "先导验收通过后，自动放出后面 7 个域", 8.95,
        sub="各域都从先导的提交开始改")
notes(s, "截图为真实运行数据：开源项目 RealWorld 的 .NET 后端，按“骨架 + 7 个业务域”分批改写为 Java + 达梦。"
         "先导“骨架”已验收闭环，其余 7 部分已改好、6 部分等人验收。8 个部分里 7 个在测试机上编译通过，规范 19 个接口改出 18 个；"
         "每部分智能体实际运行 19 到 41 分钟。没过的两处都由平台自己的诊断指出：RW-2 编译不过，RW-3 漏了一个接口，这正是要人验收的原因。"
         "这一轮没有跑接口测试，只能说编译通过、接口 18/19，不能说功能已验证。")
tracker(s, 1, 1)
pnum(s, 9)

# ---------------------------------------------------------------- 重构 · 改造工单列表
s = S()
section(s, "重构 · 改造工单")
title(s, "每一块改造都变成一张工单，和运维工单走同一条自动流程")
IX, IY, IW = 0.6, 2.1, 8.2
c = CROP["rlist"]
IH = IW * (c[3] - c[1]) / (c[2] - c[0])
pic(s, "rlist", IX, IY, w=IW, frame=False)
callout(s, IX, IY, IW, IH, F(c, (800, 290, 860, 610)), "标明是计划里的第几块", 9.2, lw=3.53,
        sub="先导一张，后面 7 个业务域各一张", via=("down", 5.15))
callout(s, IX, IY, IW, IH, F(c, (1140, 290, 1215, 610)), "每张单停在哪一步，一列看完", 9.2, lw=3.53,
        sub="已关闭、处理中、待验证")
callout(s, IX, IY, IW, IH, F(c, (44, 205, 820, 230)), "改造工单不进运维看板", 9.2, lw=3.53,
        sub="分析、改代码、构建测试、等验收和运维一样")
notes(s, "截图为真实运行数据：RealWorld .NET 后端改写为 Java + 达梦。RW-1 先导骨架已验收关闭，RW-2 在重改，其余 6 张等人验收。")
tracker(s, 1, 2)
pnum(s, 10)

# ---------------------------------------------------------------- 重构 · 改造工单详情
s = S()
section(s, "重构 · 改造工单")
title(s, "每张改造工单都写清改了什么、依据在哪，验收通过这一块才算完成")
IX, IY, IW = 0.6, 1.9, 8.0
c = CROP["rdetail"]
IH = IW * (c[3] - c[1]) / (c[2] - c[0])
pic(s, "rdetail", IX, IY, w=IW, frame=False)
LX = 9.05
callout(s, IX, IY, IW, IH, F(c, (110, 292, 1460, 370)), "智能体做到改完代码，停在人工验收", LX, lw=12.73 - LX)
callout(s, IX, IY, IW, IH, F(c, (110, 426, 1205, 492)), "根因分开标出【核实】和【推断】", LX, lw=12.73 - LX,
        sub="附上原 .NET 代码的位置")
callout(s, IX, IY, IW, IH, F(c, (110, 584, 1205, 634)), "写明改了几个文件、构建测试结果", LX, lw=12.73 - LX,
        sub="验收不通过须写原因，智能体照着重改")
callout(s, IX, IY, IW, IH, F(c, (1240, 845, 1556, 945)), "改动提交在单独分支上", LX, lw=12.73 - LX,
        sub="合入主干由人完成")
notes(s, "截图为真实运行数据：RW-4“文章收藏”业务域。智能体查了 42 处代码，新增 5 个文件，构建测试通过，改动在分支 tmh/RW-4-r20，等人验收。")
tracker(s, 1, 3)
pnum(s, 11)

# ---------------------------------------------------------------- 重构 · 一次改写的经过
from build_story import refactor_story_slide
s = S()
refactor_story_slide(s)
tracker(s, 1, 4)
pnum(s, 12)

# ---------------------------------------------------------------- 案例一：测试怎么做（见 build_cases.py）
from build_cases import case1_setup
s = S()
case1_setup(s)
pnum(s, 13)

# ---------------------------------------------------------------- 11 实测二
s = S()
section(s, "实测")
title(s, "案例一结果：40 张真实缺陷单里，34 张和官方修复方向一致")
segs = [(34, "和官方修复方向一致", ACCENT, WHITE), (6, "方向不对", GAP, WHITE)]
BX, BY, BW, BH = 0.6, 2.2, 12.13, 1.0
unit = BW / 40
x = BX
for n, lab, fill, tc in segs:
    w = n * unit
    sh_ = label_box(s, x, BY, w - 0.04, BH, [[(str(n), {"size": 30, "bold": True}), ("  张", {"size": 14})]],
                    fill=fill, color=tc, align="l" if n > 10 else "c")
    if n > 10:
        sh_.text_frame.margin_left = Inches(0.3)
    text(s, x, BY + BH + 0.1, w, 0.35, lab, size=13, color=INK, bold=True)
    x += w
finds = [("问题写得具体的单，基本能改对",
          "JB-21 指到了具体行，JB-33 给出了要加的方法，JB-40 说明了用错的列，三张和官方修复几乎一致。"),
         ("只有截图或报告人猜了原因的单，容易跑偏",
          "JB-19 报告人猜是大事务，智能体照着做了分批删除；官方的原因是请求参数个数超出上限。"),
         ("每张单几分钟出结果",
          "智能体从读单到改完代码，每张单用时中位数约 8 分钟。")]
for i, (h, d) in enumerate(finds):
    x = 0.6 + i * 4.1
    text(s, x, 4.4, 3.8, 0.4, h, size=14, color=INK, bold=True, lsp=1.3)
    text(s, x, 4.9, 3.8, 1.5, d, size=12, color=BODY, lsp=1.45)
# 底部：40 张单逐张上色，按 JB 号能回查 GitHub issue
CAT = {}
for nums, k in [((10, 12, 16, 19, 23, 27), 1)]:
    for n_ in nums:
        CAT[n_] = k
text(s, 0.6, 5.85, 12.1, 0.3, [[("逐张结果  ", {"bold": True, "color": INK}),
                               ("JB 号对应开源仓库 ", {}), ("github.com/jeecgboot/JeecgBoot", {"color": ACCENT, "bold": True}),
                               (" 上的原始 issue，可以逐张回查", {})]], size=11, color=MUTED)
cw_ = 12.13 / 40
for n_ in range(1, 41):
    _, _, fill_, tc_ = segs[CAT.get(n_, 0)]
    sh_ = label_box(s, 0.6 + (n_ - 1) * cw_, 6.22, cw_ - 0.03, 0.4, str(n_), fill=fill_, size=8.5, color=tc_, bold=True)
    sh_.text_frame.margin_left = sh_.text_frame.margin_right = 0
    sh_.text_frame.word_wrap = False
note(s, "工单和官方修复取自 JeecgBoot 开源仓库 https://github.com/jeecgboot/JeecgBoot ，JB 号与 GitHub issue 一一对应。"
         "评审逐张对照官方修复的 diff，判断智能体的改法和官方方向是否一致。方向不对的 6 张是 JB-10、12、16、19、23、27。")
pnum(s, 14)

# ---------------------------------------------------------------- 案例二：RealWorld 改写（见 build_cases.py）
from build_cases import case2_setup, case2_result
s = S()
case2_setup(s)
pnum(s, 15)
s = S()
case2_result(s)
pnum(s, 16)

# ---------------------------------------------------------------- 12 RSI 自进化（见 build_rsi.py）
from build_rsi import rsi_slide
s = S()
rsi_slide(s)
pnum(s, 17, True)

# ---------------------------------------------------------------- 13 架构
s = S()
section(s, "产品架构")
title(s, "技术路线")
LX, LW = 0.6, 1.5
CX, CW = 2.3, 9.8
rows_y = [(1.85, 1.3), (3.62, 1.8), (5.75, 0.95)]
for (y, h), lb in zip(rows_y, ["业务应用", "智能体编排", "代码知识库"]):
    label_box(s, LX, y, LW, h, lb, fill=ACCENT_T, size=13, color=ACCENT, bold=True, shape="round")
# 业务应用：运维服务 / 重构服务 / 可扩展服务
y, h = rows_y[0]
groups = [("运维服务", SERVICES[:3], 4.25), ("重构服务", SERVICES[3:], 2.85), ("可扩展服务", FUTURE, 2.4)]
gx, gg, ig = CX, 0.15, 0.08
mids = []
for gi, (gname, items, gw) in enumerate(groups):
    fut = gi == 2
    box(s, gx, y, gw, h, PANEL if fut else WHITE, RULE if fut else ACCENT_M, 0.9, dash=fut, shape="round")
    text(s, gx + 0.12, y + 0.07, gw - 0.24, 0.26, gname + ("（规划）" if fut else ""), size=10,
         color=MUTED if fut else ACCENT, bold=True)
    n = len(items)
    iw = (gw - 0.2 - ig * (n - 1)) / n
    for j, it in enumerate(items):
        x = gx + 0.1 + j * (iw + ig)
        if fut:
            box(s, x, y + 0.4, iw, 0.78, WHITE, RULE, 0.75, shape="round")
            text(s, x, y + 0.4, iw, 0.78, [it[:2], it[2:]], size=10.5, color=MUTED, align="c", anchor="m", lsp=1.1)
        else:
            box(s, x, y + 0.4, iw, 0.78, WHITE, RULE, 0.75, shape="round")
            text(s, x, y + 0.48, iw, 0.32, it[0], size=13, color=INK, bold=True, align="c")
            text(s, x, y + 0.84, iw, 0.26, it[1], size=8, color=MUTED, align="c")
    mids.append(gx + gw / 2)
    gx += gw + gg
jy = y + h + 0.16
for m in mids:
    line(s, m, y + h, m, jy, ACCENT_M, 1.0)
line(s, mids[0], jy, mids[-1], jy, ACCENT_M, 1.0)
line(s, CX + CW / 2, jy, CX + CW / 2, rows_y[1][0], ACCENT, 1.0, arrow=True)
text(s, CX + CW / 2 + 0.08, jy + 0.02, 1.5, 0.2, "提交任务", size=8.5, color=ACCENT)
# 智能体编排
y, h = rows_y[1]
box(s, CX, y, CW, h, ACCENT, None, shape="round")
text(s, CX + 0.2, y + 0.08, 4, 0.32, "编码智能体编排", size=13, color=WHITE, bold=True)
ag = 0.2
aw = (CW - 0.3 - ag * 5) / 6
for i, (nm, sub, _, _) in enumerate(AGENTS):
    x = CX + 0.15 + i * (aw + ag)
    box(s, x, y + 0.46, aw, 0.98, WHITE, None, shape="round")
    text(s, x, y + 0.6, aw, 0.34, nm, size=13, color=ACCENT, bold=True, align="c")
    text(s, x, y + 0.98, aw, 0.28, sub, size=9, color=MUTED, align="c")
    if i < 5:
        line(s, x + aw + 0.03, y + 0.95, x + aw + ag - 0.03, y + 0.95, ACCENT_T, 1.25, arrow=True)
text(s, CX, y + 1.5, CW, 0.28, "独立分支修改  ·  退回自动重改  ·  人可随时接手", size=10, color=ACCENT_T, align="c")
line(s, CX + CW / 2, y + h, CX + CW / 2, rows_y[2][0], ACCENT, 1.0, arrow=True)
text(s, CX + CW / 2 + 0.1, y + h + 0.06, 1.8, 0.2, "读取项目知识", size=8.5, color=ACCENT)
# 代码知识库
y, h = rows_y[2]
box(s, CX, y, CW, h, ACCENT_T, None, shape="round")
kw = CW / 4
for i, (nm, sub) in enumerate(KNOW):
    x = CX + i * kw
    text(s, x, y + 0.14, kw, 0.35, nm, size=14, color=INK, bold=True, align="c")
    text(s, x, y + 0.53, kw, 0.28, sub, size=9.5, color=BODY, align="c")
    if i:
        line(s, x, y + 0.18, x, y + h - 0.18, ACCENT_M, 0.75)
# 右侧回流
fx = CX + CW + 0.25
line(s, CX + CW, rows_y[0][0] + 0.65, fx, rows_y[0][0] + 0.65, ACCENT, 1.0)
line(s, fx, rows_y[0][0] + 0.65, fx, rows_y[2][0] + 0.47, ACCENT, 1.0)
line(s, fx, rows_y[2][0] + 0.47, CX + CW + 0.02, rows_y[2][0] + 0.47, ACCENT, 1.0, arrow=True)
line(s, fx, rows_y[1][0] + 1.45, CX + CW + 0.02, rows_y[1][0] + 1.45, ACCENT, 1.0, arrow=True)
text(s, fx + 0.02, 3.35, 0.32, 1.6, list("越用越准"), size=11, color=ACCENT, bold=True, align="c", lsp=1.05)
note(s, "回流：验收教训和评测用例回到编排层，知识修正回到知识库。可扩展服务尚未开发。")
pnum(s, 18)

# ---------------------------------------------------------------- 16 安全
s = S()
section(s, "部署与安全")
title(s, "代码留在客户内网里，智能体做过的每件事都有记录")
# 一张边界图：整条链路都画在“客户内网”虚线框里，四个要点落在图上，不再写成四块文字
BX0, BY0, BW0, BH0 = 0.6, 1.95, 12.13, 4.4
box(s, BX0, BY0, BW0, BH0, None, ACCENT_M, 1.25, dash=True, shape="round", radius=0.03)
text(s, BX0 + 0.3, BY0 + 0.2, 3, 0.3, "客户内网", size=12, color=ACCENT, bold=True)
NODES = [("代码仓库", "源码原样不动", PANEL, INK),
         ("代码知识库", "在本地解析，不调用模型", PANEL, INK),
         ("智能体", "读知识库、改代码", ACCENT, WHITE),
         ("独立分支", "每张工单一个分支", PANEL, INK),
         ("主干", "人审核后合入", ACCENT_T, ACCENT)]
NW, NH, NG, NY = 1.95, 1.05, 0.42, 2.75
nx = [BX0 + 0.42 + i * (NW + NG) for i in range(len(NODES))]
for x, (h, d, fill, col) in zip(nx, NODES):
    box(s, x, NY, NW, NH, fill, None, shape="round", radius=0.08)
    text(s, x, NY + 0.2, NW, 0.35, h, size=15, color=col, bold=True, align="c")
    text(s, x, NY + 0.6, NW, 0.3, d, size=10.5, color=col if col == WHITE else MUTED, align="c")
for i in range(len(NODES) - 1):
    c = ACCENT if i == 3 else MUTED
    line(s, nx[i] + NW + 0.05, NY + NH / 2, nx[i + 1] - 0.05, NY + NH / 2, c, 1.25, arrow=True)
text(s, nx[3] + NW - 0.3, NY - 0.32, NG + 0.6, 0.28, "人合入", size=10, color=ACCENT, bold=True, align="c")
# 模型挂在智能体下面，同样在内网里
mx, mw, my = nx[2] + NW / 2 - 1.5, 3.0, NY + NH + 0.5
line(s, nx[2] + NW / 2, NY + NH + 0.05, nx[2] + NW / 2, my - 0.05, MUTED, 1.25, arrow=True)
box(s, mx, my, mw, 0.8, WHITE, RULE, 1.0, shape="round", radius=0.08)
text(s, mx, my + 0.1, mw, 0.32, "国产大模型", size=13, color=INK, bold=True, align="c")
text(s, mx, my + 0.44, mw, 0.28, "Kimi、GLM 等，可部署在内网", size=10.5, color=MUTED, align="c")
# 底部：运行记录贯穿整条链路
ry = BY0 + BH0 - 0.85
line(s, BX0 + 0.42, ry, BX0 + BW0 - 0.42, ry, RULE, 0.75)
text(s, BX0 + 0.42, ry + 0.17, 1.4, 0.4, "运行记录", size=13, color=INK, bold=True, anchor="m")
text(s, BX0 + 1.9, ry + 0.17, 9.5, 0.4, "智能体每次运行，都记下依据了哪些代码、用了哪个模型、改了什么、花了多少。",
     size=12, color=BODY, anchor="m")
notes(s, "整套平台以离线安装包部署在客户内网。代码知识库在本地解析生成，不消耗模型费用。"
         "模型可接 Kimi、GLM 等国产模型。智能体只在每张工单的独立分支（tmh/工单号）上提交，合入主干由人操作。")
pnum(s, 19)

# 15 前景：倒金字塔
from build_pyramid import pyramid_slide
s = S()
pyramid_slide(s)
pnum(s, 20)

# ---------------------------------------------------------------- 商业模式（见 build_biz.py）
from build_biz import model_slide
s = S()
model_slide(s)
pnum(s, 21)

# 云涌世纪 logo：封面左上角放大，其余页左下角；深色页用白字版
for k, sl in enumerate(prs.slides):
    if k == 0:
        sl.shapes.add_picture(os.path.join(IMG, "logo.png"), Inches(0.8), Inches(0.6), height=Inches(0.62))
        continue
    f = sl.background.fill
    dark = f.type is not None and str(f.fore_color.rgb) not in ("FFFFFF",)
    sl.shapes.add_picture(os.path.join(IMG, "logo_w.png" if dark else "logo.png"), Inches(0.6), Inches(7.04),
                          height=Inches(0.26))

strip_styles(prs)
prs.save(OUT)
print("saved", OUT, len(prs.slides.__iter__.__self__._sldIdLst))
