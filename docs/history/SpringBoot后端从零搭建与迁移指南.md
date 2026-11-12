# Spring Boot 后端从零搭建与迁移指南

> 适用项目：**强风吹拂 · Running WebGIS**  
> 文档目标：在不破坏现有 FastAPI 后端的前提下，从零学习并搭建一个 Spring Boot 查询后端，最终让现有 Vue 前端可以无感切换。  
> 本文只提供工程方案与学习步骤，**暂不修改任何项目代码**。

## 1. 先确定迁移边界

本项目并不适合把所有 Python 代码一次性改写成 Java。更符合实际工程流程的方案是：

```text
FIT 原始文件
    │
    ▼
Python 离线数据处理
├─ FIT 容错解析（fitparse / fitdecode）
├─ GeoPandas / Shapely / PyProj 空间分析
├─ 质量报告
└─ 生成 JSON / GeoJSON
    │
    ▼
data/processed/
    │
    ▼
Spring Boot 只读查询服务
├─ 参数校验
├─ 活动筛选与统计
├─ JSON / GeoJSON 读取
├─ 缓存与异常处理
└─ REST API
    │
    ▼
Vue 3 + Leaflet + ECharts
```

### 推荐结论

- **保留 Python 数据处理层**：FIT 解析和 GIS 分析仍由 Python 完成。
- **用 Spring Boot 重写 FastAPI 查询层**：学习 Java、Spring MVC、依赖注入、配置、测试和工程分层。
- **暂时不引入数据库**：继续读取 `data/processed`，降低第一阶段学习复杂度。
- **新旧后端并行运行**：FastAPI 使用 `8000`，Spring Boot 使用 `8080`；接口验收完成后再切换前端代理。
- **保持 API 契约不变**：路径、参数、状态码和 JSON 字段名尽量与 FastAPI 一致，避免同时修改前端。

这是一种常见的“离线计算 + 在线查询”架构。未来数据规模或写入需求增加后，再考虑 SQLite、PostgreSQL/PostGIS。

---

## 2. 目标技术选型

| 项目 | 建议选择 | 原因 |
| --- | --- | --- |
| Java | **JDK 21 LTS** | 长期支持、资料丰富，适合学习和实际项目 |
| Spring Boot | 使用 Spring Initializr 提供的**当前稳定版** | 避免手动拼装版本；创建项目时记录实际版本 |
| 构建工具 | **Maven + Maven Wrapper** | 入门资料最多，Windows 使用简单，无需单独安装 Maven |
| Web 框架 | Spring MVC / Spring Web | 适合现有同步、只读 REST API |
| JSON | Spring Boot 默认 Jackson 集成 | 可直接映射 JSON 文件和 DTO |
| 参数校验 | Jakarta Validation | 统一校验日期、分页和数值范围 |
| 健康检查 | Spring Boot Actuator | 提供标准健康检查与运行信息 |
| 测试 | JUnit 5、Spring Boot Test、MockMvc | 覆盖单元、Web 层和集成测试 |
| IDE | IntelliJ IDEA Community 或 VS Code | 二选一即可 |

