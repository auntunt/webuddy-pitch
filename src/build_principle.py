import sys, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pptkit import *

# 「平台工作原理」：把平台画成一台等轴测的小机器，用机器本身讲一张工单怎么走到合入主干。
# 思路学自 anatomy skill：物件就是解释；不画框和箭头；零件实心、按深度从后往前画；
# 顶面最亮、两个侧面依次变暗；画面里不写字，只在底座前沿刻小铭牌。
# 唯一的强调色留给“人”：确认方案、验收、合入主干三处。
OUT = sys.argv[1] if len(sys.argv) > 1 else "principle.pptx"
prs = new_deck()

C30 = math.cos(math.radians(30))

# 三面色调：顶 / 朝左前（y 最大面）/ 朝右前（x 最大面）
T_SLAB = ("F1F3F7", "DADFE8", "C4CBD7")
T_PLINTH = ("8C97A9", "6E7A8E", "5A6579")
T_METAL = ("E3E7EE", "BEC6D3", "A1ABBB")
T_DARK = ("6E7B91", "4F5B70", "3E485A")
T_RAIL = ("CDD3DD", "A9B2C1", "8F99AA")
T_CARD = ("4F74C9", "1F4AA8", "163A86")      # 工单：画面里唯一的亮色
T_PAPER = ("FFFFFF", "E4E7EC", "D2D7DF")
T_DONE = ("3A465A", "2B3546", "222A38")       # 已合入主干的提交
T_HUMAN = ("4A4E57", "33363D", "26292F")      # 人负责的台位：最深的一档
T_GLASS = ("39465C", "2B3546", "222A38")

items = []   # (key, [ (pts3d, fill, line) ... ])
plates = []  # (x, y, z, face, text)


def boxp(x0, y0, z0, x1, y1, z1, tone, edge=None):
    top, left, right = tone
    faces = [
        ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], left),
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], right),
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], top),
    ]
    return [(f, c, edge) for f, c in faces]


def add(key, polys):
    items.append((key, polys))


def B(x0, y0, z0, x1, y1, z1, tone, layer=1, bias=0.0, edge=None):
    key = (layer, (x0 + x1) / 2 + (y0 + y1) / 2 + bias, z0)
    add(key, boxp(x0, y0, z0, x1, y1, z1, tone, edge))


def face_y(x0, x1, z0, z1, y, fill, layer=1, bias=0.0):
    """贴在某个 y=常数 面上的小平面（抽屉、窗口等）。"""
    add((layer, x0 / 2 + x1 / 2 + y + bias, z0), [([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], fill, None)])


