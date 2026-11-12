# 亲手把 Spring Boot 后端容器化：从创建文件到接入现有 Vue3/Nginx

> 编写日期：2026-11-06。适用当前项目、macOS 的 zsh、Docker Desktop、Apple Silicon。
>
> **本次只创建这一份 Markdown。文中的 Dockerfile、Compose、环境文件和目录，都由你按步骤手动创建。作者没有替你构建镜像、启动容器、修改 Java 源码或改动原有 Vue3/FastAPI 配置。**
>
> 已核对源码与配置，并静态检查本文命令及 Compose 配置；本文的 Java 镜像尚未实际构建、运行。每节“预期结果”是你操作时的验收标准，不表示已经替你实测成功。

本文可保留在当前下载位置，也可自行移动到下面的项目路径。所有操作都明确写了执行目录，不依赖 Markdown 放在哪里：

```text
/Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api/DOCKER_CONTAINERIZATION_GUIDE.md
```

## 0. 练习路线与执行规则

先运行独立 Java 后端，再复用现有前端。首次练习做完第 1—8 节；第 9—10 节是以后的更新、回滚和数据切换。

| 环节 | 做什么 | 结果或访问入口 |
| --- | --- | --- |
| 构建 | JDK 21 + Maven 编译、测试、打包，再放入 JRE 镜像 | running-webgis-springboot:1.0 |
| 单独运行 | Java API，只读挂载演示数据 | http://127.0.0.1:18001/api/health |
| 联合运行 | Vue3/Nginx + Java API 两个容器 | http://127.0.0.1:18083 |
| 更新 | 构建新镜像，再替换容器 | 1.0 → 1.1 |

项目已有 Spring Boot 4.1.1、Java 21 编译目标、Maven Wrapper 和可执行 JAR 打包插件。Java API 查询派生 JSON/GeoJSON；Python 的 FIT 离线预处理仍按原流程管理，不需要随 Java API 一起启动。

**所有 zsh 代码块都在 Mac 宿主机的本地终端执行。** 若提示符是容器里的 `/ #`，先 exit 返回 Mac。不要复制 `%`、`#`、`>` 等终端提示符；命令中的反斜杠是续行，复制时包含完整代码块。

本教程让 Java 容器监听 **0.0.0.0:8000**，匹配已有 Nginx 的 `http://api:8000`。本地开发默认的 8080 不变，部署时用环境变量覆盖，不改 Java 源文件。

```text
独立练习：Mac 18001 → Java 容器 8000 → /data/processed
联合练习：Mac 18083 → Nginx 容器 80 → api:8000 → /data/processed
```

采用新的 Compose 项目名和入口端口，不要求关闭原 FastAPI。联合练习会另启动一份 Java API，不复用独立练习的容器；两份都只读同一份样例。联合完成后，可关闭独立练习减少资源占用。

## 1. 准备 Docker、样例和端口

**执行位置：Mac 终端。**

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api
uname -s
open -a Docker
docker version
docker compose version
pwd
```

预期 uname 返回 Darwin，Docker version 同时有 Client 和 Server；pwd 以 backend_springboot/api 结尾。后文的 `DOCKER_CONTEXT=desktop-linux` 仅为当次命令指定 Docker Desktop，不修改全局连接配置。

主线在 Docker 构建阶段使用 JDK 和 Maven，不要求 Mac 预先安装它们。Mac 的 python3 仅用于检查样例 JSON。

默认复用前端教程的约 284 KiB 演示数据：5 条合成活动、200 个建筑要素，活动与轨迹不是你的真实训练记录。检查样例：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running
python3 - <<'CHECK'
import json
from pathlib import Path
base = Path('deployment/web/sample')
for name in ['processed/activities.json', 'processed/calendar.json',
             'processed/import-report.json', 'processed/spatial-grid.json',
             'cesium-data/guangzhou-buildings.geojson']:
    p = base/name
    if not p.is_file():
        raise SystemExit(f'缺少 {p}，先准备样例，再继续。')
report = json.loads((base/'processed/import-report.json').read_text())
if report.get('readiness', {}).get('api_ready') is not True:
    raise SystemExit('样例数据尚未就绪。')
print('样例文件存在，api_ready=True')
CHECK
```

