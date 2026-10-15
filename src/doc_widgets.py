"""从 tree_data 生成文档里的三张图（Claude Docs widget 的 JSX 代码），保证文档和 PPT 用同一份数据。"""
import json
from tree_data import BRANCHES, PHASES, modules, counts, AS_OF
DISPLAY = {"CLI（tmh）": "命令行工具", "场景提示词": "编程助手提示词", "MCP": "IDE 接口（MCP）"}

INK = "var(--cds-text-primary)"
QUIET = "var(--cds-text-secondary)"
EDGE = "var(--cds-chart-axis)"
RULE = "var(--cds-chart-grid)"
ACC = "var(--cds-chart-categorical-1)"
WARN = "var(--cds-chart-status-warning)"
TINT = "var(--cds-chart-reference-tint)"
MODS = list(modules())
CNT = counts()
TOT = {k: sum(c[k] for c in CNT.values()) for k in ("done", "part", "gap")}


def esc(s):
    return s.replace("'", "’").replace("{", "（").replace("}", "）")


def T(tid, x, y, words, size=None, weight=None, fill=INK, anchor=None):
    a = "<text data-claude-text-id='%s' x='%s' y='%s'" % (tid, round(x, 1), round(y, 1))
    if size:
        a += " fontSize='%s'" % size
    if weight:
        a += " fontWeight='%s'" % weight
    if anchor:
        a += " textAnchor='%s'" % anchor
    a += " fill='%s'>%s</text>" % (fill, esc(words))
    return a


def sq(x, y, st, s=9):
    if st == "done":
        return "<rect x='%s' y='%s' width='%d' height='%d' rx='2' fill='%s'/>" % (x, y, s, s, ACC)
    if st == "part":
        return "<rect x='%s' y='%s' width='%d' height='%d' rx='2' fill='%s' fillOpacity='0.35' stroke='%s' strokeWidth='1'/>" % (x, y, s, s, ACC, ACC)
    return "<rect x='%s' y='%s' width='%d' height='%d' rx='2' fill='%s'/>" % (x, y, s, s, WARN)


def ln(x1, y1, x2, y2, c=EDGE, w=1.25, extra=""):
    return "<line x1='%s' y1='%s' x2='%s' y2='%s' stroke='%s' strokeWidth='%s'%s/>" % (round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1), c, w, extra)


def P(pts, fill, op=None, stroke=None, sw=None):
    a = "<polygon points='%s' fill='%s'" % (" ".join("%s,%s" % (round(x, 1), round(y, 1)) for x, y in pts), fill)
    if op is not None:
        a += " fillOpacity='%s'" % op
    if stroke:
        a += " stroke='%s' strokeWidth='%s'" % (stroke, sw or 1.25)
    return a + "/>"


def wrap(title, body, h, label):
    return ("export default () => <svg viewBox='0 0 760 %d' role='img' aria-label='%s' fontSize='13'>" % (h, esc(label))
            + T("title", 24, 32, title, 15, 600) + body + "</svg>;")


