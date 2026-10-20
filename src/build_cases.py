import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 案例二：RealWorld .NET → Java + 达梦。全部事实取自
#   重构探索/RealWorld重写测试-说明.md、汇报PPT/重构实测/RealWorld重写测试报告.md
MONO = "Menlo"


def head(s, kicker, ttl):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, kicker, size=11, color=MUTED, bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, ttl, size=26, color=INK, bold=True)


def kv_table(s, y, rows, kw=1.9, rh=0.62):
    line(s, 0.6, y, 12.73, y, INK, 1.25)
    for k, v, code in rows:
        text(s, 0.6, y, kw, rh, k, size=12.5, color=MUTED, bold=True, anchor="m")
        paras = [[(v, {})]] if not code else [[(v, {}), ("   " + code, {"color": ACCENT, "size": 11})]]
        text(s, 0.6 + kw, y, 12.13 - kw, rh, paras, size=13.5, color=INK, anchor="m", lsp=1.3)
        y += rh
        line(s, 0.6, y, 12.73, y, RULE, 0.75)
    return y


def case2_setup(s):
    head(s, "实测", "案例二：把开源项目 RealWorld 的 .NET 后端改写成 Java + 达梦")
    rows = [("源项目", "官方 ASP.NET Core 版，约 7 千行", "github.com/gothinkster/aspnetcore-realworld-example-app · a51468c"),
            ("对照答案", "官方 Spring Boot 版，放在项目外，改代码的智能体看不到", "github.com/gothinkster/spring-boot-realworld-example-app · ee17e31"),
            ("验收标准", "官方 OpenAPI 规范里的 19 个接口：路径、方法、状态码、JSON 字段都要和原来一致", ""),
            ("目标技术栈", "JDK 17、Spring Boot 3、MyBatis、达梦 DM8", ""),
            ("怎么跑", "一个脚本从头跑到尾：全量分析、建改造计划、改骨架、验收、7 个业务域并行改、合并、出报告", ""),
            ("产物", "每个部分一个分支，合并后的 Java 代码在一个分支上，可以逐文件和官方 Java 版对照", "tmh-java-all")]
    y = kv_table(s, 2.0, rows, rh=0.66)
    text(s, 0.6, y + 0.3, 12.1, 0.5, "选它的原因：同一套接口有官方的 .NET 和 Java 两个实现，改出来的结果有现成的答案可以对。",
         size=12.5, color=BODY)
    notes(s, "RealWorld（Conduit）是一个有多种语言官方实现的开源示例项目，功能由同一份 OpenAPI 规范定义，规范还自带 Hurl 接口测试。"
             "这一轮还没跑 Hurl 接口测试；测试机上没有达梦，单元测试用 H2，达梦只做到写法和配置。")


def case1_setup(s):
    # 事实来自运维平台线程对 Li 电脑上 ~/tmh-jeecg-test（report.json、report-notes.json、driver.py、tickets.json）的核对
    head(s, "实测", "案例一：用 JeecgBoot 官方仓库里 40 个真实 issue 测缺陷修复")
    rows = [("源仓库", "JeecgBoot 官方仓库，开源的 Java 低代码平台", "github.com/jeecgboot/JeecgBoot"),
            ("工单来源", "官方修复提交里引用的 GitHub issue，标题和正文照搬原文，每张都对得上链接", "JB-1 ↔ issues/9288"),
            ("挑选规则", "修复改动的业务文件不超过 8 个，按修复日期取最近的：后端 20 张、前端 20 张", "2025-02 至 2026-09"),
            ("代码版本", "每张单都从官方修复的前一个提交开始改，官方修复不在智能体的代码历史里", "基线 84f46c2 · v3.7.2"),
            ("智能体", "OpenAI Codex。每张单实际运行时间中位数约 8 分钟", ""),
            ("评审方法", "把智能体的改动和官方修复的代码逐张对照，分成五档。只看代码，没有编译运行", "")]
    y = kv_table(s, 2.0, rows, rh=0.66)
    text(s, 0.6, y + 0.3, 12.1, 0.5, "任何人都可以按 issue 号回到 GitHub，看到原始问题和官方是怎么修的。",
         size=12.5, color=BODY)
    notes(s, "代码快照：提交 84f46c214260780c02d6af085a1b2e44af224405（2025-02-06，pom 版本 3.7.2），是 40 张单各自修复前提交的共同祖先。"
             "隔离程度：223 次运行里智能体调了 339 次 git log/show/blame/diff，没有一次看别的分支；"
             "但本地仓库里确实存有后来的提交，提示词也没有专门禁止，所以只能说没给它、日志里也没看过，不能说技术上完全隔离。"
             "评审由 AI 逐张对照 diff 完成，记录在 report-notes.json，目前还没有人工复核。"
             "模型为 Codex（日志显示 gpt-6.1-sol）；每张单 token 中位数约 34 万，没有记录真实金额。")


