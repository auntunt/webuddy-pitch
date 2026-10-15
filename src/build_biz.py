import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 商业化两页。依据：定位/商业交付模式-思路.md（第 0、2、4、5 节）。没有价格，文档里也没有定价。


def head(s, kicker, ttl):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, kicker, size=11, color=MUTED, bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, ttl, size=26, color=INK, bold=True)


STEPS = [("进场体检", "首次全项目分析，交付《项目体检报告》：业务地图、风险点、改造建议", "一次性小额收费", "E8EEF9", INK),
         ("试点", "在一个项目上跑 6 到 8 周，交付带基线对比的提效报告", "固定价，报告作为续签依据", "C9D6F0", INK),
         ("年度维保包", "工单闭环、需求答复、缺陷修复，每季度一份提效报告", "按系统规模和工单量分档，年付", "6F8FD6", WHITE),
         ("重构 / 信创改造包", "按业务域分批改造，每批验收后再放下一批", "按业务域报固定价，每个域验收通过才收这一段", ACCENT, WHITE)]


def sales_slide(s):
    head(s, "商业化方案", "从一次体检开始，一步步走到长期维保和改造")
    base, w, g = 6.6, 2.92, 0.15
    for i, (nm, what, fee, fill, tc) in enumerate(STEPS):
        h = 2.35 + i * 0.66
        x, y = 0.6 + i * (w + g), base - h
        box(s, x, y, w, h, fill, None)
        text(s, x + 0.22, y + 0.18, w - 0.4, 0.4, nm, size=17, color=tc, bold=True)
        sub = "B7C2D6" if tc == WHITE else MUTED
        text(s, x + 0.22, y + 0.66, w - 0.4, 0.85, what, size=11.5, color=tc, lsp=1.35)
        text(s, x + 0.22, y + h - 0.62, w - 0.4, 0.5, [[("收费  ", {"bold": True}), (fee, {})]],
             size=10.5, color=tc if tc == INK else "E4EBFA", lsp=1.3, anchor="b")
    # 顶部一条走向说明
    text(s, 0.6, 1.62, 9, 0.3, "每一步的交付物，就是客户决定是否进入下一步的依据", size=12, color=MUTED)
    notes(s, "按咨询公司的打法：先用低门槛的体检进场，让客户看到我们比原乙方更懂他的系统；试点交付带基线的提效报告；"
             "再转成年度维保合同（主收入和现金流）；重构和信创改造按业务域分批报价，验收一段收一段。"
             "AI 用量打包进维保费，不单列，政企不喜欢不确定的账单。目前没有定价，价格按项目规模另议。")


STAGES = ["自营", "授权", "平台"]
ROWS = [("卖给谁", ["自有老系统、需要维保的政企甲方", "其他维保乙方、区域集成商", "老系统多的大型甲方"]),
        ("怎么交付", ["我们做维保乙方，平台装在客户内网，由我们运营", "授权他们用平台，规则库更新仍由我们出",
                     "企业 AI 平台进入信创目录，直接销售"]),
        ("收什么钱", ["年度维保费、重构包", "授权年费、规则库更新订阅、AI 点数", "平台授权，更多 harness 按模块收费"]),
        ("进入下一步的标志", ["三到五个标杆项目和提效报告", "经验库能脱离我们自己的团队规模增长", "—"])]


def model_slide(s):
    head(s, "", "Webuddy 商业化策略")
    X0, KW = 0.6, 2.2
    CW = (12.13 - KW) / 3
    y = 1.95
    for i, st in enumerate(STAGES):
        x = X0 + KW + i * CW
        box(s, x + 0.05, y, CW - 0.1, 0.5, [ACCENT, "6F8FD6", "C9D6F0"][i], None)
        text(s, x + 0.25, y, CW - 0.4, 0.5, [[("第 %d 步  " % (i + 1), {"size": 11}), (st, {"bold": True, "size": 15})]],
             color=WHITE if i < 2 else INK, anchor="m")
    y += 0.62
    for k, vals in ROWS:
        rh = 0.82
        text(s, X0, y, KW - 0.2, rh, k, size=12.5, color=MUTED, bold=True, anchor="m")
        for i, v in enumerate(vals):
            text(s, X0 + KW + i * CW + 0.25, y, CW - 0.45, rh, v, size=12.5, color=INK, anchor="m", lsp=1.35)
        y += rh
        line(s, X0, y, 12.73, y, RULE, 0.75)
    text(s, X0, y + 0.3, 12.1, 0.6, [[("门槛  ", {"bold": True, "color": INK}),
                                      ("交付中攒下的规则、评测集和教训；客户那边越用越准的知识库；信创互认和软著；标杆案例和提效报告。", {})]],
         size=12.5, color=BODY, lsp=1.4)
    notes(s, "依据定位/商业交付模式-思路.md。我们不是咨询公司：按人天收钱时平台越好收入越少；维保模式下效率提升归我们自己。"
             "也不先卖软件：政企采购周期长，装了没人用、续费难。代码、提示词、用哪个模型都不是门槛。")


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "biz.pptx"
    prs = new_deck()
    sales_slide(blank(prs))
    model_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
