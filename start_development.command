#!/bin/bash
cd "$(dirname "$0")"
./start_development.sh "$@"
status=$?
if [[ $status -ne 0 ]]; then read -r -p '启动失败。按回车关闭窗口…'; fi
exit "$status"
