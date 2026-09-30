"""I disegni del bot sul grafico di MT5 (il proprietario, 30/09/2026: *"Voglio che il bot disegni, sul
grafico"*).

Il bot scrive `nvm_disegni.csv` nella cartella comune dei file di MT5; il servizio `NvmDisegni` (in
`mt5/`, installato e compilato dal bot) lo legge ogni due secondi e disegna su ogni grafico aperto dello
strumento. Si disegna come disegna Romeo nei video: la candela 1 (il range, col suo 50%), la finta della
candela 2 sul key level, l'apertura della candela 3, la candela del Model#1, l'entrata, lo stop e i due
obiettivi; la domenica, il massimo e il minimo della settimana passata portati avanti (V14).

Le ore nel file sono quelle del server del broker, come le vuole MT5.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.tempo import TF, fine_candela

FILE = "nvm_disegni.csv"
SORGENTI = ("NvmDisegni.mqh", "NvmDisegni.mq5", "NvmDisegniGrafico.mq5")
DURATA = {TF.M15: 900, TF.H1: 3600, TF.H4: 4 * 3600, TF.D1: 86400, TF.W1: 7 * 86400}
# Quanto restano sul grafico i disegni di un'operazione, dopo la fine della candela 3.
RESTANO = {TF.H4: 3 * 86400, TF.D1: 7 * 86400, TF.W1: 21 * 86400, TF.MN: 45 * 86400}
MASSIMI_GRUPPI = 80

BLU, ARANCIO, GRIGIO, ROSSO, VERDE, ORO, VIOLA, AZZURRO = (
    "30,144,255", "255,140,0", "128,128,128", "220,20,60", "34,139,34", "218,165,32", "148,0,211", "225,235,250")


@dataclass
class Segno:
    tipo: str            # linea, rettangolo, testo, su, giu, verticale, apri
    t1: int
    p1: float
    t2: int = 0
    p2: float = 0.0
    colore: str = BLU
    stile: int = 0       # 0 pieno, 1 tratteggiato, 2 puntini
    spessore: int = 1
    testo: str = ""


def _pulito(testo: str) -> str:
    return testo.replace(";", ",").replace("\n", " ")


class Disegni:
    """I gruppi di disegni in corso, per strumento; si salvano in `dati/vivo/disegni.json`."""

    def __init__(self, cartella_bot: Path, cartella_mt5: Optional[Path] = None):
        self.cartella_bot = cartella_bot
        self.cartella_mt5 = cartella_mt5
        self.gruppi: dict[str, dict] = {}
        f = cartella_bot / "disegni.json"
        if f.exists():
            try:
                self.gruppi = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.gruppi = {}

    def metti(self, gruppo: str, simbolo: str, segni: list[Segno], fino: int) -> None:
        self.gruppi[gruppo] = {"simbolo": simbolo, "fino": int(fino), "segni": [asdict(s) for s in segni]}

    def togli_scaduti(self, adesso: int) -> None:
        self.gruppi = {g: v for g, v in self.gruppi.items() if v["fino"] > adesso}
        if len(self.gruppi) > MASSIMI_GRUPPI:
            tenuti = sorted(self.gruppi, key=lambda g: -self.gruppi[g]["fino"])[:MASSIMI_GRUPPI]
            self.gruppi = {g: self.gruppi[g] for g in tenuti}

    def righe(self) -> list[str]:
        fuori = []
        for g, v in self.gruppi.items():
            for s in v["segni"]:
                fuori.append(";".join([
                    _pulito(g), v["simbolo"], s["tipo"], str(int(s["t1"])), repr(float(s["p1"])), str(int(s["t2"])),
                    repr(float(s["p2"])), s["colore"], str(int(s["stile"])), str(int(s["spessore"])), _pulito(s["testo"])]))
        return fuori

    def scrivi(self, adesso: Optional[int] = None) -> None:
        if adesso is not None:
            self.togli_scaduti(adesso)
        self.cartella_bot.mkdir(parents=True, exist_ok=True)
        (self.cartella_bot / "disegni.json").write_text(json.dumps(self.gruppi, ensure_ascii=False), encoding="utf-8")
        if self.cartella_mt5 is None:
            return
        self.cartella_mt5.mkdir(parents=True, exist_ok=True)
        tmp = self.cartella_mt5 / (FILE + ".tmp")
        # MT5 lo legge come testo ANSI (Windows): gli accenti italiani ci sono.
        tmp.write_text("\n".join(self.righe()) + "\n", encoding="cp1252", errors="replace")
        tmp.replace(self.cartella_mt5 / FILE)


def operazione(d, op, scarto_ore: int) -> list[Segno]:
    """I disegni di un'operazione nata dalla candela 3 (`giro.Decisione` e l'operazione aperta)."""
    s = d.r.scatto
    crt = s.crt
    short = crt.verso is Verso.SHORT
    sv = int(scarto_ore) * 3600
    inizio_1 = int(crt.range_inizio)
    fine_1 = int(fine_candela(inizio_1, crt.alto_tf))
    inizio_3 = int(crt.armato_quando)
    fine_3 = int(crt.fine_candela_3) if crt.fine_candela_3 < 2 ** 60 else inizio_3 + (inizio_3 - fine_1)
    dopo = fine_3 + max(fine_3 - inizio_3, 3600)
    segni = [
        Segno("apri", inizio_1 + sv, 0.0),
        Segno("rettangolo", inizio_1 + sv, crt.crt_high, fine_1 + sv, crt.crt_low, AZZURRO, testo="Candela 1 (il range)"),
        Segno("linea", inizio_1 + sv, crt.crt_high, fine_3 + sv, crt.crt_high, BLU, 0, 2, "CRT high"),
        Segno("linea", inizio_1 + sv, crt.crt_low, fine_3 + sv, crt.crt_low, BLU, 0, 2, "CRT low"),
        Segno("linea", inizio_1 + sv, crt.crt_50, dopo + sv, crt.crt_50, ARANCIO, 1, 1, "50% del range"),
        Segno("verticale", fine_1 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 2"),
        Segno("verticale", inizio_3 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 3"),
    ]
    estremo = crt.estremo_a(inizio_3)
    if estremo is not None:
        segni.append(Segno("testo", (fine_1 + inizio_3) // 2 + sv, float(estremo), 0, 0.0, ROSSO,
                           testo="Turtle soup sul key level (candela 2)"))
    if s.apertura_3 is not None:
        segni.append(Segno("linea", inizio_3 + sv, float(s.apertura_3), fine_3 + sv, float(s.apertura_3), GRIGIO, 2, 1,
                           "Apertura candela 3"))
    durata = DURATA.get(d.r.basso_tf, 3600)
    t_ts = int(s.turtle_soup_inizio)
    segni += [
        Segno("rettangolo", t_ts + sv, float(s.turtle_soup_massimo), t_ts + durata + sv, float(s.turtle_soup_minimo), ORO,
              testo="Model#1: la candela spessa della finta"),
        Segno("linea", t_ts + sv, float(s.livello), int(s.quando) + sv, float(s.livello), ORO, 0, 1, "Livello del Model#1"),
        Segno("giu" if short else "su", int(s.quando) + sv, float(op.ingresso), 0, 0.0, VIOLA,
              testo=("Vendita" if short else "Acquisto") + ": chiusura oltre il corpo"),
        Segno("linea", int(s.quando) + sv, float(op.stop), dopo + sv, float(op.stop), ROSSO, 0, 2, "Stop"),
        Segno("linea", int(s.quando) + sv, float(op.tp1), dopo + sv, float(op.tp1), VERDE, 1, 2, "Obiettivo 1 (50%)"),
        Segno("linea", int(s.quando) + sv, float(op.tp2), dopo + sv, float(op.tp2), VERDE, 0, 2, "Obiettivo 2"),
    ]
    return segni


def fino_a(d) -> int:
    crt = d.r.scatto.crt
    fine_3 = int(crt.fine_candela_3) if crt.fine_candela_3 < 2 ** 60 else int(d.r.quando) + 7 * 86400
    return fine_3 + RESTANO.get(crt.alto_tf, 7 * 86400)


def settimana(alto: float, basso: float, lunedi: int, venerdi: int, scarto_ore: int) -> list[Segno]:
    """La domenica di Romeo (V14): il lunedi' segnato, massimo e minimo della settimana passata portati avanti."""
    sv = int(scarto_ore) * 3600
    return [
        Segno("verticale", lunedi + sv, 0.0, 0, 0.0, GRIGIO, 1, 1, "Lunedì"),
        Segno("linea", lunedi + sv, alto, venerdi + sv, alto, VIOLA, 1, 1, "Massimo della settimana scorsa"),
        Segno("linea", lunedi + sv, basso, venerdi + sv, basso, VIOLA, 1, 1, "Minimo della settimana scorsa"),
    ]