**仅当 sample 目录不存在时**，才执行原有生成器：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/web
python3 prepare_sample.py
```

sample 已存在时不要重复执行。如果目录不完整，先检查原因；该工具仅在明确加 --force 时重写自己生成过的样例，不要拿它处理真实数据目录。

检查入口端口，**执行位置：Mac 终端**：

```zsh
lsof -nP -iTCP:18001 -sTCP:LISTEN
lsof -nP -iTCP:18083 -sTCP:LISTEN
```

没有输出通常表示没有监听进程；此时 lsof 可能以非零状态退出，这是正常的。有占用时，稍后修改本教程新建 .env 中的端口，并相应修改访问网址，不要随意终止未知进程。

## 2. 明确要手动创建的文件

本文本身已提供，其他文件由你逐一创建：

```text
/Users/yhcbqc/Developer/marathon_training/webgis_for_running/
├── backend_springboot/api/
│   ├── Dockerfile                     第 3 节创建
│   ├── .dockerignore                  第 4 节创建
│   ├── compose.yaml                   第 5 节创建
│   ├── .env.example                   第 5 节创建
│   ├── .env                           从示例复制，本机配置
│   └── pom.xml、mvnw、.mvn/、src/     复用已有文件
└── deployment/springboot/
    ├── compose.yaml                   第 8 节创建
    ├── .env.example                   第 8 节创建
    └── .env                           从示例复制
```

下面 cat 命令会向指定文件写入完整内容。**同名文件已存在时先阅读比较，不要直接覆盖。** 先检查独立后端目录：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api
for f in Dockerfile .dockerignore compose.yaml .env.example .env; do
  if [[ -e "$f" ]]; then
    print -r -- "已存在，请先检查：$PWD/$f"
  fi
done
```

没有输出即可继续。

`<<'DOCKERFILE'` 是 zsh 的 here-document：直到末尾单独一行 DOCKERFILE 为止，文字原样写入文件。引号会保留 `$` 等字符，不让 zsh 提前展开。结束标记必须顶格且单独占一行。

## 3. 创建 Dockerfile：构建与运行分两个阶段

**执行位置：Mac 终端，backend_springboot/api 目录。** 完整复制：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api
cat > Dockerfile <<'DOCKERFILE'
FROM eclipse-temurin:21-jdk-jammy AS build
WORKDIR /workspace
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw
COPY src/ src/
# verify 包括编译、测试、打包；下载缓存仅供构建使用。
RUN --mount=type=cache,target=/root/.m2 ./mvnw -B -ntp clean verify

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
# curl 用于健康检查；Ubuntu 基础使用 apt-get，不使用 apk。
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 webgis \
    && useradd --uid 10001 --gid webgis --no-create-home --shell /usr/sbin/nologin webgis
COPY --from=build --chown=webgis:webgis /workspace/target/running-webgis-api-0.0.1-SNAPSHOT.jar /app/app.jar
ENV RUNNING_WEBGIS_DATA_DIR=/data/processed \
    SERVER_ADDRESS=0.0.0.0 \
    SERVER_PORT=8000
