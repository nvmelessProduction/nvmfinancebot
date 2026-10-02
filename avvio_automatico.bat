@echo off
rem Fa partire il bot da solo ogni volta che Windows si accende (per esempio dopo gli aggiornamenti).
rem Doppio clic una volta sola. Per toglierlo: Win+R, scrivi shell:startup, Invio, e cancella "NVM bot.bat".
rem Il bot apre MT5 da solo quando si collega (lo fa la libreria MetaTrader5).
set "AVVIO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%AVVIO%\NVM bot.bat" echo @echo off
>> "%AVVIO%\NVM bot.bat" echo timeout /t 60 /nobreak
>> "%AVVIO%\NVM bot.bat" echo start "NVM bot" /d "%~dp0" "%~dp0avvia.bat"
echo Fatto: da ora il bot parte da solo un minuto dopo che Windows si accende.
pause
