"""La gestione della posizione di `docs/04_gestione.md`.

Copre anche `SETUP-12`, `SETUP-13`, `SETUP-14` e `SETUP-17`, che dicono le
stesse cose di `GEST-02`, `GEST-07`, `GEST-08` e del cambio di bias: sono le
medesime regole scritte in due file, e implementarle due volte significherebbe
farle divergere.

**Lo stop non si muove mai prima di TP1** (GEST-03, ESCL-08), e dopo il break
even non si muove piu' (GEST-05, ESCL-09). Non esiste trailing in alcuna forma.
Sono i due vincoli che questo modulo fa rispettare piu' di ogni altro, perche'
sono quelli che si e' tentati di violare quando una posizione va male.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from core.definizioni import Bias, Candela, Gap, KeyLevel, liv_50
from core.parametri import (
    BUFFER_BE_MOLTIPLICATORE_SPREAD,
    FRAZIONE_CHIUSA_A_TP1,
    FRAZIONE_RESIDUA,
    TF,
    gerarchia,
    richiedi,
)


@dataclass(frozen=True)
class Posizione:
    """Lo stato di una posizione, ricostruibile dopo un riavvio (GEST-12).

    I campi sono esattamente quelli che GEST-12 elenca come stato da
    ricostruire: strumento, direzione, prezzo di ingresso, timeframe del CRT
    di origine, stop corrente, TP1, target finale, e se TP1 sia gia' stato
    raggiunto.
    """

    strumento: str
    direzione: Bias
    prezzo_ingresso: float
    tf_crt: TF
    livello_stop: float
    tp1: float
    target_finale: float
    tp1_raggiunto: bool = False
    frazione_residua: float = 1.0
    ancorata_al_gap: bool = False


# ===========================================================================
# GEST-02, SETUP-12 — stop iniziale
# ===========================================================================


def stop_aggressivo(n2: Candela, direzione: Bias) -> float:
    """GEST-02 e SETUP-12 — Stop ancorato al CRT: l'estremo di N2."""
    if direzione is Bias.SHORT:
        return n2.massimo
    if direzione is Bias.LONG:
        return n2.minimo
    raise ValueError("direzione NESSUNA non ha stop")


def stop_conservativo(gap: Gap, direzione: Bias) -> float:
    """GEST-02 e SETUP-12 — Stop ancorato al gap: il bordo esterno della zona.

    Per una posizione short il bordo esterno e' quello superiore, per una long
    quello inferiore. GEST-06 osserva che questo livello **coincide** con il
    livello di invalidazione del gap: se il gap viene invalidato, lo stop e'
    gia' stato colpito.
    """
    if direzione is Bias.SHORT:
        return gap.zona_sup
    if direzione is Bias.LONG:
        return gap.zona_inf
    raise ValueError("direzione NESSUNA non ha stop")


# ===========================================================================
# GEST-07, SETUP-13 — TP1
# ===========================================================================


def tp1(n1: Candela) -> float:
    """GEST-07 e SETUP-13 — TP1 e' il 50% del range di N1.

    `N1` del timeframe **su cui e' nato il CRT**, non di un altro. La formula
    e' `liv_50` di DEF-36, applicata a `N1` e non a `C1`: sono la stessa
    formula su candele diverse e non vanno confuse.
    """
    return liv_50(n1)


def raggiunge_tp1(posizione: Posizione, prezzo_future: float) -> bool:
    """GEST-04 — SORVEGLIANZA. Il prezzo scambiato del future ha toccato TP1."""
    if posizione.tp1_raggiunto:
        return False
    if posizione.direzione is Bias.SHORT:
        return prezzo_future <= posizione.tp1
    return prezzo_future >= posizione.tp1


def livello_break_even(prezzo_ingresso: float, direzione: Bias, spread: float,
                       costo_in_prezzo: float = 0.0) -> float:
    """GEST-04 — Break even con il buffer che copre spread e commissioni.

    Lo stop a pareggio deve chiudere in pareggio **reale**, non in perdita per
    i costi. Il buffer e' un multiplo dello spread corrente e non un numero
    per strumento: uno spread cambia, un numero in tabella no (PA-46).

    `costo_in_prezzo` e' la commissione gia' pagata al broker, convertita in
    distanza di prezzo per QUESTA posizione: `costi / (valore_punto x lotti)`.
    Il buffer e' il piu' grande dei due, perche' deve soddisfare entrambe le
    condizioni -- stare fuori dal rumore dello spread **e** recuperare il
    costo.

    Perche' non basta il multiplo dello spread: PA-46 aveva scelto due spread
    *come approssimazione della commissione*, e il documento di decisione
    ammette che "il fattore 2 e' mio". Misurato il 2026-09-22, la commissione
    vera e' 4,06 EUR per lotto. Su oro ed EURUSD due spread la coprono e
    avanzano; su `USDJPY`, dove lo spread e' piccolo in proporzione, no -- e
    li' il pareggio chiudeva in perdita, che e' esattamente cio' che questa
    regola esiste per evitare.
    """
    buffer = max(BUFFER_BE_MOLTIPLICATORE_SPREAD * max(spread, 0.0),
                 max(costo_in_prezzo, 0.0))
    if direzione is Bias.LONG:
        return prezzo_ingresso + buffer
    if direzione is Bias.SHORT:
        return prezzo_ingresso - buffer
    raise ValueError("direzione NESSUNA non ha break even")


