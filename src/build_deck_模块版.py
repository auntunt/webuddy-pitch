import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pptkit import *
from tree_data import BRANCHES, PHASES, modules, counts, STATUS_LABEL, AS_OF
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION

OUT = sys.argv[1] if len(sys.argv) > 1 else "deck.pptx"
TOTAL = 21
prs = new_deck()
DISPLAY = {"CLI（tmh）": "命令行工具", "场景提示词": "编程助手提示词", "MCP": "IDE 接口（MCP）"}
for b in BRANCHES:
    b["scenes"] = [(sid, sn, [(i, DISPLAY.get(n, n), st, ph) for i, n, st, ph in ms]) for sid, sn, ms in b["scenes"]]
MODS = list(modules())
CNT = counts()
TOT = {k: sum(c[k] for c in CNT.values()) for k in ("done", "part", "gap")}
N_MOD = len(MODS)

def S():
    return blank(prs)

# ---------------------------------------------------------------- 1 封面
s = S()
box(s, 0.6, 1.55, 0.08, 2.1, ACCENT)
text(s, 0.95, 1.45, 11, 0.5, "立项汇报", size=12, color=ACCENT, bold=True)
text(s, 0.95, 1.9, 11.5, 1.0, "老项目运维提效", size=44, color=INK, bold=True)
text(s, 0.95, 2.85, 11.5, 0.6, "以业务知识库为底座的老项目维保平台", size=20, color=BODY)
text(s, 0.95, 4.35, 8, 0.9, ["Li", "2026 年 10 月"], size=12, color=MUTED, lsp=1.3)

# ---------------------------------------------------------------- 2 摘要
s = S()
header(s, "摘要", "维保的瓶颈是“读懂”老系统；先把业务知识沉淀下来，AI 才能在老项目里提效")
text(s, 0.6, 1.55, 6.6, 3.6, [
    "老项目交付之后，维保的成本主要花在找人问、读代码和不敢改上，而不是写代码本身。现有的编程助手擅长写新代码，却不了解客户的业务。",
    "我们把维保工作拆成 7 个方向、22 个场景、%d 个功能模块，并据此搭建一个维保平台：用静态分析加人工确认，把老项目沉淀成按业务流组织的知识库，再交给人和现有的编程助手使用，提效从流程里自动计量。" % N_MOD,
    "在一个约 55 万行、98% 来自反编译的财务共享平台上，不调用模型即抽出 3,079 条业务流，一句中文需求约 5 秒定位到代码。一期功能已经完成，下一步是真实项目试点。",
], size=12.5, color=BODY, lsp=1.35, space_after=9)
# 右侧：贡献
text(s, 7.75, 1.55, 5, 0.3, "本稿的三项内容", size=10, color=MUTED, bold=True)
contrib = [
    ("1", "维保工作拆解树", "按“谁在做”拆到可单独立项的功能模块。"),
    ("2", "以业务知识库为核心的平台", "一份知识，多处使用；答不了的转人工，答复写回知识库。"),
    ("3", "真实老项目上的实测", "已验证的数字，以及尚未验证的部分。"),
]
yy = 1.95
for n, t, d in contrib:
    text(s, 7.75, yy, 0.4, 0.4, n, size=20, color=ACCENT, bold=True)
    text(s, 8.25, yy + 0.02, 4.5, 0.3, t, size=12, color=INK, bold=True)
    text(s, 8.25, yy + 0.34, 4.45, 0.6, d, size=10, color=MUTED, lsp=1.25)
    yy += 1.05
# 底部关键数
line(s, 0.6, 5.45, 12.73, 5.45, RULE, 0.5)
kp = [("3,079", "条业务流，静态抽取"), ("约 5 秒", "一句中文需求定位到代码"),
      ("%d / %d" % (TOT["done"], N_MOD), "个模块已实现"), ("一期", "已完成，待试点")]
for i, (v, l) in enumerate(kp):
    x = 0.6 + i * 3.06
    text(s, x, 5.6, 3, 0.6, v, size=28, color=ACCENT, bold=True)
    text(s, x, 6.2, 2.9, 0.5, l, size=10, color=MUTED)
footer(s, 2, TOTAL)

# ---------------------------------------------------------------- 3 问题：读懂
s = S()
header(s, "问题", "维保的成本在“读懂”和“被打断”，不在“改”")
stats = [
    ("58%", "开发时间花在理解代码上", "78 名开发、3,148 工时的现场观测", "[1]"),
    ("47%", "的开发每天至少花 30 分钟回答别人的问题", "75% 重复回答过同一个问题", "[2]"),
    ("23 分钟", "被打断后回到原任务的平均时间", "需求人员每问一次开发，都有这笔代价", "[3]"),
    ("65%", "的热门开源项目走掉 1 到 2 个人就陷入危机", "知识集中在少数人身上", "[4]"),
]
for i, (v, l, d, ref) in enumerate(stats):
    x = 0.6 + i * 3.06
    line(s, x, 1.75, x + 2.8, 1.75, INK, 1.0)
    text(s, x, 1.9, 2.9, 0.8, v, size=40, color=ACCENT, bold=True)
    text(s, x, 2.75, 2.75, 0.8, l, size=12.5, color=INK, bold=True, lsp=1.2)
    text(s, x, 3.55, 2.75, 0.7, [[(d + " ", {}), (ref, {"color": FAINT})]], size=10, color=MUTED, lsp=1.2)
box(s, 0.6, 4.75, 12.13, 1.85, PANEL)
text(s, 0.85, 4.92, 11.7, 1.6, [
    [("对维保意味着什么", {"bold": True, "color": INK})],
    "老项目的代码老、文档缺、原作者多半不在。每张工单的大部分时间花在“找到该改哪里、搞清楚业务为什么这样”，而需求和实施人员判断“能不能做”也只能去问开发。",
    "所以提效的抓手不是“写代码更快”，而是让业务知识不再只存在于人脑里。",
], size=11.5, color=BODY, lsp=1.35, space_after=4)
footer(s, 3, TOTAL, "[1] Xia 等, ICSE 2018   [2] Stack Overflow 开发者调查 2024   [3] Gloria Mark，经 Fast Company   [4] arXiv 1604.06766")

