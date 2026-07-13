@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo 正在生成修行周报，请稍候…
python weekly.py --open
if errorlevel 1 pause
