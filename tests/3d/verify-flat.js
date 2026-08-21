// 展开态位置验证（用户核心要求）：rotation=0 时，每个面板 mesh 的 3D 世界范围
// 必须精确等于刀线图（diecut_engine）的网区域。这是"张开图 == 原刀线图"的证明。
// 几何数据直接复用 API 返回的 geometry（tests/3d/_geo.json，由 diecut_engine 生成），
// 3D 面板坐标从 geometry.panels 动态读取，不硬编码。
'use strict';
const THREE = require('three');
global.THREE = THREE;
global.document = { createElement: () => ({ getContext: () => ({}) }) };
global.window = {};
const fs = require('fs');
const { buildHierarchy } = require('../../static/diecut-3d.js');

const geo = JSON.parse(fs.readFileSync(__dirname + '/_geo.json', 'utf8'));
const { root, panels } = buildHierarchy(geo, {});
root.updateMatrixWorld(true);

// 期望网区域（来自 diecut_engine 生成的面板 bounds，内 300×200×60 纸厚 1.5）
const expect = {
  bottom:      [-1.5, 60, 313.5, 260],
  front_wall:  [0, 0, 312, 60],
  back_wall:   [0, 260, 312, 320],
  lid:         [4.5, 320, 307.5, 520],
  tuck:        [0, 520, 312, 580],
  lock_left:   [-58.5, 0, 0, 60],
  lock_right:  [312, 0, 370.5, 60],
  back_wing_left:  [-58.5, 260, 0, 320],
  back_wing_right: [312, 260, 370.5, 320],
  lid_wing_left:   [-54, 320, 4.5, 520],
  lid_wing_right:  [307.5, 320, 366, 520],
  tuck_ear_left:   [-58.5, 520, 0, 580],
  tuck_ear_right:  [312, 520, 370.5, 580],
  left_wall:   [-61.5, 60, -1.5, 262],
  right_wall:  [313.5, 60, 373.5, 262],
  left_gap:    [-66, 60, -61.5, 260],
  right_gap:   [373.5, 60, 378, 260],
  left_insert: [-127.5, 60, -66, 260],
  right_insert: [378, 60, 439.5, 260],
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
