@echo off
rem Manda alla palestra i quarti d'ora dei vent'anni e le settimane dal vivo. Doppio clic e basta.
rem Serve GITHUB_TOKEN nel file .env (documenti/VPS.md). Si puo' rilanciare quando si vuole.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
".venv\Scripts\python.exe" -m strumenti.consegna %*
echo.
pause
