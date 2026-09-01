"""Sorvegliante delle posizioni aperte: stop loss e take profit.

Sul broker non ci sono ordini pendenti. I livelli vivono in archivio, e
qualcuno deve guardarli: quel qualcuno e' questo ciclo, che gira in un thread
suo finche' il server e' acceso.

Cosa fa, e solo questo:
  - confronta il prezzo corrente con i livelli **gia' scritti** in archivio;
  - chiude a mercato quando il livello viene toccato;
  - riconcilia archivio e broker, perche' una posizione puo' sparire senza
    che il bot ne sappia nulla (chiusura a mano, stop out, margin call).

Cosa NON fa, di proposito: non decide i livelli, non li sposta, non fa
trailing, non apre niente. I livelli glieli scrive la strategia, quando
esistera'. Qui c'e' solo l'aritmetica di "il prezzo ha toccato o no".

Nota importante sul freno a mano (file STOP): blocca l'**apertura** di nuove
posizioni, non la sorveglianza. Un interruttore di emergenza che smette anche
di proteggere quello che e' gia' aperto sarebbe un interruttore pericoloso.
"""

import threading
from typing import Any, Optional

from core import broker, notifier, storage
from core.config import impostazioni
from core.log import diario

log = diario("sentinella")


def livello_toccato(
    direzione: str,
    bid: float,
    ask: float,
    sl: Optional[float],
    tp: Optional[float],
) -> Optional[str]:
    """Dice se stop o target sono stati toccati, e quale.

    Si usa il prezzo a cui si **uscirebbe**, non quello a cui si e' entrati:
    una posizione lunga si chiude in bid, una corta in ask. Confrontare uno
    stop di vendita col prezzo di acquisto e' l'errore classico che fa
    scattare gli stop qualche pip prima o dopo del dovuto.

    Restituisce "sl", "tp" oppure None. Se entrambi risultano toccati nello
    stesso istante vince lo stop: fra due letture possibili si sceglie la
    peggiore, perche' non sappiamo in che ordine il prezzo ci sia passato.
    """
    direzione = direzione.upper()
    uscita = bid if direzione == "BUY" else ask

    if direzione == "BUY":
        colpito_sl = sl is not None and uscita <= sl
        colpito_tp = tp is not None and uscita >= tp
    elif direzione == "SELL":
        colpito_sl = sl is not None and uscita >= sl
        colpito_tp = tp is not None and uscita <= tp
    else:
        return None

    if colpito_sl:
        return "sl"
    if colpito_tp:
        return "tp"
    return None


