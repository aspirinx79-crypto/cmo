@echo off
REM CMO 기획 도구를 직원에게 링크로 공유한다. 이 창을 닫으면 공유가 끝난다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0share_cmo.ps1"
