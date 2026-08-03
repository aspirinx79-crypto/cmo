@echo off
chcp 65001 >nul
REM CMO 기획 도구 - 더블클릭하면 브라우저가 열립니다.
setlocal
set ROOT=%~dp0
set PY=%ROOT%..\automation\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

cd /d "%ROOT%.."
"%PY%" -m cmo.server
pause
