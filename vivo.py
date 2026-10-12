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
import os
import secrets
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.agenti import foto, livelli, manopole
from nvm.agenti.cacciatore import Verso
from nvm.agenti.grilletto import MODELLI_ROMEO, apertura_romeo, kod_superato
from nvm.agenti.capo import Capo
from nvm.agenti.rischio import USCITE
from nvm.cervello import dal_vivo
from nvm.intelligenti import al_lavoro, fine_settimana, pareri
from nvm.intelligenti.squadra import MANCA_IN_PAROLE
from nvm.vivo import libro
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import NEW_YORK, TF
from nvm.vivo import autoanalisi, conversazione, disegni, foto_grafico, messaggi
from nvm.vivo.ambiente import impostazioni, leggi_env
from nvm.vivo.carta import segui
from nvm.vivo.dialogo import (
    aggiorna_diario, aggiorna_pagelle, resoconto, spinte,
)
from nvm.vivo.esecutore import MAGIC, Esecutore
from nvm.vivo import giro as _giro_modulo
from nvm.vivo.giro import COPPIA_VELOCE, COPPIE
from nvm.vivo.giro import giro as giro_orario
from nvm.vivo.riunione import Storico, riunione
from nvm.vivo.romeo_vivo import confronta as confronta_con_romeo
from nvm.vivo.romeo_vivo import leggi_comando
from nvm.prova.allenamento import leggi_memoria
from nvm.vivo.stato import Seguita, Stato, archivia, archiviate, registra
from nvm.vivo.telegram import Telegram, raggruppa
from nvm.vivo.terminale import ErroreMT5, Terminale
from nvm.vivo.tradingview import Accesso, ErroreTradingView, Fonte, TradingView

RADICE = Path(__file__).resolve().parent
# Gli strumenti su cui il bot opera dal vivo, sul conto demo: tutti quelli che conosce
# (`nvm/dati/strumenti.py`: forex, oro e argento, petrolio, indici, crypto) che il broker ha.
# L'utente, 25/09/2026: "testare tutto sul live sempre su mt5". Il proprietario, 07/10/2026: *"togliamo ukoil
# uk100 jpn225, per il resto tutto ok"*.
# Tolti dal proprietario: Brent, FTSE e Nikkei (07/10/2026); BTC ed ETH (08/10/2026).
TOLTI = ("UKOIL", "UK100", "JPN225", "BTCUSD", "ETHUSD")
STRUMENTI_VIVO = tuple(s for s in STRUMENTI if s not in TOLTI)
# Per quanto le decisioni finite restano nello stato, prima dell'archivio.
TENERE = 14 * 86400
CARTELLA = RADICE / "dati" / "vivo"
RAMO = "claude/zealous-albattani-394cd9"
ORARIE = 13000          # circa due anni: servono al key level del mensile
QUARTI = 4000           # circa sei settimane di quarti d'ora: il 4 ore e il giornaliero sopra
LUNGHE = 7000           # circa 25 anni di giornaliere: i 3, 6 e 12 mesi del metodo delle foto
RITARDO_GIRO = 5        # secondi dopo la chiusura, per dare al broker il tempo di chiudere la barra
AGGIORNATO = 3          # codice d'uscita: "mi sono aggiornato, riavviami"
CONTROLLO_VERSIONE = 120  # ogni quanti secondi guarda su GitHub se c'e' una versione nuova
RITARDO_MASSIMO = 600     # metodo delle foto: oltre 10 minuti dall'apertura della candela 3 non si entra piu'
# Telegram accetta didascalie fino a 1024 caratteri: il messaggio d'apertura ci sta, se no parte subito dopo la foto.
DIDASCALIA = 1000
# Analisi su TradingView: per quanto vale una proposta (Apri / Lascia) dall'apertura della candela 3, e il grafico del
# dollaro se nel .env non c'e' TRADINGVIEW_DXY.
VALIDITA_PROPOSTA = 1800
DXY_TRADINGVIEW = "TVC:DXY"
# I file che, se cambiano, chiedono di riavviare il bot. Il resto (documenti,
# registro, casi) si aggiorna in silenzio.
DA_RIAVVIO = (".py", ".json", ".npz", ".bat", ".txt")


def il_metodo() -> str:
    """Il metodo con cui nascono le occasioni (`nvm/vivo/giro.METODO`)."""
    return _giro_modulo.METODO


def _da(candele, k: int):
    """Le candele dalla `k`-esima in poi."""
    from nvm.dati.candele import Candele
    return Candele(candele.strumento, candele.tf, candele.inizio[k:], candele.fine[k:], candele.bid[k:],
                   candele.ask[k:], candele.volume[k:])


def _su(t: float, passo: int) -> int:
    return int(t) // passo * passo


def _unisci(base: Minuti, nuove: Minuti, quante: int) -> Minuti:
    if not len(nuove):
        return base
    vecchie = base.fra(int(base.t[0]), int(nuove.t[0])) if len(base) else base
    tutte = Minuti.unisci([m for m in (vecchie, nuove) if len(m)])
    return tutte.fra(int(tutte.t[max(0, len(tutte) - quante)]), int(tutte.t[-1]) + 1)


def di(testo: str) -> None:
    """Una riga nella finestra di `avvia.bat`, con l'ora: si vede a che punto e' il bot (il resto lo scrive su
    Telegram). Una scritta non deve mai fermare il bot."""
    try:
        print(f"{datetime.now():%d/%m %H:%M:%S}  {testo}", flush=True)
    except Exception:
        pass


