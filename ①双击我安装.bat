@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，正在打开下载页面。安装时务必勾选 Add to PATH，装完重新双击我。
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
start "" pythonw app.py
