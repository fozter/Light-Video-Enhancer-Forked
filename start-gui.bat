@echo off
cd /d "%~dp0"
python -m light_video_enhancer_forked --gui
if errorlevel 1 pause
