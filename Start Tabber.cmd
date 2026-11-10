@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m tabber.gui
) else (
  echo Run uv sync in this folder first, then open this launcher again.
  pause
)
