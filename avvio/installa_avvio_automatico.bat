@echo off
REM ===========================================================================
REM  Fa partire il bot da solo quando accendi il PC.
REM
REM  Si lancia UNA VOLTA. Crea un collegamento ad avvia.bat nella cartella di
REM  esecuzione automatica di Windows. Da quel momento, ogni volta che accendi
REM  il computer il bot riparte senza che tu faccia niente.
REM
REM  Per disattivarlo: Windows+R -> shell:startup -> cancella il collegamento.
REM ===========================================================================
setlocal
cd /d "%~dp0.."

set BERSAGLIO=%cd%\avvia.bat
set CARTELLA=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set COLLEGAMENTO=%CARTELLA%\nvmfinancebot.lnk

if not exist "%BERSAGLIO%" (
    echo ERRORE: non trovo avvia.bat in "%cd%".
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%COLLEGAMENTO%');" ^
  "$s.TargetPath='%BERSAGLIO%';" ^
  "$s.WorkingDirectory='%cd%';" ^
  "$s.Description='Avvia nvmfinancebot';" ^
  "$s.Save()"

if errorlevel 1 (
    echo ERRORE: non sono riuscito a creare il collegamento.
    pause
    exit /b 1
)

echo.
echo Fatto: il bot partira' da solo a ogni accensione del PC.
echo.
echo Restano due cose che Windows non puo' fare al posto tuo:
echo   1. MetaTrader 5 deve aprirsi e collegarsi da solo. Mettilo anche lui
echo      nella cartella che si apre con  Windows+R  ^-^>  shell:startup
echo      e in MT5 spunta "Mantieni le informazioni personali".
echo   2. Se il PC chiede la password all'accensione, niente parte finche' non
echo      entri. Vedi avvio\LEGGIMI.md, sezione "accesso automatico".
echo.
pause
