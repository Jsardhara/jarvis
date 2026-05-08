@echo off
cd /d "C:\Users\jyot2\jarvis"
python -m jarvis.daemon.sentinel >> "C:\Users\jyot2\AppData\Local\Jarvis\logs\sentinel.log" 2>&1
