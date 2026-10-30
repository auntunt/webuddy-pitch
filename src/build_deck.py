import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pptkit import *

# 业务视角版：以“业务应用 / 智能体编排 / 代码知识库”三层架构为主线，不列内部功能模块。
OUT = sys.argv[1] if len(sys.argv) > 1 else "deck.pptx"
TOTAL = 15
prs = new_deck()
_n = [0]


def PN():
    _n[0] += 1
    return _n[0]


def S():
    return blank(prs)


DECK = "运维智能体 · 立项汇报"


def hdr(s, section, title):
    header(s, section, title, deck=DECK)


# 三层架构的内容，架构页和分解页共用
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

# ---------------------------------------------------------------- 封面
s = S(); PN()
box(s, 0.6, 1.55, 0.08, 2.1, ACCENT)
text(s, 0.95, 1.45, 11, 0.5, "立项汇报", size=12, color=ACCENT, bold=True)
text(s, 0.95, 1.9, 11.5, 1.0, "运维智能体", size=44, color=INK, bold=True)
text(s, 0.95, 2.85, 11.5, 0.6, "一套底座，多种维保服务", size=20, color=BODY)
text(s, 0.95, 4.35, 8, 0.9, ["Li", "2026 年 10 月"], size=12, color=MUTED, lsp=1.3)

# ---------------------------------------------------------------- 摘要
s = S()
hdr(s, "摘要", "把老项目维保做成五项可交付的服务，由一组分工明确的智能体完成，人只在关键处确认")
text(s, 0.6, 1.55, 6.6, 3.6, [
    "老项目交付之后，维保的成本主要花在找人问、读代码和不敢改上，而不是写代码本身。通用编程助手擅长写新代码，却不了解客户的业务。",
    "运维智能体分三层：底层是从代码梳理出的代码知识库，中间是一套编码智能体按工单流程接力，受理、定位、规划、修改、验证，最后交人验收；上层是客户看到的各项服务。每张工单先评估影响，再决定智能体做到哪一步，人在哪一步确认。",
    "在一个约 55 万行、98% 来自反编译的财务共享平台上，一句中文需求约 5 秒定位到代码。需求答复已经完成，下一步是真实项目试点。",
], size=12.5, color=BODY, lsp=1.35, space_after=9)
text(s, 7.75, 1.55, 5, 0.3, "对客户的三点承诺", size=10, color=MUTED, bold=True)
promise = [
    ("1", "答得快", "需求人员在群里提问，当场得到能不能做的结论和依据。"),
    ("2", "改得稳", "每次改动先评估影响、再验证，停在人工验收，主干由人合入。"),
    ("3", "看得见", "提效和翻新进度从流程里自动统计，不靠填报。"),
]
yy = 1.95
for n, t, d in promise:
    text(s, 7.75, yy, 0.4, 0.4, n, size=20, color=ACCENT, bold=True)
    text(s, 8.25, yy + 0.02, 4.5, 0.3, t, size=12, color=INK, bold=True)
    text(s, 8.25, yy + 0.34, 4.45, 0.6, d, size=10, color=MUTED, lsp=1.25)
    yy += 1.05
line(s, 0.6, 5.45, 12.73, 5.45, RULE, 0.5)
kp = [("5", "类维保服务"), ("6", "步编排，人工验收收口"), ("约 5 秒", "一句中文需求定位到代码"), ("4", "级自动化，按风险选择")]
for i, (v, l) in enumerate(kp):
    x = 0.6 + i * 3.06
    text(s, x, 5.6, 3, 0.6, v, size=28, color=ACCENT, bold=True)
    text(s, x, 6.2, 2.9, 0.5, l, size=10, color=MUTED)
footer(s, PN(), TOTAL)

# ---------------------------------------------------------------- 3 问题：读懂
s = S()
hdr(s, "问题", "维保的成本在“读懂”和“被打断”，不在“改”")
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
footer(s, PN(), TOTAL, "[1] Xia 等, ICSE 2018   [2] Stack Overflow 开发者调查 2024   [3] Gloria Mark，经 Fast Company   [4] arXiv 1604.06766")

