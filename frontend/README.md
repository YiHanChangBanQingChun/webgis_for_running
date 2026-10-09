# Running WebGIS前端

Vue3＋TypeScript＋Vite页面，使用Leaflet地图、ECharts图表和Element Plus组件。页面包括训练总览、活动记录、训练分析和地图探索。

项目根目录的`start_development.command`同时启动前后端；开发服务器代理`/api`到所选后端。单独开发前端时：

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
npm run build
```

代理默认`http://127.0.0.1:8000`；Spring Boot使用`VITE_API_PROXY_TARGET=http://127.0.0.1:8080`。活动列表通过`src/activityApi.ts`分页获取，不限定历史总场数。训练区间编辑与主题设置保存在浏览器本地。

生成的`dist/`和平台相关的`node_modules/`不提交Git。原Vite示例组件与图片已删除。完整入口见[项目README](../README.md)。