PARTS = [("骨架", 19.4, True), ("文章标签", 29.9, False), ("用户资料查询", 40.6, True), ("文章收藏", 23.9, True),
         ("用户关注", 29.9, True), ("文章评论", 37.5, True), ("用户账户与身份认证", 23.6, True), ("文章管理", 26.2, True)]
APIS = ["POST /users/login", "POST /users", "GET /user", "PUT /user", "GET /profiles/{u}",
        "POST /profiles/{u}/follow", "DELETE /profiles/{u}/follow", "GET /articles/feed", "GET /articles",
        "POST /articles", "GET /articles/{slug}", "PUT /articles/{slug}", "DELETE /articles/{slug}",
        "GET /articles/{slug}/comments", "POST /articles/{slug}/comments", "DELETE /articles/{slug}/comments/{id}",
        "POST /articles/{slug}/favorite", "DELETE /articles/{slug}/favorite", "GET /tags"]
MISSING = {"GET /profiles/{u}"}


def case2_result(s):
    head(s, "实测", "案例二结果：8 个部分里 7 个编译通过，19 个接口做出了 18 个")
    # 左：每个部分的智能体用时（条长）和编译结果
    text(s, 0.6, 1.95, 5.5, 0.3, "每个部分：智能体用时与编译结果", size=11, color=MUTED, bold=True)
    y = 2.4
    BX, BWm = 2.75, 2.2
    for nm, mins, ok in PARTS:
        text(s, 0.6, y, 2.1, 0.4, nm, size=11.5, color=INK, anchor="m")
        box(s, BX, y + 0.11, BWm * mins / 45, 0.18, ACCENT if ok else GAP, None)
        text(s, BX + BWm * mins / 45 + 0.08, y, 0.9, 0.4, "%.0f 分" % mins, size=10.5, color=MUTED, anchor="m")
        text(s, 5.3, y, 1.1, 0.4, "编译通过" if ok else "未通过", size=10.5, color=ACCENT if ok else GAP,
             bold=not ok, anchor="m", align="r")
        y += 0.47
    # 右：19 个接口
    text(s, 6.75, 1.95, 6, 0.3, "官方规范里的 19 个接口", size=11, color=MUTED, bold=True)
    cw, ch, gx, gy = 1.93, 0.5, 0.06, 0.07
    for i, api in enumerate(APIS):
        r, c = divmod(i, 3)
        x, yy = 6.75 + c * (cw + gx), 2.4 + r * (ch + gy)
        miss = api in MISSING
        m, path = api.split(" ", 1)
        box(s, x, yy, cw, ch, WHITE if miss else ACCENT_T, GAP if miss else None, 1.25, dash=miss)
        text(s, x + 0.08, yy, cw - 0.1, ch, [[(m + " ", {"bold": True}), (path, {})]], size=8.5,
             color=GAP if miss else ACCENT, anchor="m")
    text(s, 6.75, 2.4 + 7 * (ch + gy) + 0.05, 5.98, 0.3, "虚线框：漏掉的“查询用户资料”接口", size=10.5, color=GAP)
    notes(s, "数字取自 RealWorld 重写测试报告。用时是智能体实际运行时间。"
             "“文章标签”部分在测试机上没编译过、平台诊断不通过，正在重改；“用户资料查询”部分漏了 GET /api/profiles/{username}。"
             "两处都是平台自己的诊断和对照报告指出来的，这也是每批都要人验收的原因。"
             "这一轮没有跑接口测试，只能说编译通过、接口 18/19，不能说功能已验证。")


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "cases.pptx"
    prs = new_deck()
    case2_setup(blank(prs))
    case2_result(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
