@echo off
REM ===========================================================================
REM  nvmfinancebot - aggiornamento sicuro da GitHub
REM
REM  Serve perche' `git pull` si rifiuta di procedere quando in cartella ci
REM  sono modifiche locali ai file che il pull vuole cambiare, e la via
REM  d'uscita ovvia (`git reset --hard`) butta via quelle modifiche per
REM  sempre. Qui non si butta niente:
REM
REM    1. il calendario news esce da git con una copia, perche' e' l'unico
REM       file con dati tuoi dentro e non deve passare per lo stash;
REM    2. tutto il resto va in `git stash`, che lo conserva e si recupera;
REM    3. si aggiorna;
REM    4. il calendario torna al suo posto.
REM
REM  Se qualcosa va storto, le modifiche sono nello stash: `git stash list`
REM  le elenca e `git stash pop` le rimette.
REM ===========================================================================

cd /d "%~dp0"

echo === Cosa c'e' di modificato in locale ===
git diff --stat
echo.

if exist "dati\news.csv" (
    echo Metto al sicuro il calendario news...
    copy /Y "dati\news.csv" "news.csv.salvato" >nul
    if errorlevel 1 (
        echo ERRORE: non sono riuscito a copiare il calendario. Mi fermo.
        pause
        exit /b 1
    )
)

echo Metto da parte le modifiche locali...
git stash
echo.

echo Aggiorno da GitHub...
git pull
if errorlevel 1 (
    echo.
    echo ERRORE: il pull non e' riuscito. Le tue modifiche sono nello stash
    echo e non sono perse: recuperale con  git stash pop
    pause
    exit /b 1
)
echo.

if exist "news.csv.salvato" (
    echo Rimetto il calendario news...
    copy /Y "news.csv.salvato" "dati\news.csv" >nul
    del "news.csv.salvato"
)

echo Aggiorno le dipendenze...
python -m pip install -q -r requirements.txt

echo.
echo === Aggiornato ===
echo.
echo Adesso, in ordine:
echo.
echo    python importa_dxy.py      il dollar index, senza cui SETUP-19
echo                              non abilita nulla su cinque coppie
echo    python prova_giro.py       dice se la catena regge, in un minuto
echo    avvia.bat                  solo se prova_giro.py e' pulito
echo.
echo Le modifiche locali di prima sono nello stash: `git stash list`.
echo.
pause
