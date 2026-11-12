#!/bin/bash
source "$(dirname "$0")/scripts/common.sh"
require_venv
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm ci); fi
exec .venv/bin/python scripts/dev.py "$@"
