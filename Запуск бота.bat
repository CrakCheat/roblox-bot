@echo off
chcp 65001 >nul
title Roblox deals bot
cd /d "%~dp0"
py -3 run_local.py
pause
