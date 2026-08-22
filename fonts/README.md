# fonts/ — 打包进镜像的中文字体目录

diecut 引擎 `diecut_engine.py` 会**优先扫描本目录**，注册到 reportlab 并内嵌进导出的 PDF，
使标题中文在**任何阅读器**（含 PDF.js / Firefox）都能正常显示，而不是方框。

## 丢一个中文字体文件进来即可（只需一个）

| 要求 | 说明 |
|------|------|
| 格式 | **`.ttf`（单个，最佳）或 `.ttc`（字体集合，取 subfont 0）** |
| 轮廓 | 必须是 **TrueType / glyf** 轮廓（reportlab 只支持这种） |
| 不要 | **`.otf`（CFF 轮廓）** —— reportlab 无法内嵌，Fandol / Noto CJK 官方 .otf 都是这种，会静默跳过 |

### 推荐字体（免费可商用）
- `WenQuanYi Zen Hei` → 文件名 `wqy-zenhei.ttc`（Debian 包 `fonts-wqy-zenhei`）
- `Noto Sans SC`（Google Fonts 下载的 **TrueType** 版，非 CJK .otf）→ `NotoSansSC-Regular.ttf`

### 已确认可用（云端实测）
- ✅ `wqy-zenhei.ttc` 通过 reportlab `TTFont(..., subfontIndex=0)` 可内嵌
- ❌ Fandol Song / Fandol Fang（easytodo 曾装的）是 CFF，**不可用**
- ❌ 微软雅黑 `msyh.ttc`（TrueType 集合）报告渲染易出方框，已弃用

## 生效步骤（无需改代码）
1. 把字体文件放到本目录（如 `diecut_generator/fonts/wqy-zenhei.ttc`）
2. 本地：重启 8899 进程（`diecut_engine.py` 只 import 一次）
3. 云端：本地 rsync 到 `/opt/diecut/` + `docker compose rm -fs diecut && docker compose up -d`
   （字体经 Dockerfile `COPY . .` 自动打进镜像，无需改 Dockerfile）

`.dockerignore` 未排除 `fonts/`，会正常打包。
