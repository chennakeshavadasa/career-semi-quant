@echo off
rem Semi Quant Terminal (local) - double-click to start. The first run creates a private
rem Python environment in .venv (1-3 minutes); your browser opens when it is ready.
setlocal
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || goto nopython
if not exist ".venv\Scripts\python.exe" (
  echo Setting up Semi Quant Terminal, first run takes 1-3 minutes...
  %PY% -m venv .venv || goto fail
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -e . || goto fail
)
".venv\Scripts\python.exe" -m semiquant %*
goto end
:nopython
echo Python 3.10 or newer is required.
echo Install it from https://www.python.org/downloads/  (tick "Add python.exe to PATH"), then run this file again.
pause
exit /b 1
:fail
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
:end
endlocal
