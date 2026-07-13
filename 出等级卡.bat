@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo 正在炼制等级卡，请稍候…
python card.py --open
if errorlevel 1 pause
