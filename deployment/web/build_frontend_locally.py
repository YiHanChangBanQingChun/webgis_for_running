#!/usr/bin/env python3
"""可选：Node 镜像下载失败时，用本机 Node 编译，再打包 Nginx 镜像。"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='running-webgis-frontend:1.0')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    frontend = root/'frontend'
    for name in ['node', 'npm', 'docker']:
        if not shutil.which(name):
            raise SystemExit(f'缺少 {name}；先按项目 README 配置本机开发环境。')
    env = dict(os.environ, DOCKER_CONTEXT='desktop-linux')
    # TemporaryDirectory 仅清理本次创建的临时目录，不碰已有 dist 或业务数据。
    with tempfile.TemporaryDirectory(prefix='webgis-frontend-build-') as temp:
        context = Path(temp)
        # 每次按 lock 文件安装，避免更新依赖后误用旧 node_modules。
        subprocess.run(['npm', 'ci', '--prefer-offline', '--no-audit', '--no-fund'],
                       cwd=frontend, check=True)
        subprocess.run(['npm', 'run', 'build', '--', '--outDir', str(context/'dist')],
                       cwd=frontend, check=True)
        data = context/'dist/cesium-data'
        if data.exists():
            shutil.rmtree(data)
        shutil.copyfile(frontend/'nginx/default.conf', context/'default.conf')
        shutil.copyfile(Path(__file__).with_name('Dockerfile.prebuilt'), context/'Dockerfile')
        subprocess.run(['docker', 'build', '-t', args.tag, str(context)], env=env, check=True)
    print('前端运行镜像已生成：', args.tag)


if __name__ == '__main__':
    main()