# ------------------------------------------------------------ 金字塔
def pyramid():
    cx, y0, H, half = 300, 84, 390, 250
    hw = lambda y: 64 + (half - 64) * (y - y0) / H
    b = [T("subtitle", 24, 52, "下层支撑上层：各类工作的答案都从项目知识来，经人机接口送达；度量给每一层记账", 11.5, None, QUIET)]
    # apex
    a0, a1 = y0, 204
    b.append("<g data-claude-anchor='tier-goal'>" + P([(cx - hw(a0), a0), (cx + hw(a0), a0), (cx + hw(a1), a1), (cx - hw(a1), a1)], ACC, 0.06, ACC, 2)
             + T("goal-name", cx, 134, "目标", 13, 600, INK, "middle")
             + T("goal-1", cx, 158, "答得快 · 改得稳", 11.5, None, INK, "middle")
             + T("goal-2", cx, 178, "翻新看得见", 11.5, None, INK, "middle") + "</g>")
    # work domains
    t0, t1 = 210, 320
    L0, R0, L1, R1 = cx - hw(t0), cx + hw(t0), cx - hw(t1), cx + hw(t1)
    names = [("A", "现场答复"), ("B", "日常维护"), ("C", "线上运维"), ("D", "重写升级")]
    for i, (k, nm) in enumerate(names):
        a, c = i / 4, (i + 1) / 4
        pts = [(L0 + (R0 - L0) * a, t0), (L0 + (R0 - L0) * c, t0), (L1 + (R1 - L1) * c, t1), (L1 + (R1 - L1) * a, t1)]
        mx = sum(p[0] for p in pts) / 4
        b.append("<g data-claude-anchor='tier-work-%s'>" % k.lower() + P(pts, TINT, None, EDGE, 1)
                 + T("work-%s-name" % k.lower(), mx, 270, nm, 13, 600, INK, "middle") + "</g>")
    # F
    f0, f1 = 326, 392
    b.append("<g data-claude-anchor='tier-interface'>" + P([(cx - hw(f0), f0), (cx + hw(f0), f0), (cx + hw(f1), f1), (cx - hw(f1), f1)], ACC, 0.14)
             + T("f-name", cx, 352, "人机接口", 13, 600, INK, "middle")
             + T("f-items", cx, 374, "平台 · 提示词 · MCP · CLI · 群机器人 · 流水线 · 离线包", 11.5, None, INK, "middle") + "</g>")
    # E
    e0, e1 = 398, 474
    b.append("<g data-claude-anchor='tier-knowledge'>" + P([(cx - hw(e0), e0), (cx + hw(e0), e0), (cx + hw(e1), e1), (cx - hw(e1), e1)], ACC, 0.32)
             + T("e-name", cx, 428, "项目知识（底座）", 13, 600, INK, "middle")
             + T("e-items", cx, 450, "代码图谱 → 业务流 → 业务域 → 总览；人确认；代码一改自动标过期", 11.5, None, INK, "middle") + "</g>")
    # G
    gx = 590
    g = "<g data-claude-anchor='g-metrics'>" + ln(gx, 100, gx, 474, ACC, 1.5)
    g += T("g-name", gx + 12, 96, "度量与管理", 13, 600, ACC)
    g += T("g-sub", gx + 12, 114, "横切：每一层都记账", 11.5, None, QUIET)
    rows = [(160, "g-goal-1", "答复时长 · 工单周期", "g-goal-2", "找开发次数"),
            (265, "g-work-1", "采纳率 · 退回率", "g-work-2", "改造完成度"),
            (359, "g-if-1", "出口调用记账", "g-if-2", "AI 参与率"),
            (436, "g-kb-1", "已确认页数", "g-kb-2", "过期页数")]
    for y, i1, w1, i2, w2 in rows:
        g += ln(gx, y, gx + 8, y, ACC, 1.25) + T(i1, gx + 14, y + 4, w1, 11.5, None, INK) + T(i2, gx + 14, y + 20, w2, 11.5, None, QUIET)
    b.append(g + "</g>")
    return wrap("维保提效是一座四层金字塔：知识是底座，度量贯穿每一层", "".join(b), 498, "维保提效是一座四层金字塔")


