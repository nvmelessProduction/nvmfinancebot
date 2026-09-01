"""Segnaposto della strategia. QUI NON C'E' NIENTE, ED E' VOLUTO.

Questo file e' l'unico punto in cui andra' scritta la logica di trading,
quando i documenti che la descrivono saranno pronti. Finche' quel momento
non arriva, `valuta` restituisce sempre azione "NONE" e l'impianto gira a
vuoto: riceve gli alert, li archivia, non apre nulla.

Non aggiungere qui medie mobili, RSI, gestione del rischio o calcolo della
size "nel frattempo": sarebbe codice da buttare, perche' la strategia vera
non assomiglia a nessuna strategia standard.

Quando sara' il momento, il contratto da rispettare e' solo questo:
    - ingresso: un AlertIn gia' validato e gia' salvato in archivio
    - uscita:   un Decision con azione BUY / SELL / CLOSE / NONE,
                e, se serve operare, volume ed eventuali livelli sl e tp
Tutto il resto (persistenza, notifiche, invio ordini) e' gia' pronto attorno.
"""

from core.models import AlertIn, Decision


def valuta(alert: AlertIn) -> Decision:
    """Decide cosa fare a fronte di un alert.

    STUB: restituisce sempre "NONE". La strategia va scritta qui.
    """
    # <-- QUI ANDRA' LA STRATEGIA -->
    # L'alert e' disponibile per intero (alert.simbolo, alert.chiusura, ...)
    # ma di proposito non viene ancora letto.
    return Decision(
        action="NONE",
        motivo="strategia non ancora implementata (stub in core/strategy.py)",
    )
