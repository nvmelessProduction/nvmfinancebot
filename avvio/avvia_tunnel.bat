@echo off
REM ===========================================================================
REM  Avvia il tunnel Cloudflare e lo RIAVVIA se cade.
REM
REM  ATTENZIONE, e' il punto piu' importante di tutto l'avvio automatico:
REM  questo script serve solo con un tunnel NOMINATO, che ha un indirizzo
REM  fisso. Il tunnel "quick" (cloudflared tunnel --url ...) cambia indirizzo
REM  a ogni riavvio: riavviarlo da solo produce un bot che sembra vivo ma non
REM  riceve piu' niente, perche' TradingView continua a scrivere al vecchio
REM  indirizzo e nessuno te lo dice.
REM
REM  Il tunnel nominato si crea una volta sola, e serve un dominio tuo con i
REM  DNS su Cloudflare:
REM      cloudflared tunnel login
REM      cloudflared tunnel create nvmfinancebot
REM      cloudflared tunnel route dns nvmfinancebot bot.iltuodominio.it
REM  poi si scrive il file di configurazione che manda il traffico a
REM  http://localhost:8000 (vedi avvio/LEGGIMI.md).
REM ===========================================================================
setlocal
title nvmfinancebot - tunnel
cd /d "%~dp0.."

REM Il nome che hai dato al tunnel con "cloudflared tunnel create".
set NOME_TUNNEL=nvmfinancebot

if not exist "cloudflared.exe" (
    echo.
    echo ERRORE: non trovo cloudflared.exe in "%cd%".
    echo Scaricalo da https://github.com/cloudflare/cloudflared/releases
    echo ^(file cloudflared-windows-amd64.exe^), rinominalo cloudflared.exe
    echo e mettilo in questa cartella.
    echo.
    pause
    exit /b 1
)

:ciclo
echo [%date% %time%] avvio tunnel %NOME_TUNNEL%>> "avvio\riavvii.log"
cloudflared.exe tunnel run %NOME_TUNNEL%
echo [%date% %time%] il tunnel e' uscito con codice %errorlevel%: riparto fra 15 secondi>> "avvio\riavvii.log"
echo.
echo Il tunnel si e' fermato (codice %errorlevel%). Riparto fra 15 secondi.
timeout /t 15 /nobreak >nul
goto ciclo
