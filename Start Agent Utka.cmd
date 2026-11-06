@echo off
cd /d "%~dp0"
set "BUNDLED_GIT=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd"
if exist "%BUNDLED_GIT%\git.exe" set "PATH=%BUNDLED_GIT%;%PATH%"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup Agent Utka.ps1 in PowerShell first.
  pause
  exit /b 1
)
start "" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" -m copilot.app
