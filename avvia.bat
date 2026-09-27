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
rem Codice 2: fermo per scelta (per esempio un conto reale): non riparte.
if %errorlevel%==2 goto fermo
rem Qualunque altro motivo (MT5 chiuso, internet assente, un errore): riprova da solo fra un minuto.
echo Il bot si e' fermato (codice %errorlevel%): riprovo fra un minuto. Per fermarlo chiudi questa finestra.
timeout /t 60 /nobreak >nul
goto parti
:fermo
echo.
echo Il bot si e' fermato. Leggi l'ultimo messaggio sul canale operativo.
pause
