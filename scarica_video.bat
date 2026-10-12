@echo off
rem I video di Romeo per i cervelli: fotogrammi e parole (strumenti/video.py). Doppio clic e basta.
rem Va sulla VPS o, meglio, sul computer di casa: da casa YouTube non blocca.
rem Si puo' chiudere e riprendere quando vuoi: i video gia' fatti si saltano.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto pronto
set PY=
py -3 -c "import sys" >nul 2>&1 && set PY=py -3
if not defined PY (python -c "import sys" >nul 2>&1 && set PY=python)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  echo Manca Python: lo installo, un paio di minuti...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  echo Non riesco a installare Python da solo. Installalo da python.org spuntando "Add Python to PATH", poi rifai doppio clic.
  pause
  exit /b 1
)
echo Preparo l'ambiente Python, solo la prima volta...
%PY% -m venv .venv
if exist requirements.txt ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
:pronto
echo Preparo gli strumenti per i video...
".venv\Scripts\python.exe" -m pip install -q -U "yt-dlp[default,curl-cffi]" yt-dlp-getpot-wpc deno imageio-ffmpeg
".venv\Scripts\python.exe" -m strumenti.video
echo.
pause
