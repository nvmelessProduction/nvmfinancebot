"""GEST-08, GEST-10, SETUP-17 — cosa succede alle posizioni gia' aperte.

La sentinella guarda i prezzi ogni pochi secondi e sa fare una cosa sola:
confrontare il prezzo con i livelli scritti in archivio. Tre regole pero' non
parlano di prezzi, parlano di **candele chiuse**:

- `GEST-08` estende il target alla chiusura di ogni candela di un timeframe
  superiore a quello del CRT, se quel timeframe conferma il pattern;
- `SETUP-17` porta lo stop a break even quando `bias_comando` si inverte;
- `GEST-10` chiude tutto quando il target di `tf_comando` viene raggiunto.

Il loro momento e' la chiusura di candela, cioe' l'alert: e' qui che si
applicano. Fino a REV-55 nessuna delle tre veniva mai chiamata, e una
posizione viveva con il target che aveva al momento dell'ingresso finche' non
moriva allo stop.

## Cosa fa questo modulo, e cosa no

Decide e basta. Non tocca il broker, non scrive in archivio: restituisce un
elenco di `AzioneGestione` che `main` applica. E' la stessa separazione di
`motore.valuta`, e per la stessa ragione: le regole si collaudano senza un
broker acceso.

## Le direzioni, ancora

`bias_comando` e i CRT vivono sul **future**. Le posizioni in archivio vivono
sul **CFD**: `direzione` e' l'azione mandata al broker, BUY o SELL. Su `6J` e
`6S` i due hanno segno opposto (DEF-33). Ogni confronto fra le due passa
percio' per `direzione_cfd`, come in SETUP-19.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from core import gestione as gest
from core import setup as stp
from core.definizioni import (
    Bias, KeyLevel, TipoKeyLevel, direzione_di_esecuzione, livello_di_esecuzione,
)
from core.config import impostazioni
from core.log import diario
from core.motore import Fotografia
from core.parametri import TF
from core.simboli import cfd_da_simbolo_esecuzione
from core.stato import candele_visibili

log = diario("rivalutazione")


@dataclass(frozen=True)
class AzioneGestione:
    """Una cosa da fare a una posizione aperta, e la regola che la impone."""

    id_posizione: int
    ticket: Optional[int]
    tipo: str                 # "chiudi" | "break_even" | "estendi_target"
    valore: Optional[float]   # il nuovo livello, dove serve
    regola: str
    motivo: str


def _bias_della_posizione(direzione: str) -> Bias:
    """Da "BUY"/"SELL" in archivio alla Bias **sul CFD**."""
    return Bias.LONG if direzione.upper() == "BUY" else Bias.SHORT


def _key_level_del_tf(
    key_level: Sequence[KeyLevel], tf: TF, verso_future: Bias
) -> Optional[KeyLevel]:
    """Il key level di **quel** timeframe nel verso dell'operazione.

    GEST-08 dice "key level di quel timeframe", non "del piu' alto
    disponibile": e' un'altra regola da SETUP-14 e non va confusa con essa.
    """
    cercato = TipoKeyLevel.MIN if verso_future is Bias.SHORT else TipoKeyLevel.MAX
    for livello in key_level:
        if livello.tf is tf and livello.tipo is cercato:
            return livello
    return None


def _bersaglio_ancora_disponibile(
    riga: Mapping[str, Any], foto: Fotografia, verso: Bias
) -> bool:
    """Il target della posizione esiste ancora fra i key level correnti?

    Il confronto e' per **verso e distanza**, non per uguaglianza numerica: il
    target in archivio e' un prezzo CFD, i key level della fotografia sono
    prezzi del future, e le due scale non coincidono. Se esiste ancora almeno
    un key level oltre il prezzo nel verso dell'operazione, il bersaglio c'e';
    se non ne esiste piu' nessuno, e' stato consumato (DEF-27, ESCL-17).

    E' una lettura prudente: dice "consumato" solo quando NESSUN livello e'
    rimasto davanti, che e' il caso in cui GEST-09 ha davvero qualcosa da
    dire.
    """
    cercato = TipoKeyLevel.MIN if verso is Bias.SHORT else TipoKeyLevel.MAX
    return any(livello.tipo is cercato for livello in foto.key_level_correnti)


def _piu_lontano(direzione_cfd_posizione: Bias, nuovo: float, attuale: float) -> bool:
    """GEST-08 e' a senso unico: il target si allontana, non si avvicina."""
    if direzione_cfd_posizione is Bias.LONG:
        return nuovo > attuale
    return nuovo < attuale