def applica_tp1(posizione: Posizione, spread: float,
                costo_in_prezzo: float = 0.0) -> tuple[Posizione, float]:
    """GEST-04 e GEST-07 — Chiude il 25% e porta il resto a break even.

    Restituisce (posizione aggiornata, frazione chiusa). Il residuo non ha
    ulteriori parziali: viene chiuso interamente al target finale.

    `costo_in_prezzo` e' la commissione gia' pagata, in distanza di prezzo:
    senza, il pareggio non e' un pareggio. Vedi `livello_break_even`.
    """
    if posizione.tp1_raggiunto:
        return posizione, 0.0
    nuova = replace(
        posizione,
        tp1_raggiunto=True,
        frazione_residua=posizione.frazione_residua * FRAZIONE_RESIDUA,
        livello_stop=livello_break_even(
            posizione.prezzo_ingresso, posizione.direzione, spread, costo_in_prezzo),
    )
    return nuova, posizione.frazione_residua * FRAZIONE_CHIUSA_A_TP1


# ===========================================================================
# GEST-03, GEST-05, GEST-14 — cosa non si fa mai allo stop
# ===========================================================================


def spostamento_stop_ammesso(posizione: Posizione, nuovo_stop: float) -> tuple[bool, str]:
    """GEST-03, GEST-05, GEST-14, ESCL-07, ESCL-08, ESCL-09.

    Lo stop si muove **una volta sola**, a break even, e **solo dopo TP1**.
    Prima di TP1 non si muove per nessun motivo. Dopo il break even non si
    muove piu': nessun trailing, in nessuna forma.

    E non si allarga mai: uno stop piu' lontano dal prezzo aumenta la perdita
    massima di un'operazione gia' dimensionata su quella distanza.
    """
    if not posizione.tp1_raggiunto:
        return False, "GEST-03: lo stop non si sposta prima di TP1"

    if posizione.direzione is Bias.SHORT and nuovo_stop > posizione.livello_stop:
        return False, "ESCL-07: stop allargato"
    if posizione.direzione is Bias.LONG and nuovo_stop < posizione.livello_stop:
        return False, "ESCL-07: stop allargato"

    if nuovo_stop != posizione.livello_stop:
        return False, "GEST-05: dopo il break even lo stop non si sposta piu'"

    return True, "nessuno spostamento richiesto"


def mediazione_ammessa() -> bool:
    """GEST-14 ed ESCL-06 — Nessuna posizione in perdita viene mai incrementata."""
    return False


# ===========================================================================
# GEST-08, SETUP-14 — estensione del target
# ===========================================================================


def estendi_target(
    posizione: Posizione,
    tf_che_conferma: TF,
    key_level_di_quel_tf: KeyLevel,
    crt_formato_su_quel_tf: bool,
) -> Posizione:
    """GEST-08 e SETUP-14 — Estensione progressiva e a senso unico.

    Alla chiusura di ogni candela di un timeframe **superiore** a quello del
    CRT, se quel timeframe conferma il pattern il target si sposta al suo key
    level. "Conferma il pattern" significa che vi si e' formato un CRT nella
    stessa direzione: "pattern" indica la CRT in tutti i documenti (REV-26).

    A senso unico: il target sale nella gerarchia dei timeframe, mai
    all'indietro. Un timeframe inferiore o pari a quello del CRT non estende
    nulla.
    """
    if not crt_formato_su_quel_tf:
        return posizione
    ordine = gerarchia()
    if ordine.index(tf_che_conferma) >= ordine.index(posizione.tf_crt):
        return posizione                                    # non e' superiore
    return replace(posizione, target_finale=key_level_di_quel_tf.valore)


