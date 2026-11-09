# 把 Running WebGIS 的 FastAPI 后端放进 Docker

> 编写与验证日期：2026-11-04。适用：你的 macOS 27、Apple Silicon、Docker Desktop，以及本项目当前的 FastAPI 后端。
>
> 练习目标：构建镜像 → 启动容器 → 查询真实数据 → 连接 Vue 前端 → 更新代码 → 更新数据 → 回滚版本。

**当前练习起点（2026-11-04 已清理）：** 我已按你的要求停止并删除验证用独立后端、联合前后端的 3 个容器、两个项目网络，以及 running-webgis-backend:1.0 和 running-webgis-frontend:1.0 应用镜像。源码、教程、数据、基础镜像和构建缓存保留，其他 Docker 练习未清理。现在需要你按第 2—5 节自行准备、配置、构建和启动；第 7 节之后的更新、导入、回滚属于后续练习。

本教程的本机后端构建、接口、挂载、重建和镜像更新/回滚机制已经验证；数据重新导入、另一台机器运行等扩展步骤没有全部实际执行，范围见第 13 节。不要把“提供完整操作步骤”理解为“所有分支都在真实生产环境测试过”。

## 0. 先明确执行位置和本教程范围

**所有终端命令均在 Mac 的“终端”或 VS Code 的本地终端执行。** 不要在提示符为 `/ #` 的 Alpine 容器内部执行 Docker 命令。若仍在容器里，先在那个 shell 输入 `exit` 返回 Mac。不确定时运行 `uname -s`，本教程主机应返回 `Darwin`。

命令中的 `\` 是续行；代码块要完整复制，提示符 `%`、`#` 不需要输入。`>` 续行提示由 shell 自动显示。

本教程中的“backend”是 FastAPI 服务，不包含 Spring Boot。数据导入仍使用项目已有的 Mac 脚本。本次已提供以下配套文件，你可以先看附录理解内容，再逐步执行命令，无需重新创建文件：

```text
/Users/yhcbqc/Developer/marathon_training/webgis_for_running/
├── backend/
│   ├── app/                    原有 API 代码
│   ├── requirements-core.txt   原有核心依赖
│   ├── Dockerfile              新增：镜像构建步骤
│   ├── .dockerignore           新增：构建文件白名单
│   ├── compose.yaml            新增：容器运行配置
│   ├── .env.example            新增：可复制的配置示例
│   └── DOCKER_GUIDE.md         本教程
└── data/processed/             原有派生数据，在镜像外保存
```

应用路径与环境变量依据 `app/main.py`、`app/paths.py` 核对；依赖使用现有 `requirements-core.txt`。本次不安装包含 GeoPandas 等工具的完整研究依赖，因为在线查询 API 的运行路径不需要它们。保留核心清单中原有的 FIT 解析包，避免另维护一份重复清单。

## 1. 先看容器化后的关系

```text
Mac 源代码 backend/app + requirements-core.txt
                │ docker compose build
                ▼
镜像 running-webgis-backend:1.0
                │ docker compose up
                ▼
api 容器：/srv/backend/app，Uvicorn 监听 0.0.0.0:8000
       ▲                                  │
       │ 请求                             │ 只读访问
Mac 127.0.0.1:18000                 容器 /data/processed
                                          │ 绑定挂载
                              Mac 的 data/processed
```

| 对象 | 本教程的名称/路径 | 作用 |
| --- | --- | --- |
| 镜像 | `running-webgis-backend:1.0` | 代码、Python 和核心依赖的运行模板 |
| Compose 项目 | `running-webgis-backend` | 管理这一组部署资源 |
| 服务 | `api` | Compose 命令中使用的服务名 |
| 容器 | 通常为 `running-webgis-backend-api-1` | 镜像启动后的运行实例，由 Compose 命名 |
| 主机端口 | `18000` | Mac 浏览器、curl、前端代理访问入口 |
| 容器端口 | `8000` | Uvicorn 在容器内部监听 |
| 数据目录 | `/data/processed` | 容器内部的数据访问位置，不是 Mac 路径 |