# ---------------------------------------------------------------- 4 一线证据
s = S()
hdr(s, "问题", "一线抱怨集中在“知识只在人脑子里”和“不敢改”")
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
footer(s, PN(), TOTAL)


# ---------------------------------------------------------------- 总体架构
s = S()
hdr(s, "总体架构", "一套底座，多种服务：上层五项服务共用同一套编码智能体和代码知识库")
LX, LW = 0.6, 1.5
CX, CW = 2.3, 9.8
rows_y = [(1.45, 1.3), (3.22, 1.8), (5.35, 0.95)]
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
footer(s, PN(), TOTAL, "越用越准：验收教训和评测用例回流到编排，知识修正回流到知识库。可扩展服务尚未开发。")

# ---------------------------------------------------------------- 服务能力
s = S()
hdr(s, "服务能力", "五项服务，各自对应客户最常见的一类诉求")
rows = [["服务", "客户遇到的问题", "我们交付什么", "现在能做到"],
        ["需求答复", "售前和实施判断“能不能做、多久能做”只能去问开发", "群里当场答复：能 / 不能 / 需确认，附依据和代码位置；答不了的转给对的人", SERVICES[0][2]],
        ["日常维护", "改一处坏一处，线上问题定位慢", "告警和报错日志自动开单并对到代码；定位、修改、验证后交人验收", SERVICES[1][2]],
        ["功能扩展", "原作者不在，新功能不知道该加在哪、会碰到什么", "变更方案和影响清单先行，再由智能体实现、验证", SERVICES[2][2]],
        ["系统重构", "推倒重来屡次失败，进度只能听口头汇报", "按业务域拆成改动工单，牵连少的先做试点，再分批放出", SERVICES[3][2]],
        ["系统升级", "依赖老化、信创适配踩坑多", "依赖升级、框架迁移、兼容适配同样按业务域分批，逐单验收", SERVICES[4][2]]]
table(s, 0.6, 1.6, 12.13, [1.45, 3.75, 4.6, 2.33], rows, size=10.5, row_h=0.72, first_bold=True)
caption(s, 0.6, 6.05, 12.1, "表 2", "“人审后采纳”指智能体完成修改，开发审核后合入；能否放开为无人值守，由试点数据决定。")
footer(s, PN(), TOTAL)

# ---------------------------------------------------------------- 人机分工
s = S()
hdr(s, "人机分工", "每张工单先评估影响，再决定智能体做到哪一步、人在哪一步确认")
steps = [("关联业务", "识别是哪类服务，关联到业务域和相关代码"),
         ("影响评估", "找出涉及的业务流、表和定时任务，判断风险高低"),
         ("选择程度", "按类型和风险，决定智能体做到哪一步"),
         ("人工确认", "高风险或把握不足时交人，确认点前置")]
sx, sw_, sg = 0.6, 2.85, 0.24
for i, (t, d) in enumerate(steps):
    x = sx + i * (sw_ + sg)
    box(s, x, 1.6, sw_, 1.35, ACCENT_T if i < 3 else WHITE, ACCENT, 1.0, shape="round")
    text(s, x + 0.18, 1.72, sw_ - 0.36, 0.35, t, size=14, color=ACCENT, bold=True)
    text(s, x + 0.18, 2.12, sw_ - 0.36, 0.8, d, size=10, color=BODY, lsp=1.25)
    if i < 3:
        line(s, x + sw_ + 0.02, 2.27, x + sw_ + sg - 0.02, 2.27, ACCENT, 1.25, arrow=True)
text(s, 0.6, 3.3, 8, 0.3, "按风险选择自动化程度", size=10, color=MUTED, bold=True)
lv = [("问答", "人提问，智能体作答并附依据", "人：提问、判断", "现场答复"),
      ("辅助", "开发自己写，知识自动送到手边", "人：写代码", "复杂需求"),
      ("半自动", "智能体完成修改，人审核后采纳", "人：审核、验收", "当前默认"),
      ("无人值守", "低风险工单通过检查后自动完成", "人：只验收", "范围由试点数据决定")]
