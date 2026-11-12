# Vue3 + Nginx + FastAPI：双容器部署与静态数据迁移

> 日期：2026-11-04。适用本项目当前 Vue3/Vite/Cesium 前端、已经容器化的 FastAPI 后端、macOS Apple Silicon + Docker Desktop。
>
> 所有终端命令均在 **Mac 宿主机终端**执行；只有最后迁移到另一台 Linux 机器的步骤明确改在目标机执行。若当前提示符是 Alpine 的 `/ #`，先输入 exit 回到 Mac。

**当前练习起点（2026-11-04 已按你的要求清理）：** 验证用的联合服务、独立后端容器、对应网络和前后端 1.0 应用镜像均已删除。现在打开 18080 或 18000 不会有本教程服务响应，需要你自己构建、启动。

源码、配置、教程、真实数据和约 284 KiB 的 sample 均保留；基础镜像和构建缓存保留，因此构建时出现 CACHED 是正常现象。其他 Docker 入门练习未清理。按第 3 节开始准备，再做第 4 节构建、第 5 节启动即可；第 7—9 节是后续的数据切换、更新与迁移练习，不是首次启动前置条件。

本教程覆盖本机双容器部署的完整流程，**不代表每条扩展操作都已实测**。第 4.1 节的备用构建、本机网页/API/地图、后端重建连接、独立迁移目录启动已实测；标准 Node 多阶段构建受镜像下载影响未完成，另一台机器恢复与 AMD64 构建未实测。详细记录在第 11 节。配套文件已经放入项目，不必从附录再复制一遍。

## 1. FastAPI 容器到底要不要改？

已检查现有后端：Dockerfile 启动 Uvicorn 时监听 `0.0.0.0:8000`，应用支持 `RUNNING_WEBGIS_DATA_DIR`，健康接口是 `/api/health`。这些都适合接入 Nginx，**无需修改 app 业务代码或后端 Dockerfile**。

需要调整的是联合部署时的运行配置：

| 内容 | 原后端单独练习 | 本教程联合部署 |
| --- | --- | --- |
| Compose 项目名 | running-webgis-backend | running-webgis-fullstack |
| 后端发布到 Mac 的端口 | 18000 → 8000 | 不发布；由同网 Nginx 访问 api:8000 |
| 后端数据 | 完整派生目录 | 默认使用少量合成演示数据 |
| 前端入口 | Mac 上的 Vite 开发服务 | Nginx 前端容器，127.0.0.1:18080 |
| CORS | 允许原开发网址 | 浏览器通过同源 /api 访问，不需要为本方案修改 CORS |

原来的 backend/compose.yaml 保留，其验证容器已清理。你以后分别运行两套教程时，两个 Compose 项目各有网络与容器；本教程网页默认访问演示 API，独立后端教程则在 18000 提供完整数据 API。联合部署不要求你先启动独立后端；其所需 API 会在第 5 节一起启动。

## 2. 这次新增了哪些文件

```text
项目根目录 /Users/yhcbqc/Developer/marathon_training/webgis_for_running
├── frontend/
│   ├── Dockerfile                       Node 构建 + Nginx 运行
│   ├── .dockerignore                    只发送构建需要的源文件
│   ├── nginx/default.conf               网页、API 代理与静态文件规则
│   └── DOCKER_NGINX_MIGRATION_GUIDE.md   本教程
├── backend/                            沿用前一步的 Dockerfile
└── deployment/web/
    ├── compose.yaml                    本地构建与运行
    ├── compose.runtime.yaml            迁移后只加载镜像运行
    ├── .env.example                    版本、入口端口和数据路径示例
    ├── .gitignore                      不提交数据、个人配置与镜像归档
    ├── prepare_sample.py               可重复生成的小型演示数据
    ├── build_frontend_locally.py       本机 Node 编译的备用路径
    ├── Dockerfile.prebuilt             备用路径使用的 Nginx 打包配置
    └── sample/                         生成目录，已被忽略
        ├── processed/                  合成活动、日历、轨迹、就绪报告
        ├── cesium-data/                200 个建筑样例
        └── sample-manifest.json        明确记录样例来源和数量
```

