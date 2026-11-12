# 强风吹拂 WebGIS：Spring Boot 后端说明

## 1. 子项目定位

本目录是原 FastAPI 查询服务的 Spring Boot 迁移版本。它使用 **Java 21、Spring Boot 4.1.1、Maven Wrapper、Spring MVC、Jackson 3、Validation 与 Actuator**。

初学者建议先读[代码阅读指南](docs/代码阅读指南.md)，再沿 Controller → Service → Repository 阅读实现；指南同时解释常见注解、数据流和重构后的计算步骤。

系统仍采用“离线处理 + 在线只读查询”的边界：

- Python 负责 FIT 解析、异常文件恢复、GIS 运算和派生文件生成；
- Spring Boot 只读取 `data/processed`，负责筛选、统计、训练洞察和 HTTP API；
- Vue 前端只通过 `/api/**` 使用数据，不直接读取磁盘；
- 当前不使用数据库，也不会在 HTTP 请求中解析 FIT。

这样保留了 Python 在 `fitparse`、`fitdecode`、GeoPandas/GDAL 等方面的优势，同时可以学习标准的 Java Web 工程结构。

## 2. 数据流

```text
原始 FIT（永久保留）
        │
        ▼
Python 批处理脚本
        │
        ├── activities.json       活动轻量索引
        ├── calendar.json         运动日历
        ├── import-report.json    导入质量报告
        ├── athlete-profile.json  运动员区间配置
        ├── spatial-grid.json     预计算空间网格
        └── tracks/*.geojson      单次轨迹和逐点指标
                    │
                    ▼
        Spring Boot Repository（只读、带自动失效缓存）
                    │
                    ▼
       Service（筛选、聚合、洞察、质量门禁）
                    │
                    ▼
          Controller → Vue / 浏览器
```

Spring Boot 不会修改上述文件。Python 重新生成文件后，Repository 根据文件修改时间和大小自动刷新缓存，通常不需要重启后端。

## 3. 工程结构

```text
api/
├── pom.xml                              Maven 配置，Java 21 / Spring Boot 4.1.1
├── mvnw / mvnw.cmd                      Maven Wrapper，无需单独安装 Maven
├── SpringBoot后端说明.md                 本文档
├── docs/代码阅读指南.md                  初学者阅读顺序、注解与调用链说明
└── src/
    ├── main/
    │   ├── java/dev/runningatlas/api/
    │   │   ├── RunningWebgisApiApplication.java
    │   │   ├── package-info.java           包级职责与推荐阅读顺序
    │   │   ├── activity/
    │   │   │   ├── ActivityController.java
    │   │   │   ├── ActivityService.java
    │   │   │   ├── ActivityRepository.java
    │   │   │   └── ActivityInsightsService.java
    │   │   ├── statistics/
    │   │   │   ├── StatisticsController.java
    │   │   │   └── StatisticsService.java
    │   │   ├── exploration/
    │   │   │   ├── HeatGridController.java
    │   │   │   └── HeatGridService.java
    │   │   ├── system/
    │   │   │   └── SystemDataController.java
    │   │   ├── config/
    │   │   │   ├── RunningWebgisProperties.java
    │   │   │   └── WebConfig.java
    │   │   └── common/
    │   │       ├── ApiException.java
    │   │       ├── ApiExceptionHandler.java
    │   │       ├── DataReadinessService.java
    │   │       └── JsonValues.java
    │   └── resources/application.properties
    └── test/
        ├── java/dev/runningatlas/api/
        │   ├── RunningWebgisApiApplicationTests.java
        │   ├── ServiceRegressionTests.java
        │   └── activity/ActivityRepositoryTests.java
        └── resources/service-responses.json    重构前人工样本的接口响应
```

### 3.1 各层职责

- **Controller**：声明 URL，接收和初步校验查询参数，不实现复杂业务。
- **Service**：实现活动筛选、月度统计、滚动负荷、网格过滤和训练洞察。
- **Repository**：封装文件路径、Jackson 解析、缓存与路径安全检查。
- **Config**：绑定外部配置并设置 CORS。
- **Common**：放置跨模块的异常、数据就绪门禁和 JSON 工具。

