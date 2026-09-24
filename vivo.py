"""Il bot dal vivo, sul conto demo. Si avvia con `avvia.bat` sulla VPS.

    python vivo.py

Ogni minuto sorveglia le posizioni aperte (pareggio, chiusure). Venti
secondi dopo ogni ora fa il giro: l'equipe guarda le orarie appena chiuse,
il Capo decide, il Rischio sceglie la puntata, l'Esecutore apre. Poi guarda
se su GitHub c'e' una versione nuova: se c'e', la scarica e si riavvia.
Il sabato mattina fa la riunione, e il Capo si riaddestra.

Chiude con il codice 3 quando si e' aggiornato: `avvia.bat` lo riavvia.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from nvm.agenti.capo import Capo
from nvm.dati.minuti import PUNTO, Minuti
from nvm.vivo import messaggi
from nvm.vivo.ambiente import impostazioni
from nvm.vivo.carta import segui
from nvm.vivo.dialogo import aggiorna_pagelle, discussione, resoconto, spinte
from nvm.vivo.esecutore import Esecutore
from nvm.vivo.giro import giro as giro_orario
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.stato import Seguita, Stato, registra
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import ErroreMT5, Terminale

RADICE = Path(__file__).resolve().parent
CARTELLA = RADICE / "dati" / "vivo"
RAMO = "claude/zealous-albattani-394cd9"
ORARIE = 13000          # circa due anni: servono al key level del mensile
RITARDO_GIRO = 20       # secondi dopo l'ora, per dare al broker il tempo di chiudere la barra
AGGIORNATO = 3          # codice d'uscita: "mi sono aggiornato, riavviami"


def _ora(t: float) -> int:
    return int(t) // 3600 * 3600


def _unisci(base: Minuti, nuove: Minuti, quante: int = ORARIE) -> Minuti:
    if not len(nuove):
        return base
    vecchie = base.fra(int(base.t[0]), int(nuove.t[0])) if len(base) else base
    tutte = Minuti.unisci([m for m in (vecchie, nuove) if len(m)])
    return tutte.fra(int(tutte.t[max(0, len(tutte) - quante)]), int(tutte.t[-1]) + 1)


def _capo() -> Capo:
    p = CARTELLA / "capo.json"
    if not p.exists():
        p = RADICE / "nvm" / "vivo" / "capo.json"
    return Capo.da_dati(json.loads(p.read_text(encoding="utf-8")))


def _parte() -> float:
    p = CARTELLA / "rischio.json"
    if not p.exists():
        p = RADICE / "nvm" / "vivo" / "rischio.json"
    return float(json.loads(p.read_text(encoding="utf-8"))["parte"])


# I file che, se cambiano, chiedono di riavviare il bot. Il resto (documenti,
# registro, casi) si aggiorna in silenzio.
DA_RIAVVIO = (".py", ".json", ".npz", ".bat", ".txt")


def _versione_nuova() -> str:
    """Se su GitHub c'e' una versione nuova la scarica. Se cambia il bot ne
    restituisce il titolo (e il bot si riavvia); se cambiano solo documenti, ''."""
    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=RADICE, capture_output=True, text=True, timeout=120, check=True).stdout.strip()
    git("fetch", "-q", "origin", RAMO)
    if git("rev-parse", "HEAD") == git("rev-parse", "FETCH_HEAD"):
        return ""
    cambiati = git("diff", "--name-only", "HEAD", "FETCH_HEAD").splitlines()
    git("merge", "-q", "--ff-only", "FETCH_HEAD")
    if not any(c.endswith(DA_RIAVVIO) for c in cambiati):
        return ""
    return git("log", "-1", "--format=%s")


class Bot:
    def __init__(self) -> None:
        self.imp = impostazioni(RADICE)
        self.tg = Telegram(self.imp)
        self.stato = Stato.carica(CARTELLA)
        self.capo = _capo()
        self.terminale = Terminale(self.imp.suffisso)
        self.esecutore = Esecutore(self.terminale, _parte())
        self.basi: dict[str, Minuti] = {}
        self._allarmi: dict[str, float] = {}

    def allarme(self, testo: str) -> None:
        """Un allarme sul canale operativo, al massimo una volta l'ora per lo stesso testo."""
        if time.time() - self._allarmi.get(testo, 0) > 3600:
            self._allarmi[testo] = time.time()
            self.tg.operativo(messaggi.allarme(testo))

    def avvia(self) -> None:
        self.terminale.connetti()
        conto = self.terminale.conto()
        if not conto.demo:
            self.tg.operativo(messaggi.allarme(
                f"Il conto {conto.login} è un conto reale: il bot opera solo sul demo. Mi fermo."))
            sys.exit(1)
        if self.stato.scarto is not None:
            self.terminale.scarto = self.stato.scarto
        while self.terminale.misura_scarto("EURUSD") is None:
            self.allarme("Non so ancora l'ora del server del broker: aspetto che il mercato si muova.")
            time.sleep(60)
        self.stato.scarto = self.terminale.scarto
        for strumento in PUNTO:
            self.basi[strumento] = self.terminale.orarie(strumento, ORARIE)
        if self.stato.ultimo_giro is None:
            self.stato.ultimo_giro = _ora(time.time())
        self.stato.salva(CARTELLA)
        riavvio = CARTELLA / "riavvio"
        if riavvio.exists():
            self.tg.operativo(f"🔄 Aggiornato e ripartito: {riavvio.read_text(encoding='utf-8')}")
            riavvio.unlink()
        else:
            self.tg.operativo(messaggi.avvio(conto.login, conto.server, conto.saldo, conto.valuta, list(PUNTO), self.terminale.scarto))

    def minuto(self) -> None:
        self.stato.vive, fatti = self.esecutore.sorveglia(self.stato.vive)
        for f in fatti:
            (self.tg.equipe if f.equipe else self.tg.operativo)(f.testo)
            registra(CARTELLA, "sorveglianza", testo=f.testo)
        adesso = time.time()
        ora = _ora(adesso)
        if ora > self.stato.ultimo_giro and adesso - ora >= RITARDO_GIRO:
            self.giro(ora)
            self.stato.salva(CARTELLA)
            try:
                titolo = _versione_nuova()
            except Exception as errore:
                titolo = ""
                self.allarme(f"non riesco a controllare se c'è una versione nuova: {type(errore).__name__}")
            if titolo:
                self.stato.salva(CARTELLA)
                (CARTELLA / "riavvio").write_text(titolo, encoding="utf-8")
                sys.exit(AGGIORNATO)
        oggi = datetime.fromtimestamp(adesso, tz=timezone.utc)
        settimana = f"{oggi.isocalendar().year}-S{oggi.isocalendar().week:02d}"
        if oggi.weekday() == 5 and oggi.hour >= 8 and self.stato.ultima_riunione != settimana:
            self.riunione(settimana, int(adesso))
        self.stato.salva(CARTELLA)

    def giro(self, ora: int) -> None:
        for strumento in PUNTO:
            self.basi[strumento] = _unisci(self.basi[strumento], self.terminale.orarie(strumento, 50))
        self.stato.scarto = self.terminale.scarto
        dal = max(self.stato.ultimo_giro + 1, ora - 86400)
        conto = self.terminale.conto()
        for d in giro_orario(self.basi, dal, ora, self.capo):
            per = spinte(self.capo, d.x)
            self.tg.equipe(messaggi.pareri(d) + "\n\n" + discussione(per, d.entra, d.atteso))
            in_tempo = ora - d.r.quando <= 3600
            aperta = False
            if d.entra and in_tempo:
                viva, fatto = self.esecutore.apri(d, conto)
                (self.tg.equipe if fatto.equipe else self.tg.operativo)(fatto.testo)
                if viva is not None:
                    self.stato.vive.append(viva)
                    aperta = True
                    conto = self.terminale.conto()
            elif d.entra:
                self.tg.equipe(messaggi.saltata(d, "è scattata mentre il bot era spento"))
            op = d.op
            s = Seguita(d.chiave, d.r.strumento, d.r.alto_tf.value, d.r.basso_tf.value, d.r.verso.value, d.r.quando,
                        op.ingresso, op.stop, op.tp1, op.tp2, d.scadenza, aperta,
                        [float(v) for v in d.x], d.r.rr1, d.r.rr2, d.r.costo_erre, d.p1, d.q, d.atteso,
                        spinte=per, leggibile=f"{d.r.strumento} {d.r.verso.value.upper()}, {messaggi.coppia(d)}, {messaggi.quando(d.r.quando)}")
            self.stato.seguite.append(s)
            registra(CARTELLA, "decisione", chiave=d.chiave, entra=d.entra, aperta=aperta, p1=d.p1, q=d.q,
                     atteso=d.atteso, x=s.x, ingresso=op.ingresso, stop=op.stop, tp1=op.tp1, tp2=op.tp2)
        for s in segui(self.stato.seguite, self.basi, ora):
            testo, ragione, torto = resoconto(s.leggibile or s.chiave, s.esito, s.entrata, s.spinte, s.atteso)
            self.tg.equipe(testo)
            aggiorna_pagelle(self.stato.pagelle, ragione, torto)
            registra(CARTELLA, "finita sulla carta", chiave=s.chiave, ragione=ragione, torto=torto, **s.esito)
        # Le seguite finite da piu' di un anno non servono piu' qui: stanno nel registro.
        self.stato.seguite = [s for s in self.stato.seguite if s.esito is None or s.esito["quando"] > ora - 365 * 86400]
        self.stato.ultimo_giro = ora

    def riunione(self, settimana: str, adesso: int) -> None:
        storico = Storico.carica(RADICE / "nvm" / "vivo" / "storico.npz")
        testo, nuovo, parte = riunione(self.stato.seguite, self.capo, storico, adesso - 7 * 86400, settimana,
                                       self.stato.pagelle, self.esecutore.parte)
        self.tg.equipe(testo)
        self.capo, self.esecutore.parte = nuovo, parte
        CARTELLA.mkdir(parents=True, exist_ok=True)
        (CARTELLA / "capo.json").write_text(json.dumps(nuovo.come_dati()), encoding="utf-8")
        (CARTELLA / "rischio.json").write_text(json.dumps({"parte": parte}), encoding="utf-8")
        registra(CARTELLA, "riunione", settimana=settimana, testo=testo)
        self.stato.ultima_riunione = settimana


def main() -> None:
    bot = Bot()
    try:
        bot.avvia()
    except ErroreMT5 as errore:
        bot.tg.operativo(messaggi.allarme(f"Non parto: {errore}"))
        sys.exit(1)
    while True:
        try:
            bot.minuto()
        except ErroreMT5 as errore:
            bot.allarme(f"MT5: {errore}")
            try:
                bot.terminale.connetti()
            except ErroreMT5:
                pass
        except SystemExit:
            raise
        except Exception as errore:
            bot.allarme(f"errore nel bot: {errore!r}")
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        time.sleep(60 - time.time() % 60 + 1)


if __name__ == "__main__":
    main()