USER webgis
EXPOSE 8000
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
DOCKERFILE
cat Dockerfile
```

| 部分 | 含义 |
| --- | --- |
| 第一个 FROM | 构建环境用 JDK 21；jammy 是 Ubuntu 22.04 基础环境，没有桌面 |
| COPY .mvn、mvnw、pom.xml | 放入项目 Maven Wrapper 及构建定义 |
| COPY src | 放入 Java 源码、配置、测试与测试资源 |
| RUN ./mvnw … clean verify | 下载依赖、编译、测试并打包可执行 JAR |
| --mount=type=cache | 保留构建用 Maven 下载缓存，加快后续构建 |
| 第二个 FROM | 运行环境用 JRE，不带前一阶段完整源码、Maven 缓存和编译工具 |
| COPY --from=build | 把构建阶段生成的 JAR 复制到运行镜像，改名为 app.jar |
| ENV | 设置数据目录、监听地址与端口，保持原 Java 文件不变 |
| USER webgis | 服务用普通用户运行；挂载目录须允许它读取 |
| ENTRYPOINT | 容器启动时执行 Java；写 Dockerfile 时不会立即执行它 |

当前项目已经配置 Spring Boot Maven 插件。生成的可执行 JAR 包含应用代码、依赖及内嵌 Tomcat；JVM 由 JRE 镜像提供，processed 数据在镜像外。

这里精确指定 JAR 文件名，避免误选其他归档。以后改 pom.xml 中的 artifactId/version 时，同步修改 COPY 的来源路径。Docker 标签 1.0 与 Maven 版本 0.0.1-SNAPSHOT 是两套编号，不要求相同。

这份 Dockerfile 使用 Docker Desktop 默认的 BuildKit。不要改成用现有 start_development_springboot.command 启动容器：那是 Mac 的开发流程，会安排前端和本机环境，且把开发服务限制在 127.0.0.1。本教程直接运行 Java JAR。

## 4. 创建 .dockerignore：限定构建输入

**执行位置：Mac 终端，backend_springboot/api 目录。**

```zsh
cat > .dockerignore <<'IGNORE'
**
!Dockerfile
!pom.xml
!mvnw
!.mvn/
!.mvn/**
!src/
!src/**
**/.DS_Store
IGNORE
cat .dockerignore
```

先忽略全部，再放行构建所需文件。Mac 上已有 target、IDE 文件、.env 不进入构建上下文，JAR 在构建阶段重新生成。项目根目录数 GiB 的归档不在本次构建目录中，也不会被打进镜像。

.dockerignore 管 Docker 构建输入，不等于 Git 的 .gitignore。本机 .env 不要提交；当前只写版本、端口和路径，未来凭据应单独管理。

## 5. 创建独立后端 Compose 和环境文件

**执行位置：Mac 终端，backend_springboot/api 目录。**

```zsh
cat > compose.yaml <<'YAML_API'
name: running-webgis-springboot
services:
  api:
    build:
      context: .
    image: running-webgis-springboot:${SPRING_IMAGE_TAG:-1.0}
    environment:
      RUNNING_WEBGIS_DATA_DIR: /data/processed
      SERVER_ADDRESS: 0.0.0.0
      SERVER_PORT: "8000"
    ports:
      - "127.0.0.1:${SPRING_API_PORT:-18001}:8000"
    volumes:
      - type: bind
        source: ${SPRING_DATA_DIR:-../../deployment/web/sample/processed}
        target: /data/processed
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "--show-error", "--max-time", "3", "http://127.0.0.1:8000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
YAML_API

cat > .env.example <<'ENV_API'
SPRING_IMAGE_TAG=1.0
SPRING_API_PORT=18001
SPRING_DATA_DIR=../../deployment/web/sample/processed
ENV_API

