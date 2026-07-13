#!/bin/bash
# AI修仙模拟器 macOS 安装入口（双击运行；如提示无法打开，右键 → 打开）
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python3。按系统弹出的提示安装开发者工具，或去 python.org 下载安装，装完重新双击我。"
  python3 --version
  read -r -p "回车退出"
  exit 1
fi
exec python3 app.py
