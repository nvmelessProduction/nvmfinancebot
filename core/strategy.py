"""Il ponte fra l'impianto webhook e il motore di strategia.

Fino alla v0.2 questo file era uno stub che restituiva sempre `NONE`, perche'
la strategia non esisteva. Ora esiste: sta in `core/motore.py` e nei moduli che
lo circondano, ed e' la traduzione delle regole di `docs/`.

**Quello che manca non e' la strategia: e' il livello dati.** Un alert di
TradingView, da solo, non basta a far girare questo motore. La `Fotografia` che
`motore.valuta()` richiede vuole cinque anni di storia su dieci timeframe, i
key level presi, le fasi del gap, l'equity, il calendario news. L'alert non e'
l'ingresso del motore: e' l'**innesco** che dice "una candela si e' chiusa,
rivaluta".

Per questo qui c'e' un innesto, non un'implementazione. Chi ha i dati registra
un fornitore con `registra_fornitore()`; finche' nessuno lo fa, il bot risponde
`NONE` dicendo che il livello dati non e' collegato — che e' la verita', ed e'
meglio di un `NONE` muto che sembra una decisione di strategia.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.log import diario
from core.models import AlertIn, Decision
from core.motore import Decisione, Fotografia
from core.motore import valuta as valuta_motore
from core.parametri import TF

log = diario("strategy")

# Un fornitore riceve l'alert e restituisce (fotografia, timeframe di trigger),
# oppure None se non e' in grado di costruirla per quell'alert.
Fornitore = Callable[[AlertIn], Optional[tuple[Fotografia, TF]]]

_fornitore: Optional[Fornitore] = None


def registra_fornitore(fornitore: Optional[Fornitore]) -> None:
    """Collega il livello dati al motore.

    Passare None scollega, e il bot torna ad astenersi dichiarando il motivo:
    e' il modo per fermare la strategia senza toccare l'impianto.
    """
    global _fornitore
    _fornitore = fornitore


def fornitore_collegato() -> bool:
    """True se qualcuno sa costruire la fotografia."""
    return _fornitore is not None


def traduci(decisione: Decisione) -> Decision:
    """Da `motore.Decisione` al modello che l'impianto gia' conosce.

    L'impianto vuole azione, motivo, volume, sl e tp. La decisione del motore
    porta anche l'elenco delle regole: finisce dentro `motivo`, perche' e' li'
    che l'archivio e Telegram lo faranno vedere. Perderlo significherebbe
    tornare a un bot che non sa dire perche' ha fatto quello che ha fatto.
    """
    regole = ", ".join(
        decisione.regole_che_bloccano if decisione.azione == "NONE"
        else decisione.regole_applicate
    )
    motivo = f"{decisione.motivo} [{regole}]" if regole else decisione.motivo

    return Decision(
        action=decisione.azione,
        # Il motore ragiona sul future ma decide per il CFD: `strumento` e'
        # gia' quello di esecuzione. Il suffisso del broker lo aggiunge
        # l'impianto, perche' e' un fatto del conto e non della strategia.
        symbol=decisione.strumento,
        motivo=motivo,
        volume=decisione.volume,
        sl=decisione.livello_stop,
        tp=decisione.target_finale,
        # GEST-04, GEST-08 e GEST-12: senza questi tre l'impianto riceve una
        # posizione che sa solo morire allo stop o al target, e il parziale
        # del 25% non ha nulla su cui appoggiarsi.
        tp1=decisione.tp1,
        tf_crt=decisione.tf_crt.value if decisione.tf_crt else None,
        spread=decisione.spread,
        rischio=decisione.rischio,
        rapporto_giud01=decisione.rapporto_giud01,
    )


def valuta(alert: AlertIn) -> Decision:
    """Decide cosa fare a fronte di un alert.

    L'alert dice **quando** rivalutare, non **cosa** decidere: il contesto lo
    costruisce il fornitore, dallo storico. Se non c'e' un fornitore, non si
    opera e lo si dice.
    """
    if _fornitore is None:
        return Decision(
            action="NONE",
            motivo=(
                "livello dati non collegato: il motore c'e' ma nessuno "
                "costruisce la Fotografia. Vedi core/strategy.registra_fornitore"
            ),
        )

    try:
        contesto = _fornitore(alert)
    except Exception as errore:
        # Il fornitore sa perche' non ce l'ha fatta, e quel motivo vale piu'
        # del fatto che non ce l'ha fatta: finisce in archivio e su Telegram.
        return Decision(action="NONE", motivo=f"PRIN-99: {errore}")

    if contesto is None:
        return Decision(
            action="NONE",
            motivo=(
                f"PRIN-99: il fornitore non ha potuto costruire la fotografia "
                f"per {alert.simbolo} {alert.tf}"
            ),
        )

    fotografia, tf_trigger = contesto
    return traduci(valuta_motore(fotografia, tf_trigger))


def gestisci_aperte(alert: AlertIn) -> tuple:
    """GEST-08, GEST-10, SETUP-17 — cosa fare alle posizioni gia' aperte.

    Stesso innesto di `valuta`, altra domanda. `valuta` chiede "si apre
    qualcosa?", questa chiede "cambia qualcosa per cio' che e' gia' aperto?".
    Sono separate perche' la prima puo' astenersi per venti motivi diversi —
    news, limiti di rischio, festivita' — che non hanno alcun effetto sulle
    posizioni in corso: un limite giornaliero raggiunto blocca le aperture,
    non la gestione (RISK-10).

    Restituisce una tupla di `rivalutazione.AzioneGestione`, vuota quando non
    c'e' nulla da fare. Non tocca ne' broker ne' archivio.
    """
    from core import storage
    from core.rivalutazione import rivaluta

    if _fornitore is None:
        return ()

    try:
        contesto = _fornitore(alert)
    except Exception as errore:
        log.warning("rivalutazione saltata: %s", errore)
        return ()
    if contesto is None:
        return ()

    aperte = storage.posizioni_aperte()
    if not aperte:
        return ()

    fotografia, tf_trigger = contesto
    return rivaluta(fotografia, tf_trigger, aperte)
