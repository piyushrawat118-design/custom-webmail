@echo off
title Custom Webmail Launcher
color 0A

echo ================================================
echo      Custom Webmail - Free Public URL
echo ================================================
echo.

:: Kill any old instance
taskkill /f /im ngrok.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1

:: Install requirements silently
echo [1/3] Installing requirements...
cd /d "C:\Users\HP\.gemini\antigravity\scratch\custom-webmail"
python -m pip install -r requirements.txt -q

:: Start Flask in background
echo [2/3] Starting email server...
start /min "" cmd /c "python app.py"
timeout /t 3 >nul

:: Save settings via API
echo [3/3] Saving HostGator settings...
python -c "import requests,time; time.sleep(2); r=requests.post('http://127.0.0.1:5000/api/settings',json={'imap_host':'sh008.hostgator.in','imap_port':993,'smtp_host':'sh008.hostgator.in','smtp_port':465,'email':'swati@digihype.in','password':'Swati123*'}); print('Settings:', r.json())"

echo.
echo ================================================
echo  Starting ngrok tunnel... 
echo  Copy the https://xxxx.ngrok-free.app link below
echo ================================================
echo.

:: Start ngrok
ngrok http 5000