本方案通过同一个 Compose 管理两个服务，避免手动创建网络和填写容器 IP：

```text
浏览器：http://127.0.0.1:18080
              │
              ▼
web 容器：Nginx，内部 80
├── /、/assets/*                  前端镜像内的 dist 内容
├── /cesium/*                     镜像内 Cesium Worker/图片/控件资源
├── /cesium-data/*                挂载的小型建筑数据
└── /api/*、/docs、/openapi.json   转发至 http://api:8000
                                            │
                                            ▼
                                  api 容器：FastAPI
                                            │ 只读挂载
                                  sample/processed 数据
```

Vue、Cesium 等 JavaScript 下载到浏览器后执行。前端容器负责发送文件；Node 只在镜像构建阶段编译项目，最终 Nginx 镜像不包含整个 Node 构建环境。

所以这里“前端容器”内部就运行 Nginx，不需要再加一个只运行 Vue 的容器。规模扩大后，团队可以再加统一入口代理，管理多个站点、HTTPS 等；本练习的两个容器已经能组成一个完整站点。

## 3. 准备 Docker 和小型数据

**执行位置：Mac 终端。**

```bash
cd /Users/yhcbqc/Developer/marathon_training/webgis_for_running/deployment/web
open -a Docker
docker version
docker compose version
```

等 version 同时出现 Client、Server。后文 `DOCKER_CONTEXT=desktop-linux` 只对该次命令指定本机 Desktop 连接，也能让构建子进程继承正确连接。

本次已生成 sample。若从新检出的项目首次开始、sample 不存在，执行：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
python3 prepare_sample.py
```

若 sample 已存在，脚本会报错并保留目录；不要把它误认为 Docker 故障。只有确实想重新生成本工具的样例时，才在停止相关容器后使用 `python3 prepare_sample.py --force`。

脚本只读取项目现有广州建筑文件，从附近选取 200 个要素；5 条跑步活动、圆形轨迹和心率等数值全部合成，日期为 2026-11-01 至 2026-11-05。合成轨迹只是渲染样例，距离等数值不代表真实地理测量或训练事实。没有提取你的个人 FIT 或 GPS 轨迹，报告中的 api_ready=true 只表示演示数据按 API 所需结构准备好。

建筑从你项目已有文件抽样，`public` 是前端静态目录名称，不代表本工具确认了数据的对外发布授权。

当前样例约 284 KiB；完整活动归档的数 GiB 内容不参与前端构建。查看来源说明：

**执行位置：Mac 终端。**

```bash
cat sample/sample-manifest.json
du -sh sample
cp -n .env.example .env
DOCKER_CONTEXT=desktop-linux docker compose config -q
DOCKER_CONTEXT=desktop-linux docker compose config
```

`.env` 不存在时 cp -n 才复制；已有文件则保留。初次应使用示例中的 1.0 镜像版本、18080 端口和两条 sample 路径。终端里 export 的同名变量可能覆盖 .env，以 config 的实际结果为准。

相对路径由这份 Compose 文件所在目录解析，不是由容器内目录解析。create_host_path=false 会在路径拼错、目录不存在时直接报错，不悄悄创建一个空文件夹。

## 4. 构建两个镜像

先拉基础镜像，再构建。每一步成功后再继续；第一轮有依赖下载，会比后续构建慢。

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker pull node:24-alpine
DOCKER_CONTEXT=desktop-linux docker pull nginx:stable-alpine
DOCKER_CONTEXT=desktop-linux docker pull python:3.13-alpine
DOCKER_CONTEXT=desktop-linux docker compose --progress plain build api web
```

虽然验证用应用镜像已删除，之前的构建层通常仍能复用缓存。前端经历 npm ci → npm run build → 将 dist 复制进 Nginx；COPY 进镜像的源文件由 frontend/.dockerignore 白名单决定。

