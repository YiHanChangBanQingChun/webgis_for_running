# 强风吹拂 · Running WebGIS

个人跑步FIT数据的地图、日历与训练分析工具。Vue前端通过只读API查询Python预处理的JSON/GeoJSON；API可选FastAPI或Spring Boot。个人训练SQLite位于工作区兄弟目录`../training_database/`。

## macOS快速使用

首次配置需要Python3.11+、Node.js22.12+（推荐24）；Spring Boot另需JDK21+。

```bash
./setup_macos.sh
./import_data.sh
./start_development.sh
```

Finder可直接双击：

| 入口 | 用途 |
|---|---|
| `start_development.command` | 启动FastAPI＋前端，打开浏览器 |
| `start_development_springboot.command` | 启动Spring Boot＋前端 |
| `import_data.command` | 导入最新已解压的完整FIT导出 |

前端地址`http://127.0.0.1:5173`；FastAPI为8000端口、Spring Boot为8080端口。Ctrl-C或关闭启动终端会清理前后端进程。导入前关闭服务，导入后重启以刷新缓存。

```bash
# 指定其他完整导出
./import_data.sh --source '/完整路径/exportSportData_...'
# 更新兄弟目录训练SQLite（自动先备份）
.venv/bin/python backend/scripts/update_training.py
```

## 目录结构

```text
backend/                  FIT解析、派生、质量检查、FastAPI
backend_springboot/api/    Spring Boot只读API
frontend/                 Vue/TypeScript/Vite页面
scripts/                  macOS启动辅助逻辑
tools/training/           训练跟踪工具的唯一源码与测试
data/                     原始导出、当前派生数据、回滚备份及活动标注
docs/                     当前说明、迁移记录、训练复盘、历史文档
archive/windows/          旧Windows启动器，仅作历史存档
```

## 数据规则

- 原始FIT只读；完整导出先在暂存目录重建，通过质量检查才替换`data/processed/`，自动保留上一版。
- 优先选择`data/newdata*/export*/`最新已解压目录，也可显式指定来源。
- 活动ID使用字符串；FIT与COROS按ID去重，用户说明、观测和分析各自保留来源。
- `data/activity-overrides.json`记录经用户确认的混合或排除活动；原始记录仍可查看。
- 训练分析只计正式跑步；首页月度汇总各类运动，并排除已标注活动。未知负荷不是零。
- 原始数据、SQLite、GPS全量文件、备份与依赖缓存不提交Git。

## 文档与验证

[文档索引](docs/README.md) · [macOS迁移与回滚](docs/macos-migration.md) · [数据处理说明](backend/README.md) · [训练复盘](docs/2026-10-09-training-review.md) · [整理记录](docs/cleanup-2026-10-09.md)

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
python3 -m unittest discover -s tools/training -v
(cd frontend && npm run build)
(cd backend_springboot/api && ./mvnw -B -ntp -Dmaven.repo.local=../../.maven-cache test)
python3 tools/training/track_training.py verify
```

旧Windows使用手册、最初项目规划和Spring Boot学习方案统一保存在[历史文档](docs/history/README.md)，不代表当前启动配置。
