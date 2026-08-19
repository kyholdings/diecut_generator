(function () {
  'use strict';

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function format(value) {
    return Number(value.toFixed(3)).toString();
  }

  function arcPoints(cx, cy, radius, start, end, count) {
    const points = [];
    for (let index = 0; index <= count; index += 1) {
      const angle = start + (end - start) * index / count;
      points.push([cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)]);
    }
    return points;
  }

  function roundedCorner(previous, corner, next, radius) {
    if (radius <= 0) return [corner];
    const v1 = [corner[0] - previous[0], corner[1] - previous[1]];
    const v2 = [next[0] - corner[0], next[1] - corner[1]];
    const length1 = Math.hypot(v1[0], v1[1]);
    const length2 = Math.hypot(v2[0], v2[1]);
    if (length1 < 1e-9 || length2 < 1e-9) return [corner];
    const u1 = [v1[0] / length1, v1[1] / length1];
    const u2 = [v2[0] / length2, v2[1] / length2];
    const n1 = [u1[1], -u1[0]];
    const n2 = [u2[1], -u2[0]];
    const determinant = n1[0] * n2[1] - n1[1] * n2[0];
    if (Math.abs(determinant) < 1e-9) return [corner];
    const dx = (radius * n2[1] - radius * n1[1]) / determinant;
    const dy = (n1[0] * radius - n2[0] * radius) / determinant;
    const center = [corner[0] + dx, corner[1] + dy];
    const t1 = (center[0] - corner[0]) * u1[0] + (center[1] - corner[1]) * u1[1];
    const t2 = (center[0] - corner[0]) * u2[0] + (center[1] - corner[1]) * u2[1];
    if (t1 > 0 || t2 < 0) return [corner];
    const p1 = [corner[0] + t1 * u1[0], corner[1] + t1 * u1[1]];
    const p2 = [corner[0] + t2 * u2[0], corner[1] + t2 * u2[1]];
    const a1 = Math.atan2(p1[1] - center[1], p1[0] - center[0]);
    const a2 = Math.atan2(p2[1] - center[1], p2[0] - center[0]);
    const cross = (p1[0] - center[0]) * (p2[1] - center[1]) -
      (p1[1] - center[1]) * (p2[0] - center[0]);
    if (cross > 0) {
      return arcPoints(center[0], center[1], radius, a1, a1 > a2 ? a2 + 2 * Math.PI : a2, 12);
    }
    return arcPoints(center[0], center[1], radius, a1 < a2 ? a1 + 2 * Math.PI : a1, a2, 12);
  }

  function roundedPolyline(points, radius, indices) {
    const result = [];
    points.forEach((point, index) => {
      const last = points.length - 1;
      const replacement = index > 0 && index < last && indices.has(index)
        ? roundedCorner(points[index - 1], point, points[index + 1], radius)
        : [point];
      replacement.forEach((item) => {
        if (!result.length || result[result.length - 1][0] !== item[0] || result[result.length - 1][1] !== item[1]) {
          result.push(item);
        }
      });
    });
    return result;
  }

  function pathData(points) {
    return points.map((point, index) => `${index ? 'L' : 'M'}${format(point[0])} ${format(point[1])}`).join(' ');
  }

  function generate(form) {
    let L = Number(form.length);
    let W = Number(form.width);
    let H = Number(form.height);
    const t = Number(form.thickness);
    if (![L, W, H, t].every((value) => Number.isFinite(value) && value > 0)) {
      throw new Error('长、宽、高、纸厚必须为正数');
    }
    const internal = form.board_compensation == null ? form.internal !== false : Boolean(form.board_compensation);
    if (!internal) {
      L = Math.max(L - 2 * t, 1);
      W = Math.max(W - 2 * t, 1);
      H = Math.max(H - t, 1);
    }
    const Hw = H + t;
    const tab = Math.max(form.tab_depth ? Number(form.tab_depth) : H, 4);
    const wing = Math.max(H - t, 4);
    const back = Math.max(H - t, 4);
    const lock = Math.max((H - t) * Number(form.lock_ratio || 1), 4);
    const sideInner = Hw;
    const sideOuter = Math.max(H - t, 4);
    const sideTotal = sideInner + sideOuter;
    const fold = Math.min(Math.max(6, wing * Number(form.fold_ratio || 0.3)), wing - 2);
    const wingFold = wing - fold;
    const backFold = back - fold;
    const slant = Math.min(wing * 0.3, 0.15 * L);
    const tabSlant = Math.min(0.08 * L, 12);
    const earSlant = Math.min(12, tab * 0.2);
    const earWidth = wing;
    const hookRatio = clamp(Number(form.hook_ratio || 0.33), 0.2, 0.5);
    const hookDepth = Math.max(8, H * 0.15);
    const hookHeight = W * hookRatio;
    const radius = clamp(Number(form.corner_radius || 0), 0, Math.max(0, Math.min(earWidth, L / 2 - 0.5)));
    const y0 = 0;
    const y1 = Hw;
    const y2 = Hw + W;
    const y3 = y2 + Hw;
    const y4 = y3 + W;
    const y5 = y4 + tab;
    const segments = [];
    function add(kind, points, cut) {
      const clean = [];
      points.forEach((point) => {
        if (!clean.length || clean[clean.length - 1][0] !== point[0] || clean[clean.length - 1][1] !== point[1]) clean.push(point);
      });
      if (clean.length >= 2) segments.push({ kind, points: clean, cut: Boolean(cut) });
    }
    function hooks(x, a, b, upward) {
      const center = (a + b) / 2;
      const half = hookHeight / 2;
      return upward
        ? [[x, a], [x, center - half], [x - hookDepth, center - half], [x - hookDepth, center + half], [x, center + half], [x, b]]
        : [[x, a], [x, center + half], [x + hookDepth, center + half], [x + hookDepth, center - half], [x, center - half], [x, b]];
    }
    const left = [[0, y0], [-lock, y0], [-lock, y1], [0, y1], [-sideTotal, y1]];
    left.push(...hooks(-sideTotal, y1, y2, true), [0, y2], [-back, y2], [-back, y3], [0, y3]);
    left.push(...roundedPolyline([[0, y3], [-wing, y3 + slant], [-wing, y4 - slant], [0, y4]], radius, new Set([1, 2])));
    const tuck = roundedPolyline([[0, y4], [-earWidth, y4 + earSlant], [-earWidth, y5 - earSlant], [0, y5], [L, y5], [L + earWidth, y5 - earSlant], [L + earWidth, y4 + earSlant], [L, y4]], radius, new Set([1, 2, 3, 4, 5, 6]));
    const right = roundedPolyline([[L, y4], [L + wing, y4 - slant], [L + wing, y3 + slant], [L, y3]], radius, new Set([1, 2]));
    right.push([L + back, y3], [L + back, y2], [L, y2], [L + sideTotal, y2], ...hooks(L + sideTotal, y2, y1, false), [L, y1], [L + lock, y1], [L + lock, y0], [L, y0]);
    add('cut', [...left, ...tuck, ...right, [0, y0]]);
    [y1, y2, y3, y4].forEach((y) => add('crease', [[0, y], [L, y]], y === y1 || y === y2 || y === y3));
    [[0, y0, 0, y1], [0, y1, 0, y2], [0, y2, 0, y3], [0, y3, 0, y4], [0, y4, 0, y5], [L, y0, L, y1], [L, y1, L, y2], [L, y2, L, y3], [L, y3, L, y4], [L, y4, L, y5], [-wingFold, y3, -wingFold, y4], [L + wingFold, y3, L + wingFold, y4], [-backFold, y2, -backFold, y3], [L + backFold, y2, L + backFold, y3], [-sideInner, y1, -sideInner, y2], [L + sideInner, y1, L + sideInner, y2]].forEach((line) => add('crease', [[line[0], line[1]], [line[2], line[3]]]));
    add('cut', [[-lock, y1], [0, y1]]); add('cut', [[L, y1], [L + lock, y1]]);
    add('cut', [[-back, y2], [0, y2]]); add('cut', [[L, y2], [L + back, y2]]);
    add('cut', [[-back, y3], [0, y3]]); add('cut', [[L, y3], [L + back, y3]]);
    const slotCenter = (y1 + y2) / 2;
    const slotLow = slotCenter - hookHeight / 2;
    const slotHigh = slotCenter + hookHeight / 2;
    const slotCenterX = Math.min(hookDepth, L / 2);
    const halfSlot = Math.min(t / 2, slotCenterX, L / 2 - slotCenterX);
    const x0 = slotCenterX - halfSlot;
    const x1 = slotCenterX + halfSlot;
    [[x0, x1], [L - x1, L - x0]].forEach((range) => add('cut', [[range[0], slotLow], [range[1], slotLow], [range[1], slotHigh], [range[0], slotHigh], [range[0], slotLow]]));
    const layers = Array.isArray(form.layers) ? form.layers : ['CUT', 'CREASE'];
    const bounds = segments.reduce((box, segment) => segment.points.reduce((current, point) => [Math.min(current[0], point[0]), Math.min(current[1], point[1]), Math.max(current[2], point[0]), Math.max(current[3], point[1])], box), [Infinity, Infinity, -Infinity, -Infinity]);
    const pad = 10;
    const viewBox = [bounds[0] - pad, bounds[1] - pad, bounds[2] - bounds[0] + pad * 2, bounds[3] - bounds[1] + pad * 2];
    const cutWidth = 0.25 + t * 0.02;
    const creaseWidth = 0.20 + t * 0.02;
    const parts = [`<svg xmlns="http://www.w3.org/2000/svg" width="${format(viewBox[2])}mm" height="${format(viewBox[3])}mm" viewBox="${viewBox.map(format).join(' ')}">`, '<defs><style>', `.cut{stroke:#000;stroke-width:${format(cutWidth)};fill:none}`, `.crease{stroke:#e02020;stroke-width:${format(creaseWidth)};stroke-dasharray:4 2;fill:none}`, '</style></defs>'];
    const flip = 2 * viewBox[1] + viewBox[3];
    parts.push(`<g transform="translate(0,${format(flip)}) scale(1,-1)">`);
    [['CUT', 'cut'], ['CREASE', 'crease']].forEach(([layer, kind]) => {
      if (!layers.includes(layer)) return;
      parts.push(`<g id="layer-${layer}">`);
      segments.filter((segment) => segment.kind === kind).forEach((segment) => parts.push(`<path class="${kind}" d="${pathData(segment.points)}"/>`));
      parts.push('</g>');
    });
    parts.push('</g></svg>');
    return { svg: parts.join('\n'), geometry: { schema_version: 'offline-1.0', type: 'airplane_box', units: 'mm', bounds, segments, layers } };
  }

  window.DiecutOffline = { generate };
}());
