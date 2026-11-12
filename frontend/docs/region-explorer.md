# 区域探索：城市跑步剧场

把一次跑步的 GPS、时间、配速、心率与广州建筑放到同一个 Cesium 场景中。
本轮在第五个导航“区域探索”中实现，不需要改造 Python / Spring Boot 后端。

## 设想与取舍

| 设想                     | 可视化价值                                   | 所需条件与开销                                                                   | 本轮结果 |
| ------------------------ | -------------------------------------------- | -------------------------------------------------------------------------------- | -------- |
| 三维跑步回放与指标着色   | 看到自己在建筑间如何跑、在哪里变快或变慢     | 现有 GPS、时间、速度、心率已经齐备；中等工作量                                   | 已实现   |
| 沿线建筑探索             | 同一条路线可比较沿线楼高、建筑数量与城市空间 | 利用现有 `height_m`，前端做近似距离筛选即可                                      | 已实现   |
| 相机跟随与俯瞰           | 在局部体验和完整路线之间切换                 | 使用 Cesium Camera，工作量较小                                                   | 已实现   |
| 多年路线叠加、区域点亮   | 观察跑步领地随时间扩展                       | 现有二维网格已具备基础，但一次加载全部历史轨迹成本高；宜先建立时间索引、聚合接口 | 后续方向 |
| 日照、阴影、街道峡谷分析 | 比较跑步时间与城市日照环境                   | 还需要可靠建筑底高、地形、时区和覆盖完整的建筑，当前数据不足以做严谨分析         | 暂缓     |
| 整城 3D Tiles            | 支持更大建筑集合、按视距分级加载             | 需要单独的瓦片转换流程，适合下一阶段学习                                         | 暂缓     |

## 如何操作

1. 启动现有前后端，进入“区域探索”，默认选择最新的一次含 GPS 的正式跑步。
2. 切换“按配速 / 按心率 / 单色发光”。图例使用固定数值，不是个人训练区间。
3. 点击“播放”，选择 10、30 或 60 倍速，或拖动进度条。白点是跑者，细白线是已跑过的部分。
4. 勾选“跟随跑者”进入倾斜跟随视角；“全程俯瞰”恢复自由相机并展示完整路线。
5. 探索距离可切换为 100、250、500 米，只加载这一范围内的建筑。
6. 建筑按原始高度分色。可设置 1–3 倍视觉夸张，统计与点击属性始终使用原值。
7. 默认是无需外部网络的纯色地球；OSM 底图可以按需开启，保留其署名。

## 推荐阅读顺序

| 文件                                       | 学习重点                                                                   |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| `src/features/region/types.ts`             | 数据“长什么样”：接口、单位、图例的约定                                     |
| `src/features/region/geometry.ts`          | 数据“怎样处理”：时间、距离、插值、建筑筛选；不依赖 Vue 和 Cesium，便于单测 |
| `src/features/region/RegionScene.ts`       | 数据“怎样画”：Viewer、DataSource、Entity、PolygonGraphics、Camera          |
| `src/features/region/useRegionExplorer.ts` | “怎样连起来”：请求、ref/computed/watch、播放循环和生命周期                 |
| `src/components/RegionExplorer.vue`        | “怎样交互”：模板、事件绑定、控件布局与组件样式                             |
| `tests/regionGeometry.test.ts`             | 用具体输入输出理解空间筛选和时间插值                                       |

### 一次页面打开的数据流

```text
onMounted 创建 RegionScene / Viewer
  ├─ GET /api/activities?has_gps=true&sport=running&sort=date_desc
  │    └─ 自动选中最新活动 → GET /api/activities/{id}/track
  │         └─ prepareTrack → setRoute → 相机俯瞰
  └─ GET /cesium-data/guangzhou-buildings.geojson
       └─ prepareBuildings

完整轨迹 + 建筑集合 + radius
  └─ filterNearbyBuildings → GeoJsonDataSource → extrudedHeight

requestAnimationFrame → elapsed → sampleTrack → updateRunner
                                           └─ 可选 Camera.lookAt 跟随
```

活动接口按分页读取，兼容原有两个后端。只保留正式跑步，排除 `training_excluded`。
建筑文件在一次页面挂载期间读取一次；切换活动只重新请求对应轨迹并筛选建筑。

### Vue 与 Cesium 为什么拆开

