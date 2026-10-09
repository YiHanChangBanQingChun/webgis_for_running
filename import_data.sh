#!/bin/bash
source "$(dirname "$0")/scripts/common.sh"
require_venv
exec .venv/bin/python backend/scripts/refresh_data.py "$@"
