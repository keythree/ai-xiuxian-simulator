#!/bin/bash
# AI修仙模拟器 macOS 样本打包入口（双击运行；如提示无法打开，右键 → 打开）
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python3，先双击 ①双击我安装.command 按提示装好。"
  read -r -p "回车退出"
  exit 1
fi
python3 sample_pack.py
read -r -p "回车退出"