cp -n .env.example .env
cat .env
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose config
```

cp -n 不覆盖已有 .env。终端 export 的同名变量可能覆盖 .env，以 config 的结果为准。

预期 config -q 成功且无输出；普通 config 显示镜像 running-webgis-springboot:1.0、Mac 端口 18001，挂载源指向样例 processed 的绝对路径。

相对源路径按 Compose 文件所在目录解析，不按容器目录解析。create_host_path=false 会在源目录不存在时报错，避免悄悄创建空目录。

端口映射左边 18001 是 Mac 入口，右边 8000 是容器内 Java 端口。健康检查运行在容器里，所以访问 8000。

/api/health 检查 import-report 中的就绪标记。/actuator/health 属于另一种管理健康检查，不能代替数据就绪验证。

## 6. 拉取基础镜像，构建 Java 应用镜像

**执行位置：Mac 终端，backend_springboot/api 目录。每一步成功再继续。**

```zsh
DOCKER_CONTEXT=desktop-linux docker pull eclipse-temurin:21-jdk-jammy
DOCKER_CONTEXT=desktop-linux docker pull eclipse-temurin:21-jre-jammy
DOCKER_CONTEXT=desktop-linux docker compose --progress plain build api
```

第一次有多种下载：Docker Hub 拉基础镜像、Wrapper 下载 Maven、Maven 下载依赖和插件、apt 下载 curl。前一项能访问，不保证后一项也正常。

预期经历 COPY → Maven 下载/编译/测试 → BUILD SUCCESS → 复制 JAR → 镜像导出完成。测试失败先阅读错误，不要默认加 -DskipTests 掩盖。现有测试使用临时人工样本，不要求把个人归档带入构建。

-B 是 Maven 批处理模式，-ntp 隐藏下载进度。长时间没有输出时，要按日志阶段判断；不要并行重复启动相同构建或默认清空所有缓存。

构建成功后再检查：

```zsh
DOCKER_CONTEXT=desktop-linux docker image inspect running-webgis-springboot:1.0 \
  --format '系统={{.Os}} 架构={{.Architecture}} 用户={{.Config.User}}'
DOCKER_CONTEXT=desktop-linux docker run --rm --pull never \
  --entrypoint java running-webgis-springboot:1.0 -version
```

Apple Silicon 默认预期 linux/arm64，用户 webgis，Java 21。第二条仅启动临时版本检查，退出就删容器，不启动 API，也不要求挂载数据。最终镜像比单个 JAR 大，因为还包含 JRE 和基础系统。

## 7. 单独启动、检查接口与容器内容

**执行位置：Mac 终端，backend_springboot/api 目录。**

```zsh
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 240
DOCKER_CONTEXT=desktop-linux docker compose ps
DOCKER_CONTEXT=desktop-linux docker compose images
curl -fsS http://127.0.0.1:18001/api/health
curl -fsS 'http://127.0.0.1:18001/api/activities?limit=2'
curl -fsS http://127.0.0.1:18001/api/calendar
curl -fsS 'http://127.0.0.1:18001/api/stats/monthly?month=2026-11'
```

预期 api 为 healthy；健康接口 status=ok、api_ready=true。默认样例总共 5 条活动，limit=2 的 items 最多 2 项；月统计应为 5 次、18000 米。换真实数据后，数量相应变化。

| 选项 | 意思 |
| --- | --- |
| -d | 后台运行，up 返回终端后服务继续运行 |
| --no-build | 使用上一节构建的镜像 |
| --pull never | 不从仓库拉应用镜像，缺少就报错 |
| --wait | 等待运行并通过配置的健康检查 |
| --wait-timeout 240 | 启动/健康等待上限，不是 Maven 下载超时 |

检查用户、JAR 和只读挂载：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose exec api id
DOCKER_CONTEXT=desktop-linux docker compose exec api ls -lh /app
DOCKER_CONTEXT=desktop-linux docker compose exec api ls -l /data/processed
DOCKER_CONTEXT=desktop-linux docker inspect running-webgis-springboot-api-1 \
  --format '{{range .Mounts}}{{println .Source "->" .Destination "RW=" .RW}}{{end}}'
```

预期应用用户不是 root，/app 中有 app.jar，数据挂载为 RW=false。Java 源码编译打包后，运行容器中主要看到 JAR；源码仍在 Mac 的 src 目录。

当前 Java 项目没有 springdoc/Swagger 配置，18001/docs 返回 404 是预期情况。前面的 /docs 是 FastAPI 自动提供的功能，Java 服务先用业务接口验收。

失败时，在本目录检查：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose logs --tail 100 api
DOCKER_CONTEXT=desktop-linux docker compose ps -a
```

## 8. 接入已有 Vue3/Nginx：新建独立联合项目

第 7 节通过后再继续。原 Nginx 连接 api:8000，Vue 使用 /api 相对请求；本教程保持服务名和内部端口一致，不修改前端源码、Nginx 配置或原 FastAPI Compose。

### 8.1 确认前端镜像存在

**执行位置：Mac 终端。**

```zsh
DOCKER_CONTEXT=desktop-linux docker image inspect running-webgis-frontend:1.0 \
  --format '{{.Os}}/{{.Architecture}}'