# ------------------------------------------------------------ 完整拆解树
def tree():
    PH = {1: "一期", 2: "二期", 3: "三期"}
    out = [T("subtitle", 24, 52, "7 个方向、22 个场景、%d 个模块：已有 %d、部分 %d、缺 %d（截至 %s）" % (len(MODS), TOT["done"], TOT["part"], TOT["gap"], AS_OF), 11.5, None, QUIET)]
    # legend
    lx = 24
    leg = "<g data-claude-anchor='legend'>"
    for st, lab in (("done", "已有"), ("part", "部分具备"), ("gap", "缺")):
        leg += sq(lx, 69, st) + T("legend-" + st, lx + 14, 78, lab, 11.5, None, QUIET)
        lx += 14 + 12 * len(lab) + 22
    leg += T("legend-phase", lx, 78, "一期 / 二期 / 三期 = 入期", 11.5, None, ACC)
    leg += T("legend-kind", 736, 78, "虚线框 = 横切能力（无场景层）", 11.5, None, QUIET, "end") + "</g>"
    out.append(leg)
    rootY = 96
    out.append("<g data-claude-anchor='root'><rect x='200' y='%d' width='360' height='36' rx='8' fill='%s' fillOpacity='0.12' stroke='%s' strokeWidth='2'/>" % (rootY, ACC, ACC)
               + T("root", 380, rootY + 23, "老项目运维提效：答得快 · 改得稳 · 翻新看得见", 13, 600, INK, "middle") + "</g>")
    bus = rootY + 52
    cols = {"L": dict(x=40, spine=24, ids=["A", "B", "C"]), "R": dict(x=414, spine=398, ids=["D", "E", "F", "G"])}
    W = 322
    conn = ln(380, rootY + 36, 380, bus) + ln(24, bus, 398, bus)
    body = []
    for key, c in cols.items():
        y = bus + 16
        last_mid = None
        for bid in c["ids"]:
            b = [x for x in BRANCHES if x["id"] == bid][0]
            x = c["x"]
            kind = b["kind"]
            dash = " strokeDasharray='4 3'" if kind == "cross" else ""
            fill, op = (ACC, 0.32) if kind == "base" else ("none", None)
            g = "<g data-claude-anchor='branch-%s'>" % bid.lower()
            g += "<rect x='%d' y='%d' width='%d' height='40' rx='8' fill='%s'%s stroke='%s' strokeWidth='%s'%s/>" % (
                x, y, W, fill, (" fillOpacity='%s'" % op) if op else "", ACC if kind != "work" else EDGE, 1.5 if kind != "work" else 1.25, dash)
            g += T("b-%s" % bid.lower(), x + 12, y + 25, b["name"], 13, 600, INK)
            g += T("who-%s" % bid.lower(), x + W - 12, y + 25, b["who"].replace("横切：", ""), 11.5, None, QUIET, "end")
            conn += ln(c["spine"], y + 20, x, y + 20)
            last_mid = y + 20
            yy = y + 40 + 6
            trunk_x = x + 12
            trunk_end = None
            for sid, sname, mods in b["scenes"]:
                if sname:
                    g += ln(trunk_x, yy + 10, trunk_x + 10, yy + 10, RULE, 1)
                    g += T("s-%s" % sid.lower(), trunk_x + 14, yy + 14, sname, 11.5, 600, INK)
                    trunk_end = yy + 10
                    sub_top = yy + 18
                    yy += 20
                    mx = trunk_x + 26
                else:
                    mx = trunk_x + 2
                    sub_top = None
                last = None
                for mid_, mname, st, ph in mods:
                    if sname:
                        g += ln(trunk_x + 20, yy + 9, mx - 2, yy + 9, RULE, 1)
                    g += sq(mx, yy + 4, st)
                    g += T("m-%s" % mid_.lower(), mx + 14, yy + 13, DISPLAY.get(mname, mname), 11.5, None, INK)
                    if ph:
                        g += T("p-%s" % mid_.lower(), x + W - 12, yy + 13, PH[ph], 11.5, 600, ACC, "end")
                    last = yy + 9
                    yy += 18
                if sname and last:
                    g += ln(trunk_x + 20, sub_top, trunk_x + 20, last, RULE, 1)
                yy += 4
            if trunk_end:
                g += ln(trunk_x, y + 40, trunk_x, trunk_end, RULE, 1)
            body.append(g + "</g>")
            y = yy + 14
        conn += ln(c["spine"], bus, c["spine"], last_mid)
        c["end"] = y
    h = int(max(c["end"] for c in cols.values()) + 8)
    content = "".join(out) + "<g data-claude-anchor='connectors'>" + conn + "</g>" + "".join(body)
    return wrap("完整拆解树：一期已实现，缺口集中在重写升级和日常维护的回归环节", content, h, "完整拆解树")