建筑 GeoJSON 被排除出构建上下文，因此 dist 不会自带这份大数据。它在运行时挂载至 `/usr/share/nginx/html/cesium-data`，浏览器原有 `/cesium-data/guangzhou-buildings.geojson` 请求保持可用。Cesium 的程序资源仍由现有 Vite 插件构建到 `/cesium/`。

**预期：** running-webgis-frontend:1.0 和 running-webgis-backend:1.0 构建成功。镜像不包含个人原始数据，也不需要在运行环境安装 Node/npm。

遇到 FROM 元数据超时，先单独 pull；npm ci 的下载失败属于另一阶段，应看 npm 的错误。不要用 --no-cache 作为网络故障的默认修复，它通常增加重复下载。

### 4.1 本次已验证的备用方法：本机 Node 编译，再打包 Nginx

本次 Docker Hub 的 node:24-alpine 下载一直未完成，因此**没有完成标准多阶段构建的实际运行验证**。本机已有 Node v24.21.0、npm 11.19.0，采用下面备用方法成功生成前端运行镜像。两种方法任选一种，成功后都接第 5 节，不必各做一次。

先确认本机开发依赖，再运行：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
node --version
npm --version
DOCKER_CONTEXT=desktop-linux docker compose build api
python3 build_frontend_locally.py --tag running-webgis-frontend:1.0
```

脚本每次按 package-lock.json 执行 npm ci，再执行 TypeScript 检查与 Vite 构建；只在临时目录里删除构建产物中的 cesium-data，并将剩余文件和 Nginx 配置打包到镜像。它不改你现有的 frontend/dist 或真实数据，最终镜像仍只需 Nginx 运行。npm ci 会重建 frontend/node_modules，属于依赖安装步骤；如果 npm 下载也失败，仍要先处理对应网络问题。

此路径仍需要 nginx:stable-alpine 镜像；它不是离线首次安装方案。清理后这份基础镜像仍保留在本机缓存。构建日志中“大于 500 kB 的 chunk”等警告不等于构建失败，最终应看到成功生成镜像。

以后用这条路径构建 1.1 版本，要把参数改为 `--tag running-webgis-frontend:1.1`，并让 .env 的 WEB_IMAGE_TAG 与它一致。不要写成新的版本号却仍构建默认 1.0。

## 5. 启动联合部署并打开页面

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 180
DOCKER_CONTEXT=desktop-linux docker compose ps
open http://127.0.0.1:18080
```

这条 up 命令中的 d 表示后台运行；--no-build 只使用现有镜像；--pull never 不再访问仓库拉镜像；--wait 等待服务健康；--wait-timeout 180 最多等 180 秒。若提示镜像不存在，应先完成第 4 节构建，而不是跳过错误。

api 先通过业务健康检查，web 再启动。web 的健康检查会通过 Nginx 请求 `/api/health`，因此还验证了代理能连接后端；它不能代替浏览器页面、所有接口和地图渲染的完整验收。

**预期：** web、api 均 healthy；网页显示演示活动。点击区域探索可查看合成圆形轨迹和附近的部分建筑；默认样例不是全广州建筑数据库。首页日历会选到 2026 年 11 月。

在另一个 Mac 终端检查同一个网站入口：

**执行位置：Mac 终端。**

```bash
curl -fsS http://127.0.0.1:18080/api/health
curl -fsS 'http://127.0.0.1:18080/api/activities?limit=1'
curl -I http://127.0.0.1:18080/cesium/Assets/Images/cesium_credit.png
curl -I http://127.0.0.1:18080/cesium-data/guangzhou-buildings.geojson
open http://127.0.0.1:18080/docs
```

预期 API 返回 JSON，图片是 image/png，GeoJSON 可读取。文档页及底图/字体可能需要外部网络，见第 10 节。缺失地图文件应返回 404；如果返回 200 + text/html，不能认为资源可用。

## 6. Nginx 与 API 连接时容易混淆的地方