```

不存在时，按原前端教程构建 web，**执行位置为 deployment/web**：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/web
DOCKER_CONTEXT=desktop-linux docker compose --progress plain build web
```

如果使用原前端教程的本机 Node 备用方法，在同一目录用 `python3 build_frontend_locally.py --tag running-webgis-frontend:1.0` 代替 build web。两条路径任选一种。这里不重新创建前端 Dockerfile。已有镜像不是 1.0 时，后面的 WEB_IMAGE_TAG 也要对应实际版本。

### 8.2 创建联合配置文件

**执行位置：Mac 终端。**

```zsh
mkdir -p /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/springboot
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/springboot
for f in compose.yaml .env.example .env; do
  if [[ -e "$f" ]]; then
    print -r -- "已存在，请先检查：$PWD/$f"
  fi
done
```

若输出同名文件，先检查，不直接覆盖。确认后，继续在 deployment/springboot 目录执行：

```zsh
cat > compose.yaml <<'YAML_WEB'
name: running-webgis-springboot-fullstack
services:
  api:
    image: running-webgis-springboot:${SPRING_IMAGE_TAG:-1.0}
    environment:
      RUNNING_WEBGIS_DATA_DIR: /data/processed
      SERVER_ADDRESS: 0.0.0.0
      SERVER_PORT: "8000"
    expose:
      - "8000"
    volumes:
      - type: bind
        source: ${SPRING_DATA_DIR:-../web/sample/processed}
        target: /data/processed
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "curl", "--fail", "--silent", "--show-error", "--max-time", "3", "http://127.0.0.1:8000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
  web:
    image: running-webgis-frontend:${WEB_IMAGE_TAG:-1.0}
    ports:
      - "127.0.0.1:${SPRING_WEB_PORT:-18083}:80"
    volumes:
      - type: bind
        source: ${SPRING_BUILDINGS_DIR:-../web/sample/cesium-data}
        target: /usr/share/nginx/html/cesium-data
        read_only: true
        bind:
          create_host_path: false
    depends_on:
      api:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1/api/health"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 60s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
YAML_WEB

cat > .env.example <<'ENV_WEB'
SPRING_IMAGE_TAG=1.0
WEB_IMAGE_TAG=1.0
SPRING_WEB_PORT=18083
SPRING_DATA_DIR=../web/sample/processed
SPRING_BUILDINGS_DIR=../web/sample/cesium-data
ENV_WEB

cp -n .env.example .env
cat .env
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose config
```

这份配置只引用已构建镜像，没有 build 字段。Java 镜像在第 6 节构建，前端镜像使用原流程。联合 API 不发布宿主机端口，web 通过本项目网络连接它；expose 用于描述内部端口，不是防火墙规则。

**这是独立完整配置，不要用 -f 与原 FastAPI Compose 合并。** 合并可能保留原 Python 健康检查或构建路径，造成错误。相同服务名在不同项目网络中分别解析，不会自动把请求发到另一套项目。

### 8.3 启动并检查页面、API、地图

**执行位置：Mac 终端，deployment/springboot 目录。**

```zsh
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 240
DOCKER_CONTEXT=desktop-linux docker compose ps
curl -fsS http://127.0.0.1:18083/api/health
curl -fsS 'http://127.0.0.1:18083/api/activities?limit=2'
curl -I http://127.0.0.1:18083/cesium/Assets/Images/cesium_credit.png
curl -I http://127.0.0.1:18083/cesium-data/guangzhou-buildings.geojson
open http://127.0.0.1:18083
```

预期 web、api 都 healthy。首页日历选择 2026 年 11 月，应显示合成活动。点击区域探索，检查轨迹和建筑；源文件有 200 个面，沿线距离筛选后显示数量可能更少。在线底图和字体需要外部网络，默认本地纯色地球不需要在线底图。

