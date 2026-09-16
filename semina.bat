@echo off
REM  Semina l'archivio con vent'anni di candele vere Dukascopy.
REM  Si puo' rilanciare: riprende da dove era e non riscrive cio' che c'e'.
REM  La prima volta ci mette un'ora circa e scarica qualche centinaio di MB.

cd /d "%~dp0"
echo Semina dell'archivio da Dukascopy.
echo Prezzi scambiati, BID e ASK separati, estremi toccati e non campionati.
echo.
python importa_dukascopy.py
echo.
echo Fatto. Controlla la copertura con:  python -c "from core import storage; storage.inizializza(); print(storage.copertura_candele())"
pause
