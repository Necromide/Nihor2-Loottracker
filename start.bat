@echo off
rem Start from source (requires Python 3.10+). Friends without Python use the .exe instead.
cd /d "%~dp0"
python run.py %*
pause