PNG 应是 image/png，GeoJSON 应可解析。缺失地图资源应 404，不能用入口 HTML 伪装成功。首页返回 200 不能代替完整功能检查。

继续在本目录核对代理：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose exec web nginx -t
DOCKER_CONTEXT=desktop-linux docker compose exec web \
  wget -q -O - http://api:8000/api/health
DOCKER_CONTEXT=desktop-linux docker compose logs --tail 80 api web
```

当前 Nginx 还会转发 /docs、/redoc、/openapi.json，但 Java 工程没有对应路由，返回 404 正常；Vue 的业务请求不依赖 Swagger 页面。

联合站点通过后，可关闭第 7 节的独立 Java 服务，减少一份进程。**执行位置：Mac 终端，明确切回独立后端目录**：

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api
DOCKER_CONTEXT=desktop-linux docker compose down
```

这只关闭 running-webgis-springboot，18083 联合项目继续运行。不要在错误目录清理。

## 9. 更新 Java 代码与镜像版本

要更新时，先完成你自己的 Java 源码修改。然后用编辑器打开独立后端配置：

```text
/Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api/.env
```

将 SPRING_IMAGE_TAG 改为 1.1，保留其他行。下面是文件内容示意，不是终端指令：

```dotenv
SPRING_IMAGE_TAG=1.1
```

**执行位置：Mac 终端，backend_springboot/api 目录。**

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend_springboot/api
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose --progress plain build api
DOCKER_CONTEXT=desktop-linux docker image inspect running-webgis-springboot:1.1 \
  --format '{{.Id}}'
```

构建成功再替换服务。仅使用独立后端时，在此目录执行第 7 节的 up 命令；使用联合站点时，把下面 .env 内的 SPRING_IMAGE_TAG 也改为 1.1：

```text
/Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/springboot/.env
```

**执行位置：Mac 终端，deployment/springboot 目录。**

```zsh
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/springboot
DOCKER_CONTEXT=desktop-linux docker compose config
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 240
DOCKER_CONTEXT=desktop-linux docker compose images
curl -fsS http://127.0.0.1:18083/api/health
```

预期 api 使用 1.1，web 继续原版本。仅更新 Java 不需要重建 Vue。已有 Nginx 使用 Docker DNS 重新解析后端，重建附近可能短暂 502；单副本练习不保证零停机。

流程是：修改源码 → 构建新 JAR/镜像 → 按新标签重建容器。宿主机修改 src 不会自动改变当前镜像；不要直接在运行容器里改 JAR 作为更新方式。

## 10. 回滚、数据切换与关闭

### 10.1 回滚 Java 版本

保留旧镜像时，把正在使用的 .env 内 SPRING_IMAGE_TAG 改回 1.0，然后在**对应项目目录**执行：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 240
DOCKER_CONTEXT=desktop-linux docker compose images
```

不要 build 覆盖旧 1.0，否则它不再代表原来的版本。镜像回滚不恢复数据，旧代码也必须兼容当前数据。

### 10.2 切换到真实派生数据

两个新 Compose 目录层级相同，可以把各自 .env 中的源改为：

```dotenv
SPRING_DATA_DIR=../../data/processed
```

联合站点需要完整建筑文件时，再改：

```dotenv
SPRING_BUILDINGS_DIR=../../frontend/public/cesium-data
```

数据仍留在 Mac，不复制进镜像，不需要重新构建。确认目录存在、数据就绪，且允许容器 UID 10001 读取/遍历后，在对应项目目录执行：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose config
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --force-recreate --wait --wait-timeout 240
```

先看 config 的绝对源路径，确认再 up。Java 对单文件有修改时间/大小缓存检查，但切换挂载或导入脚本替换整个目录时，重新创建容器更明确。

导入仍按原项目流程进行，导入时停止正在读取这份数据的服务。不要批量 chmod 777；个人活动由 API 读取，不挂载进 Nginx 的公开目录。

### 10.3 暂停、恢复或结束练习

暂停并保留容器，**执行位置：需要暂停的项目目录**：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose stop
```

