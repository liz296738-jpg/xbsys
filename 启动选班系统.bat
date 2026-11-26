@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   教师选班系统 正在启动
echo   教师端  http://127.0.0.1:8765
echo   管理端  http://127.0.0.1:8765/admin
echo   关闭本窗口即停止服务
echo ==========================================
echo.
python "%~dp0app.py" --open
pause