# ------------------------------------------------------------ 分期
GATES = {1: ("过关：试点项目自动答复的", "采纳率达到立项会定的线"), 2: ("过关：低风险工单无人化后", "退回率不高于人工基线"), 3: ("过关：一个老项目按看板", "完成一个业务域的翻新")}
def phases():
    ids = {1: ["p1-a", "p1-b", "p1-c", "p1-d", "p1-e", "p1-f"], 2: ["p2-a", "p2-b", "p2-c", "p2-d", "p2-e", "p2-f", "p2-g"], 3: ["p3-a", "p3-b", "p3-c", "p3-d"]}
    order = {1: ["A2-1", "A2-2", "F-5", "A1-2", "G-4", "F-7"], 2: ["B4-2", "B4-3", "B3-2", "A3-1", "G-3", "B5-2", "G-5"], 3: ["D5-1", "D2-1", "D3-1", "D4-1"]}
    byid = {m["id"]: m for m in MODS}
    y0, Wc, Hc = 72, 216, 336
    out = [T("subtitle", 24, 52, "一期 6 个模块截至 %s 已实现，待试点验证；过关条件满足再进下一期" % AS_OF, 11.5, None, QUIET)]
    arrows = "<g data-claude-anchor='arrows' fill='none' stroke='%s' strokeWidth='1.25'><path d='M240 102H262' markerEnd='url(#phase-arrow)'/><path d='M480 102H502' markerEnd='url(#phase-arrow)'/></g>" % EDGE
    for i, p in enumerate(PHASES):
        x = 24 + i * 240
        main = i == 0
        n = p["n"]
        g = "<g data-claude-anchor='phase-%d'>" % n
        g += "<rect x='%d' y='%d' width='%d' height='%d' rx='8' fill='%s'%s stroke='%s' strokeWidth='%s'/>" % (
            x, y0, Wc, Hc, ACC if main else "none", " fillOpacity='0.1'" if main else "", ACC if main else EDGE, 2 if main else 1.25)
        g += T("p%d-name" % n, x + 16, 102, "%s期 · %s" % ("一二三"[i], p["name"]), 15, 600, INK)
        g += T("p%d-goal" % n, x + 16, 124, p["goal"], 12, None, QUIET)
        g += T("p%d-state" % n, x + 16, 146, p["state"], 11.5, 600, ACC if main else QUIET)
        g += ln(x + 16, 160, x + Wc - 16, 160, RULE, 1)
        yy = 184
        for tid, mid in zip(ids[n], order[n]):
            m = byid[mid]
            g += sq(x + 16, yy - 9, m["status"])
            g += T(tid, x + 30, yy, m["name"], 12.5, None, INK)
            yy += 22
        g += ln(x + 16, 344, x + Wc - 16, 344, RULE, 1)
        g1, g2 = GATES[n]
        g += T("p%d-gate-1" % n, x + 16, 366, g1, 11.5, None, QUIET)
        g += T("p%d-gate-2" % n, x + 16, 384, g2, 11.5, None, QUIET)
        out.append(g + "</g>")
    defs = "<defs><marker id='phase-arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='6' markerHeight='6' orient='auto-start-reverse'><path d='M0 0L10 5L0 10z' fill='%s'/></marker></defs>" % EDGE
    code = ("export default () => <svg viewBox='0 0 760 432' role='img' aria-label='先做答得快，再做改得稳，最后让翻新看得见' fontSize='13'>" + defs
            + T("title", 24, 32, "先做答得快，再做改得稳，最后让翻新看得见", 15, 600) + arrows + "".join(out) + "</svg>;")
    return code


if __name__ == "__main__":
    import sys
    d = {"pyramid": pyramid(), "tree": tree(), "phases": phases()}
    json.dump(d, open(sys.argv[1], "w"), ensure_ascii=False)
    for k, v in d.items():
        print(k, len(v))
