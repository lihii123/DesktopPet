@echo off
cd /d %~dp0
title Aku Desktop Pet - Build
echo.
echo ============================================
echo   Aku Desktop Pet - one-click build
echo ============================================
call build_core.bat
echo.
echo ============================================
echo   build.bat finished.
echo   The window stays open - press any key to close.
echo ============================================
pause
