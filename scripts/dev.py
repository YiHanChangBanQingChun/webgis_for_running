"""Run the local API and Vite together; Ctrl-C stops both process groups."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def check_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except PermissionError:
            raise SystemExit('当前运行环境不允许监听本地端口，请在 macOS 终端中运行。')
        except OSError:
            raise SystemExit(f'端口 {port} 已被占用，请关闭原服务后重试。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['fastapi', 'springboot'], default='fastapi')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    data = Path(os.environ.get('RUNNING_WEBGIS_DATA_DIR', ROOT / 'data/processed')).resolve()
    report = data / 'import-report.json'
    if not report.exists() or not json.loads(report.read_text())['readiness']['api_ready']:
        raise SystemExit('数据尚未就绪，请先运行 ./import_data.sh。')
    port = 8000 if args.backend == 'fastapi' else 8080
    check_port(port)
    check_port(5173)
    env = dict(os.environ, RUNNING_WEBGIS_DATA_DIR=str(data),
               VITE_API_PROXY_TARGET=f'http://127.0.0.1:{port}')
    if args.backend == 'springboot':
        java = subprocess.run(['java', '-version'], capture_output=True, text=True)
        if java.returncode:
            raise SystemExit('需要 JDK 21+；请安装 Temurin 21 后重试。')
        backend = ['./mvnw', '-B', '-ntp', f'-Dmaven.repo.local={ROOT / ".maven-cache"}',
                   'spring-boot:run', '-Dspring-boot.run.arguments=--server.address=127.0.0.1']
        cwd = ROOT / 'backend_springboot/api'
    else:
        backend = [sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
                   '--host', '127.0.0.1', '--port', str(port)]
        cwd = ROOT
    children = []
    def stop(signum=None, frame=None):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGHUP, stop)
    try:
        children.append(subprocess.Popen(backend, cwd=cwd, env=env, start_new_session=True))
        deadline = time.monotonic() + 180
        while True:
            if children[0].poll() is not None:
                raise RuntimeError('后端提前退出，请查看上面的错误。')
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('等待后端超时。')
            time.sleep(.5)
        children.append(subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1',
                                         '--port', '5173', '--strictPort'],
                                        cwd=ROOT / 'frontend', env=env, start_new_session=True))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if children[-1].poll() is not None:
                raise RuntimeError('前端提前退出。')
            try:
                with urlopen('http://127.0.0.1:5173', timeout=1):
                    break
            except OSError:
                time.sleep(.3)
        else:
            raise RuntimeError('等待前端超时。')
        print(f'\nWebGIS: http://127.0.0.1:5173\nAPI: http://127.0.0.1:{port}/api/health\n按 Ctrl-C 停止前后端。', flush=True)
        if not args.no_open:
            webbrowser.open('http://127.0.0.1:5173')
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        raise RuntimeError('一个服务已退出，正在关闭另一个服务。')
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()


if __name__ == '__main__':
    main()
