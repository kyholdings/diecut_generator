// 折叠后精确审计：输出每个面板中心位置、法线方向，判断盒体组合正确性。
// 坐标系：root 帧 = 刀版网坐标（X=网x, Y=网y, Z 向上）。
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
hinges.forEach(h => { if (h.axis) h.group.rotation[h.axis] = h.to; });
root.updateMatrixWorld(true);

function centerOf(id) {
  const p = panels.find(x => x.id === id);
  const lr = p.localRect;
  const v = new THREE.Vector3((lr[0] + lr[2]) / 2, (lr[1] + lr[3]) / 2, 0);
  p.mesh.localToWorld(v);
  return [v.x, v.y, v.z].map(x => +x.toFixed(1));
}
function normalOf(id) {
  const p = panels.find(x => x.id === id);
  const m = p.mesh.matrixWorld;
  const n = new THREE.Vector3(m.elements[8], m.elements[9], m.elements[10]).normalize();
  return n.toArray().map(x => +x.toFixed(2));
}

console.log('=== 折叠后各面板审计（网坐标 root，L=200 W=150 H=60）===');
const rows = [
  ['bottom', '底面'], ['front_wall', '前壁'], ['back_wall', '后壁'],
  ['left_wall', '左壁'], ['right_wall', '右壁'],
  ['left_outer', '左外段'], ['right_outer', '右外段'],
  ['lid', '盖面'], ['tuck', '插舌'],
  ['lock_left', '左锁扣翼'], ['lock_right', '右锁扣翼'],
  ['back_wing_left', '左后翼'], ['back_wing_right', '右后翼'],
  ['lid_wing_left', '左盖翼'], ['lid_wing_right', '右盖翼'],
  ['tuck_ear_left', '左耳翼'], ['tuck_ear_right', '右耳翼'],
];
rows.forEach(([id, label]) => {
  console.log(`${label.padEnd(6)} 中心[${centerOf(id).join(',')}]  法线[${normalOf(id).join(',')}]`);
});

console.log('\n=== 期望（root=网坐标：底面 y∈[63,213]）===');
console.log('底面  中心≈(100,138,0)   法线(0,0,1)');
console.log('前壁  中心≈(100,63,31.5) 法线(0,±1,0)');
console.log('后壁  中心≈(100,213,31.5)法线(0,∓1,0)');
console.log('左壁  中心≈(0,138,31.5)  法线(±1,0,0)');
console.log('右壁  中心≈(200,138,31.5)法线(∓1,0,0)');
console.log('盖面  中心≈(100,138,63)  法线(0,0,-1)');
console.log('外段/翼 应折入盒内（法线不指向盒外）');
