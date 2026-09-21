"""I divieti permanenti di `docs/06_esclusioni.md`.

Differenza da `contesto.py`: la' ci sono condizioni **temporanee** che
sospendono l'operativita'. Qui ci sono divieti che non ammettono eccezioni e
non sono soggetti a valutazione caso per caso.

Per `PREC-05` questo file batte tutto: nessuna regola di alcun altro file puo'
autorizzare cio' che e' vietato qui.

**A cosa serve, dato che le altre regole gia' impediscono queste cose.** Serve
proprio a questo. Se un giorno un errore in `setup.py` o in `rischio.py`
lasciasse passare un ordine contro la bias di comando, o senza stop, o su uno
strumento fuori dall'universo, `verifica_divieti()` lo fermerebbe comunque.
E' l'ultima riga di difesa, e l'unica il cui compito e' non fidarsi delle
altre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.definizioni import Bias
from core.rischio import stop_obbligatorio
from core.parametri import MAX_POSIZIONI_PER_STRUMENTO, TF, TF_SOLO_GAP, UNIVERSO, gerarchia


@dataclass(frozen=True)
class Divieto:
    """Un divieto violato, con l'ID della regola."""

    regola: str
    motivo: str


@dataclass(frozen=True)
class OrdineProposto:
    """Quanto basta a `verifica_divieti` per dire se un ordine e' lecito.

    Non e' l'ordine che arriva al broker: e' la sua descrizione, ridotta ai
    soli campi su cui i divieti si pronunciano.
    """

    strumento: str
    direzione: Bias
    bias_comando: Bias
    tf_crt: TF
    key_level_preso: bool
    livello_stop: Optional[float]
    prezzo_ingresso: float
    posizioni_aperte_strumento: int
    target_comando_raggiunto: bool
    su_posizione_in_perdita: bool = False
    stop_allargato: bool = False
    stop_spostato_prima_di_tp1: bool = False
    usa_trailing: bool = False
    indicatori_usati: tuple[str, ...] = ()
    prezzi_future_e_cfd_confrontati: bool = False
    candela_in_formazione: bool = False


# Gli unici indicatori ammessi, e a quali condizioni (ESCL-15).
INDICATORI_AMMESSI: frozenset[str] = frozenset({"RSI", "ATR"})


def verifica_divieti(ordine: OrdineProposto) -> tuple[Divieto, ...]:
    """Applica tutti i divieti di 06_esclusioni.md a un ordine proposto.

    Restituisce l'elenco dei divieti violati. Vuoto significa che nessun
    divieto permanente si oppone.

    Un ordine che viola anche un solo divieto non parte, qualunque cosa dicano
    gli altri file (PREC-05).
    """
    violati: list[Divieto] = []

    # --- Divieti sull'operativita' ---------------------------------------
    if ordine.bias_comando is Bias.NESSUNA:
        violati.append(Divieto("ESCL-01", "nessuna bias di comando definita"))
    elif ordine.direzione is not ordine.bias_comando:
        violati.append(
            Divieto("ESCL-01", f"ordine {ordine.direzione.value} contro bias_comando {ordine.bias_comando.value}")
        )
        if not ordine.target_comando_raggiunto:
            violati.append(Divieto("ESCL-03", "reversal prima che il target di tf_comando sia raggiunto"))

    if not ordine.key_level_preso:
        violati.append(Divieto("ESCL-02", "ingresso senza la presa di un key level"))

    if ordine.tf_crt in TF_SOLO_GAP:
        violati.append(Divieto("ESCL-04", f"{ordine.tf_crt.value} serve solo ai gap (DEF-31)"))
    elif ordine.tf_crt not in gerarchia():
        violati.append(Divieto("ESCL-04", f"timeframe fuori da DEF-01: {ordine.tf_crt}"))

    if ordine.strumento not in UNIVERSO:
        violati.append(Divieto("ESCL-05", f"strumento fuori da PRIN-08: {ordine.strumento}"))

    # --- Divieti sulla gestione ------------------------------------------
    if ordine.su_posizione_in_perdita:
        violati.append(Divieto("ESCL-06", "incremento di size su una posizione in perdita"))
    if ordine.stop_allargato:
        violati.append(Divieto("ESCL-07", "stop allargato"))
    if ordine.stop_spostato_prima_di_tp1:
        violati.append(Divieto("ESCL-08", "stop spostato prima del raggiungimento di TP1"))
    if ordine.usa_trailing:
        violati.append(Divieto("ESCL-09", "trailing stop, vietato in qualsiasi forma"))
    if not stop_obbligatorio(ordine.livello_stop):
        # RISK-11 ed ESCL-10 sono la stessa condizione scritta in due file.
        # La funzione sta in `rischio` e vale la pena chiamarla invece di
        # riscrivere qui `is None`: due copie della stessa regola divergono.
        violati.append(Divieto("ESCL-10", "nessuno stop loss definito"))
    elif ordine.livello_stop == ordine.prezzo_ingresso:
        violati.append(Divieto("ESCL-10", "stop coincidente con l'ingresso: distanza nulla"))
    if ordine.posizioni_aperte_strumento >= MAX_POSIZIONI_PER_STRUMENTO:
        violati.append(
            Divieto("ESCL-11", f"{ordine.posizioni_aperte_strumento} posizioni gia' aperte su {ordine.strumento}")
        )

    # --- Divieti sui dati -------------------------------------------------
    if ordine.prezzi_future_e_cfd_confrontati:
        violati.append(Divieto("ESCL-12", "confronto fra un prezzo future e uno CFD"))
    if ordine.candela_in_formazione:
        violati.append(Divieto("ESCL-13", "valutazione di una candela in formazione"))
    for indicatore in ordine.indicatori_usati:
        if indicatore not in INDICATORI_AMMESSI:
            violati.append(Divieto("ESCL-15", f"indicatore non ammesso: {indicatore}"))

    return tuple(violati)


