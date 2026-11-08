@echo off
cd /d "%~dp0"
if exist ".venv-media\Scripts\python.exe" (
  ".venv-media\Scripts\python.exe" -m tabber.collect --interactive
  pause
) else (
  echo The media environment is not installed. See MEDIA_COLLECTION.md.
  pause
)
