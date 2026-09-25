@echo off
rem Scarica da Dukascopy le altre 23 coppie forex (nvm\dati\strumenti.py). Doppio clic e basta.
rem Prima le ore (un paio d'ore), poi i minuti (qualche giorno). Riprende da dove era.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo Prima le ore delle coppie nuove...
".venv\Scripts\python.exe" scarica.py --strumenti nuovi --ore --rapporto dati\rapporto-ore-coppie.txt
echo.
echo Ore finite. Adesso i minuti delle coppie nuove: ci vuole tanto, puoi chiudere e riprendere quando vuoi.
".venv\Scripts\python.exe" scarica.py --strumenti nuovi --rapporto dati\rapporto-minuti-coppie.txt
echo.
echo Finito. Fai doppio clic su consegna.bat per spedire tutto.
pause
