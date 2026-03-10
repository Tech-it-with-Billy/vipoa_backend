@echo off
REM generic launcher for Windows development
cd /d %~dp0
REM activate your own virtualenv first, then run:
python manage.py runserver
pause
