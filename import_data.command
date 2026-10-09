#!/bin/bash
cd "$(dirname "$0")"
./import_data.sh "$@"
status=$?
read -r -p '按回车关闭窗口…'
exit "$status"