这是按业务功能分包（package by feature），而不是把所有 Controller、Service 分别堆在全局目录。随着功能增加，每个业务模块仍能保持内聚。

## 4. 运行环境

当前项目的编译版本以 `pom.xml` 为准，要求 JDK 21 或可编译 Java 21 的更高版本。
在 macOS / Linux 中先执行：

```bash
java -version
javac -version
./mvnw --version
```

后续 Windows 路径是历史机器的配置示例，不能直接用于当前 macOS 环境。
历史 Windows 环境曾安装 JDK 25：

```text
C:\Users\admin\.jdks\openjdk-25\jdk-25.0.2
```

新开 PowerShell 后先检查：

```powershell
java -version
javac -version
```

两者应满足当前项目的 Java 21 编译要求。如果 Windows 的 VS Code 终端仍使用旧 JDK，可只为当前终端设置（以下仍以历史 JDK 25 路径为例）：

```powershell
$env:JAVA_HOME = 'C:\Users\admin\.jdks\openjdk-25\jdk-25.0.2'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

建议在 VS Code 命令面板运行 `Java: Configure Java Runtime`，为项目选择已安装且满足要求的 JDK。

## 5. 开发运行方式

必须先进入包含 `pom.xml` 的目录：

```powershell
cd D:\Users\admin\Downloads\marathon_training\webgis_for_running\backend_springboot\api
```

运行测试：

```powershell
.\mvnw.cmd clean test
```

启动开发服务：

```powershell
.\mvnw.cmd spring-boot:run
```

默认地址：

```text
http://127.0.0.1:8080
```

验证：

```text
http://127.0.0.1:8080/actuator/health
http://127.0.0.1:8080/api/health
```

看到 `"status":"UP"` 和 `"status":"ok"` 表示 Java 服务与派生数据都已就绪。`/actuator/health` 只说明进程健康；`/api/health` 还会检查导入质量报告。

## 6. 数据目录配置

默认配置是：

```properties
running-webgis.data-directory=${RUNNING_WEBGIS_DATA_DIR:../../data/processed}
```

该相对路径以启动命令所在目录 `backend_springboot/api` 为基准。若从其他目录运行 JAR，建议使用绝对路径：

```powershell
$env:RUNNING_WEBGIS_DATA_DIR = 'D:\Users\admin\Downloads\marathon_training\webgis_for_running\data\processed'
.\mvnw.cmd spring-boot:run
```

部署时也应通过环境变量配置，不要把个人绝对路径提交到 Git。

## 7. API 清单

| 方法与路径 | 作用 | 主要参数 |
|---|---|---|
| `GET /api/health` | 数据质量与 API 就绪状态 | 无 |
| `GET /api/quality-report` | 完整导入质量报告 | 无 |
| `GET /api/athlete-profile` | 个人阈值、比赛预测、六区配置 | 无 |
| `GET /api/activities` | 活动筛选、排序、分页 | `start`、`end`、`sport`、`has_gps`、距离、排序、分页 |
| `GET /api/calendar` | 运动日历派生数据 | 无 |
| `GET /api/stats/monthly` | 月度汇总 | `month=YYYY-MM` |
| `GET /api/stats/range` | 范围汇总、每日/每周数据、7/28 日负荷 | `start`、`end` |
| `GET /api/map/heat-grid` | 空间探索网格过滤 | `start`、`end`、`min_visits` |
| `GET /api/activities/{id}` | 单次活动摘要 | 活动 ID |
| `GET /api/activities/{id}/track` | 单次 GeoJSON 与逐点指标 | 活动 ID |
| `GET /api/activities/{id}/insights` | 稳定性、漂移、停顿、类型与公里分段 | 活动 ID |

示例：

```text
GET /api/activities?start=2026-08-01&end=2026-08-31&sport=running&sort=distance_desc&limit=20
GET /api/stats/monthly?month=2026-08
GET /api/map/heat-grid?start=2026-01-01&end=2026-12-31&min_visits=2
```

当前返回结构尽量保持与 FastAPI 一致，前端只需把 API 基础地址从 `http://127.0.0.1:8000` 改为 `http://127.0.0.1:8080` 即可逐步切换。

## 8. 请求内部逻辑

以 `GET /api/activities` 为例：

