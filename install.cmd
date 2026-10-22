@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare.ps1"
  if errorlevel 1 goto fail
)
"%~dp0runtime\python.exe" -X utf8 "%~dp0setup_tool.py" %*
if errorlevel 3 goto fail
if errorlevel 2 goto partial
if errorlevel 1 goto fail
echo.
pause
exit /b 0
:partial
echo 部分步骤未完成，请查看上方原因和 reports 中的报告。已有组件未覆盖。
pause
exit /b 2
:fail
echo 安装未完成，请查看上方提示。
pause
exit /b 1
