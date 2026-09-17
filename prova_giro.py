"""Il ciclo puo' davvero decidere? Si scopre in un minuto, non in ventiquattro ore.

## Perche' serve

Un bot che non opera e un bot che opera e si astiene hanno lo stesso aspetto
dall'esterno: `/salute` mostra dei contatori che salgono e nessun errore. La
differenza si vede solo entrando nella catena, e finora si e' vista troppo
tardi -- dopo ore di attesa e un archivio pieno di decisioni che non erano
mai state prese.

Questo script percorre la catena **una volta**, sullo stato reale della
macchina, e dice a quale anello si ferma. Non apre nulla e non scrive nulla.

Una cosa pero' la fa, e va detta: se una valutazione arriva fino a BUY o
SELL, il giudizio discrezionale parte davvero e consuma una chiamata alle
API. E' il comportamento giusto -- verifica anche quel collegamento -- ma non
deve essere una sorpresa. Nessun ordine viene inviato al broker: l'esecuzione
sta in `main.py` e questo script non la chiama.

Le cinque cose che ha gia' sbagliato in silenzio, e che qui si vedono subito:

1. l'alert costruito dal ciclo non era leggibile da chi lo riceve;
2. i timeframe intraday non erano riconoscibili, quindi le coppie di Romeo
   sotto l'ora non potevano scattare;
3. l'archivio era scritto sotto un nome e letto sotto un altro;
4. senza DXY, `SETUP-19` non abilita nulla su cinque coppie su sei;
5. senza cinque anni di storia, `DEF-26` fa tacere i timeframe di bias.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from core import storage
from core.config import impostazioni
from core.duka_dxy import NOME_ARCHIVIO as DXY
from core.log import configura as configura_log
from core.mercato import TF_INGRESSO_OPERATIVI, TF_OPERATIVI
from core.mercato_duka import _alert, ultima_archiviata
from core.parametri import LOOKBACK_ANNI, TF, UNIVERSO

OK, NO, FORSE = "  OK  ", " NO   ", "  ?   "


def riga(stato: str, testo: str) -> None:
    print(f"[{stato}] {testo}")


def prova_archivio(adesso: datetime) -> bool:
    """C'e' abbastanza storia, e sotto il nome giusto?"""
    print("\n--- Archivio ----------------------------------------------------")
    tutto_bene = True
    soglia = adesso - timedelta(days=365 * LOOKBACK_ANNI)

    for strumento in list(UNIVERSO) + [DXY]:
        pezzi = []
        for tf in (TF.M1, TF.D1, TF.H1, TF.MIN15, TF.MIN5, TF.MIN1):
            righe = storage.candele_archiviate(strumento, tf.value)
            if not righe:
                pezzi.append(f"{tf.value.replace('TF_', '')}:-")
                continue
            pezzi.append(f"{tf.value.replace('TF_', '')}:{len(righe)}")
        ultima = ultima_archiviata(strumento, TF.H1)
        if ultima is None:
            riga(NO, f"{strumento:8s} nessuna oraria in archivio")
            tutto_bene = False
            continue
        ritardo = adesso - ultima
        # Sei ore: il fine settimana e le feste fanno ritardi legittimi molto
        # piu' lunghi, quindi un ritardo alto e' un dubbio, non una condanna.
        stato = OK if ritardo < timedelta(hours=6) else FORSE
        riga(stato, f"{strumento:8s} ultima oraria {ultima:%Y-%m-%d %H:%M} "
                    f"({ritardo.total_seconds() / 3600:.1f}h fa)   "
                    + "  ".join(pezzi))

    # DEF-26 vuole cinque anni sui timeframe di bias.
    for strumento in list(UNIVERSO) + [DXY]:
        prime = storage.candele_archiviate(strumento, TF.D1.value)
        if not prime:
            continue
        inizio = str(prime[0]["chiusura_utc"])[:10]
        if inizio > soglia.strftime("%Y-%m-%d"):
            riga(FORSE, f"{strumento:8s} storia giornaliera dal {inizio}: meno di "
                        f"{LOOKBACK_ANNI} anni, DEF-26 fa tacere i timeframe di bias")
            tutto_bene = False
    return tutto_bene


def prova_dxy(adesso: datetime) -> bool:
    """Senza bias del DXY, SETUP-19 non abilita nulla su cinque coppie su sei."""
    print("\n--- Il DXY (SETUP-19) -------------------------------------------")
    from core.stato import bias_comando_dxy
    from core.fornitore_tradingview import FornitoreTradingView

    fornitore = FornitoreTradingView(suffisso_broker=impostazioni().MT5_SUFFISSO_SIMBOLI)
    storico = fornitore.storico(DXY)
    quante = sum(len(v) for v in storico.values())
    if not quante:
        riga(NO, f"archivio del DXY vuoto sotto il nome '{DXY}'. "
                 f"Semina con:  python importa_dxy.py")
        riga(NO, "finche' e' vuoto il motore si astiene su tutte le coppie "
                 "tranne XAUUSD, che PRIN-09 esenta")
        return False

    bias = bias_comando_dxy(storico, adesso)
    if bias.value == "NESSUNA":
        riga(NO, f"{quante} candele in archivio ma bias di comando NESSUNA: "
                 f"SETUP-19 non abilita alcuna operazione")
        return False
    riga(OK, f"{quante} candele, bias di comando {bias.value}")
    return True


def prova_calendario(adesso: datetime) -> bool:
    """Il calendario non ferma piu' il bot, ma quel che perde va detto."""
    from pathlib import Path

    from core import calendario
    from core.parametri import (
        ETA_MASSIMA_CALENDARIO_ORE,
        PERCORSO_CALENDARIO_NEWS,
        richiedi,
    )

    print("\n--- Il calendario news (CTX-02, PA-55) --------------------------")
    lettura = richiedi("PA-55")
    eventi, eta, motivo = calendario.carica(Path(PERCORSO_CALENDARIO_NEWS), adesso)

    if eventi:
        if eta is not None and eta > ETA_MASSIMA_CALENDARIO_ORE:
            riga(FORSE, f"{len(eventi)} eventi ma il file ha {eta:.0f} ore: "
                        f"sono tutti passati, CTX-02 non blocchera' nulla")
        else:
            riga(OK, f"{len(eventi)} eventi, {eta:.0f} ore: CTX-02 funziona")
        return True

    if lettura == "astieniti":
        riga(NO, f"calendario non utilizzabile ({motivo}) e PA-55 vale "
                 f"'astieniti': il bot non aprira' nulla")
        return False

    riga(FORSE, f"calendario non utilizzabile ({motivo}), ma PA-55 vale "
                f"'opera': il bot lavora lo stesso")
    riga(FORSE, "CTX-02 e' spento: nessun divieto di aprire a ridosso di una "
                "notizia a tre stelle")
    return True


