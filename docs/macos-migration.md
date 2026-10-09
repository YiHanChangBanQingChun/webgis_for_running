# macOS迁移与目录逻辑（2026-10-09）

## 项目结构

父目录marathon_training是Windows工作目录的复制品，本身没有Git仓库。唯一现有Git仓库是webgis_for_running，远程为YiHanChangBanQingChun/webgis_for_running。

| 目录 | 职责 | 迁移处理 |
|---|---|---|
| training_database | SQLite训练跟踪、COROS原始快照、用户报告、计划、评价、目标 | 先读AGENTS/CONTEXT/README，备份后更新；不同来源分表，计划不算完成 |
| coros_exports | 早期COROS导出资料 | 保留作来源，不自动联网同步 |
| ../archive/windows-workspace/.coros-mcp | 旧COROS连接包装器 | 2026-10-09整理时归档，当前本地FIT流程不使用 |
| ../archive/windows-workspace/.npm-global、.pydeps | 旧依赖副本 | 已归档；旧.npm-cache已清理，当前使用.venv及npm ci |
| webgis_for_running/backend/app | FIT全量归档、活动/日历/轨迹派生、FastAPI只读服务 | 路径从脚本位置解析，支持环境变量和暂存目录 |
| backend/scripts | 解析、质量报告、250m探索网格、诊断、画图 | 新增refresh_data.py完整导出导入及update_training.py入库 |
| backend_springboot/api | Spring Boot只读API，复用Python派生数据 | Java目标21；Maven Wrapper，不依赖全局mvn |
| frontend | Vue/TypeScript/Vite，Leaflet地图、ECharts图表 | npm ci重装macOS原生依赖，代理随所选后端切换 |
| data/running | 旧576个原始FIT | 保留 |
| data/newdata20261009 | 新630个原始FIT及ZIP | 只读导入；自动选择最新已解压export目录 |
| data/processed | 页面与API实际读取的数据 | 完整导出在暂存目录重建，质量通过才替换 |
| data/processed-backup-* | 上一版完整派生数据 | 可恢复；不提交Git |
| data/activity-overrides.json | 经用户确认的混合/排除活动说明 | 提交规则；不覆盖原始FIT |
| tools/training | 训练跟踪唯一源码与测试 | 父目录训练工具为兼容入口，数据默认读取兄弟training_database |

处理链：原FIT → 全消息归档（含SHA-256与字段元信息）→ 活动索引/日历/GeoJSON → 质量报告/空间网格 → FastAPI或Spring Boot → Vite页面。API不在页面请求时解析FIT。训练SQLite是另一条链，保存COROS原始响应、FIT观测和journal，按ID去重汇总。

## 安装与一键使用

