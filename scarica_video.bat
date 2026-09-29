@echo off
rem I video di Romeo per i cervelli: fotogrammi e parole (video.py). Doppio clic e basta.
rem Poi doppio clic su consegna.bat per mandarli. Si puo' chiudere e riprendere quando vuoi.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparo l'ambiente Python, solo la prima volta...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo Preparo gli strumenti per i video...
".venv\Scripts\python.exe" -m pip install -q -U yt-dlp imageio-ffmpeg
".venv\Scripts\python.exe" video.py
echo.
pause
