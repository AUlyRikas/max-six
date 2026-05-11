@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  外围杀肖（三级回退融合版）
echo  L1:双条件 L2:四项单条件 L3:动态位移
echo ========================================
echo.
python waiwei_shaxiao.py
echo.
echo ========================================
pause >nul