def prova_catena(adesso: datetime) -> bool:
    """L'alert che il ciclo costruisce arriva davvero fino a una decisione?"""
    print("\n--- La catena, un alert alla volta ------------------------------")
    from core import strategy
    from core.definizioni import Candela
    from core.simboli import future_da_ticker, timeframe_da_intervallo

    tutto_bene = True
    da_provare = sorted(set(TF_OPERATIVI) | set(TF_INGRESSO_OPERATIVI),
                        key=lambda t: t.value)

    for strumento in UNIVERSO:
        for tf in da_provare:
            righe = storage.candele_archiviate(strumento, tf.value, limite=1)
            if not righe:
                riga(NO, f"{strumento:8s} {tf.value:9s} nessuna candela: "
                         f"questo timeframe non puo' innescare nulla")
                tutto_bene = False
                continue
            r = righe[0]
            candela = Candela(
                datetime.fromisoformat(str(r["chiusura_utc"]).replace("Z", "+00:00")),
                float(r["apertura"]), float(r["massimo"]),
                float(r["minimo"]), float(r["chiusura"]),
            )
            alert = _alert(strumento, tf, candela, impostazioni().WEBHOOK_SECRET or "")

            # I due passaggi che tornavano None senza dirlo.
            if future_da_ticker(alert.simbolo) is None:
                riga(NO, f"{strumento:8s} {tf.value:9s} simbolo {alert.simbolo!r} "
                         f"non riconosciuto")
                tutto_bene = False
                continue
            if timeframe_da_intervallo(alert.tf) is None:
                riga(NO, f"{strumento:8s} {tf.value:9s} intervallo {alert.tf!r} "
                         f"non riconosciuto")
                tutto_bene = False
                continue

            decisione = strategy.valuta(alert)
            motivo = (decisione.motivo or "")[:88]
            if "PRIN-99" in motivo or "livello dati non collegato" in motivo:
                riga(NO, f"{strumento:8s} {tf.value:9s} {motivo}")
                tutto_bene = False
            else:
                stato = OK if decisione.azione in ("BUY", "SELL") else FORSE
                riga(stato, f"{strumento:8s} {tf.value:9s} {decisione.azione}: {motivo}")
    return tutto_bene


def main() -> int:
    configura_log()
    storage.inizializza()
    adesso = datetime.now(timezone.utc)
    cfg = impostazioni()

    print(f"prova del giro  --  {adesso:%Y-%m-%d %H:%M} UTC")
    print(f"fornitore dati: {cfg.FORNITORE_DATI}   modalita': {cfg.MODE}")

    if cfg.FORNITORE_DATI == "dukascopy":
        from core.fornitore_tradingview import collega
        collega(suffisso_broker=cfg.MT5_SUFFISSO_SIMBOLI)

    esiti = [
        prova_archivio(adesso),
        prova_dxy(adesso),
        prova_calendario(adesso),
        prova_catena(adesso),
    ]

    print("\n-----------------------------------------------------------------")
    if all(esiti):
        print("La catena regge: ogni anello risponde. Un NONE qui e' un'astensione")
        print("vera, non un guasto travestito.")
        return 0
    print("Qualcosa non risponde. Le righe [ NO   ] qui sopra dicono cosa, e")
    print("finche' restano il bot non puo' aprire nulla su quegli strumenti.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