| 配置 | 为什么这样写 |
| --- | --- |
| api 监听 0.0.0.0:8000 | 让同网络中的其他容器可以连接 |
| api 不配置 ports | 后端只通过容器网络供 web 使用；expose 说明端口，不是防火墙规则 |
| Nginx 连接 api:8000 | api 是同一 Compose 网络内的服务名；localhost 会指向 Nginx 自己 |
| 浏览器请求 /api/... | 浏览器访问 18080 上的同源入口，不需要认识 Docker 内部服务名 |
| 保留完整请求 URI | 后端路由本来带 /api，不能把前缀删掉；查询参数也要保留 |
| Docker DNS resolver | 后端重建后 IP 可能变化，Nginx 可重新解析 api，避免一直记住旧 IP |
| /cesium 和 /cesium-data 用 try_files =404 | 图片或 Worker 缺失时返回真实错误，避免用入口 HTML 伪装成功 |
| /assets 长缓存，HTML/地图数据重新验证 | 哈希资源和固定名称数据采用不同缓存规则，降低更新后混用旧文件的概率 |

Nginx 配置采用变量形式的 `proxy_pass $api_upstream$request_uri`；$request_uri 包含原路径和查询串。不要把本教程这行改成带另一段 URI 的写法后还假设效果相同。[Nginx proxy_pass 规则](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)

## 7. 切换到完整数据，或替换静态建筑样例

项目中的“静态文件”需要按用途理解：

| 文件 | 运行时在哪里 | 更新或迁移方式 |
| --- | --- | --- |
| Vue 编译后的 HTML、JS、CSS | 前端镜像内 | 重新构建并切换前端镜像 |
| Cesium Worker、图片、Widgets 等程序资源 | 前端镜像内 /cesium/ | 随前端镜像迁移 |
| 建筑 GeoJSON | 宿主机目录，挂载到 Nginx | 独立复制数据目录，保持文件名和 URL |
| processed 活动 JSON、轨迹 | 宿主机目录，挂载到 API | 独立复制 processed 目录，重建 API 刷新缓存 |
| 原始 FIT、历史归档 | 不属于网页运行必需文件 | 保留独立备份，不打进这次演示运行包 |

只要目录结构和 URL 保持一致，建筑数据不需要因为容器化而改写内容。先完成小样例验证，再考虑完整数据。编辑 deployment/web/.env：

```dotenv
WEBGIS_DATA_DIR=../../data/processed
WEBGIS_BUILDINGS_DIR=../../frontend/public/cesium-data
```

这是配置文件内容，不能当终端命令整块执行。两个路径分别控制后端数据和前端建筑数据，可分别切换；修改其中一项不必修改另一项。

目录必须存在且容器可读。完整数据仍留在 Mac 目录中，不会因此被复制进前端或后端镜像。切换后：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose config
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --force-recreate --wait --wait-timeout 180
curl -fsS http://127.0.0.1:18080/api/health
```

不需要重新构建镜像。force-recreate 刷新挂载和 FastAPI 的进程内缓存，尤其适用于导入脚本替换整个 processed 目录的情况。仅替换同一个建筑文件时 Nginx 通常可读取新内容，浏览器仍可能需要重新加载页面；替换整个目录时也应重新创建 web。

原始 FIT、完整活动归档不应直接放进 Nginx 的公开目录。只把需要浏览器直接下载的建筑文件放在 cesium-data；个人活动和轨迹继续通过后端访问。

## 8. 更新代码和回滚

先在 .env 中修改要发布的镜像版本，例如前端改为 WEB_IMAGE_TAG=1.1，后端仍 API_IMAGE_TAG=1.0。后端有实际代码改动时再给它新版本号。不要覆盖唯一的旧版本镜像，否则难以回滚。

仅修改 Vue、CSS 或 Nginx 配置时：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose build web
```

若第 4 节选择本机 Node 备用路径，这里用 `python3 build_frontend_locally.py --tag running-webgis-frontend:1.1` 代替 build web，并确保 .env 为 WEB_IMAGE_TAG=1.1。

