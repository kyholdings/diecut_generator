// 逻辑验证：检查每个 3D 面板的 tex 变换映射到的网坐标区域，是否与刀线图（diecut_engine）一致。
// 用户要求：从脚本逻辑关系上验证张开图 == 原刀线图。
// 几何数据复用 API 返回的 geometry（tests/3d/_geo.json），3D 坐标从 geometry.panels 动态读取。
'use strict';
const THREE = require('three');
global.THREE = THREE;
global.document = { createElement: () => ({ getContext: () => ({}) }) };
global.window = {};
const fs = require('fs');
const { buildHierarchy } = require('../../static/diecut-3d.js');

const geo = JSON.parse(fs.readFileSync(__dirname + '/_geo.json', 'utf8'));
const { root, hinges, panels } = buildHierarchy(geo, {});

function netRegion(panel) {
  const lr = panel.localRect;       // mesh 局部坐标范围
  const o = panel.tex.origin;       // 锚点（网坐标）
  return [o[0] + lr[0], o[1] + lr[1], o[0] + lr[2], o[1] + lr[3]];
}

// 预期网区域（来自 diecut_engine 生成的面板 bounds，内 300×200×60 纸厚 1.5，side_comp=2）
// 底面高度 = 制造宽 202（盒底与后腰折线 y=262 与侧壁内段顶边/后腰翼底边共线）
// 外段/间隙段相对内段垂直居中：y 上下各缩进 side_comp/2 = 1mm
// 所有两翼沿主面板方向上下各缩 t=1.5：锁扣/后腰/耳翼高 H-2t=57，盖翼高 W-2t=197
// 大侧壁外段始终比内段窄 t：side_outer=58.5，外段 x 从 -126 到 -66
const expect = {
  bottom:      [-1.5, 60, 313.5, 262],
  front_wall:  [0, 0, 312, 60],
  back_wall:   [0, 262, 312, 322],
  lid:         [4.5, 322, 307.5, 522],
  tuck:        [0, 522, 312, 582],
  lock_left:   [-58.5, 1.5, 0, 58.5],
  lock_right:  [312, 1.5, 370.5, 58.5],
  back_wing_left:  [-58.5, 263.5, 0, 320.5],
  back_wing_right: [312, 263.5, 370.5, 320.5],
  lid_wing_left:   [-54, 323.5, 4.5, 520.5],
  lid_wing_right:  [307.5, 323.5, 366, 520.5],
  tuck_ear_left:   [-58.5, 523.5, 0, 580.5],
  tuck_ear_right:  [312, 523.5, 370.5, 580.5],
  left_wall:   [-61.5, 60, -1.5, 262],
  right_wall:  [313.5, 60, 373.5, 262],
  left_gap:    [-66, 61, -61.5, 261],
  right_gap:   [373.5, 61, 378, 261],
  left_insert: [-126, 61, -66, 261],
  right_insert: [378, 61, 438, 261],
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
