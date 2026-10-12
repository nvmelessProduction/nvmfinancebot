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
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import weekend
from nvm.tempo import TF, fine_candela

FILE = "nvm_disegni.csv"
# Il battito del programma in MT5: tipo;versione;ora UTC;grafici;oggetti;errori;ultimo errore.
STATO = "nvm_disegni_stato.txt"
VERSIONE_MT5 = "4"
_WINDOWS = sys.platform == "win32"
SORGENTI = ("NvmDisegni.mqh", "NvmDisegni.mq5", "NvmDisegniGrafico.mq5")
DURATA = {TF.M15: 900, TF.H1: 3600, TF.H4: 4 * 3600, TF.D1: 86400, TF.W1: 7 * 86400}
# Quanto restano sul grafico i disegni di un'operazione, dopo la fine della candela 3.
RESTANO = {TF.H4: 3 * 86400, TF.D1: 7 * 86400, TF.W1: 21 * 86400, TF.MN: 45 * 86400}
MASSIMI_GRUPPI = 400

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


def _corto(gruppo: str) -> str:
    """Il nome di un gruppo nel file: corto, perche' in MT5 il nome di un oggetto sta in 63 caratteri."""
    return hashlib.sha1(gruppo.encode("utf-8")).hexdigest()[:10]


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
                    _corto(g), v["simbolo"], s["tipo"], str(int(s["t1"])), repr(float(s["p1"])), str(int(s["t2"])),
                    repr(float(s["p2"])), s["colore"], str(int(s["stile"])), str(int(s["spessore"])), _pulito(s["testo"])]))
        return fuori

    def togli(self, inizio: str) -> None:
        """Toglie i gruppi il cui nome comincia cosi' (quelli che si rifanno a ogni giro)."""
        self.gruppi = {g: v for g, v in self.gruppi.items() if not g.startswith(inizio)}

    def stato_mt5(self, adesso: float) -> Optional[dict]:
        """Il battito del programma in MT5, se c'e': chi e', quanto e' vecchio, quanti disegni e errori."""
        if self.cartella_mt5 is None or not (self.cartella_mt5 / STATO).exists():
            return None
        try:
            parti = (self.cartella_mt5 / STATO).read_text(encoding="cp1252").strip().split(";")
            return {"tipo": parti[0], "versione": parti[1], "eta": adesso - int(parti[2]), "grafici": int(parti[3]),
                    "oggetti": int(parti[4]), "errori": int(parti[5]), "ultimo_errore": int(parti[6])}
        except (OSError, ValueError, IndexError):
            return None

    def chiedi_foto(self, simbolo: str, periodo: str, numero: str) -> bool:
        """Chiede al programma in MT5 la foto del grafico coi disegni (per il telefono, su Telegram)."""
        if self.cartella_mt5 is None:
            return False
        self.cartella_mt5.mkdir(parents=True, exist_ok=True)
        (self.cartella_mt5 / f"nvm_foto_{numero}.req").write_bytes(f"{simbolo};{periodo}\r\n".encode("cp1252"))
        return True

    def esito_foto(self, numero: str) -> Optional[str]:
        """Com'e' andata una foto, se MT5 l'ha gia' detto: "ok" o il motivo. Il file si toglie."""
        if self.cartella_mt5 is None:
            return None
        f = self.cartella_mt5 / f"nvm_foto_{numero}.esito"
        try:
            testo = f.read_text(encoding="cp1252").strip()
            f.unlink()
            return testo
        except OSError:
            return None

    def scrivi(self, adesso: Optional[int] = None) -> None:
        if adesso is not None:
            self.togli_scaduti(adesso)
        self.cartella_bot.mkdir(parents=True, exist_ok=True)
        (self.cartella_bot / "disegni.json").write_text(json.dumps(self.gruppi, ensure_ascii=False), encoding="utf-8")
        if self.cartella_mt5 is None:
            return
        self.cartella_mt5.mkdir(parents=True, exist_ok=True)
        tmp = self.cartella_mt5 / (FILE + ".tmp")
        # MT5 lo legge come testo ANSI di Windows, righe chiuse da \r\n: gli accenti italiani ci sono.
        tmp.write_bytes(("".join(r + "\r\n" for r in self.righe())).encode("cp1252", errors="replace"))
        tmp.replace(self.cartella_mt5 / FILE)