# ---------------------------------------------------------------- 4 一线证据
s = S()
header(s, "问题", "一线抱怨集中在“知识只在人脑子里”和“不敢改”")
rows = [["痛点", "一线怎么说（转述）", "来源"],
        ["知识只在人脑子里", "问报表字段怎么算，经理只说“自己看代码”", "V2EX"],
        ["交接断档", "离职同事一次交接 11 个项目，无文档无注释，最后一周才安排", "V2EX"],
        ["不敢改", "花两周修好的金额精度 bug，被 AI 重构“简化”回去，单测全过", "V2EX"],
        ["承诺先于评估", "售前很难判断方案能不能落地，只能去问技术，否则容易乱报价", "V2EX"],
        ["交付后边界模糊", "客户借“维护”提新功能，还要 7×24 随叫随到，年费又低", "V2EX"],
        ["线上定位慢", "开发没有生产日志和库权限，只能请人导数据回测试环境调", "V2EX"],
        ["重写失控", "亲历的推倒重来没有一次成功，渐进迁移又要新旧双改", "V2EX"],
        ["信创踩坑", "达梦大小写敏感只能安装时定；同一函数 Oracle 30 秒、达梦 3 小时", "V2EX"],
        ["AI 带来的新问题", "AI 写的代码连作者都讲不清，同事来问只能再转给 AI", "linux.do"],
        ["复制粘贴式交付", "每个客户复制一份源码，修复不会同步到其他客户的分叉", "博客园"]]
table(s, 0.6, 1.55, 12.13, [2.3, 8.43, 1.4], rows, size=10.5, row_h=0.4, first_bold=True)
caption(s, 0.6, 6.1, 12.1, "表 1", "从 36 条公开的一线讨论中每类选一条，为定性证据。")
footer(s, 4, TOTAL)

# ---------------------------------------------------------------- 5 AI 新问题 + 假设
s = S()
header(s, "问题", "没有项目知识时，AI 在老代码上未必提效；先沉淀知识再喂给智能体，才有收益")
# 左：对照
text(s, 0.6, 1.6, 6.0, 0.3, "两组公开结果放在一起看", size=10, color=MUTED, bold=True)
cards = [
    ("−19%", "资深开发在熟悉的大型老项目上用 AI，反而变慢", "METR 2025 [5]。2026 年更新改测为变快约 18%，但 METR 自己称结果不可靠 [6]", FAINT),
    ("−40%", "Meta 给模块预生成上下文文件后，智能体的工具调用和 token 都减少约 40%", "Meta 工程博客 2026-04 [7]，6 个任务的初步测试", ACCENT),
]
yy = 1.95
for v, l, d, c in cards:
    line(s, 0.6, yy, 6.4, yy, RULE, 0.5)
    text(s, 0.6, yy + 0.12, 1.6, 0.7, v, size=30, color=c, bold=True)
    text(s, 2.25, yy + 0.15, 4.2, 0.7, l, size=12, color=INK, bold=True, lsp=1.2)
    text(s, 2.25, yy + 0.85, 4.2, 0.6, d, size=9.5, color=MUTED, lsp=1.2)
    yy += 1.6
line(s, 0.6, yy, 6.4, yy, RULE, 0.5)
# 右：AI 带来的新维保问题
text(s, 7.1, 1.6, 5.6, 0.3, "AI 本身也在制造新的维保问题", size=10, color=MUTED, bold=True)
newp = [("代码不出内网", "内网里只有一年前的国产模型，并发一高就卡，智能体工具也装不上。"),
        ("AI 债", "高强度用 AI 写代码后，作者自己也讲不清实现。"),
        ("政策反转", "上个月号召学 AI，这周要求卸载所有境外 AI 工具。"),
        ("测试被撤", "推 AI 编码后测试岗被撤，评审的人看不懂 AI 的方案。")]
yy = 1.95
for t, d in newp:
    text(s, 7.1, yy, 1.45, 0.5, t, size=11, color=INK, bold=True)
    text(s, 8.6, yy, 4.1, 0.6, d, size=10.5, color=BODY, lsp=1.2)
    yy += 0.62
box(s, 0.6, 5.35, 12.13, 1.3, ACCENT_T)
text(s, 0.85, 5.48, 11.7, 1.1, [
    [("工作假设", {"bold": True, "color": ACCENT})],
    [("在老项目上，AI 提效的前提是业务层上下文。", {"bold": True, "color": INK}),
     ("模型越弱，上下文的价值越大；与模型无关的知识库也不受工具和政策变化的影响。", {})],
], size=11.5, color=BODY, lsp=1.35, space_after=3)
footer(s, 5, TOTAL, "[5] METR 2025-07   [6] METR 2026-02 uplift update   [7] Meta Engineering, 2026-04-06")

# ---------------------------------------------------------------- 6 相关工作：定位图
s = S()
header(s, "相关工作", "现有产品解决“同一种改动跨上千仓库”，我们解决“一个老项目里每天不同的工单”")
X0, Y0, W, H = 1.5, 1.6, 7.0, 4.75
box(s, X0, Y0, W, H, None, RULE, 0.75)
line(s, X0 + W / 2, Y0, X0 + W / 2, Y0 + H, RULE, 0.5, dash=True)
line(s, X0, Y0 + H / 2, X0 + W, Y0 + H / 2, RULE, 0.5, dash=True)
text(s, X0, Y0 + H + 0.08, W, 0.3, "知识的层次   语法与代码引用  →  架构与质量  →  业务流程", size=9.5, color=MUTED, align="c")
text(s, 0.3, Y0 + 0.05, 1.1, 0.5, ["一个项目", "每日不同工单"], size=8.5, color=MUTED, align="r")
text(s, 0.3, Y0 + H - 0.5, 1.1, 0.5, ["同一种改动", "跨上千仓库"], size=8.5, color=MUTED, align="r")
text(s, 0.3, Y0 + H / 2 - 0.15, 1.1, 0.3, "处理的单位", size=8.5, color=INK, bold=True, align="r")
pts = [("Moderne", 0.12, 0.88, "LST + 1 万多条确定性配方"), ("Sourcegraph", 0.25, 0.80, "代码搜索 + 跨仓批量变更"),
       ("Codemod", 0.10, 0.70, "框架升级，JS/TS 为主"), ("CodeScene", 0.47, 0.42, "代码健康度 + Git 行为"),
       ("vFunction", 0.62, 0.52, "运行时分析拆单体"), ("通用编程助手", 0.22, 0.26, "Claude Code · Codex · Cursor")]
for name, px, py, d in pts:
    cx, cy = X0 + px * W, Y0 + py * H
    box(s, cx - 0.07, cy - 0.07, 0.14, 0.14, FAINT if name == "通用编程助手" else BODY, None, shape="oval")
    text(s, cx + 0.12, cy - 0.17, 2.4, 0.25, name, size=10, color=INK, bold=True)
    text(s, cx + 0.12, cy + 0.04, 2.6, 0.25, d, size=8.5, color=MUTED)