bx, bw, base = 0.6, 2.95, 6.2
for i, (t, d, who, fit) in enumerate(lv):
    x = bx + i * (bw + 0.11)
    h = 1.2 + i * 0.4
    y = base - h - 0.55
    fill = [WHITE, ACCENT_T, ACCENT_M, ACCENT][i]
    tc = WHITE if i == 3 else INK
    box(s, x, y, bw, h, fill, ACCENT if i < 2 else None, 0.9)
    text(s, x + 0.15, y + 0.1, bw - 0.3, 0.35, t, size=13, color=tc, bold=True)
    text(s, x + 0.15, y + 0.46, bw - 0.3, 0.7, d, size=9.5, color=tc, lsp=1.2)
    text(s, x, base - 0.47, bw, 0.25, who, size=9.5, color=INK, bold=True)
    text(s, x, base - 0.22, bw, 0.25, "适用：" + fit, size=9, color=MUTED)
footer(s, PN(), TOTAL, "风险自动分级在二期上线；在此之前，自动化程度由人选择。")

# ---------------------------------------------------------------- 智能体分工
s = S()
hdr(s, "智能体编排", "六个环节按工单流程接力，每一步都有交付物，人确认的位置是固定的")
rows = [["环节", "负责", "交付物", "人确认什么"]]
for nm, sub, out, who in AGENTS:
    rows.append([nm, sub, out, who])
table(s, 0.6, 1.6, 12.13, [1.8, 3.2, 4.0, 3.13], rows, size=11, row_h=0.6, first_bold=True)
box(s, 0.6, 6.0, 12.13, 0.72, PANEL)
text(s, 0.8, 6.05, 11.8, 0.62, [[("分工的好处：", {"bold": True, "color": INK}),
     ("每一步的输入输出都留档，哪一步出了问题可以单独返工；五项服务共用这一套编排，新服务接上来不用重做。", {})]],
     size=10.5, color=BODY, anchor="m")
footer(s, PN(), TOTAL)

# ---------------------------------------------------------------- 代码知识库
s = S()
hdr(s, "代码知识库", "共用一份代码知识库：业务讲得清，结论有出处，源码不出内网")
cols = [
    ("业务地图", "老项目的业务说明书", [
        "从代码自动梳理出业务域、业务流和数据表的关系",
        "需求按业务名称就能找到对应代码",
        "代码一改，相关内容自动标记过期"]),
    ("代码证据", "每个结论都有出处", [
        "答复附入口、调用链和文件行号",
        "告警和报错堆栈自动对到代码",
        "每次修改记录依据、模型和改动"]),
    ("项目知识页", "人确认过的才算数", [
        "业务确认人确认后才用于直接答复",
        "开发的答复写回知识页，同类问题下次直接答",
        "按实际用到的业务逐步补全"]),
    ("本地离线", "在客户内网里也能用", [
        "分析全部在本地完成，源码不外传",
        "内网离线安装包，可接国产模型",
        "群机器人支持钉钉、飞书、企业微信"]),
]
cw3 = 2.93
for i, (t, sub, pts) in enumerate(cols):
    x = 0.6 + i * (cw3 + 0.14)
    line(s, x, 1.6, x + cw3, 1.6, ACCENT, 2.0)
    text(s, x, 1.75, cw3, 0.4, t, size=16, color=INK, bold=True)
    text(s, x, 2.2, cw3, 0.3, sub, size=10.5, color=MUTED)
    yy = 2.75
    for p in pts:
        box(s, x, yy + 0.08, 0.08, 0.08, ACCENT)
        text(s, x + 0.22, yy, cw3 - 0.25, 0.6, p, size=11, color=BODY, lsp=1.25)
        yy += 0.68
box(s, 0.6, 5.3, 12.13, 1.3, PANEL)
text(s, 0.85, 5.38, 11.7, 1.15, [
    [("越用越准：", {"bold": True, "color": INK}),
     ("验收不通过记成教训，自动重改；验收通过的工单进入评测集，换模型或改提示词前先回放打分。", {})],
    [("看得见：", {"bold": True, "color": INK}),
     ("答复时长、找开发次数、工单周期从流程里自动统计。", {})],
], size=10.5, color=BODY, lsp=1.35, space_after=4, anchor="m")
footer(s, PN(), TOTAL)