恢复并检查健康，仍在该项目目录：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 240
```

结束练习、删除该项目的容器和网络：

```zsh
DOCKER_CONTEXT=desktop-linux docker compose down
```

down 默认保留镜像、Mac 数据和你创建的配置文件。两个新 Java 项目要分别在各自目录管理；不要运行全局 system prune 清理其他练习。

## 11. 按阶段排错

| 现象 | 检查方向 |
| --- | --- |
| FROM 元数据超时 | Docker Hub 网络，先单独 pull |
| Wrapper 下载失败 | .mvn/wrapper 中的 Maven distributionUrl 与容器网络 |
| Maven 依赖下载长时间重试 | 查看具体仓库/依赖；-ntp 隐藏进度，需要时暂去掉它观察 |
| 编译或测试失败 | 阅读 Maven 错误与测试摘要，先解决代码/依赖/测试 |
| COPY 找不到 JAR | 检查打包是否成功、pom.xml 的 artifactId/version 是否变化 |
| apt 安装 curl 失败 | Ubuntu 软件源网络，与 Maven 阶段分别定位 |
| bind source 不存在 | config 检查绝对路径，先准备数据 |
| Permission denied | 普通容器用户需要读取/遍历目录的权限 |
| Actuator 正常而业务健康失败 | 查 import-report、api_ready 与挂载目录 |
| 18001 正常，18083 是 502 | 查联合项目自己的 API、8000 端口、监听地址和日志 |
| 页面有数据但地图资源 404 | 查建筑挂载、前端镜像 /cesium/，不是 Java 编译问题 |
| /docs 是 404 | 当前 Java 项目没有 Swagger 配置，属于预期 |
| 不同网址数据不同 | 可能访问了另一套 FastAPI/Compose 项目 |
| up 找不到镜像 | 检查标签并先构建；--pull never 不替你下载或构建 |

Mac 的 Maven 缓存不会自动进入构建容器；本教程用 BuildKit 缓存挂载管理容器构建时的依赖。出现 CACHED 是正常现象，不要求每次从零下载。

查看这两个项目的容器，**执行位置：任意 Mac 终端目录**：

```zsh
DOCKER_CONTEXT=desktop-linux docker ps -a \
  --filter label=com.docker.compose.project=running-webgis-springboot
DOCKER_CONTEXT=desktop-linux docker ps -a \
  --filter label=com.docker.compose.project=running-webgis-springboot-fullstack
```

如果异常，保留执行目录、完整命令、最后约 30 行日志，以及 .env 的非敏感部分再分析。不要先清空整个 Docker 环境。

## 12. 自查与验证边界

完成后应能做到：

- 说明 Mac 源码、构建阶段 /workspace、运行阶段 /app/app.jar 的关系。
- 区分 Maven 版本号、Java 版本号和 Docker 镜像标签。
- 验证健康接口与活动查询，而不只看容器 Up。
- 检查只读挂载，理解数据不进镜像。
- 在联合站点实际检查日历、轨迹与建筑。
- 新版本构建成功再更新容器，并保留旧镜像回滚。

本文没有安排上传镜像或公开生产服务。Mac 默认构建 ARM64，迁移 AMD64 主机要使用匹配架构的镜像并单独验证。生产公开服务还需要自身的访问控制、HTTPS 和备份设计。

**本次作者只创建本文，并检查已有源码、配置、样例和本文静态语法。没有创建任何文中配套文件，没有执行 Maven、构建 Java 镜像或启动部署。** 由你完成后，按每节预期结果逐步验收。

参考：[Spring Boot 可执行归档](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)、[外部配置与环境变量](https://docs.spring.io/spring-boot/reference/features/external-config.html)、[Eclipse Temurin 官方镜像](https://hub.docker.com/_/eclipse-temurin)、[Dockerfile 指令](https://docs.docker.com/reference/dockerfile/)、[Compose 网络](https://docs.docker.com/compose/how-tos/networking/)。