cx, cy = X0 + 0.86 * W, Y0 + 0.13 * H
box(s, cx - 0.11, cy - 0.11, 0.22, 0.22, ACCENT, None, shape="oval")
text(s, cx - 1.9, cy + 0.15, 2.6, 0.25, "本项目", size=11, color=ACCENT, bold=True, align="r")
text(s, cx - 2.6, cy + 0.4, 3.3, 0.45, "业务知识库 + 流程台账", size=8.5, color=MUTED, align="r")
# 右侧说明
rx = 9.0
text(s, rx, 1.6, 3.73, 0.3, "我们的差异", size=10, color=MUTED, bold=True)
diff = [("处理的单位", "一张工单，而不是一次迁移"), ("知识层次", "从代码延伸到业务流和业务域"),
        ("服务对象", "维保和交付团队、部门负责人"), ("适用场景", "反编译代码、低代码、国产数据库、私有化部署"),
        ("和智能体的关系", "给它们供业务上下文，并记录它们做了什么")]
yy = 1.95
for k, v in diff:
    text(s, rx, yy, 3.73, 0.25, k, size=10, color=INK, bold=True)
    text(s, rx, yy + 0.27, 3.73, 0.55, v, size=10, color=BODY, lsp=1.2)
    yy += 0.86
caption(s, 1.5, 6.68, 7.2, "图 1", "按各家公开材料定性放置。")
footer(s, 6, TOTAL, "[15] Moderne   [16] Sourcegraph   [17] Codemod   [18] CodeScene   [19] vFunction")

# ---------------------------------------------------------------- 7 已有答案成熟度
s = S()
header(s, "相关工作", "每类痛点都已有成熟做法，空白都在业务层：我们把它们搬到“业务流”这个单位上")
rows = [["方向", "已有做法的成熟度", "值得借鉴的做法", "我们补的空白"],
        ["现场答复", "方法成熟，自动答复只解决约一半", "KCS“答即写条目”[10]；Uber Genie 转人工与反馈 [9]", "答“这套老系统能不能做”，而不是“工具怎么用”"],
        ["日常维护", "成熟，大厂有数字；但 12% 的组织完全不做回归 [21]", "表征测试录现状；LLM 补测试只收过三道关的 [11]", "用业务流影响分析驱动回归和快照"],
        ["线上运维", "中等，准确率 0.4 到 0.77", "先用规则收窄范围，再让模型排序 [22]", "报错对应到业务流和最近工单"],
        ["重写升级", "最一致：不要推倒重来；七成以上大型机迁出预计达不到预期收益 [8]", "绞杀者模式 [23]；影子流量比对 [12]", "进度按业务流统计，领导看得懂"],
        ["项目知识", "成熟，工业界领先学术界", "预计算上下文文件 [7]；带代码引用的记忆 [14]", "从代码层延伸到业务层"],
        ["接入与度量", "结论不一致", "速度和返工并列报 [13]；自己做前后对比", "内网弱模型靠业务上下文补足"]]
table(s, 0.6, 1.6, 12.13, [1.65, 2.6, 4.2, 3.68], rows, size=10.5, row_h=0.56, first_bold=True)
caption(s, 0.6, 5.65, 12.1, "表 2", "按工作方向归纳的已有做法。")
box(s, 0.6, 6.05, 12.13, 0.7, PANEL)
text(s, 0.8, 6.13, 11.8, 0.55, [[("可信的自动答复数字只有 Uber Genie 的 48.9% 有帮助率 [9]。", {"bold": True, "color": INK}),
     ("所以“转人工、答案回流”不是兜底功能，而是一期的核心。", {})]], size=11, color=BODY, anchor="m")
footer(s, 7, TOTAL, "[9] Uber Genie   [10] KCS v6   [11] Meta TestGen-LLM   [12] GitHub Scientist   [13] DORA 2024   [14] GitHub Copilot 记忆   [22] RCACopilot   [23] Fowler   [8] Gartner，经 The Register   [21] Gartner Peer 投票")

# ---------------------------------------------------------------- 8 金字塔
s = S()
header(s, "问题拆解", "维保提效是一座金字塔：项目知识是底座")
cx, top, H, half = 6.35, 1.55, 4.95, 3.55
def hw(y): return half * (y - top) / H
tiers = [  # (y0, y1)
    (top, top + 1.45), (top + 1.5, top + 2.85), (top + 2.9, top + 3.9), (top + 3.95, top + H)]
# 顶：目标
y0, y1 = tiers[0]
poly(s, [(cx, y0), (cx + hw(y1), y1), (cx - hw(y1), y1)], WHITE, ACCENT, 1.5)
text(s, cx - 0.9, y0 + 0.62, 1.8, 0.8, [[("目标", {"bold": True, "color": ACCENT, "size": 12})], "答得快 · 改得稳", "翻新看得见"], size=9.5, color=INK, align="c", lsp=1.15)
# 第二层：四个工作域
y0, y1 = tiers[1]
names = [("现场答复", "需求接入"), ("日常维护", "需求与功能"), ("线上运维", "问题与数据"), ("重写升级", "技术演进")]
L0, R0, L1, R1 = cx - hw(y0), cx + hw(y0), cx - hw(y1), cx + hw(y1)
for i, (k, nm) in enumerate(names):
    a, b = i / 4, (i + 1) / 4
    ptl = (L0 + (R0 - L0) * a, y0); ptr = (L0 + (R0 - L0) * b, y0)
    pbr = (L1 + (R1 - L1) * b, y1); pbl = (L1 + (R1 - L1) * a, y1)
    poly(s, [ptl, ptr, pbr, pbl], PANEL, WHITE, 2.0)
    mx = (ptl[0] + ptr[0] + pbr[0] + pbl[0]) / 4
    text(s, mx - 0.6, y0 + 0.4, 1.2, 0.7, [[(k, {"bold": True, "size": 11, "color": INK})], nm], size=9, color=MUTED, align="c", lsp=1.2)
# 第三层：人机接口
y0, y1 = tiers[2]
poly(s, [(cx - hw(y0), y0), (cx + hw(y0), y0), (cx + hw(y1), y1), (cx - hw(y1), y1)], ACCENT_T, None)
text(s, cx - 2.5, y0 + 0.15, 5.0, 0.8, [[("人机接口", {"bold": True, "size": 12, "color": INK})],
     "平台 · 编程助手 · 群机器人 · 自动流水线 · 内网部署"], size=9, color=BODY, align="c", lsp=1.25)
# 底：项目知识
y0, y1 = tiers[3]
poly(s, [(cx - hw(y0), y0), (cx + hw(y0), y0), (cx + hw(y1), y1), (cx - hw(y1), y1)], ACCENT, None)
text(s, cx - 3.0, y0 + 0.18, 6.0, 0.9, [[("项目知识", {"bold": True, "size": 12.5, "color": WHITE})],
     "代码 → 业务流 → 业务域；人工确认，随代码自动更新"], size=9.5, color=WHITE, align="c", lsp=1.3)
