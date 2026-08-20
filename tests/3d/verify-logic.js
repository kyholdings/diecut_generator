// 逻辑验证：检查每个 3D 面板的 tex 变换映射到的网坐标区域，是否与刀线图（diecut_engine）一致。
// 用户要求：从脚本逻辑关系上验证张开图 == 原刀线图。
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
const { root, hinges, panels } = buildHierarchy(geo, meta);

function netRegion(panel) {
  const lr = panel.localRect;       // mesh 局部坐标范围
  const o = panel.tex.origin;       // 锚点（网坐标）
  return [o[0] + lr[0], o[1] + lr[1], o[0] + lr[2], o[1] + lr[3]];
}

// 预期网区域（从刀线图推导，L=200 y0=0 y1=63 y2=213 y3=276 y4=426 y5=486）
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
  const act = netRegion(p);
  const ok = Math.abs(act[0] - exp[0]) < 0.5 && Math.abs(act[1] - exp[1]) < 0.5 &&
             Math.abs(act[2] - exp[2]) < 0.5 && Math.abs(act[3] - exp[3]) < 0.5;
  ok ? pass++ : fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${p.id.padEnd(15)} 网区域=[${act.map(v => v.toFixed(0)).join(',')}]  期望=[${exp.join(',')}]`);
});
console.log(`\n===== 网区域一致性: ${pass}/${pass + fail} =====`);
process.exit(fail === 0 ? 0 : 1);
