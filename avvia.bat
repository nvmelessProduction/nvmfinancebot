@echo off
REM ===========================================================================
REM  AVVIA IL BOT.
REM
REM  Fa tutto: al primo lancio prepara l'ambiente, chiede la configurazione e
REM  scarica lo storico; dalla seconda volta in poi parte e basta.
REM
REM  Se il bot si ferma, riparte da solo dopo 15 secondi. Per fermarlo
REM  davvero: chiudi questa finestra.
REM ===========================================================================
setlocal
title nvmfinancebot
cd /d "%~dp0"

echo.
echo ===========================================================================
echo   nvmfinancebot
echo ===========================================================================
echo.

REM --- 1. Python c'e'? -------------------------------------------------------
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: non trovo Python.
    echo Installalo da https://www.python.org/downloads/windows/
    echo e ricordati di spuntare "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

REM --- 2. L'ambiente e le librerie -------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Preparo l'ambiente. Succede solo la prima volta, ci vuole un minuto...
    py -3 -m venv .venv
    if errorlevel 1 goto :errore_venv
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    if errorlevel 1 goto :errore_librerie
    echo       fatto.
) else (
    echo [1/4] Ambiente gia' pronto.
)

set PY=.venv\Scripts\python.exe

REM --- 3. La configurazione --------------------------------------------------
if not exist ".env" (
    echo [2/4] Configurazione: tre domande, si fanno una volta sola.
    "%PY%" configura.py
    if errorlevel 1 goto :errore_config
) else (
    echo [2/4] Configurazione gia' fatta.
)

REM --- 4. Lo storico ---------------------------------------------------------
"%PY%" -c "from core import storage; storage.inizializza(); import sys; sys.exit(0 if storage.copertura_candele() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [3/4] Scarico lo storico dei future. Prima volta, cinque minuti circa...
    "%PY%" scarica_storico.py
) else (
    echo [3/4] Storico gia' in archivio.
)

REM --- 5. Si parte -----------------------------------------------------------
echo [4/4] Avvio.
echo.
echo   Il bot adesso lavora da solo: cerca le candele, decide, e ti avvisa.
echo   Non devi configurare nessun alert.
echo.
echo   Per fermarlo: chiudi questa finestra.
echo   Per bloccare gli ordini lasciando la sorveglianza accesa: crea un file
echo   chiamato STOP in questa cartella.
echo.

:ciclo
"%PY%" main.py
echo.
echo [%date% %time%] il bot si e' fermato (codice %errorlevel%): riparto fra 15 secondi>> "avvio\riavvii.log"
echo Il bot si e' fermato. Riparto fra 15 secondi. Chiudi la finestra per fermarlo davvero.
timeout /t 15 /nobreak >nul
goto ciclo

:errore_venv
echo.
echo ERRORE: non sono riuscito a creare l'ambiente .venv.
pause
exit /b 1

:errore_librerie
echo.
echo ERRORE: l'installazione delle librerie e' fallita.
echo Controlla la connessione a internet e rilancia.
pause
exit /b 1

:errore_config
echo.
echo Configurazione non completata: rilancia quando vuoi.
pause
exit /b 1
