"""Lettura del calendario news da file locale (PA-54).

`CTX-02` e `RISK-13` indicano investing.com come fonte, ma non dicono come si
legga. La decisione presa e' un **file locale**, riletto a ogni valutazione:
nessuna dipendenza in piu', nessuna chiamata di rete nel percorso che porta a
un ordine, e un formato che si puo' compilare a mano o con uno script che non
fa parte del motore.

Se il file manca, e' vuoto o e' piu' vecchio della soglia, si applica `PA-55`:
astensione. Il motore lo verifica con `contesto.calendario_utilizzabile()`.

**Formato.** CSV con intestazione, quattro colonne:

```
data_ora_utc,valuta,stelle,descrizione
2026-03-10T14:30:00Z,USD,3,Non-Farm Payrolls
2026-03-11T09:00:00Z,EUR,2,Produzione industriale
```

Le righe con meno di tre stelle si leggono lo stesso e le filtra `CTX-02`:
tenerle permette di distinguere "nessuna news importante" da "file vuoto".
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from core.contesto import EventoNews

INTESTAZIONE: tuple[str, ...] = ("data_ora_utc", "valuta", "stelle", "descrizione")


class CalendarioMalformato(ValueError):
    """Il file esiste ma non e' leggibile come calendario.

    Non e' la stessa cosa di un file assente: un file rotto va segnalato, non
    trattato come "nessuna news".
    """


def interpreta_riga(riga: dict[str, str], numero: int) -> Optional[EventoNews]:
    """Trasforma una riga del CSV in un evento, o solleva se e' malformata.

    Restituisce None per le righe vuote, che sono tollerate: un file compilato
    a mano ne contiene sempre.
    """
    grezzo = (riga.get("data_ora_utc") or "").strip()
    if not grezzo:
        return None

    try:
        momento = datetime.fromisoformat(grezzo.replace("Z", "+00:00"))
    except ValueError as errore:
        raise CalendarioMalformato(f"riga {numero}: data non interpretabile: {grezzo!r}") from errore
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)

    valuta = (riga.get("valuta") or "").strip().upper()
    if not valuta:
        raise CalendarioMalformato(f"riga {numero}: valuta mancante")

    try:
        stelle = int((riga.get("stelle") or "0").strip())
    except ValueError as errore:
        raise CalendarioMalformato(f"riga {numero}: stelle non numeriche") from errore

    return EventoNews(momento.astimezone(timezone.utc), valuta, stelle)


def leggi_calendario(percorso: str | Path) -> tuple[EventoNews, ...]:
    """Legge il file e restituisce gli eventi, ordinati per orario.

    Solleva `FileNotFoundError` se il file non c'e' e `CalendarioMalformato` se
    c'e' ma non si legge. Chi chiama distingue i due casi: il primo e' uno
    stato previsto, il secondo un errore da mostrare.
    """
    percorso = Path(percorso)
    with percorso.open(encoding="utf-8", newline="") as file:
        lettore = csv.DictReader(file)
        if lettore.fieldnames is None:
            raise CalendarioMalformato(f"{percorso}: file senza intestazione")
        mancanti = set(INTESTAZIONE[:3]) - set(lettore.fieldnames)
        if mancanti:
            raise CalendarioMalformato(f"{percorso}: colonne mancanti: {sorted(mancanti)}")

        eventi: list[EventoNews] = []
        for numero, riga in enumerate(lettore, start=2):
            evento = interpreta_riga(riga, numero)
            if evento is not None:
                eventi.append(evento)

    return tuple(sorted(eventi, key=lambda e: e.orario_utc))


def eta_ore(percorso: str | Path, adesso: datetime) -> Optional[float]:
    """Da quante ore il file non viene aggiornato.

    None se il file non esiste. Serve a `PA-55`: un calendario vecchio non e'
    utilizzabile, perche' potrebbe non contenere la news di fra due minuti.
    """
    percorso = Path(percorso)
    if not percorso.exists():
        return None
    modificato = datetime.fromtimestamp(percorso.stat().st_mtime, tz=timezone.utc)
    return (adesso - modificato).total_seconds() / 3600.0


def carica(
    percorso: str | Path,
    adesso: datetime,
) -> tuple[Optional[tuple[EventoNews, ...]], Optional[float], str]:
    """Carica calendario ed eta', senza sollevare.

    Restituisce (eventi, eta_ore, motivo). Con eventi a None il motore si
    astiene per PA-55, e `motivo` dice perche': e' l'unica informazione che
    serve per capire, dal log, se il bot sta fermo per colpa di un file.
    """
    percorso = Path(percorso)
    if not percorso.exists():
        return None, None, f"calendario assente: {percorso}"
    try:
        eventi = leggi_calendario(percorso)
    except CalendarioMalformato as errore:
        return None, None, f"calendario illeggibile: {errore}"
    except OSError as errore:
        return None, None, f"calendario non apribile: {errore!r}"

    if not eventi:
        # Un file con la sola intestazione non e' "oggi non esce niente": e'
        # un file mai compilato. La differenza esiste perche' questo formato
        # chiede di tenere anche gli eventi a una e due stelle (li filtra poi
        # CTX-02), quindi una giornata davvero tranquilla ha comunque righe.
        # Trattarlo come vuoto-ma-valido significherebbe spegnere in silenzio
        # un filtro che CTX-01 #8 e SETUP-15 rendono obbligatorio, e bastava
        # creare il file per farlo.
        return None, None, (
            f"calendario vuoto: {percorso} esiste ma non contiene nemmeno un "
            f"evento. Finche' non lo compili il bot non opera (PA-55)"
        )

    eta = eta_ore(percorso, adesso)
    return eventi, eta, f"{len(eventi)} eventi, aggiornato {eta:.1f} ore fa" if eta is not None else "eta' ignota"


def scrivi_modello(percorso: str | Path) -> None:
    """Crea un calendario di esempio, con la sola intestazione e un commento.

    Serve a partire: senza file il bot non opera, e un file vuoto ma valido e'
    meglio di un errore alla prima valutazione.
    """
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with percorso.open("w", encoding="utf-8", newline="") as file:
        scrittore = csv.writer(file)
        scrittore.writerow(INTESTAZIONE)
