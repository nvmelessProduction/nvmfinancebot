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
from core import gestione
from core.definizioni import Bias
from core.log import diario
from core.parametri import TF

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


def prezzo_di_uscita(direzione: str, bid: float, ask: float) -> float:
    """Il prezzo a cui si uscirebbe adesso da questa posizione.

    Una posizione lunga si chiude in bid, una corta in ask. E' lo stesso
    principio di `livello_toccato`: confrontare uno stop di vendita col
    prezzo di acquisto fa scattare gli stop qualche pip prima o dopo del
    dovuto.
    """
    return bid if direzione.upper() == "BUY" else ask


def tp1_toccato(
    direzione: str,
    bid: float,
    ask: float,
    tp1: Optional[float],
) -> bool:
    """GEST-04 — Il prezzo ha raggiunto TP1?

    L'aritmetica del confronto e' quella di `gestione.raggiunge_tp1`, che e'
    dove la regola vive: qui si aggiunge solo la scelta fra bid e ask, che
    `gestione` non puo' fare perche' non conosce lo spread del broker.
    Riscriverla sarebbe una seconda copia della stessa regola, e due copie
    finiscono per divergere proprio nel punto che muove i soldi.

    TP1 non e' un'uscita: e' un parziale che lascia in vita il 75%. Per
    questo e' separata da `livello_toccato`, che chiude tutto.
    """
    if tp1 is None:
        return False
    if direzione.upper() not in ("BUY", "SELL"):
        return False
    magra = gestione.Posizione(
        strumento="", direzione=_bias(direzione), prezzo_ingresso=0.0,
        tf_crt=TF.H4, livello_stop=0.0, tp1=float(tp1), target_finale=0.0,
    )
    return gestione.raggiunge_tp1(magra, prezzo_di_uscita(direzione, bid, ask))


def _bias(direzione: str) -> Bias:
    return Bias.LONG if direzione.upper() == "BUY" else Bias.SHORT


