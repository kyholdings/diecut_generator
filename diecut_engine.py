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
    """一段刀线。kind: 'cut' 或 'crease'，points 为折线顶点。"""
    kind: str
    points: List[Tuple[float, float]]


@dataclass
class DieCutGeometry:
    """完整的刀版几何。"""
    length: float          # 内尺寸长 L（mm，横向列宽）
    width: float           # 内尺寸宽 W（mm，底面高度）
    height: float          # 内尺寸高 H（mm，盒高）
    thickness: float       # 纸板厚度 t（mm）
    wall_height: float     # 壁展开尺寸 = H + t（前/后壁、大侧壁内段）
    bottom_height: float   # 底面高度 = W（盒宽）
    lid_height: float      # 盖子顶面高度 = W（盒宽，盖住盒顶）
    tab_depth: float       # 插舌高度 = H（盒高，梯形圆角 + 两侧耳翼）
    wing_width: float      # 盖翼宽度 = H - t（两折）
    back_flap_width: float # 后壁矩形翼宽度 = H - t（腰部翼）
    lock_width: float      # 前壁锁扣翼宽度 = H - t（底部翼，与腰部翼同尺寸）
    side_inner: float      # 大侧壁内段 = H + t（侧壁主体，一折）
    side_outer: float      # 大侧壁外段 = H - t（折叠后插入盒底）
    fold_seg: float        # 两折翼的插入段长度
    segments: List[Segment] = field(default_factory=list)

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
) -> DieCutGeometry:
    """
    构建自锁式飞机盒刀版几何（按折叠逻辑严格推算尺寸）。

    折叠逻辑：
      - 列宽（横向） = 盒长 L
      - 底面高度 = 盒宽 W
      - 前壁 / 后壁 = 盒高 H + 纸厚 t（从底面折起 90°，一折）
      - 盖子顶面高度 = 盒宽 W（平面盖面，盖住盒顶）
      - 插舌高度 = 盒高 H，梯形 + 顶部圆弧化
      - 底面大侧壁宽度 = H + t（一折）
      - 盖翼（机翼）/ 后壁矩形翼宽度 = H - t（两折）

    参数：
      length / width / height : 长 / 宽 / 高（mm）
      thickness               : 纸板厚度（mm）
      internal                : True 内尺寸，False 外尺寸
      tab_depth               : 插舌深度（mm），默认 20
      fold_ratio              : 两折翼插入段占总宽比例，默认 0.3
      lock_ratio              : 锁扣翼宽度比例，默认 1.0
    """
    L = float(length)
    W = float(width)
    H = float(height)
    t = float(thickness)

    if min(L, W, H, t) <= 0:
        raise ValueError("长、宽、高、纸厚必须为正数")

    if not internal:
        L = max(L - 2 * t, 1.0)
        W = max(W - 2 * t, 1.0)
        H = max(H - t, 1.0)

    Hw = H + t                                  # 前后壁展开高度（一折）
    tab = max(float(tab_depth) if tab_depth else H, 4.0)   # 插舌高度 = 盒高 H（梯形圆角+两侧耳翼）
    wing_w = max(H - t, 4.0)                    # 盖翼宽度（两折 = H - t）
    back_w = max(H - t, 4.0)                    # 后壁矩形翼宽度（腰部翼 = H - t）
    lock_w = max((H - t) * float(lock_ratio), 4.0)   # 前壁锁扣翼（底部翼 = 腰部翼尺寸 H - t）
    side_inner = Hw                             # 大侧壁内段（侧壁主体，一折 = H + t）
    side_outer = max(H - t, 4.0)                # 大侧壁外段（折叠后插入盒底 = H - t）
    side_total = side_inner + side_outer        # 大侧壁总宽（两段）
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
    hook_d = max(8.0, H * 0.15)                 # 大侧壁外段插舌末端凸起钩深度
    hook_h = W / 3.0                            # 插舌末端凸起钩高度（居中 1 个）

    # 纵向分层（从下到上）
    y0 = 0.0
    y1 = Hw                 # 前壁顶
    y2 = Hw + W             # 底面顶
    y3 = Hw + W + Hw        # 后壁顶
    y4 = y3 + W             # 盖子顶面顶（高度 = 盒宽 W，盖住盒顶）
    y5 = y4 + tab           # 插舌顶（高度 = 盒高 H）

    Lx = L                  # 列宽

    segments: List[Segment] = []

    def poly(kind: str, pts: List[Tuple[float, float]]) -> None:
        segments.append(Segment(kind, pts))

    def arc_pts(cx: float, cy: float, r: float, t0: float, t1: float, n: int = 10) -> List[Tuple[float, float]]:
        """以 (cx,cy) 为圆心、半径 r 的圆弧，t0..t1 弧度。"""
        out = []
        for i in range(n + 1):
            th = t0 + (t1 - t0) * i / n
            out.append((cx + r * math.cos(th), cy + r * math.sin(th)))
        return out

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
        # 前壁锁扣翼（底部翼 = 腰部翼尺寸 H-t）
        pts += [(0.0, y0), (-lock_w, y0), (-lock_w, y1), (0.0, y1)]
        # 底面左侧壁（内段 H+t + 外段插舌 H-t，末端三个凸起钩）
        pts.append((-side_total, y1))
        pts += side_hooks(-side_total, y1, y2, up=True)
        pts.append((0.0, y2))
        # 后壁矩形翼（腰部翼，矩形 = 前壁锁扣翼，宽度 H-t）
        pts += [(-back_w, y2), (-back_w, y3), (0.0, y3)]
        # 盖面盖翼（等腰梯形：外边垂直、上下两腰对称斜，宽度 H-t）
        pts += [(-wing_w, y3 + slant_w), (-wing_w, y4 - slant_w), (0.0, y4)]
        return pts

    def tuck_outline() -> List[Tuple[float, float]]:
        """插舌轮廓（本体矩形 + 两侧等腰梯形翼，左右绝对对称），从 (0,y4) 到 (Lx,y4)。"""
        pts: List[Tuple[float, float]] = []
        pts.append((0.0, y4))
        # 左翼（等腰梯形：下腰、外边、上腰）
        pts.append((-tab_ear_w, y4 + tab_ear_slant))
        pts.append((-tab_ear_w, y5 - tab_ear_slant))
        pts.append((0.0, y5))
        # 插舌顶边（水平全宽，本体矩形）
        pts.append((Lx, y5))
        # 右翼（等腰梯形：上腰、外边、下腰）
        pts.append((Lx + tab_ear_w, y5 - tab_ear_slant))
        pts.append((Lx + tab_ear_w, y4 + tab_ear_slant))
        pts.append((Lx, y4))
        return pts

    def right_side_points() -> List[Tuple[float, float]]:
        """右侧轮廓，从 (Lx,y4) 到 (Lx,y0)。"""
        pts: List[Tuple[float, float]] = []
        # 盖面盖翼（右，等腰梯形）
        pts += [(Lx + wing_w, y4 - slant_w), (Lx + wing_w, y3 + slant_w), (Lx, y3)]
        # 后壁矩形翼（右，矩形 = 前壁锁扣翼）
        pts += [(Lx + back_w, y3), (Lx + back_w, y2), (Lx, y2)]
        # 底面右侧壁（内段 H+t + 外段插舌 H-t，末端三个凸起钩，自上而下）
        pts.append((Lx + side_total, y2))
        pts += side_hooks(Lx + side_total, y2, y1, up=False)
        pts.append((Lx, y1))
        # 前壁锁扣翼（右）
        pts += [(Lx + lock_w, y1), (Lx + lock_w, y0), (Lx, y0)]
        return pts

    # ---- 外轮廓（模切线）----
    outline = left_side_points() + tuck_outline() + right_side_points() + [(0.0, y0)]
    poly("cut", outline)

    # ---- 压痕线（折叠线）----
    # 主列横向折痕：前壁|底面|后壁|盖面|插舌
    for yy in (y1, y2, y3, y4):
        poly("crease", [(0.0, yy), (Lx, yy)])
    # 左/右侧翼与主列连接折痕（一折）
    poly("crease", [(0.0, y0), (0.0, y1)])      # 前壁|锁扣翼
    poly("crease", [(0.0, y1), (0.0, y2)])      # 底面|侧壁
    poly("crease", [(0.0, y2), (0.0, y3)])      # 后壁|矩形翼
    poly("crease", [(0.0, y3), (0.0, y4)])      # 盖面|盖翼
    poly("crease", [(0.0, y4), (0.0, y5)])      # 插舌|左翼（翼内边，闭合）
    poly("crease", [(Lx, y0), (Lx, y1)])
    poly("crease", [(Lx, y1), (Lx, y2)])
    poly("crease", [(Lx, y2), (Lx, y3)])
    poly("crease", [(Lx, y3), (Lx, y4)])
    poly("crease", [(Lx, y4), (Lx, y5)])        # 插舌|右翼（翼内边，闭合）
    # 两折翼内部折线
    poly("crease", [(-wing_fold, y3), (-wing_fold, y4)])
    poly("crease", [(Lx + wing_fold, y3), (Lx + wing_fold, y4)])
    poly("crease", [(-back_fold, y2), (-back_fold, y3)])
    poly("crease", [(Lx + back_fold, y2), (Lx + back_fold, y3)])
    # 大侧壁内部折线（内段|外段，折叠后插入盒底）
    poly("crease", [(-side_inner, y1), (-side_inner, y2)])
    poly("crease", [(Lx + side_inner, y1), (Lx + side_inner, y2)])

    # ---- 分刀线（相邻侧翼之间切开）----
    # 锁扣翼 与 侧壁 之间
    poly("cut", [(-lock_w, y1), (0.0, y1)])
    poly("cut", [(Lx, y1), (Lx + lock_w, y1)])
    # 侧壁 与 后壁矩形翼 之间
    poly("cut", [(-back_w, y2), (0.0, y2)])
    poly("cut", [(Lx, y2), (Lx + back_w, y2)])
    # 后壁矩形翼 与 盖翼 之间
    poly("cut", [(-back_w, y3), (0.0, y3)])
    poly("cut", [(Lx, y3), (Lx + back_w, y3)])

    return DieCutGeometry(
        length=L,
        width=W,
        height=H,
        thickness=t,
        wall_height=Hw,
        bottom_height=W,
        lid_height=W,
        tab_depth=tab,
        wing_width=wing_w,
        back_flap_width=back_w,
        lock_width=lock_w,
        side_inner=side_inner,
        side_outer=side_outer,
        fold_seg=fold_seg,
        segments=segments,
    )