需要Python 3.11+、Node.js 22.12+（推荐24）；选择Spring Boot时另需JDK21+。脚本支持Homebrew标准路径与fnm安装的Node，Python可通过PYTHON_BIN指定。系统自带Python3.9不满足依赖要求。Codex运行时Python仅作为本机已存在时的后备，不是其他机器的安装前提。

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running
./setup_macos.sh
./import_data.sh
./start_development.sh
# 切换Spring Boot
./start_development.sh --backend springboot
# 更新兄弟目录训练SQLite，自动先备份
.venv/bin/python backend/scripts/update_training.py
```

Finder中可双击start_development.command；Spring Boot版是start_development_springboot.command；导入工具是import_data.command。首次启动缺少.venv时自动安装；后续不重复安装，不在每次启动时重新导入。终端显示前后端日志，启动成功自动打开浏览器；Ctrl-C会停止两个进程组。端口被占用时报告错误，不自动换端口。

默认FastAPI为127.0.0.1:8000、Vite为127.0.0.1:5173；Spring Boot为127.0.0.1:8080，前端代理自动随之切换。Vite和API均只监听本机。Maven依赖缓存放项目.maven-cache。

```bash
# 任意完整新导出，请传解压后的FIT目录
./import_data.sh --source '/完整路径/exportSportData_...'
# 无浏览器的验证模式
./start_development.sh --no-open
# Python数据目录覆盖（Spring Boot同样支持）
RUNNING_WEBGIS_DATA_DIR=/完整路径/processed ./start_development.sh
```

完整导出导入会严格使用指定导出的活动集合，不混入旧导出已不存在的活动。SHA-256相同的全量归档可复用，改变的文件会重新解析；部分解析会尝试fitdecode恢复。refresh_data在独立目录完成所有派生和质量检查，失败时原数据仍可用，并保留失败暂存目录供诊断。导入期间应关闭开发服务器；完成后重新启动以刷新缓存。锁目录data/.import-lock防止并发导入；异常断电后确认没有导入进程再移除该空锁。

回滚：停止服务，将data/processed改名保留，再把所需data/processed-backup-*改名为data/processed后重启。不要删除原始FIT或唯一备份。

## 时区与训练口径

FIT规范的date_time字段代表UTC；local_date_time不等同UTC。只有带明确偏移，或字段元信息确认date_time的时间才转换到Asia/Shanghai日期；任意未知naive时间不补时区。索引保留original_start_time、start_time与timezone_evidence，归档不改写。依据：[Garmin FIT Date/Time说明](https://developer.garmin.com/fit/articles/cookbook/datetime.html)。旧8月5日的UTC晚间间歇现在显示中国8月6日，与COROS一致。

78条2026-07-01以来FIT观测单独写入fit_observations，保存session/lap消息与来源SHA。observed_training及weekly_observed_training合并正式跑步、COROS优先、按TEXT活动ID去重；旧weekly_training仍只COROS。未知负荷显示—；圈组不相加。9/16休闲跑及10/2骑车混入记录排除；其他运动保留但不计跑量。10/7类型64暂不猜测。无记录日不是确认休息。

页面活动列表保留全部原活动；详情显示用户备注。训练分析只计正式跑步；首页月度是各类运动汇总，但排除已确认混合/排除活动，日历保留这些活动入口且不计其距离。页面相对负荷来自时长/HR模型，不是COROS训练负荷。运动员参考参数更新到本地10/1观测，观察日期与迁移日期分开，未重新确认旧分区边界。

## 本次结果及验证

- 原576场 → 新630场（新导出覆盖全部旧ID，新增54场）；572条SHA一致归档复用，58条解析或恢复，其中4条是已有ID文件内容改变。
- 活动列表改为按250条分页获取全部记录，修正原来固定576条导致新导出列表截断的问题。
- 630场全部完整解析或带警告完整解析，0条partial_or_failed；620条GPS轨迹，947个250m网格，API就绪。
- Edge独立浏览器会话实际加载页面，无pageerror；首页显示新10月日历，混合活动原记录入口仍可打开。
- 两套后端实际启动、经Vite代理检查health/范围统计/轨迹或insights/空间网格均通过；Ctrl-C退出清理通过；分页函数实际读取3页共630条唯一活动。
- 前端兼容依赖更新后npm audit为0项，生产构建通过；13个Python回归测试及2个Spring Boot测试通过，SQLite integrity/foreign_key检查通过。
- 训练库COROS70场/1321圈保留，fit_archive630条、fit_observations78条；正式新增10/3、10/5、10/6、10/7四场跑步44.186km。
- 10/2腹痛后骑车未关表，7.004km原始混合记录保留但整场排除正式统计；未知有效跑步部分不估算。
- 新数据最新日期10/7；没有10/8新增记录，不标记休息。健康/预测仍是10/1观测。

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
python3 -m unittest discover -s tools/training -v
(cd frontend && npm run build)
(cd backend_springboot/api && ./mvnw -B -ntp -Dmaven.repo.local=../../.maven-cache test)
python3 tools/training/track_training.py verify
```

SQLite、原始FIT、GPS全量轨迹与依赖缓存不提交Git。可重建的导入代码、macOS工具、排除规则、测试及本次训练复盘提交到WebGIS仓库。训练主库位于仓库外的兄弟目录，保留本机原位置；训练脚本唯一源码随仓库提交，兄弟目录保留兼容入口。

## 后续目录整理

2026-10-09已将原Windows启动器移至archive/windows，旧说明及学习方案移至docs/history。根README现在只描述当前用法；训练源码统一在tools/training，兄弟training_database保留兼容入口。详情见[整理记录](cleanup-2026-10-09.md)。
