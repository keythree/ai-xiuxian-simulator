#!/bin/bash
cd "$(dirname "$0")"
echo "正在生成修行周报，请稍候…"
python3 app.py weekly --open
