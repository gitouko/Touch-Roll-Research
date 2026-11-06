@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Read-only: indexes data\, parses every stage file, writes reports to generated\trcore\
py -3 -m trcore validate --out generated\trcore
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo trcore reported problems - exit code %RC%. See generated\trcore\run_summary.json
if "%RC%"=="0" echo trcore finished without errors. Matrix: generated\trcore\validation_matrix.md
pause
exit /b %RC%