# 左侧：每层回答的问题
qs = ["为什么做\n价值与目标", "做什么\n各角色的日常工作", "怎么用\n送到人和工具手里", "靠什么\n可核对的业务知识"]
for (y0, y1), q in zip(tiers, qs):
    a, b = q.split("\n")
    text(s, 0.6, (y0 + y1) / 2 - 0.3, 2.0, 0.6, [[(a, {"bold": True, "color": INK})], b], size=9.5, color=MUTED, lsp=1.2)
# 右侧：G 度量
gx = 10.25
line(s, gx, tiers[0][0] + 0.3, gx, tiers[3][1], ACCENT, 1.25)
text(s, gx + 0.15, tiers[0][0] - 0.05, 2.4, 0.5, [[("度量", {"bold": True, "color": ACCENT, "size": 11})], "每一层自动记录"], size=8.5, color=MUTED, lsp=1.15)
gm = ["答复时长\n工单周期", "采纳率\n退回率", "使用次数\nAI 参与率", "已确认页数"]
for (y0, y1), m in zip(tiers, gm):
    ym = (y0 + y1) / 2 + (0.25 if y0 == tiers[0][0] else 0)
    line(s, gx, ym, gx + 0.12, ym, ACCENT, 1.0)
    text(s, gx + 0.2, ym - 0.25, 2.3, 0.55, m.split("\n"), size=9, color=BODY, lsp=1.15)
caption(s, 0.6, 6.62, 12.1, "图 2", "上层依赖下层：所有工作场景都从项目知识取答案。")
footer(s, 8, TOTAL)

# ---------------------------------------------------------------- 9 功能分解树
s = S()
header(s, "问题拆解", "维保工作拆解树：%d 个模块中已实现 %d 个" % (N_MOD, TOT["done"]))
x0, gap = 0.45, 0.05
cw = (SW - 2 * x0 - 6 * gap) / 7
ry = 1.42
root = label_box(s, SW / 2 - 1.9, ry, 3.8, 0.38, [[("老项目运维提效", {"bold": True, "color": WHITE}), ("   答得快 · 改得稳 · 翻新看得见", {"color": "D8E0F2", "size": 8.5})]], fill=INK, size=10.5, color=WHITE)
bus = 1.96
line(s, SW / 2, ry + 0.38, SW / 2, bus, INK, 0.75)
cols = [x0 + i * (cw + gap) for i in range(7)]
line(s, cols[0] + cw / 2, bus, cols[-1] + cw / 2, bus, INK, 0.75)
by, bh = 2.08, 0.56
PH = {1: "①", 2: "②", 3: "③"}
for b, cx_ in zip(BRANCHES, cols):
    line(s, cx_ + cw / 2, bus, cx_ + cw / 2, by, INK, 0.75)
    if b["kind"] == "base":
        fl, ln, tc, sc = ACCENT, None, WHITE, "D8E0F2"
    elif b["kind"] == "cross":
        fl, ln, tc, sc = WHITE, ACCENT, ACCENT, MUTED
    else:
        fl, ln, tc, sc = WHITE, INK, INK, MUTED
    label_box(s, cx_, by, cw, bh, [[(b["name"], {"bold": True, "color": tc, "size": 9})],
                                  [(b["who"], {"color": sc, "size": 7})]],
              fill=fl, line=ln, lw=1.0, dash=(b["kind"] == "cross"))
    yy = by + bh + 0.12
    trunk_top = by + bh
    last_scene_mid = None
    for sid, sname, mods in b["scenes"]:
        if sname:
            mid = yy + 0.1
            line(s, cx_ + 0.04, mid, cx_ + 0.09, mid, FAINT, 0.5)
            text(s, cx_ + 0.1, yy, cw - 0.1, 0.2, [[(sname, {"bold": True})]], size=7.5, color=INK)
            last_scene_mid = mid
            sub_top = yy + 0.2
            yy += 0.2
        last_mod_mid = None
        for mid_, mname, st, ph in mods:
            gm = yy + 0.1
            if sname:
                line(s, cx_ + 0.12, gm, cx_ + 0.16, gm, FAINT, 0.5)
            glyph(s, cx_ + 0.17, yy + 0.05, st, 0.1)
            lab = [(mname, {"color": BODY if st != "gap" else GAP})]
            text(s, cx_ + 0.31, yy, cw - 0.31 - 0.14, 0.2, [lab], size=7.5, color=BODY)
            if ph:
                text(s, cx_ + cw - 0.15, yy - 0.01, 0.15, 0.2, PH[ph], size=8, color=ACCENT, bold=True, align="r")
            last_mod_mid = gm
            yy += 0.2
        if sname and last_mod_mid:
            line(s, cx_ + 0.12, sub_top, cx_ + 0.12, last_mod_mid, FAINT, 0.5)
        yy += 0.07
    if last_scene_mid:
        line(s, cx_ + 0.04, trunk_top, cx_ + 0.04, last_scene_mid, FAINT, 0.5)
# 图例
ly = 6.55
lx = 0.45
for st in ("done", "part", "gap"):
    glyph(s, lx, ly + 0.06, st, 0.11)
    text(s, lx + 0.17, ly, 1.0, 0.25, "%s %d" % (STATUS_LABEL[st], TOT[st]), size=8.5, color=BODY)
    lx += 1.05
text(s, lx + 0.1, ly, 4.5, 0.25, [[("①②③", {"color": ACCENT, "bold": True}), ("  一期 / 二期 / 三期", {})]], size=8.5, color=BODY)
footer(s, 9, TOTAL, "现状截至 %s。" % AS_OF)

# ---------------------------------------------------------------- 10 现状统计
s = S()
header(s, "问题拆解", "缺口集中在重写升级和日常维护的回归环节")
cd = CategoryChartData()
order = ["A", "B", "C", "D", "E", "F", "G"]
bname = {b["id"]: b["name"] for b in BRANCHES}
cd.categories = [bname[k] for k in order]
for st in ("done", "part", "gap"):
    cd.add_series(STATUS_LABEL[st], [CNT[k][st] for k in order])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.6), Inches(1.55), Inches(7.4), Inches(4.7), cd)
ch = gf.chart
ch.has_title = False
ch.font.size = Pt(10)
ch.font.name = LATIN
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.TOP
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(9)
plot = ch.plots[0]
plot.gap_width = 55
plot.overlap = 100
for ser, st in zip(plot.series, ("done", "part", "gap")):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = rgb(STATUS_FILL[st])
    ser.format.line.color.rgb = rgb(WHITE)
    ser.format.line.width = Pt(1)