class Sentinella:
    """Il ciclo di sorveglianza, in un thread separato."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.giri: int = 0
        self.ultimo_errore: Optional[str] = None
        self.chiusure: int = 0

    # -- ciclo di vita ----------------------------------------------------
    def avvia(self) -> None:
        """Fa partire il thread di sorveglianza, se non gia' in corsa."""
        cfg = impostazioni()
        if not cfg.SENTINELLA_ATTIVA:
            log.warning(
                "sentinella disattivata da configurazione: stop e target NON "
                "saranno sorvegliati"
            )
            return
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, name="sentinella", daemon=True)
        self._thread.start()
        log.info("sentinella avviata (ogni %.1fs)", cfg.SENTINELLA_INTERVALLO_SEC)

    def ferma(self, attesa: float = 5.0) -> None:
        """Chiede al thread di fermarsi e lo aspetta."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=attesa)
        log.info("sentinella fermata dopo %d giri", self.giri)

    def attiva(self) -> bool:
        """True se il thread sta girando davvero."""
        return self._thread is not None and self._thread.is_alive()

    def _giro_protetto(self) -> None:
        """Un giro che non puo' sollevare.

        Un errore isolato (rete giu', terminale che non risponde) non deve
        spegnere la sorveglianza: si annota e si riprova al giro dopo.
        """
        try:
            self.giro()
            self.ultimo_errore = None
        except Exception as errore:
            self.ultimo_errore = repr(errore)
            log.exception("giro di sorveglianza fallito")

    def _ciclo(self) -> None:
        """Gira finche' non gli si dice di smettere. Non deve morire mai."""
        intervallo = impostazioni().SENTINELLA_INTERVALLO_SEC
        while not self._stop.wait(intervallo):
            self._giro_protetto()

    # -- lavoro vero ------------------------------------------------------
    def giro(self) -> dict[str, Any]:
        """Un singolo passaggio su tutte le posizioni aperte in archivio."""
        self.giri += 1
        aperte = storage.posizioni_aperte()
        if not aperte:
            return {"controllate": 0, "chiuse": 0}

        if not broker.disponibile():
            # Senza broker non possiamo ne' leggere prezzi ne' chiudere.
            # Va detto forte: ci sono posizioni scoperte.
            log.error(
                "ci sono %d posizioni aperte in archivio ma MT5 non e' "
                "disponibile: stop e target NON sono sorvegliati",
                len(aperte),
            )
            return {"controllate": 0, "chiuse": 0, "errore": "MT5 non disponibile"}

        ok_broker, posizioni_broker, messaggio = broker.posizioni_broker()
        if not ok_broker:
            log.error("impossibile leggere le posizioni dal broker: %s", messaggio)
            return {"controllate": 0, "chiuse": 0, "errore": messaggio}

        ticket_sul_broker = {p["ticket"] for p in posizioni_broker}
        chiuse = 0

        for posizione in aperte:
            if self._stop.is_set():
                break
            if self._controlla(posizione, ticket_sul_broker):
                chiuse += 1

        self._segnala_orfane(posizioni_broker, aperte)
        return {"controllate": len(aperte), "chiuse": chiuse}

    def _controlla(self, posizione: dict[str, Any], ticket_sul_broker: set[int]) -> bool:
        """Controlla una singola posizione. True se e' stata chiusa."""
        id_posizione = int(posizione["id"])
        ticket = posizione["ticket"]
        simbolo = str(posizione["simbolo"])
        direzione = str(posizione["direzione"])

        # 1. La posizione esiste ancora sul broker?
        if ticket is None:
            log.warning(
                "posizione %s (%s) senza ticket: non e' sorvegliabile, la chiudo "
                "in archivio",
                id_posizione,
                simbolo,
            )
            storage.chiudi_posizione(id_posizione, None, "senza ticket, non sorvegliabile")
            return False

        if int(ticket) not in ticket_sul_broker:
            # Chiusa a mano, per stop out o dal broker: allineiamo l'archivio.
            log.warning(
                "posizione %s (ticket %s) non e' piu' sul broker: la segno chiusa",
                id_posizione,
                ticket,
            )
            storage.chiudi_posizione(id_posizione, None, "chiusa fuori dal bot")
            notifier.invia(
                f"Posizione {simbolo} (ticket {ticket}) non risulta piu' aperta sul "
                "broker. Archivio allineato."
            )
            return False

        # 2. Ci sono livelli da sorvegliare?
        sl = posizione["sl"]
        tp = posizione["tp"]
        if sl is None and tp is None:
            return False

        # 3. Il prezzo li ha toccati?
        ok_prezzo, tick, messaggio = broker.prezzo_corrente(simbolo)
        if not ok_prezzo or tick is None:
            log.warning("niente prezzo per %s: %s", simbolo, messaggio)
            return False

        colpito = livello_toccato(direzione, tick["bid"], tick["ask"], sl, tp)
        if colpito is None:
            return False

        livello = sl if colpito == "sl" else tp
        log.info(
            "%s toccato su %s (ticket %s): livello %s, bid %s ask %s",
            colpito.upper(),
            simbolo,
            ticket,
            livello,
            tick["bid"],
            tick["ask"],
        )

        # 4. Chiusura. Se fallisce non tocchiamo l'archivio: al prossimo giro
        #    si riprova, ed e' esattamente quello che vogliamo.
        esito = broker.chiudi_posizione(int(ticket))
        if not esito.ok:
            log.error("chiusura di %s fallita: %s", ticket, esito.messaggio)
            notifier.invia(
                f"ATTENZIONE: {colpito.upper()} toccato su {simbolo} (ticket {ticket}) "
                f"ma la chiusura e' fallita: {esito.messaggio}\n"
                "Riprovo al prossimo giro. Controlla il terminale."
            )
            return False

        storage.chiudi_posizione(id_posizione, esito.prezzo, f"{colpito} toccato")
        self.chiusure += 1
        notifier.invia(
            f"{colpito.upper()} su {simbolo} {direzione} (ticket {ticket})\n"
            f"livello {livello}, chiusa a {esito.prezzo}"
        )
        return True

    def _segnala_orfane(
        self,
        posizioni_broker: list[dict[str, Any]],
        aperte_archivio: list[dict[str, Any]],
    ) -> None:
        """Avvisa se sul broker ci sono posizioni del bot che l'archivio non ha.

        Succede se il bot e' stato spento fra l'invio dell'ordine e la sua
        registrazione. Sono posizioni senza stop sorvegliato: vanno viste.
        """
        nostro_magic = impostazioni().MT5_MAGIC
        noti = {p["ticket"] for p in aperte_archivio if p["ticket"] is not None}
        for posizione in posizioni_broker:
            if posizione.get("magic") == nostro_magic and posizione["ticket"] not in noti:
                log.error(
                    "posizione orfana sul broker: ticket %s su %s, aperta dal bot "
                    "ma assente dall'archivio. Nessuno sorveglia i suoi livelli.",
                    posizione["ticket"],
                    posizione["simbolo"],
                )

    def stato(self) -> dict[str, Any]:
        """Riassunto per /salute."""
        cfg = impostazioni()
        return {
            "attiva": self.attiva(),
            "configurata": cfg.SENTINELLA_ATTIVA,
            "intervallo_sec": cfg.SENTINELLA_INTERVALLO_SEC,
            "giri": self.giri,
            "chiusure": self.chiusure,
            "ultimo_errore": self.ultimo_errore,
        }


# Istanza unica usata dal server.
sentinella = Sentinella()
