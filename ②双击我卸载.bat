@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，无法运行卸载脚本。可以手动清理：任务计划程序里删「AI修仙-数据源轮询」，再删本文件夹。
  pause
  exit /b 1
)
python uninstall.py
pause
