@echo off
rem Collega il bot al vostro account TradingView, una volta sola. Doppio clic e basta.
rem Si apre il browser: entrate con l'account TradingView e premete "Allow". Poi la finestra prova i grafici.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
".venv\Scripts\python.exe" -m strumenti.tradingview_accesso %*
echo.
pause