Vue 擅长管理控件状态，Cesium 是直接操作场景对象的库。
`RegionScene` 将命令式 API 集中在一起，Vue 组件不需要知道 `Entity` 怎么创建。
Cesium Viewer 使用普通变量，大型只读数组使用 `shallowRef`，避免不必要的深层代理。

例如更改探索距离时：

```ts
watch(radius, () => {
  void updateCorridor()
})
```

`updateCorridor` 先做空间筛选，再调用 `scene.setBuildings`，模板中的数量统计通过 `computed` 更新。
拖动高度滑块只调整已加载建筑的 `extrudedHeight`，不会重新读取 GeoJSON。

### 时间、距离与指标

- `timestamp` 决定相邻 GPS 点的时间间隔，停顿也保留；缺失、重复或倒退的时间戳按 1 秒/点回退，并显示提示。
- 动画经过的记录时间 = 真实帧间隔 × 播放倍速，不使用“每帧前进一个点”，因此不同刷新率下速度一致。
- 经纬度和累计距离在相邻点之间线性插值；心率、配速取前一采样点，缺失时显示 `—`。
- 速度单位为米/秒，配速单位为秒/千米：`paceSeconds = 1000 / speed`。
- 累计距离减去第一点的偏移；若设备距离缺失或倒退，则用相邻经纬度的球面距离回退。
- 绘图对长轨迹抽样，着色最多约 160 段，颜色取各段起点的采样值；回放、统计与建筑筛选使用完整点列。

### 沿线建筑的空间含义

`geometry.ts` 使用建筑包围盒中心与轨迹线段的距离。
先以轨迹首点为原点，将 WGS84 经纬度近似转为局部米制坐标；再用 1 km 网格查找候选线段，最后计算点到线段的距离。
网格是加速工具，不会抽样轨迹，也不会把“离采样点远、但离两点之间线段近”的建筑漏掉。

这是广州市域的近似可视化筛选，不是多边形轮廓与精确缓冲区的相交分析。
大建筑的中心可能在范围外，建筑边缘却在范围内；跨市、跨日期变更线等场景需要换用正式地理算法。
源数据是部分 OSM 建筑，不覆盖所有建筑。无命中时会提示扩大距离或更换轨迹，不生成虚构建筑。

建筑底高为椭球高 0 米，顶部为 `height_m × heightScale`；路线统一抬高 5 米。
这保留了原始建筑相对高度，但不代表已经与真实地形或设备海拔对齐。
未来加入地形时，应另行处理建筑基底、相对地面高度与贴地路线。
源建筑缺少有效高度时回退 10 米，后续引入新建筑数据时可扩展缺失值标识。

### 错误与资源释放

- 选择活动时会取消上一条轨迹请求，迟到的响应不能覆盖新选择。
- 建筑加载使用版本号；旧的 `GeoJsonDataSource.load` 完成后若已过期，就不会再添加。
- 请求或建筑文件失败时显示中文提示，轨迹和建筑分别处理错误。
- 页面隐藏时暂停动画；离开页面时取消帧、请求、监听器和 ResizeObserver，并销毁 Viewer。
- 按需渲染 `requestRenderMode` 减少静止场景的 GPU 开销；回放更新时显式请求绘制。
- `App.vue` 使用异步组件，Cesium 单独打包，仅进入区域探索时加载。

## 验证

```bash
npm run test:region
npm run format:check
npm run build
find dist/cesium -maxdepth 1 -type d
```

`test:region` 使用 Node 内置测试器直接执行 TypeScript，需 Node 22.18+ 或 Node 24+。
预期 Cesium 静态资源目录是 `dist/cesium/Assets`、`ThirdParty`、`Widgets`、`Workers`。
构建成功不能代替浏览器渲染检查；需要同时验证能播放、拖动、切换活动和离开页面。

## 官方 API 对照

- [GeoJsonDataSource](https://cesium.com/learn/cesiumjs/ref-doc/GeoJsonDataSource.html)：将建筑 GeoJSON 转成 Entity。
- [PolygonGraphics](https://cesium.com/learn/cesiumjs/ref-doc/PolygonGraphics.html)：建筑高度、材质和拉伸。
- [Camera](https://cesium.com/learn/cesiumjs/ref-doc/Camera.html)：倾斜俯瞰、跟随与解除跟随。
- [Scene.requestRender](https://cesium.com/learn/cesiumjs/ref-doc/Scene.html)：显式请求渲染。
