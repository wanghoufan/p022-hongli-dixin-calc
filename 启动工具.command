#!/bin/bash
cd "$(dirname "$0")"
clear
printf '红利打新底仓计算器 V1.2 正式长期版\n\n'
if ! command -v python3 >/dev/null 2>&1; then
  echo '未找到 python3。请先安装 Python 3，然后重新双击本文件。'
  read -n 1 -s -r -p '按任意键退出…'
  exit 1
fi
python3 server.py --port 8765