def operazione(d, op, scarto_ore: int, key_level: Optional[tuple] = None) -> list[Segno]:
    """I disegni di un'operazione nata dalla candela 3 (`giro.Decisione` e l'operazione aperta).
    `key_level`: (che livello e', prezzo) dalle domande di Romeo, se c'e'. Le scritte di stop e obiettivi
    stanno a destra, quelle della candela 1 a sinistra, per non coprirsi."""
    s = d.r.scatto
    crt = s.crt
    short = crt.verso is Verso.SHORT
    sv = int(scarto_ore) * 3600
    inizio_1 = int(crt.range_inizio)
    fine_1 = int(fine_candela(inizio_1, crt.alto_tf, weekend(crt.strumento)))
    inizio_3 = int(crt.armato_quando)
    fine_3 = int(crt.fine_candela_3) if crt.fine_candela_3 < 2 ** 60 else inizio_3 + (inizio_3 - fine_1)
    dopo = fine_3 + max(fine_3 - inizio_3, 3600)
    vicino = 0.02 * (crt.crt_high - crt.crt_low)
    lato_tp2 = crt.crt_low if short else crt.crt_high
    tp2_sul_lato = abs(float(op.tp2) - lato_tp2) <= vicino
    tp1_al_50 = abs(float(op.tp1) - crt.crt_50) <= vicino
    segni = [
        Segno("apri", inizio_1 + sv, 0.0),
        Segno("rettangolo", inizio_1 + sv, crt.crt_high, fine_1 + sv, crt.crt_low, AZZURRO, testo="Candela 1"),
        # Le linee col nome a destra: si scrivono dalla fine all'inizio (la scritta va sul primo punto).
        Segno("linea", fine_3 + sv, crt.crt_high, inizio_1 + sv, crt.crt_high, BLU, 0, 2,
              "" if (tp2_sul_lato and not short) else "CRT high"),
        Segno("linea", fine_3 + sv, crt.crt_low, inizio_1 + sv, crt.crt_low, BLU, 0, 2,
              "" if (tp2_sul_lato and short) else "CRT low"),
        Segno("linea", inizio_1 + sv, crt.crt_50, int(s.quando) + sv, crt.crt_50, ARANCIO, 1, 1, "" if tp1_al_50 else "50%"),
        Segno("verticale", fine_1 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 2"),
        Segno("verticale", inizio_3 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 3"),
    ]
    if key_level is not None:
        nome, prezzo = key_level
        segni.append(Segno("linea", inizio_1 - 3 * (fine_1 - inizio_1) + sv, float(prezzo), dopo + sv, float(prezzo),
                           ROSSO, 1, 1, f"Key level: {nome}"))
    estremo = crt.estremo_a(inizio_3)
    if estremo is not None:
        segni.append(Segno("testo", fine_1 + sv, float(estremo), 0, 0.0, ROSSO, testo="Finta della candela 2"))
    if s.apertura_3 is not None:
        segni.append(Segno("linea", fine_3 + sv, float(s.apertura_3), inizio_3 + sv, float(s.apertura_3), GRIGIO, 2, 1,
                           "Apertura candela 3" + ("" if crt.alto_tf is TF.H4 else " (mezzanotte di New York)")))
    durata = DURATA.get(d.r.basso_tf, 3600)
    t_ts = int(s.turtle_soup_inizio)
    segni += [
        Segno("rettangolo", t_ts + sv, float(s.turtle_soup_massimo), t_ts + durata + sv, float(s.turtle_soup_minimo), ORO,
              testo={"kiss of death": "Kiss of death (l'ultima finta prima dell'obiettivo)",
                     "vera rottura": "Turtle soup della vera rottura di struttura"}.get(
                  getattr(s, "modello", ""), "Model#1 (finta della candela 3)")),
        Segno("linea", t_ts + sv, float(s.livello), int(s.quando) + sv, float(s.livello), ORO, 0, 1, ""),
        Segno("giu" if short else "su", int(s.quando) + sv, float(op.ingresso), 0, 0.0, VIOLA,
              testo=("Vendita" if short else "Acquisto") + (": ritorno nella zona dopo la rottura"
                                                           if getattr(s, "modello", "") == "vera rottura"
                                                           else ": chiusura oltre il corpo")),
        Segno("linea", dopo + sv, float(op.stop), int(s.quando) + sv, float(op.stop), ROSSO, 0, 2, "Stop"),
        Segno("linea", dopo + sv, float(op.tp1), int(s.quando) + sv, float(op.tp1), VERDE, 1, 2, "Obiettivo 1 (50%)"),
        Segno("linea", dopo + sv, float(op.tp2), int(s.quando) + sv, float(op.tp2), VERDE, 0, 2,
              "Obiettivo 2 (" + ("CRT low" if short else "CRT high") + ")" if tp2_sul_lato else "Obiettivo 2"),
    ]
    return segni


def operazione_foto(d, op, scarto_ore: int, key_level: Optional[tuple] = None) -> list[Segno]:
    """I disegni di un'operazione del metodo delle foto (`documenti/spec/metodo_foto.md`): il range (la candela 1 o la
    madre), la finta della candela 2, il key level preso, l'entrata all'apertura della candela 3, lo stop oltre la
    candela 2, il TP1 all'altro lato del range e il target finale (il gap o il key level)."""
    info = d.foto
    st = info["setup"]
    ob = info["obiettivo"]
    short = st.short
    sv = int(scarto_ore) * 3600
    inizio_1 = int(st.range_inizio)
    inizio_2, inizio_3 = int(st.n2_inizio), int(st.n3_inizio)
    fine_3 = int(st.n3_fine)
    dopo = fine_3 + max(fine_3 - inizio_3, 3600)
    nome_range = "Range (candela madre, con le inside bar)" if st.dentro else "Range (candela 1)"
    segni = [
        Segno("apri", inizio_1 + sv, 0.0),
        Segno("rettangolo", inizio_1 + sv, st.range_alto, inizio_2 + sv, st.range_basso, AZZURRO, testo=nome_range),
        Segno("verticale", inizio_2 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 2"),
        Segno("verticale", inizio_3 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 3: entrata all'apertura"),
        Segno("testo", inizio_2 + sv, float(st.n2_alto if short else st.n2_basso), 0, 0.0, ROSSO,
              testo="Finta della candela 2" + (" (dal DXY)" if st.dal_dxy else
                                               " (dalla TOTAL)" if getattr(st, "dal_totale", False) else "")),
    ]
    if key_level is not None:
        nome, prezzo = key_level
        segni.append(Segno("linea", inizio_1 - 3 * max(inizio_2 - inizio_1, 3600) + sv, float(prezzo), dopo + sv,
                           float(prezzo), ROSSO, 1, 1, f"Key level preso: {nome}"))
    segni += [
        Segno("giu" if short else "su", inizio_3 + sv, float(op.ingresso), 0, 0.0, VIOLA,
              testo=("Vendita" if short else "Acquisto") + " all'apertura della candela 3"),
        Segno("linea", dopo + sv, float(op.stop), inizio_3 + sv, float(op.stop), ROSSO, 0, 2, "Stop (oltre la candela 2)"),
        Segno("linea", dopo + sv, float(op.tp1), inizio_3 + sv, float(op.tp1), VERDE, 1, 2,
              "TP1: chiusura del CRT" + (f" ({round(100 * op.parziale)}% + pareggio)" if float(op.tp2) != float(op.tp1) else "")),
    ]
    if float(op.tp2) != float(op.tp1):
        segni.append(Segno("linea", dopo + sv, float(op.tp2), inizio_3 + sv, float(op.tp2), VERDE, 0, 2,
                           f"Target finale: {ob.nome}" if abs(float(op.tp2) - ob.prezzo) < 1e-9 else "Target finale"))
    return segni


def fino_a(d) -> int:
    crt = d.r.scatto.crt
    fine_3 = int(crt.fine_candela_3) if crt.fine_candela_3 < 2 ** 60 else int(d.r.quando) + 7 * 86400
    return fine_3 + RESTANO.get(crt.alto_tf, 7 * 86400)


def in_attesa(crt, apertura_3: Optional[float], scarto_ore: int) -> list[Segno]:
    """Un CRT che gli agenti stanno guardando: la candela 2 ha fatto la finta ed e' chiusa dentro, ora si
    aspetta nella candela 3 la finta oltre la sua apertura e la conferma (V9 24:20)."""
    short = crt.verso is Verso.SHORT
    sv = int(scarto_ore) * 3600
    inizio_1 = int(crt.range_inizio)
    fine_1 = int(fine_candela(inizio_1, crt.alto_tf, weekend(crt.strumento)))
    inizio_3 = int(crt.armato_quando)
    fine_3 = int(crt.fine_candela_3) if crt.fine_candela_3 < 2 ** 60 else inizio_3 + (inizio_3 - fine_1)
    nome = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H4: "a 4 ore"}.get(crt.alto_tf, "")
    segni = [
        Segno("rettangolo", inizio_1 + sv, crt.crt_high, fine_1 + sv, crt.crt_low, AZZURRO,
              testo=f"CRT {nome}: candela 1 (il range)"),
        Segno("linea", inizio_1 + sv, crt.crt_high, fine_3 + sv, crt.crt_high, BLU, 0, 1, "CRT high"),
        Segno("linea", inizio_1 + sv, crt.crt_low, fine_3 + sv, crt.crt_low, BLU, 0, 1, "CRT low"),
        Segno("linea", inizio_1 + sv, crt.crt_50, fine_3 + sv, crt.crt_50, ARANCIO, 1, 1, "50% (primo obiettivo)"),
        Segno("verticale", fine_1 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 2"),
        Segno("verticale", inizio_3 + sv, 0.0, 0, 0.0, GRIGIO, 2, 1, "Candela 3"),
    ]
    estremo = crt.estremo_a(inizio_3)
    if estremo is not None:
        segni.append(Segno("testo", (fine_1 + inizio_3) // 2 + sv, float(estremo), 0, 0.0, ROSSO,
                           testo="Finta della candela 2 (turtle soup)"))
    if apertura_3 is not None:
        segni.append(Segno("linea", inizio_3 + sv, float(apertura_3), fine_3 + sv, float(apertura_3), GRIGIO, 2, 1,
                           "Apertura candela 3" + ("" if crt.alto_tf is TF.H4 else " (mezzanotte di New York)")
                           + ": " + ("aspettiamo la finta sopra per vendere" if short else
                                                     "aspettiamo la finta sotto per comprare")))
    return segni


def aperta(v, adesso: int, scarto_ore: int) -> list[Segno]:
    """Un'operazione aperta sul conto: entrata, stop, obiettivi."""
    sv = int(scarto_ore) * 3600
    t0, t1 = int(getattr(v, "quando", adesso)) + sv, int(adesso) + 2 * 86400 + sv
    compra = v.verso != "short"
    return [
        Segno("su" if compra else "giu", t0, float(v.ingresso), 0, 0.0, VIOLA,
              testo="Operazione aperta: " + ("acquisto" if compra else "vendita")),
        Segno("linea", t0, float(v.stop), t1, float(v.stop), ROSSO, 0, 2, "Stop"),
        Segno("linea", t0, float(v.tp1), t1, float(v.tp1), VERDE, 1, 2, "TP1"),
        Segno("linea", t0, float(v.tp2), t1, float(v.tp2), VERDE, 0, 2, "Target finale"),
    ]


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
        # Il comando come lo scrive MetaQuotes, con le virgolette dopo i due punti: i percorsi di
        # Windows possono avere spazi.
        comando = f'"{editor}" /compile:"{dest / programma}" /log:"{dest / "compilazione.log"}"'
        try:
            subprocess.run(comando if _WINDOWS else [str(editor), f"/compile:{dest / programma}",
                                                      f"/log:{dest / 'compilazione.log'}"],
                           timeout=180, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            fatti = False
            continue
        if compilato.exists():
            segno.write_text(impronta, encoding="utf-8")
        else:
            fatti = False
    if not fatti:
        perche = "MetaEditor non trovato" if editor is None else "la compilazione non è riuscita"
        return False, (f"non sono riuscito a preparare il programma dei disegni per MT5 ({perche}): il bot lavora "
                       "lo stesso, ma senza disegni sul grafico.")
    return True, ""


def stato_in_parole(s: Optional[dict]) -> Optional[str]:
    """Cosa dire se i disegni in MT5 non vanno; None se va tutto bene."""
    if s is None or s["eta"] > 600:
        return ("i disegni non arrivano sul grafico: il programma NvmDisegni in MT5 non è acceso. In MT5: Navigatore "
                "(Ctrl+N) → «Services» → «NVM» → tasto destro su «NvmDisegni» → «Start».")
    if s["versione"] != VERSIONE_MT5:
        return ("in MT5 gira ancora il programma dei disegni vecchio: tasto destro su «NvmDisegni» (in «Services» → "
                "«NVM») → «Stop», poi di nuovo «Start».")
    if s["errori"] and not s["oggetti"]:
        return (f"MT5 non mi lascia disegnare (errore {s['ultimo_errore']}): trascina «NvmDisegniGrafico» "
                "(Navigatore → «Indicators» → «NVM») su un grafico qualsiasi e premi OK.")
    return None


AVVISO = ("✏️ Da adesso disegno sul grafico di MT5 le operazioni come le disegna Romeo: la candela 1 col suo "
          "50%, la finta sul key level, l'apertura della candela 3, la candela spessa del Model#1, l'entrata, lo "
          "stop e i due obiettivi; la domenica il massimo e il minimo della settimana passata.\n"
          "Per vederli serve una cosa sola, una volta: in MT5 apri il Navigatore (Ctrl+N), tasto destro su "
          "«Services» (Servizi) → «Refresh» (Aggiorna), apri «Services» e la cartella «NVM»: tasto destro su "
          "«NvmDisegni» → «Start» (Avvia). Da lì in poi i disegni compaiono da soli su ogni grafico aperto.")

SUBITO = ("✏️ Ora sui grafici aperti di MT5 disegno subito, a ogni ora: i CRT che stiamo guardando (candela 1 col "
          "50%, la finta della candela 2, l'apertura della candela 3 dove aspettiamo l'entrata), le operazioni "
          "aperte, e il massimo e il minimo della settimana scorsa. In alto a sinistra di ogni grafico compare la "
          "scritta «NVM: disegni accesi». Se non la vedi entro qualche minuto, te lo dico io qui.")

TELEFONO = ("📱 Le app di MT5 sul telefono non mostrano i disegni (le fa così MetaQuotes): li vedi sul computer. "
            "Sul telefono te li mando io qui, in foto: a ogni operazione nuova arriva il grafico disegnato, e quando "
            "vuoi lo chiedi tu scrivendo per esempio «/grafico EURUSD» (o «/grafico XAUUSD H4»).")
