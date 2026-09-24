@echo off
py -3.12 "%~dp0lcu" %*
exit /b %ERRORLEVEL%