# ---------------------------------------------------------------- 一个例子
s = S()
hdr(s, "一个例子", "一句需求在群里提出，几秒后拿到带依据的答复")
box(s, 0.6, 1.55, 12.13, 0.7, PANEL)
text(s, 0.8, 1.55, 11.8, 0.7, [[("实施人员在群里问：", {"color": MUTED}),
     ("“批量审批时，能不能记录真实审批人？任一单据失败要整批回滚。”", {"bold": True, "color": INK})]], size=12.5, anchor="m")
flow = [("任务受理", "归为需求答复；只问能不能做，按问答处理"),
        ("问题定位", "在代码知识库里找到“批量审批”业务流，已有确认过的说明"),
        ("给出结论", "需改代码，附需要修改的代码位置和依据页"),
        ("人工确认", "实施人员确认范围后，一键转成工单"),
        ("后续接力", "方案规划、开发执行、验证审查依次接手")]
fx, fw, fg = 0.6, 2.3, 0.157
for i, (t, d) in enumerate(flow):
    x = fx + i * (fw + fg)
    main = i < 3
    box(s, x, 2.7, fw, 2.3, ACCENT_T if main else WHITE, ACCENT if main else RULE, 1.0, shape="round")
    text(s, x + 0.15, 2.82, 0.5, 0.4, str(i + 1), size=20, color=ACCENT, bold=True)
    text(s, x + 0.15, 3.32, fw - 0.3, 0.35, t, size=13, color=INK, bold=True)
    text(s, x + 0.15, 3.72, fw - 0.3, 1.2, d, size=10, color=BODY, lsp=1.25)
    if i < 4:
        line(s, x + fw + 0.01, 3.85, x + fw + fg - 0.01, 3.85, ACCENT, 1.0, arrow=True)
box(s, 0.6, 5.35, 12.13, 1.3, WHITE, RULE, 0.75)
text(s, 0.85, 5.45, 11.7, 1.15, [
    [("同样的问题，换一个还没梳理过的业务域：", {"bold": True, "color": INK}),
     ("能找到相关代码，但给不出确定结论，会转给对应的开发。", {})],
    [("开发的答复写回知识页，", {"bold": True, "color": INK}),
     ("下次同类问题就能直接答。知识页按实际用到的业务逐步补全。", {})],
], size=10.5, color=BODY, lsp=1.35, space_after=4)
footer(s, PN(), TOTAL, "示例取自 55 万行财务共享平台的实测。")

# ---------------------------------------------------------------- 14 实测
s = S()
hdr(s, "实测", "55 万行的财务共享平台：自动梳理出 3,079 条业务流，一句需求约 5 秒定位")
rows = [["项目", "数值"],
        ["代码规模", "约 55 万行，98% 来自反编译"],
        ["梳理出的业务流", "3,079 条"],
        ["涉及的数据表 / 业务域", "802 张 / 114 个"],
        ["一句中文需求定位到代码", "约 5 秒"],
        ["改动后知识库更新", "小型项目约 1 分钟"],
        ]
table(s, 0.6, 1.6, 6.3, [2.6, 3.7], rows, size=10.5, row_h=0.5, first_bold=True)
caption(s, 0.6, 4.75, 6.3, "表 3", "分析全部在本地完成，源码不外传。")
rx = 7.6
for i, (v, l) in enumerate([("3,079", "条业务流，按业务域归档"), ("约 5 秒", "一句中文需求定位到代码"), ("源码不外传", "分析全部在本地完成")]):
    yy = 1.6 + i * 1.2
    line(s, rx, yy, 12.73, yy, RULE, 0.5)
    text(s, rx, yy + 0.12, 5.1, 0.6, v, size=28, color=ACCENT, bold=True)
    text(s, rx, yy + 0.72, 5.1, 0.35, l, size=11, color=MUTED)
footer(s, PN(), TOTAL)