build 成功后再切换：

**执行位置：Mac 终端。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose up -d \
  --no-build --pull never --wait --wait-timeout 180
DOCKER_CONTEXT=desktop-linux docker compose images
```

后端更新同理，先改 API_IMAGE_TAG，再 build api 和 up。后端更换 IP 后，Nginx 通过 Docker DNS 重新解析；切换附近可能有数秒短暂 502，单副本方案不提供零停机保证。持续 502 先看日志，检查 API 是否健康及是否在同一网络。

回滚时，把 .env 中版本号改回已保留的旧标签，再运行上面的 up 命令。代码版本、建筑数据和后端数据是三项独立内容；回滚镜像不等于回滚数据。数据回滚需要另外指定匹配的备份目录并 force-recreate。

## 9. 把小样例迁移到另一台机器

先明确 CPU 架构：你这台 Mac 默认生成 linux/arm64 镜像。下面的归档适用于兼容的 ARM64 Linux Docker 环境。AMD64 服务器应重新构建相应架构镜像或制作多平台版本，不能靠改 tar 文件名转换架构。

迁移最少需要：两个运行镜像、运行配置、两份数据目录。Node 构建缓存、node_modules、原始 FIT 不需要一起搬走。这里提供独立的 compose.runtime.yaml，不含 build 路径，目标机不必保留源代码目录结构。

只导出演示样例时，先确认版本仍为 1.0；若已升级，按实际镜像版本调整归档与配置。确认 export-1.0 不存在后进行，避免反复嵌套复制：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
mkdir export-1.0
cp compose.runtime.yaml export-1.0/compose.yaml
cp .env.example export-1.0/.env
cp -R sample export-1.0/sample
DOCKER_CONTEXT=desktop-linux docker image save -o export-1.0/images.tar \
  running-webgis-frontend:1.0 running-webgis-backend:1.0
tar -czf webgis-demo-1.0-arm64.tar.gz -C export-1.0 .
```

`docker image save` 保存镜像及镜像层，目标机用 docker load 恢复；不要换成 docker export，后者导出的是容器文件系统，不能等价保留镜像配置。tar 命令中的 c 是创建归档、z 是 gzip 压缩、f 后面跟文件名；目标机的 x 是解包，-C 指定切换目录，末尾的点表示当前目录全部内容。

此处 .env.example 特意选择演示数据配置，不复制你可能切换过真实目录的个人 .env。迁移包里镜像比小样例大得多，约 284 KiB 只指样例数据，不是整套运行环境的大小。打包前不要给 sample 目录混入真实个人数据。

把这个 tar.gz 文件传到**你有权限使用的 ARM64 Linux Docker 主机**。WSL2 或另一台 Mac 的 ARM64 Docker 环境也可以用于练习，实际架构要核对。目标机先安装、启动 Docker 和 Compose。

**执行位置：目标机终端，不是 Mac 容器内部。将压缩包放在当前目录后执行。**

```bash
mkdir webgis-demo-1.0
tar -xzf webgis-demo-1.0-arm64.tar.gz -C webgis-demo-1.0
cd webgis-demo-1.0
docker load -i images.tar
docker compose config -q
docker compose up -d --no-build --pull never --wait --wait-timeout 180
curl -fsS http://127.0.0.1:18080/api/health
```

运行配置只绑定目标机的 127.0.0.1。如果是远程 Linux 服务器，可从自己的 Mac 另开终端建立 SSH 转发，保持目标机端口只供本机访问：

**执行位置：你的 Mac 终端；先把用户名和服务器地址替换成真实值。**

```bash
ssh -N -L 18082:127.0.0.1:18080 your_user@your_server
```

保持 SSH 连接，在 Mac 浏览器打开 http://127.0.0.1:18082。公开网站上线需要另行设计域名、HTTPS、访问控制和备份，不建议把个人完整轨迹直接公开。将端口改为 0.0.0.0 本身不等于完成生产上线。

