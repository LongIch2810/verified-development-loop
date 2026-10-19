@echo off
setlocal
python "%~dp0vdl_host_hook.py" %*
exit /b 0
