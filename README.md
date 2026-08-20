# 自锁飞机盒刀版生成器（Die-cut Dieline Generator）

一个输入盒子的 **长 L × 宽 W × 高 H × 纸板厚度 t**，自动生成 **自锁式飞机盒（Self-locking Mailer Box）** 平面展开刀版（dieline）的 Web 工具。

- **PDF**：1:1 毫米制，可直接打印或发给刀模厂
- **DXF**：毫米制，`CUT` 图层为模切线（红），`CREASE` 图层为压痕线（蓝虚线），供 CAD / 刀模软件使用
- **SVG**：网页内实时预览

## 特性

- 三片式自锁结构：插舌 + 锁扣翼互锁，**无需胶水**
- 竖排 5 层面板，按盒子折叠逻辑严格推算各区块尺寸
- 盖翼 / 插舌翼为**等腰梯形**，后壁翼为矩形，横向尺寸统一（= H − t）
- 底面大侧壁分两段（内段成盒壁 + 外段插入盒底），末端凸起钩
- 绝对左右对称，所有线条闭合
- 纯 Python 生成 PDF / DXF，**不需要 LibreOffice / CAD**

## 依赖安装

```bash
pip install -r requirements.txt
```

依赖：`flask`、`reportlab`、`ezdxf`

## 启动

```bash
python app.py
```

浏览器打开 <http://127.0.0.1:8899>。

## 使用方法

1. 输入盒子的长 L、宽 W、高 H、纸板厚度 t（mm）
2. 选择尺寸类型：内尺寸 / 外尺寸
3. （可选）高级参数：插舌深度、两折翼插入段比例、锁扣翼比例
4. 点击"生成刀版"，实时预览 SVG
5. 下载 PDF / DXF

参数变化会自动防抖刷新预览；服务暂时不可用时，浏览器会使用本地几何引擎按当前参数生成 SVG。最近一次服务器结果也会保存在浏览器本地作为回退缓存。离线模式仅支持 SVG 预览，PDF / DXF 需要恢复服务器连接。

生成成功后可打开 **Three.js 3D 折叠预览**：支持进度滑杆逐帧折叠、自动播放、展开/折叠动画、鼠标拖动旋转、滚轮缩放。每个面板的纹理就是真实刀模线（CUT 实线 / CREASE 虚线），张开图与 2D 刀版逐像素一致；折叠完成后外段折入盒底、插舌垂下插入盒内前壁。3D 视图仅用于结构检查，生产尺寸仍以 SVG / PDF / DXF 为准。

3D 折叠采用正向运动学：面板以折痕为锚点嵌套在 `THREE.Group` 中，子翼继承父面板的局部旋转，算法参考 [Somacharitha/dieline-fold](https://github.com/Somacharitha/dieline-fold)。面板 mesh 直接用刀版网坐标几何，保证张开图精确还原刀线图。验证测试见 `tests/3d/`（张开图一致性 / 网区域 / 折叠审计 / 插入盒底，全部 PASS 才正确）。

## API

### `POST /api/diecut/generate`

请求 JSON：

```json
{
  "length": 200,
  "width": 150,
  "height": 60,
  "thickness": 3,
  "internal": true,
  "tab_depth": 60,
  "fold_ratio": 0.3,
  "lock_ratio": 1.0
}
```

返回：

```json
{
  "ok": true,
  "id": "abc123",
  "title": "自锁飞机盒刀版 内 200x150x60mm 纸厚3.0mm",
  "pdf_url": "/api/diecut/download/abc123.pdf",
  "dxf_url": "/api/diecut/download/abc123.dxf",
  "svg_url": "/api/diecut/download/abc123.svg",
  "meta": { "inner": {...}, "outer": {...}, "blank": {...}, "segments": {...} }
}
```

### `GET /api/diecut/download/<filename>`

下载生成的文件（pdf / dxf / svg）。

### `GET /api/diecut/schema`

返回请求 JSON Schema，供客户端或外部工具校验参数。

### 拼版估算

在生成请求中传入 `sheet` 后，返回 `meta.nesting`：

```json
{
      "sheet": { "width": 1200, "height": 800, "margin": 10, "gap": 5 }
}
```

估算支持直放和横放两种方向，当前使用刀版包围盒进行基础排样，不替代轮廓级嵌套优化。

## 刀版结构

```text
        ┌──────────────────────────────┐
  翼 ───┤ 插舌 H（等腰梯形翼）         ├─── 翼
        ├──────────────────────────────┤
  翼 ───┤ 盖子顶面 W（等腰梯形盖翼）   ├─── 翼
        ├──────────────────────────────┤
  翼 ───┤ 后壁 H+t（矩形翼）           ├─── 翼
        ├──────────────────────────────┤
 侧壁 ─┤ 底面 W（大侧壁 内段+外段）   ├─── 侧壁
        ├──────────────────────────────┤
  翼 ───┤ 前壁 H+t（锁扣翼）           ├─── 翼
        └──────────────────────────────┘
```

- 列宽 = 盒长 L
- 底面 / 盖子顶面高度 = 盒宽 W
- 前壁 / 后壁高度 = 盒高 H + 纸厚 t
- 插舌高度 = 盒高 H
- 底面大侧壁 = 内段 (H+t) + 外段 (H−t)，内部折线，外段末端凸起钩插入盒底
- 盖翼 / 插舌翼 = 等腰梯形；后壁翼 / 前壁锁扣翼 = 矩形；横向尺寸均 = H−t
- 实线 = 模切线，虚线 = 压痕线

## 项目结构

```text
diecut_generator/
├── app.py                 # Flask 后端 + API
├── diecut_engine.py       # 刀版几何计算 / PDF / DXF / SVG 生成
├── static/
│   └── index.html         # Vue 3 + Bootstrap 前端页面
├── requirements.txt
├── README.md
└── start.bat
```

## 许可证

MIT
