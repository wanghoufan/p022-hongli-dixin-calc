@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py --port 8765
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (py -3 server.py --port 8765) else (
    echo 未找到 Python 3，请先安装 Python 3。
    pause
  )
)