def target_consumato_prima_di_tp1(
    posizione: Posizione,
    nuovo_target: Optional[float],
) -> tuple[Posizione, str]:
    """GEST-09 e PA-48 — Il target sparisce prima che TP1 sia stato raggiunto.

    GEST-09 presuppone che TP1 sia gia' stato raggiunto e la posizione sia
    protetta a break even. Se il target viene consumato **prima**, la
    posizione e' ancora allo stop iniziale e GEST-09 non dice nulla.

    Deciso seguendo il modello di DEF-29, che per un target raggiunto dice di
    rieseguire la ricerca del successivo: si ricalcola il target. Se non ne
    esiste uno, PRIN-99 e si chiude a mercato — una posizione senza bersaglio
    non ha ragione di restare aperta.
    """
    if richiedi("PA-48") != "ricalcola_target":
        raise ValueError(f"PA-48: lettura non riconosciuta: {richiedi('PA-48')!r}")
    if nuovo_target is None:
        return posizione, "PRIN-99: nessun target successivo, chiudere a mercato"
    return replace(posizione, target_finale=nuovo_target), "target ricalcolato (DEF-29)"


# ===========================================================================
# GEST-06 — gap invalidato con posizione aperta
# ===========================================================================


def gap_invalidato_con_posizione_aperta(posizione: Posizione) -> tuple[bool, str]:
    """GEST-06 e PA-47 — Il gap che motivava la posizione viene invalidato.

    Due casi distinti:

    - **stop conservativo**: lo stop e' gia' stato colpito, perche' il livello
      di invalidazione del gap e il bordo esterno della zona coincidono. La
      posizione e' chiusa in perdita, non c'e' nulla da decidere.
    - **stop aggressivo**: la posizione puo' sopravvivere all'invalidazione del
      gap che l'aveva motivata. GEST-06 dice "nessuna azione automatica", e
      resta cosi': portarla a break even prima di TP1 violerebbe GEST-03 ed
      ESCL-08, e chiuderla sarebbe una regola che nessuno ha scritto.

    Restituisce (va chiusa, motivo).
    """
    if richiedi("PA-47") != "nessuna_azione":
        raise ValueError(f"PA-47: lettura non riconosciuta: {richiedi('PA-47')!r}")
    if posizione.ancorata_al_gap:
        return True, "GEST-06: stop conservativo gia' colpito, il livello coincide con l'invalidazione"
    return False, "GEST-06: stop aggressivo, nessuna azione automatica"


# ===========================================================================
# SETUP-17 — cambio di bias su posizione aperta
# ===========================================================================


def cambio_bias_su_posizione_aperta(
    posizione: Posizione,
    nuova_bias_comando: Bias,
    spread: float,
) -> tuple[Posizione, str]:
    """SETUP-17 — La posizione non viene chiusa: viene protetta.

    Se `bias_comando` cambia in direzione opposta a quella della posizione, lo
    stop va a break even. Non si chiude.

    Attenzione al conflitto con GEST-03, che vieta di spostare lo stop prima
    di TP1: qui SETUP-17 impone uno spostamento che protegge, e GEST-03 ne
    vieta uno che rischia. Sono compatibili perche' il break even non allarga
    mai lo stop — ma se TP1 non e' ancora stato raggiunto, la posizione
    passa a break even in anticipo rispetto al percorso ordinario.
    """
    if nuova_bias_comando is posizione.direzione or nuova_bias_comando is Bias.NESSUNA:
        return posizione, "bias invariata o non definita: nessuna azione"
    nuovo_stop = livello_break_even(posizione.prezzo_ingresso, posizione.direzione, spread)
    return (
        replace(posizione, livello_stop=nuovo_stop),
        "SETUP-17: bias_comando invertita, stop portato a break even senza chiudere",
    )


# ===========================================================================
# GEST-10 — chiusura al target di tf_comando
# ===========================================================================


def chiudere_al_target_di_comando(
    posizione: Posizione,
    bias_comando_vecchia: Bias,
    target_di_comando_raggiunto: bool,
) -> bool:
    """GEST-10 e SETUP-08 — Al target di tf_comando si chiude tutto.

    *"Il target di tf_comando era il bersaglio dichiarato dell'operativita':
    una volta raggiunto, le posizioni che lo inseguivano non hanno piu' ragione
    di esistere."* Si chiudono a mercato quelle nella direzione della vecchia
    bias, non le altre.
    """
    return target_di_comando_raggiunto and posizione.direzione is bias_comando_vecchia


# ===========================================================================
# GEST-11, GEST-13 — esecuzione e indipendenza
# ===========================================================================


def chiusura_ha_soglia_di_tolleranza() -> bool:
    """GEST-11 — Nessuna deviazione massima oltre cui rinunciare a chiudere.

    Se il prezzo del future raggiunge stop o target, si chiude a mercato sul
    CFD senza soglia sul prezzo ottenuto. Il future e' l'unico riferimento
    (RISK-12).
    """
    return False


def posizioni_si_gestiscono_a_blocco() -> bool:
    """GEST-13 — No. Ogni posizione ha il proprio TP1, break even e target.

    Le posizioni sullo stesso strumento non si gestiscono come blocco unico:
    lo stop di una non influenza le altre. Ognuna e' calcolata sul timeframe
    del CRT che l'ha generata.
    """
    return False
