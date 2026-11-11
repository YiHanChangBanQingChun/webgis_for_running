# GitHub Pages 展示版

发布分支：`codex/github-pages-demo`。站点：<https://yihanchangbanqingchun.github.io/webgis_for_running/>。

## 数据范围

- 本地 SQLite 中 **2026-09-01 至 2026-09-14** 连续两周全部 15 场活动，包含有记录的每一种活动，不把无记录日标成已确认休息。
- **2026-11-01 佛山半马**与 **2026-11-08 郴州半马**，来自原始 COROS FIT；显示设备距离和设备用时。
- 广州建筑原有 9,531 栋中，保留距 `(113.34, 23.14)` 最近的 1,907 栋（约 20%），仅保留几何、名称、高度和 OSM ID。此比例按建筑数量计算，建筑几何与高度不作生成式修改。
- 不发布 SQLite、原始 FIT、全量归档、来源路径、训练日记、个人健康快照与个人阈值。

首页默认 2026 年 9 月；训练分析与地图探索默认公开两周，可切换全部公开活动。页面明确说明统计只涉及选集，未公开日期不等于休息。只有连续公开窗口具备足够天数时才显示滚动负荷；当前 28 日基线与负荷比留空。负荷是按时长、平均心率计算的相对指标，不是 COROS 官方负荷。

## 代码与运行方式

复用 `frontend/src` 的原有 Vue 组件。常规 `npm run dev` 和 `npm run build` 仍通过后端 API；`pages` 构建模式由 `dataClient.ts` 读取 `frontend/public-demo` 的公开数据，并在浏览器进行筛选、分页、月度统计、区间统计和网格查询。单场洞察预计算成静态 JSON。

三维页默认独立加载整个广州片区，切换跑步不卸载建筑；“定位广州”和“定位当前路线”可以分别定位两类数据。仍可切换到轨迹附近的建筑筛选模式。

```bash
cd frontend
npm ci
npm run test:static
npm run test:region
npm run build:pages
npx vite preview --outDir ../pages --base /webgis_for_running/ --port 4173
```

构建产物位于仓库根目录 `pages/`，已加入 Git 忽略规则，每次 Pages 构建自动清空重建。GitHub Actions 只上传这个目录，不上传开发数据目录；部署不需要后端、SQLite 或 COROS 认证。

## 重新生成公开数据

原始半马 FIT 以 COROS 活动 ID 命名，保存在被忽略的 `.runtime/pages-races/`：

- `481437585388896557.fit`
- `481600047625044669.fit`

```bash
.venv/bin/python scripts/export_pages_data.py
```

脚本只读打开兄弟目录的训练库，定向读取两周活动及其轨迹；验证区间内数据库活动完整覆盖后，生成 `frontend/public-demo/`。不会修改训练库或全量派生数据。需要调整公开范围时，应同时更新导出规则、清单和验证中的明确活动范围，再检查公开产物。

## 发布

仓库 Settings → Pages 的 Source 使用 **GitHub Actions**。推送到 `codex/github-pages-demo` 会先运行静态数据测试、三维几何测试和生产构建，再部署 Pages。若以后改用其他发布分支，需要同时调整 `pages.yml` 的触发分支与仓库的环境规则。

默认路径为 `/webgis_for_running/`。Vite 资源、Cesium Workers 和数据文件均使用这一子路径。二维 OSM 底图及 Google Fonts 仍需外部网络；三维默认纯色地球，建筑和轨迹可独立工作。
