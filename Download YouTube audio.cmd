@echo off
cd /d "%~dp0"
if exist ".venv-media\Scripts\pythonw.exe" (
  start "" ".venv-media\Scripts\pythonw.exe" -m tabber.media_gui
) else (
  echo The media environment is not installed. See MEDIA_COLLECTION.md.
  pause
)
