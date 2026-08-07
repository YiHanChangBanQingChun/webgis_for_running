# 数据导入与派生模块

## 数据层次

- `data/running/exportfrom20260806/`：原始 FIT；脚本只读，绝不移动、删除或覆盖。
- `data/processed/activities/<id>.full.json`：所有可由 `fitparse` 识别的 FIT 消息、字段元信息、源文件 SHA-256 和解析状态。
- `data/processed/activities.json`、`calendar.json`、`tracks/<id>.geojson`：由完整归档生成的页面数据，可随时删除后重建。

GeoJSON 只保存地图回放所需字段；完整信息仍在 `.full.json` 和原始 `.fit` 中。若以后新增分析字段，可重新运行派生脚本或重新解析原始 FIT。

## 运行方式

在 PowerShell 中：

```powershell
conda activate running-webgis
cd D:\Users\admin\Downloads\marathon_training\webgis_for_running
python backend\scripts\import_fit.py
python backend\scripts\build_derived.py
python backend\scripts\build_quality_report.py
python backend\scripts\build_spatial_grid.py
```

开发时可先只处理一个文件：

```powershell
python backend\scripts\import_fit.py --limit 1
python backend\scripts\build_derived.py
```

`import_fit.py` 默认跳过已有归档；使用 `--force` 才会重新解析已有活动。

无法完整解析的文件会自动尝试使用更宽容的 `fitdecode` 恢复；若新解析器恢复到更多消息，就保存恢复结果及警告。已在旧版本中标记为部分解析的归档可单独修复，无需重跑完整活动：

```powershell
python backend\scripts\import_fit.py --repair-partial
```

## 何时运行

推荐在**手动导出新的 FIT 文件后**运行：这是数据量不大、最透明可靠的方式。

后端 API 不应在用户打开页面时同步解析 FIT，因为批处理耗时且容易阻塞请求。FastAPI 的职责是读取 `data/processed` 下的派生文件并提供查询接口。

后续若接入自动下载流程，可采用两种方式：

1. Windows 任务计划程序：每天或每次同步后执行这两个脚本。
2. FastAPI 管理接口：触发后台任务/队列执行导入，前端轮询任务状态。

个人项目第一版选择手动运行即可；在确认导入稳定后再自动化。新增 FIT 并完成派生后，应再运行
`build_spatial_grid.py`，以便地图探索页面包含新轨迹；该脚本只读取派生 GeoJSON，不修改原始 FIT。

## 质量报告与最小 API

每次批量导入、派生完成后运行：

```powershell
python backend\scripts\build_quality_report.py
```

它会生成 `data/processed/import-report.json`，其中包含归档覆盖率、解析状态、备用解析器恢复情况、GPS 覆盖、日期范围、运动类型、总距离和 API 就绪判定。

当报告中的 `readiness.api_ready` 为 `true` 时，可启动只读 API：

```powershell
uvicorn app.main:app --app-dir backend --reload
```

接口文档地址为 `http://127.0.0.1:8000/docs`。API 只读取 `data/processed`，不会重新解析或修改 FIT 文件。

当前页面使用的主要接口：

- `GET /api/activities`：活动筛选和分页。
- `GET /api/calendar`、`GET /api/stats/monthly`：首页日历与月度汇总。
- `GET /api/stats/range`：范围汇总、每日/每周序列和 7/28 日相对训练负荷。
- `GET /api/map/heat-grid`：按日期和最少经过次数过滤空间探索网格。
- `GET /api/activities/{id}/track`：单次活动轨迹和逐点指标。
- `GET /api/activities/{id}/insights`：配速稳定性、心率漂移、自动训练类型和公里分段。

训练负荷与自动类型均为基于个人数据的观察指标，不用于医疗判断，也不替代实际训练记录。

## 无法完整解析的 FIT 诊断

对某一个 `partial_or_failed` 文件运行以下命令：

```powershell
python backend\scripts\diagnose_fit.py data\running\exportfrom20260806\458572979607994368.fit
```

该工具只读 FIT，并在 `data/processed/diagnostics/` 写入报告。报告会检查 FIT 头中声明的数据长度是否与文件实际长度匹配，并分别使用 `fitparse` 和 `fitdecode` 尝试读取，记录两者能恢复的消息类型和逐点记录数量。若备用解析器能读取更多 `record`，下一步可将它作为指定文件的恢复解析器；若两者都在同一位置失败，通常说明导出文件在该处截断或含有设备私有字段错误。