def _leggi(nome: str) -> dict:
    """Prima quello riaddestrato dal vivo; se manca o e' di una versione vecchia, quello del repository.
    Per il Rischio vale il piu' recente dei due: si riallena sia qui il sabato sia in palestra."""
    if nome == "rischio.json":
        letti = [json.loads(p.read_text(encoding="utf-8")) for p in (CARTELLA / nome, RADICE / "nvm" / "vivo" / nome)
                 if p.exists()]
        if not letti:
            raise FileNotFoundError(nome)
        return max(letti, key=lambda d: d.get("quando", 0))
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
        # I messaggi dell'equipe di un giro: partono insieme alla fine, in pochi messaggi.
        self._da_dire: list[str] = []
        # Gli strumenti su cui si opera davvero: quelli di STRUMENTI_VIVO che il broker ha (si vede all'avvio).
        self.strumenti: list[str] = list(STRUMENTI_VIVO)
        self.stato = Stato.carica(CARTELLA)
        self.capo = Capo.da_dati(_leggi("capo.json"))
        self.terminale = Terminale(self.imp.suffisso)
        rischio = _leggi("rischio.json")
        self.esecutore = Esecutore(self.terminale, float(rischio["parte"]), rischio.get("correlazioni"),
                                   float(rischio.get("minimo", 0.0)))
        self.storico = Storico.carica(RADICE / "nvm" / "vivo" / "storico.npz")
        # Le scelte del proprietario (per esempio: sul demo decidono i cervelli).
        scelte = RADICE / "nvm" / "vivo" / "scelte.json"
        self.scelte = json.loads(scelte.read_text(encoding="utf-8")) if scelte.exists() else {}
        # I cervelli degli agenti (`nvm/cervello/`): usciti da scuola, con tutto quello che hanno
        # imparato dal vivo. Se qualcosa non va, il bot lavora come prima, col Capo.
        try:
            self.cervelli, self.cervelli_info = dal_vivo.carica(RADICE / "nvm" / "vivo" / "cervelli.json", CARTELLA)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            self.cervelli, self.cervelli_info = None, {}
        # La squadra intelligente (`nvm/intelligenti/`): i nostri agenti con le regole di Romeo. Votano,
        # discutono, decidono da soli e imparano solo dal vivo. Niente AI esterne, niente vent'anni.
        try:
            self.squadra = al_lavoro.crea(CARTELLA, self.scelte)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            self.squadra = None
        self._verdetti: dict = {}
        # Le lezioni della squadra di oggi, per il riepilogo della sera.
        self._lezioni_oggi: list[str] = []
        # Le lezioni si scrivono in disparte: il giro non aspetta.
        self._diario = ThreadPoolExecutor(1)
        # Quante volte, per segnale, e' arrivato il primo obiettivo: le prove della conversazione.
        self._prove = None
        self.versione = _versione()
        self.basi: dict[str, Minuti] = {}
        self.fini: dict[str, Minuti] = {}
        # Il grafico del dollaro del broker (USDX su FP Markets): lo legge l'agente DXY, il bot non ci opera.
        self.dxy: Optional[Minuti] = None
        # Le giornaliere di tanti anni (per i 3, 6, 12 mesi del metodo delle foto) e il giorno in cui si sono prese.
        self.lunghe: dict[str, Minuti] = {}
        self._lunghe_del = 0
        self._allarmi: dict[str, float] = {}
        self._ultimo_controllo = 0.0
        # I disegni sul grafico di MT5 (`nvm/vivo/disegni.py`): pronti dopo il collegamento.
        self.disegni: Optional[disegni.Disegni] = None
        self._avviso_disegni = 0.0
        # Le foto dei grafici chieste a MT5 e non ancora arrivate (per vedere i disegni dal telefono).
        self._cartella_foto: Optional[Path] = None
        self._foto: list[dict] = []
        # Le foto delle operazioni appena aperte: si disegnano a fine giro, dopo tutti gli ordini.
        self._foto_da_fare: list = []
        # Le candele da TradingView (`nvm/vivo/tradingview.py`), se nel .env ci sono i grafici: senza, da MT5.
        self.fonte: Optional[Fonte] = None
        # Le proposte mandate con i pulsanti Apri / Lascia e non ancora decise: numero -> decisione.
        self.proposte: dict[str, dict] = {}

    @property
    def _fonte(self):
        """Da dove arrivano le candele: TradingView se e' acceso, se no MT5 (gli ordini vanno sempre su MT5)."""
        return getattr(self, "fonte", None) or self.terminale

    @property
    def _su_tradingview(self) -> bool:
        return getattr(self, "fonte", None) is not None

    def _accendi_tradingview(self) -> None:
        """Con i grafici di TradingView nel .env (TRADINGVIEW_SIMBOLI) il bot analizza li'. Le condizioni di
        TradingView vietano il trading automatico sui loro dati senza un permesso scritto: il bot propone, e apre
        solo col vostro «Apri»."""
        self.fonte = None
        if self.imp.tradingview_sbagliati:
            self.allarme("TradingView: questi grafici non li capisco: " + ", ".join(self.imp.tradingview_sbagliati) +
                         ". Nel .env scrivili come OANDA:EURUSD, o col nome del bot dopo l'uguale: OANDA:US30USD=US30.")
        if not self.imp.tradingview:
            return
        accesso = Accesso(CARTELLA)
        dxy = self.imp.tradingview_dxy or DXY_TRADINGVIEW
        self.fonte = Fonte(TradingView(accesso), list(self.imp.tradingview), dxy, self.imp.tradingview_totale)
        if not (CARTELLA / "riavvio").exists():
            # Dopo un aggiornamento non si ripete: lo si dice all'avvio a mano.
            self.tg.operativo(messaggi.tradingview_acceso([x for x, _ in self.imp.tradingview], dxy,
                                                          self.imp.tradingview_totale))
        if not accesso.pronto:
            self.allarme("TradingView: manca l'accesso. Sulla VPS fai doppio clic su tradingview_accesso.bat ed entra "
                         "col vostro account. Finché manca non analizzo niente; le operazioni aperte le seguo lo stesso.")

    def allarme(self, testo: str) -> None:
        """Un allarme sul canale operativo, al massimo una volta l'ora per lo stesso testo."""
        if time.time() - self._allarmi.get(testo, 0) > 3600:
            self._allarmi[testo] = time.time()
            di(f"Allarme: {testo}")
            self.tg.operativo(messaggi.allarme(testo))

    # --- avvio ---

    def avvia(self) -> None:
        di("Mi collego a MT5 (il terminale deve essere aperto e collegato al conto)...")
        self.terminale.connetti()
        conto = self.terminale.conto()
        di(f"Collegato: conto {conto.login} su {conto.server}, {conto.saldo:.2f} {conto.valuta}, "
           f"{'demo' if conto.demo else 'REALE'}.")
        if not conto.demo:
            di("Il conto è reale: il bot opera solo sul demo. Mi fermo.")
            self.tg.operativo(messaggi.allarme(
                f"Il conto {conto.login} è un conto reale: il bot opera solo sul demo. Mi fermo."))
            # Codice 2: fermo per scelta, avvia.bat non riparte da solo.
            sys.exit(FERMO)
        if self.stato.scarto is not None:
            self.terminale.scarto = self.stato.scarto
        di("Misuro l'ora del server del broker...")
        while self.terminale.misura_scarto("EURUSD") is None:
            self.allarme("Non so ancora l'ora del server del broker: aspetto che il mercato si muova.")
            time.sleep(60)
        self.stato.scarto = self.terminale.scarto
        di(f"Ora del server: UTC{self.terminale.scarto:+d}.")
        self._accendi_tradingview()
        # Su TradingView si guardano i grafici scelti nel .env; se no tutti quelli che il bot conosce.
        da_guardare = [n for _, n in self.imp.tradingview] if self._su_tradingview else list(STRUMENTI_VIVO)
        # Il broker puo' non avere tutti gli strumenti: quelli che mancano si saltano, e si dice quali.
        self.strumenti, mancanti = [], []
        for i, strumento in enumerate(da_guardare, 1):
            di(f"Scarico le candele: {i}/{len(da_guardare)} {strumento}")
            if not self.terminale.esiste(strumento):
                mancanti.append(strumento)
                continue
            try:
                self.basi[strumento] = self._fonte.orarie(strumento, ORARIE)
                self.fini[strumento] = self._fonte.barre(strumento, QUARTI, 900)
                self.strumenti.append(strumento)
            except ErroreMT5:
                mancanti.append(strumento)
            except ErroreTradingView as errore:
                # Si riprova a ogni giro: lo strumento resta fra quelli guardati.
                self.strumenti.append(strumento)
                self.allarme(f"TradingView: {errore}")
        # Le operazioni ancora aperte su strumenti tolti dalla lista: il bot le segue lo stesso fino alla fine.
        for v in self.stato.vive:
            if v.strumento not in self.strumenti:
                try:
                    self.terminale.esiste(v.strumento)
                except Exception:
                    registra(CARTELLA, "errore", testo=traceback.format_exc())
        if mancanti:
            di(f"Il broker non ha: {', '.join(mancanti)}.")
        di("Cerco il grafico del dollaro (USDX)...")
        self.aggiorna_dxy()
        if self.dxy is not None:
            di(f"Dollaro: leggo il grafico {self._fonte.simbolo('DXY')}.")
        self.aggiorna_totale()
        di("Scarico le giornaliere di tanti anni (3, 6 e 12 mesi)...")
        self.aggiorna_lunghe(time.time())
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
            self.tg.operativo(messaggi.avvio(conto.login, conto.server, conto.saldo, conto.valuta, list(self.strumenti), self.terminale.scarto))
        if mancanti:
            self.tg.operativo(messaggi.mancanti(mancanti, len(self.strumenti)))
        di("Mando il messaggio di avvio su Telegram e preparo disegni e foto...")
        self.prova_collegamento(solo_se_non_va=da_aggiornamento)
        self.prepara_disegni()
        self.prepara_foto()
        # La lista degli strumenti del broker, una volta sola (poi a richiesta con /strumenti).
        mandati_simboli = CARTELLA / "simboli_mandati"
        if not mandati_simboli.exists():
            try:
                self.manda_simboli()
                mandati_simboli.write_text("1", encoding="utf-8")
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
        if not self.imp.chat_equipe:
            self.tg.operativo(messaggi.allarme(
                "Il canale équipe non è impostato: nel file .env manca la riga TELEGRAM_CHAT_EQUIPE= con l'id del "
                "canale. Finché manca, l'équipe parla solo sullo schermo della VPS."))
        # All'avvio a mano, e la prima volta dopo questo aggiornamento, il Capo dice come lavora la squadra:
        # un messaggio solo, non una presentazione per agente.
        versione = "9" if self.squadra is not None else "2"
        if not da_aggiornamento or not presentati.exists() or presentati.read_text(encoding="utf-8") != versione:
            testo = (al_lavoro.benvenuto(len(self.strumenti)) if self.squadra is not None
                     else conversazione.benvenuto(len(self.strumenti)))
            self.tg.voci([conversazione.Voce("Capo", testo)])
            presentati.write_text(versione, encoding="utf-8")
        if self.squadra is None:
            # Gli allenamenti sui vent'anni si raccontano solo se decide il sistema di prima.
            self.racconta_allenamento()
            self.racconta_evoluzione()

    def aggiorna_lunghe(self, adesso: float) -> None:
        """Le giornaliere lunghe, una volta al giorno: senza, i 3, 6 e 12 mesi si fanno con le orarie (due anni)."""
        giorno = int(adesso // 86400)
        if giorno == self._lunghe_del:
            return
        self._lunghe_del = giorno
        for s in self.strumenti + (["DXY"] if getattr(self, "dxy", None) is not None else []) + \
                (["TOTAL"] if getattr(self, "totale", None) is not None else []):
            try:
                self.lunghe[s] = self._fonte.giornaliere(s, LUNGHE)
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())

    def aggiorna_dxy(self) -> None:
        """Il grafico del dollaro del broker (`terminale.GRAFICI`): all'avvio le ore di due anni, poi ogni ora le
        nuove. Se il conto non ce l'ha, l'agente DXY resta neutro e lo si dice (al massimo una volta l'ora)."""
        self.dxy = getattr(self, "dxy", None)
        try:
            if self.dxy is None:
                if self._fonte.esiste("DXY"):
                    self.dxy = self._fonte.orarie("DXY", ORARIE)
            else:
                self.dxy = _unisci(self.dxy, self._fonte.orarie("DXY", 50), ORARIE)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        if self.dxy is None and self._su_tradingview:
            self.allarme(f"TradingView: il grafico del dollaro ({self._fonte.simbolo('DXY')}) non arriva: l'agente DXY "
                         "resta neutro finché non c'è.")
        elif self.dxy is None:
            self.allarme("Sul conto non trovo il grafico del dollaro (USDX): l'agente DXY resta neutro finché non c'è.")

    def aggiorna_totale(self) -> None:
        """La TOTAL di TradingView (TRADINGVIEW_TOTAL), che guida BTC ed ETH: come il grafico del dollaro."""
        self.totale = getattr(self, "totale", None)
        if not self._su_tradingview or not self._fonte.esiste("TOTAL"):
            self.totale = None
            return
        try:
            self.totale = (self._fonte.orarie("TOTAL", ORARIE) if self.totale is None
                           else _unisci(self.totale, self._fonte.orarie("TOTAL", 50), ORARIE))
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        if self.totale is None:
            self.allarme(f"TradingView: il grafico della TOTAL ({self._fonte.simbolo('TOTAL')}) non arriva: BTC ed ETH "
                         "si guardano da soli finché non c'è.")

    def gemelli(self) -> dict[str, Minuti]:
        """Le ore di tutti gli strumenti e, se ci sono, del grafico del dollaro (chiave "DXY") e della TOTAL."""
        dxy, totale = getattr(self, "dxy", None), getattr(self, "totale", None)
        fuori = self.basi if dxy is None else {**self.basi, "DXY": dxy}
        return fuori if totale is None else {**fuori, "TOTAL": totale}

    def manda_simboli(self, canale: str = "operativo") -> None:
        """Tutti gli strumenti del broker, su Telegram (comando /strumenti), e nel registro (arriva a Claude con
        i dati della VPS)."""
        simboli = self.terminale.tutti_i_simboli()
        usati = {self.terminale.simbolo(s): s for s in self.strumenti}
        registra(CARTELLA, "simboli del broker", simboli=[list(x) for x in simboli], usati=usati)
        manda = self.tg.operativo if canale == "operativo" else self.tg.equipe
        for testo in messaggi.simboli_del_broker(simboli, usati):
            manda(testo)

    def prepara_disegni(self) -> None:
        """Installa e compila in MT5 il programma che disegna sul grafico, e lo dice una volta sola."""
        try:
            info = self.terminale.mt5.terminal_info()
            comune = Path(info.commondata_path) / "Files"
            fatto, problema = disegni.installa(RADICE, Path(info.data_path), Path(info.path))
            self._cartella_foto = Path(info.data_path) / "MQL5" / "Files"
            self.disegni = disegni.Disegni(CARTELLA, comune)
            self.disegni.scrivi(int(time.time()))
            avvisato = CARTELLA / "disegni_avvisato"
            if fatto and not avvisato.exists():
                self.tg.operativo(disegni.AVVISO)
                avvisato.write_text("1", encoding="utf-8")
            elif not fatto:
                self.allarme(problema)
            if fatto:
                self.aggiorna_disegni(int(time.time()))
                subito = CARTELLA / "disegni_subito"
                if not subito.exists():
                    self.tg.operativo(disegni.SUBITO)
                    subito.write_text("1", encoding="utf-8")
                telefono = CARTELLA / "disegni_telefono"
                if not telefono.exists():
                    self.tg.operativo(disegni.TELEFONO)
                    telefono.write_text("1", encoding="utf-8")
        except Exception as errore:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            self.allarme(f"non sono riuscito a preparare i disegni per MT5 ({type(errore).__name__}: {errore}): "
                         "il bot lavora lo stesso, ma senza disegni sul grafico.")

    @staticmethod
    def _tema(d) -> str:
        """Di quale operazione si parla, in testa a ogni messaggio in equipe."""
        return conversazione.tema(d.r.strumento, d.r.verso.value, d.r.alto_tf.value)

    def _disegna(self, d, viva, adesso: int, testo: Optional[str] = None) -> None:
        if getattr(d, "foto", None):
            # La foto per il telefono la disegna il bot (`foto_grafico`), a fine giro: gli ordini non aspettano.
            # `testo`: il messaggio d'apertura, che parte con la sua foto.
            if not hasattr(self, "_foto_da_fare"):
                self._foto_da_fare = []
            self._foto_da_fare.append((d, viva, testo))
        if self.disegni is None or (getattr(d.r.scatto, "modello", "") not in MODELLI_ROMEO and not getattr(d, "foto", None)):
            return
        try:
            v = self._verdetti.get(d.chiave)
            kl = (getattr(v, "metodo", None).fatti.get("key level")
                  if v is not None and getattr(v, "metodo", None) is not None else None)
            disegno = (disegni.operazione_foto(d, viva, self.terminale.scarto or 0, kl) if getattr(d, "foto", None)
                       else disegni.operazione(d, viva, self.terminale.scarto or 0, kl))
            self.disegni.metti(d.chiave, self.terminale.simbolo(d.r.strumento), disegno, disegni.fino_a(d))
            self.disegni.scrivi(adesso)
            if not getattr(d, "foto", None):
                self.chiedi_foto(d.r.strumento, d.r.basso_tf.value, "operativo",
                                 f"📸 {d.r.strumento}: la nostra operazione sul grafico.")
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def manda_foto_operazioni(self) -> None:
        """Le foto delle operazioni appena aperte, disegnate dal bot: sfondo bianco, candele verdi e rosse, solo
        l'operazione (il proprietario: *"quando manda le foto non si legge un cazzo"*). Le foto di MT5 non si
        mandano piu': se il disegno non riesce, lo si dice."""
        da_fare, self._foto_da_fare = getattr(self, "_foto_da_fare", []), []
        for lavoro in da_fare:
            d, viva, testo = lavoro if len(lavoro) == 3 else (*lavoro, None)
            try:
                png = foto_grafico.operazione_foto(d, viva)
            except Exception as errore:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
                if testo:
                    self.tg.operativo(testo)
                self.allarme(_foto_non_riuscita(errore))
                continue
            # Il messaggio d'apertura e' la didascalia della sua foto: arrivano insieme, una operazione alla volta.
            if testo and len(testo) <= DIDASCALIA:
                self.tg.foto("operativo", png, testo)
            else:
                self.tg.foto("operativo", png, f"📸 {d.r.strumento}: l'operazione sul grafico, come nelle foto.")
                if testo:
                    self.tg.operativo(testo)

    def prepara_foto(self) -> None:
        """Le foto le disegna matplotlib: se manca (l'installazione di `avvia.bat` non e' andata), il bot lo
        installa da solo, in disparte, e lo dice."""
        if foto_grafico.pronto():
            return

        def installa():
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "matplotlib>=3.8"], cwd=RADICE,
                               capture_output=True, text=True, timeout=900, check=True)
                fatto = foto_grafico.pronto()
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
                fatto = False
            self.tg.operativo("📸 Il programma che disegna le foto del grafico è installato: da ora le foto arrivano "
                              "nuove." if fatto else messaggi.allarme(
                                  "Non riesco a installare il programma che disegna le foto (matplotlib). Nella "
                                  "cartella del bot apri un prompt e scrivi: .venv\\Scripts\\python.exe -m pip install "
                                  "matplotlib"))
        threading.Thread(target=installa, name="installa matplotlib", daemon=True).start()

    def aggiorna_disegni(self, adesso: int) -> None:
        """A ogni giro: i livelli della settimana, i CRT che gli agenti stanno guardando nella candela 3 e le
        operazioni aperte. Cosi' sul grafico c'e' sempre il lavoro della squadra, anche senza operazioni nuove."""
        if self.disegni is None:
            return
        try:
            from nvm.agenti.cacciatore import Stato as StatoCRT
            from nvm.vivo import giro as il_giro
            scarto = self.terminale.scarto or 0
            self.disegni.togli("attesa ")
            # Col metodo delle foto non si aspetta niente dentro la candela 3: si entra alla sua apertura.
            for s in ([] if il_metodo() == "foto" else self.strumenti):
                base = self.basi.get(s)
                if base is None or not len(base):
                    continue
                for alto, basso in ((TF.D1, TF.H1), (TF.W1, TF.H4)):
                    basse = il_giro._candele(base, basso, adesso)
                    for c in il_giro._crt3(base, alto, basso, adesso):
                        if c.stato_a(adesso) is not StatoCRT.ARMATO:
                            continue
                        ap = apertura_romeo(c, basse, il_giro._candele(base, TF.H1, adesso))
                        apertura = ap[1] if ap is not None else None
                        fino = min(int(c.decaduto_quando), int(c.fine_candela_3), adesso + 8 * 86400)
                        self.disegni.metti(f"attesa {s} {alto.value} {c.verso.value} {c.range_inizio}",
                                           self.terminale.simbolo(s), disegni.in_attesa(c, apertura, scarto), fino)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        # Ogni parte per conto suo: un errore in una non toglie le altre dal grafico.
        try:
            self.disegni.togli("aperta ")
            for v in self.stato.vive:
                if v.chiave not in self.disegni.gruppi:
                    self.disegni.metti(f"aperta {v.chiave}", self.terminale.simbolo(v.strumento),
                                       disegni.aperta(v, adesso, self.terminale.scarto or 0), adesso + 2 * 3600)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        try:
            self.disegna_settimana(adesso)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def chiedi_foto(self, strumento: str, periodo: str, canale: str, didascalia: str) -> None:
        """Chiede a MT5 la foto del grafico coi disegni; arriva su Telegram appena e' pronta."""
        if self.disegni is None or self._cartella_foto is None:
            return
        numero = str(int(time.time() * 1000) % 10 ** 12)
        if self.disegni.chiedi_foto(self.terminale.simbolo(strumento), periodo, numero):
            self._foto.append({"numero": numero, "canale": canale, "didascalia": didascalia, "strumento": strumento,
                               "entro": time.time() + 300})

    def consegna_foto(self) -> None:
        """Le foto pronte partono su Telegram; se MT5 dice che non riesce, o non risponde in 5 minuti, si
        dice perche' e cosa fare."""
        restano = []
        for f in self._foto:
            png = self._cartella_foto / f"nvm_foto_{f['numero']}.png" if self._cartella_foto else None
            rispondi = self.tg.operativo if f["canale"] == "operativo" else self.tg.equipe
            esito = f.get("esito") or (self.disegni.esito_foto(f["numero"]) if self.disegni is not None else None)
            f["esito"] = esito
            try:
                if png is not None and png.exists() and png.stat().st_size > 0 and time.time() - png.stat().st_mtime > 2:
                    self.tg.foto(f["canale"], png.read_bytes(), f["didascalia"])
                    png.unlink()
                    continue
            except OSError:
                pass
            if esito and esito != "ok":
                rispondi(f"Non sono riuscito a fotografare il grafico di {f['strumento']}: {esito}. Scrivimelo e lo "
                         "sistemo.")
                continue
            if time.time() > f["entro"]:
                stato = self.disegni.stato_mt5(time.time()) if self.disegni is not None else None
                rispondi(f"Non sono riuscito a fotografare il grafico di {f['strumento']}: "
                         + (disegni.stato_in_parole(stato) or "MT5 non ha risposto in 5 minuti."))
                continue
            restano.append(f)
        self._foto = restano

    def _grafico(self, m) -> None:
        """Il comando /grafico SIMBOLO [PERIODO]: la foto del grafico disegnata dal bot, per il telefono."""
        parti = m.testo.split()
        canale = "operativo" if m.chat in self.imp.chat_operativo else "equipe"
        rispondi = self.tg.operativo if canale == "operativo" else self.tg.equipe
        if len(parti) < 2:
            rispondi("Scrivi per esempio «/grafico EURUSD» oppure «/grafico XAUUSD H4».")
            return
        nome = parti[1].upper().rstrip("+.").replace("/", "")
        strumento = next((s for s in self.strumenti if s == nome or self.terminale.simbolo(s).upper() == parti[1].upper()), None)
        periodo = parti[2].upper() if len(parti) > 2 and parti[2].upper() in ("M15", "H1", "H4", "H6", "D1", "W1", "MN") else "H1"
        if strumento is None:
            rispondi(f"Non conosco «{parti[1]}». Scrivi per esempio «/grafico EURUSD».")
            return
        try:
            # La foto la disegna il bot: le candele e le operazioni aperte su quello strumento.
            sorgente = self.fini if periodo == "M15" else self.basi
            candele = costruisci(sorgente[strumento], TF(periodo))
            aperte = [v for v in self.stato.vive if v.strumento == strumento]
            nome = foto_grafico.NOMI_TF.get(TF(periodo), periodo)
            self.tg.foto(canale, foto_grafico.grafico(candele, strumento, aperte), f"📸 {strumento} ({nome}).")
        except Exception as errore:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            rispondi(_foto_non_riuscita(errore))

    def controlla_disegni(self, adesso: float) -> None:
        """Il programma dei disegni in MT5 e' vivo e disegna? Se no lo dice, al massimo ogni 12 ore."""
        if self.disegni is None:
            return
        problema = disegni.stato_in_parole(self.disegni.stato_mt5(adesso))
        if problema and adesso - self._avviso_disegni > 12 * 3600:
            self._avviso_disegni = adesso
            self.tg.operativo(messaggi.allarme(problema))

    def disegna_settimana(self, adesso: int) -> None:
        """La domenica di Romeo (V14), tenuta per tutta la settimana: il lunedi' e i livelli della settimana passata."""
        if self.disegni is None:
            return
        ny = datetime.fromtimestamp(adesso, tz=NEW_YORK)
        # Da lunedi' a venerdi' la settimana in corso; il sabato e la domenica quella che arriva.
        giorni = -ny.weekday() if ny.weekday() <= 4 else 7 - ny.weekday()
        lunedi_ny = (ny + timedelta(days=giorni)).replace(hour=0, minute=0, second=0, microsecond=0)
        lunedi = int(lunedi_ny.timestamp())
        venerdi = int((lunedi_ny + timedelta(days=4, hours=17)).timestamp())
        for s in self.strumenti:
            p = fine_settimana.previsione(self.basi[s], adesso) if s in self.basi else None
            if p is None:
                continue
            self.disegni.metti(f"settimana {s}", self.terminale.simbolo(s),
                               disegni.settimana(p[1], p[2], lunedi, venerdi, self.terminale.scarto or 0), venerdi + 86400)
        self.disegni.scrivi(adesso)

    def racconta_evoluzione(self) -> None:
        """Come i cervelli hanno provato a cambiare se stessi in settimana: una volta sola, in equipe."""
        ev = (self.cervelli_info or {}).get("evoluzione") or {}
        chi = str(ev.get("id", ""))
        if chi and ev.get("testo") and chi != self.stato.ultima_evoluzione:
            self.tg.equipe(ev["testo"])
            self.stato.ultima_evoluzione = chi
            self.stato.salva(CARTELLA)

    def racconta_allenamento(self) -> None:
        """Il rapporto corto dell'ultimo allenamento, una volta sola, sul canale equipe (quello
        lungo resta nel registro). I rapporti di prima, solo lunghi, non si mandano piu'."""
        ultimo = leggi_memoria().get("ultimo", {})
        # Ogni allenamento ha il suo numero: due nella stessa settimana si raccontano tutti e due.
        chi = str(ultimo.get("id", ultimo.get("settimana", "")))
        if chi and ultimo.get("breve") and chi != self.stato.ultimo_allenamento:
            self.tg.equipe(ultimo["breve"])
            self.stato.ultimo_allenamento = chi
            self.stato.salva(CARTELLA)

    def prova_collegamento(self, solo_se_non_va: bool = False) -> None:
        """A ogni avvio: MT5 accetterebbe un ordine su ogni strumento? Lo dice sul
        canale operativo; dopo un aggiornamento, solo se qualcosa non va."""
        prove = []
        for strumento in self.strumenti:
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
        self._scadute()
        if self._foto:
            self.consegna_foto()
        try:
            self.stato.vive, fatti = self.esecutore.sorveglia(self.stato.vive)
        except ErroreMT5:
            # Senza le posizioni da MT5 si salta la sorveglianza di questo minuto, non il resto:
            # il bot deve continuare a guardare il mercato.
            fatti = []
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        for f in fatti:
            (self.tg.equipe if f.equipe else self.tg.operativo)(f.testo)
            registra(CARTELLA, "sorveglianza", testo=f.testo)
            if f.erre is not None:
                netto = (f.libro or {}).get("netto")
                self.stato.chiuse.append([int(time.time()), float(f.erre), None if netto is None else float(netto)])
            if f.libro is not None:
                self._nel_libro("chiusura", **f.libro)
                # Le chiusure fatte a mano non sono il metodo: la squadra impara da come sarebbe finita sulla carta.
                if self.squadra is not None and f.erre is not None and f.libro.get("chiave"):
                    if f.libro.get("a_mano"):
                        self._chiusa_a_mano(f.libro["chiave"], f.libro.get("strumento", ""), f.libro.get("verso", ""))
                    else:
                        self._risultato_vero(f.libro["chiave"], float(f.erre), f.libro.get("strumento", ""),
                                             f.libro.get("verso", ""))
        adesso = time.time()
        quarto = _su(adesso, 900)
        if quarto > self.stato.ultimo_quarto and adesso - quarto >= RITARDO_GIRO:
            self.giro_veloce(quarto)
        ora = _su(adesso, 3600)
        if ora > self.stato.ultimo_giro and adesso - ora >= RITARDO_GIRO:
            self.giro(ora)
            self.stato.salva(CARTELLA)
        self.riepilogo(adesso)
        oggi = datetime.fromtimestamp(adesso, tz=timezone.utc)
        settimana = f"{oggi.isocalendar().year}-S{oggi.isocalendar().week:02d}"
        if oggi.weekday() == 5 and oggi.hour >= 8 and self.stato.ultima_riunione != settimana:
            self.riunione(settimana, int(adesso))
        if oggi.weekday() == 6 and oggi.hour >= 18 and self.stato.ultima_domenica != settimana:
            self.domenica(settimana, int(adesso))
        self.stato.salva(CARTELLA)

    def controlla_versione(self) -> None:
        """Ogni due minuti: c'e' una versione nuova su GitHub? Fuori da `minuto`, cosi' un errore nel giro non
        blocca gli aggiornamenti (prima era successo: il giro si rompeva e il bot non si aggiornava piu')."""
        adesso = time.time()
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
            if getattr(m, "tasto", ""):
                try:
                    self._tasto(m)
                except Exception:
                    registra(CARTELLA, "errore", testo=traceback.format_exc())
                    self.tg.rispondi_tasto(m.id_tasto, "Qualcosa non è andato: riprova fra un minuto")
                continue
            if m.testo.lower().split("@")[0].startswith("/strumenti"):
                try:
                    self.manda_simboli("operativo" if m.chat in self.imp.chat_operativo else "equipe")
                except Exception:
                    registra(CARTELLA, "errore", testo=traceback.format_exc())
                continue
            if m.testo.lower().split("@")[0].startswith("/grafico"):
                try:
                    self._grafico(m)
                except Exception:
                    registra(CARTELLA, "errore", testo=traceback.format_exc())
                continue
            if m.testo.lower().split("@")[0].startswith("/piano"):
                try:
                    self._piano(m)
                except Exception:
                    registra(CARTELLA, "errore", testo=traceback.format_exc())
                continue
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

    # --- le proposte con i pulsanti (analisi su TradingView) ---

    def _proponi(self, d, v) -> None:
        """Il setup sul canale operativo, con i pulsanti «Apri» e «Lascia»: si apre solo se lo premete."""
        ident = secrets.token_hex(4)
        while ident in self.proposte:
            ident = secrets.token_hex(4)
        scade = int(d.r.quando) + VALIDITA_PROPOSTA
        self.proposte[ident] = {"d": d, "v": v, "scade": scade}
        grafico = self.fonte.simbolo(d.r.strumento) if self._su_tradingview else d.r.strumento
        self.tg.proposta(messaggi.proposta(d, scade, grafico), [("✅ Apri", f"apri:{ident}"), ("❌ Lascia", f"lascia:{ident}")])
        registra(CARTELLA, "proposta", chiave=d.chiave, grafico=grafico, ingresso=d.op.ingresso, stop=d.op.stop,
                 tp1=d.op.tp1, tp2=d.op.tp2, scade=scade)

    def _non_presa(self, p: dict) -> None:
        """Una proposta non aperta: per la squadra conta come non presa."""
        if p.get("v") is not None and self.squadra is not None:
            self.squadra.annulla(p["d"].chiave)

    def _scadute(self) -> None:
        for ident, p in list(getattr(self, "proposte", {}).items()):
            if time.time() > p["scade"]:
                del self.proposte[ident]
                self._non_presa(p)
                registra(CARTELLA, "proposta scaduta", chiave=p["d"].chiave)

    def _non_si_apre(self, p: dict) -> str:
        """Perche' una proposta non si puo' piu' aprire ('' se si puo'). Oltre lo stop o il TP1 lo controlla
        l'esecutore, come sempre."""
        d = p["d"]
        k = d.r.strumento
        if time.time() > p["scade"]:
            return f"è scaduta alle {messaggi.ora_italiana(p['scade'])}"
        if any(x.strumento == k for x in self.stato.vive):
            return f"su {k} c'è già un'operazione aperta"
        bid, ask = self.terminale.prezzo(k)
        prezzo = bid if d.r.verso is Verso.SHORT else ask
        segno = -1 if d.r.verso is Verso.SHORT else 1
        rischio = segno * (prezzo - d.op.stop)
        resa = segno * (d.op.tp2 - prezzo)
        if rischio > 0 and 0 < resa < foto.RR_MINIMO * rischio - 1e-12:
            return (f"su MT5 il prezzo ({messaggi.prezzo(k, prezzo)}) si è mosso: il target finale renderebbe meno di "
                    f"{foto.RR_MINIMO:g} volte il rischio")
        return ""

    def _tasto(self, m) -> None:
        """Un pulsante premuto sotto una proposta. Chi ha scelto cosa va nel registro: sono le lezioni per la rete."""
        azione, _, ident = m.tasto.partition(":")
        if azione not in ("apri", "lascia"):
            self.tg.rispondi_tasto(m.id_tasto)
            return
        chi = m.chi or "voi"

        def fine(esito: str, breve: str) -> None:
            self.tg.rispondi_tasto(m.id_tasto, breve)
            self.tg.chiudi_tasti(m.chat, m.messaggio, (m.originale + "\n\n" if m.originale else "") + esito)

        p = self.proposte.get(ident)
        if p is None:
            fine("⌛ Questa proposta non vale più (scaduta, già decisa, o il bot è ripartito).", "Non vale più")
            return
        d, v = p["d"], p["v"]
        if azione == "lascia":
            del self.proposte[ident]
            self._non_presa(p)
            registra(CARTELLA, "scelta del proprietario", chiave=d.chiave, scelta="lascia", chi=chi)
            fine(f"❌ Lasciata da {chi}.", "Lasciata")
            return
        motivo = self._non_si_apre(p)
        if motivo:
            del self.proposte[ident]
            self._non_presa(p)
            registra(CARTELLA, "scelta del proprietario", chiave=d.chiave, scelta="apri", chi=chi, aperta=False,
                     motivo=motivo)
            fine(f"⚠️ Non aperta: {motivo}.", "Non aperta")
            return
        conto = self.terminale.conto()
        if v is not None:
            # Quanto puntare l'ha deciso il Rischio della squadra quando ha proposto.
            viva, fatto = self.esecutore.apri(d, conto, self.stato.vive, pieno=v.puntata, parte=1.0,
                                              fiducia_minima=0.0, riduci=False)
        else:
            viva, fatto = self.esecutore.apri(d, conto, self.stato.vive)
        del self.proposte[ident]
        registra(CARTELLA, "scelta del proprietario", chiave=d.chiave, scelta="apri", chi=chi, aperta=viva is not None)
        if viva is None:
            self._non_presa(p)
            fine("⚠️ Non aperta: " + fatto.testo, "Non aperta")
            return
        self.stato.vive.append(viva)
        for s in self.stato.seguite:
            if s.chiave == d.chiave:
                s.entrata = True
        self.stato.salva(CARTELLA)
        fine(f"✅ Aperta da {chi}: {viva.volume:g} lotti a {messaggi.prezzo(viva.strumento, viva.ingresso)} su MT5.",
             "Aperta")
        con_foto = bool(getattr(d, "foto", None)) and foto_grafico.pronto()
        self._disegna(d, viva, int(time.time()), fatto.testo if con_foto else None)
        if not con_foto:
            self.tg.operativo(fatto.testo)
        self.manda_foto_operazioni()
        conto = self.terminale.conto()
        self._nel_libro("apertura", strumento=viva.strumento, verso=viva.verso, tickets=viva.tickets,
                        volume=viva.volume, ingresso=viva.ingresso, stop=viva.stop, tp1=viva.tp1, tp2=viva.tp2,
                        rischio=viva.rischio, valuta=viva.valuta, chiave=viva.chiave,
                        chi_decide=f"{chi} con «Apri» (analisi su TradingView)")
        if v is not None and self.squadra is not None:
            saldo = conto.saldo
            aperte_ora, quota_totale = self._esposizione(saldo)
            self.tg.voci(al_lavoro.voci(v, viva.rischio, viva.valuta, viva.rischio / saldo if saldo else None,
                                        aperte_ora, quota_totale), tema=self._tema(d))

    def _piano(self, m) -> None:
        """«/piano STRUMENTO TP1 TPFINALE»: cambia il piano dell'operazione aperta su quello strumento (il proprietario,
        08/10/2026, sull'SPX500 aperto con le candele di prima: *"prendere il TP1, mettere il TP finale e mettere a BE
        una volta preso il TP1 e preso il 25%"*). Il TP finale va su MT5; al TP1 il bot chiude il 25% e porta lo stop
        a pareggio, come nelle operazioni nuove. Lo stop non cambia."""
        rispondi = self.tg.operativo if m.chat in self.imp.chat_operativo else self.tg.equipe
        parti = m.testo.split()
        aiuto = "Scrivi per esempio «/piano SPX500 7799 7832»: lo strumento, il TP1 (25% e pareggio) e il TP finale."
        if len(parti) != 4:
            rispondi(aiuto)
            return
        strumento = parti[1].upper()
        try:
            tp1, tp2 = (float(x.replace(",", ".")) for x in parti[2:])
        except ValueError:
            rispondi(aiuto)
            return
        vive = [v for v in self.stato.vive if v.strumento == strumento]
        if not vive:
            rispondi(f"Non ho operazioni aperte su {strumento}.")
            return
        v = vive[-1]
        ancora = [x for x in v.tickets if x not in v.chiusi]
        if len(ancora) != 1:
            rispondi(f"{strumento}: questa operazione non è una posizione sola, il piano non lo cambio.")
            return
        if v.pareggio_fatto or v.meta_fatta:
            rispondi(f"{strumento}: il TP1 è già stato preso, il piano non lo cambio.")
            return
        su = 1 if not v.short else -1
        if not (su * (tp1 - v.ingresso) > 0 and su * (tp2 - tp1) >= 0):
            rispondi(f"{strumento}: per {'un acquisto' if su > 0 else 'una vendita'} da {v.ingresso:g} il TP1 deve "
                     f"stare {'sopra' if su > 0 else 'sotto'} l'entrata e il TP finale oltre il TP1.")
            return
        minimo, passo, _ = self.terminale.lotti(strumento)
        meta = round(int(v.volume * foto.PARZIALE / passo + 1e-9) * passo, 8)
        if meta < minimo or v.volume - meta < minimo - 1e-9:
            meta = 0.0
        e = self.terminale.sposta_stop(strumento, ancora[0], v.stop, tp2)
        if not e.ok:
            rispondi(f"{strumento}: non riesco a mettere il TP finale su MT5 ({e.messaggio}). Il piano resta com'era.")
            return
        v.tp1, v.tp2, v.meta, v.meta_fatta, v.pareggio_a = tp1, tp2, meta, False, 1.0
        v.uscita = USCITE[0] if meta > 0 else USCITE[2]
        self.stato.salva(CARTELLA)
        registra(CARTELLA, "piano cambiato", strumento=strumento, tp1=tp1, tp2=tp2, meta=meta)
        parziale = f"chiudo {meta:g} lotti (il 25%) e " if meta > 0 else "(il lotto non si divide: niente 25%) "
        rispondi(f"✅ {strumento}: TP finale {tp2:g} messo su MT5. Al TP1 {tp1:g} {parziale}porto lo stop a pareggio "
                 f"({v.ingresso:g}). Lo stop resta {v.stop:g}.")

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
            di(f"C'è una versione nuova ({titolo}): mi riavvio.")
            sys.exit(AGGIORNATO)

    def giro_veloce(self, quarto: int) -> None:
        """La coppia 4 ore -> 15 minuti, ogni quarto d'ora. Uno strumento alla volta: con tante
        coppie, la prima non aspetta che il bot abbia guardato tutte le altre."""
        dal = max(self.stato.ultimo_quarto + 1, quarto - 86400)
        for s in self.strumenti:
            try:
                self.fini[s] = (_unisci(self.fini[s], self._fonte.barre(s, 20, 900), QUARTI) if s in self.fini
                                else self._fonte.barre(s, QUARTI, 900))
            except ErroreTradingView as errore:
                self.allarme(f"TradingView: {errore}")
                continue
            if il_metodo() == "foto":
                # Col metodo delle foto si entra all'apertura delle candele, che cadono tutte allo scoccare
                # dell'ora: decide il giro orario.
                continue
            self._decidi(giro_orario({s: self.fini[s]}, dal, quarto, self.capo, (COPPIA_VELOCE,), {s: self.basi[s]},
                                     gemelli=self.gemelli()),
                         quarto, 900)
        self.uscite(quarto)
        self.stato.ultimo_quarto = quarto
        self.parla()

    def giro(self, ora: int) -> None:
        dal = max(self.stato.ultimo_giro + 1, ora - 86400)
        # Uno strumento alla volta: le ore nuove, poi subito le decisioni e gli ordini. Un errore su uno
        # strumento non ferma gli altri e non fa ripartire il giro (prima rifaceva da capo anche gli strumenti
        # gia' guardati); se non va nessuno (MT5 staccato) si riprova al minuto dopo.
        self.aggiorna_dxy()
        self.aggiorna_totale()
        self.aggiorna_lunghe(time.time())
        andati, ultimo_errore = 0, None
        foto_metodo = il_metodo() == "foto"
        # Prima le occasioni di tutti gli strumenti, poi si decide su tutte insieme: il Capo sceglie le migliori del
        # giro (il proprietario, 07/10/2026: *"il capo deve selezionare i crt"*).
        tutte: dict[str, list] = {}
        for s in self.strumenti:
            try:
                self._ore_nuove(s)
                tutte[s] = giro_orario({s: self.basi[s]}, dal, ora, self.capo, COPPIE, gemelli=self.gemelli(),
                                       lunghe=self.lunghe)
                andati += 1
            except ErroreTradingView as errore:
                # Lo stesso allarme per tutti gli strumenti: arriva una volta sola, non uno per grafico.
                ultimo_errore = errore
                registra(CARTELLA, "errore", testo=f"{s}: {traceback.format_exc()}")
                self.allarme(f"TradingView: {errore}")
            except Exception as errore:
                ultimo_errore = errore
                registra(CARTELLA, "errore", testo=f"{s}: {traceback.format_exc()}")
                self.allarme(f"{s}: errore nel giro dell'ora ({errore!r}). Gli altri strumenti vanno avanti.")
        if not andati and ultimo_errore is not None:
            raise ultimo_errore
        # Si entra all'apertura della candela 3 (*"entra ad apertura candela"*): se il bot arriva tardi (riavvio, MT5
        # lento) non si entra a un prezzo che non e' piu' quello.
        adesso, finestra = (int(time.time()), RITARDO_MASSIMO) if foto_metodo else (ora, 3600)
        decisioni = sorted((d for ds in tutte.values() for d in ds), key=lambda d: (d.r.quando, d.r.strumento))
        try:
            self._decidi(decisioni, adesso, finestra)
        except Exception as errore:
            # Se qualcosa si rompe sul giro intero, si riprova uno strumento alla volta (le occasioni gia' decise non
            # tornano: `_decidi` salta quelle gia' viste).
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            for s, ds in tutte.items():
                try:
                    self._decidi(ds, int(time.time()) if foto_metodo else ora, finestra)
                except Exception as errore_s:
                    registra(CARTELLA, "errore", testo=f"{s}: {traceback.format_exc()}")
                    self.allarme(f"{s}: errore nel giro dell'ora ({errore_s!r}). Gli altri strumenti vanno avanti.")
        if self.squadra is not None and foto_metodo:
            # Il Bias dice le sue previsioni del giorno, una volta al giorno, dopo gli ordini.
            try:
                self._previsioni_del_giorno(ora)
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
        # Le decisioni dell'ora sono fatte: il giro non si ripete, qualunque cosa succeda dopo.
        self.stato.ultimo_giro = ora
        self.stato.scarto = self.terminale.scarto
        self.stato.salva(CARTELLA)
        for passo in (self.manda_foto_operazioni, lambda: self.uscite(ora), lambda: self._segui_carta(ora),
                      lambda: self.aggiorna_disegni(ora), lambda: self.controlla_disegni(time.time()), self.parla):
            try:
                passo()
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())

    def _ore_nuove(self, s: str) -> None:
        """Le ore nuove dello strumento; se non ci sono ancora (all'avvio TradingView non rispondeva), tutte."""
        if s in self.basi:
            self.basi[s] = _unisci(self.basi[s], self._fonte.orarie(s, 50), ORARIE)
        else:
            self.basi[s] = self._fonte.orarie(s, ORARIE)

    def _previsioni_del_giorno(self, adesso: int) -> None:
        """Le previsioni del Bias su tutti gli strumenti, all'apertura del giorno (le tiene fino a sera)."""
        if self.squadra.memoria.previsioni_dette == pareri.apertura_giorno(adesso):
            return
        from nvm.agenti import foto
        quadri = {}
        for s in self.strumenti:
            try:
                if s in self.basi and len(self.basi[s]) >= 200:
                    quadri[s] = foto.Quadro.da(self.basi[s], adesso, self.lunghe.get(s))
            except Exception:
                registra(CARTELLA, "errore", testo=f"{s}: {traceback.format_exc()}")
        testo = al_lavoro.previsioni_del_giorno(self.squadra, quadri, adesso)
        if testo:
            self.tg.voci([conversazione.Voce("Bias", testo)])

    def _contesto(self) -> "pareri.Contesto":
        """Quello che la squadra deve sapere oltre l'occasione: la previsione della domenica."""
        return pareri.Contesto(dict(self.stato.previsioni or {}))

    def _segui_carta(self, ora: int) -> None:
        """Le occasioni seguite sulla carta: come sono finite, cosa impara la squadra, l'archivio."""
        for s in segui(self.stato.seguite, self.basi, ora, self.fini):
            self._finita(s, ora)
        if self.squadra is not None:
            # Livelli rivede come sarebbero andati gli altri stop e le altre uscite.
            try:
                al_lavoro.valuta_piani(self.squadra, self.basi, self.fini, ora)
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
        # Le seguite finite da piu' di due settimane vanno nell'archivio: con tanti strumenti lo
        # stato, salvato ogni minuto, diventerebbe troppo grande. La riunione le rilegge.
        vecchie = [s for s in self.stato.seguite if s.esito is not None and s.esito["quando"] <= ora - TENERE]
        if vecchie:
            archivia(CARTELLA, vecchie)
            self.stato.seguite = [s for s in self.stato.seguite if s.esito is None or s.esito["quando"] > ora - TENERE]

    def _equipe(self, testo: str) -> None:
        self._da_dire.append(testo)

    def _prove_dei_segnali(self) -> Optional[dict]:
        """Per ogni agente e segnale, quante volte sui vent'anni e' arrivato il primo obiettivo (una volta sola)."""
        if self._prove is None and self.storico.tp1 is not None:
            self._prove = conversazione.prove(self.storico.x, self.storico.tp1)
        return self._prove

    def _esposizione(self, saldo: float) -> tuple[int, float]:
        """Quante operazioni aperte, e che parte del conto rischiano insieme (quelle a pareggio non rischiano)."""
        a_rischio = sum(v.rischio for v in self.stato.vive if not v.pareggio_fatto)
        return len(self.stato.vive), (a_rischio / saldo if saldo else 0.0)

    def riepilogo(self, adesso: float) -> None:
        """A fine giornata (le 17 di New York, quando chiude la giornata del forex) un messaggio solo."""
        ny = datetime.fromtimestamp(adesso, tz=NEW_YORK)
        giorno = ny.strftime("%Y-%m-%d")
        if ny.hour < 17 or self.stato.ultimo_riepilogo == giorno:
            return
        if not self.stato.ultimo_riepilogo:
            # La prima sera: la giornata prima il bot non c'era, non c'e' niente da riassumere.
            self.stato.ultimo_riepilogo = giorno
            return
        fine = int(ny.replace(hour=17, minute=0, second=0, microsecond=0).timestamp())
        try:
            conto = self.terminale.conto()
            saldo, valuta = conto.saldo, conto.valuta
        except ErroreMT5:
            saldo, valuta = 0.0, "EUR"
        if self.squadra is not None:
            # Decide la squadra: da ricordare, le sue lezioni di oggi.
            lezioni, self._lezioni_oggi = self._lezioni_oggi[-3:], []
            gara = al_lavoro.come_va(self.squadra)
        else:
            lezioni = [f"{k} avrebbe fatto meglio {n} volt{'a' if n == 1 else 'e'}"
                       for k, n in sorted(self.stato.lezioni.items(), key=lambda a: -a[1])]
            gara = [x for x in (dal_vivo.gara(self.stato.seguite, fine - 86400, fine, self.cervelli_info.get("soglia", 0.5)),
                                dal_vivo.la_migliore(self.stato.seguite, fine - 86400, fine,
                                                     float(self.cervelli_info.get("rischio", {}).get("minimo", 0.0))))
                    if x]
        testo = conversazione.riepilogo(self.stato.seguite, fine - 86400, fine, *self._esposizione(saldo), lezioni,
                                        self.stato.saltate, [c[1:] for c in self.stato.chiuse], gara,
                                        cervelli=self._decidono_i_cervelli and self.squadra is None,
                                        saldo=saldo or None, valuta=valuta, sempre=True,
                                        mancanze=self.stato.mancanze if self.squadra is not None else None)
        if testo:
            self.tg.equipe(testo)
        self.stato.lezioni = {}
        self.stato.saltate = {}
        self.stato.mancanze = {}
        self.stato.chiuse = []
        self.stato.ultimo_riepilogo = giorno

    def parla(self) -> None:
        """I messaggi dell'equipe del giro, messi insieme: con tante coppie sarebbero troppi per Telegram."""
        for testo in raggruppa(self._da_dire):
            self.tg.equipe(testo)
        self._da_dire.clear()

    def uscite(self, adesso: int) -> None:
        """Le uscite prima dello stop: il kiss of death superato dopo il primo obiettivo (V16 15:32), e quelle
        che gli agenti hanno imparato (idea invalidata o troppo lenta)."""
        for v in self.stato.vive:
            if il_metodo() == "foto":
                # Il kiss of death era del metodo dei video: nelle foto si esce allo stop, al pareggio o al target.
                break
            if not (v.pareggio_fatto and v.primo_quando and v.basso) or v.uscita_anticipata:
                continue
            if all(t in v.chiusi for t in v.tickets):
                continue
            sorgente = self.fini if TF(v.basso) is TF.M15 else self.basi
            if v.strumento not in sorgente:
                continue
            try:
                basse = costruisci(sorgente[v.strumento], TF(v.basso)).chiuse_entro(adesso)
                dopo = int(np.searchsorted(basse.inizio, v.primo_quando))
                livello = kod_superato(_da(basse, dopo), v.short)
            except Exception:
                # Un errore qui non deve fermare il giro: lo stop a pareggio protegge gia' l'operazione.
                registra(CARTELLA, "errore", testo=traceback.format_exc())
                continue
            if livello is not None:
                fatto = self.esecutore.chiudi(v, f"il prezzo ha chiuso oltre il kiss of death ({livello:g}): Romeo dice "
                                                 "che allora l'obiettivo non arriva (V16 15:32)")
                self.tg.operativo(fatto.testo)
                registra(CARTELLA, "uscita anticipata", chiave=v.chiave, motivo="kiss of death superato")
        for v in self.stato.vive:
            if not (v.invalida_candele or v.tempo_candele) or not v.basso:
                continue
            sorgente = self.fini if TF(v.basso) is TF.M15 else self.basi
            if v.strumento not in sorgente:
                continue
            basse = costruisci(sorgente[v.strumento], TF(v.basso)).chiuse_entro(adesso)
            fatto = self.esecutore.uscita_anticipata(v, basse)
            if fatto is not None:
                (self._equipe if fatto.equipe else self.tg.operativo)(fatto.testo)
                registra(CARTELLA, "uscita anticipata", chiave=v.chiave, motivo=v.uscita_anticipata)

    def _nel_libro(self, evento: str, **dati) -> None:
        """Il libro delle operazioni vere, col saldo del momento. Un errore qui non ferma il bot."""
        try:
            try:
                dati["saldo"] = self.terminale.conto().saldo
            except ErroreMT5:
                dati["saldo"] = None
            libro.scrivi(CARTELLA, evento, quando=int(time.time()), **dati)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def _giudizio(self, d) -> Optional[dict]:
        """Cosa ne pensano i cervelli degli agenti, dopo il confronto."""
        if self.cervelli is None or d.viste is None:
            return None
        try:
            return dal_vivo.giudica(self.cervelli, d.viste)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            return None

    @property
    def _decidono_i_cervelli(self) -> bool:
        """Decidono i cervelli se hanno vinto l'esame, o se l'ha scelto il proprietario (`scelte.json`)."""
        return bool(self.cervelli is not None and (self.cervelli_info.get("decidono") or self.scelte.get("decidono_i_cervelli")))

    def _entra(self, d, g: Optional[dict]) -> bool:
        """Chi decide: la squadra intelligente. Solo se e' spenta (`scelte.json`), i cervelli o il Capo di prima."""
        v = self._verdetti.get(d.chiave)
        if v is not None:
            return v.entra and v.puntata > 0
        if self.squadra is not None:
            # Decide la squadra: se su questa occasione non ha potuto riunirsi, non si entra.
            return False
        if self._decidono_i_cervelli and g is not None:
            return g["fiducia"] > self.cervelli_info.get("soglia", 0.5)
        return d.entra

    def _con_piano(self, d, g: Optional[dict]):
        v = self._verdetti.get(d.chiave)
        if v is not None:
            # Il piano lo sceglie Livelli, fra quelli di Romeo (-1: quello proposto).
            piani = getattr(d, "piani_romeo", None)
            if piani and 0 <= v.piano < len(piani) and piani[v.piano] is not None:
                return replace(d, op=piani[v.piano])
            return d
        if not self._decidono_i_cervelli or g is None or not d.piani:
            return d
        try:
            scelta = dal_vivo.scegli_piano(self.cervelli_info.get("piani"), d.viste, d.piani)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
            return d
        if scelta is None:
            return d
        j, valori = scelta
        g["piano"], g["valori"] = j, valori
        return replace(d, op=d.piani[j])

    def _decidi(self, decisioni, adesso: int, finestra: int) -> None:
        # Un CRT si guarda e si apre una volta sola (il proprietario: *"una per CRT"*): se il giro si ripete,
        # le occasioni gia' viste non tornano.
        viste = {s.chiave for s in self.stato.seguite} | {v.chiave for v in self.stato.vive}
        decisioni = [d for d in decisioni if d.chiave not in viste]
        conto = self.terminale.conto() if decisioni else None
        # Se decide la squadra, i cervelli allenati sui vent'anni non giudicano piu'.
        giudizi = {d.chiave: (None if self.squadra is not None else self._giudizio(d)) for d in decisioni}
        for d in decisioni:
            if giudizi[d.chiave] is not None:
                # Cosa avrebbe fatto il Capo di prima: serve alla gara della sera.
                giudizi[d.chiave]["capo"] = bool(d.entra)
        # La squadra intelligente si riunisce su ogni occasione e decide.
        self._verdetti = {}
        if self.squadra is not None and decisioni:
            self.squadra.ultimo_errore = ""
            try:
                esposizione = self._esposizione(conto.saldo)[1] if conto is not None else 0.0
                # Quanto e' gia' a rischio su ogni strumento: decide il Rischio se e quanto aggiungere.
                per_strumento: dict = {}
                for v in self.stato.vive:
                    if not v.pareggio_fatto and conto is not None and conto.saldo:
                        per_strumento[v.strumento] = per_strumento.get(v.strumento, 0.0) + v.rischio / conto.saldo
                self._verdetti = al_lavoro.riunioni(self.squadra, decisioni, self.basi, self.fini, esposizione,
                                                    per_strumento, self._contesto(),
                                                    {v.strumento for v in self.stato.vive})
                if self.squadra.ultima_scelta:
                    # La scelta del Capo fra le occasioni del giro, in equipe: chi prende, chi lascia e perche'.
                    self.tg.voci([conversazione.Voce("Capo", self.squadra.ultima_scelta)])
            except Exception:
                self.squadra.ultimo_errore = traceback.format_exc()
            if self.squadra.ultimo_errore:
                registra(CARTELLA, "errore", testo=f"squadra intelligente: {self.squadra.ultimo_errore}")
                self.allarme("La squadra non è riuscita a riunirsi su qualche occasione: su quelle non si entra. "
                             "Il dettaglio è nel registro.")
        for v in self._verdetti.values():
            # Per il riepilogo della sera: cosa mancava alle occasioni guardate (la prima regola che manca).
            mancano = v.pareri.get("Capo", {}).get("mancano", [])
            chiave_m = "tutte le regole" if v.a_piu else MANCA_IN_PAROLE.get(mancano[0], mancano[0]) if mancano else ""
            if chiave_m:
                self.stato.mancanze[chiave_m] = self.stato.mancanze.get(chiave_m, 0) + 1
        if self._verdetti:
            try:
                self._smt_contro(decisioni)
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
        # Quando decidono i cervelli, i Livelli scelgono anche il piano: dove lo stop, come il profitto.
        decisioni = [self._con_piano(d, giudizi[d.chiave]) for d in decisioni]
        # Prima gli ordini, poi i messaggi: il mercato non aspetta Telegram.
        aperte, da_dire = set(), []
        for d in decisioni:
            g = giudizi[d.chiave]
            v = self._verdetti.get(d.chiave)
            if self._entra(d, g) and adesso - d.r.quando > finestra and getattr(d, "foto", None):
                # La candela 3 e' aperta da troppo: non si entra in ritardo, l'occasione si segue sulla carta.
                self.stato.saltate["arrivato tardi"] = self.stato.saltate.get("arrivato tardi", 0) + 1
                if v is not None and self.squadra is not None:
                    self.squadra.annulla(d.chiave)
                registra(CARTELLA, "saltata", testo=f"{d.chiave}: candela 3 aperta da {int(adesso - d.r.quando)} s")
            occupato = any(x.strumento == d.r.strumento for x in self.stato.vive)
            if self._entra(d, g) and adesso - d.r.quando <= finestra and occupato:
                # Il proprietario, 07/10/2026: al massimo un'operazione aperta per strumento. Le altre occasioni
                # su quello strumento si seguono solo sulla carta.
                chiave_s = "già un'operazione aperta sullo strumento"
                self.stato.saltate[chiave_s] = self.stato.saltate.get(chiave_s, 0) + 1
                if v is not None and self.squadra is not None:
                    self.squadra.annulla(d.chiave)
                registra(CARTELLA, "saltata", testo=f"{d.chiave}: su {d.r.strumento} c'è già un'operazione aperta")
            elif self._entra(d, g) and adesso - d.r.quando <= finestra and self._su_tradingview:
                # Sui grafici di TradingView il bot propone e decidete voi (pulsanti Apri / Lascia).
                self._proponi(d, v)
            elif self._entra(d, g) and adesso - d.r.quando <= finestra:
                if v is not None:
                    # Quanto puntare lo decide il Rischio della squadra, da solo: nessuno lo riduce.
                    viva, fatto = self.esecutore.apri(d, conto, self.stato.vive, pieno=v.puntata,
                                                      parte=1.0, fiducia_minima=0.0, riduci=False)
                elif self._decidono_i_cervelli and g is not None:
                    r = self.cervelli_info.get("rischio", {})
                    # Quanto puntare lo dice il cervello del Rischio.
                    viva, fatto = self.esecutore.apri(d, conto, self.stato.vive,
                                                      pieno=dal_vivo.puntata(self.cervelli_info, g, d.viste),
                                                      parte=r.get("parte"), fiducia_minima=r.get("minimo"))
                else:
                    viva, fatto = self.esecutore.apri(d, conto, self.stato.vive)
                # L'apertura del metodo delle foto parte insieme alla sua foto, come didascalia (`manda_foto_operazioni`):
                # con piu' operazioni aperte insieme foto e messaggi non si sfasano piu' (il proprietario, 07/10/2026).
                con_foto = viva is not None and bool(getattr(d, "foto", None)) and foto_grafico.pronto()
                if not con_foto:
                    da_dire.append(fatto)
                if viva is None and v is not None and self.squadra is not None:
                    # L'ordine non e' partito: per imparare conta come non presa.
                    self.squadra.annulla(d.chiave)
                if viva is not None:
                    self.stato.vive.append(viva)
                    aperte.add(d.chiave)
                    try:
                        # Subito su disco: se il bot riparte, sa gia' che questo CRT e' aperto.
                        self.stato.salva(CARTELLA)
                    except Exception:
                        registra(CARTELLA, "errore", testo=traceback.format_exc())
                    self._disegna(d, viva, adesso, fatto.testo if con_foto else None)
                    conto = self.terminale.conto()
                    self._nel_libro("apertura", strumento=viva.strumento, verso=viva.verso, tickets=viva.tickets,
                                    volume=viva.volume, ingresso=viva.ingresso, stop=viva.stop, tp1=viva.tp1,
                                    tp2=viva.tp2, rischio=viva.rischio, valuta=viva.valuta, chiave=viva.chiave,
                                    chi_decide=("squadra intelligente" if d.chiave in self._verdetti else
                                                "cervelli" if self._decidono_i_cervelli else "Capo"))
        for fatto in da_dire:
            if fatto.saltata:
                # Non fa rumore: si conta nel riepilogo della sera (e resta nel registro).
                self.stato.saltate[fatto.saltata] = self.stato.saltate.get(fatto.saltata, 0) + 1
                registra(CARTELLA, "saltata", testo=fatto.testo)
            else:
                (self._equipe if fatto.equipe else self.tg.operativo)(fatto.testo)
        for d in decisioni:
            try:
                per = spinte(self.capo, d.x)
            except Exception:
                # Il Capo di prima (riallenato sulla VPS con meno colonne): con la squadra non serve.
                per = {}
            aperta = d.chiave in aperte
            if aperta:
                # In equipe parla solo chi ha qualcosa da dire, e solo sulle operazioni aperte davvero:
                # le occasioni lasciate si contano nel riepilogo della sera.
                viva = next(v for v in self.stato.vive if v.chiave == d.chiave)
                saldo = conto.saldo if conto is not None else 0.0
                voci = conversazione.apertura(d, per, None if self.squadra is not None else self._prove_dei_segnali(),
                                              viva.rischio / saldo if saldo else 0.0,
                                              *self._esposizione(saldo), ingresso=viva.ingresso,
                                              da_sola=viva.da_sola, legate=tuple(viva.legate))
                g = giudizi[d.chiave]
                if d.chiave in self._verdetti:
                    # La discussione della squadra: ognuno col suo bot, il Capo e il Rischio in fondo,
                    # il Rischio coi soldi veri dell'ordine.
                    aperte_ora, quota_totale = self._esposizione(saldo)
                    self.tg.voci(al_lavoro.voci(self._verdetti[d.chiave], viva.rischio, viva.valuta,
                                                viva.rischio / saldo if saldo else None, aperte_ora, quota_totale),
                                 tema=self._tema(d))
                    voci = []
                elif g is not None:
                    # Il ragionamento dei cervelli, prima che il Capo chiuda.
                    voci.insert(len(voci) - 1, conversazione.Voce("Cervelli", dal_vivo.voce(
                        g, self.cervelli_info.get("soglia", 0.5), self._decidono_i_cervelli)))
                    if self._decidono_i_cervelli:
                        voci[-1] = conversazione.Voce("Capo", dal_vivo.capo_quando_decidono(d.p1, g["capo"]))
                    if "piano" in g:
                        testo = dal_vivo.voce_livelli(g["piano"], g["valori"])
                        k = next((i for i, v in enumerate(voci) if v.chi == "Livelli"), None)
                        if k is None:
                            voci.insert(1, conversazione.Voce("Livelli", testo))
                        else:
                            voci[k] = conversazione.Voce("Livelli", voci[k].testo + " " + testo)
                if voci:
                    self.tg.voci(voci, tema=self._tema(d))
            op = d.op
            crt = d.r.scatto.crt if d.r.scatto is not None else None
            s = Seguita(d.chiave, d.r.strumento, d.r.alto_tf.value, d.r.basso_tf.value, d.r.verso.value, d.r.quando,
                        op.ingresso, op.stop, op.tp1, op.tp2, d.scadenza, aperta,
                        [float(v) for v in d.x], d.r.rr1, d.r.rr2, d.r.costo_erre, d.p1, d.q, d.atteso,
                        spinte=per, leggibile=messaggi.leggibile(d),
                        romeo=1.0 if d.romeo is None else d.romeo, pareggio_a=op.pareggio_a, livello=op.livello_model1,
                        invalida_candele=op.invalida_candele, tempo_candele=op.tempo_candele,
                        crt_alto=None if crt is None else crt.crt_high, crt_basso=None if crt is None else crt.crt_low,
                        estremo=None if crt is None else crt.estremo_a(d.r.quando),
                        stop_minimo=livelli.STOP_MINIMO, oltre=livelli.OLTRE, qualita=d.qualita,
                        decisa=self._entra(d, giudizi[d.chiave]), cervelli=giudizi[d.chiave],
                        parziale=op.parziale, pareggio=op.pareggio)
            self.stato.seguite.append(s)
            registra(CARTELLA, "decisione", chiave=d.chiave, entra=d.entra, aperta=aperta, p1=d.p1, q=d.q,
                     atteso=d.atteso, qualita=d.qualita, romeo=d.romeo, x=s.x, spinte=per, ingresso=op.ingresso, stop=op.stop, tp1=op.tp1, tp2=op.tp2)

    def _finita(self, s: Seguita, adesso: int) -> None:
        if self.squadra is not None:
            # Decide la squadra: impara lei, dal risultato vero (anche delle occasioni lasciate).
            _, ragione, torto = resoconto(s.leggibile or s.chiave, s.esito, s.entrata, s.spinte, s.presa_dal_capo)
            ancora_aperta = any(v.chiave == s.chiave for v in self.stato.vive)
            if s.chiave in self.squadra.memoria.discusse and ancora_aperta and s.chiave not in self.squadra.memoria.veri:
                # Sulla carta e' finita ma sul conto e' ancora aperta: si impara quando arriva il risultato vero.
                self.squadra.memoria.discusse[s.chiave]["aspetta_vero"] = True
            elif s.chiave in self.squadra.memoria.discusse:
                nome = f"{s.strumento} ({'vendita' if s.verso == 'short' else 'acquisto'})"
                self._diario.submit(self._lezioni_della_squadra, s.chiave, float(s.esito["erre"]), bool(s.entrata),
                                    nome)
            registra(CARTELLA, "finita sulla carta", chiave=s.chiave, ragione=ragione, torto=torto, **s.esito)
            return
        _, ragione, torto = resoconto(s.leggibile or s.chiave, s.esito, s.entrata, s.spinte, s.presa_dal_capo)
        aggiorna_pagelle(self.stato.pagelle, ragione, torto)
        aggiorna_diario(self.stato.diario, s.x, s.esito["erre"] > 0)
        # Ognuno si chiede dove ha sbagliato: rifa' l'operazione con le sue scelte vicine, guarda la sua storia.
        alt = {}
        try:
            sorgente = self.fini if TF(s.basso) is TF.M15 else self.basi
            if s.strumento in sorgente:
                alt = autoanalisi.alternative(s, costruisci(sorgente[s.strumento], TF(s.basso)).chiuse_entro(adesso))
                autoanalisi.aggiorna(self.stato.diario, alt, float(s.esito["erre"]))
        except Exception:
            # Un errore qui non deve mai fermare il giro: le operazioni vengono prima.
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        if s.cervelli and self.cervelli is not None:
            # Ogni esperienza insegna qualcosa ai cervelli: imparano subito, ripassando, e lo ricordano.
            try:
                lezione = dal_vivo.impara(self.cervelli, CARTELLA, s.cervelli, float(s.esito["erre"]),
                                          self.cervelli_info)
                if lezione:
                    cambio = lezione.pop("cambio", None)
                    prudenza = lezione.pop("prudenza", None)
                    promozione = lezione.pop("promozione", None)
                    if prudenza:
                        registra(CARTELLA, "prudenza", **prudenza)
                        self.tg.equipe(dal_vivo.voce_della_prudenza(prudenza))
                    if promozione:
                        registra(CARTELLA, "promozione", **promozione)
                        self.tg.equipe(dal_vivo.voce_della_promozione(promozione))
                    registra(CARTELLA, "lezione", chiave=s.chiave, **{k: round(float(x), 4) for k, x in lezione.items()})
                    if s.entrata:
                        self.tg.equipe(dal_vivo.voce_della_lezione(lezione, float(s.esito["erre"])))
                    if cambio:
                        # Un agente ha cambiato se stesso perche' l'esperienza gli ha dato ragione.
                        registra(CARTELLA, "cambio", **cambio)
                        self.tg.equipe(dal_vivo.voce_del_cambio(cambio))
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
        if s.entrata:
            self.tg.voci(conversazione.chiusura(s, alt, torto, self._prove_dei_segnali()),
                         tema=conversazione.tema(s.strumento, s.verso, s.alto))
        # Le lezioni della giornata, per il riepilogo della sera: chi, con quale scelta, avrebbe fatto meglio.
        for agente, voci_alt in alt.items():
            nome, v, r = max(voci_alt, key=lambda a: a[2])
            if r > float(s.esito["erre"]) + autoanalisi.POCO:
                chiave = f"{agente}: «{autoanalisi.scelta(nome, v)}»"
                self.stato.lezioni[chiave] = self.stato.lezioni.get(chiave, 0) + 1
        registra(CARTELLA, "finita sulla carta", chiave=s.chiave, ragione=ragione, torto=torto,
                 alternative={a: [[n, v, r] for n, v, r in voci] for a, voci in alt.items()}, **s.esito)

    def _smt_contro(self, decisioni) -> None:
        """L'SMT ferma l'obiettivo (V10 06:02, V16 10:03): se su uno strumento in cui siamo dentro nasce
        un'occasione nel verso opposto con l'SMT confermato, prima del primo obiettivo si chiude."""
        for v in list(self.stato.vive):
            if v.pareggio_fatto or v.uscita_anticipata:
                continue
            for d in decisioni:
                verdetto = self._verdetti.get(d.chiave)
                m = getattr(verdetto, "metodo", None)
                if m is None or d.r.strumento != v.strumento or d.r.verso.value == v.verso:
                    continue
                if not any(c.nome == "SMT" and c.si for c in m.confluenze):
                    continue
                fatto = self.esecutore.chiudi(v, "SMT confermato contro di noi: Romeo dice che con l'SMT "
                                                 "l'obiettivo non arriva (V10 06:02)")
                self.tg.operativo(fatto.testo)
                self._equipe(f"Grilletto: su {v.strumento} il mercato gemello non ha seguito, con la rottura di "
                             "struttura a confermarlo. È l'unico caso in cui Romeo dice che l'obiettivo non arriva: "
                             "chiudiamo prima del primo obiettivo.")
                registra(CARTELLA, "uscita anticipata", chiave=v.chiave, motivo="SMT contro")
                break

    def _risultato_vero(self, chiave: str, erre: float, strumento: str, verso: str) -> None:
        """Il risultato vero dal broker: la squadra impara da questo, non da quello sulla carta."""
        try:
            self.squadra.vero(chiave, erre)
            d = self.squadra.memoria.discusse.get(chiave)
            if d is not None and d.get("aspetta_vero"):
                nome = f"{strumento} ({'vendita' if verso == 'short' else 'acquisto'})"
                self._diario.submit(self._lezioni_della_squadra, chiave, erre, True, nome)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def _chiusa_a_mano(self, chiave: str, strumento: str, verso: str) -> None:
        """Un'operazione chiusa a mano: se sulla carta era gia' finita e la squadra aspettava il risultato vero,
        impara da quello sulla carta (come sarebbe andata col metodo); se no lo fara' quando finisce sulla carta."""
        try:
            d = self.squadra.memoria.discusse.get(chiave)
            s = next((x for x in self.stato.seguite if x.chiave == chiave and x.esito is not None), None)
            if d is not None and d.get("aspetta_vero") and s is not None:
                nome = f"{strumento} ({'vendita' if verso == 'short' else 'acquisto'})"
                self._diario.submit(self._lezioni_della_squadra, chiave, float(s.esito["erre"]), True, nome)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def _lezioni_della_squadra(self, chiave: str, erre: float, presa: bool, racconto: str) -> None:
        try:
            lezioni = self.squadra.rifletti(chiave, erre, presa, racconto)
            if lezioni:
                registra(CARTELLA, "lezioni della squadra", chiave=chiave, erre=erre, lezioni=lezioni)
                self._lezioni_oggi += [f"{l['agente']}: {l['lezione']}" for l in lezioni
                                       if presa and not l.get("giusto")]
                if presa:
                    self.tg.equipe(al_lavoro.lezioni_in_breve(lezioni, racconto, erre))
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())

    def _prese_in_settimana(self, adesso: int) -> list:
        """Le operazioni prese e finite negli ultimi sette giorni: (strumento, verso, R, parte del conto)."""
        return [(s.strumento, s.verso, float(s.esito["erre"]), None) for s in self.stato.seguite
                if s.entrata and s.esito is not None and s.esito["quando"] > adesso - 7 * 86400]

    def domenica(self, settimana: str, adesso: int) -> None:
        """La domenica di Romeo (V14): la previsione della settimana e i livelli da portare avanti."""
        try:
            operati = [p[0] for p in self._prese_in_settimana(adesso)]
            testo, previsioni = fine_settimana.domenica(self.basi, adesso, operati)
            testo = self._domenica_dxy(adesso, testo, previsioni)
            self.tg.equipe(testo)
            self.stato.previsioni = previsioni
            registra(CARTELLA, "domenica di Romeo", settimana=settimana, previsioni=previsioni)
            self.disegna_settimana(adesso)
        except Exception:
            registra(CARTELLA, "errore", testo=traceback.format_exc())
        self.stato.ultima_domenica = settimana
        self.stato.salva(CARTELLA)

    def _domenica_dxy(self, adesso: int, testo: str, previsioni: dict) -> str:
        """Il DXY comanda le coppie forex col dollaro (il proprietario, 08/10/2026): la sua previsione della settimana
        va nel messaggio della domenica e diventa quella di ogni coppia forex col dollaro."""
        dxy = getattr(self, "dxy", None)
        p = fine_settimana.previsione(dxy, adesso) if dxy is not None and len(dxy) else None
        if p is None:
            return testo
        direzione, alto, basso, perche = p
        previsioni["DXY"] = direzione
        if direzione not in ("rialzista", "ribassista"):
            return testo + (f"\n• DXY: la settimana {perche}: nessuna direzione chiara. Le coppie forex col dollaro "
                            "tengono la loro.")
        su, giu = [], []
        for s in self.strumenti:
            col = foto.segno_col_dxy(s) if s in foto.FOREX_DOLLARO else 0
            if col:
                v = (1 if direzione == "rialzista" else -1) * col
                previsioni[s] = "rialzista" if v > 0 else "ribassista"
                (su if v > 0 else giu).append(s)
        return testo + (f"\n• DXY (comanda le coppie forex col dollaro): la settimana {perche}: {direzione}. Livelli "
                        f"da guardare: massimo {alto:.3f}, minimo {basso:.3f}. Quindi in settimana cerchiamo "
                        f"acquisti su {', '.join(su) or 'nessuna'} e vendite su {', '.join(giu) or 'nessuna'}.")

    def riunione(self, settimana: str, adesso: int) -> None:
        if self.squadra is not None:
            # Decide la squadra: il sabato e' la sua revisione, niente Capo riallenato sui vent'anni.
            try:
                self.tg.equipe(fine_settimana.sabato(self.basi, adesso, self._prese_in_settimana(adesso),
                                                     self.stato.previsioni))
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
            try:
                cambi = self.squadra.riscrivi_manuali()
                registra(CARTELLA, "revisione della squadra", settimana=settimana, cambi=cambi)
                self.tg.equipe(al_lavoro.manuali_in_breve(cambi))
            except Exception:
                registra(CARTELLA, "errore", testo=traceback.format_exc())
            self.stato.ultima_riunione = settimana
            self.stato.salva(CARTELLA)
            self.consegna()
            return
        tutte = archiviate(CARTELLA, adesso - 365 * 86400) + self.stato.seguite
        testo, nuovo, rischio, verbale = riunione(tutte, self.capo, self.storico, adesso - 7 * 86400, settimana,
                                                  self.stato.pagelle, self.esecutore.parte, self.stato.diario,
                                                  self.stato.romeo, _leggi("rischio.json"))
        self.tg.equipe(testo)
        self.capo = nuovo
        self.esecutore.parte = float(rischio["parte"])
        self.esecutore.minimo = float(rischio.get("minimo", 0.0))
        corr = rischio.get("correlazioni")
        self.esecutore.correlazioni = {float(c): float(r) for c, r in corr.items()} if corr else None
        CARTELLA.mkdir(parents=True, exist_ok=True)
        (CARTELLA / "capo.json").write_text(json.dumps(nuovo.come_dati()), encoding="utf-8")
        (CARTELLA / "rischio.json").write_text(json.dumps(rischio), encoding="utf-8")
        registra(CARTELLA, "riunione", settimana=settimana, testo=testo, verbale=verbale)
        self.stato.ultima_riunione = settimana
        self.stato.salva(CARTELLA)
        self.consegna()

    def consegna(self) -> None:
        """Le settimane dal vivo vanno alla palestra (`consegna.py`), se nel .env c'e' il GITHUB_TOKEN.
        In un processo a parte: il bot non aspetta GitHub."""
        if not leggi_env(RADICE / ".env").get("GITHUB_TOKEN"):
            return
        try:
            subprocess.Popen([sys.executable, str(RADICE / "consegna.py"), "--solo-vivo"], cwd=RADICE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as errore:
            registra(CARTELLA, "errore", testo=f"consegna non partita: {errore!r}")


# I codici d'uscita per avvia.bat: 3 si e' aggiornato (riparte subito), 2 fermo per scelta (non
# riparte), qualunque altro (MT5 non risponde, un errore imprevisto) riparte da solo dopo un minuto.
FERMO = 2


# Se un giro non finisce entro questo tempo il bot si e' inchiodato (MT5 o la rete che non rispondono):
# il cane da guardia lo chiude, e avvia.bat lo fa ripartire dopo un minuto.
INCHIODATO = 20 * 60
BLOCCATO = 4


def _foto_non_riuscita(errore: Exception) -> str:
    if isinstance(errore, ImportError):
        return ("La foto del grafico non è partita: manca il programma che la disegna (matplotlib). Lo sto "
                "installando: le prossime arrivano.")
    return f"La foto del grafico non è partita ({errore!r}). Scrivimelo e lo sistemo."


def cane_da_guardia(bot, controlla_ogni: float = 30.0, uscita=os._exit) -> threading.Thread:
    """Un filo a parte che guarda se il giro di ogni minuto finisce. Se no, lo scrive e chiude il bot."""
    def guarda():
        while True:
            time.sleep(controlla_ogni)
            fermo = time.time() - bot.battito
            if fermo > INCHIODATO:
                try:
                    registra(CARTELLA, "errore", testo=f"bot inchiodato da {int(fermo)} secondi: lo riavvio")
                    bot.tg.operativo(messaggi.allarme(f"Il bot era bloccato da {int(fermo // 60)} minuti (MT5 o la "
                                                      "rete non rispondevano): lo riavvio da solo."))
                    bot.tg.svuota(10)
                finally:
                    uscita(BLOCCATO)
                return
    filo = threading.Thread(target=guarda, name="cane da guardia", daemon=True)
    filo.start()
    return filo


def main() -> None:
    di("Avvio il bot...")
    bot = Bot()
    try:
        bot.avvia()
    except ErroreMT5 as errore:
        di(f"Non parto: {errore}")
        bot.tg.operativo(messaggi.allarme(f"Non parto: {errore}"))
        sys.exit(1)
    di(f"Partito: lavoro su {len(bot.strumenti)} mercati. Da qui scrivo su Telegram; questa finestra resta aperta "
       "(chiuderla ferma il bot).")
    bot.battito = time.time()
    cane_da_guardia(bot)
    while True:
        bot.battito = time.time()
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
        try:
            bot.controlla_versione()
        except SystemExit:
            raise
        except Exception:
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
