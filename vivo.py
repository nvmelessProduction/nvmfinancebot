"""Il bot dal vivo, sul conto demo. Si avvia con `avvia.bat` sulla VPS.

    python vivo.py

Ogni minuto sorveglia le posizioni aperte (pareggio, chiusure). Ogni quarto
d'ora guarda la coppia 4 ore -> 15 minuti; ogni ora le altre tre: il
Cacciatore dice quali CRT si sono armati, a ogni Model#1 l'equipe si
confronta, il Capo decide, il Rischio sceglie la puntata, l'Esecutore apre.
Quando un'operazione finisce (presa o sulla carta) si vede chi aveva
ragione e chi ha sbagliato dice come migliorare. Poi guarda se su GitHub
c'e' una versione nuova. Il sabato mattina la riunione col Capo.

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
from nvm.vivo.dialogo import (
    aggiorna_diario, aggiorna_pagelle, come_migliorare, discussione_con_prove, presentazioni, prove, resoconto, spinte,
)
from nvm.vivo.esecutore import Esecutore
from nvm.vivo.giro import COPPIA_VELOCE, COPPIE, armati
from nvm.vivo.giro import giro as giro_orario
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.stato import Seguita, Stato, registra
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import ErroreMT5, Terminale

RADICE = Path(__file__).resolve().parent
CARTELLA = RADICE / "dati" / "vivo"
RAMO = "claude/zealous-albattani-394cd9"
ORARIE = 13000          # circa due anni: servono al key level del mensile
QUARTI = 4000           # circa sei settimane di quarti d'ora: il 4 ore e il giornaliero sopra
RITARDO_GIRO = 20       # secondi dopo la chiusura, per dare al broker il tempo di chiudere la barra
AGGIORNATO = 3          # codice d'uscita: "mi sono aggiornato, riavviami"
# I file che, se cambiano, chiedono di riavviare il bot. Il resto (documenti,
# registro, casi) si aggiorna in silenzio.
DA_RIAVVIO = (".py", ".json", ".npz", ".bat", ".txt")


def _su(t: float, passo: int) -> int:
    return int(t) // passo * passo


def _unisci(base: Minuti, nuove: Minuti, quante: int) -> Minuti:
    if not len(nuove):
        return base
    vecchie = base.fra(int(base.t[0]), int(nuove.t[0])) if len(base) else base
    tutte = Minuti.unisci([m for m in (vecchie, nuove) if len(m)])
    return tutte.fra(int(tutte.t[max(0, len(tutte) - quante)]), int(tutte.t[-1]) + 1)


def _leggi(nome: str) -> dict:
    """Prima quello riaddestrato dal vivo; se manca o e' di una versione vecchia, quello del repository."""
    for p in (CARTELLA / nome, RADICE / "nvm" / "vivo" / nome):
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if nome != "capo.json":
                return d
            try:
                Capo.da_dati(d)
                return d
            except ValueError:
                continue
    raise FileNotFoundError(nome)


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
        self.capo = Capo.da_dati(_leggi("capo.json"))
        self.terminale = Terminale(self.imp.suffisso)
        self.esecutore = Esecutore(self.terminale, float(_leggi("rischio.json")["parte"]))
        self.storico = Storico.carica(RADICE / "nvm" / "vivo" / "storico.npz")
        self.basi: dict[str, Minuti] = {}
        self.fini: dict[str, Minuti] = {}
        self._allarmi: dict[str, float] = {}

    def allarme(self, testo: str) -> None:
        """Un allarme sul canale operativo, al massimo una volta l'ora per lo stesso testo."""
        if time.time() - self._allarmi.get(testo, 0) > 3600:
            self._allarmi[testo] = time.time()
            self.tg.operativo(messaggi.allarme(testo))

    # --- avvio ---

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
            self.fini[strumento] = self.terminale.barre(strumento, QUARTI, 900)
        adesso = time.time()
        if self.stato.ultimo_giro is None:
            self.stato.ultimo_giro = _su(adesso, 3600)
        if self.stato.ultimo_quarto is None:
            self.stato.ultimo_quarto = _su(adesso, 900)
        self.stato.salva(CARTELLA)
        riavvio = CARTELLA / "riavvio"
        presentati = CARTELLA / "presentati"
        da_aggiornamento = riavvio.exists()
        if da_aggiornamento:
            self.tg.operativo(f"🔄 Aggiornato e ripartito: {riavvio.read_text(encoding='utf-8')}")
            riavvio.unlink()
        else:
            self.tg.operativo(messaggi.avvio(conto.login, conto.server, conto.saldo, conto.valuta, list(PUNTO), self.terminale.scarto))
        if not self.imp.chat_equipe:
            self.tg.operativo(messaggi.allarme(
                "Il canale équipe non è impostato: nel file .env manca la riga TELEGRAM_CHAT_EQUIPE= con l'id del "
                "canale. Finché manca, l'équipe parla solo sullo schermo della VPS."))
        # Gli agenti si presentano a ogni avvio a mano, e la prima volta dopo un aggiornamento.
        if not da_aggiornamento or not presentati.exists():
            for testo in presentazioni(self.stato.pagelle, self.capo, self.esecutore.parte):
                self.tg.equipe(testo)
            presentati.write_text("sì", encoding="utf-8")

    # --- il giro di ogni minuto ---

    def minuto(self) -> None:
        self.stato.vive, fatti = self.esecutore.sorveglia(self.stato.vive)
        for f in fatti:
            (self.tg.equipe if f.equipe else self.tg.operativo)(f.testo)
            registra(CARTELLA, "sorveglianza", testo=f.testo)
        adesso = time.time()
        quarto = _su(adesso, 900)
        if quarto > self.stato.ultimo_quarto and adesso - quarto >= RITARDO_GIRO:
            self.giro_veloce(quarto)
        ora = _su(adesso, 3600)
        if ora > self.stato.ultimo_giro and adesso - ora >= RITARDO_GIRO:
            self.giro(ora)
            self.stato.salva(CARTELLA)
            try:
                titolo = _versione_nuova()
            except Exception as errore:
                titolo = ""
                self.allarme(f"non riesco a controllare se c'è una versione nuova: {type(errore).__name__}")
            if titolo:
                (CARTELLA / "riavvio").write_text(titolo, encoding="utf-8")
                sys.exit(AGGIORNATO)
        oggi = datetime.fromtimestamp(adesso, tz=timezone.utc)
        settimana = f"{oggi.isocalendar().year}-S{oggi.isocalendar().week:02d}"
        if oggi.weekday() == 5 and oggi.hour >= 8 and self.stato.ultima_riunione != settimana:
            self.riunione(settimana, int(adesso))
        self.stato.salva(CARTELLA)

    def giro_veloce(self, quarto: int) -> None:
        """La coppia 4 ore -> 15 minuti, ogni quarto d'ora."""
        for strumento in PUNTO:
            self.fini[strumento] = _unisci(self.fini[strumento], self.terminale.barre(strumento, 20, 900), QUARTI)
        dal = max(self.stato.ultimo_quarto + 1, quarto - 86400)
        self._decidi(giro_orario(self.fini, dal, quarto, self.capo, (COPPIA_VELOCE,)), quarto, 900)
        self.stato.ultimo_quarto = quarto

    def giro(self, ora: int) -> None:
        for strumento in PUNTO:
            self.basi[strumento] = _unisci(self.basi[strumento], self.terminale.orarie(strumento, 50), ORARIE)
        self.stato.scarto = self.terminale.scarto
        dal = max(self.stato.ultimo_giro + 1, ora - 86400)
        nuovi = armati(self.basi, dal, ora, COPPIE) + armati(self.fini, dal, ora, (COPPIA_VELOCE,))
        if nuovi:
            self.tg.equipe(messaggi.armati(nuovi))
        self._decidi(giro_orario(self.basi, dal, ora, self.capo, COPPIE), ora, 3600)
        for s in segui(self.stato.seguite, self.basi, ora, self.fini):
            self._finita(s)
        # Le seguite finite da piu' di un anno non servono piu' qui: stanno nel registro.
        self.stato.seguite = [s for s in self.stato.seguite if s.esito is None or s.esito["quando"] > ora - 365 * 86400]
        self.stato.ultimo_giro = ora

    def _decidi(self, decisioni, adesso: int, finestra: int) -> None:
        conto = self.terminale.conto() if decisioni else None
        for d in decisioni:
            per = spinte(self.capo, d.x)
            argomenti = prove(d.x, self.storico.x, self.storico.erre) if self.storico.erre is not None else {}
            self.tg.equipe(messaggi.pareri(d) + "\n\n" + discussione_con_prove(per, d.entra, d.atteso, argomenti))
            aperta = False
            if d.entra and adesso - d.r.quando <= finestra:
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
                     atteso=d.atteso, x=s.x, spinte=per, ingresso=op.ingresso, stop=op.stop, tp1=op.tp1, tp2=op.tp2)

    def _finita(self, s: Seguita) -> None:
        testo, ragione, torto = resoconto(s.leggibile or s.chiave, s.esito, s.entrata, s.spinte, s.atteso)
        aggiorna_pagelle(self.stato.pagelle, ragione, torto)
        aggiorna_diario(self.stato.diario, s.x, s.esito["erre"] > 0)
        migliorare = come_migliorare(torto, self.stato.diario, s.x)
        self.tg.equipe(testo + ("\n\n" + migliorare if migliorare else ""))
        registra(CARTELLA, "finita sulla carta", chiave=s.chiave, ragione=ragione, torto=torto, **s.esito)

    def riunione(self, settimana: str, adesso: int) -> None:
        testo, nuovo, parte = riunione(self.stato.seguite, self.capo, self.storico, adesso - 7 * 86400, settimana,
                                       self.stato.pagelle, self.esecutore.parte, self.stato.diario)
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
