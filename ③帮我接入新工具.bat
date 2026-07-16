@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，先双击 ①双击我安装.bat 按提示装好 Python。
  pause
  exit /b 1
)
python sample_pack.py
pause
