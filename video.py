"""I video di Romeo per i cervelli: fotogrammi e parole. Gira sulla VPS.

    python video.py            # tutti i video del canale @Romeotpt non ancora fatti

Da Claude YouTube blocca gli scaricamenti; dalla VPS di solito no. Per ogni video: scarica il
video (senza audio, al massimo 720p) e i sottotitoli automatici in inglese, prende un
fotogramma ogni `OGNI` secondi (i grafici che Romeo disegna mentre parla), cancella il video
e lascia fotogrammi e sottotitoli in `dati/consegna/video/<id>/`. `consegna.bat` li spedisce
alla palestra (ramo `dati-vps`, mai nel codice). Si puo' interrompere e riprendere: i video
gia' fatti si saltano.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent
USCITA = RADICE / "dati" / "consegna" / "video"
LAVORO = RADICE / "dati" / "video_tmp"
CANALE = "https://www.youtube.com/@Romeotpt"
OGNI = 15            # secondi fra un fotogramma e l'altro
LARGHEZZA = 960
# I video del canale al 29/09/2026, se l'elenco non si riesce a leggere.
NOTI = ["T7udbrWlARI", "FYr6J5pIDB4", "_oiwm8_id8c", "n2GF8kCpgVg", "p8UYOgVn1-g", "3IWgc52Dqsg", "h7NCST2wPw8",
        "-mWYppebugo", "2sxdsgcIeYA", "af7ECe4HBjc", "1EK-LMwgJ3c", "Pmmx41M7KhA", "8LblVvGZaGY", "4DZWbCzEvhM",
        "wkSiy27a8ps", "UUq_wKQ61Wo", "U-gNCwbGtTI"]


def _ytdlp(*argomenti: str) -> subprocess.CompletedProcess:
    # YouTube vuole un motore JavaScript per dare i video: deno, installato col pip accanto a python.
    percorso = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    return subprocess.run([sys.executable, "-m", "yt_dlp", *argomenti], capture_output=True, text=True,
                          env={**os.environ, "PATH": percorso})


def elenco() -> list[tuple[str, str]]:
    """I video del canale (id, titolo): video, dirette e corti."""
    trovati: dict[str, str] = {}
    for parte in ("videos", "streams", "shorts"):
        r = _ytdlp("--flat-playlist", "--print", "%(id)s|%(title)s", f"{CANALE}/{parte}")
        for riga in r.stdout.splitlines():
            if "|" in riga:
                i, titolo = riga.split("|", 1)
                trovati[i] = titolo
    for i in NOTI:
        trovati.setdefault(i, "")
    return list(trovati.items())


def fotogrammi(video: Path, cartella: Path) -> int:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cartella.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-loglevel", "error", "-i", str(video), "-vf", f"fps=1/{OGNI},scale={LARGHEZZA}:-2",
                    "-q:v", "5", str(cartella / "f%04d.jpg")], check=True)
    # Il fotogramma n (da 1) e' al secondo (n - 1) * OGNI: il nome dice il secondo, per unirlo alle parole.
    n = 0
    for f in sorted(cartella.glob("f*.jpg")):
        secondo = (int(f.stem[1:]) - 1) * OGNI
        f.rename(cartella / f"s{secondo:05d}.jpg")
        n += 1
    return n


def uno(identita: str, titolo: str) -> str:
    fine = USCITA / identita
    if (fine / "fatto.json").exists():
        return "già fatto"
    shutil.rmtree(LAVORO, ignore_errors=True)
    LAVORO.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={identita}"
    r = _ytdlp("-f", "bv*[height<=720][ext=mp4]/bv*[height<=720]/b[height<=720]/bv*/b", "--write-auto-subs",
               "--sub-langs", "en", "--sub-format", "vtt", "-o", str(LAVORO / "v.%(ext)s"), "--", identita)
    video = next((f for f in LAVORO.glob("v.*") if f.suffix in (".mp4", ".webm", ".mkv")), None)
    for s in LAVORO.glob("*.vtt"):
        # Le parole si tengono anche se il video non arriva: il video si riprova la volta dopo.
        fine.mkdir(parents=True, exist_ok=True)
        shutil.copy(s, fine / "parole.vtt")
    if video is None:
        errore = (r.stderr.strip().splitlines() or ["sconosciuto"])[-1]
        return f"non scaricato ({errore[:120]})"
    n = fotogrammi(video, fine)
    (fine / "fatto.json").write_text(json.dumps({"id": identita, "titolo": titolo, "url": url, "fotogrammi": n,
                                                 "ogni_secondi": OGNI}, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(LAVORO, ignore_errors=True)
    return f"{n} fotogrammi"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pausa", type=int, default=30, help="secondi di pausa fra un video e l'altro")
    a = parser.parse_args()
    video = elenco()
    print(f"{len(video)} video sul canale di Romeo.", flush=True)
    for i, (identita, titolo) in enumerate(video, start=1):
        esito = uno(identita, titolo)
        print(f"[{i}/{len(video)}] {titolo or identita}: {esito}", flush=True)
        if esito != "già fatto":
            time.sleep(a.pausa)
    fatti = sum(1 for _ in USCITA.glob("*/fatto.json"))
    print(f"\nFatti {fatti} video su {len(video)}. Adesso doppio clic su consegna.bat per mandarli.", flush=True)


if __name__ == "__main__":
    main()
