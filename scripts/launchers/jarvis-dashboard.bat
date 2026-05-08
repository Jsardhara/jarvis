@echo off
cd /d "C:\Users\jyot2\jarvis\web"
pnpm dev --port 3000 >> "C:\Users\jyot2\AppData\Local\Jarvis\logs\dashboard.log" 2>&1
