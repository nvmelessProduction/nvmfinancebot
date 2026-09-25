@echo off
rem Scarica da Dukascopy gli strumenti nuovi (nvm\dati\strumenti.py): le altre 23 coppie forex,
rem argento, petrolio, indici e crypto. Doppio clic e basta.
rem Prima le ore (un paio d'ore), poi i minuti (qualche giorno). Riprende da dove era.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo Prima le ore degli strumenti nuovi...
".venv\Scripts\python.exe" scarica.py --strumenti nuovi --ore --rapporto dati\rapporto-ore-nuovi.txt
echo.
echo Ore finite: puoi gia' fare doppio clic su consegna.bat. Adesso i minuti: ci vuole tanto, puoi chiudere e riprendere quando vuoi.
".venv\Scripts\python.exe" scarica.py --strumenti nuovi --rapporto dati\rapporto-minuti-nuovi.txt
echo.
echo Finito. Fai doppio clic su consegna.bat per spedire tutto.
pause