plot.has_data_labels = True
dl = plot.data_labels
dl.font.size = Pt(9)
dl.font.color.rgb = rgb(WHITE)
dl.font.bold = True
dl.position = XL_LABEL_POSITION.CENTER
ca = ch.category_axis
ca.reverse_order = True
ca.tick_labels.font.size = Pt(10)
ca.format.line.color.rgb = rgb(RULE)
ca.has_major_gridlines = False
va = ch.value_axis
va.has_major_gridlines = False
va.visible = False
va.maximum_scale = 11
caption(s, 0.6, 6.3, 7.4, "图 4", "各方向模块的现状（共 %d 个）。" % N_MOD)
rx = 8.5
text(s, rx, 1.6, 4.2, 0.3, "读这张图", size=10, color=MUTED, bold=True)
pts_ = [("重写升级", "改造规划、批量改写、新旧行为对比，即三期内容。"),
        ("日常维护", "回归清单和风险分级，决定能否无人值守地改。"),
        ("线上运维", "报错定位和巡检已有基础，按试点需要补齐。"),
        ("一期已完成", "现场答复相关功能已实现，待真实环境验证。")]
yy = 1.95
for t, d in pts_:
    text(s, rx, yy, 4.2, 0.3, t, size=11.5, color=INK, bold=True)
    text(s, rx, yy + 0.32, 4.2, 0.7, d, size=10, color=BODY, lsp=1.25)
    yy += 0.95
footer(s, 10, TOTAL)

# ---------------------------------------------------------------- 11 知识库架构
s = S()
header(s, "方法", "知识库：事实由工具抽取，理解由模型撰写并经人确认")
def node(x, y, w, h, title, sub, fill=WHITE, line_=INK, tc=INK, sc=MUTED, dash=False):
    label_box(s, x, y, w, h, [[(title, {"bold": True, "color": tc, "size": 10.5})], [(sub, {"color": sc, "size": 8.5})]],
              fill=fill, line=line_, lw=0.9, dash=dash)
Y = 1.75
node(0.6, Y, 1.75, 0.95, "源代码", "Java · .NET · SQL · 配置")
node(2.75, Y, 2.0, 0.95, "静态解析", "不调用模型")
node(5.15, Y, 2.0, 0.95, "知识图谱", "随代码增量更新")
for xa, xb in ((2.35, 2.75), (4.75, 5.15), (7.15, 7.55)):
    line(s, xa, Y + 0.475, xb, Y + 0.475, INK, 1.0, arrow=True)
# Wiki 大框
wx, wy, ww, wh = 7.55, 1.5, 2.55, 3.05
box(s, wx, wy, ww, wh, ACCENT_T, ACCENT, 1.0)
text(s, wx + 0.12, wy + 0.08, ww - 0.2, 0.5, [[("业务 Wiki", {"bold": True, "color": ACCENT, "size": 10.5})], "模型写、人确认，自底向上"], size=8.5, color=MUTED, lsp=1.1)
levels = ["系统总览", "业务域", "模块", "业务对象（表）", "业务流"]
for i, lv in enumerate(levels):
    yy = wy + 0.68 + i * 0.45
    label_box(s, wx + 0.3, yy, ww - 0.6, 0.32, lv, fill=WHITE, line=ACCENT_M, size=9, color=INK)
    if i < len(levels) - 1:
        line(s, wx + ww / 2, yy + 0.45, wx + ww / 2, yy + 0.32, ACCENT, 0.75, arrow=True)
# 出口
node(10.5, 1.75, 2.23, 0.95, "按需读取", "只取相关页面原文", fill=WHITE)
line(s, 10.1, Y + 0.475, 10.5, Y + 0.475, INK, 1.0, arrow=True)
node(10.5, 3.05, 2.23, 0.95, "人与编程助手", "平台 · IDE · 群聊", fill=WHITE)
line(s, 11.615, 2.7, 11.615, 3.05, INK, 1.0, arrow=True)
# 回流环
Y2 = 4.95
node(0.6, Y2, 2.35, 0.8, "代码改动（diff）", "工单采纳后", line_=MUTED)
node(3.35, Y2, 2.7, 0.8, "影响比对", "只把受影响的页标为过期", line_=MUTED)
node(6.45, Y2, 2.6, 0.8, "修订", "只重写过期页", line_=MUTED)
line(s, 2.95, Y2 + 0.4, 3.35, Y2 + 0.4, MUTED, 1.0, arrow=True)
line(s, 6.05, Y2 + 0.4, 6.45, Y2 + 0.4, MUTED, 1.0, arrow=True)
line(s, 8.6, Y2, 8.6, wy + wh, MUTED, 1.0, arrow=True)
node(9.45, Y2, 3.28, 0.8, "业务方答复", "原话写回，只有人能写", line_=MUTED)
line(s, 10.0, Y2, 9.6, wy + wh, MUTED, 1.0, arrow=True)
line(s, 1.775, Y2, 1.775, Y + 0.95, FAINT, 0.75, dash=True)
text(s, 1.85, 3.9, 2.4, 0.3, "代码在变", size=8, color=FAINT)
# 底部：页面结构 + 原则
box(s, 0.6, 6.0, 6.0, 0.82, PANEL)
text(s, 0.75, 6.05, 5.8, 0.75, [[("事实与理解分开  ", {"bold": True, "color": INK}), ("事实由工具生成，可核对到代码行；理解由模型撰写，经人确认。", {})]], size=9.5, color=BODY, lsp=1.3, anchor="m")
box(s, 6.75, 6.0, 5.98, 0.82, ACCENT_T)
text(s, 6.9, 6.05, 5.7, 0.75, [[("只认一份知识。", {"bold": True, "color": ACCENT}),
                                ("使用时读取原文，不做二次摘要，避免信息再次损失。", {})]], size=9.5, color=BODY, lsp=1.3, anchor="m")
footer(s, 11, TOTAL, "[14] GitHub Copilot 记忆   [24] RepoDoc")

# ---------------------------------------------------------------- 12 现场答复
s = S()
header(s, "方法", "现场答复：模型只做选择题，把握度从概率中读出")
Y = 1.7
node(0.6, Y, 1.9, 1.1, "需求原文", "群聊 · 工单 · 平台")
node(2.85, Y, 2.1, 1.1, "取相关知识", "相关业务流与业务域原文")
line(s, 2.5, Y + 0.55, 2.85, Y + 0.55, INK, 1.0, arrow=True)
# 三道单选
qx, qw = 5.3, 3.3
box(s, qx, 1.5, qw, 2.6, ACCENT_T, ACCENT, 1.0)
text(s, qx + 0.15, 1.58, qw - 0.3, 0.3, "三道选择题", size=10.5, color=ACCENT, bold=True)
qs3 = [("怎么处理", "直接答复 / 需改代码 / 与规则冲突 / 需问业务方"),
       ("依据哪一页", "从相关知识页中选"),
       ("该问谁", "从已知答复人中选")]
