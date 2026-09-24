@echo off
rem Il bot dal vivo sul conto demo. Doppio clic e basta.
rem Prima: il terminale MT5 aperto e collegato al conto demo, con "Algo Trading" acceso,
rem e il file .env in questa cartella (lo stesso del vecchio bot, col token Telegram nuovo).
cd /d "%~dp0"
if not exist ".env" (
  echo Manca il file .env in questa cartella: copialo da quella del vecchio bot.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
:parti
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
".venv\Scripts\python.exe" vivo.py
rem Codice 3: il bot si e' aggiornato da solo, si riparte con la versione nuova.
if %errorlevel%==3 goto parti
echo.
echo Il bot si e' fermato. Leggi l'ultimo messaggio sul canale operativo.
pause
