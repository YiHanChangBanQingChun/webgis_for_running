#!/bin/bash
# Shared bootstrap for terminal and Finder .command launchers.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v node >/dev/null 2>&1; then
  for node_dir in "$HOME"/.local/share/fnm/node-versions/*/installation/bin "$HOME"/Library/Application\ Support/fnm/node-versions/*/installation/bin; do
    if [[ -x "$node_dir/node" ]]; then export PATH="$node_dir:$PATH"; fi
  done
fi
cd "$PROJECT_DIR"
select_python() {
  for candidate in "${PYTHON_BIN:-}" python3.14 python3.13 python3.12 python3.11 python3 "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"; do
    if [[ -n "$candidate" ]] && "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' >/dev/null 2>&1; then
      PYTHON_EXEC="$candidate"
      return
    fi
  done
  echo '需要 Python 3.11+。安装后重试，或设置 PYTHON_BIN=/完整路径/python3。' >&2
  exit 1
}
require_venv() {
  if [[ ! -x .venv/bin/python ]]; then
    echo '首次运行正在配置 Python 和前端依赖…'
    bash "$PROJECT_DIR/setup_macos.sh"
  fi
}
