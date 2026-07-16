#!/bin/bash
# AI修仙模拟器 macOS 卸载入口（双击运行；如提示无法打开，右键 → 打开）
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python3。可以手动清理：删 ~/Library/LaunchAgents/com.ai-xiuxian.poll.plist，再删本文件夹。"
  read -r -p "回车退出"
  exit 1
fi
python3 uninstall.py
read -r -p "回车退出"