def volume_del_parziale(
    volume_iniziale: float,
    volume_attuale: float,
    passo_broker: float,
    frazione: float,
) -> Optional[float]:
    """GEST-04 — Quanto chiudere a TP1, arrotondato a cio' che il broker accetta.

    `frazione` la decide `gestione.applica_tp1`, che e' dove GEST-04 dice
    quanto si chiude. Qui si fa solo l'aritmetica del broker: quel numero
    moltiplicato per il volume, arrotondato al passo.

    Il 25% si calcola sul volume **iniziale**, non su quello attuale: sono
    uguali finche' non ci sono stati parziali, e GEST-07 dice che di parziali
    ce n'e' uno solo, ma calcolarlo sull'iniziale e' l'unica lettura che regge
    se un giorno ne comparisse un secondo.

    None quando il parziale non e' eseguibile, e sono due casi distinti che
    qui hanno la stessa risposta:

    - il 25% arrotondato per difetto al passo del broker da' zero. Succede
      sulle posizioni alla size minima, dove un quarto di lotto minimo non
      esiste. Non si chiude nulla e non si tocca lo stop: applicare il break
      even senza aver incassato il parziale cambierebbe l'operazione in una
      che le regole non descrivono.
    - il parziale consumerebbe tutta la posizione. Sarebbe una chiusura
      totale a TP1, che e' proprio cio' che GEST-07 esclude ("il restante 75%
      non ha ulteriori parziali" presuppone che un restante ci sia).
    """
    if passo_broker <= 0 or volume_iniziale <= 0 or volume_attuale <= 0:
        return None
    grezzo = volume_iniziale * frazione
    passi = int(grezzo / passo_broker + 1e-9)
    quota = round(passi * passo_broker, 8)
    if quota <= 0 or quota >= volume_attuale:
        return None
    return quota


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
        tp1 = posizione.get("tp1")
        if sl is None and tp is None and tp1 is None:
            return False

        # 3. Il prezzo li ha toccati?
        ok_prezzo, tick, messaggio = broker.prezzo_corrente(simbolo)
        if not ok_prezzo or tick is None:
            log.warning("niente prezzo per %s: %s", simbolo, messaggio)
            return False

        colpito = livello_toccato(direzione, tick["bid"], tick["ask"], sl, tp)

        # 3bis. TP1 (GEST-04, GEST-07). Si guarda **dopo** stop e target e
        #       solo se nessuno dei due e' stato toccato: fra due letture il
        #       prezzo puo' aver attraversato TP1 e poi essere tornato fino
        #       allo stop, e fra due letture possibili si sceglie la peggiore.
        #       Lo stesso principio di `livello_toccato` quando sl e tp
        #       risultano toccati insieme.
        if colpito is None:
            self._parziale_a_tp1(posizione, tick)
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

    def _parziale_a_tp1(
        self, posizione: dict[str, Any], tick: dict[str, float]
    ) -> bool:
        """GEST-04 e GEST-07 — Chiude il 25% a TP1 e porta il resto a break even.

        Una volta sola per posizione: `tp1_raggiunto` in archivio e' il solo
        stato che sopravvive a un riavvio (GEST-12), e GEST-05 vieta di
        muovere ancora lo stop dopo il break even.

        Le due azioni — parziale e spostamento dello stop — sono un fatto solo
        e vengono scritte insieme. Se il broker esegue il parziale ma la
        scrittura fallisce, la posizione resta col volume ridotto e lo stop
        vecchio: e' rumoroso di proposito, perche' e' l'unico caso in cui
        l'archivio e il broker divergono e va visto subito.

        True se il parziale e' stato eseguito.
        """
        if posizione.get("tp1_raggiunto"):
            return False                                  # GEST-05: una volta sola

        tp1 = posizione.get("tp1")
        if not tp1_toccato(str(posizione["direzione"]), tick["bid"], tick["ask"], tp1):
            return False

        id_posizione = int(posizione["id"])
        ticket = int(posizione["ticket"])
        simbolo = str(posizione["simbolo"])
        direzione = str(posizione["direzione"])

        ok_spec, specifiche, messaggio = broker.specifiche_simbolo(simbolo)
        if not ok_spec or specifiche is None:
            log.warning("niente specifiche per %s: %s", simbolo, messaggio)
            return False

        volume_attuale = float(posizione["volume"])
        volume_iniziale = float(posizione.get("volume_iniziale") or volume_attuale)

        # GEST-04 in persona: quanto si chiude e dove va lo stop lo decide
        # `gestione.applica_tp1`, non questo file. Qui c'e' solo l'aritmetica
        # del broker e l'ordine delle scritture.
        #
        # Lo spread e' quello REGISTRATO ALL'INGRESSO, non quello di adesso:
        # il buffer di PA-46 deve coprire un costo gia' pagato, che e' un
        # fatto passato. Con lo spread corrente il livello si muoverebbe, e
        # molto durante una news, mentre GEST-05 lo vuole immobile.
        spread = posizione.get("spread_ingresso")
        if spread is None:
            spread = tick["ask"] - tick["bid"]
        prima = gestione.Posizione(
            strumento=simbolo,
            direzione=_bias(direzione),
            prezzo_ingresso=float(posizione["prezzo_ingresso"]),
            tf_crt=TF.H4,          # non entra nel calcolo di GEST-04
            livello_stop=float(posizione["sl"]),
            tp1=float(tp1),
            target_finale=float(posizione.get("tp") or 0.0),
        )
        dopo, frazione = gestione.applica_tp1(prima, float(spread))

        quota = volume_del_parziale(
            volume_iniziale, volume_attuale, float(specifiche["volume_step"]), frazione
        )
        if quota is None:
            # Size minima: un quarto non e' eseguibile. Non si chiude nulla e
            # NON si sposta lo stop — un break even senza parziale incassato e'
            # un'operazione che le regole non descrivono. Si dice una volta e
            # si smette, marcando TP1 come gestito.
            log.info(
                "TP1 su %s (ticket %s): il 25%% di %s non e' eseguibile al passo "
                "%s, la posizione prosegue intera con lo stop iniziale",
                simbolo, ticket, volume_iniziale, specifiche["volume_step"],
            )
            storage.applica_parziale_tp1(
                id_posizione, volume_attuale, float(posizione["sl"])
            )
            notifier.invia(
                f"TP1 raggiunto su {simbolo} (ticket {ticket}) ma il parziale del "
                f"25% non e' eseguibile alla size minima. La posizione resta "
                f"intera con lo stop iniziale."
            )
            return False

        esito = broker.chiudi_posizione(ticket, volume=quota)
        if not esito.ok:
            log.error("parziale su %s fallito: %s", ticket, esito.messaggio)
            notifier.invia(
                f"ATTENZIONE: TP1 toccato su {simbolo} (ticket {ticket}) ma il "
                f"parziale e' fallito: {esito.messaggio}\nRiprovo al prossimo giro."
            )
            return False

        # GEST-03, GEST-05, GEST-14, ESCL-07/08/09: lo stop si muove una volta
        # sola, a break even, e solo dopo TP1. Il controllo gira sulla
        # posizione **dopo** il parziale, che e' quella a cui lo spostamento
        # si applica. In funzionamento normale passa sempre; se un giorno non
        # passasse, vorrebbe dire che `applica_tp1` ha prodotto uno stop che
        # le esclusioni vietano, e allora e' giusto fermarsi.
        nuovo_stop = dopo.livello_stop
        ammesso, perche = gestione.spostamento_stop_ammesso(dopo, nuovo_stop)
        if not ammesso:
            log.error(
                "parziale eseguito su %s ma lo stop NON si puo' spostare: %s",
                ticket, perche,
            )
            notifier.invia(
                f"ATTENZIONE: parziale eseguito su {simbolo} (ticket {ticket}) ma "
                f"lo stop non e' stato portato a pareggio: {perche}"
            )
            nuovo_stop = float(posizione["sl"])

        # E il pareggio non puo' finire OLTRE il prezzo corrente.
        #
        # `livello_break_even` e' `ingresso -/+ due spread`, un livello
        # calcolato sull'ingresso e mai confrontato col prezzo di adesso. Se
        # a TP1 il prezzo si e' mosso meno di due spread, quel livello cade
        # dalla parte gia' superata: e' uno stop gia' toccato.
        #
        # Misurato il 2026-09-22 sul ticket 327995073, AUDUSD SELL: prezzo
        # 0,71113, pareggio calcolato 0,71107, cioe' SOTTO. MT5 ha rifiutato
        # la modifica con `10016`, ma l'archivio se lo scriveva lo stesso, e
        # al giro dopo la sentinella lo trovava toccato e chiudeva il
        # residuo. Nove volte in un'ora e mezza.
        #
        # Lo stop vecchio e' piu' lontano e quindi sempre valido: si tiene
        # quello, e GEST-05 resta soddisfatta perche' lo spostamento a
        # pareggio semplicemente non avviene.
        uscita = prezzo_di_uscita(direzione, tick["bid"], tick["ask"])
        ancora_davanti = (nuovo_stop > uscita if _bias(direzione) is Bias.SHORT
                          else nuovo_stop < uscita)
        if not ancora_davanti:
            log.warning(
                "%s (ticket %s): il pareggio a %s sarebbe gia' oltre il "
                "prezzo %s, lo stop resta a %s",
                simbolo, ticket, nuovo_stop, uscita, posizione["sl"])
            nuovo_stop = float(posizione["sl"])

        residuo = round(volume_attuale - quota, 8)
        storage.applica_parziale_tp1(id_posizione, residuo, nuovo_stop)

        # Lo stop nuovo va anche al BROKER, non solo in archivio. Sono due
        # reti, e quella del broker e' l'unica che sopravvive alla morte del
        # bot: lasciarla allo stop vecchio dopo un parziale vuol dire che, se
        # il processo cade, il residuo e' protetto al livello sbagliato.
        esito_livelli = broker.modifica_livelli(ticket, stop=nuovo_stop)
        if not esito_livelli.ok:
            log.warning("parziale su %s scritto in archivio ma il broker non "
                        "ha accettato lo stop nuovo: %s",
                        ticket, esito_livelli.messaggio)
        log.info(
            "TP1 su %s (ticket %s): chiusi %s a %s, restano %s con stop a %s",
            simbolo, ticket, quota, esito.prezzo, residuo, nuovo_stop,
        )
        notifier.invia(
            f"TP1 su {simbolo} {direzione} (ticket {ticket})\n"
            f"chiuso il 25% ({quota} lotti) a {esito.prezzo}\n"
            f"restano {residuo} lotti, stop a pareggio {nuovo_stop}"
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
