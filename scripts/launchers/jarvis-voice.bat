@echo off
REM Jarvis Voice — always-on background loop (wake word → STT → chat → TTS)
REM Logs to %LOCALAPPDATA%\Jarvis\logs\voice.log
cd /d "C:\Users\jyot2\jarvis"
if not exist "%LOCALAPPDATA%\Jarvis\logs" mkdir "%LOCALAPPDATA%\Jarvis\logs"
python -m jarvis.apps.voice >> "%LOCALAPPDATA%\Jarvis\logs\voice.log" 2>&1