这里使用的是 **bind mount（绑定挂载）**，直接复用项目已有数据目录；没有另外创建数据库，也没有把数据复制进镜像。当前 API 读取 JSON/GeoJSON，兄弟目录的训练 SQLite 不需要挂载进这个服务。

## 2. 准备 Docker 和数据

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend
uname -s
open -a Docker
docker version
docker compose version
docker context show
```

等待 Docker Desktop 引擎启动，`docker version` 应同时显示 Client 和 Server。`docker --version` 只显示命令行版本，不能证明引擎正常。后文使用单次命令的 `DOCKER_CONTEXT=desktop-linux` 前缀，明确连接这台 Mac 的 Docker Desktop；不会修改全局 context。

检查数据。以下命令只检查存在性和就绪状态，不打印活动轨迹：

**执行位置：Mac 终端。**

```bash
python3 - <<'PY'
import json
from pathlib import Path

data = Path("../data/processed")
for name in ["activities.json", "calendar.json", "import-report.json", "spatial-grid.json"]:
    path = data / name
    print(name, "存在" if path.is_file() else "缺少")
report = json.loads((data / "import-report.json").read_text())
print("api_ready =", report["readiness"]["api_ready"])
PY
```

**预期：** 四个文件存在，`api_ready = True`。如果文件缺少或就绪为 False，先按项目原有数据导入流程解决，不要通过修改健康检查来掩盖问题。你可以从项目根目录执行原有 `./import_data.sh`，其前置环境和用法见根目录 README；更新步骤见第 8 节。

## 3. 配置第一次运行的版本与端口

**执行位置：Mac 终端，工作目录仍为 backend。**

```bash
cp -n .env.example .env
cat .env
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose config
```

`cp -n` 仅在 `.env` 不存在时复制，不覆盖已有文件；已有文件时检查它是否包含下列设置。`cat` 在这里显示的是教程配置，不应把以后添加的密码复制给别人。

```dotenv
API_IMAGE_TAG=1.0
API_PORT=18000
```

`.env` 给 Compose 提供 `${...}` 插值。容器真正收到的数据路径变量由 `compose.yaml` 的 `environment` 设置为 `/data/processed`。Mac 数据源路径可用 `RUNNING_WEBGIS_HOST_DATA_DIR` 自定义，默认相对 backend 为 `../data/processed`。

`config -q` 成功时不输出内容；不等于容器已运行。普通 `config` 可以确认实际镜像名、发布端口和挂载源路径。如果 Mac shell 中已 export 同名变量，它可能覆盖 `.env`；用 `printenv API_IMAGE_TAG`、`printenv API_PORT` 检查，按实际需要处理，再看 config。

## 4. 下载基础镜像并构建自己的镜像

**执行位置：Mac 终端。先执行第一条，成功后再执行第二条。**

```bash
DOCKER_CONTEXT=desktop-linux docker pull python:3.13-alpine
DOCKER_CONTEXT=desktop-linux docker compose --progress plain build api
```

第一条从 Docker Hub 下载 Python 基础镜像；第二条按 Dockerfile 安装依赖、复制 app 源代码，生成 `running-webgis-backend:1.0`。基础镜像选用与你此前练习一致的 Python 3.13 Alpine；本项目核心依赖能否安装，以末尾实际验证记录为准。

构建中 `RUN pip install ...` 发生在镜像内部，不会安装到 Mac 的 Python 环境。第一次需要访问 Docker Hub 和 PyPI；后续只改 app 代码时，依赖安装层通常可以使用缓存。

**预期：** 最后出现镜像 Built/导出成功的信息。确认镜像：

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker image inspect running-webgis-backend:1.0 \
  --format '{{.Os}}/{{.Architecture}} User={{.Config.User}}'
```

预期为 `linux/arm64`，用户 `webgis`。Dockerfile 的 `USER` 让应用以普通用户运行；挂载的数据也必须对这个用户可读。镜像名称中的 1.0 是我们定义的应用版本，与 Python 的版本不同。

