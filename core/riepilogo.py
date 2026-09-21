"""Il riepilogo periodico su Telegram: cosa ha fatto il bot, e perche' no.

## Perche' esiste

Telegram avvisava solo su un ordine mandato o bloccato. Ma i CRT validi sono
rari per costruzione - 226 operazioni in vent'anni sulla configurazione
migliore - quindi per giorni interi non c'e' niente da mandare, e da fuori un
bot che lavora e si astiene e un bot spento sono identici.

L'autore lo ha detto con parole sue: *"Telegram stampa messaggi, solo che son
pochi e non spiega nulla"*. Questo modulo risponde a quello: ogni poche ore un
messaggio che dice quante valutazioni sono state fatte, quanti CRT sono stati
trovati davvero, **quale regola** li ha fermati, e in che stato sono i dati su
cui tutto questo e' stato deciso.

## Cosa NON fa

Non manda un messaggio per ogni astensione. Nelle ultime ventiquattro ore le
astensioni sono state oltre mille: notificarle una per una renderebbe Telegram
inutile esattamente come lo e' il silenzio, solo piu' rumoroso.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from core import storage
from core.log import diario

log = diario("riepilogo")

# Ogni quanto mandare il riepilogo. Sei ore: abbastanza spesso da accorgersi
# in giornata che qualcosa si e' fermato, abbastanza raro da non diventare
# rumore che si smette di leggere.
ORE_FRA_RIEPILOGHI = 6.0

# I codici delle regole stanno in coda al motivo, fra parentesi quadre:
# "... [RISK-05, PRIN-99]".
_CODICI = re.compile(r"\[([A-Z]{3,5}-\d{2}(?:,\s*[A-Z]{3,5}-\d{2})*)\]")

# Cosa significano i blocchi piu' frequenti, in italiano. Un codice da solo
# non spiega niente a chi non ha la bibbia aperta davanti.
SPIEGAZIONI: dict[str, str] = {
    "SETUP-00": "nessun CRT: il prezzo non ha preso un key level superiore",
    "RISK-05": "la bias del DXY era contraria alla direzione del CRT",
    "CRT-20": "conferme di Romeo: ombre di N2 troppo strette",
    "SETUP-05": "meno di due timeframe superiori allineati",
    "SETUP-07": "direzione del CRT opposta alla bias di comando",
    "SETUP-09": "il setup non ha superato i controlli di ingresso",
    "GEST-01": "rapporto rischio/rendimento sotto 1,5 sul primo bersaglio",
    "CTX-02": "finestra di una notizia ad alto impatto",
    "CTX-04": "giorno di festivita'",
    "DEF-26": "storia insufficiente su quel timeframe",
    "PRIN-99": "dati mancanti: il bot si astiene invece di indovinare",
    "PRIN-13": "domenica: si opera solo da TF_1W in su",
    "GIUD-02": "il trader discrezionale ha rifiutato",
    "RISK-02": "limite di rischio del gruppo di correlazione",
    "RISK-06": "tetto di posizioni sullo strumento",
    "ESCL-11": "posizione gia' aperta sullo stesso strumento",
}


def _codici(motivo: str) -> list[str]:
    trovati = _CODICI.findall(motivo or "")
    fuori: list[str] = []
    for gruppo in trovati:
        fuori.extend(c.strip() for c in gruppo.split(","))
    return fuori


def _conteggi(da: datetime) -> tuple[int, int, dict[str, int], int]:
    """(valutazioni, crt trovati, blocchi per codice, operazioni)."""
    with storage.connessione() as conn:
        righe = conn.execute(
            "SELECT azione, motivo FROM decisione WHERE creata_utc >= ?",
            (da.strftime("%Y-%m-%dT%H:%M:%S+00:00"),),
        ).fetchall()

    blocchi: dict[str, int] = {}
    crt = 0
    operazioni = 0
    for riga in righe:
        motivo = str(riga["motivo"] or "")
        codici = set(_codici(motivo))
        if str(riga["azione"] or "") in ("BUY", "SELL"):
            operazioni += 1
        # "Nessun CRT" e "manca il dato" non sono un CRT trovato e scartato:
        # sono i casi in cui non c'era proprio niente da valutare.
        if {"SETUP-00", "DEF-26", "PRIN-99"} & codici:
            continue
        crt += 1
        # I blocchi si contano SOLO sui CRT veri. Contandoli su tutte le
        # decisioni, i filtri di contesto - che il motore valuta anche
        # quando il CRT non c'e' - schiacciavano tutto il resto: in una
        # domenica `PRIN-13` compariva 946 volte su 1.018 decisioni, e il
        # messaggio diceva che aveva fermato 946 CRT quando i CRT erano 66.
        for codice in codici:
            blocchi[codice] = blocchi.get(codice, 0) + 1
    return len(righe), crt, blocchi, operazioni


def _freschezza() -> list[str]:
    """Le serie che contano e quanto sono vecchie, in righe gia' pronte."""
    adesso = datetime.now(timezone.utc)
    fuori = []
    for riga in storage.copertura_candele():
        if riga["strumento"] != "EURUSD" or riga["tf"] not in ("TF_H1", "TF_1D"):
            continue
        try:
            quando = datetime.fromisoformat(str(riga["alla"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        ore = (adesso - quando).total_seconds() / 3600
        fuori.append(f"{riga['tf']}: {ore:.1f}h fa")
    return fuori


def _bias_dxy() -> str:
    """La bias di comando, o perche' non c'e'."""
    try:
        from core.config import impostazioni
        from core.fornitore_tradingview import FornitoreTradingView
        from core.simboli import DXY_FUTURE
        from core.stato import bias_comando_dxy

        fornitore = FornitoreTradingView(
            suffisso_broker=impostazioni().MT5_SUFFISSO_SIMBOLI)
        storico = fornitore.storico(DXY_FUTURE)
        if not sum(len(v) for v in storico.values()):
            return "assente (SETUP-19 non abilita nulla)"
        return bias_comando_dxy(storico, datetime.now(timezone.utc)).value
    except Exception as errore:                       # pragma: no cover
        log.warning("bias del DXY non leggibile: %r", errore)
        return "non leggibile"


def componi(ore: float = ORE_FRA_RIEPILOGHI) -> str:
    """Il testo del riepilogo delle ultime `ore`."""
    da = datetime.now(timezone.utc) - timedelta(hours=ore)
    valutazioni, crt, blocchi, operazioni = _conteggi(da)

    righe = [f"Riepilogo ultime {ore:.0f}h"]
    righe.append(f"Valutazioni: {valutazioni}")
    righe.append(f"CRT trovati: {crt}")
    righe.append(f"Operazioni aperte: {operazioni}")

    if crt:
        righe.append("")
        righe.append("Cosa ha fermato i CRT trovati:")
        interessanti = [
            (c, n) for c, n in blocchi.items() if c not in ("SETUP-00", "PRIN-99")
        ]
        for codice, quante in sorted(interessanti, key=lambda x: -x[1])[:6]:
            spiega = SPIEGAZIONI.get(codice, "")
            righe.append(f"  {quante}x {codice}" + (f" - {spiega}" if spiega else ""))
    elif valutazioni:
        righe.append("")
        righe.append(
            "Nessun CRT valido in questa finestra: il prezzo non ha preso "
            "nessun key level di timeframe superiore. E' il caso normale - "
            "i CRT sono rari."
        )

    # I setup armati stanno in `core/ingresso_ltf`, non in storage: sono lo
    # stato fra i due tempi di CRT-13 (il CRT c'e', l'ingresso si aspetta).
    try:
        from core.ingresso_ltf import armati

        in_attesa = armati()
        righe.append(f"Setup armati in attesa: {len(in_attesa)}")
        for setup in in_attesa[:3]:
            righe.append(
                f"  {setup.strumento} {setup.direzione.value} da {setup.tf_crt}, "
                f"attende su {setup.tf_ingresso} (barra {setup.barre_attesa})"
            )
    except Exception:                                  # pragma: no cover
        log.warning("setup armati non leggibili", exc_info=True)

    righe.append("")
    righe.append(f"Bias DXY: {_bias_dxy()}")
    fresche = _freschezza()
    if fresche:
        righe.append("Archivio EURUSD - " + ", ".join(fresche))

    try:
        aperte = storage.posizioni_aperte()
        righe.append(f"Posizioni aperte: {len(aperte)}")
    except Exception:                                  # pragma: no cover
        pass

    return "\n".join(righe)


def manda(ore: float = ORE_FRA_RIEPILOGHI) -> bool:
    """Compone e manda il riepilogo. Non solleva mai."""
    from core import notifier

    try:
        testo = componi(ore)
    except Exception:
        log.exception("riepilogo non componibile")
        return False
    inviato, _ = notifier.invia(testo)
    return inviato
