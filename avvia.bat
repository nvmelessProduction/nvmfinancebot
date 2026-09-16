@echo off
REM ===========================================================================
REM  nvmfinancebot - avvio su Windows
REM
REM  Va lanciato dalla cartella del progetto. Prima di usarlo:
REM    1. il terminale MT5 deve essere APERTO e collegato al conto
REM    2. il file .env deve esistere e contenere le credenziali
REM    3. l'archivio deve essere stato seminato (semina.bat)
REM ===========================================================================

cd /d "%~dp0"

if not exist ".env" (
    echo ERRORE: manca il file .env
    echo Copia .env.example in .env e compilalo.
    pause
    exit /b 1
)

echo Verifica dell'ambiente...
python -c "import fastapi, uvicorn, pydantic" 2>nul
if errorlevel 1 (
    echo Dipendenze mancanti. Installo...
    python -m pip install -r requirements.txt
)

echo.
echo Verifica del broker...
python prova_esecuzione.py
if errorlevel 1 (
    echo.
    echo Il broker non risponde. Controlla che MT5 sia aperto e collegato.
    echo Il bot parte lo stesso in dry_run, ma non potra' operare.
    echo.
    pause
)

echo.
echo === nvmfinancebot in avvio ===
echo    pannello:  http://127.0.0.1:8000/
echo    salute:    http://127.0.0.1:8000/salute
echo    Cowork:    http://127.0.0.1:8000/cowork/in-attesa
echo.
echo    Per fermarlo: CTRL+C, oppure crea un file STOP in questa cartella
echo    (il file STOP blocca le APERTURE, non la sorveglianza).
echo.

python -m uvicorn main:app --host 127.0.0.1 --port 8000