# ---------------------------------------------------------------------------
# SVG 输出
# ---------------------------------------------------------------------------

def _format_pt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def geometry_to_svg(geo: DieCutGeometry, title: str = "") -> str:
    min_x, min_y, max_x, max_y = geo.bounds
    pad = 10.0
    vb_x = min_x - pad
    vb_y = min_y - pad
    vb_w = (max_x - min_x) + 2 * pad
    vb_h = (max_y - min_y) + 2 * pad

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_format_pt(vb_w)}mm" '
        f'height="{_format_pt(vb_h)}mm" viewBox="{_format_pt(vb_x)} {_format_pt(vb_y)} {_format_pt(vb_w)} {_format_pt(vb_h)}">',
        '<defs>',
        '  <style>',
        '    .cut { stroke: #000; stroke-width: 0.25; fill: none; }',
        '    .crease { stroke: #e02020; stroke-width: 0.2; stroke-dasharray: 4 2; fill: none; }',
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
    for seg in geo.segments:
        cls = "cut" if seg.kind == "cut" else "crease"
        d_parts = []
        for i, (x, y) in enumerate(seg.points):
            cmd = "M" if i == 0 else "L"
            d_parts.append(f"{cmd}{_format_pt(x)} {_format_pt(y)}")
        parts.append(f'  <path class="{cls}" d="{" ".join(d_parts)}"/>')
    parts.append("</g>")
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
            c.setLineWidth(0.5)
            c.setDash()
        else:
            c.setStrokeColorRGB(0.9, 0.1, 0.1)
            c.setLineWidth(0.35)
            c.setDash(3, 2)
        p = c.beginPath()
        x0, y0 = seg.points[0]
        p.moveTo((x0 + tx) * mm, (y0 + ty) * mm)
        for x, y in seg.points[1:]:
            p.lineTo((x + tx) * mm, (y + ty) * mm)
        c.drawPath(p, stroke=1, fill=0)
        c.restoreState()

    for seg in geo.segments:
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

    try:
        if "DASHED" not in doc.linetypes:
            doc.linetypes.add("DASHED", pattern=[0.2, 0.1, -0.1])
    except Exception:
        pass

    for seg in geo.segments:
        layer = "CUT" if seg.kind == "cut" else "CREASE"
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
                "layer": "CUT",
                "insert": (geo.bounds[0], geo.bounds[1] - 8.0),
            },
        )

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