yy = 1.95
for i, (t, d) in enumerate(qs3):
    text(s, qx + 0.15, yy, qw - 0.3, 0.25, "%d  %s" % (i + 1, t), size=9.5, color=INK, bold=True)
    text(s, qx + 0.52, yy + 0.25, qw - 0.65, 0.45, d, size=8.5, color=BODY, lsp=1.15)
    yy += 0.7
line(s, 4.95, Y + 0.55, 5.3, Y + 0.55, INK, 1.0, arrow=True)
# 概率
node(9.0, 1.5, 3.73, 1.15, "把握度", "由选项概率计算；把握不足即交人")
line(s, 8.6, 2.07, 9.0, 2.07, INK, 1.0, arrow=True)
label_box(s, 9.0, 2.95, 3.73, 1.15, [[("规则兜底（只降不升）", {"bold": True, "color": GAP, "size": 10})],
          [("涉及资金、审批、统计口径时，依据未确认一律交人", {"size": 8.5, "color": BODY})]], fill=GAP_T, line=GAP, lw=0.9)
line(s, 10.865, 2.65, 10.865, 2.95, INK, 1.0, arrow=True)
# 输出
Y3 = 4.55
node(5.3, Y3, 3.3, 0.85, "直接答复", "固定句式，附依据", line_=ACCENT, tc=ACCENT)
node(9.0, Y3, 3.73, 0.85, "转人工", "派给对应的答复人", line_=GAP, tc=GAP)
line(s, 10.0, 4.1, 7.6, Y3, INK, 0.75, arrow=True)
line(s, 10.865, 4.1, 10.865, Y3, INK, 0.75, arrow=True)
node(9.0, 5.75, 3.73, 0.8, "答复写回知识库", "同类问题下次可直接答", line_=MUTED)
line(s, 10.865, Y3 + 0.85, 10.865, 5.75, MUTED, 1.0, arrow=True)
line(s, 9.0, 6.15, 3.9, 6.15, MUTED, 1.0, arrow=False)
line(s, 3.9, 6.15, 3.9, Y + 1.1, MUTED, 1.0, arrow=True)
text(s, 4.0, 5.85, 4.8, 0.3, "回流：确认的页越多，能直接答的越多", size=8.5, color=MUTED)
# 左下：为什么
text(s, 0.6, 3.15, 3.0, 0.3, "为什么这样设计", size=10, color=MUTED, bold=True)
text(s, 0.6, 3.5, 3.0, 2.2, [
    "模型擅长在给定选项中判断，不擅长自由作答。",
    "公开案例中自动答复约一半有帮助 [9]，转人工是主路径之一。",
], size=9.5, color=BODY, lsp=1.3, space_after=5)
footer(s, 12, TOTAL, "[9] Uber Genie   [20] System One")

# ---------------------------------------------------------------- 13 人机接口与无人化分级
s = S()
header(s, "方法", "自动化分四级，按工单风险选择")
lv = [("问答", "人提问，知识库作答，附代码位置和把握度", "人：提问、判断", "现场答复"),
      ("辅助", "开发在自己的工具里工作，知识自动送到", "人：写代码", "复杂需求"),
      ("半自动", "智能体完成修改，人审核后采纳", "人：审核、验收", "当前默认"),
      ("无人值守", "低风险工单通过检查后自动完成", "人：只验收", "由试点数据决定范围")]
bx, bw, base = 0.6, 2.95, 5.8
for i, (t, d, who, fit) in enumerate(lv):
    x = bx + i * (bw + 0.11)
    h = 1.5 + i * 0.55
    y = base - h
    fill = [WHITE, ACCENT_T, ACCENT_M, ACCENT][i]
    tc = WHITE if i == 3 else INK
    box(s, x, y, bw, h, fill, ACCENT if i < 2 else None, 0.9)
    text(s, x + 0.15, y + 0.12, bw - 0.3, 0.35, t, size=13, color=tc, bold=True)
    text(s, x + 0.15, y + 0.5, bw - 0.3, 0.9, d, size=9.5, color=tc, lsp=1.2)
    text(s, x, base + 0.08, bw, 0.25, who, size=9.5, color=INK, bold=True)
    text(s, x, base + 0.34, bw, 0.25, "适用：" + fit, size=9, color=MUTED)
line(s, 0.6, 1.62, 3.6, 1.62, FAINT, 0.75, arrow=True)
text(s, 3.7, 1.5, 4, 0.25, "自动化程度提高，人出现的点减少", size=8.5, color=MUTED)
footer(s, 13, TOTAL)

# ---------------------------------------------------------------- 14 实测
s = S()
header(s, "实测", "55 万行的财务共享平台：不调用模型，抽出 3,079 条业务流")
rows = [["项目", "数值"],
        ["代码规模", "约 55 万行 Java，98% 来自反编译"],
        ["Java 源文件 / 类 / 方法", "2,673 / 2,740 / 37,449"],
        ["接口 / 定时任务", "2,918 / 161"],
        ["业务流 / 表 / 业务域", "3,079 / 802 / 114"],
        ["还原的状态机", "170"],
        ["一句中文需求定位到代码", "约 5 秒"],
        ]
table(s, 0.6, 1.6, 6.3, [2.6, 3.7], rows, size=10.5, row_h=0.43, first_bold=True)
caption(s, 0.6, 4.75, 6.3, "表 3", "分析全部在本地完成，源码不外传。")
text(s, 0.6, 5.3, 6.3, 1.0, [
    [("小型 OA 项目：", {"bold": True, "color": INK}), ("全量分析约 3 分 40 秒；改动一个方法后，增量更新 56 秒。", {})],
], size=10, color=BODY, lsp=1.3)
cd = CategoryChartData()
cd.categories = ["改进前", "改进后"]
cd.add_series("能追到数据库表的业务流占比", (0.069, 0.690))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(7.45), Inches(1.9), Inches(5.2), Inches(3.6), cd)
ch = gf.chart
ch.has_title = False
ch.has_legend = False
ch.font.size = Pt(10)
ch.font.name = LATIN
pl = ch.plots[0]
pl.gap_width = 90
ser = pl.series[0]
ser.format.fill.solid(); ser.format.fill.fore_color.rgb = rgb(ACCENT)
pt0 = ser.points[0]; pt0.format.fill.solid(); pt0.format.fill.fore_color.rgb = rgb(FAINT)
pl.has_data_labels = True
pl.data_labels.number_format = "0.0%"
pl.data_labels.number_format_is_linked = False
pl.data_labels.font.size = Pt(13); pl.data_labels.font.bold = True
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
va = ch.value_axis; va.visible = False; va.has_major_gridlines = False; va.maximum_scale = 0.85; va.minimum_scale = 0
ch.category_axis.format.line.color.rgb = rgb(RULE)
ch.category_axis.tick_labels.font.size = Pt(10.5)
text(s, 7.45, 1.55, 5.2, 0.3, "业务流能追到数据库表的比例", size=10.5, color=INK, bold=True)
caption(s, 7.45, 5.55, 5.3, "图 5", "补全数据访问层解析之后。")
footer(s, 14, TOTAL)

