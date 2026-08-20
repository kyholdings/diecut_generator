/* =====================================================================
 * diecut-3d.js — 自锁飞机盒刀版 3D 折叠预览
 *
 * 核心思路（正向运动学，借鉴 dieline-fold）：
 *   - 每个面板的 mesh 直接用"刀版网坐标"几何（netRect），展开态天然
 *     精确等于原始刀线图，杜绝方向/镜像/纹理错位。
 *   - 铰链组 position = 折线的网坐标锚点；mesh 局部 = 网坐标 - 锚点。
 *   - 折叠 = 铰链绕局部轴（水平折线绕 x、竖直折线绕 y）旋转，子面板
 *     继承父面板旋转。
 *   - 纹理 = 真实刀线（CUT 实线 / CREASE 虚线）绘制到面板局部画布。
 *
 * API: window.Diecut3D = { mount, update, setProgress, toggleFold, play,
 *                          dispose, getProgress, setCamera, hideGrid, setSolid }
 * ===================================================================== */
(function () {
  'use strict';

  var HALF = Math.PI / 2;

  // ---------- 折叠顺序（0..1 进度） ----------
  // 真实飞机盒折叠次序：
  //   1. 前后壁折 90°（盖面+插舌随竖）→ 2. 腰部两翼（锁扣翼+后壁翼）折 90°
  //   3. 侧壁内段立起 + 外段折入（包裹腰部两翼）
  //   4. 盒盖带插舌折 90° 盖住 → 5. 盖翼折 90° 插入两侧
  //   6. 插舌折 90° 与前壁平行 → 7. 耳翼折 90° 插入盒底夹缝
  var STAGES = {
    frontBack: [0.00, 0.18],   // 前后壁折起（盖面+插舌随竖）
    waistWings: [0.18, 0.36],  // 腰部两翼（锁扣翼+后壁翼）折入
    sides: [0.36, 0.52],       // 侧壁内段立起
    outer: [0.52, 0.68],       // 外段折入包裹腰部两翼
    lid: [0.70, 0.82],         // 盒盖+插舌折起盖住
    lidWings: [0.84, 0.92],    // 盖翼折入两侧
    tuck: [0.92, 0.97],        // 插舌折下与前壁平行
    tuckEars: [0.96, 1.00],    // 耳翼折入盒底夹缝
  };

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function ease(x) { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); }

  // 面板纸板色（轻微色调差异便于区分结构）
  var FILL = {
    base: '#f2ead6',
    wall: '#efe5cf',
    side: '#eae2cb',
    wing: '#efe7d0',
    outer: '#e6ddc6',
    lid: '#f4ecda',
    tuck: '#f0e6cf',
  };

  // =====================================================================
  // 构建 3D 层级（纯 three，可离线测试）
  //
  // 坐标系：3D X=网x, Y=网y, Z=0（展开态）。root 帧 = 网坐标。
  // 每个面板：anchor 为折线锚点（网坐标），mesh 局部 = 网坐标 - anchor。
  // 铰链绕局部轴旋转：水平折线（沿网 x）→ axis 'x'；竖直折线（沿网 y）→ 'y'。
  // =====================================================================
  function buildHierarchy(geometry, meta) {
    var g = geometry, m = meta || {};
    var L = g.dimensions.length;
    var der = g.derived || {};
    var Hw = der.wall_height, Wb = der.bottom_height, lidH = der.lid_height, tab = der.tab_depth;
    var wing = der.wing_width, sideInner = der.side_inner, sideOuter = der.side_outer;
    var blank = m.blank || {};
    var back = blank.back_flap_width_mm || wing;
    var lock = blank.lock_width_mm || wing;
    var lidSlant = Math.min(wing * 0.3, 0.15 * L);
    var tabEarSlant = Math.min(12.0, tab * 0.2);
    var hookD = Math.max(8, g.dimensions.height * 0.15);   // 大侧壁外段末端凸起钩深度
    var outerLen = sideOuter + hookD;                       // 外段面板含钩的实际净长
    var sideTotal = sideInner + sideOuter;                  // 大侧壁总宽（不含钩）

    var y0 = 0, y1 = Hw, y2 = Hw + Wb, y3 = Hw + Wb + Hw, y4 = y3 + lidH, y5 = y4 + tab;

    var root = new THREE.Group();
    var hinges = [];
    var panels = [];
    var hingesById = {};

    // 面板定义：id / parent / anchor(网坐标折线锚点) / netRect(网区域) / axis / to / fill / shape(可选梯形)
    var DEFS = [
      { id: 'bottom', parent: 'root', anchor: [0, y1], net: [0, y1, L, y2], fill: FILL.base },
      { id: 'front_wall', parent: 'bottom', anchor: [0, y1], net: [0, y0, L, y1], axis: 'x', to: -HALF, range: STAGES.frontBack, fill: FILL.wall },
      { id: 'back_wall', parent: 'bottom', anchor: [0, y2], net: [0, y2, L, y3], axis: 'x', to: HALF, range: STAGES.frontBack, fill: FILL.wall },
      { id: 'left_wall', parent: 'bottom', anchor: [0, y1], net: [-sideInner, y1, 0, y2], axis: 'y', to: HALF, range: STAGES.sides, fill: FILL.side },
      { id: 'right_wall', parent: 'bottom', anchor: [L, y1], net: [L, y1, L + sideInner, y2], axis: 'y', to: -HALF, range: STAGES.sides, fill: FILL.side },
      { id: 'left_outer', parent: 'left_wall', anchor: [-sideInner, y1], net: [-sideTotal - hookD, y1, -sideInner, y2], axis: 'y', to: Math.PI, range: STAGES.outer, fill: FILL.outer },
      { id: 'right_outer', parent: 'right_wall', anchor: [L + sideInner, y1], net: [L + sideInner, y1, L + sideTotal + hookD, y2], axis: 'y', to: -Math.PI, range: STAGES.outer, fill: FILL.outer },
      { id: 'lid', parent: 'back_wall', anchor: [0, y3], net: [0, y3, L, y4], axis: 'x', to: HALF, range: STAGES.lid, fill: FILL.lid },
      { id: 'tuck', parent: 'lid', anchor: [0, y4], net: [0, y4, L, y5], axis: 'x', to: HALF, range: STAGES.tuck, fill: FILL.tuck },
      { id: 'lock_left', parent: 'front_wall', anchor: [0, y1], net: [-lock, y0, 0, y1], axis: 'y', to: HALF, range: STAGES.waistWings, fill: FILL.wing },
      { id: 'lock_right', parent: 'front_wall', anchor: [L, y1], net: [L, y0, L + lock, y1], axis: 'y', to: -HALF, range: STAGES.waistWings, fill: FILL.wing },
      { id: 'back_wing_left', parent: 'back_wall', anchor: [0, y2], net: [-back, y2, 0, y3], axis: 'y', to: HALF, range: STAGES.waistWings, fill: FILL.wing },
      { id: 'back_wing_right', parent: 'back_wall', anchor: [L, y2], net: [L, y2, L + back, y3], axis: 'y', to: -HALF, range: STAGES.waistWings, fill: FILL.wing },
      { id: 'lid_wing_left', parent: 'lid', anchor: [0, y3], net: [-wing, y3, 0, y4], axis: 'y', to: HALF, range: STAGES.lidWings, fill: FILL.wing,
        shape: [[0, 0], [0, lidH], [-wing, lidH - lidSlant], [-wing, lidSlant]] },
      { id: 'lid_wing_right', parent: 'lid', anchor: [L, y3], net: [L, y3, L + wing, y4], axis: 'y', to: -HALF, range: STAGES.lidWings, fill: FILL.wing,
        shape: [[0, 0], [0, lidH], [wing, lidH - lidSlant], [wing, lidSlant]] },
      { id: 'tuck_ear_left', parent: 'tuck', anchor: [0, y4], net: [-wing, y4, 0, y5], axis: 'y', to: HALF, range: STAGES.tuckEars, fill: FILL.wing,
        shape: [[0, 0], [0, tab], [-wing, tab - tabEarSlant], [-wing, tabEarSlant]] },
      { id: 'tuck_ear_right', parent: 'tuck', anchor: [L, y4], net: [L, y4, L + wing, y5], axis: 'y', to: -HALF, range: STAGES.tuckEars, fill: FILL.wing,
        shape: [[0, 0], [0, tab], [wing, tab - tabEarSlant], [wing, tabEarSlant]] },
    ];

    function makePanel(def) {
      var ax = def.anchor[0], ay = def.anchor[1];
      var x0 = def.net[0], y0n = def.net[1], x1 = def.net[2], y1n = def.net[3];
      // mesh 局部坐标 = 网坐标 - 锚点
      var lx0 = x0 - ax, lx1 = x1 - ax, ly0 = y0n - ay, ly1 = y1n - ay;
      var localRect = [Math.min(lx0, lx1), Math.min(ly0, ly1), Math.max(lx0, lx1), Math.max(ly0, ly1)];

      var parent = def.parent === 'root' ? root : hingesById[def.parent].group;
      var hinge = new THREE.Group();
      // 铰链锚点相对父面板 mesh 原点：父帧坐标 = 网坐标 - 父锚点。
      // 由于父 hinge 组就在父锚点（网坐标），子 hinge 位置 = 网坐标差。
      // 父面板无缩放，因此子 hinge 在父帧 = 本面板锚点 - 父面板锚点。
      var parentDef = def.parent === 'root' ? null : DEFS.find(function (d) { return d.id === def.parent; });
      if (parentDef) {
        hinge.position.set(ax - parentDef.anchor[0], ay - parentDef.anchor[1], 0);
      } else {
        hinge.position.set(ax, ay, 0);
      }
      parent.add(hinge);

      var mesh;
      if (def.shape) {
        // 梯形翼：ShapeGeometry，顶点为局部坐标（= 网坐标 - 锚点）
        var shp = new THREE.Shape();
        shp.moveTo(def.shape[0][0], def.shape[0][1]);
        for (var s = 1; s < def.shape.length; s++) shp.lineTo(def.shape[s][0], def.shape[s][1]);
        shp.closePath();
        mesh = new THREE.Mesh(new THREE.ShapeGeometry(shp, 24), null);
      } else {
        var w = x1 - x0, h = y1n - y0n;
        var geo = new THREE.PlaneGeometry(w, h);
        geo.translate((x0 + x1) / 2 - ax, (y0n + y1n) / 2 - ay, 0);
        mesh = new THREE.Mesh(geo, null);
      }
      hinge.add(mesh);

      var rec = {
        id: def.id, group: hinge, mesh: mesh, axis: def.axis, from: 0, to: def.to || 0,
        range: def.range || [0, 1], localRect: localRect, fill: def.fill,
        size: [x1 - x0, y1n - y0n],
        tex: { origin: [ax, ay], xAxis: [1, 0], yAxis: [0, 1], size: [x1 - x0, y1n - y0n] },
      };
      hinges.push(rec);
      hingesById[def.id] = rec;
      panels.push(rec);
      return rec;
    }

    DEFS.forEach(makePanel);

    return { root: root, hinges: hinges, panels: panels, dims: { L: L, Wb: Wb, Hw: Hw, lidH: lidH, tab: tab, wing: wing, sideInner: sideInner, sideOuter: sideOuter, outerLen: outerLen, back: back, lock: lock, y1: y1, y5: y5 } };
  }

  // =====================================================================
  // 把刀版网坐标 segment 变换到面板局部坐标并绘制纹理
  // =====================================================================
  function netToLocal(nx, ny, tex) {
    var dx = nx - tex.origin[0], dy = ny - tex.origin[1];
    return [dx * tex.xAxis[0] + dy * tex.xAxis[1], dx * tex.yAxis[0] + dy * tex.yAxis[1]];
  }

  function drawPanelTexture(panel, segments, scale) {
    var lr = panel.localRect;   // [minX, minY, maxX, maxY]
    var rw = lr[2] - lr[0], rh = lr[3] - lr[1];
    var px = Math.max(4, Math.round(rw * scale));
    var py = Math.max(4, Math.round(rh * scale));
    var canvas = document.createElement('canvas');
    canvas.width = px;
    canvas.height = py;
    var ctx = canvas.getContext('2d');

    // 面板形状填充（矩形整幅 / 梯形按顶点），其余透明
    ctx.beginPath();
    if (panel.shape) {
      panel.shape.forEach(function (p, i) {
        var sx = (p[0] - lr[0]) * scale, sy = py - (p[1] - lr[1]) * scale;
        if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
    } else {
      ctx.rect(0, 0, px, py);
    }
    ctx.fillStyle = panel.fill;
    ctx.fill();

    // 刀线：CUT 实线 / CREASE 虚线（含 HALFCUT 点线）
    var lwCut = Math.max(1, 2.2 * scale / 1.5);
    var lwCrease = Math.max(1, 2.0 * scale / 1.5);
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      var kind = seg.kind;
      if (kind !== 'cut' && kind !== 'crease' && kind !== 'halfcut') continue;
      var pts = [];
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (var j = 0; j < seg.points.length; j++) {
        var lp = netToLocal(seg.points[j][0], seg.points[j][1], panel.tex);
        pts.push(lp);
        if (lp[0] < minX) minX = lp[0];
        if (lp[1] < minY) minY = lp[1];
        if (lp[0] > maxX) maxX = lp[0];
        if (lp[1] > maxY) maxY = lp[1];
      }
      // 与面板局部范围相交才绘制
      if (maxX < lr[0] - 0.5 || minX > lr[2] + 0.5 || maxY < lr[1] - 0.5 || minY > lr[3] + 0.5) continue;
      ctx.save();
      ctx.strokeStyle = kind === 'cut' ? '#1f2937' : kind === 'crease' ? '#d6364f' : '#1d4ed8';
      ctx.lineWidth = kind === 'cut' ? lwCut : kind === 'crease' ? lwCrease : Math.max(1, lwCrease * 0.7);
      ctx.setLineDash(kind === 'cut' ? [] : kind === 'crease' ? [7 * scale / 1.5, 5 * scale / 1.5] : [2 * scale / 1.5, 4 * scale / 1.5]);
      ctx.beginPath();
      for (var k = 0; k < pts.length; k++) {
        var sx2 = (pts[k][0] - lr[0]) * scale, sy2 = py - (pts[k][1] - lr[1]) * scale;
        if (k === 0) ctx.moveTo(sx2, sy2); else ctx.lineTo(sx2, sy2);
      }
      ctx.stroke();
      ctx.restore();
    }
    return canvas;
  }

  // =====================================================================
  // 渲染器 + 交互
  // =====================================================================
  var scene, camera, renderer, netRoot;
  var hinges = [];
  var segments = [];
  var texScale = 1.5;
  var foldProgress = 0;
  var foldAnim = null;
  var autoRotate = true;
  var dragging = false;
  var lastX = 0, lastY = 0;
  var radius = 380, theta = 0.9, phi = 0.85;
  var target = { x: 0, y: 30, z: 10 };
  var cameraTarget = { x: 0, y: 30, z: 10 };
  var lastGeometry = null, lastMeta = null;
  var solidMode = false;

  function materialFor(panel, canvas) {
    if (solidMode) {
      var hash = 0;
      for (var i = 0; i < panel.id.length; i++) hash = (hash * 31 + panel.id.charCodeAt(i)) >>> 0;
      var hue = (hash % 360) / 360;
      return new THREE.MeshStandardMaterial({
        color: new THREE.Color().setHSL(hue, 0.55, 0.72),
        roughness: 0.85,
        side: THREE.DoubleSide,
      });
    }
    var tex = new THREE.CanvasTexture(canvas);
    tex.anisotropy = 4;
    return new THREE.MeshStandardMaterial({
      map: tex,
      roughness: 0.82,
      metalness: 0.03,
      side: THREE.DoubleSide,
    });
  }

  function disposeObject(obj) {
    obj.traverse(function (node) {
      if (node.geometry) node.geometry.dispose();
      if (node.material) {
        if (node.material.map) node.material.map.dispose();
        node.material.dispose();
      }
    });
  }

  function build(geometry, meta) {
    var h = buildHierarchy(geometry, meta);
    hinges = h.hinges;
    segments = geometry.segments || [];

    var maxDim = h.dims.y5 + 2 * (h.dims.Hw);
    texScale = clamp(1500 / maxDim, 1.0, 3.0);

    h.panels.forEach(function (panel) {
      if (!panel.mesh) return;
      var canvas = drawPanelTexture(panel, segments, texScale);
      panel.mesh.material = materialFor(panel, canvas);
      panel.texture = panel.mesh.material.map;
      panel.mesh.userData.label = panel.id;
    });

    netRoot = new THREE.Group();
    netRoot.add(h.root);
    var box = new THREE.Box3().setFromObject(netRoot);
    var center = box.getCenter(new THREE.Vector3());
    var size = box.getSize(new THREE.Vector3());
    netRoot.position.set(-center.x, -center.y, 0);

    // 相机目标 = 折叠后盒中心（网坐标底面中心）相对平移后的位置
    cameraTarget.x = 0;
    cameraTarget.y = (h.dims.y1 + h.dims.Wb / 2) - center.y;
    cameraTarget.z = h.dims.Hw * 0.42;
    target.x = cameraTarget.x; target.y = cameraTarget.y; target.z = cameraTarget.z;
    radius = Math.max(size.x, size.y) * 0.62 + 80;

    scene.add(netRoot);
    applyProgress(0);
    if (camera) updateCamera();
  }

  function applyProgress(p) {
    foldProgress = p;
    for (var i = 0; i < hinges.length; i++) {
      var hn = hinges[i];
      if (!hn.axis) continue;
      var raw = (p - hn.range[0]) / (hn.range[1] - hn.range[0]);
      var e = ease(raw);
      hn.group.rotation[hn.axis] = hn.from + (hn.to - hn.from) * e;
    }
  }

  function animateTo(target, duration) {
    if (foldAnim) cancelAnimationFrame(foldAnim);
    var start = foldProgress;
    var t0 = performance.now();
    function frame(now) {
      var amt = clamp((now - t0) / duration, 0, 1);
      applyProgress(start + (target - start) * amt);
      if (amt < 1) foldAnim = requestAnimationFrame(frame);
      else foldAnim = null;
    }
    foldAnim = requestAnimationFrame(frame);
  }

  function updateCamera() {
    camera.position.set(
      target.x + radius * Math.sin(phi) * Math.sin(theta),
      target.y + radius * Math.cos(phi),
      target.z + radius * Math.sin(phi) * Math.cos(theta)
    );
    camera.lookAt(target.x, target.y, target.z);
  }

  function mount() {
    var host = document.getElementById('preview-3d');
    if (!host || !window.THREE) return;
    if (renderer) {
      if (!host.contains(renderer.domElement)) host.appendChild(renderer.domElement);
      resize();
      return;
    }
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f4f6);
    camera = new THREE.PerspectiveCamera(38, 1, 1, 5000);
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa7b8, 1.5));
    var key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(300, 420, 280);
    scene.add(key);
    var fill = new THREE.DirectionalLight(0x8fb3ff, 0.35);
    fill.position.set(-260, 120, -220);
    scene.add(fill);

    var grid = new THREE.GridHelper(700, 24, 0xc3cdd9, 0xdfe4ea);
    grid.position.y = -0.2;
    scene.add(grid);

    function onDown(e) {
      dragging = true;
      lastX = e.clientX; lastY = e.clientY;
      host.setPointerCapture(e.pointerId);
    }
    function onMove(e) {
      if (!dragging) return;
      var dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      theta -= dx * 0.007;
      phi = clamp(phi - dy * 0.007, 0.15, Math.PI - 0.15);
      autoRotate = false;
      updateCamera();
    }
    function onUp() { dragging = false; }
    function onWheel(e) {
      e.preventDefault();
      radius = clamp(radius + e.deltaY * 0.4, 100, 1400);
      updateCamera();
    }
    host.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    host.addEventListener('wheel', onWheel, { passive: false });
    window.addEventListener('resize', resize);
    updateCamera();

    function render() {
      requestAnimationFrame(render);
      if (autoRotate && !dragging) {
        theta += 0.0028;
        updateCamera();
      }
      renderer.render(scene, camera);
    }
    render();
  }

  function resize() {
    var host = document.getElementById('preview-3d');
    if (!host || !renderer) return;
    var w = Math.max(host.clientWidth, 320);
    var h = Math.max(host.clientHeight, 360);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  // =====================================================================
  // 对外 API
  // =====================================================================
  var Diecut3D = {
    mount: mount,
    update: function (geometry, meta) {
      if (!geometry || !geometry.dimensions) return;
      lastGeometry = geometry;
      lastMeta = meta;
      mount();
      if (scene && netRoot) {
        scene.remove(netRoot);
        disposeObject(netRoot);
        netRoot = null;
      }
      build(geometry, meta);
    },
    setProgress: function (p) {
      if (foldAnim) cancelAnimationFrame(foldAnim);
      foldAnim = null;
      applyProgress(p);
    },
    toggleFold: function () {
      if (netRoot) animateTo(foldProgress < 0.5 ? 1 : 0, 1200);
      return foldProgress >= 0.5;
    },
    play: function (toClose) {
      animateTo(toClose === undefined ? (foldProgress < 0.5 ? 1 : 0) : toClose, 1400);
    },
    dispose: function () {
      if (scene && netRoot) {
        scene.remove(netRoot);
        disposeObject(netRoot);
        netRoot = null;
      }
    },
    getProgress: function () { return foldProgress; },
    setCamera: function (horizDeg, vertRad, dist) {
      theta = horizDeg === undefined ? theta : (horizDeg * Math.PI / 180);
      if (vertRad !== undefined) phi = clamp(vertRad, 0.15, Math.PI - 0.15);
      if (dist !== undefined) radius = clamp(dist, 100, 1400);
      if (camera) updateCamera();
    },
    hideGrid: function () {
      if (scene) scene.children.forEach(function (c) { if (c.isGridHelper) scene.remove(c); });
    },
    setSolid: function (on) {
      solidMode = !!on;
      if (scene && netRoot) {
        scene.remove(netRoot);
        disposeObject(netRoot);
        netRoot = null;
        if (lastGeometry) build(lastGeometry, lastMeta || {});
      }
    },
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { buildHierarchy: buildHierarchy, netToLocal: netToLocal, drawPanelTexture: drawPanelTexture, STAGES: STAGES };
  }
  if (typeof window !== 'undefined') window.Diecut3D = Diecut3D;
}());