截至本文编写时，Spring 官方当前稳定文档为 Spring Boot 4.1.x，最低要求 Java 17；本文仍推荐安装 Java 21 LTS。实际创建项目时，以 [Spring Initializr](https://start.spring.io/) 当天提供的稳定版本为准，不选择 SNAPSHOT 或 MILESTONE。

官方参考：

- [Spring Boot 官方主页](https://spring.io/projects/spring-boot)
- [Spring Boot 系统要求](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring 官方入门教程](https://spring.io/guides/gs/spring-boot/)

---

## 3. Windows 从零安装 Java 环境

你的电脑目前没有 Java 环境，因此先完成 JDK 安装。**JRE 不够，必须安装 JDK**，因为项目需要编译 Java 源码。

### 3.1 安装 JDK 21

推荐使用 Eclipse Temurin 21 或 Microsoft Build of OpenJDK 21，选择其中一个即可，不要重复安装多套 JDK。

#### 方法 A：使用 winget

在 PowerShell 中执行：

```powershell
winget install EclipseAdoptium.Temurin.21.JDK
```

如果更希望使用 Microsoft OpenJDK：

```powershell
winget install Microsoft.OpenJDK.21
```

#### 方法 B：图形化安装

从发行商官网下载 Windows x64 JDK 21 安装包，安装时勾选：

- 设置 `JAVA_HOME`；
- 将 Java 加入 `PATH`；
- 安装 JDK，而不是仅安装 JRE。

安装完成后关闭并重新打开 PowerShell。

### 3.2 验证安装

```powershell
java -version
javac -version
Get-Command java
$env:JAVA_HOME
```

预期结果：

- `java -version` 和 `javac -version` 都显示 21；
- `Get-Command java` 指向刚安装的 JDK；
- `JAVA_HOME` 指向 JDK 根目录，而不是 `bin` 目录。

如果终端仍提示找不到 `java`，先重启终端；若仍失败，再检查系统环境变量，不要在项目脚本里写死个人 JDK 路径。

### 3.3 安装开发工具

任选一种：

#### IntelliJ IDEA Community

适合第一次系统学习 Java。打开项目时将 Project SDK 选择为 JDK 21。

#### VS Code

安装扩展：

- Extension Pack for Java；
- Spring Boot Extension Pack。

现有 Vue 前端仍可以使用同一个 VS Code 工作区。

### 3.4 Maven 是否需要单独安装

不需要。由 Spring Initializr 生成的项目会携带：

```text
mvnw
mvnw.cmd
.mvn/wrapper/
```

Windows 使用 `mvnw.cmd` 即可。Wrapper 会使用项目声明的 Maven 版本，有利于团队保持构建环境一致。

---

## 4. 用 Spring Initializr 创建工程

### 4.1 建议的存放位置

迁移期间不要覆盖 `backend/`。建议在当前仓库中新建并行目录：

```text
webgis_for_running/
├─ backend/                 # 现有 Python/FastAPI，暂时保留
├─ backend-springboot/      # 新 Spring Boot 工程
├─ frontend/
└─ data/
```

待 Spring Boot 完成全部接口、测试通过并稳定使用后，再决定是否重命名目录。

### 4.2 Initializr 参数

访问 <https://start.spring.io/>，建议选择：

| 项目项 | 建议值 |
| --- | --- |
| Project | Maven |
| Language | Java |
| Spring Boot | 当前稳定版，不选 SNAPSHOT/MILESTONE |
| Group | `dev.runningatlas` |
| Artifact | `running-webgis-api` |
| Name | `running-webgis-api` |
| Description | `REST API for personal running WebGIS` |
| Package name | `dev.runningatlas.api` |
| Packaging | Jar |
| Java | 21 |

添加依赖：

- **Spring Web**：REST API 和内嵌服务器；
- **Validation**：请求参数校验；
- **Spring Boot Actuator**：健康检查；
- **Spring Boot DevTools**：开发期自动重启，可选；
- **Configuration Processor**：配置属性提示，可选。

暂时不要添加：

- Spring Data JPA；
- 数据库驱动；
- Spring Security；
- Lombok；
- WebFlux。

原因是第一阶段只重写现有只读 API。过早加入数据库、安全框架或响应式编程，会让学习重点从 Spring MVC 和工程结构偏离。

下载 ZIP 后，将内容解压到：

```text
D:\Users\admin\Downloads\marathon_training\webgis_for_running\backend-springboot
```

### 4.3 第一次构建和启动

```powershell
cd D:\Users\admin\Downloads\marathon_training\webgis_for_running\backend-springboot
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
```

默认端口为 `8080`。第一次运行需要从 Maven Central 下载依赖，耗时取决于网络。

常用命令：

```powershell
# 运行全部测试
.\mvnw.cmd test

# 开发模式启动
.\mvnw.cmd spring-boot:run

# 清理并打包
.\mvnw.cmd clean package

# 运行打包后的应用
java -jar target\running-webgis-api-0.0.1-SNAPSHOT.jar
```

---

## 5. 推荐的工程结构

不建议把所有 Controller、Service、DTO 各自堆进一个巨大目录。对本项目而言，“按业务功能分包，功能内部再分层”更利于扩展：

```text
backend-springboot/
├─ pom.xml
├─ mvnw.cmd
├─ .mvn/wrapper/
└─ src/
   ├─ main/
   │  ├─ java/dev/runningatlas/api/
   │  │  ├─ RunningWebgisApiApplication.java
   │  │  ├─ common/
   │  │  │  ├─ config/              # CORS、配置属性、Jackson
   │  │  │  ├─ error/               # 统一异常和错误响应
   │  │  │  └─ model/               # 跨功能共用类型
   │  │  ├─ activity/
   │  │  │  ├─ ActivityController.java
   │  │  │  ├─ ActivityService.java
   │  │  │  ├─ ActivityRepository.java
   │  │  │  └─ dto/
   │  │  ├─ calendar/
   │  │  ├─ stats/
   │  │  ├─ map/
   │  │  ├─ profile/
   │  │  ├─ quality/
   │  │  └─ infrastructure/
   │  │     └─ json/                 # JSON/GeoJSON 文件加载实现
   │  └─ resources/
   │     ├─ application.yml
   │     ├─ application-dev.yml
   │     └─ application-prod.yml
   └─ test/
      └─ java/dev/runningatlas/api/
```

### 各层职责

#### Controller

- 接收 HTTP 请求；
- 解析 Query/Path 参数；
- 触发 Jakarta Validation；
- 调用 Service；
- 返回 DTO 和状态码；
- 不直接读取文件，不编写复杂统计逻辑。

#### Service

- 实现筛选、排序、分页和统计；
- 组合多个 Repository 的结果；
- 决定找不到活动、数据未就绪等业务行为；
- 不关心 HTTP 细节。

#### Repository

- 定义数据读取接口；
- 将来可以从 JSON 实现切换到数据库实现；
- 第一阶段由 `JsonActivityRepository` 等类读取文件。

#### DTO / Model

- 明确接口输入输出结构；
- 不直接把任意 `Map<String, Object>` 传播到整个系统；
- 对结构固定的活动摘要优先使用 Java `record`；
- 对结构复杂、字段动态的 GeoJSON，可先使用 `JsonNode`，以后再逐步类型化。

---

## 6. 外部数据目录与配置

### 6.1 不要把运动数据打进 JAR

`data/processed` 会被 Python 更新，因此不能放到 `src/main/resources`。资源目录会被打包进 JAR，不适合运行时变化的数据。

建议在 `application.yml` 定义自有配置：

```yaml
server:
  port: 8080

running:
  data-root: ${RUNNING_DATA_ROOT:../data/processed}

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

含义：

- 优先读取环境变量 `RUNNING_DATA_ROOT`；
- 没有环境变量时，使用相对于 `backend-springboot` 的 `../data/processed`；
- 不写死 `D:\Users\admin\...` 这样的个人路径；
- 部署到其他电脑时只需更改环境变量。

PowerShell 临时配置：

```powershell
$env:RUNNING_DATA_ROOT = "D:\running-data\processed"
.\mvnw.cmd spring-boot:run
```

建议使用 `@ConfigurationProperties(prefix = "running")` 将配置映射成类型安全的配置类，并在启动时验证目录是否存在。

### 6.2 当前需要读取的数据

| 文件 | 结构 | 用途 |
| --- | --- | --- |
| `activities.json` | 活动对象数组 | 活动列表、详情、统计 |
| `calendar.json` | 按日期聚合的数组 | 运动日历 |
| `import-report.json` | 单个对象 | 质量报告和 API 就绪判断 |
| `spatial-grid.json` | 单个对象，包含 `cells` | 地图探索 |
| `athlete-profile.json` | 单个对象 | 个人阈值和默认区间 |
| `tracks/{id}.geojson` | GeoJSON FeatureCollection | 单次轨迹和逐点指标 |

### 6.3 活动摘要字段

当前 `activities.json` 包含：

```text
id, source_file, parse_status, parse_error, date, start_time,
sport, sub_sport, distance_m, elapsed_s, timer_s, calories,
average_heart_rate, max_heart_rate, average_speed_mps,
average_pace_s_per_km, total_ascent_m, total_descent_m,
record_count, has_gps, metrics_derived_from_records,
full_data_path, track_path
```

Java 字段通常使用驼峰命名，例如 `distanceM`。但现有前端期望 `distance_m`。迁移时应确保 JSON 仍输出 snake_case，可以：

- 在全局 Jackson 配置中设置 snake_case；或
- 给 DTO 字段添加明确的 JSON 属性名。

第一种方式更统一，第二种方式更显式。无论选择哪种，都要用接口测试锁定输出字段名。

---

## 7. JSON 文件读取方案

### 7.1 第一阶段：启动时加载到内存

当前只有数百条活动摘要，适合：

1. 应用启动时读取 `activities.json`、`calendar.json` 和质量报告；
2. 使用不可变集合保存在内存；
3. 按活动 ID 建立 `Map<String, ActivitySummary>` 索引；
4. 轨迹 GeoJSON 按请求读取，或使用有上限的缓存；
5. API 请求只做内存筛选和必要的文件读取。

这与现有 FastAPI 的缓存思路接近，容易验证行为一致性。

### 7.2 不建议的做法

- 每次请求重新读取全部 `activities.json`；
- Controller 里直接调用 `Files.readString()`；
- 用字符串拼接用户传入的活动 ID 形成文件路径；
- 无限缓存所有轨迹；
- Python 正在重写文件时，Java 恰好读到半个 JSON。

### 7.3 安全读取轨迹

活动 ID 必须满足预期格式，例如仅允许数字或安全的 UUID 字符。读取前应：

1. 校验 ID；
2. 使用 `dataRoot.resolve("tracks").resolve(id + ".geojson").normalize()`；
3. 确认最终路径仍位于 `tracks` 目录下；
4. 文件不存在时返回 404；
5. JSON 损坏或无法读取时返回统一的 503/500 错误。

这可以防止路径穿越，例如恶意 ID `../../secret`。

### 7.4 Python 与 Java 的文件交接

后续建议让 Python 使用原子替换：

1. 先写入同目录临时文件；
2. 完整写入并关闭；
3. 再用替换操作覆盖正式 JSON。

Spring Boot 可以提供手动刷新机制，或检查文件修改时间后重载缓存。第一版不要使用定时轮询，先实现明确、可测试的启动加载与手动重启。

---

## 8. API 契约迁移清单

Spring Boot 第一版应复刻以下接口：

| 优先级 | 方法与路径 | 核心行为 |
| --- | --- | --- |
| P0 | `GET /api/health` | 数据是否就绪；未就绪返回 503 |
| P0 | `GET /api/quality-report` | 返回导入质量报告 |
| P0 | `GET /api/activities` | 筛选、排序、偏移和分页 |
| P0 | `GET /api/calendar` | 返回日历数组 |
| P0 | `GET /api/activities/{id}` | 单次活动摘要；不存在返回 404 |
| P0 | `GET /api/activities/{id}/track` | 返回原始 GeoJSON；不存在返回 404 |
| P1 | `GET /api/stats/monthly` | 月度汇总 |
| P1 | `GET /api/stats/range` | 范围统计、日/周序列、7/28 日负荷 |
| P1 | `GET /api/map/heat-grid` | 日期和访问次数筛选 |
| P1 | `GET /api/activities/{id}/insights` | 配速稳定性、心率漂移和公里分段 |
| P2 | `GET /api/athlete-profile` | 个人阈值和默认区间 |

### 8.1 `/api/activities` 参数

需要保持：

```text
start, end, sport, has_gps,
min_distance_km, max_distance_km,
sort, offset, limit
```

工程建议：

- 将查询参数封装成 `ActivityQuery`；
- 日期使用 `LocalDate`，不要在业务层反复比较字符串；
- `sort` 使用枚举，不接受任意字符串；
- `offset >= 0`；
- `1 <= limit <= 576`，以后再将上限改成配置；
- 返回 `{ "total": ..., "items": [...] }`，保持前端兼容。

### 8.2 状态码约定

| 场景 | 状态码 |
| --- | --- |
| 请求成功 | 200 |
| 参数格式或范围错误 | 400 |
| 活动或轨迹不存在 | 404 |
| 数据文件尚未生成/暂不可用 | 503 |
| 未预期的服务端错误 | 500 |

现有 FastAPI 某些参数错误可能返回 422，而 Spring Validation 通常更适合统一成 400。若目标是完全无感替换，可以先保留原状态码；若允许规范化，则应同步更新测试和文档。

### 8.3 统一错误响应

建议所有错误返回同一结构：

```json
{
  "timestamp": "2026-10-06T12:00:00Z",
  "status": 404,
  "code": "ACTIVITY_NOT_FOUND",
  "message": "未找到该活动",
  "path": "/api/activities/123"
}
```

使用全局异常处理器集中处理：

- 参数校验异常；
- 活动不存在；
- 数据未就绪；
- JSON 解析失败；
- 其他未预期异常。

不要在每个 Controller 中重复 `try/catch`。

---

## 9. 建议的实现顺序

### 阶段 0：记录现有契约

在改写前保存：

- FastAPI `/docs` 中的接口定义；
- 每个接口一份典型响应；
- 空结果、非法参数、无轨迹活动等边界响应；
- 当前前端实际请求参数。

这些内容是迁移验收标准，而不是只靠“页面看起来能打开”。

### 阶段 1：最小可运行服务

学习目标：

- `@SpringBootApplication`；
- 依赖注入；
- `@RestController`；
- `@GetMapping`；
- `application.yml`；
- Actuator 健康检查。

先完成自定义 `/api/health`，不要一开始实现所有统计。

### 阶段 2：配置与 JSON Repository

学习目标：

- `@ConfigurationProperties`；
- `ObjectMapper`；
- `Path` / `Files`；
- DTO 与 Java `record`；
- 应用启动生命周期；
- 业务异常。

先读取：

1. `import-report.json`；
2. `activities.json`；
3. `calendar.json`。

### 阶段 3：完成 P0 查询接口

依次完成：

1. 质量报告；
2. 活动列表；
3. 活动详情；
4. 轨迹；
5. 日历。

此时就可以用浏览器或 API 客户端与 FastAPI 对照响应。

### 阶段 4：迁移统计逻辑

将 FastAPI 中的逻辑逐项翻译为 Java：

- 月度统计；
- 日期范围统计；
- 日/周聚合；
- 7/28 日相对负荷；
- 配速变异系数；
- 心率漂移；
- 公里分段；
- 空间网格筛选。

迁移算法时先用相同输入建立“黄金样本”，比较 Python 和 Java 输出。浮点结果应允许合理误差，而不是要求二进制级完全相等。

### 阶段 5：切换前端进行验收

现有 Vite 将 `/api` 代理到 FastAPI 的 `8000` 端口。Spring Boot 默认使用 `8080`。

验收时只需临时把代理目标改成：

```text
http://127.0.0.1:8080
```

依次检查：

- 首页日历与月度统计；
- 活动筛选和分页；
- 活动详情；
- 地图和轨迹回放；
- 全部运动图表；
- 训练分析；
- 空间探索；
- 深色模式下的错误提示。

Spring Boot 未全部完成前，随时可以把代理切回 `8000`。

### 阶段 6：完成替换

只有在以下条件全部满足后，才停止默认启动 FastAPI：

- Spring Boot 覆盖全部现用 API；
- 自动测试通过；
- 前端功能回归通过；
- 响应时间可接受；
- 数据文件更新后可以可靠重载；
- README 和启动方式已经更新。

Python 脚本仍然保留，负责 FIT 导入和数据派生。

---

## 10. 测试策略

### 10.1 测试金字塔

#### 单元测试

目标：快速验证纯业务算法。

- 活动筛选；
- 日期范围；
- 排序；
- 月度统计；
- 负荷计算；
- 配速稳定性；
- 心率漂移；
- 分段逻辑。

这些测试不启动 Spring，不读取真实个人数据。

#### Web 层测试

使用 MockMvc 测试：

- 路由是否正确；
- 参数是否绑定；
- 校验失败状态码；
- JSON 字段名；
- 404 和 503 错误结构。

#### 集成测试

使用测试资源或临时目录放置少量脱敏 JSON：

- 正常活动；
- 无 GPS 活动；
- 空日历；
- 损坏 JSON；
- 缺少轨迹文件；
- 边界日期。

测试不应依赖本机 `data/processed`，否则其他开发者和 CI 无法复现。

### 10.2 API 契约对比

可为每个接口准备脱敏请求，并分别请求：

```text
FastAPI:      http://127.0.0.1:8000/api/...
Spring Boot:  http://127.0.0.1:8080/api/...
```

比较：

- 状态码；
- JSON 键名和类型；
- 排序顺序；
- null 与缺失字段；
- 日期时间格式；
- 浮点误差；
- 中文错误消息是否稳定。

### 10.3 每次提交前

```powershell
.\mvnw.cmd test
.\mvnw.cmd clean package
```

同时运行前端构建：

```powershell
cd ..\frontend
npm run build
```

---

## 11. CORS、日志与运行配置

### 11.1 CORS

开发期允许：

```text
http://localhost:5173
http://127.0.0.1:5173
```

建议集中配置 CORS，不要在每个 Controller 上重复注解。生产环境应从配置读取明确的前端域名，避免使用 `*`。

Vite 开发代理正常工作时，浏览器看到的是同源 `/api` 请求，通常不触发 CORS；但保留受控的开发 CORS 有利于独立调试 API。

### 11.2 日志

使用 Spring Boot 默认日志体系即可，避免 `System.out.println`。建议记录：

- 应用启动时的数据根目录；
- 加载的活动数量；
- 缺失或损坏的数据文件；
- 缓存刷新结果；
- 请求异常的错误码和上下文。

不要记录：

- 完整 GPS 坐标序列；
- COROS 登录信息；
- Token、Cookie；
- 整份运动员配置；
- 用户主目录等无关隐私。

### 11.3 配置分环境

建议：

```text
application.yml          # 所有环境共用默认值
application-dev.yml      # 本地开发
application-prod.yml     # 生产部署
```

启动指定环境：

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=dev"
```

敏感配置使用环境变量，不提交真实值到 Git。

---

## 12. 性能与缓存

第一版无需复杂优化，但应避免明显问题：

- 活动摘要和日历启动时读取一次；
- 活动 ID 使用 `Map` 索引，避免详情接口每次遍历全部列表；
- GeoJSON 可以先按请求读取；
- 若增加轨迹缓存，应设置最大数量或最大内存；
- 不要把 576 条完整轨迹一次性加载进 JVM；
- 统计接口先复用内存活动摘要；
- 使用只读、不可变集合，避免并发请求修改共享数据。

在没有测量之前不要引入 Redis。单用户本地应用的瓶颈更可能是大 GeoJSON 传输和前端绘图，而不是活动摘要查询。

---

## 13. 何时引入数据库

满足以下任一需求时，再考虑数据库：

- 页面需要编辑标签、备注、装备和训练感受；
- 多个用户同时使用；
- 需要账户、权限和私有数据隔离；
- 查询组合显著增加；
- 需要增量写入、事务和审计；
- 需要空间索引、路线相似度或复杂空间查询。

演进顺序建议：

```text
JSON/GeoJSON
  → SQLite（单机、结构化写入）
  → PostgreSQL + PostGIS（多用户与空间查询）
```

届时 Repository 接口可以保持不变，只替换基础设施实现。这正是现在定义 Repository 边界的价值。

---

## 14. 暂时不要做的事情

学习过程中容易出现“工具很多，所以全部加上”的情况。第一版不建议：

- 把 Python FIT 解析器强行全部翻译成 Java；
- 同时引入数据库、登录、JWT、Redis、消息队列和微服务；
- 为单用户项目拆成多个 Spring Boot 服务；
- 在 Controller 中直接实现所有统计；
- 把真实 FIT 和 GeoJSON放入 `src/test/resources`；
- 为减少几行代码立即引入 Lombok；
- 在不了解线程模型前改用 WebFlux；
- 直接删除 FastAPI 后端再开始开发。

一个可测试、接口兼容的单体 Spring Boot 服务，是当前最有学习价值且风险最低的目标。

---

## 15. 建议学习路线

按照项目实际需求学习，比先看完整理论更容易形成经验。

### 第一阶段：Java 基础

- 类、接口、包；
- 构造器；
- 集合与泛型；
- `record`；
- `Optional` 的适用边界；
- Stream API；
- 异常；
- `LocalDate`、`Instant`；
- `Path`、`Files`；
- JUnit 5。

练习：不使用 Spring，读取一个简化的 `activities.json` 并完成日期过滤。

### 第二阶段：Spring 核心

- IoC / 依赖注入；
- Bean；
- 构造器注入；
- 自动配置；
- 配置属性；
- Spring Boot 启动过程。

练习：完成 `/api/health`。

### 第三阶段：Spring MVC

- REST Controller；
- Path Variable；
- Request Parameter；
- DTO；
- Validation；
- 状态码；
- 全局异常处理。

练习：完成活动列表和活动详情。

### 第四阶段：工程化

- Maven 生命周期；
- 分层和包结构；
- 单元测试；
- MockMvc；
- Profile 与环境变量；
- 日志；
- Actuator；
- CI 构建。

练习：完成所有 P0 API，并与 FastAPI 做契约对比。

### 第五阶段：数据持久化（未来）

- SQL；
- JDBC / Spring Data JPA；
- 数据库迁移工具 Flyway；
- PostgreSQL；
- PostGIS；
- 事务和索引。

这部分应等 JSON 版 Spring Boot 后端稳定后再开始。

---

## 16. Git 与工程流程建议

建议为迁移创建独立分支：

```powershell
git switch -c feature/springboot-backend
```

推荐按小步骤提交：

```text
chore: scaffold Spring Boot backend
feat: add data root configuration
feat: load activity archive from JSON
feat: implement activity query endpoints
test: add activity API contract tests
feat: implement statistics endpoints
chore: switch development proxy to Spring Boot
docs: update backend development guide
```

每个提交应：

1. 能够编译；
2. 相关测试通过；
3. 不包含真实运动数据；
4. 不包含本机绝对路径；
5. 不同时混入无关前端改动。

建议将下列内容加入忽略规则：

```gitignore
backend-springboot/target/
backend-springboot/.idea/
backend-springboot/*.iml
```

保留并提交：

```text
backend-springboot/mvnw
backend-springboot/mvnw.cmd
backend-springboot/.mvn/wrapper/
backend-springboot/pom.xml
```

---

## 17. 第一阶段验收标准

Spring Boot 版本达到以下状态，即可认为第一次迁移成功：

- [ ] JDK 21 安装并验证；
- [ ] Maven Wrapper 可以测试、启动和打包；
- [ ] 数据目录由环境变量或配置指定；
- [ ] 不修改原始 FIT；
- [ ] 可以加载活动、日历和质量报告；
- [ ] 全部 P0 API 已实现；
- [ ] JSON 字段名与现有前端兼容；
- [ ] 错误响应格式统一；
- [ ] 关键 Service 有单元测试；
- [ ] Controller 有 MockMvc 测试；
- [ ] 使用脱敏测试数据；
- [ ] Vue 前端切到 `8080` 后首页、活动详情和轨迹正常；
- [ ] FastAPI 仍可随时作为对照启动；
- [ ] Git 中没有真实轨迹、运动档案或个人绝对路径。

---

## 18. 最适合本项目的最终形态

```text
webgis_for_running/
├─ backend/                    # Python ETL / FIT / GIS
│  ├─ app/
│  └─ scripts/
├─ backend-springboot/         # Java 在线查询 API
│  ├─ src/
│  ├─ pom.xml
│  └─ mvnw.cmd
├─ frontend/                   # Vue 3 WebGIS
├─ data/                       # 本地私有数据，不进入 Git
└─ docs/
```

职责划分：

| 模块 | 主要职责 |
| --- | --- |
| Python | FIT 解析、数据清洗、GIS 运算、派生文件生成 |
| Spring Boot | 数据加载、筛选、统计、校验、缓存、REST API |
| Vue | 页面交互、地图、图表、主题和浏览器本地设置 |

这种结构既符合本项目的数据特点，也能让你真正练习 Spring Boot 中最常见的工程能力：分层、配置、依赖注入、REST API、异常处理、测试、构建和部署，而不是把时间消耗在 Java 生态中重新寻找不如 Python 成熟的 FIT/GIS 处理替代品。

---

## 19. 下一次实际操作建议

下一次开始编码时，只完成以下小目标：

1. 安装并验证 JDK 21；
2. 用 Spring Initializr 创建 `backend-springboot`；
3. 运行 Initializr 自带测试；
4. 添加 `/api/health`；
5. 添加 `running.data-root` 配置；
6. 为这两个功能编写测试；
7. 暂停并检查工程结构。

不要在第一次操作中直接迁移十个接口。先把创建、运行、配置、测试这条最小工程闭环走通，再开始读取真实派生数据。
