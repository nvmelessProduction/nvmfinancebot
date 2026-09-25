"""Il bot dal vivo, sul conto demo. Si avvia con `avvia.bat` sulla VPS.

    python vivo.py

Ogni minuto sorveglia le posizioni aperte (pareggio, chiusure). Ogni quarto
d'ora guarda la coppia 4 ore -> 15 minuti; ogni ora le altre tre: il
Cacciatore dice quali CRT si sono armati, a ogni Model#1 l'equipe si
confronta, il Capo decide, il Rischio sceglie la puntata, l'Esecutore apre.
Quando un'operazione finisce (presa o sulla carta) si vede chi aveva
ragione e chi ha sbagliato dice come migliorare. Ogni due minuti guarda se
su GitHub c'e' una versione nuova. Il sabato mattina la riunione col Capo.

Chiude con il codice 3 quando si e' aggiornato: `avvia.bat` lo riavvia.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from nvm.agenti import manopole
from nvm.agenti.capo import Capo
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO, Minuti
from nvm.tempo import TF
from nvm.vivo import messaggi
from nvm.vivo.ambiente import impostazioni
from nvm.vivo.carta import segui
from nvm.vivo.dialogo import (
    aggiorna_diario, aggiorna_pagelle, come_migliorare, presentazioni, resoconto, spinte,
)
from nvm.vivo.esecutore import MAGIC, Esecutore
from nvm.vivo.giro import COPPIA_VELOCE, COPPIE, armati
from nvm.vivo.giro import giro as giro_orario
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.romeo_vivo import confronta as confronta_con_romeo
from nvm.vivo.romeo_vivo import leggi_comando
from nvm.prova.allenamento import leggi_memoria
from nvm.vivo.stato import Seguita, Stato, registra
from nvm.vivo.telegram import Telegram
from nvm.vivo.terminale import ErroreMT5, Terminale

RADICE = Path(__file__).resolve().parent
CARTELLA = RADICE / "dati" / "vivo"
RAMO = "claude/zealous-albattani-394cd9"
ORARIE = 13000          # circa due anni: servono al key level del mensile
QUARTI = 4000           # circa sei settimane di quarti d'ora: il 4 ore e il giornaliero sopra
RITARDO_GIRO = 5        # secondi dopo la chiusura, per dare al broker il tempo di chiudere la barra
AGGIORNATO = 3          # codice d'uscita: "mi sono aggiornato, riavviami"
CONTROLLO_VERSIONE = 120  # ogni quanti secondi guarda su GitHub se c'e' una versione nuova
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


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=RADICE, capture_output=True, text=True, timeout=120, check=True).stdout.strip()


def _versione() -> str:
    try:
        return _git("rev-parse", "HEAD")
    except Exception:
        return ""


def _versione_nuova(partito_da: str) -> str:
    """Se su GitHub c'e' una versione nuova la scarica. Se il codice su disco e'
    diverso da quello con cui il bot e' partito (anche per un `git pull` fatto a
    mano) ne restituisce il titolo, e il bot si riavvia; se cambiano solo
    documenti, ''."""
    _git("fetch", "-q", "origin", RAMO)
    if _git("rev-parse", "HEAD") != _git("rev-parse", "FETCH_HEAD"):
        _git("merge", "-q", "--ff-only", "FETCH_HEAD")
    adesso = _git("rev-parse", "HEAD")
    if not partito_da or adesso == partito_da:
        return ""
    cambiati = _git("diff", "--name-only", partito_da, adesso).splitlines()
    if not any(c.endswith(DA_RIAVVIO) for c in cambiati):
        return ""
    return _git("log", "-1", "--format=%s")


class Bot:
    def __init__(self) -> None:
        # Le manopole che gli agenti hanno scelto nell'ultimo allenamento (`nvm/vivo/agenti.json`).
        manopole.carica_e_applica()
        self.imp = impostazioni(RADICE)
        self.tg = Telegram(self.imp)
        self.stato = Stato.carica(CARTELLA)
        self.capo = Capo.da_dati(_leggi("capo.json"))
        self.terminale = Terminale(self.imp.suffisso)
        self.esecutore = Esecutore(self.terminale, float(_leggi("rischio.json")["parte"]))
        self.storico = Storico.carica(RADICE / "nvm" / "vivo" / "storico.npz")
        self.versione = _versione()
        self.basi: dict[str, Minuti] = {}
        self.fini: dict[str, Minuti] = {}
        self._allarmi: dict[str, float] = {}
        self._ultimo_controllo = 0.0

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
            self.tg.operativo(messaggi.aggiornato(riavvio.read_text(encoding="utf-8")))
            riavvio.unlink()
        else:
            self.tg.operativo(messaggi.avvio(conto.login, conto.server, conto.saldo, conto.valuta, list(PUNTO), self.terminale.scarto))
        self.prova_collegamento(solo_se_non_va=da_aggiornamento)
        if not self.imp.chat_equipe:
            self.tg.operativo(messaggi.allarme(
                "Il canale équipe non è impostato: nel file .env manca la riga TELEGRAM_CHAT_EQUIPE= con l'id del "
                "canale. Finché manca, l'équipe parla solo sullo schermo della VPS."))
        # Gli agenti si presentano a ogni avvio a mano, e la prima volta dopo un aggiornamento.
        if not da_aggiornamento or not presentati.exists():
            for testo in presentazioni(self.stato.pagelle, self.capo, self.esecutore.parte, self.storico.romeo_x):
                self.tg.equipe(testo)
            presentati.write_text("sì", encoding="utf-8")
        self.racconta_allenamento()

    def racconta_allenamento(self) -> None:
        """Il rapporto dell'ultimo allenamento degli agenti, una volta sola, sul canale equipe."""
        ultimo = leggi_memoria().get("ultimo", {})
        # Ogni allenamento ha il suo numero: due nella stessa settimana si raccontano tutti e due.
        chi = str(ultimo.get("id", ultimo.get("settimana", "")))
        if chi and ultimo.get("rapporto") and chi != self.stato.ultimo_allenamento:
            self.tg.equipe(ultimo["rapporto"])
            self.stato.ultimo_allenamento = chi
            self.stato.salva(CARTELLA)

    def prova_collegamento(self, solo_se_non_va: bool = False) -> None:
        """A ogni avvio: MT5 accetterebbe un ordine su ogni strumento? Lo dice sul
        canale operativo; dopo un aggiornamento, solo se qualcosa non va."""
        prove = []
        for strumento in PUNTO:
            try:
                e = self.terminale.prova_ordine(strumento, MAGIC)
                prove.append((strumento, e.ok, e.messaggio))
            except Exception as errore:
                prove.append((strumento, False, f"errore: {errore}"))
        try:
            aperte = len(self.terminale.aperte(MAGIC))
        except ErroreMT5:
            aperte = 0
        if not solo_se_non_va or not all(ok for _, ok, _ in prove):
            self.tg.operativo(messaggi.collegamento(prove, aperte))
        registra(CARTELLA, "collegamento", prove=prove, aperte=aperte)

    # --- il giro di ogni minuto ---

    def minuto(self) -> None:
        self.ascolta()
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
        oggi = datetime.fromtimestamp(adesso, tz=timezone.utc)
        settimana = f"{oggi.isocalendar().year}-S{oggi.isocalendar().week:02d}"
        if oggi.weekday() == 5 and oggi.hour >= 8 and self.stato.ultima_riunione != settimana:
            self.riunione(settimana, int(adesso))
        self.stato.salva(CARTELLA)
        if adesso - self._ultimo_controllo >= CONTROLLO_VERSIONE:
            self._ultimo_controllo = adesso
            self.aggiorna_se_serve()

    def ascolta(self) -> None:
        """I comandi arrivati sui canali del bot: per ora solo /romeo, le entrate
        di Romeo che l'utente vede sul suo canale (`nvm/vivo/romeo_vivo.py`)."""
        try:
            arrivati, self.stato.telegram_dal = self.tg.ricevi(self.stato.telegram_dal)
        except Exception as errore:
            self.allarme(f"non riesco a leggere i messaggi di Telegram: {errore}")
            return
        for m in arrivati:
            if not m.testo.lower().startswith("/romeo"):
                continue
            e = leggi_comando(m.testo, m.quando or int(time.time()))
            if isinstance(e, str):
                self.tg.equipe(messaggi.romeo_non_letta(e))
                continue
            s = confronta_con_romeo(e, self.stato.seguite)
            self.stato.romeo.append(e)
            self.tg.equipe(messaggi.romeo_ricevuta(e, s))
            registra(CARTELLA, "romeo dal vivo", **asdict(e))

    def aggiorna_se_serve(self) -> None:
        """Se su GitHub c'e' codice nuovo, lo prende ed esce per farsi riavviare
        da `avvia.bat`. Lo stato e' gia' salvato: il bot riparte da dov'era."""
        try:
            titolo = _versione_nuova(self.versione)
        except Exception as errore:
            titolo = ""
            self.allarme(f"non riesco a controllare se c'è una versione nuova: {type(errore).__name__}")
        if titolo:
            (CARTELLA / "riavvio").write_text(titolo, encoding="utf-8")
            sys.exit(AGGIORNATO)

    def giro_veloce(self, quarto: int) -> None:
        """La coppia 4 ore -> 15 minuti, ogni quarto d'ora."""
        for strumento in PUNTO:
            self.fini[strumento] = _unisci(self.fini[strumento], self.terminale.barre(strumento, 20, 900), QUARTI)
        dal = max(self.stato.ultimo_quarto + 1, quarto - 86400)
        self._decidi(giro_orario(self.fini, dal, quarto, self.capo, (COPPIA_VELOCE,), self.basi), quarto, 900)
        self.uscite(quarto)
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
        self.uscite(ora)
        for s in segui(self.stato.seguite, self.basi, ora, self.fini):
            self._finita(s)
        # Le seguite finite da piu' di un anno non servono piu' qui: stanno nel registro.
        self.stato.seguite = [s for s in self.stato.seguite if s.esito is None or s.esito["quando"] > ora - 365 * 86400]
        self.stato.ultimo_giro = ora

    def uscite(self, adesso: int) -> None:
        """Le uscite prima dello stop che gli agenti hanno imparato: idea invalidata o troppo lenta."""
        for v in self.stato.vive:
            if not (v.invalida_candele or v.tempo_candele) or not v.basso:
                continue
            sorgente = self.fini if TF(v.basso) is TF.M15 else self.basi
            if v.strumento not in sorgente:
                continue
            basse = costruisci(sorgente[v.strumento], TF(v.basso)).chiuse_entro(adesso)
            fatto = self.esecutore.uscita_anticipata(v, basse)
            if fatto is not None:
                (self.tg.equipe if fatto.equipe else self.tg.operativo)(fatto.testo)
                registra(CARTELLA, "uscita anticipata", chiave=v.chiave, motivo=v.uscita_anticipata)

    def _decidi(self, decisioni, adesso: int, finestra: int) -> None:
        conto = self.terminale.conto() if decisioni else None
        # Prima gli ordini, poi i messaggi: il mercato non aspetta Telegram.
        aperte, da_dire = set(), []
        for d in decisioni:
            if d.entra and adesso - d.r.quando <= finestra:
                viva, fatto = self.esecutore.apri(d, conto)
                da_dire.append(fatto)
                if viva is not None:
                    self.stato.vive.append(viva)
                    aperte.add(d.chiave)
                    conto = self.terminale.conto()
        for fatto in da_dire:
            (self.tg.equipe if fatto.equipe else self.tg.operativo)(fatto.testo)
        for d in decisioni:
            per = spinte(self.capo, d.x)
            self.tg.equipe(messaggi.pareri(d, per))
            aperta = d.chiave in aperte
            if d.entra and adesso - d.r.quando > finestra:
                self.tg.equipe(messaggi.saltata(d, "è scattata mentre il bot era spento"))
            op = d.op
            s = Seguita(d.chiave, d.r.strumento, d.r.alto_tf.value, d.r.basso_tf.value, d.r.verso.value, d.r.quando,
                        op.ingresso, op.stop, op.tp1, op.tp2, d.scadenza, aperta,
                        [float(v) for v in d.x], d.r.rr1, d.r.rr2, d.r.costo_erre, d.p1, d.q, d.atteso,
                        spinte=per, leggibile=f"{d.r.strumento} {messaggi.direzione(d.r.verso)} · {messaggi.coppia(d)} · {messaggi.quando(d.r.quando)}",
                        romeo=1.0 if d.romeo is None else d.romeo, pareggio_a=op.pareggio_a, livello=op.livello_model1,
                        invalida_candele=op.invalida_candele, tempo_candele=op.tempo_candele)
            self.stato.seguite.append(s)
            registra(CARTELLA, "decisione", chiave=d.chiave, entra=d.entra, aperta=aperta, p1=d.p1, q=d.q,
                     atteso=d.atteso, romeo=d.romeo, x=s.x, spinte=per, ingresso=op.ingresso, stop=op.stop, tp1=op.tp1, tp2=op.tp2)

    def _finita(self, s: Seguita) -> None:
        testo, ragione, torto = resoconto(s.leggibile or s.chiave, s.esito, s.entrata, s.spinte, s.atteso)
        aggiorna_pagelle(self.stato.pagelle, ragione, torto)
        aggiorna_diario(self.stato.diario, s.x, s.esito["erre"] > 0)
        migliorare = come_migliorare(torto, self.stato.diario, s.x)
        self.tg.equipe(testo + ("\n\n" + migliorare if migliorare else ""))
        registra(CARTELLA, "finita sulla carta", chiave=s.chiave, ragione=ragione, torto=torto, **s.esito)

    def riunione(self, settimana: str, adesso: int) -> None:
        testo, nuovo, parte = riunione(self.stato.seguite, self.capo, self.storico, adesso - 7 * 86400, settimana,
                                       self.stato.pagelle, self.esecutore.parte, self.stato.diario, self.stato.romeo)
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
        time.sleep(attesa(time.time()))


def attesa(adesso: float) -> float:
    """Fino al prossimo minuto, o prima se una candela da un quarto d'ora chiude prima:
    il bot decide pochi secondi dopo la chiusura, non fino a un minuto dopo."""
    prossimo_minuto = 60 - adesso % 60 + 1
    prossimo_quarto = 900 - adesso % 900 + RITARDO_GIRO
    if prossimo_quarto > 900:            # siamo appena dopo la chiusura: il giro e' questo
        prossimo_quarto -= 900
    return max(0.5, min(prossimo_minuto, prossimo_quarto))


if __name__ == "__main__":
    main()
