#!/bin/bash
source "$(dirname "$0")/scripts/common.sh"
select_python
command -v npm >/dev/null || { echo '需要 Node.js 22.12+（推荐 Node 24）。'; exit 1; }
node -e 'const [major,minor]=process.versions.node.split(".").map(Number); if(major<22 || (major===22 && minor<12))process.exit(1)' || { echo '需要 Node.js 22.12+。'; exit 1; }
[[ -x .venv/bin/python ]] || "$PYTHON_EXEC" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-core.txt
(cd frontend && npm ci)
echo '配置完成。运行 ./import_data.sh 导入数据，或双击 start_development.command 启动。'