如果 `load metadata for python:3.13-alpine` 超时，仍在下载阶段；先单独重试 pull。若持续失败，检查 Docker Desktop 的网络与代理设置。增加 `--wait-timeout` 无法延长镜像下载超时，也不需要重新复制源代码。[Docker Desktop 代理设置](https://docs.docker.com/desktop/settings-and-maintenance/settings/#proxies)

## 5. 启动并检查健康状态

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 180
DOCKER_CONTEXT=desktop-linux docker compose ps
DOCKER_CONTEXT=desktop-linux docker compose images
```

| 选项 | 含义 |
| --- | --- |
| `-d` | 后台运行，终端关闭后服务仍由 Docker 管理 |
| `--no-build` | 使用上一节构建好的镜像，不在启动时再构建 |
| `--pull never` | 只使用本地镜像；缺少镜像就报错，避免启动阶段又访问仓库 |
| `--wait` | 等待服务运行并通过已配置的健康检查 |
| `--wait-timeout 180` | 启动/健康等待上限，不包含解决下载网络问题的能力 |

**预期：** 服务 api 显示 healthy，端口类似 `127.0.0.1:18000->8000/tcp`。健康检查在容器里使用 Python 请求 `http://127.0.0.1:8000/api/health`，不依赖容器装 curl。

这里的业务健康检查会读取导入报告，报告不就绪时返回 503；“容器 Up”只说明进程在运行，healthy 才表示这项检查通过。它不能代替所有业务接口的完整验收。健康失败本身不会自动触发普通 Docker 重启策略。

## 6. 从 Mac 查询真实接口

**执行位置：Mac 终端。默认端口为 18000；如修改 .env，也要修改 URL。**

```bash
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS 'http://127.0.0.1:18000/api/activities?limit=1'
open http://127.0.0.1:18000/docs
```

预期健康接口返回 status 为 ok，活动接口返回 JSON，浏览器出现 FastAPI 文档。`/docs` 页面的交互界面需要加载其前端资源；如果 API 正常但文档界面不完整，检查浏览器外部资源请求，不要据此直接判定后端未启动。

查看日志与运行身份：

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose logs --tail 50 api
DOCKER_CONTEXT=desktop-linux docker compose exec api id
DOCKER_CONTEXT=desktop-linux docker compose exec api printenv RUNNING_WEBGIS_DATA_DIR
DOCKER_CONTEXT=desktop-linux docker compose exec api ls /data/processed
```

这些 docker exec 命令仍然在 Mac 发起，id、printenv、ls 才在容器内部执行；它们不会把你留在交互式 shell。预期用户为 webgis，数据路径为 `/data/processed`。

## 7. 让 Vue 前端使用这个容器后端

前端当前的 Vite 配置支持 `VITE_API_PROXY_TARGET`。打开另一个 **Mac 终端**，只启动前端，避免根目录开发启动器又启动一份本机 FastAPI：

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/frontend
VITE_API_PROXY_TARGET=http://127.0.0.1:18000 npm run dev
```

前提是已经按原项目安装前端依赖。如果没有，先根据根目录 README 完成安装。打开 Vite 实际输出的本地网址，检查活动列表、日历和地图。浏览器请求 `/api/...`，Vite 在 Mac 上把请求转给容器发布的 18000。

本教程只把后端容器化；这个 Vite 命令仍是开发模式。正式发布前端时应构建静态文件并在 Nginx 等入口配置 `/api` 代理，不能把 Vite 开发代理当作正式部署配置。

## 8. 以后更新：先判断改的是哪一层

| 变化 | 是否重新构建镜像 | 是否重新创建容器 |
| --- | --- | --- |
| 修改 app 下的代码 | 是 | 是 |
| 修改 requirements-core.txt | 是 | 是 |
| 修改 Dockerfile | 是 | 是 |
| 修改端口、挂载路径等 Compose 配置 | 否 | 用 up 应用变化 |
| 更新 data/processed 数据 | 否 | 建议强制重新创建，刷新缓存并重新挂载目录 |
| 临时停止后继续用相同版本 | 否 | 不需要，start 原容器即可 |

### 8.1 发布代码或依赖的新版本

先完成你实际需要的代码修改和项目检查。下面示范从 1.0 升到 1.1，旧的 1.0 镜像保留用于回滚。不要用一个固定标签反复覆盖所有历史版本。

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend
cp -p .env .env.before-update
nano .env
```

在编辑器中把 `API_IMAGE_TAG=1.0` 改成 `API_IMAGE_TAG=1.1`，其他行保留。nano 中按 Ctrl+O、回车保存，Ctrl+X 退出。`.env.before-update` 只保留这次编辑前的配置，下次执行同名复制会覆盖它；长期版本请自行按日期保存。

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose config
DOCKER_CONTEXT=desktop-linux docker compose build api
```

确认 config 中镜像标签为 1.1，且 build 成功后，再进行切换：

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 180
DOCKER_CONTEXT=desktop-linux docker compose images
curl -fsS http://127.0.0.1:18000/api/health
```

新镜像构建期间旧容器可以继续运行。up 切换时，单副本服务可能短暂中断；这不是零停机部署方案。构建失败时先修复 build，不要继续 up。若新容器启动失败，先看日志，再按第 9 节回滚。

**仅执行 restart 不会把 Mac 新代码复制进镜像。** 本方案在构建时 COPY 代码，运行时不挂载 app 目录，因此必须 build 新镜像并创建新容器。

### 8.2 更新 FIT 派生数据

后端多处使用进程内缓存。原导入脚本还可能替换整个 processed 目录，因此只 restart 原容器可能仍挂着旧目录；这里统一用 force-recreate 重新建立挂载。

下面的导入会更新项目数据，只在你已经准备好新的 FIT 导出、需要更新数据时执行；它不是首次运行必需步骤。先停止 API，避免导入期间读取到不同批次的数据。

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend
DOCKER_CONTEXT=desktop-linux docker compose stop api

cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running
./import_data.sh
```

只有导入成功、质量检查通过之后才继续；若失败，查看导入报告和项目原有备份，不能靠启动容器修复数据。

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --force-recreate --wait --wait-timeout 180
curl -fsS http://127.0.0.1:18000/api/health
```

这次无需 build，因为镜像中的程序没有变化。恢复服务后，再查活动数量、日期范围和一条轨迹，确认真的使用了新数据。

## 9. 回滚到上一版

假设 1.0 镜像仍保留，回滚代码时编辑 `.env`，将 `API_IMAGE_TAG` 改回 `1.0`；若你使用了其他版本号，以实际保存的版本为准。然后执行：

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker image inspect running-webgis-backend:1.0 \
  --format '{{.Id}}'
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 180
curl -fsS http://127.0.0.1:18000/api/health
```

确认旧镜像存在后才执行 up。**镜像回滚不等于数据回滚。** 如果数据格式也变了，应选择对应的、已确认可用的数据备份，在 `.env` 中将 `RUNNING_WEBGIS_HOST_DATA_DIR` 设置为那个备份目录的真实绝对路径，再使用第 8.2 节的 force-recreate 命令。不要在不清楚备份内容时直接覆盖当前数据。

## 10. 日常停止、恢复与清理

**执行位置：Mac 终端，工作目录为 backend。根据目标选择一条，不要全部连着执行。**

```bash
# 暂停，保留原容器。
DOCKER_CONTEXT=desktop-linux docker compose stop api
```

**执行位置：Mac 终端。**

```bash
# 未修改配置时，恢复原容器。
DOCKER_CONTEXT=desktop-linux docker compose start api
```

**执行位置：Mac 终端。**

```bash
# 停止并删除本项目容器、默认网络；保留镜像和 Mac 数据。
DOCKER_CONTEXT=desktop-linux docker compose down
```

down 不会删除 Mac 上绑定挂载的 processed 文件。下次按第 5 节 up 即可。`restart: unless-stopped` 也不能让服务在 Docker Desktop 尚未启动时运行；先确保引擎可用。

确认不再需要某个旧版本、且没有容器引用它时，才按完整名称删除对应镜像。保留最近可回滚版本，不要求执行全局 prune。

## 11. 排错表

| 现象 | 应从哪里检查 |
| --- | --- |
| `/ #` 下出现 docker not found | 执行位置错了，exit 返回 Mac |
| Cannot connect to Docker daemon | 启动 Desktop，等 docker version 出现 Server |
| default 构建器连接 /var/run/docker.sock 失败 | 使用本教程 DOCKER_CONTEXT=desktop-linux 前缀，让构建子进程继承正确连接 |
| FROM python 拉取超时 / EOF | 单独 pull，检查 Docker Desktop 网络、代理；和 app.py 逻辑无关 |
| pip install 报错 | 已进入依赖安装层；检查错误是下载超时还是依赖解析/编译失败 |
| bind source path 不存在 | 看 compose config 中的 source；create_host_path=false 会让拼错路径直接报错 |
| Permission denied 读取数据 | Mac 目录和文件必须允许容器普通用户读取/遍历；先检查实际权限，不要批量改成 777 |
| unhealthy / HTTP 503 | 查看 logs、import-report.json 中的 api_ready，确认读取的是所选数据目录 |
| 404 | 健康地址是 /api/health，不是 /health |
| 18000 被占用 | 用 lsof 查询；编辑 .env 中 API_PORT 后 up 应用，curl 和前端代理也相应更改 |
| 修改代码后看不到变化 | 确认新版本 build 完成，再 up；exec/restart 不会重新 COPY 代码 |
| 数据目录已替换但仍读旧值 | 使用 force-recreate 刷新绑定挂载和进程缓存 |
| 容器中运行正常，Mac 访问失败 | 确认 127.0.0.1:主机端口映射、Uvicorn 监听 0.0.0.0:8000 |

按顺序检查：

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/backend
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose ps -a
DOCKER_CONTEXT=desktop-linux docker compose logs --tail 80 api
lsof -nP -iTCP:18000 -sTCP:LISTEN
curl -i --max-time 10 http://127.0.0.1:18000/api/health
```

## 12. 学习方案与正式服务器的边界

默认只发布到 Mac 的 127.0.0.1，适合本地学习和前端联调。以后放到正式服务器时，需要单独设计 HTTPS 入口、访问控制、备份和日志管理；这是你的个人运动/GPS 数据，当前 API 的 GET 只读特性不代表别人无权读取。不要直接把本方案端口绑定到公网作为完成上线。

Mac 默认构建 ARM64 镜像。若服务器是 AMD64，应在对应架构环境构建/验证，或制作多平台镜像。镜像提供运行依赖，不包含 Mac Desktop 或独立 Linux 内核。

本教程通过顶层 requirements 固定了直接依赖，但未锁定全部间接依赖，基础标签也会更新。严格复现某次发布，需要同时保存镜像 digest、依赖锁文件、代码版本、运行配置和匹配的数据版本。

主要依据：[FastAPI 官方容器部署](https://fastapi.tiangolo.com/deployment/docker/)、[Docker Compose 部署说明](https://docs.docker.com/compose/how-tos/production/)、[绑定挂载](https://docs.docker.com/engine/storage/bind-mounts/)。这些页面解释通用规则，本教程里的路径、健康接口、缓存行为依据当前项目代码核对。

## 13. 本次实际验证记录

以下是 2026-11-04 清理前完成的历史验证。随后已按你的要求删除验证容器、网络和应用镜像。现在应先按正文构建、启动，再访问 http://127.0.0.1:18000/api/health 和 http://127.0.0.1:18000/docs。

| 检查 | 实测结果 |
| --- | --- |
| Docker 环境 | Engine 29.9.2，Compose v5.6.1，Linux ARM64 服务端 |
| 镜像构建 | running-webgis-backend:1.0 成功，Python 3.13 Alpine，现有核心清单安装成功 |
| 应用启动 | api 容器 healthy，Mac 仅监听 127.0.0.1:18000 |
| 真实数据接口 | /api/health、活动查询、日历、一个有 GPS 的活动轨迹均返回 HTTP 200 |
| 文档端点 | /docs 返回 HTML 200；未进行浏览器交互界面的视觉验证 |
| 挂载和用户 | /data/processed 为 bind，实际 RW=false；运行 UID 非 0 |
| 代码与数据分离 | 无挂载启动镜像检查：app/main.py 存在，/data/processed 不在镜像中 |
| 强制重建 | 容器 ID 更换，重新挂载数据后健康检查通过 |
| 更新与回滚演练 | 构建带验证 LABEL 的临时版本，切换成功，再回滚到 1.0；验证镜像已删除 |
| 数据完整性 | 四个主要派生 JSON 文件验证前后的 SHA256 相同 |
| 文档命令 | 19 个 bash 代码块通过本机 zsh -n 语法检查 |

更新演练验证的是镜像切换、容器重建和回滚机制，没有为了演示修改业务代码。没有执行 FIT 数据导入，没有修改原始 FIT 或训练 SQLite，也没有运行 Vue 浏览器联调；这些步骤由你在需要更新时按正文进行。当前 API 的源代码保持原样，新增的文件仅为本教程及四个容器化配套文件。


## 附录：配套文件的完整内容与说明

### Dockerfile

FROM 选择 Python；WORKDIR 设置工作目录；COPY 在构建时复制文件；RUN 构建时安装依赖；USER 设置运行用户；CMD 在启动容器时执行。EXPOSE 只记录端口，ports 才真正发布端口。CMD 中 host=0.0.0.0 允许 Docker 转发请求进入，Mac 的发布地址仍限制为 127.0.0.1。

```dockerfile
FROM python:3.13-alpine

WORKDIR /srv/backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_WEBGIS_DATA_DIR=/data/processed

# 先安装固定的核心依赖，修改应用代码时可以复用依赖安装层。
COPY requirements-core.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt \
    && addgroup -S webgis \
    && adduser -S -G webgis webgis

# 只打包 API 源代码，运行数据通过 Compose 单独挂载。
COPY --chown=webgis:webgis app ./app
USER webgis
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### compose.yaml

build 指定构建上下文为 backend；image 指定应用版本；ports 为主机地址:主机端口:容器端口；source 是 Mac 的数据目录，target 是容器访问位置，read_only=true 只允许容器读取。create_host_path=false 避免把拼错的源目录自动创建为空目录。healthcheck 检查业务就绪；restart 处理主进程退出，不处理 unhealthy 本身。

```yaml
name: running-webgis-backend

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: running-webgis-backend:${API_IMAGE_TAG:-1.0}
    ports:
      - "127.0.0.1:${API_PORT:-18000}:8000"
    environment:
      RUNNING_WEBGIS_DATA_DIR: /data/processed
    volumes:
      - type: bind
        source: ${RUNNING_WEBGIS_HOST_DATA_DIR:-../data/processed}
        target: /data/processed
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

### .dockerignore

采用白名单，仅将 app、requirements-core.txt 和构建文件纳入上下文，排除 Python 缓存。

```text
**
!Dockerfile
!requirements-core.txt
!app/
!app/**
**/__pycache__
**/*.py[cod]
```

### .env.example

首次复制为 .env 后由 Compose 读取；版本、端口及自定义数据目录均可在这里调整。

```dotenv
# 镜像版本。发布新版本时修改此项，并重新构建、创建容器。
API_IMAGE_TAG=1.0
# Mac 发布端口；容器内部始终使用 8000。
API_PORT=18000
# 默认数据目录为 backend 的兄弟目录 data/processed。
# 自定义时取消注释，并填写 Mac 上已存在的绝对路径。
# RUNNING_WEBGIS_HOST_DATA_DIR=/absolute/path/to/processed
```

