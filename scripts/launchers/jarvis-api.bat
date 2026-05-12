@echo off
cd /d "C:\Users\jyot2\jarvis"
python -m uvicorn jarvis.apps.api.app:app --host 0.0.0.0 --port 8765 >> "C:\Users\jyot2\AppData\Local\Jarvis\logs\api.log" 2>&1