def face_x(y0, y1, z0, z1, x, fill, layer=1, bias=0.0):
    add((layer, x + y0 / 2 + y1 / 2 + bias, z0), [([(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], fill, None)])


def card(x, y, z, tone=T_CARD, along="x", marked=False, bias=0.02):
    """一张工单：薄片，顶面画两条“字行”。"""
    w, d = (0.5, 0.42) if along == "x" else (0.42, 0.5)
    B(x, y, z, x + w, y + d, z + 0.05, tone, bias=bias)
    zt = z + 0.05
    lines = [(0.08, 0.32), (0.08, 0.22)]
    for i, (a, b) in enumerate([(0.10, 0.14), (0.20, 0.24)]):
        if along == "x":
            pts = [(x + 0.08, y + a, zt), (x + w - 0.1 - i * 0.12, y + a, zt),
                   (x + w - 0.1 - i * 0.12, y + b, zt), (x + 0.08, y + b, zt)]
        else:
            pts = [(x + a, y + 0.08, zt), (x + b, y + 0.08, zt),
                   (x + b, y + d - 0.1 - i * 0.12, zt), (x + a, y + d - 0.1 - i * 0.12, zt)]
        add((1, x + w / 2 + y + d / 2 + bias + 0.001, zt), [(pts, "A9BEEB", None)])
    if marked:  # 改过代码的单：顶面加一块深色补丁
        if along == "x":
            pts = [(x + 0.08, y + 0.28, zt), (x + 0.3, y + 0.28, zt), (x + 0.3, y + 0.36, zt), (x + 0.08, y + 0.36, zt)]
        else:
            pts = [(x + 0.28, y + 0.08, zt), (x + 0.36, y + 0.08, zt), (x + 0.36, y + 0.3, zt), (x + 0.28, y + 0.3, zt)]
        add((1, x + w / 2 + y + d / 2 + bias + 0.002, zt), [(pts, "FFFFFF", None)])


def rail_x(x0, x1, y0, y1, z=0.4, rollers=True):
    B(x0, y0, z, x1, y1, z + 0.12, T_RAIL, bias=-0.3)
    B(x0, y0 - 0.06, z, x1, y0, z + 0.2, T_METAL, bias=-0.35)
    B(x0, y1, z, x1, y1 + 0.06, z + 0.2, T_METAL, bias=0.1)
    if rollers:
        x = x0 + 0.15
        while x < x1 - 0.1:
            add((1, x + (y0 + y1) / 2 - 0.25, z + 0.12),
                [([(x, y0, z + 0.121), (x + 0.05, y0, z + 0.121), (x + 0.05, y1, z + 0.121), (x, y1, z + 0.121)],
                  "B3BBC8", None)])
            x += 0.3


def rail_y(y0, y1, x0, x1, z=0.4, rollers=True):
    B(x0, y0, z, x1, y1, z + 0.12, T_RAIL, bias=-0.3)
    B(x0 - 0.06, y0, z, x0, y1, z + 0.2, T_METAL, bias=-0.35)
    B(x1, y0, z, x1 + 0.06, y1, z + 0.2, T_METAL, bias=0.1)
    if rollers:
        y = y0 + 0.15
        while y < y1 - 0.1:
            add((1, (x0 + x1) / 2 + y - 0.25, z + 0.12),
                [([(x0, y, z + 0.121), (x1, y, z + 0.121), (x1, y + 0.05, z + 0.121), (x0, y + 0.05, z + 0.121)],
                  "B3BBC8", None)])
            y += 0.3


Z = 0.4          # 台面高度
RY0, RY1 = 1.2, 1.8   # 工作线（独立分支）在 A 段的 y 范围
RX0, RX1 = 7.6, 8.2   # 工作线在 B 段的 x 范围
TX0, TX1 = 9.1, 9.5   # 主干线

# ---------------------------------------------------------------- 底座：L 形台面
B(6.8, -6.0, -0.25, 10.0, -2.2, 0.0, T_PLINTH, layer=0, bias=-10)
B(6.8, -6.0, 0.0, 10.0, -2.2, Z, T_SLAB, layer=0, bias=-10)
B(0.0, -2.2, -0.25, 10.0, 3.0, 0.0, T_PLINTH, layer=0, bias=-5)
B(0.0, -2.2, 0.0, 10.0, 3.0, Z, T_SLAB, layer=0, bias=-5)

# ---------------------------------------------------------------- 工作线（独立分支）：A 段沿 x，拐角后 B 段沿 -y
rail_x(1.95, RX1, RY0, RY1)
rail_y(-4.85, RY0, RX0, RX1)
# 主干线：B 段外侧，上面是已合入的提交
rail_y(-5.7, 2.7, TX0, TX1, rollers=False)
for yy in (1.9, 0.9, -0.1, -1.1):
    B(TX0 + 0.06, yy, Z + 0.12, TX1 - 0.06, yy + 0.45, Z + 0.3, T_DONE, bias=0.05)

# ---------------------------------------------------------------- 1 受理：进单口
B(0.55, 0.85, Z, 1.95, 2.15, Z + 0.9, T_METAL)
B(0.7, 1.0, Z + 0.9, 1.8, 2.0, Z + 0.92, T_DARK)
for i in range(4):
    card(0.75 + i * 0.03, 1.25 - i * 0.04, Z + 0.92 + i * 0.06, bias=0.3 + i * 0.01)
card(2.15, RY0 + 0.09, Z + 0.12)

# ---------------------------------------------------------------- 2 代码知识库：抽屉柜，一格拉出，里面是关联到的 3 条业务流
KX0, KX1, KY0, KY1, KZ = 2.5, 5.2, -2.0, -0.6, 1.9
B(KX0, KY0, Z, KX1, KY1, Z + KZ, T_METAL, bias=-1)
B(KX0 - 0.05, KY0 - 0.05, Z + KZ, KX1 + 0.05, KY1 + 0.05, Z + KZ + 0.08, T_RAIL, bias=-1)
cols, rows = 5, 4
dw, dh = (KX1 - KX0 - 0.2) / cols, (KZ - 0.25) / rows
for r in range(rows):
    for c in range(cols):
        x0 = KX0 + 0.1 + c * dw + 0.04
        z0 = Z + 0.12 + r * dh + 0.04
        if (r, c) == (1, 2):
            continue
        face_y(x0, x0 + dw - 0.08, z0, z0 + dh - 0.08, KY1, "D3D9E2", bias=-0.9)
        face_y(x0 + dw / 2 - 0.13, x0 + dw / 2 + 0.05, z0 + dh / 2 - 0.06, z0 + dh / 2 - 0.02, KY1, "7E8AA0",
               bias=-0.89)
x0 = KX0 + 0.1 + 2 * dw + 0.04
z0 = Z + 0.12 + 1 * dh + 0.04
face_y(x0, x0 + dw - 0.08, z0, z0 + dh - 0.08, KY1, "3E485A", bias=-0.9)
B(x0, KY1 - 0.4, z0, x0 + dw - 0.08, KY1 + 0.45, z0 + dh - 0.08, T_METAL, bias=-0.2)
for i in range(3):
    B(x0 + 0.07 + i * 0.12, KY1 - 0.15, z0 + dh - 0.08, x0 + 0.13 + i * 0.12, KY1 + 0.35, z0 + dh, T_PAPER,
      bias=-0.19)


# ---------------------------------------------------------------- 3、4 智能体：两台龙门臂（分析和方案；改代码）
def gantry(xc, marked=False):
    B(xc - 0.3, 0.05, Z, xc + 0.3, 0.6, Z + 0.15, T_METAL, bias=-0.5)
    B(xc - 0.15, 0.15, Z + 0.15, xc + 0.15, 0.45, Z + 1.75, T_DARK, bias=-0.5)
    B(xc - 0.12, 0.15, Z + 1.6, xc + 0.12, 1.65, Z + 1.85, T_DARK, bias=-0.1)
    B(xc - 0.08, 1.4, Z + 0.75, xc + 0.08, 1.56, Z + 1.6, T_METAL, bias=0.15)
    B(xc - 0.2, 1.3, Z + 0.62, xc + 0.2, 1.66, Z + 0.75, T_DARK, bias=0.2)
    for j in range(3):
        face_y(xc - 0.1 + j * 0.08, xc - 0.06 + j * 0.08, Z + 1.68, Z + 1.72, 1.65, "C7CEDA", bias=0.0)
    card(xc - 0.25, RY0 + 0.09, Z + 0.12, marked=marked, bias=0.0)


gantry(3.85)
B(3.7, -0.6, Z + 1.0, 3.84, 0.15, Z + 1.1, T_METAL, bias=-0.6)     # 伸向知识库的读取杆
card(5.0, RY0 + 0.09, Z + 0.12)                                    # 已出方案，往改代码那台去
gantry(6.3, marked=True)

# ---------------------------------------------------------------- 5 测试机：编译、和原代码基线对比；窗里三格是最多再改 3 轮
TY0, TY1 = -1.9, -0.25
B(7.35, TY0, Z, 8.65, TY1, Z + 1.5, T_METAL, bias=0.4)
face_x(TY0 + 0.25, TY1 - 0.25, Z + 0.45, Z + 1.2, 8.65, "2B3546", bias=0.41)
for k in range(3):
    face_x(TY0 + 0.4 + k * 0.38, TY0 + 0.66 + k * 0.38, Z + 0.6, Z + 0.76, 8.65, "6E7B91", bias=0.42)
face_y(7.4, 8.5, Z + 0.15, Z + 0.35, TY1, "9AA4B5", bias=0.41)
B(7.5, TY0 + 0.2, Z + 1.5, 8.2, TY0 + 0.9, Z + 1.75, T_DARK, bias=0.4)
for k in range(4):
    add((1, 7.85 + TY0 + 0.55 + 0.45, Z + 1.75), [([(7.56 + k * 0.16, TY0 + 0.27, Z + 1.751), (7.62 + k * 0.16, TY0 + 0.27, Z + 1.751),
                                              (7.62 + k * 0.16, TY0 + 0.83, Z + 1.751), (7.56 + k * 0.16, TY0 + 0.83, Z + 1.751)],
                                             "3E485A", None)])

# ---------------------------------------------------------------- 6 闸门：横梁上 6 根检查销，被拦下的改动转进旁边的人审台
GY = -2.6
B(7.35, GY - 0.12, Z, 7.5, GY + 0.12, Z + 1.25, T_DARK, bias=0.3)
B(8.3, GY - 0.12, Z, 8.45, GY + 0.12, Z + 1.25, T_DARK, bias=0.6)
B(7.35, GY - 0.12, Z + 1.25, 8.45, GY + 0.12, Z + 1.4, T_DARK, bias=0.6)
for k in range(6):
    px = 7.47 + k * 0.155
    B(px, GY - 0.04, Z + 1.4, px + 0.06, GY + 0.04, Z + 1.62, T_METAL, bias=0.61 + k * 0.001)
card(RX0 + 0.05, GY + 0.35, Z + 0.12, along="y", marked=True)
# 人审台
B(8.5, GY - 0.45, Z, 8.95, GY + 0.35, Z + 0.55, T_HUMAN, bias=0.7)
card(8.52, GY - 0.3, Z + 0.55, along="y", marked=True, bias=0.75)

# ---------------------------------------------------------------- 7 人：验收（压印台）。不通过的教训沿回流带送回知识库
VY = -3.85
B(7.3, VY - 0.3, Z, 7.45, VY + 0.3, Z + 1.6, T_HUMAN, bias=0.0)
B(8.35, VY - 0.3, Z, 8.5, VY + 0.3, Z + 1.6, T_HUMAN, bias=0.5)
B(7.3, VY - 0.3, Z + 1.6, 8.5, VY + 0.3, Z + 1.85, T_HUMAN, bias=0.5)
B(7.75, VY - 0.08, Z + 0.9, 8.05, VY + 0.08, Z + 1.6, T_METAL, bias=0.55)
B(7.6, VY - 0.22, Z + 0.72, 8.2, VY + 0.22, Z + 0.9, T_HUMAN, bias=0.56)
card(RX0 + 0.05, VY - 0.25, Z + 0.12, along="y", marked=True, bias=0.0)
# 回流带：验收台内侧沿 -y 回到拐角，再沿 x 回到知识库
rail_y(VY - 0.2, -0.75, 6.75, 7.05, rollers=False)
rail_x(KX1, 7.05, -1.05, -0.75, rollers=False)
for yy in (-3.3, -2.3, -1.3):
    B(6.8, yy, Z + 0.12, 7.0, yy + 0.22, Z + 0.22, T_DONE, bias=0.02)
for xx in (5.6, 6.4):
    B(xx, -1.0, Z + 0.12, xx + 0.22, -0.8, Z + 0.22, T_DONE, bias=0.02)

# ---------------------------------------------------------------- 8 人：合入主干（扳手），独立分支上的改动横移到主干
rail_x(RX1, TX0, -5.45, -4.85)
card(8.55, -5.38, Z + 0.12, marked=True)
B(9.65, -5.35, Z, 9.9, -4.95, Z + 0.5, T_HUMAN, bias=0.8)
B(9.72, -5.23, Z + 0.5, 9.82, -5.07, Z + 1.15, T_HUMAN, bias=0.81)
B(9.67, -5.28, Z + 1.15, 9.87, -5.02, Z + 1.3, T_HUMAN, bias=0.82)

# ---------------------------------------------------------------- 铭牌：刻在台面前沿；人负责的三处前面加“人 ·”
plates = [
    (1.25, "A", "受理"), (3.85, "A", "分析 · 方案"), (6.3, "A", "改代码"),
    (-1.05, "B", "编译 · 对比基线"), (-2.6, "B", "闸门"), (-3.85, "B", "人 · 验收"), (-5.72, "B", "人 · 合入"),
]

# ---------------------------------------------------------------- 投影、自适应缩放、绘制
def proj(p):
    x, y, z = p
    return ((x - y) * C30, (x + y) * 0.5 - z)


allpts = [proj(p) for _, polys in items for pts, _, _ in polys for p in pts]
mnx = min(p[0] for p in allpts); mxx = max(p[0] for p in allpts)
mny = min(p[1] for p in allpts); mxy = max(p[1] for p in allpts)
BX, BY, BW, BH = 0.6, 1.85, 12.13, 5.35
K = min(BW / (mxx - mnx), BH / (mxy - mny))
OX = BX + (BW - (mxx - mnx) * K) / 2 - mnx * K
OY = BY + (BH - (mxy - mny) * K) / 2 - mny * K


def S2(p):
    sx, sy = proj(p)
    return (OX + sx * K, OY + sy * K)


def principle_slide(s, pnum_text=None):
  text(s, 0.6, 0.45, 8, 0.3, "工作原理", size=11, color=MUTED, bold=True)
  text(s, 0.6, 0.78, 12.1, 0.9, "智能体在独立分支上改代码，验收和合入主干由人负责", size=26, color=INK, bold=True)

  for key, polys in sorted(items, key=lambda t: t[0]):
      for pts, fill, edge in polys:
          poly(s, [S2(p) for p in pts], fill=fill, line=edge, lw=0.5)

  # 说明：每条用一句话讲这个部件在做什么，细线连到部件上的一个点
  def callout(anchor, lx, ly, head, sub, right=False, lw=4.2):
      ax, ay = S2(anchor)
      tx = lx - lw if right else lx
      sw = len(sub) * 0.155            # 说明行的大致宽度：线从说明行末端引出，不穿过文字
      sx = lx - sw - 0.1 if right else lx + sw + 0.1
      line(s, sx, ly + 0.5, ax, ay, ACCENT_M, 0.75)
      box(s, ax - 0.045, ay - 0.045, 0.09, 0.09, ACCENT, None, shape="oval")
      text(s, tx, ly, lw, 0.9, [[(head, {"bold": True, "color": INK})], [(sub, {"color": MUTED, "size": 11})]],
           size=13, align="r" if right else "l", lsp=1.3)

  callout((KX0 + 0.5, KY1, Z + 1.55), 0.6, 1.95, "项目知识库", "业务地图和代码证据，智能体先查这里")
  callout((3.85, 0.45, Z + 0.9), 0.6, 5.75, "智能体", "找到代码位置、写方案，只在独立分支上改代码")
  callout((8.65, -1.6, Z + 0.25), 12.73, 6.05, "测试机和检查", "编译、测试不过就自动重改；改动超出方案转给人审", right=True)
  callout((8.5, VY - 0.3, Z + 1.7), 12.73, 1.95, "人", "验收，通过后合入主干；不通过的原因写回知识库", right=True)

  notes(s, "蓝色薄片是工单，从左上的进单口进入，沿独立分支这条线走：知识库抽屉里拉出和这张单相关的业务流（最多 3 条）；"
           "第一台臂分析、找到代码证据并起草方案，找不到证据就转人工；第二台臂在独立分支上改代码。"
           "测试机编译并和原代码基线对比，不过就按诊断再改，最多 3 轮。"
           "闸门有 6 项检查：构建失败、诊断认为没解决、改了方案外的文件、改动超过 400 行、删了文件、改了已有测试或受保护文件；任一项成立就转人审，不自动提交。"
           "通过的改动提交到独立分支，人验收：通过记成评测用例；不通过记成教训，沿回流带送回知识库，带着原因自动重改，最多 2 次。"
           "合入主干由人操作。深灰色的台位是人负责的地方。")


if __name__ == "__main__":
    principle_slide(blank(prs))
    strip_styles(prs)
    prs.save(OUT)
    print("saved", OUT, "parts", len(items))
