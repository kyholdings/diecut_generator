# -*- coding: utf-8 -*-
"""
飞机盒刀版生成器 - Flask 后端。

启动:
    cd diecut_generator
    python app.py

默认地址: http://127.0.0.1:8899
"""

from __future__ import annotations

import os
import uuid

from flask import Flask, jsonify, request, send_from_directory

from diecut_engine import (
    build_airplane_box,
    geometry_to_dxf_bytes,
    geometry_to_pdf_bytes,
    geometry_to_svg,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def _float(value, default):
    try:
        v = float(value)
        if v <= 0:
            return default
        return v
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/diecut/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/diecut/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True) or {}

    length = _float(data.get("length"), 200)
    width = _float(data.get("width"), 150)
    height = _float(data.get("height"), 60)
    thickness = _float(data.get("thickness"), 3)
    internal = bool(data.get("internal", True))
    tab_depth = data.get("tab_depth")
    if tab_depth is not None:
        tab_depth = _float(tab_depth, 20)
    fold_ratio = _float(data.get("fold_ratio", 0.3), 0.3)
    lock_ratio = _float(data.get("lock_ratio", 1.0), 1.0)

    # 新增参数（Step 3）：圆角半径 / 凸起钩比例 / 纸厚补偿 / 图层
    corner_radius = _float(data.get("corner_radius", 0.0), 0.0)
    hook_ratio = _float(data.get("hook_ratio", 0.33), 0.33)
    if hook_ratio < 0.2:
        hook_ratio = 0.2
    elif hook_ratio > 0.5:
        hook_ratio = 0.5
    board_compensation = data.get("board_compensation", None)
    if board_compensation is not None:
        board_compensation = bool(board_compensation)
    layers_raw = data.get("layers")
    if isinstance(layers_raw, list):
        layers = [str(x).upper() for x in layers_raw if str(x).upper() in ("CUT", "CREASE", "HALFCUT", "DIMENSION")]
    else:
        layers = None

    # 简单校验
    if length > 3000 or width > 3000 or height > 3000:
        return jsonify({"error": "尺寸超出合理范围（≤3000mm）"}), 400
    if thickness > 20:
        return jsonify({"error": "纸板厚度超出合理范围（≤20mm）"}), 400

    try:
        geo = build_airplane_box(
            length=length,
            width=width,
            height=height,
            thickness=thickness,
            internal=internal,
            tab_depth=tab_depth,
            fold_ratio=fold_ratio,
            lock_ratio=lock_ratio,
            corner_radius=corner_radius,
            hook_ratio=hook_ratio,
            board_compensation=board_compensation,
            layers=layers,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    effective_internal = geo.board_compensation

    # 生成标题 / 元数据
    if effective_internal:
        title = f"自锁飞机盒刀版 内 {length:.0f}x{width:.0f}x{height:.0f}mm 纸厚{thickness:.1f}mm"
        outer_l = length + 2 * thickness
        outer_w = width + 2 * thickness
        outer_h = height + thickness
    else:
        title = f"自锁飞机盒刀版 外 {length:.0f}x{width:.0f}x{height:.0f}mm 纸厚{thickness:.1f}mm"
        outer_l, outer_w, outer_h = length, width, height

    svg = geometry_to_svg(geo, title)
    pdf = geometry_to_pdf_bytes(geo, title)
    dxf = geometry_to_dxf_bytes(geo, title)

    fid = uuid.uuid4().hex[:12]
    svg_path = os.path.join(OUTPUT_DIR, f"{fid}.svg")
    pdf_path = os.path.join(OUTPUT_DIR, f"{fid}.pdf")
    dxf_path = os.path.join(OUTPUT_DIR, f"{fid}.dxf")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    with open(pdf_path, "wb") as f:
        f.write(pdf)
    with open(dxf_path, "wb") as f:
        f.write(dxf)

    min_x, min_y, max_x, max_y = geo.bounds
    cut_count = sum(1 for s in geo.segments if s.kind == "cut")
    crease_count = sum(1 for s in geo.segments if s.kind == "crease")

    return jsonify(
        {
            "ok": True,
            "id": fid,
            "title": title,
            "pdf_url": f"/api/diecut/download/{fid}.pdf",
            "dxf_url": f"/api/diecut/download/{fid}.dxf",
            "svg_url": f"/api/diecut/download/{fid}.svg",
            "meta": {
                "input_length": length,
                "input_width": width,
                "input_height": height,
                "thickness": thickness,
                "internal": effective_internal,
                "inner": {"length": geo.length, "width": geo.width, "height": geo.height},
                "outer": {"length": outer_l, "width": outer_w, "height": outer_h},
                "blank": {
                    "width_mm": max_x - min_x,
                    "height_mm": max_y - min_y,
                    "panel_width_mm": geo.length,
                    "wall_height_mm": geo.wall_height,
                    "bottom_height_mm": geo.bottom_height,
                    "lid_height_mm": geo.lid_height,
                    "tab_depth_mm": geo.tab_depth,
                    "wing_width_mm": geo.wing_width,
                    "back_flap_width_mm": geo.back_flap_width,
                    "fold_seg_mm": geo.fold_seg,
                    "lock_width_mm": geo.lock_width,
                    "side_inner_mm": geo.side_inner,
                    "side_outer_mm": geo.side_outer,
                },
                "segments": {"cut": cut_count, "crease": crease_count},
                "parameters": {
                    "corner_radius_mm": geo.corner_radius,
                    "hook_ratio": geo.hook_ratio,
                    "hook_height_mm": geo.width * geo.hook_ratio,
                    "board_compensation": geo.board_compensation,
                    "layers": geo.layers,
                },
            },
        }
    )


@app.route("/api/diecut/download/<path:filename>")
def download(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    print("飞机盒刀版生成器: http://127.0.0.1:8899")
    app.run(host="127.0.0.1", port=8899, debug=False)
