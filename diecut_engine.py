# -*- coding: utf-8 -*-
"""
自锁式飞机盒（Self-locking Mailer Box）刀版生成引擎。

参考图结构（从上到下 5 层竖排）：
  1. 插舌 Tuck Flap        —— 顶部，两侧带半圆形防尘耳
  2. 盖子顶面 Lid Panel    —— 两侧为梯形斜切盖翼（机翼）
  3. 后壁 Back Wall        —— 两侧小防尘翼
  4. 底面 Bottom Panel     —— 两侧巨大的左右侧壁，外缘台阶状锯齿互锁
  5. 前壁 Front Wall       —— 两侧矩形锁扣翼，插入侧壁切口，自锁免胶

输出：
  - cut    : 模切线（外轮廓 / 分刀线）
  - crease : 压痕线（折叠线）
PDF / DXF / SVG 三种输出，均为 1:1 毫米制，不需要 LibreOffice。
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """一段刀线。kind: 'cut' 或 'crease'，points 为折线顶点。

    cut 标记仅用于折痕线：当某段折痕与分刀线共线时，cut=True 表示该处
    同时也是模切线（在 SVG 中按 <g> 分层渲染，避免视觉重叠）。
    """
    kind: str
    points: List[Tuple[float, float]]
    cut: bool = False


@dataclass
class DieCutGeometry:
    """完整的刀版几何。"""
    length: float          # 内尺寸长 L（mm，横向列宽）
    width: float           # 内尺寸宽 W（mm，底面高度）
    height: float          # 内尺寸高 H（mm，盒高）
    thickness: float       # 纸板厚度 t（mm）
    wall_height: float     # 壁展开尺寸 = 盒内高 H（前/后壁、大侧壁内段，厚度在盒外）
    bottom_height: float   # 底面高度 = 制造宽 W + side_comp（盒宽方向）
    lid_height: float      # 盖子顶面高度 = W（盒宽，盖住盒顶）
    tab_depth: float       # 插舌高度 = H（盒高，梯形圆角 + 两侧耳翼）
    wing_width: float      # 盖翼宽度 = H - t（两折）
    back_flap_width: float # 后壁矩形翼宽度 = H - t（腰部翼）
    lock_width: float      # 前壁锁扣翼宽度 = H - t（底部翼，与腰部翼同尺寸）
    side_inner: float      # 大侧壁内段 = 盒内高 H（侧壁主体，一折）
    side_outer: float      # 大侧壁外段 = 盒高 H（折叠后插入盒底，末端钩 = t）
    fold_seg: float        # 两折翼的插入段长度
    segments: List[Segment] = field(default_factory=list)
    # —— 新增参数化字段（Step 2）——
    corner_radius: float = 0.0        # 盖翼圆角半径（只作用于盒盖两盖翼顶角）
    hook_ratio: float = 0.33          # 凸起钩高度比例（hook_h = W * hook_ratio）
    board_compensation: bool = True   # 是否启用纸厚补偿（内外尺寸换算）
    layers: List[str] = field(default_factory=lambda: ["CUT", "CREASE"])  # 活跃图层
    column_width: float = 0.0         # 前壁/后壁/插舌宽 = 制造长 - 2t
    lid_width: float = 0.0            # 盖面宽 = 制造长 - 8t
    side_height: float = 0.0          # 侧壁内段制造宽（网坐标 Y 方向）= width + side_comp

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """返回 (min_x, min_y, max_x, max_y)。"""
        xs = [p[0] for s in self.segments for p in s.points]
        ys = [p[1] for s in self.segments for p in s.points]
        return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# 几何计算
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_airplane_box(
    length: float,
    width: float,
    height: float,
    thickness: float,
    internal: bool = True,
    tab_depth: float | None = None,
    fold_ratio: float = 0.3,
    lock_ratio: float = 1.0,
    corner_radius: float = 0.0,
    tab_ear_radius: float = 0.0,
    hook_ratio: float = 0.33,
    board_compensation: bool | None = None,
    layers: List[str] | None = None,
    fb_comp: float | None = None,
    side_comp: float | None = None,
) -> DieCutGeometry:
    """
    构建自锁式飞机盒刀版几何（按折叠逻辑严格推算尺寸）。

    折叠逻辑：
      - 列宽（横向） = 盒长 L
      - 底面高度 = 制造宽 W + side_comp（盒底与后腰折线 → 盒底与前端折线）
      - 前壁 / 后壁 = 盒内高 H（厚度在盒外，从底面折起 90°，一折）
      - 盖子顶面高度 = 盒宽 W（平面盖面，盖住盒顶）
      - 插舌高度 = 盒高 H，直角三角形 + 顶角圆弧化
      - 底面大侧壁宽度 = 盒高 H（内段 / 外段 = H，末端凸起钩 = 纸厚 t）
      - 盖翼（机翼）/ 后壁矩形翼宽度 = H - t（两折）

     参数：
      length / width / height : 长 / 宽 / 高（mm）
      thickness               : 纸板厚度（mm）
      internal                : True 内尺寸，False 外尺寸
      tab_depth               : 插舌深度（mm），默认 20
      fold_ratio              : 两折翼插入段占总宽比例，默认 0.3
      lock_ratio              : 锁扣翼宽度比例，默认 1.0
      corner_radius           : 盖翼圆角半径（mm），默认 0（关闭，保持直角）
      hook_ratio              : 凸起钩高度比例，默认 0.33（= W/3.0 行为）
      board_compensation      : 纸厚补偿开关，默认 None（沿用 internal）
      layers                  : 活跃图层列表，默认 ["CUT", "CREASE"]
    """
    L = float(length)
    W = float(width)
    H = float(height)
    t = float(thickness)

    if min(L, W, H, t) <= 0:
        raise ValueError("长、宽、高、纸厚必须为正数")

    # 纸厚补偿开关：若显式给出则覆盖 internal
    if board_compensation is not None:
        internal = bool(board_compensation)

    if not internal:
        L = max(L - 2 * t, 1.0)
        W = max(W - 2 * t, 1.0)
        H = max(H - t, 1.0)

    # 立体几何尺寸（内尺寸 L×W×H 为基准，纸厚 t，壁从底面内表面折起）：
    #   - 前壁/后壁展开高 = 盒内高 H（壁内表面 z∈[0,H]，厚度在盒外）
    #   - 侧壁内段高 = H；外段 = H - t（折入贴盒底，厚度占用 t）
    #   - 盖翼/后壁翼/锁扣翼 = H - t（折入贴壁，厚度占用 t）
    Hw = H                                      # 前后壁展开高度 = 盒内高
    tab = max(float(tab_depth) if tab_depth else H, 4.0)   # 插舌深度 = 盒高 H
    wing_w = max(H - t, 4.0)                    # 盖翼宽度（两折 = H - t）
    back_w = max(H - t, 4.0)                    # 后壁矩形翼宽度（腰部翼 = H - t）
    lock_w = max((H - t) * float(lock_ratio), 4.0)   # 前壁锁扣翼（底部翼 = 腰部翼尺寸 H - t）
    side_inner = Hw                             # 大侧壁内段（侧壁主体 = 盒内高）
    gap = 3.0 * t                               # 间隙段（3t，含侧壁厚度；折叠后净空隙 2t 容纳腰部翼/耳翼厚度）
    side_outer = side_inner - t                 # 大侧壁插入段（始终比内段窄 t，折回后钩端到达盒底）
    side_total = side_inner + gap + side_outer  # 大侧壁总宽（内段 + 间隙段 + 插入段）
    fold_seg = max(6.0, wing_w * float(fold_ratio))   # 两折翼插入段
    fold_seg = min(fold_seg, wing_w - 2.0)
    wing_fold = wing_w - fold_seg               # 盖翼折线位置
    back_fold = back_w - fold_seg               # 后壁翼折线位置
    slant_w = min(wing_w * 0.3, 0.15 * L)       # 盖翼梯形斜切
    tab_slant = min(0.08 * L, 12.0)             # 插舌梯形斜切
    tab_r = _clamp(min(4.0, tab * 0.25), 1.5, 6.0)   # 插舌顶部圆角半径
    tab_ear_w = wing_w                          # 插舌翼横向 = 盖翼 = 锁扣翼 = H - t（等腰梯形）
    tab_ear_slant = min(12.0, tab * 0.2)        # 插舌翼等腰梯形斜切
    back_slant = min(15.0, back_w * 0.3)        # （后壁翼已改矩形，此值保留备用）
    hook_ratio = _clamp(float(hook_ratio), 0.2, 0.5)
    hook_d = t                                  # 大侧壁外段插舌长度 = 材料厚度（穿过盒底插口）
    hook_h = W * hook_ratio                    # 插舌末端凸起钩高度（居中 1 个，可调比例）

    # 圆角半径安全钳制：不能大于插舌翼宽，也不能让插舌顶边变成负宽
    len_ear = math.hypot(tab_ear_w, tab_ear_slant)
    corner_radius = _clamp(
        float(corner_radius),
        0.0,
        max(0.0, min(tab_ear_w, len_ear * 0.9, L / 2.0 - 0.5)),
    )

    side_comp = float(side_comp) if side_comp is not None else 2.0
    # 翼根交汇处外凸圆喙圆角半径：约纸厚量级，两翼根部"水平+竖直"转折处圆成朝外的小圆喙
    # （左右镜像共用同一半径，保证轴对称；无折线、无燕尾尖刺）
    beak_r = _clamp(t * 0.7, 1.0, 3.5)

    # 纵向分层（从下到上）
    y0 = 0.0
    y1 = Hw                       # 前壁顶 / 盒底前端折线
    y2 = Hw + W + side_comp       # 底面顶 = 制造宽（盒底与后腰折线），与侧壁内段顶边共线
    y3 = y2 + Hw                  # 后壁顶
    y4 = y3 + W                   # 盖子顶面顶（高度 = 盒宽 W，盖住盒顶）
    y5 = y4 + tab                 # 插舌顶（高度 = 盒高 H）
    y2_side = y2                  # 内段顶边 = 底面顶（制造宽），不侵入后腰翼
    y_in_lo = y1 + side_comp / 2.0    # 外段底边（相对内段居中缩进 side_comp/2）
    y_in_hi = y2 - side_comp / 2.0    # 外段顶边（相对内段居中缩进 side_comp/2）
    y2_base = y_in_hi             # 兼容引用：外段顶边

    fb_comp = float(fb_comp) if fb_comp is not None else 10.0 * t
    Lx = L + fb_comp                 # 制造长基准（盒外）= 内长 + 10t
    colW = Lx - 2.0 * t              # 前壁/后壁/插舌宽（腰部）= 制造长 - 2t
    lidW = Lx - 8.0 * t              # 盖面宽 = 制造长 - 8t
    # 各面板居中偏置（左右对称，两侧同时伸缩）
    # 底面 = 制造尺寸 Lx（含纸厚补偿），前/后壁 = Lx-2t，盖面 = Lx-8t
    ofs_b = (colW - Lx) / 2.0           # 底面居中（底面 = 制造尺寸 Lx）
    ofs_l = (colW - lidW) / 2.0         # 盖面居中

    segments: List[Segment] = []

    def poly(kind: str, pts: List[Tuple[float, float]], cut: bool = False) -> None:
        clean: List[Tuple[float, float]] = []
        for point in pts:
            if not clean or point != clean[-1]:
                clean.append(point)
        if len(clean) >= 2:
            segments.append(Segment(kind, clean, cut=cut))

    def arc_pts(cx: float, cy: float, r: float, t0: float, t1: float, n: int = 10) -> List[Tuple[float, float]]:
        """以 (cx,cy) 为圆心、半径 r 的圆弧，t0..t1 弧度。"""
        out = []
        for i in range(n + 1):
            th = t0 + (t1 - t0) * i / n
            out.append((cx + r * math.cos(th), cy + r * math.sin(th)))
        return out

    def rounded_corner(prev: Tuple[float, float], corner: Tuple[float, float],
                       nxt: Tuple[float, float], r: float) -> List[Tuple[float, float]]:
        """凸角圆弧化（外轮廓为 CW 走向，材料在右侧）。

        返回替换 corner 的圆弧点列（含两端点 p1/p2）；若 r<=0 或几何退化则原样返回 [corner]。
        圆弧中心 C 满足到两边距离均为 r（内移法线），两端点为 C 到两边的垂足（切点）。
        """
        if r <= 0:
            return [corner]
        v1x, v1y = corner[0] - prev[0], corner[1] - prev[1]
        v2x, v2y = nxt[0] - corner[0], nxt[1] - corner[1]
        len1 = math.hypot(v1x, v1y)
        len2 = math.hypot(v2x, v2y)
        if len1 < 1e-9 or len2 < 1e-9:
            return [corner]
        u1 = (v1x / len1, v1y / len1)
        u2 = (v2x / len2, v2y / len2)
        # 右侧法向（CW 路径，材料在右）：旋转 90° → (dy, -dx)
        n1 = (u1[1], -u1[0])
        n2 = (u2[1], -u2[0])
        # 求圆心 C：(C-corner)·n1 = r 且 (C-corner)·n2 = r
        det = n1[0] * n2[1] - n1[1] * n2[0]
        if abs(det) < 1e-9:
            return [corner]
        dx = (r * n2[1] - r * n1[1]) / det
        dy = (n1[0] * r - n2[0] * r) / det
        cx = corner[0] + dx
        cy = corner[1] + dy
        # 切点：C 到两边的垂足
        t1 = (cx - corner[0]) * u1[0] + (cy - corner[1]) * u1[1]
        t2 = (cx - corner[0]) * u2[0] + (cy - corner[1]) * u2[1]
        if t1 > 0 or t2 < 0:
            # 切点落在角外侧（凹角），不圆角化
            return [corner]
        p1 = (corner[0] + t1 * u1[0], corner[1] + t1 * u1[1])
        p2 = (corner[0] + t2 * u2[0], corner[1] + t2 * u2[1])
        if abs(math.hypot(cx - p1[0], cy - p1[1]) - r) > 0.05:
            return [corner]
        a1 = math.atan2(p1[1] - cy, p1[0] - cx)
        a2 = math.atan2(p2[1] - cy, p2[0] - cx)
        # 凸角：圆弧走 p1→p2 较短一侧（材料内部）。CP>0 走 CCW，CP<0 走 CW。
        cp = (p1[0] - cx) * (p2[1] - cy) - (p1[1] - cy) * (p2[0] - cx)
        if cp > 0:
            if a1 > a2:
                a2 += 2 * math.pi
            return arc_pts(cx, cy, r, a1, a2, 12)

        else:
            if a1 < a2:
                a1 += 2 * math.pi
            return arc_pts(cx, cy, r, a1, a2, 12)

    def rounded_polyline(points: List[Tuple[float, float]], radius: float,
                         rounded_indices: set[int]) -> List[Tuple[float, float]]:
        """对折线指定拐角圆角化，并去除相邻重复点。"""
        result: List[Tuple[float, float]] = []
        last_index = len(points) - 1
        for index, point in enumerate(points):
            if 0 < index < last_index and index in rounded_indices:
                replacement = rounded_corner(
                    points[index - 1], point, points[index + 1], radius
                )
            else:
                replacement = [point]
            for replacement_point in replacement:
                if not result or replacement_point != result[-1]:
                    result.append(replacement_point)
        return result

    def side_hooks(x_out: float, y_a: float, y_b: float, up: bool) -> List[Tuple[float, float]]:
        """大侧壁外段（插入底部的插舌）末端：一个居中凸起钩（左右对称）。"""
        pts: List[Tuple[float, float]] = []
        ylo, yhi = min(y_a, y_b), max(y_a, y_b)
        span = yhi - ylo
        c = ylo + span / 2.0
        pts.append((x_out, y_a))
        if up:
            pts.append((x_out, c - hook_h / 2.0))
            pts.append((x_out - hook_d, c - hook_h / 2.0))
            pts.append((x_out - hook_d, c + hook_h / 2.0))
            pts.append((x_out, c + hook_h / 2.0))
        else:
            pts.append((x_out, c + hook_h / 2.0))
            pts.append((x_out + hook_d, c + hook_h / 2.0))
            pts.append((x_out + hook_d, c - hook_h / 2.0))
            pts.append((x_out, c - hook_h / 2.0))
        pts.append((x_out, y_b))
        return pts

    def left_side_points() -> List[Tuple[float, float]]:
        """左侧轮廓，从 (0,y0) 到 (0,y4)。"""
        pts: List[Tuple[float, float]] = []
        # 前壁锁扣翼（底部翼 = 腰部翼尺寸 H-t；沿主面板方向上下各缩 t 顺畅插入盒内）
        pts += [(0.0, y0), (0.0, y0 + t), (-lock_w, y0 + t), (-lock_w, y1 - t), (0.0, y1 - t), (0.0, y1)]
        pts.append((0.0, y_in_lo))                  # 前壁顶 → 外段底边台阶（竖直，避免斜线）
        # 底面左侧壁（内段 + 外段插舌，末端凸起钩；外段相对内段垂直居中缩进 side_comp/2）
        pts.append((ofs_b - side_total, y_in_lo))   # 外段底边（水平）
        pts += side_hooks(ofs_b - side_total, y_in_lo, y_in_hi, up=True)
        pts.append((ofs_b - side_inner, y_in_hi))   # 外段顶边（居中缩进）
        pts.append((ofs_b - side_inner, y2_side))   # 内段台阶（内段全高）
        pts.append((ofs_b, y2_side))                # 内段顶边（= 制造宽顶）
        pts.append((0.0, y2_side))                  # 内段顶边 → 后壁左缘（水平）
        pts.append((0.0, y2 + t))                   # 后壁左缘底部缺口（竖直）
        # 后壁矩形翼（腰部翼，矩形 = 前壁锁扣翼；上下各缩 t，竖直升/降边避免斜线）
        pts += [(-back_w, y2 + t), (-back_w, y3 - t), (0.0, y3 - t)]
        # 外凸圆喙交汇（轴对称）：后腰翼顶边(0,y3-t) → 水平到盖翼左缘(ofs_l,y3-t) → 竖直到盖翼底边(ofs_l,y3+t)
        pts += rounded_polyline([(0.0, y3 - t), (ofs_l, y3 - t), (ofs_l, y3 + t)], beak_r, {1})
        # 盖面盖翼：左右外侧拐角统一圆角化，形成完整等腰梯形（上下各缩 t）
        pts += rounded_polyline(
            [(ofs_l, y3 + t), (ofs_l - wing_w, y3 + t + slant_w),
             (ofs_l - wing_w, y4 - t - slant_w), (ofs_l, y4 - t)],
            corner_radius,
            {1, 2},
        )
        # 外凸圆喙交汇（朝盒内 +x 凸，轴对称）：盖翼顶边(ofs_l,y4-t) → 耳翼底边(0,y4+t)
        pts += rounded_polyline([(ofs_l, y4 - t), (ofs_l, y4 + t), (0.0, y4 + t)], beak_r, {1})
        return pts

    def tuck_outline() -> List[Tuple[float, float]]:
        """插舌本体与左右耳翼的统一对称外轮廓（耳翼为直角三角形，底边水平，顶角圆角由 tab_ear_radius 控制）。"""
        apex_r = _clamp(tab_ear_radius, 0.0, tab_ear_w * 0.5)
        outline = [
            (0.0, y4 + t),                            # 左耳翼底角（直角，插舌左壁底）
            (-tab_ear_w, y4 + t),                     # 左耳翼外底角（水平伸出）
            (0.0, y5 - t),                            # 左耳翼顶角（收回插舌左壁顶）
            (colW, y5 - t),                           # 右耳翼顶角
            (colW + tab_ear_w, y4 + t),               # 右耳翼外底角（水平伸出）
            (colW, y4 + t),                           # 右耳翼底角（直角，插舌右壁底）
        ]
        return rounded_polyline(outline, apex_r, {1, 4})

    def right_side_points() -> List[Tuple[float, float]]:
        """右侧轮廓，从 (Lx,y4) 到 (Lx,y0)。"""
        pts: List[Tuple[float, float]] = []
        # 外凸圆喙交汇（轴对称）：耳翼底边(colW,y4+t) → 水平到盖翼右缘(ofs_l+lidW,y4+t) → 竖直到盖翼顶边(ofs_l+lidW,y4-t)
        pts += rounded_polyline([(colW, y4 + t), (ofs_l + lidW, y4 + t), (ofs_l + lidW, y4 - t)], beak_r, {1})
        # 盖面盖翼：左右外侧拐角统一圆角化，形成完整等腰梯形（上下各缩 t）
        pts += rounded_polyline(
            [(ofs_l + lidW, y4 - t), (ofs_l + lidW + wing_w, y4 - t - slant_w),
             (ofs_l + lidW + wing_w, y3 + t + slant_w), (ofs_l + lidW, y3 + t)],
            corner_radius,
            {1, 2},
        )
        # 后壁矩形翼（右，矩形 = 前壁锁扣翼；上下各缩 t，竖直升/降边避免斜线）
        pts.append((ofs_l + lidW, y3 + t))          # 盖翼底边内端
        # 外凸圆喙交汇（朝盒内 -x 凸，轴对称）：盖翼底边(ofs_l+lidW,y3+t) → 后腰翼顶边(colW,y3-t)
        pts += rounded_polyline([(ofs_l + lidW, y3 + t), (ofs_l + lidW, y3 - t), (colW, y3 - t)], beak_r, {1})
        pts += [(colW + back_w, y3 - t), (colW + back_w, y2 + t), (colW, y2 + t)]   # 后腰翼
        pts.append((colW, y2_side))                 # 后壁右缘底部缺口（竖直）
        # 底面右侧壁（内段顶边到外段顶角，向下走到外段底角，末端凸起钩；外段垂直居中缩进）
        pts.append((ofs_b + Lx, y2_side))               # 内段顶角
        pts.append((ofs_b + Lx + side_inner, y2_side))  # 内段|外段分界线顶
        pts.append((ofs_b + Lx + side_inner, y_in_hi))  # 外段顶角（居中缩进）
        pts += side_hooks(ofs_b + Lx + side_total, y_in_hi, y_in_lo, up=False)
        pts.append((colW, y_in_lo))                 # 外段底边 → 前壁顶台阶（水平，避免斜线）
        pts.append((colW, y1))                      # 台阶（竖直）
        # 前壁锁扣翼（右；上下各缩 t，严格镜像左翼：含前壁右缘上下缺口 + 前壁底边角）
        pts += [(colW, y1 - t), (colW + lock_w, y1 - t), (colW + lock_w, y0 + t), (colW, y0 + t), (colW, y0)]
        return pts

    # ---- 外轮廓（模切线）----
    outline = left_side_points() + tuck_outline() + right_side_points() + [(0.0, y0)]
    poly("cut", outline)

    # ---- 压痕线（折叠线）----
    # 主列横向折痕：前壁|底面|后壁|盖面|插舌
    # y1/y2/y3 处与分刀线共线（侧翼切口延伸），标记 cut=True 供分层渲染
    for yy in (y1, y2, y3, y4):
        poly("crease", [(0.0, yy), (colW, yy)], cut=(yy in (y1, y2, y3)))
    # 左/右侧翼与主列连接折痕（一折；折线只画在翼根部范围内，翼上下各缩 t）
    poly("crease", [(0.0, y0 + t), (0.0, y1 - t)])      # 前壁|锁扣翼
    poly("crease", [(ofs_b, y1), (ofs_b, y2)])      # 底面|侧壁
    poly("crease", [(0.0, y2 + t), (0.0, y3 - t)])      # 后壁|矩形翼
    poly("crease", [(ofs_l, y3 + t), (ofs_l, y4 - t)])      # 盖面|盖翼
    poly("crease", [(0.0, y4 + t), (0.0, y5 - t)])      # 插舌|左翼（翼内边，闭合）
    poly("crease", [(colW, y0 + t), (colW, y1 - t)])      # 前壁|锁扣翼（右）
    poly("crease", [(ofs_b + Lx, y1), (ofs_b + Lx, y2)])      # 底面|侧壁（右）
    poly("crease", [(colW, y2 + t), (colW, y3 - t)])      # 后壁|矩形翼（右）
    poly("crease", [(ofs_l + lidW, y3 + t), (ofs_l + lidW, y4 - t)])      # 盖面|盖翼（右）
    poly("crease", [(colW, y4 + t), (colW, y5 - t)])      # 插舌|右翼（翼内边，闭合）
    # 两折翼内部折线（随翼高收缩）
    poly("crease", [(ofs_l - wing_fold, y3 + t), (ofs_l - wing_fold, y4 - t)])
    poly("crease", [(ofs_l + lidW + wing_fold, y3 + t), (ofs_l + lidW + wing_fold, y4 - t)])
    poly("crease", [(-back_fold, y2 + t), (-back_fold, y3 - t)])
    poly("crease", [(colW + back_fold, y2 + t), (colW + back_fold, y3 - t)])
    # 大侧壁内部折线（内段|间隙段|插入段，折叠后外段距内段 2t 空隙）
    poly("crease", [(ofs_b - side_inner, y1), (ofs_b - side_inner, y2_side)])
    poly("crease", [(ofs_b + Lx + side_inner, y1), (ofs_b + Lx + side_inner, y2_side)])
    poly("crease", [(ofs_b - side_inner - gap, y_in_lo), (ofs_b - side_inner - gap, y_in_hi)])
    poly("crease", [(ofs_b + Lx + side_inner + gap, y_in_lo), (ofs_b + Lx + side_inner + gap, y_in_hi)])

    # ---- 分刀线（相邻侧翼之间切开）----
    # 两翼收缩后，翼边界已由外轮廓定义，分刀线在原 y1/y2/y3 悬空，故不再生成

    # ---- 底面侧壁凸钩对应的插口 ----
    # 插口沿盒宽方向开刀，位置与左右侧壁凸钩中心对齐，并关于底面中心镜像。
    # 插口为封闭矩形，短边使用纸板厚度，避免单刀线无法形成实际开口。
    slot_center = (y1 + y2) / 2.0
    slot_low = slot_center - hook_h / 2.0
    slot_high = slot_center + hook_h / 2.0
    slot_center_x = min(hook_d, colW / 2.0)
    slot_half_width = min(t / 2.0, slot_center_x, (colW / 2.0) - slot_center_x)
    # 插孔对齐插入段折叠后的落点（底面内移 gap，即距内段 gap 处，关于刀版中心对称）
    left_slot_c = ofs_b + gap
    right_slot_c = ofs_b + Lx - gap
    left_slot_x0 = left_slot_c - slot_half_width
    left_slot_x1 = left_slot_c + slot_half_width
    right_slot_x0 = right_slot_c - slot_half_width
    right_slot_x1 = right_slot_c + slot_half_width
    poly("cut", [
        (left_slot_x0, slot_low), (left_slot_x1, slot_low),
        (left_slot_x1, slot_high), (left_slot_x0, slot_high),
        (left_slot_x0, slot_low),
    ])
    poly("cut", [
        (right_slot_x0, slot_low), (right_slot_x1, slot_low),
        (right_slot_x1, slot_high), (right_slot_x0, slot_high),
        (right_slot_x0, slot_low),
    ])

    # ---- 可选图层：防尘耳半切线（HALFCUT）----
    if layers and "HALFCUT" in layers:
        # 左右插舌耳翼中线半切线，便于撕除防尘耳（随翼收缩）
        poly("halfcut", [(-tab_ear_w * 0.5, y4 + t), (-tab_ear_w * 0.5, y5 - t)])
        poly("halfcut", [(colW + tab_ear_w * 0.5, y4 + t), (colW + tab_ear_w * 0.5, y5 - t)])

    # ---- 可选图层：关键尺寸标注线（DIMENSION）----
    if layers and "DIMENSION" in layers:
        dim_margin = 8.0
        xd = -(tab_ear_w + dim_margin)   # 左侧总长标注位置
        xd_r = colW - xd                 # 右侧对称标注位置（关于列宽中轴镜像）
        yd = y0 - dim_margin             # 底部长度标注位置
        # 长度（底部水平，关于列宽中轴居中）
        poly("dimension", [((colW - Lx) / 2.0, yd), ((colW + Lx) / 2.0, yd)])
        # 展开总高（左右对称竖直标注）：前壁+底面+后壁+盖面+插舌
        poly("dimension", [(xd, y0), (xd, y5)])
        poly("dimension", [(xd_r, y0), (xd_r, y5)])

    return DieCutGeometry(
        length=L,
        width=W,
        height=H,
        thickness=t,
        wall_height=Hw,
        bottom_height=W + side_comp,   # 盒底宽度 = 制造宽（盒底与后腰折线 → 盒底与前端折线）
        lid_height=W,
        tab_depth=tab,
        wing_width=wing_w,
        back_flap_width=back_w,
        lock_width=lock_w,
        side_inner=side_inner,
        side_outer=side_outer,
        fold_seg=fold_seg,
        segments=segments,
        corner_radius=corner_radius,
        hook_ratio=hook_ratio,
        board_compensation=internal,
        layers=list(layers) if layers else ["CUT", "CREASE"],
        column_width=colW,
        lid_width=lidW,
        side_height=W + side_comp,
    )


def validate_geometry(geo: DieCutGeometry) -> List[str]:
    """检查几何对象是否适合导出和拼版。"""
    errors: List[str] = []
    for index, segment in enumerate(geo.segments):
        if len(segment.points) < 2:
            errors.append(f"segment[{index}] 少于两个点")
        for point in segment.points:
            if not all(math.isfinite(value) for value in point):
                errors.append(f"segment[{index}] 包含非有限坐标")
        if any(first == second for first, second in zip(segment.points, segment.points[1:])):
            errors.append(f"segment[{index}] 包含连续重复点")
    min_x, min_y, max_x, max_y = geo.bounds
    if not (min_x < max_x and min_y < max_y):
        errors.append("刀版边界无效")
    return errors


def geometry_to_json(geo: DieCutGeometry) -> dict:
    """将几何转换为稳定的 API geometry contract。"""
    y0 = 0.0
    y1 = geo.wall_height
    y2 = y1 + geo.bottom_height
    y3 = y2 + geo.wall_height
    y4 = y3 + geo.lid_height
    y5 = y4 + geo.tab_depth
    colW = geo.column_width or geo.length
    lidW = geo.lid_width or geo.length
    Lx = colW + 2.0 * geo.thickness      # 制造尺寸 = 制造宽 + 2t
    ofs_b = (colW - Lx) / 2.0            # 底面居中（底面 = 制造尺寸 Lx）
    ofs_l = (colW - lidW) / 2.0          # 盖面居中
    wing_w = geo.wing_width
    lock_w = geo.lock_width
    back_w = geo.back_flap_width
    tab_ear_w = wing_w                       # 插舌翼横向 = 盖翼 = 锁扣翼 = H - t
    tab_ear_slant = min(12.0, geo.tab_depth * 0.2)
    slant_w = min(wing_w * 0.3, 0.15 * geo.length)
    t = geo.thickness                        # 纸板厚度
    hook_d = geo.thickness                   # 大侧壁外段插舌长度 = 材料厚度
    hook_h = geo.width * geo.hook_ratio      # 凸起钩高度（居中，可调比例）
    side_comp = (geo.side_height or geo.width) - geo.width   # 侧壁宽补偿
    outer_h = geo.width                      # 大侧壁外段高度 = 盒宽 W（内宽，相对内段居中缩进 side_comp/2）
    outer_lo = side_comp / 2.0               # 外段局部 y 起点（居中）
    outer_c = outer_lo + outer_h / 2.0
    gap = 3.0 * geo.thickness                # 间隙段（3t，含侧壁厚度；折叠后净空隙 2t 容纳腰部翼/耳翼）
    side_inner = geo.side_inner
    side_outer = geo.side_outer
    side_total = side_inner + gap + side_outer
    y2_side = y2                             # 内段顶边 = 底面顶（制造宽，与后腰翼底边共线）
    y_in_lo = y1 + side_comp / 2.0           # 外段底边（居中缩进）
    y_in_hi = y2 - side_comp / 2.0           # 外段顶边（居中缩进）
    return {
        "schema_version": "1.0",
        "type": "airplane_box",
        "units": "mm",
        "dimensions": {
            "length": geo.length,
            "width": geo.width,
            "height": geo.height,
            "thickness": geo.thickness,
        },
        "derived": {
            "wall_height": geo.wall_height,
            "bottom_height": geo.bottom_height,
            "lid_height": geo.lid_height,
            "tab_depth": geo.tab_depth,
            "wing_width": geo.wing_width,
            "side_inner": geo.side_inner,
            "side_outer": geo.side_outer,
            "column_width": geo.column_width or geo.length,
            "lid_width": geo.lid_width or geo.length,
            "side_height": geo.side_height or geo.width,
        },
        "bounds": dict(zip(("min_x", "min_y", "max_x", "max_y"), geo.bounds)),
        "layers": list(geo.layers),
        "panels": [
            # 主面板（竖排 5 层）：bounds = 网区域，anchor = 折痕锚点，shape = 梯形翼局部顶点（null = 矩形）
            {"id": "front_wall", "bounds": [0.0, y0, colW, y1], "anchor": [0.0, y1], "shape": None},
            {"id": "bottom", "bounds": [ofs_b, y1, ofs_b + Lx, y2], "anchor": [ofs_b, y1], "shape": None},
            {"id": "back_wall", "bounds": [0.0, y2, colW, y3], "anchor": [0.0, y2], "shape": None},
            {"id": "lid", "bounds": [ofs_l, y3, ofs_l + lidW, y4], "anchor": [ofs_l, y3], "shape": None},
            {"id": "tuck", "bounds": [0.0, y4, colW, y5], "anchor": [0.0, y4], "shape": None},
            # 前壁锁扣翼（矩形 = 腰部翼尺寸 H - t；沿主面板方向上下各缩 t）
            {"id": "lock_left", "bounds": [-lock_w, y0 + t, 0.0, y1 - t], "anchor": [0.0, y1], "shape": None},
            {"id": "lock_right", "bounds": [colW, y0 + t, colW + lock_w, y1 - t], "anchor": [colW, y1], "shape": None},
            # 后壁矩形翼（腰部翼；上下各缩 t）
            {"id": "back_wing_left", "bounds": [-back_w, y2 + t, 0.0, y3 - t], "anchor": [0.0, y2], "shape": None},
            {"id": "back_wing_right", "bounds": [colW, y2 + t, colW + back_w, y3 - t], "anchor": [colW, y2], "shape": None},
            # 盖翼（等腰梯形，从盖面左右缘伸出；上下各缩 t）
            {"id": "lid_wing_left", "bounds": [ofs_l - wing_w, y3 + t, ofs_l, y4 - t], "anchor": [ofs_l, y3],
             "shape": [[0, t], [0, geo.lid_height - t], [-wing_w, geo.lid_height - t - slant_w], [-wing_w, t + slant_w]]},
            {"id": "lid_wing_right", "bounds": [colW - ofs_l, y3 + t, colW - ofs_l + wing_w, y4 - t], "anchor": [colW - ofs_l, y3],
             "shape": [[0, t], [0, geo.lid_height - t], [wing_w, geo.lid_height - t - slant_w], [wing_w, t + slant_w]]},
            # 插舌耳翼（直角三角形；底边水平，直角靠插舌侧壁，上下各缩 t）
            {"id": "tuck_ear_left", "bounds": [-tab_ear_w, y4 + t, 0.0, y5 - t], "anchor": [0.0, y4],
             "shape": [[0, t], [-tab_ear_w, t], [0, geo.tab_depth - t]]},
            {"id": "tuck_ear_right", "bounds": [colW, y4 + t, colW + tab_ear_w, y5 - t], "anchor": [colW, y4],
             "shape": [[0, t], [tab_ear_w, t], [0, geo.tab_depth - t]]},
            # 大侧壁内段（成盒壁）
            {"id": "left_wall", "bounds": [ofs_b - side_inner, y1, ofs_b, y2_side], "anchor": [ofs_b, y1], "shape": None},
            {"id": "right_wall", "bounds": [ofs_b + Lx, y1, ofs_b + Lx + side_inner, y2_side], "anchor": [ofs_b + Lx, y1], "shape": None},
            # 大侧壁间隙段（2t，折叠后形成内段与外段之间的空隙，容纳腰部翼/耳翼厚度；随外段居中缩进）
            {"id": "left_gap", "bounds": [ofs_b - side_inner - gap, y_in_lo, ofs_b - side_inner, y_in_hi], "anchor": [ofs_b - side_inner, y1], "shape": None},
            {"id": "right_gap", "bounds": [ofs_b + Lx + side_inner, y_in_lo, ofs_b + Lx + side_inner + gap, y_in_hi], "anchor": [ofs_b + Lx + side_inner, y1], "shape": None},
            # 大侧壁插入段（折叠后插入盒底，末端凸起钩=插舌，两侧清废；shape 裁剪出插舌，避免 3D 显示多余材料）
            {"id": "left_insert", "bounds": [ofs_b - side_total - hook_d, y_in_lo, ofs_b - side_inner - gap, y_in_hi], "anchor": [ofs_b - side_inner - gap, y1],
             "shape": [[-side_outer, outer_lo], [-side_outer, outer_c - hook_h / 2.0], [-side_outer - hook_d, outer_c - hook_h / 2.0],
                       [-side_outer - hook_d, outer_c + hook_h / 2.0], [-side_outer, outer_c + hook_h / 2.0],
                       [-side_outer, outer_lo + outer_h], [0.0, outer_lo + outer_h], [0.0, outer_lo]]},
            {"id": "right_insert", "bounds": [ofs_b + Lx + side_inner + gap, y_in_lo, ofs_b + Lx + side_total + hook_d, y_in_hi], "anchor": [ofs_b + Lx + side_inner + gap, y1],
             "shape": [[0.0, outer_lo], [0.0, outer_lo + outer_h], [side_outer, outer_lo + outer_h], [side_outer, outer_c + hook_h / 2.0],
                       [side_outer + hook_d, outer_c + hook_h / 2.0], [side_outer + hook_d, outer_c - hook_h / 2.0],
                       [side_outer, outer_c - hook_h / 2.0], [side_outer, outer_lo]]},
        ],
        "fold_sequence": [
            {"order": 1, "from": "front_wall", "to": "bottom", "axis_y": y1},
            {"order": 2, "from": "back_wall", "to": "bottom", "axis_y": y2},
            {"order": 3, "from": "lid", "to": "back_wall", "axis_y": y3},
            {"order": 4, "from": "tuck", "to": "lid", "axis_y": y4},
        ],
        "fold_lines": [
            {"points": [list(point) for point in segment.points], "cut": segment.cut}
            for segment in geo.segments
            if segment.kind == "crease"
        ],
        "segments": [
            {
                "kind": segment.kind,
                "cut": segment.cut,
                "points": [list(point) for point in segment.points],
            }
            for segment in geo.segments
        ],
    }


def estimate_sheet_utilization(
    geo: DieCutGeometry,
    sheet_width: float,
    sheet_height: float,
    margin: float = 10.0,
    gap: float = 5.0,
) -> dict:
    """用刀版包围盒估算直放/横放的拼版数量和利用率。"""
    if min(sheet_width, sheet_height) <= 0 or min(margin, gap) < 0:
        raise ValueError("纸张尺寸、边距和间距必须有效")
    min_x, min_y, max_x, max_y = geo.bounds
    blank_width = max_x - min_x
    blank_height = max_y - min_y
    sheet_area = sheet_width * sheet_height
    candidates = []
    for rotation, item_width, item_height in (
        (0, blank_width, blank_height),
        (90, blank_height, blank_width),
    ):
        usable_width = sheet_width - 2 * margin
        usable_height = sheet_height - 2 * margin
        columns = int((usable_width + gap) // (item_width + gap)) if item_width else 0
        rows = int((usable_height + gap) // (item_height + gap)) if item_height else 0
        count = max(0, columns) * max(0, rows)
        used_area = count * blank_width * blank_height
        candidates.append({
            "rotation": rotation,
            "columns": max(0, columns),
            "rows": max(0, rows),
            "count": count,
            "utilization": used_area / sheet_area if sheet_area else 0.0,
        })
    best = max(candidates, key=lambda item: (item["count"], item["utilization"]))
    return {
        "sheet_width_mm": sheet_width,
        "sheet_height_mm": sheet_height,
        "margin_mm": margin,
        "gap_mm": gap,
        "blank_width_mm": blank_width,
        "blank_height_mm": blank_height,
        "rotation": best["rotation"],
        "columns": best["columns"],
        "rows": best["rows"],
        "count": best["count"],
        "utilization": best["utilization"],
        "candidates": candidates,
        "nesting_hint": "优先采用包围盒利用率最高的旋转方向",
    }


# ---------------------------------------------------------------------------
# SVG 输出
# ---------------------------------------------------------------------------

def _format_pt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


LAYER_OF_KIND = {
    "cut": "CUT",
    "crease": "CREASE",
    "halfcut": "HALFCUT",
    "dimension": "DIMENSION",
}


def _dimension_marks(points):
    """为一条 dimension 折线生成端部箭头 path 与中点标注文字。

    返回 (arrows: list[str], text: (x, y, label, rotate) | None)。
    仅对每个线段标注尺寸值（mm），当前 dimension 段均为单线段。
    """
    arrows = []
    texts = []
    tick = 1.6  # 端部箭头长度（mm）
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx, dy = x1 - x0, y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-9:
            continue
        ang = math.atan2(dy, dx)
        for (px, py, dirn) in ((x0, y0, 1), (x1, y1, -1)):
            base = ang if dirn > 0 else ang + math.pi
            for off in (math.pi * 0.8, -math.pi * 0.8):
                ex = px + tick * math.cos(base + off)
                ey = py + tick * math.sin(base + off)
                arrows.append(
                    f'<path class="dimension" d="M{_format_pt(px)} {_format_pt(py)} '
                    f'L{_format_pt(ex)} {_format_pt(ey)}"/>'
                )
        texts.append(
            ((x0 + x1) / 2.0, (y0 + y1) / 2.0, f"{seg_len:.1f}",
             -90 if abs(dy) > abs(dx) else 0)
        )
    return arrows, texts[0] if texts else None


def geometry_to_svg(geo: DieCutGeometry, title: str = "") -> str:
    min_x, min_y, max_x, max_y = geo.bounds
    pad = 10.0
    vb_x = min_x - pad
    vb_y = min_y - pad
    vb_w = (max_x - min_x) + 2 * pad
    vb_h = (max_y - min_y) + 2 * pad

    # 线条宽度随纸板厚度动态调整（Step 1 项 5）
    t = geo.thickness
    cut_w = 0.25 + t * 0.02
    crease_w = 0.20 + t * 0.02
    halfcut_w = 0.15 + t * 0.02
    dim_w = 0.35

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_format_pt(vb_w)}mm" '
        f'height="{_format_pt(vb_h)}mm" viewBox="{_format_pt(vb_x)} {_format_pt(vb_y)} {_format_pt(vb_w)} {_format_pt(vb_h)}">',
        '<defs>',
        '  <style>',
        f'    .cut {{ stroke: #000; stroke-width: {_format_pt(cut_w)}; fill: none; }}',
        f'    .crease {{ stroke: #e02020; stroke-width: {_format_pt(crease_w)}; stroke-dasharray: 4 2; fill: none; }}',
        f'    .halfcut {{ stroke: #1d4ed8; stroke-width: {_format_pt(halfcut_w)}; stroke-dasharray: 1 1.5; fill: none; }}',
        f'    .dimension {{ stroke: #334155; stroke-width: {_format_pt(dim_w)}; fill: none; }}',
        '  </style>',
        '</defs>',
    ]
    if title:
        parts.append(
            f'<text x="{_format_pt(vb_x + 2)}" y="{_format_pt(vb_y + 8)}" '
            f'font-size="4" fill="#666" font-family="sans-serif">{title}</text>'
        )
    # 翻转 Y 轴：让插舌(顶)显示在上方，与参考图方向一致
    flip_t = 2 * vb_y + vb_h
    parts.append(f'<g transform="translate(0,{_format_pt(flip_t)}) scale(1,-1)">')
    active = set(geo.layers)
    dim_texts = []
    # 按图层分组渲染（Step 5）：CUT / CREASE / 可选 HALFCUT / DIMENSION
    for layer in ("CUT", "CREASE", "HALFCUT", "DIMENSION"):
        if layer not in active:
            continue
        parts.append(f'  <g id="layer-{layer}">')
        for seg in geo.segments:
            if LAYER_OF_KIND.get(seg.kind) != layer:
                continue
            d_parts = []
            for i, (x, y) in enumerate(seg.points):
                cmd = "M" if i == 0 else "L"
                d_parts.append(f"{cmd}{_format_pt(x)} {_format_pt(y)}")
            parts.append(f'    <path class="{seg.kind}" d="{" ".join(d_parts)}"/>')
            if seg.kind == "dimension":
                arrows, lbl = _dimension_marks(seg.points)
                parts.extend(arrows)
                if lbl:
                    dim_texts.append(lbl)
        parts.append("  </g>")
    parts.append("</g>")
    # 尺寸标注文字：组内坐标被 scale(1,-1) 倒置，故在翻转组外按翻转还原后输出，
    # 文字本身保持正向可读。
    for (tx, ty, label, rot) in dim_texts:
        ty2 = flip_t - ty
        rot_attr = f' transform="rotate({rot} {_format_pt(tx)} {_format_pt(ty2)})"' if rot else ""
        parts.append(
            f'<text x="{_format_pt(tx)}" y="{_format_pt(ty2)}" font-size="3.4" '
            f'fill="#334155" font-family="sans-serif" text-anchor="middle"'
            f'{rot_attr}>{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# PDF 输出（ReportLab，无需 LibreOffice）
# ---------------------------------------------------------------------------

def geometry_to_pdf_bytes(geo: DieCutGeometry, title: str = "") -> bytes:
    from reportlab.lib.pagesizes import mm
    from reportlab.pdfgen import canvas

    min_x, min_y, max_x, max_y = geo.bounds
    pad_mm = 15.0
    page_w = (max_x - min_x) + 2 * pad_mm
    page_h = (max_y - min_y) + 2 * pad_mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w * mm, page_h * mm))
    c.setTitle(title or "飞机盒刀版")

    tx = pad_mm - min_x
    ty = pad_mm - min_y

    def draw_segment(seg: Segment) -> None:
        c.saveState()
        if seg.kind == "cut":
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(0.5 + geo.thickness * 0.02)
            c.setDash()
        elif seg.kind == "halfcut":
            c.setStrokeColorRGB(0.1, 0.3, 0.8)
            c.setLineWidth(0.2 + 0.0)
            c.setDash(1, 1.5)
        elif seg.kind == "dimension":
            c.setStrokeColorRGB(0.2, 0.25, 0.33)
            c.setLineWidth(0.35)
            c.setDash()
        else:
            c.setStrokeColorRGB(0.9, 0.1, 0.1)
            c.setLineWidth(0.35 + geo.thickness * 0.02)
            c.setDash(3, 2)
        p = c.beginPath()
        x0, y0 = seg.points[0]
        p.moveTo((x0 + tx) * mm, (y0 + ty) * mm)
        for x, y in seg.points[1:]:
            p.lineTo((x + tx) * mm, (y + ty) * mm)
        c.drawPath(p, stroke=1, fill=0)
        c.restoreState()

    active = set(geo.layers)
    for seg in geo.segments:
        if LAYER_OF_KIND.get(seg.kind) not in active:
            continue
        draw_segment(seg)

    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont("Helvetica", 8)
    c.drawString(10 * mm, page_h * mm - 10 * mm, title or "Airplane Box Die Cut (mm)")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# DXF 输出（ezdxf）
# ---------------------------------------------------------------------------

def geometry_to_dxf_bytes(geo: DieCutGeometry, title: str = "") -> bytes:
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # 毫米
    msp = doc.modelspace()

    if "CUT" not in doc.layers:
        doc.layers.add("CUT", color=1)
    if "CREASE" not in doc.layers:
        doc.layers.add("CREASE", color=5)
    if "HALFCUT" not in doc.layers:
        doc.layers.add("HALFCUT", color=4)
    if "DIMENSION" not in doc.layers:
        doc.layers.add("DIMENSION", color=2)

    try:
        if "DASHED" not in doc.linetypes:
            doc.linetypes.add("DASHED", pattern=[0.2, 0.1, -0.1])
    except Exception:
        pass

    dxf_layer = {
        "cut": "CUT",
        "crease": "CREASE",
        "halfcut": "HALFCUT",
        "dimension": "DIMENSION",
    }
    active = set(geo.layers)
    for seg in geo.segments:
        if dxf_layer.get(seg.kind) not in active:
            continue
        layer = dxf_layer.get(seg.kind, "CREASE")
        attribs = {"layer": layer}
        if seg.kind == "crease":
            try:
                attribs["linetype"] = "DASHED"
            except Exception:
                pass
        pts = seg.points
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            msp.add_line((x0, y0), (x1, y1), dxfattribs=attribs)

    if title:
        msp.add_text(
            title,
            dxfattribs={
                "height": 3.0,
                "layer": "CUT" if "CUT" in active else (geo.layers[0] if geo.layers else "CUT"),
                "insert": (geo.bounds[0], geo.bounds[1] - 8.0),
            },
        )

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
