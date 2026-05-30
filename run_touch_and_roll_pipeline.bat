@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "data\decompressed" mkdir "data\decompressed"
if not exist "data\grouped" mkdir "data\grouped"
if not exist "docs\research_notes\reports" mkdir "docs\research_notes\reports"

echo ==========================================
echo  Touch & Roll one-click analysis pipeline
echo ==========================================
echo.

echo [1/4] Grouping stage files...
py -3 "%~dp0tools\group_stages_fixed.py" "%~dp0data\decompressed" -o "%~dp0data\grouped"
if errorlevel 1 goto :fail

echo.
echo [2/4] Generating manifest...
py -3 "%~dp0tools\generate_manifest.py" "%~dp0data\grouped" -o "%~dp0manifest.json"
if errorlevel 1 goto :fail

echo.
echo [3/4] Analyzing .stc files...
for /r "%~dp0data\grouped" %%F in (*.stc) do (
    echo   Analyzing %%~nxF
    py -3 "%~dp0tools\analyze_stc.py" "%%F" -o "%~dp0docs\research_notes\reports\%%~nF.json"
)

echo.
echo [4/4] Detecting repeated patterns...
py -3 "%~dp0tools\detect_patterns.py" "%~dp0data\grouped" --chunk 16 --across-files > "%~dp0docs\research_notes\pattern_report.txt"
if errorlevel 1 goto :fail

echo.
echo Pipeline complete.
echo - Manifest: manifest.json
echo - STC reports: docs\research_notes\reports\
echo - Pattern report: docs\research_notes\pattern_report.txt
pause
exit /b 0

:fail
echo.
echo Pipeline failed. Check the last command above for the error.
pause
exit /b 1