1. Spring MVC 将查询参数转换成 `LocalDate`、`Boolean`、`Double` 等 Java 类型；
2. Controller 检查分页和负数距离等边界；
3. Service 调用 `DataReadinessService`，确认 `api_ready=true`；
4. Repository 读取或复用 `activities.json` 缓存；
5. Service 完成筛选、排序和分页；
6. Jackson 3 将 `JsonNode` 序列化为 JSON 响应。

保留 `JsonNode` 是迁移阶段的有意选择：派生轨迹包含大量动态指标，而且现有前端已经依赖其 JSON 结构。未来数据契约稳定后，可逐步将轻量活动摘要替换成 Java `record` DTO；GeoJSON 和逐点序列仍适合保留树模型。

## 9. 缓存与一致性

Repository 缓存每个已读取文件，同时记录：

- 最后修改时间；
- 文件大小；
- 已解析的 Jackson 节点。

下一次请求若发现任一元数据变化，就重新读取文件。这样可以避免每个请求重复解析大型 GeoJSON，又能在 Python 派生完成后自动更新。

生成文件时应继续遵循“先写临时文件，再原子替换目标文件”的做法，避免 Spring Boot 恰好读到半写入 JSON。

## 10. 异常与安全边界

- 缺少必要派生数据时返回 `503 Service Unavailable`；
- 找不到活动或轨迹时返回 `404 Not Found`；
- 日期范围、分页、排序等参数错误返回 `422 Unprocessable Entity`；
- 活动 ID 仅允许字母、数字、下划线和连字符，防止目录穿越；
- CORS 当前只允许本地 Vite 的 5173 端口；
- API 只有 GET 路由，不提供原始 FIT 下载、修改或删除接口；
- 训练负荷与自动分类是观察指标，不是医疗结论。

错误响应示例：

```json
{
  "timestamp": "2026-10-07T20:00:00-06:00",
  "detail": "起始日期不能晚于结束日期。"
}
```

## 11. 新增 FIT 后如何刷新

不要让 Spring Boot 直接处理 FIT。在项目根目录依次运行：

```powershell
conda activate running-webgis
python backend\scripts\import_fit.py
python backend\scripts\build_derived.py
python backend\scripts\build_quality_report.py
python backend\scripts\build_spatial_grid.py
```

然后刷新网页即可。Repository 会检测派生文件变化。只有修改 Java 源码或配置时才需要重启 Spring Boot。

## 12. 打包与运行 JAR

```powershell
.\mvnw.cmd clean package
java -jar target\running-webgis-api-0.0.1-SNAPSHOT.jar
```

由于 JAR 可能从任意工作目录启动，推荐先设置：

```powershell
$env:RUNNING_WEBGIS_DATA_DIR = 'D:\绝对路径\webgis_for_running\data\processed'
```

## 13. 测试说明

- `RunningWebgisApiApplicationTests`：确认完整 Spring 上下文能够创建；
- `ActivityRepositoryTests`：在临时目录构造 JSON，验证读取与文件变化后的缓存刷新；
- 真实数据冒烟测试应覆盖健康、活动列表、月度/范围统计、网格、详情、轨迹和洞察。

测试不会改动 `data/processed`。执行：

```powershell
.\mvnw.cmd clean test
```

## 14. 推荐的后续学习顺序

1. 为 Controller 增加 MockMvc 接口契约测试；
2. 将活动摘要逐步改为明确的 Java `record` DTO；
3. 引入 springdoc-openapi，提供 Swagger UI；
4. 增加 ETag 或 `Last-Modified`，优化大型轨迹响应；
5. 数据规模明显增大后再引入 PostGIS，Repository 接口保持不变；
6. 如需自动导入，使用计划任务或独立作业，不在 GET 请求中同步解析 FIT。

## 15. 与 FastAPI 的关系

迁移完成后不必立即删除 FastAPI。学习阶段可以让两者并行：

```text
FastAPI:     http://127.0.0.1:8000
Spring Boot: http://127.0.0.1:8080
```

用相同参数比较两边 JSON，确认前端页面行为一致后再切换。Python 后端中的离线 FIT/GIS 工具仍应长期保留；真正被替代的是在线只读 HTTP 查询层。
