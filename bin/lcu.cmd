@echo off
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 (
  >&2 echo LCU requires Python 3.12 or newer via the Windows Python launcher.
  exit /b 1
)
py -3 "%~dp0lcu" %*
exit /b %ERRORLEVEL%