# ---------------------------------------------------------------- 路线
s = S()
hdr(s, "路线", "先答得快，再改得稳，最后让翻新看得见")
phases = [
    ("一期 · 答得快", "需求人员少找开发", "已完成，待试点", True,
     ["群里提问，当场答复能不能做", "答不了的转给对的人，答复写回知识页", "相似工单自动提示", "内网离线安装", "“少找人”自动统计"],
     "试点项目自动答复的采纳率达到立项会定的线"),
    ("二期 · 改得稳", "不敢改变成敢改、自动改", "未开始", False,
     ["工单风险自动分级，低风险自动处理", "改动前生成回归清单和测试", "工作量区间估算", "工时自动归集，维保价值账单", "补丁同步到其他客户的分支"],
     "低风险工单无人化后，退回率不高于人工基线"),
    ("三期 · 翻新看得见", "改造进度按业务流可查", "未开始", False,
     ["可重复执行的批量改写", "新旧系统行为对比", "改造进度看板"],
     "一个老项目按看板完成一个业务域的翻新"),
]
cw3 = 3.95
for i, (t, goal, state, main, items, gate) in enumerate(phases):
    x = 0.6 + i * (cw3 + 0.14)
    box(s, x, 1.6, cw3, 4.65, ACCENT_T if main else WHITE, ACCENT if main else RULE, 1.5 if main else 0.75)
    text(s, x + 0.2, 1.72, cw3 - 0.4, 0.4, t, size=15, color=INK, bold=True)
    text(s, x + 0.2, 2.15, cw3 - 0.4, 0.3, goal, size=10, color=MUTED)
    label_box(s, x + 0.2, 2.5, 1.6 if main else 1.0, 0.27, state, fill=ACCENT if main else PANEL, size=8.5,
              color=WHITE if main else MUTED, bold=True)
    line(s, x + 0.2, 2.95, x + cw3 - 0.2, 2.95, RULE, 0.5)
    yy = 3.1
    for it in items:
        box(s, x + 0.22, yy + 0.08, 0.08, 0.08, ACCENT if main else FAINT)
        text(s, x + 0.42, yy, cw3 - 0.6, 0.3, it, size=10.5, color=BODY)
        yy += 0.38
    line(s, x + 0.2, 5.25, x + cw3 - 0.2, 5.25, RULE, 0.5)
    text(s, x + 0.2, 5.33, cw3 - 0.4, 0.85, [[("过关：", {"bold": True, "color": INK}), (gate, {})]], size=10, color=BODY, lsp=1.25)
    if i < 2:
        line(s, x + cw3 + 0.01, 2.0, x + cw3 + 0.13, 2.0, ACCENT, 1.25, arrow=True)
footer(s, PN(), TOTAL, "其余能力按试点项目的实际需要安排。")

# ---------------------------------------------------------------- 18 度量
s = S()
hdr(s, "度量", "提效只看三类数：答复更快、交付更快、少找人")
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
     ("AI 采用率每提高 25%，交付稳定性下降 7.2% [5]。", {})],
    [("基线：", {"bold": True, "color": INK}),
     ("以试点项目过去 3～6 个月的工单历史为准。", {})],
], size=10.5, color=BODY, lsp=1.35, space_after=4, anchor="m")
footer(s, PN(), TOTAL, "[5] DORA 2024")

# ---------------------------------------------------------------- 20 立项请求
s = S()
hdr(s, "下一步", "试点需要确认三件事")
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
footer(s, PN(), TOTAL)


# ---------------------------------------------------------------- 参考文献
s = S()
hdr(s, "参考文献", "参考文献")
refs = [
    "[1] Xia 等. Measuring Program Comprehension. ICSE 2018.",
    "[2] Stack Overflow. 2024 Developer Survey insights.",
    "[3] Gloria Mark 的打断研究，经 Fast Company 报道.",
    "[4] Avelino 等. Truck factor. arXiv 1604.06766.",
    "[5] Google Cloud. DORA 2024 report.",
]
text(s, 0.6, 1.55, 12, 5.2, refs, size=10.5, color=BODY, lsp=1.35, space_after=4)
footer(s, PN(), TOTAL)

strip_styles(prs)
prs.save(OUT)
print("saved", OUT, len(prs.slides), "pages counted", _n[0])
