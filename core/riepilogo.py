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
    "PRIN-13": "domenica: si opera solo dal settimanale in su",
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


# I nomi dei timeframe come li direbbe una persona, non come li scrive il
# codice. "TF_M1min" in un messaggio sul telefono non lo legge nessuno.
NOMI_TF: dict[str, str] = {
    "TF_M1min": "1 min", "TF_M5": "5 min", "TF_M15": "15 min",
    "TF_H1": "1 ora", "TF_H4": "4 ore", "TF_1D": "giornaliero",
    "TF_1W": "settimanale", "TF_1M": "mensile",
}

# Le serie da cui dipende una decisione intraday. Se una di queste resta
# indietro il bot decide su prezzi vecchi, ed e' gia' successo per giorni
# senza che nulla lo dicesse.
TF_DA_SORVEGLIARE: tuple[str, ...] = ("TF_M5", "TF_M15", "TF_H1", "TF_1D")


def _numero(valore: float, decimali: int = 2) -> str:
    """Un numero come si scrive in italiano: 1.002,66 e non 1,002.66."""
    testo = f"{valore:,.{decimali}f}"
    return testo.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _quanto_fa(ore: float) -> str:
    """Un'eta' leggibile: '12 min fa', '3 ore fa', '2 giorni fa'."""
    if ore < 1:
        return f"{int(round(ore * 60))} min fa"
    if ore < 48:
        return f"{_numero(ore, 1)} ore fa"
    return f"{_numero(ore / 24, 1)} giorni fa"


def _freschezza() -> list[str]:
    """Quanto sono vecchie le serie che contano, su TUTTI gli strumenti.

    Prima qui c'era EURUSD e basta, come campione. Dal telefono sembrava che
    il bot seguisse una coppia sola: l'autore lo ha fatto notare, e aveva
    ragione a dubitarne.
    """
    from core.parametri import UNIVERSO

    adesso = datetime.now(timezone.utc)
    ritardi: dict[str, float] = {}
    for riga in storage.copertura_candele():
        strumento = str(riga["strumento"])
        if strumento not in UNIVERSO or str(riga["tf"]) not in TF_DA_SORVEGLIARE:
            continue
        try:
            quando = datetime.fromisoformat(str(riga["alla"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        ore = (adesso - quando).total_seconds() / 3600
        chiave = f"{strumento} {NOMI_TF.get(str(riga['tf']), str(riga['tf']))}"
        ritardi[chiave] = ore

    if not ritardi:
        return ["nessuna serie leggibile"]

    peggiore = max(ritardi.items(), key=lambda x: x[1])
    quante_indietro = sum(1 for ore in ritardi.values() if ore > 26)
    fuori = [f"{len(ritardi)} serie su {len(UNIVERSO)} strumenti"]
    if quante_indietro:
        fuori.append(f"ATTENZIONE: {quante_indietro} indietro di oltre un giorno")
    fuori.append(f"la piu' vecchia: {peggiore[0]}, {_quanto_fa(peggiore[1])}")
    return fuori


def _crt_per_strumento(da: datetime) -> list[tuple[str, int]]:
    """Quanti CRT per ciascuno dei sei, cosi' si vede che li guarda tutti."""
    from core.simboli import cfd_di, future_da_ticker

    with storage.connessione() as conn:
        righe = conn.execute(
            "SELECT a.simbolo AS simbolo, d.motivo AS motivo "
            "FROM decisione d JOIN alert a ON a.id = d.alert_id "
            "WHERE d.creata_utc >= ?",
            (da.strftime("%Y-%m-%dT%H:%M:%S+00:00"),),
        ).fetchall()

    from core.parametri import UNIVERSO

    # Si parte da zero per TUTTI e sei: uno strumento senza CRT in questa
    # finestra deve comparire con uno zero, non sparire. Sparendo faceva
    # credere che il bot ne seguisse solo alcuni.
    conta: dict[str, int] = {nome: 0 for nome in UNIVERSO}
    for riga in righe:
        codici = set(_codici(str(riga["motivo"] or "")))
        if {"SETUP-00", "DEF-26", "PRIN-99"} & codici:
            continue
        future = future_da_ticker(str(riga["simbolo"] or ""))
        nome = (cfd_di(future) if future else None) or str(riga["simbolo"])
        conta[nome] = conta.get(nome, 0) + 1
    return sorted(conta.items(), key=lambda x: (-x[1], x[0]))


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
    """Il testo del riepilogo delle ultime `ore`.

    Scritto per essere letto dal telefono: righe corte, niente codici nudi
    senza il loro significato, numeri all'italiana. Un messaggio che si
    salta perche' illeggibile vale quanto un messaggio non mandato.
    """
    adesso = datetime.now(timezone.utc)
    da = adesso - timedelta(hours=ore)
    valutazioni, crt, blocchi, operazioni = _conteggi(da)

    righe = [
        f"RIEPILOGO {ore:.0f}h  -  {adesso:%d/%m %H:%M} UTC",
        "",
        "STRATEGIA",
        f"Valutazioni: {valutazioni}",
        f"CRT trovati: {crt}",
    ]

    # I setup armati sono lo stato fra i due tempi di CRT-13: il CRT c'e' e
    # si aspetta il ritorno nell'FVG. E' il momento in cui c'e' davvero
    # un'occasione, quindi va per primo fra le cose che contano.
    in_attesa = []
    try:
        from core.ingresso_ltf import armati

        in_attesa = armati()
    except Exception:                                  # pragma: no cover
        log.warning("setup armati non leggibili", exc_info=True)
    righe.append(f"Setup armati: {len(in_attesa)}")
    righe.append(f"Operazioni aperte: {operazioni}")
    for setup in in_attesa[:3]:
        righe.append(
            f"  -> {setup.strumento} {setup.direzione.value} da "
            f"{NOMI_TF.get(setup.tf_crt, setup.tf_crt)}, attende su "
            f"{NOMI_TF.get(setup.tf_ingresso, setup.tf_ingresso)}"
        )

    per_strumento = _crt_per_strumento(da)
    if per_strumento:
        righe += ["", "CRT PER STRUMENTO"]
        righe.append("  ".join(f"{nome} {quanti}" for nome, quanti in per_strumento))

    if crt:
        righe += ["", "COSA LI HA FERMATI"]
        interessanti = [
            (c, n) for c, n in blocchi.items() if c not in ("SETUP-00", "PRIN-99")
        ]
        for codice, quante in sorted(interessanti, key=lambda x: -x[1])[:6]:
            righe.append(f"{quante}x {codice}")
            spiega = SPIEGAZIONI.get(codice)
            if spiega:
                righe.append(f"   {spiega}")
    elif valutazioni:
        righe += ["", "COSA LI HA FERMATI"]
        righe.append(
            "Nessun CRT valido: il prezzo non ha preso nessun key level di "
            "timeframe superiore. E' il caso normale, i CRT sono rari."
        )

    righe += ["", "CONTO"]
    try:
        from core import broker

        ok, dati, _ = broker.info_conto()
        if ok and dati:
            righe.append(f"Saldo: {_numero(float(dati['equity']))} {dati['valuta']}")
    except Exception:                                  # pragma: no cover
        log.warning("conto non leggibile", exc_info=True)
    try:
        righe.append(f"Posizioni aperte: {len(storage.posizioni_aperte())}")
    except Exception:                                  # pragma: no cover
        pass
    righe.append(f"Bias del dollaro: {_bias_dxy()}")

    righe += ["", "DATI"]
    righe += _freschezza()

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