# ---------------------------------------------------------------- 15 定位对照
s = S()
header(s, "实测", "有业务理解的部分，需求定位准确")
cases = [
    ("案例 A · 审批域", "已写理解页", ACCENT, "批量审批要记录真实审批人，任一单据失败整批回滚",
     ["排在最前的正是“批量审批”相关页面，现有问题已写明",
      "直接给出需要修改的代码位置",
      "无需通读 55 万行代码即可动手"], "准确"),
    ("案例 B · 银行域", "只有代码事实", GAP, "银行流水自动匹配收款单的金额容差改为 0.01 元",
     ["找到了匹配逻辑所在的代码，方向正确",
      "但排在第一的业务流不相关",
      "原因：这部分还没有业务层的说明"], "半准"),
]
for i, (t, tag, c, req, steps, verdict) in enumerate(cases):
    x = 0.6 + i * 6.17
    line(s, x, 1.6, x + 5.95, 1.6, c, 2.0)
    text(s, x, 1.72, 4.2, 0.35, t, size=13, color=INK, bold=True)
    text(s, x + 4.0, 1.75, 1.95, 0.3, tag, size=9.5, color=c, bold=True, align="r")
    text(s, x, 2.15, 1.0, 0.25, "需求原文", size=8.5, color=MUTED)
    box(s, x, 2.42, 5.95, 0.62, PANEL)
    text(s, x + 0.15, 2.42, 5.7, 0.62, "“" + req + "”", size=11, color=INK, anchor="m")
    yy = 3.3
    for j, st in enumerate(steps):
        text(s, x, yy, 0.3, 0.3, str(j + 1), size=11, color=c, bold=True)
        text(s, x + 0.35, yy, 5.6, 0.6, st, size=10.5, color=BODY, lsp=1.25)
        yy += 0.68
    text(s, x, 5.45, 5.95, 0.4, [[("结果：", {"color": MUTED}), (verdict, {"bold": True, "color": c})]], size=13)
box(s, 0.6, 6.05, 12.13, 0.7, ACCENT_T)
text(s, 0.8, 6.1, 11.8, 0.6, [[("对应假设：", {"bold": True, "color": ACCENT}), ("知识库按工单涉及的业务逐步补全，投入集中在真正用到的部分。命中率需在试点中统计。", {})]], size=10.5, color=BODY, anchor="m")
footer(s, 15, TOTAL)

# ---------------------------------------------------------------- 16 覆盖现状
s = S()
header(s, "实测", "知识库已初步建成，下一步是人工确认")
cd = CategoryChartData()
cats = ["业务域", "系统总览", "业务流", "业务对象", "模块"]
written = [114, 1, 17, 0, 0]
total = [114, 1, 1208, 347, 1]
cd.categories = ["%s  %d / %s" % (c, w, format(t, ",")) for c, w, t in zip(cats, written, total)]
cd.add_series("已写（待确认）", written)
cd.add_series("未分析", [t - w for t, w in zip(total, written)])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(0.6), Inches(1.6), Inches(7.8), Inches(4.0), cd)
ch = gf.chart
ch.has_title = False
ch.font.size = Pt(10); ch.font.name = LATIN
ch.has_legend = True; ch.legend.position = XL_LEGEND_POSITION.TOP; ch.legend.include_in_layout = False
pl = ch.plots[0]; pl.gap_width = 55; pl.overlap = 100
for ser, c in zip(pl.series, (ACCENT, "E4E3DE")):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = rgb(c)
pl.has_data_labels = False
ca = ch.category_axis; ca.reverse_order = True; ca.format.line.color.rgb = rgb(RULE)
va = ch.value_axis; va.has_major_gridlines = False; va.visible = False
caption(s, 0.6, 5.7, 7.6, "图 6", "知识库各类页面的撰写进度。")
rx = 8.9
kpis = [("132", "页已撰写"), ("290", "处待确认"), ("7", "个问题待业务方答复")]
yy = 1.6
for v, l in kpis:
    text(s, rx, yy, 1.6, 0.6, v, size=28, color=INK, bold=True)
    text(s, rx + 1.7, yy + 0.17, 2.3, 0.5, l, size=11, color=MUTED)
    yy += 0.78
text(s, rx, 4.2, 3.9, 1.3, "确认之前，问题都会转人工。试点中每次人工答复都会写回并推动确认。", size=10.5, color=BODY, lsp=1.3)
footer(s, 16, TOTAL)

# ---------------------------------------------------------------- 17 路线图
s = S()
header(s, "路线", "先答得快，再改得稳，最后让翻新看得见")
pm = {p: [m for m in MODS if m["phase"] == p] for p in (1, 2, 3)}
cw3 = 3.95
for i, p in enumerate(PHASES):
    x = 0.6 + i * (cw3 + 0.14)
    main = i == 0
    box(s, x, 1.6, cw3, 4.65, ACCENT_T if main else WHITE, ACCENT if main else RULE, 1.5 if main else 0.75)
    text(s, x + 0.2, 1.72, cw3 - 0.4, 0.4, "%s期 · %s" % ("一二三"[i], p["name"]), size=15, color=INK, bold=True)
    text(s, x + 0.2, 2.15, cw3 - 0.4, 0.3, p["goal"], size=10, color=MUTED)
    st_c = ACCENT if main else FAINT
    label_box(s, x + 0.2, 2.5, 2.4 if main else 1.0, 0.27, p["state"], fill=ACCENT if main else PANEL, size=8.5, color=WHITE if main else MUTED, bold=True)
    line(s, x + 0.2, 2.95, x + cw3 - 0.2, 2.95, RULE, 0.5)
    yy = 3.08
    for m in pm[p["n"]]:
        glyph(s, x + 0.22, yy + 0.07, m["status"], 0.11)
        text(s, x + 0.42, yy, cw3 - 0.6, 0.28, m["name"], size=10, color=BODY)
        yy += 0.32
    line(s, x + 0.2, 5.25, x + cw3 - 0.2, 5.25, RULE, 0.5)
    text(s, x + 0.2, 5.33, cw3 - 0.4, 0.85, [[("过关：", {"bold": True, "color": INK}), (p["gate"], {})]], size=10, color=BODY, lsp=1.25)
    if i < 2:
        line(s, x + cw3 + 0.01, 2.0, x + cw3 + 0.13, 2.0, ACCENT, 1.25, arrow=True)