def gap_puo_tornare_valido() -> bool:
    """ESCL-16 — Un gap INVALIDATO non torna mai valido, in nessuna circostanza."""
    return False


def livello_puo_tornare_disponibile() -> bool:
    """ESCL-17 — Un livello CONSUMATO non torna mai disponibile."""
    return False


def id_riciclabile(identificativo: str) -> bool:
    """ESCL-18 — Se una regola viene ritirata, il suo ID muore con lei.

    Gli ID ritirati e mai riutilizzabili dichiarati da `01_definizioni.md`
    sono DEF-05, DEF-06, DEF-07 e DEF-08. `SETUP-08` non e' stato riciclato
    quando la tabella DXY e' rientrata: le e' stato dato `SETUP-19`.
    """
    del identificativo
    return False


ID_RITIRATI: frozenset[str] = frozenset({"DEF-05", "DEF-06", "DEF-07", "DEF-08", "DEF-15"})


def strumento_abilitabile_da_parametro() -> bool:
    """ESCL-24 — Non esistono strumenti abilitati da parametro.

    Aggiungere uno strumento richiede di modificare PRIN-08, non un file di
    configurazione. Nel codice questo e' garantito dalla struttura:
    `UNIVERSO` in `parametri.py` e' un dizionario scritto a mano, non un
    valore letto dal `.env`, e `SCELTE` non puo' toccarlo.
    """
    return False


# ESCL-19, ESCL-20, ESCL-21, ESCL-22 e ESCL-23 non hanno codice, ed e'
# corretto cosi': sono regole su **come si scrivono e si mantengono i
# documenti**, non sul comportamento del bot.
#
#   ESCL-19  mai un aggettivo valutativo senza soglia numerica
#   ESCL-20  mai rimandi impliciti fra parti dei documenti
#   ESCL-21  mai informazione presente solo in un'immagine
#   ESCL-22  mai eccezioni discrezionali alle regole
#   ESCL-23  mai etichettare un caso di 07_casi.md sull'esito del trade
#
# ESCL-22 e' quella che il codice rispetta per costruzione: non esiste alcun
# percorso che porti a un ordine se non attraverso le regole. Non c'e' un
# ramo "opera comunque".
REGOLE_SUI_DOCUMENTI: frozenset[str] = frozenset(
    {"ESCL-19", "ESCL-20", "ESCL-21", "ESCL-22", "ESCL-23"}
)


# ===========================================================================
# Cio' che invece e' ammesso (sezione 6 di 06_esclusioni.md)
# ===========================================================================
# Elencato perche' non venga confuso con un divieto. Ognuna di queste
# funzioni restituisce True: sono permessi, non vincoli.


def chiusura_manuale_ammessa() -> bool:
    """AMM-01 — L'operatore puo' chiudere in qualsiasi momento.

    Non viola alcuna regola. Va pero' annotata in `07_casi.md` con etichetta
    di conformita': una chiusura manuale non prevista dalle regole e', per
    definizione, NON CONFORME. Registrarla e' cio' che permette di capire se
    convenga cambiare una regola o correggere il comportamento.
    """
    return True


def riapertura_dopo_stop_ammessa() -> bool:
    """AMM-02 — Nessun timeframe resta bruciato dopo una perdita."""
    return True


def direzioni_opposte_su_strumenti_diversi_ammesse() -> bool:
    """AMM-03 e SETUP-18 — Ogni strumento e' valutato indipendentemente."""
    return True


def mantenimento_nel_fine_settimana_ammesso() -> bool:
    """AMM-04 e RISK-14 — Le posizioni non si chiudono per calendario.

    Resta il rischio di apertura domenicale, che nessuno stop puo' coprire:
    il prezzo puo' aprire oltre il livello. E' accettato consapevolmente
    (PA-37).
    """
    return True


def operativita_durante_rollover_ammessa() -> bool:
    """AMM-05, CTX-11 e DEF-35 — I gap da rollover sono gap ordinari."""
    return True
