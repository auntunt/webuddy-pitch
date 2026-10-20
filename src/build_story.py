import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 「一张工单的经过」：用示例项目里一张真实缺陷单（JB-17，取自 JeecgBoot 开源仓库）讲谁做了什么。
# 用有轴的表，不用卡片和时间轴；人做的行铺浅底色。内容均取自 截图-新/02 的工单详情。

ROWS = [
    ("提交问题", "报告人", "在接口文档页面测试接口时，请求没有自动带上登录凭证，测不了。", True),
    ("找原因", "智能体", "查了 29 处相关代码，确认是接口文档的凭证配置和后台的读取方式对不上。", False),
    ("出方案", "智能体", "只改一个配置文件，业务接口和数据库都不动。", False),
    ("改代码", "智能体", "改动放在单独的分支上，正式代码保持原样。", False),
    ("验收", "验收人", "在页面上实际试一遍：通过就关单；不通过写明原因退回，智能体照着重改。这张单正在等这一步。", True),
]


def table_slide(s, kicker, ttl, rows, note_text):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, kicker, size=11, color=MUTED, bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, ttl, size=26, color=INK, bold=True)

    X0, W = 0.6, 12.13
    C1, C2 = 1.75, 1.55          # 步骤、谁来做 两列宽；其余给“发生了什么”
    y = 2.05
    for t, x, w in [("步骤", X0, C1), ("谁来做", X0 + C1, C2), ("这一单上发生了什么" if "工单" in kicker else "这个项目上发生了什么", X0 + C1 + C2, W - C1 - C2)]:
        text(s, x + 0.15, y, w - 0.3, 0.3, t, size=11, color=MUTED, bold=True)
    y += 0.42
    line(s, X0, y, X0 + W, y, INK, 1.25)
    RH = min(0.82, 4.35 / len(rows))
    for step, who, what, human in rows:
        if human:
            box(s, X0, y + 0.02, W, RH - 0.04, "EEF2FA", None)
        text(s, X0 + 0.15, y, C1 - 0.3, RH, step, size=15, color=INK, bold=True, anchor="m")
        text(s, X0 + C1 + 0.15, y, C2 - 0.3, RH, who, size=13, color=ACCENT if human else BODY,
             bold=human, anchor="m")
        text(s, X0 + C1 + C2 + 0.15, y, W - C1 - C2 - 0.3, RH, what, size=13, color=BODY, anchor="m", lsp=1.35)
        y += RH
        line(s, X0, y, X0 + W, y, RULE, 0.75)
    notes(s, note_text)


def story_slide(s):
    table_slide(s, "运维 · 一张工单的经过", "修好一张接口文档的缺陷，人只需要在最后验收", ROWS,
                "工单取自 JeecgBoot 开源仓库，在示例项目里由平台处理，界面截图见缺陷修复那页。"
                "原因已读代码核实：Swagger3Config.java 第 97–99 行把 X-Access-Token 声明成了 HTTP 鉴权，后台读取的是同名自定义请求头。"
                "改动在分支 tmh/JB-17-r215。这张单处理时设置为不跑构建测试，没有经过测试机；目前停在人工验收。")


# 重构的实例：RealWorld 的 .NET 后端改写为 Java + 达梦。数字取自 汇报PPT/重构实测/RealWorld重写测试报告.md
REF_ROWS = [
    ("定目标", "项目负责人", "把开源项目 RealWorld 的 .NET 后端改写成 Java，数据库换成达梦；对外接口一个都不能变。", True),
    ("拆分", "平台", "分成一个公共骨架和 7 个业务域，按和其他域共用表的多少排先后。", False),
    ("改骨架", "智能体", "工程、配置、建表脚本、登录鉴权一次做好，用了约 20 分钟。", False),
    ("验收骨架", "验收人", "骨架通过后，7 个业务域一次全部放出。", True),
    ("改业务域", "智能体", "7 个域并行改，每个用了 24 到 41 分钟。6 个编译通过；要求的 19 个接口做出了 18 个。", False),
    ("逐域验收", "验收人", "6 个域在等验收；编译没过的那个域正在重改。", True),
]


def refactor_story_slide(s):
    table_slide(s, "重构 · 一次改写的经过", "把一个 .NET 项目改写成 Java，人在开头定规矩，在每一批结束时验收", REF_ROWS,
                "RealWorld 是有官方 .NET 和 Java 两个实现的开源项目，用来对照。Java 参考版放在项目外，改代码的智能体看不到。"
                "8 个部分里 7 个在测试机上编译通过：没过的是“文章标签”域（RW-2）；“用户资料查询”域（RW-3）漏了 GET /api/profiles/{username}。"
                "这一轮没有跑接口测试，只能说编译通过、接口 18/19，不能说功能已验证。达梦目前只做到写法和配置，测试机上用 H2。")

if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "story.pptx"
    prs = new_deck()
    story_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