def installa(radice: Path, dati_mt5: Path, programma_mt5: Path) -> tuple[bool, str]:
    """Copia i programmi di `mt5/` nella cartella di MT5 e li compila con MetaEditor (solo se cambiati).
    Restituisce (fatto, cosa dire se qualcosa non va)."""
    sorgente = radice / "mt5"
    impronta = hashlib.sha256(b"".join((sorgente / n).read_bytes() for n in SORGENTI)).hexdigest()[:16]
    editor = next((programma_mt5 / n for n in ("MetaEditor64.exe", "metaeditor64.exe", "MetaEditor.exe")
                   if (programma_mt5 / n).exists()), None)
    fatti = True
    for cartella, programma in (("Services", "NvmDisegni.mq5"), ("Indicators", "NvmDisegniGrafico.mq5")):
        dest = dati_mt5 / "MQL5" / cartella / "NVM"
        segno = dest / "versione.txt"
        compilato = dest / programma.replace(".mq5", ".ex5")
        if segno.exists() and segno.read_text(encoding="utf-8") == impronta and compilato.exists():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sorgente / "NvmDisegni.mqh", dest / "NvmDisegni.mqh")
        shutil.copy2(sorgente / programma, dest / programma)
        if editor is None:
            fatti = False
            continue
        try:
            subprocess.run([str(editor), f"/compile:{dest / programma}", f"/log:{dest / 'compilazione.log'}"],
                           timeout=180, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            fatti = False
            continue
        if compilato.exists():
            segno.write_text(impronta, encoding="utf-8")
        else:
            fatti = False
    if not fatti:
        return False, ("non sono riuscito a preparare il programma dei disegni per MT5 (MetaEditor non trovato o "
                       "compilazione fallita): il bot lavora lo stesso, ma senza disegni sul grafico.")
    return True, ""


AVVISO = ("✏️ Da adesso disegno sul grafico di MT5 le operazioni come le disegna Romeo: la candela 1 col suo "
          "50%, la finta sul key level, l'apertura della candela 3, la candela spessa del Model#1, l'entrata, lo "
          "stop e i due obiettivi; la domenica il massimo e il minimo della settimana passata.\n"
          "Per vederli serve una cosa sola, una volta: in MT5 apri il Navigatore (Ctrl+N), apri «Servizi», poi "
          "la cartella «NVM»: tasto destro su «NvmDisegni» → «Avvia». Se non lo vedi: tasto destro su «Servizi» → "
          "«Aggiorna». Da lì in poi i disegni compaiono da soli su ogni grafico aperto.")
