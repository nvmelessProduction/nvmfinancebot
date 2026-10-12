@echo off
rem Scarica lo storico al minuto da Dukascopy. Doppio clic e basta.
rem La prima volta prepara l'ambiente Python; poi riprende da dove era.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
".venv\Scripts\python.exe" -m strumenti.scarica %*
echo.
echo Finito. Il rapporto dei controlli e' in dati\rapporto-dati.txt
pause
