import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 总述页：运维和重构是两套独立流程，各画一张“人 / 智能体”泳道图。
# 步骤取自平台实际流程：运维见缺陷修复页和工单看板；重构见 重构探索/RealWorld重写测试-说明.md。
H_, A_ = 0, 1
OPS = [("受理", A_, ""), ("确认范围", H_, "需求人员"), ("定位", A_, ""), ("出方案", A_, ""), ("审方案", H_, "开发"),
       ("修改", A_, ""), ("验证", A_, ""), ("验收", H_, "验收人"), ("合入主干", H_, "项目团队")]
REF = [("定目标和约束", H_, "项目负责人"), ("拆分业务域", A_, ""), ("改公共骨架", A_, ""), ("验收骨架", H_, "验收人"),
       ("各域并行改", A_, ""), ("逐域验收", H_, "验收人"), ("合入主干", H_, "项目团队")]


def lane_block(s, y, name, sub, steps, gi=None, pages=""):
    LH = 0.72
    if gi is not None:
        # 右上角：这一套流程后面分几页讲，编号与各页右上角的导航一致
        n = len(TRACK[gi][1])
        x = 12.73 - n * (CHIP_W + CHIP_G) + CHIP_G
        text(s, x - 1.25, y + 0.05, 1.15, CHIP_H, pages, size=10, color=ACCENT, bold=True, align="r", anchor="m")
        chips(s, x, y + 0.05, gi, show_name=False)
    text(s, 0.6, y, 1.2, 0.36, name, size=17, color=INK, bold=True, anchor="m")
    text(s, 1.45, y, 8, 0.36, sub, size=11, color=MUTED, anchor="m")
    ly = y + 0.45
    lx = 0.6
    for i, nm in enumerate(["人", "智能体"]):
        yy = ly + i * (LH + 0.05)
        box(s, lx, yy, 12.73 - lx, LH, "EEF2FA" if i == 0 else PANEL, None, shape="round", radius=0.08)
        text(s, lx + 0.15, yy, 0.8, LH, nm, size=11, color=MUTED, bold=True, anchor="m")
    x0, x1 = lx + 0.95, 12.6
    bw = 0.98 if len(steps) > 7 else 1.3
    pitch = (x1 - x0 - bw) / (len(steps) - 1)
    pos = []
    for i, (t, lane, who) in enumerate(steps):
        x = x0 + i * pitch
        yy = ly + lane * (LH + 0.05) + (0.07 if who else 0.14)
        human = lane == H_
        label_box(s, x, yy, bw, 0.42, t, fill=ACCENT if human else WHITE, line=None if human else RULE,
                  size=11.5, color=WHITE if human else INK, bold=True, shape="round")
        if who:
            text(s, x - 0.25, yy + 0.42, bw + 0.5, 0.22, who, size=9, color=ACCENT, align="c")
        pos.append((x, yy))
    for i in range(len(steps) - 1):
        (xa, ya), (xb, yb) = pos[i], pos[i + 1]
        line(s, xa + bw + 0.02, ya + 0.21, xb - 0.02, yb + 0.21, MUTED, 1.0, arrow=True)


def flows_slide(s):
    pass  # 去掉标题上方小字：text(s, 0.6, 0.45, 8, 0.3, "怎么干活", size=11, color=MUTED, bold=True)
    text(s, 0.6, 0.78, 12.1, 0.9, "运维一张单一张单地处理，重构按计划分批推进，关键几步都由人拍板",
         size=26, color=INK, bold=True)
    lane_block(s, 1.9, "运维", "需求答复、缺陷修复、日常维护，按单处理", OPS, 0, "详见第 4–7 页")
    lane_block(s, 4.05, "重构", "跨语言重写、框架迁移、依赖升级等，按改造计划分批推进", REF, 1, "详见第 8–12 页")
    text(s, 0.6, 6.25, 12.1, 0.6,
         "两套流程里，智能体都只在独立分支上改代码，改完先在测试机上构建；合入主干都由人操作。",
         size=12.5, color=BODY, lsp=1.4)
    notes(s, "运维：确认范围和审方案两步不是每张单都有，看单子的影响面；验证不通过智能体自动重改，最多 3 轮，仍不通过交给人；"
             "验收不通过须写明原因，原因记为教训。"
             "重构：人先写目标和不能变的东西（比如对外接口完全不变）；平台按业务域拆分，按和其他域共用表的多少排顺序；"
             "先做公共骨架，骨架验收通过前只放这一张；通过后其余业务域一次放出、并行改，每个都从骨架的分支开始。")


if __name__ == "__main__":
    OUT = sys.argv[1] if len(sys.argv) > 1 else "flows.pptx"
    prs = new_deck()
    flows_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT)
