@echo off
REM ===========================================================================
REM  Avvia il server del bot e lo RIAVVIA se muore.
REM
REM  Va lanciato da solo: se lo chiudi, il bot si ferma. Per farlo partire da
REM  solo all'accensione del PC, metti un collegamento a questo file dentro la
REM  cartella che si apre con:  Windows+R  ->  shell:startup
REM
REM  Il riavvio automatico NON e' una rete di sicurezza per gli ordini: se il
REM  server muore mentre una posizione e' aperta, per quei secondi nessuno
REM  sorveglia stop e target. Serve a non lasciare il bot spento per ore.
REM ===========================================================================
setlocal
title nvmfinancebot - server
cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo ERRORE: non trovo l'ambiente .venv in "%cd%".
    echo Crealo cosi', dal Prompt dei comandi in questa cartella:
    echo     py -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

:ciclo
echo [%date% %time%] avvio main.py>> "avvio\riavvii.log"
python main.py
echo [%date% %time%] main.py e' uscito con codice %errorlevel%: riparto fra 15 secondi>> "avvio\riavvii.log"
echo.
echo Il server si e' fermato (codice %errorlevel%). Riparto fra 15 secondi.
echo Per fermarlo davvero: chiudi questa finestra.
timeout /t 15 /nobreak >nul
goto ciclo