text(s, 0.6, 6.38, 12.1, 0.5, "其余功能按试点项目的实际需要安排。", size=9.5, color=MUTED, lsp=1.25)
footer(s, 17, TOTAL)

# ---------------------------------------------------------------- 18 度量
s = S()
header(s, "度量", "提效只看三类数：答复更快、交付更快、少找人")
rows = [["指标", "定义", "口径", "主指标所在期", "现在能采吗"],
        ["答复时长", "需求人员提问到拿到可行性结论的时间", "答复更快", "一期", "能"],
        ["自动答复采纳率", "自动答复未被开发推翻的比例", "少找人", "一期", "能"],
        ["找开发次数", "每周转人工的提问数，对比上线前", "少找人", "一期", "能，需上线前基线"],
        ["工单周期", "从提出到验收通过，对比 Jira / 禅道基线", "交付更快", "二期", "能"],
        ["无人化占比与退回率", "自动跑完的工单数及其验收退回比例", "交付更快", "二期", "待建"],
        ["改造完成度", "已改造并通过新旧对比的业务流占比", "交付更快", "三期", "待建"]]
table(s, 0.6, 1.6, 12.13, [2.0, 4.35, 1.4, 1.5, 2.88], rows, size=10.5, row_h=0.5, first_bold=True)
caption(s, 0.6, 5.2, 12.1, "表 4", "全部从流程中自动采集，无需额外填报。")
box(s, 0.6, 5.6, 12.13, 1.1, PANEL)
text(s, 0.8, 5.65, 11.8, 1.0, [
    [("速度与返工并列报告：", {"bold": True, "color": INK}),
     ("AI 采用率每提高 25%，交付稳定性下降 7.2% [13]。", {})],
    [("基线：", {"bold": True, "color": INK}),
     ("以试点项目过去 3～6 个月的工单历史为准。", {})],
], size=10.5, color=BODY, lsp=1.35, space_after=4, anchor="m")
footer(s, 18, TOTAL, "[13] DORA 2024")

# ---------------------------------------------------------------- 19 局限
s = S()
header(s, "局限", "已验证能抽取、能定位、能闭环；真实环境的效果待试点验证")
rows = [["方面", "已验证", "待验证"],
        ["模型", "主流编程助手上跑通全流程", "国产模型的撰写质量"],
        ["外部系统", "工单系统与群机器人在模拟环境测试", "真实工单系统与群聊联调"],
        ["规模", "55 万行项目", "更多项目；定位命中率样本"],
        ["知识正确性", "事实可核对到代码行", "人工确认；反编译代码与线上版本核对"],
        ["度量", "指标可从流程采集", "带基线的实测提效数据"]]
table(s, 0.6, 1.6, 12.13, [1.65, 4.6, 5.88], rows, size=10.5, row_h=0.66, first_bold=True, colors=[BODY, BODY, GAP])
caption(s, 0.6, 5.75, 12.1, "表 5", "由第一个试点回答。")
footer(s, 19, TOTAL)

# ---------------------------------------------------------------- 20 立项请求
s = S()
header(s, "下一步", "试点需要确认三件事")
dec = [("1", "试点范围", "选定一个项目，以及若干高频业务", "先运行 4 周得到基线，再定过关标准。"),
       ("2", "接入渠道", "钉钉、飞书、企业微信，先接哪一个？", "三种接口均已具备，选一个在真实群聊中联调。"),
       ("3", "业务确认人", "每个业务域指定一位确认人", "知识页经确认后，才用于直接答复。")]
yy = 1.65
for n, t, q, d in dec:
    line(s, 0.6, yy, 12.73, yy, RULE, 0.5)
    text(s, 0.6, yy + 0.15, 0.6, 0.8, n, size=34, color=ACCENT, bold=True)
    text(s, 1.35, yy + 0.2, 3.0, 0.4, t, size=15, color=INK, bold=True)
    text(s, 4.4, yy + 0.2, 8.3, 0.45, q, size=13, color=INK)
    text(s, 4.4, yy + 0.68, 8.3, 0.6, d, size=10.5, color=MUTED, lsp=1.25)
    yy += 1.45
line(s, 0.6, yy, 12.73, yy, RULE, 0.5)
footer(s, 20, TOTAL)

# ---------------------------------------------------------------- 21 参考文献
s = S()
header(s, "参考文献", "参考文献")
refs = [
    "[1] Xia 等. Measuring Program Comprehension. ICSE 2018.",
    "[2] Stack Overflow. 2024 Developer Survey insights.",
    "[3] Gloria Mark 的打断研究，经 Fast Company 报道.",
    "[4] Avelino 等. Truck factor. arXiv 1604.06766.",
    "[5] METR. Early-2025 AI on experienced OS devs. 2025-07.",
    "[6] METR. Uplift update. 2026-02.",
    "[7] Meta Engineering. Map tribal knowledge in data pipelines. 2026-04.",
    "[8] The Register. Gartner mainframe exit analysis. 2026-04.",
    "[9] Uber. Genie: Gen AI on-call copilot.",
    "[10] Consortium for Service Innovation. KCS v6.",
    "[11] Alshahwan 等. TestGen-LLM. arXiv 2402.09171.",
    "[12] GitHub. Scientist: move fast and fix things.",
    "[13] Google Cloud. DORA 2024 report.",
    "[14] GitHub. Agentic memory for Copilot. 2026-01.",
    "[15] Moderne. Gartner MQ Leader 新闻稿. 2026-08-05.",
    "[16] Sourcegraph. Agentic Batch Changes public beta. 2026-06.",
    "[17] Codemod 官网与 Express 5 迁移指南.",
    "[18] InfoQ. CodeScene agentic refactoring case. 2026-09.",
    "[19] vFunction. Power for Kiro. 2026.",
    "[20] typesafe.ai. Introducing System One models and Jev.",
    "[21] Gartner Peer Community. 回归测试手工占比投票.",
    "[22] Microsoft. RCACopilot. arXiv 2305.15778.",
    "[23] Martin Fowler. Strangler Fig Application.",
    "[24] RepoDoc. arXiv 2604.26523.",
]
half_ = (len(refs) + 1) // 2
text(s, 0.6, 1.55, 6.0, 5.2, refs[:half_], size=9.5, color=BODY, lsp=1.3, space_after=3)
text(s, 6.75, 1.55, 6.0, 5.2, refs[half_:], size=9.5, color=BODY, lsp=1.3, space_after=3)
footer(s, 21, TOTAL)

strip_styles(prs)
prs.save(OUT)
print("saved", OUT, len(prs.slides))
