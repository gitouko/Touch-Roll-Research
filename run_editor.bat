@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Touch & Roll Stage Editor. Your ROM is opened read-only; saving always writes a separate copy.

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
  echo The editor needs Python 3.10 or newer ^(required by PySide6^).
  echo Your "py -3" is:
  py -3 --version
  echo Install a newer Python from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 2
)

py -3 -c "import PySide6" 2>nul
if errorlevel 1 (
  echo The editor needs PySide6 ^(Qt for Python^), which is not installed yet.
  choice /M "Install it now with pip (about 100 MB download)"
  if errorlevel 2 (
    echo Not installed. You can install it later with:  py -3 -m pip install PySide6
    pause
    exit /b 2
  )
  py -3 -m pip install --user PySide6
  if errorlevel 1 (
    echo pip could not install PySide6.
    pause
    exit /b 2
  )
)

py -3 -m tredit %*
if errorlevel 1 pause
