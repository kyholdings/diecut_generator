// 展开态位置验证（用户核心要求）：rotation=0 时，每个面板 mesh 的 3D 世界范围
// 必须精确等于刀线图（diecut_engine）的网区域。这是"张开图 == 原刀线图"的证明。
'use strict';
const THREE = require('three');
global.THREE = THREE;
global.document = { createElement: () => ({ getContext: () => ({}) }) };
global.window = {};
const { buildHierarchy } = require('../../static/diecut-3d.js');

const geo = {
  dimensions: { length: 200, width: 150, height: 60, thickness: 3 },
  derived: { wall_height: 63, bottom_height: 150, lid_height: 150, tab_depth: 60, wing_width: 57, side_inner: 63, side_outer: 57 },
  segments: [],
};
const meta = { blank: { back_flap_width_mm: 57, lock_width_mm: 57, fold_seg_mm: 17 }, parameters: { corner_radius_mm: 0 } };
const { root, panels } = buildHierarchy(geo, meta);
root.updateMatrixWorld(true);

// 期望网区域（从刀线图推导）
const expect = {
  bottom:      [0, 63, 200, 213],
  front_wall:  [0, 0, 200, 63],
  back_wall:   [0, 213, 200, 276],
  lid:         [0, 276, 200, 426],
  tuck:        [0, 426, 200, 486],
  lock_left:   [-57, 0, 0, 63],
  lock_right:  [200, 0, 257, 63],
  back_wing_left:  [-57, 213, 0, 276],
  back_wing_right: [200, 213, 257, 276],
  lid_wing_left:   [-57, 276, 0, 426],
  lid_wing_right:  [200, 276, 257, 426],
  tuck_ear_left:   [-57, 426, 0, 486],
  tuck_ear_right:  [200, 426, 257, 486],
  left_wall:   [-63, 63, 0, 213],
  right_wall:  [200, 63, 263, 213],
  left_outer:  [-129, 63, -63, 213],
  right_outer: [263, 63, 329, 213],
};

let pass = 0, fail = 0;
panels.forEach(p => {
  const exp = expect[p.id];
  if (!exp) return;
  // mesh 世界 bbox：局部 localRect 4 角 → 世界
  const lr = p.localRect;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const corners = [[lr[0], lr[1]], [lr[2], lr[1]], [lr[2], lr[3]], [lr[0], lr[3]]];
  corners.forEach(([cx, cy]) => {
    const v = new THREE.Vector3(cx, cy, 0);
    p.mesh.localToWorld(v);
    minX = Math.min(minX, v.x); maxX = Math.max(maxX, v.x);
    minY = Math.min(minY, v.y); maxY = Math.max(maxY, v.y);
  });
  const ok = Math.abs(minX - exp[0]) < 0.01 && Math.abs(minY - exp[1]) < 0.01 &&
             Math.abs(maxX - exp[2]) < 0.01 && Math.abs(maxY - exp[3]) < 0.01;
  ok ? pass++ : fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${p.id.padEnd(15)} 展开态3D=[${minX.toFixed(0)},${minY.toFixed(0)},${maxX.toFixed(0)},${maxY.toFixed(0)}]  期望=[${exp.join(',')}]`);
});
console.log(`\n===== 张开图与刀线图一致性: ${pass}/${pass + fail} =====`);
process.exit(fail === 0 ? 0 : 1);