def rivaluta(
    foto: Fotografia,
    tf_trigger: TF,
    posizioni: Sequence[Mapping[str, Any]],
) -> tuple[AzioneGestione, ...]:
    """Cosa fare alle posizioni aperte su questo strumento, a questa chiusura.

    `posizioni` sono le righe di `storage.posizioni_aperte()`. Vengono
    considerate solo quelle sullo strumento della fotografia: GEST-13 dice che
    ogni posizione si gestisce per conto proprio, e una posizione su `XAUUSD`
    non ha nulla a che vedere con la chiusura di una candela di `EURUSD`.

    L'ordine dei controlli e' quello della gravita': prima chi chiude, poi chi
    protegge, poi chi allunga. Una posizione che GEST-10 chiude non ha bisogno
    di un target esteso.
    """
    azioni: list[AzioneGestione] = []

    # In archivio il simbolo e' quello di ESECUZIONE, col suffisso del broker
    # (`EURUSD.a`). Confrontarlo col nome nudo dello strumento e' lo stesso
    # errore che rendeva inerti RISK-02 e RISK-06.
    suffisso = impostazioni().MT5_SUFFISSO_SIMBOLI
    mie = [
        p for p in posizioni
        if cfd_da_simbolo_esecuzione(str(p.get("simbolo", "")), suffisso) == foto.strumento
        and str(p.get("stato", "aperta")) == "aperta"
    ]
    if not mie:
        return ()

    comando, _tf_comando = stp.bias_comando(foto.bias_per_tf, foto.target_raggiunto_per_tf)

    # GEST-10 parla della **vecchia** bias_comando, e la distinzione non e'
    # sfumata: `bias_comando` SCARTA il timeframe il cui target e' gia' stato
    # raggiunto (SETUP-06, `core/setup.py:239`) e scende a quello sotto.
    # Quindi `tf_comando` non e' mai il timeframe il cui target si e' appena
    # raggiunto, e leggere `target_raggiunto_per_tf[tf_comando]` da' sempre
    # False: GEST-10 non scatterebbe mai.
    #
    # La vecchia bias e' quella che si otterrebbe **ignorando** i target
    # raggiunti: e' il timeframe che comandava fino a un momento fa, ed e'
    # esattamente quello di cui GEST-10 dice che il bersaglio e' stato colpito.
    comando_vecchio, tf_vecchio = stp.bias_comando(foto.bias_per_tf, {})

    # Il CRT su questo timeframe, che serve a GEST-08. Puo' non esserci: la
    # maggior parte delle chiusure di candela non forma un CRT.
    candele = candele_visibili(foto.candele_per_tf.get(tf_trigger, ()), foto.istante)
    crt = (
        stp.cerca_crt(candele[-2], candele[-1], tf_trigger, foto.key_level_presi)
        if len(candele) >= 2 else None
    )

    for riga in mie:
        id_posizione = int(riga["id"])
        ticket = riga.get("ticket")
        verso = _bias_della_posizione(str(riga["direzione"]))

        # --- GEST-10 — il target di tf_comando e' stato raggiunto ---------
        #
        # `target_raggiunto_per_tf` non viene popolato in produzione: il
        # target direzionale di DEF-46 non e' calcolato da nessuno (difetto
        # noto, vedi docs/AUDIT-2026-09-16.md). Quindi questo ramo oggi non
        # scatta mai. E' scritto lo stesso, e collaudato: il giorno in cui
        # quel dato arrivera', GEST-10 sara' gia' al suo posto invece di
        # essere l'ennesima regola implementata e mai chiamata.
        raggiunto = (
            bool(foto.target_raggiunto_per_tf.get(tf_vecchio)) if tf_vecchio else False
        )
        if raggiunto and comando_vecchio is not Bias.NESSUNA:
            # Si chiudono solo quelle nella direzione della vecchia bias: le
            # altre non stavano inseguendo quel target.
            magra = gest.Posizione(
                strumento=foto.strumento, direzione=verso,
                prezzo_ingresso=float(riga.get("prezzo_ingresso") or 0.0),
                tf_crt=tf_trigger, livello_stop=0.0, tp1=0.0, target_finale=0.0,
            )
            if gest.chiudere_al_target_di_comando(
                magra,
                direzione_di_esecuzione(
                    comando_vecchio, foto.strumento, foto.analisi_in_scala_cfd),
                True,
            ):
                azioni.append(AzioneGestione(
                    id_posizione, ticket, "chiudi", None, "GEST-10",
                    f"target di {tf_vecchio.value} raggiunto: la posizione non "
                    "ha piu' il bersaglio che inseguiva",
                ))
                continue

        # --- SETUP-17 — bias_comando invertita ----------------------------
        #
        # Non si chiude: si protegge. E il break even si applica una volta
        # sola, come quello di GEST-04: `tp1_raggiunto` e' il flag che segna
        # "lo stop e' gia' stato spostato" e GEST-05 vieta di rifarlo.
        if comando is not Bias.NESSUNA and not riga.get("tp1_raggiunto"):
            comando_cfd = direzione_di_esecuzione(
                comando, foto.strumento, foto.analisi_in_scala_cfd)
            prezzo_ingresso = riga.get("prezzo_ingresso")
            if comando_cfd is not verso and prezzo_ingresso:
                # SETUP-17 in persona, con la sua nota sul conflitto con
                # GEST-03: il break even non allarga mai lo stop, e i due sono
                # compatibili. La regola vive li', non qui.
                prima = gest.Posizione(
                    strumento=foto.strumento, direzione=verso,
                    prezzo_ingresso=float(prezzo_ingresso),
                    tf_crt=tf_trigger,
                    livello_stop=float(riga.get("sl") or 0.0),
                    tp1=float(riga.get("tp1") or 0.0),
                    target_finale=float(riga.get("tp") or 0.0),
                )
                dopo, perche = gest.cambio_bias_su_posizione_aperta(
                    prima, comando_cfd,
                    float(riga.get("spread_ingresso") or foto.spread),
                )
                if dopo.livello_stop != prima.livello_stop:
                    azioni.append(AzioneGestione(
                        id_posizione, ticket, "break_even", dopo.livello_stop,
                        "SETUP-17", perche,
                    ))
                    continue

        # --- GEST-08 — estensione del target ------------------------------
        if crt is None or riga.get("tf_crt") is None or riga.get("tp") is None:
            continue
        try:
            tf_origine = TF(str(riga["tf_crt"]))
        except ValueError:
            log.warning("posizione %s con tf_crt illeggibile: %r", id_posizione, riga["tf_crt"])
            continue

        # --- GEST-09 e PA-48 — il target e' stato consumato ----------------
        #
        # Un key level CONSUMATO non torna disponibile (ESCL-17). Se il
        # bersaglio della posizione non compare piu' fra i key level correnti
        # nel suo verso, quel bersaglio non c'e' piu': PA-48 dice di
        # ricalcolarlo, e se non ne esiste uno successivo PRIN-99 dice di
        # chiudere, perche' una posizione senza bersaglio non ha ragione di
        # restare aperta.
        if not _bersaglio_ancora_disponibile(riga, foto, verso):
            base_g9 = gest.Posizione(
                strumento=foto.strumento, direzione=verso,
                prezzo_ingresso=float(riga.get("prezzo_ingresso") or 0.0),
                tf_crt=TF(str(riga["tf_crt"])),
                livello_stop=float(riga.get("sl") or 0.0),
                tp1=float(riga.get("tp1") or 0.0),
                target_finale=float(riga["tp"]),
            )
            successivo = _key_level_del_tf(
                foto.key_level_correnti, tf_trigger, crt.direzione
            )
            nuovo_g9 = None
            if successivo is not None:
                try:
                    nuovo_g9 = livello_di_esecuzione(
                        successivo.valore, candele[-1].chiusura,
                        foto.prezzo_cfd, foto.strumento,
                        foto.analisi_in_scala_cfd,
                    )
                except ValueError:
                    nuovo_g9 = None
            _, perche_g9 = gest.target_consumato_prima_di_tp1(base_g9, nuovo_g9)
            if nuovo_g9 is None:
                azioni.append(AzioneGestione(
                    id_posizione, ticket, "chiudi", None, "GEST-09", perche_g9,
                ))
            else:
                azioni.append(AzioneGestione(
                    id_posizione, ticket, "estendi_target", nuovo_g9,
                    "GEST-09", perche_g9,
                ))
            continue

        livello = _key_level_del_tf(foto.key_level_correnti, tf_trigger, crt.direzione)
        if livello is None:
            continue


        base = gest.Posizione(
            strumento=foto.strumento,
            direzione=crt.direzione,
            prezzo_ingresso=float(riga.get("prezzo_ingresso") or 0.0),
            tf_crt=tf_origine,
            livello_stop=float(riga.get("sl") or 0.0),
            tp1=float(riga.get("tp1") or 0.0),
            target_finale=float(riga["tp"]),
        )
        # "Conferma il pattern" = un CRT nella stessa direzione dell'operazione
        # (REV-26). La direzione dell'operazione e' quella sul CFD, quella del
        # CRT e' sul future: si confrontano dopo DEF-33.
        conferma = direzione_di_esecuzione(
            crt.direzione, foto.strumento, foto.analisi_in_scala_cfd) is verso
        esteso = gest.estendi_target(base, tf_trigger, livello, conferma)
        if esteso.target_finale == base.target_finale:
            continue

        # Il key level e' un livello del FUTURE, il target in archivio e' un
        # livello del CFD: la stessa conversione dell'ingresso (REV-52).
        try:
            nuovo = livello_di_esecuzione(
                esteso.target_finale, candele[-1].chiusura, foto.prezzo_cfd,
                foto.strumento, foto.analisi_in_scala_cfd,
            )
        except ValueError as errore:
            log.warning("target non convertibile per %s: %s", id_posizione, errore)
            continue

        if not _piu_lontano(verso, nuovo, base.target_finale):
            # GEST-08 e' a senso unico. Il controllo sulla gerarchia dei
            # timeframe lo fa gia' `estendi_target`; questo tiene conto del
            # fatto che un key level piu' alto nella gerarchia non e'
            # necessariamente piu' lontano nel prezzo.
            continue

        azioni.append(AzioneGestione(
            id_posizione, ticket, "estendi_target", nuovo, "GEST-08",
            f"{tf_trigger.value} conferma il pattern: target esteso al suo key level",
        ))

    return tuple(azioni)