## 10. 排错与验证边界

| 现象 | 定位方向 |
| --- | --- |
| 18080 端口被占用 | 修改 .env 中 WEB_PORT，并相应更改访问网址 |
| nginx: host not found / 502 | 确认在同一个联合 Compose 项目；API 服务名为 api，端口 8000 |
| API 404 | 检查 /api 前缀是否在代理中被误删 |
| 页面能打开但活动为空 | 检查 /api/health、/api/activities 响应，确认 sample 挂载 |
| GeoJSON 404 | 检查 WEBGIS_BUILDINGS_DIR 指向的目录，里面必须有固定文件名 |
| 静态文件返回 HTML | 检查 Nginx location；不要用 SPA 的 index.html 回退处理地图资源 |
| 地图底图/字体缺失，API 正常 | 当前代码依赖外部 OpenStreetMap 瓦片、Google Fonts；镜像迁移不把这些服务搬进来 |
| /docs 不完整 | 页面还会加载外部 Swagger 资源，检查浏览器网络请求 |
| 更新后仍看到旧页面 | 检查镜像版本是否真正切换、浏览器缓存，以及是否重开页面 |
| 后端单独 18000 与网页数据不同 | 两套 Compose 项目：原后端完整数据，联合项目默认样例 |

**执行位置：Mac 终端，deployment/web 目录。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose ps -a
DOCKER_CONTEXT=desktop-linux docker compose logs --tail 60 api web
DOCKER_CONTEXT=desktop-linux docker compose exec web nginx -t
DOCKER_CONTEXT=desktop-linux docker compose exec web \
  wget -q -O - http://api:8000/api/health
