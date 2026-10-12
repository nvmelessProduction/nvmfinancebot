@echo off
rem Installa la rete neurale del bot (PyTorch per processore, circa 200 MB). Una volta sola. Doppio clic e basta.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo Scarico e installo PyTorch: ci vogliono alcuni minuti...
".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
".venv\Scripts\python.exe" -c "from nvm.vivo.rete_vivo import Rete; r, p = Rete.carica(); print('Rete neurale pronta.' if r else 'Non va: ' + p)"
echo.
echo Adesso riavvia il bot: chiudi la finestra di avvia.bat e rifai doppio clic.
pause