```

要结束本教程这套服务：

**执行位置：Mac 终端，deployment/web 目录。**

```bash
DOCKER_CONTEXT=desktop-linux docker compose down
```

只删除该联合项目的容器和网络，保留镜像以及挂载在 Mac 的样例和完整数据。此命令不会停止另一个 running-webgis-backend 项目。以后用第 5 节命令恢复。

依据：[Vite 静态资源规则](https://vite.dev/guide/assets.html)、[Vite 静态发布](https://vite.dev/guide/static-deploy.html)、[Compose 网络与服务名](https://docs.docker.com/compose/how-tos/networking/)、[Nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)。

## 11. 本次实际验证记录

以下是 **2026-11-04 清理前**在当前 Mac 的 Docker Desktop/linux-arm64 环境完成的历史验证。按你的要求，验证部署随后已清理；这些记录不表示容器现在仍在运行。

- 使用本机 Node + Nginx 备用路径完成依赖安装、TypeScript/Vite 编译和镜像构建；342 项 Cesium 运行资源被生成。标准多阶段 Dockerfile 已提供，但因 Node 基础镜像下载未完成，没有将其写成已验证成功。
- 验证时两个联合服务均 healthy；当时保留了原先 18000 的独立后端。随后按你的清理要求，这三个验证容器都已删除。
- 通过 18080 入口验证健康、活动分页、日历、月统计、轨迹、轨迹分析、网格、OpenAPI 和文档路由。查询 limit=1 确实只返回 1 项，验证了查询参数保留。
- 浏览器实际显示 5 次合成活动、18.0 km 演示月里程；区域探索载入 200 个建筑面，默认距离筛选后显示 20 个沿线建筑，圆形轨迹与三维建筑可见。此次默认本地纯色底图，无需在线 OSM。
- PNG 返回真实 PNG；GeoJSON 与样例文件字节一致；缺失 Cesium、建筑、JS 返回 404。建筑数据未烘焙进前端镜像；两个数据挂载均只读；API 非 root 运行，未发布宿主机端口。
- 单独重新创建 API 后，原 Nginx 能继续请求 /api/health；这验证了重连能力，未证明零停机。
- 在单独目录只复制 compose.runtime.yaml、.env.example、sample，复用现有镜像，以临时项目在 18082 启动并通过健康检查，随后清理临时容器。验证了本机迁移目录布局；没有实际在另一台机器导入镜像归档，也没有验证 AMD64 构建。

本次没有迁移数 GiB 完整归档，没有上传镜像，没有修改原 Vue 或 FastAPI 业务源码。完整数据切换与另一台机器的恢复步骤留给你按需练习。

## 附录：构建、Nginx 和联合运行配置原文

### frontend/Dockerfile

```dockerfile
FROM node:24-alpine AS build
WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist/ /usr/share/nginx/html/
EXPOSE 80
```

### frontend/.dockerignore

```text
**
!package.json
!package-lock.json
!tsconfig*.json
!vite.config.ts
!index.html
!src/
!src/**
!public/
!public/**
!nginx/
!nginx/**
public/cesium-data/
```

### frontend/nginx/default.conf

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Docker 内置 DNS；后端重建、更换 IP 后可重新解析服务名。
    resolver 127.0.0.11 valid=10s ipv6=off;
    set $api_upstream http://api:8000;

    # 保留原始 /api 路径和查询参数，不能把 /api 前缀去掉。
    location ^~ /api/ {
        proxy_pass $api_upstream$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }

    location ~ ^/(docs|redoc|openapi\.json)$ {
        proxy_pass $api_upstream$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 大文件和地图运行资源缺失时应真正返回 404，不能回退成 HTML。
    location ^~ /cesium-data/ {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
    }
    location ^~ /cesium/ {
        try_files $uri =404;
        add_header Cache-Control "no-cache" always;
    }
    location ^~ /assets/ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
    location = /index.html {
        add_header Cache-Control "no-cache" always;
    }
    location ~* \.(js|mjs|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|json|geojson)$ {
        try_files $uri =404;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### deployment/web/.env.example

```dotenv
WEB_IMAGE_TAG=1.0
API_IMAGE_TAG=1.0
WEB_PORT=18080
# 默认运行合成活动 + 少量公开建筑的迁移演示数据。
WEBGIS_DATA_DIR=./sample/processed
WEBGIS_BUILDINGS_DIR=./sample/cesium-data
# 切换到现有完整数据时，分别将上面两项改为：
# WEBGIS_DATA_DIR=../../data/processed
# WEBGIS_BUILDINGS_DIR=../../frontend/public/cesium-data
```

### deployment/web/compose.yaml

```yaml
name: running-webgis-fullstack

services:
  api:
    build:
      context: ../../backend
    image: running-webgis-backend:${API_IMAGE_TAG:-1.0}
    environment:
      RUNNING_WEBGIS_DATA_DIR: /data/processed
    expose:
      - "8000"
    volumes:
      - type: bind
        source: ${WEBGIS_DATA_DIR:-./sample/processed}
        target: /data/processed
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  web:
    build:
      context: ../../frontend
    image: running-webgis-frontend:${WEB_IMAGE_TAG:-1.0}
    ports:
      - "127.0.0.1:${WEB_PORT:-18080}:80"
    volumes:
      - type: bind
        source: ${WEBGIS_BUILDINGS_DIR:-./sample/cesium-data}
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
      retries: 5
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

### deployment/web/compose.runtime.yaml

```yaml
# 迁移用：只使用已构建的镜像，无需源代码构建上下文。
name: running-webgis-fullstack

services:
  api:
    image: running-webgis-backend:${API_IMAGE_TAG:-1.0}
    environment:
      RUNNING_WEBGIS_DATA_DIR: /data/processed
    expose:
      - "8000"
    volumes:
      - type: bind
        source: ${WEBGIS_DATA_DIR:-./sample/processed}
        target: /data/processed
        read_only: true
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  web:
    image: running-webgis-frontend:${WEB_IMAGE_TAG:-1.0}
    ports:
      - "127.0.0.1:${WEB_PORT:-18080}:80"
    volumes:
      - type: bind
        source: ${WEBGIS_BUILDINGS_DIR:-./sample/cesium-data}
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
      retries: 5
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```
