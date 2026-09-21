"""CRT-13 — l'ingresso di Romeo, sul timeframe basso, in produzione.

## Il cambio di architettura, e perche' era inevitabile

Fino a qui il motore faceva una cosa sola: alla chiusura della candela di
range trovava il CRT e mandava l'ordine. Un colpo solo.

Romeo non fa cosi', e la differenza vale +0,44 R per operazione:

    mio ingresso      chiusura di N2      winrate 30,8%   -0,0782 R
    ingresso ROMEO    ritorno nell'FVG    winrate 62,4%   +0,3613 R

La sua sequenza ha due momenti separati nel tempo:

    1. chiude la candela di RANGE, il CRT c'e'      <- si ARMA
    2. sul timeframe basso: CISD, FVG, ritorno      <- si ENTRA

Fra i due passano minuti o ore. Un motore che decide tutto in un istante non
puo' esprimerlo: serve uno stato che sopravvive fra una candela e l'altra, ed
e' quello che questo modulo tiene.

## Lo stato vive in archivio, non in memoria

Un setup armato che sparisse al riavvio sarebbe peggio di non averlo: il bot
dimenticherebbe di essere in attesa proprio mentre il prezzo torna nel vuoto.
E' lo stesso principio di `GEST-12` per le posizioni aperte.

## La scadenza

Un setup armato non aspetta per sempre. `SETUP-04` fa decadere un CRT non
eseguito all'apertura di `N3`: qui la traduzione e' che l'attesa dura al
massimo quanto la candela di range che l'ha generata. Oltre, il contesto che
lo motivava non c'e' piu'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from core import notifier, storage
from core.definizioni import Bias, Candela, cisd
from core.log import diario
from core.contesto import RR_MINIMO
from core.parametri import TF

log = diario("ingresso_ltf")

# Quanto dura l'attesa, in candele del timeframe di ingresso. Su `4h -> 15m`
# sedici quarti d'ora sono quattro ore: la durata della candela di range.
ATTESA_MASSIMA_BARRE = 16

# Quante barre indietro guarda il CISD. Otto e' la finestra su cui la misura
# e' stata fatta; piu' corta perde i cambi di consegna lenti, piu' lunga
# comincia a trovare serie che non hanno a che fare con questo sweep.
FINESTRA_CISD = 8


@dataclass(frozen=True)
class SetupArmato:
    """Un CRT che ha spazzato e ora aspetta il suo ingresso sul TF basso."""

    id_setup: int
    strumento: str
    direzione: Bias
    tf_crt: str
    tf_ingresso: str
    estremo_sweep: float      # dove va lo stop
    eq_range: float           # il primo bersaglio (CRT-16)
    lato_opposto: float       # il secondo
    livello_cisd: Optional[float]
    fvg_inf: Optional[float]
    fvg_sup: Optional[float]
    barre_attesa: int
    armato_utc: str


def _prezzo(strumento: str, valore: float) -> str:
    """Un prezzo scritto come lo scrive il broker per quello strumento.

    Cinque decimali per tutti scriveva l'oro come `4352,94000` e lo yen come
    `157,24750`: cifre che non esistono sul book, e che fanno sembrare
    sbagliato un numero giusto. Le cifre si ricavano dall'ordine di grandezza
    invece che da una tabella, cosi' non c'e' un elenco da tenere allineato a
    `PRIN-08` ogni volta che cambia.
    """
    grandezza = abs(valore)
    if grandezza >= 1000:                      # oro
        cifre = 2
    elif grandezza >= 10:                      # yen
        cifre = 3
    else:                                      # i cambi
        cifre = 5
    return f"{valore:,.{cifre}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _nome_tf(tf: TF) -> str:
    """`TF_M15` non dice niente a chi legge dal telefono.

    L'elenco e' quello del riepilogo: due elenchi finiscono per divergere, e
    lo stesso timeframe chiamato in due modi nei due messaggi che arrivano
    sullo stesso telefono e' peggio di una sigla.
    """
    from core.riepilogo import NOMI_TF

    return NOMI_TF.get(tf.value, tf.value)


def prepara_tabella() -> None:
    with storage.connessione(scrittura=True) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS setup_armato (
                id_setup      INTEGER PRIMARY KEY AUTOINCREMENT,
                strumento     TEXT    NOT NULL,
                direzione     TEXT    NOT NULL,
                tf_crt        TEXT    NOT NULL,
                tf_ingresso   TEXT    NOT NULL,
                estremo_sweep REAL    NOT NULL,
                eq_range      REAL    NOT NULL,
                lato_opposto  REAL    NOT NULL,
                livello_cisd  REAL,
                fvg_inf       REAL,
                fvg_sup       REAL,
                barre_attesa  INTEGER NOT NULL DEFAULT 0,
                armato_utc    TEXT    NOT NULL,
                stato         TEXT    NOT NULL DEFAULT 'armato',
                chiuso_utc    TEXT,
                motivo        TEXT
            )
        """)


def arma(
    strumento: str, direzione: Bias, tf_crt: TF, tf_ingresso: TF,
    estremo_sweep: float, eq_range: float, lato_opposto: float,
) -> int:
    """Il CRT c'e': si aspetta l'ingresso. Non parte alcun ordine."""
    prepara_tabella()
    with storage.connessione(scrittura=True) as conn:
        # Lo stesso CRT, non uno nuovo.
        #
        # Un CRT vive finche' vive la sua candela di range, e il motore lo
        # ritrova identico ad ogni valutazione: stesso strumento, stessa
        # direzione, stesso timeframe, stesso estremo spazzato. Qui sotto
        # ogni passaggio marcava il precedente come "sostituito" e ne
        # inseriva uno nuovo -- e ogni inserimento mandava un messaggio.
        # Su Telegram arrivava una fila di avvisi identici per un solo CRT,
        # che e' il modo piu' rapido di far smettere di leggerli.
        #
        # `barre_attesa` sta sulla riga, quindi ri-armare azzerava anche il
        # conto delle barre di SETUP-04: un setup che avrebbe dovuto decadere
        # restava armato per sempre.
        gia = conn.execute(
            "SELECT id_setup FROM setup_armato WHERE stato='armato'"
            " AND strumento=? AND direzione=? AND tf_crt=? AND tf_ingresso=?"
            " AND estremo_sweep=? AND eq_range=?",
            (strumento, direzione.value, tf_crt.value, tf_ingresso.value,
             estremo_sweep, eq_range),
        ).fetchone()
        if gia is not None:
            return int(gia["id_setup"])

        # Un solo setup armato per strumento e direzione: due CRT consecutivi
        # nello stesso verso descrivono lo stesso movimento, e armarli
        # entrambi produrrebbe due ingressi sullo stesso setup.
        # Il motivo va passato come PARAMETRO, non interpolato: l'apostrofo
        # di "piu'" chiude la stringa SQL. E' anche il motivo per cui nessun
        # valore in questo file finisce dentro una query per concatenazione.
        conn.execute(
            "UPDATE setup_armato SET stato='sostituito', chiuso_utc=?, motivo=? "
            "WHERE stato='armato' AND strumento=? AND direzione=?",
            (_adesso(), "un CRT piu' recente nella stessa direzione",
             strumento, direzione.value),
        )
        cur = conn.execute(
            "INSERT INTO setup_armato (strumento, direzione, tf_crt, tf_ingresso,"
            " estremo_sweep, eq_range, lato_opposto, armato_utc)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (strumento, direzione.value, tf_crt.value, tf_ingresso.value,
             estremo_sweep, eq_range, lato_opposto, _adesso()),
        )
    log.info("armato %s %s su %s, attende l'ingresso su %s",
             strumento, direzione.value, tf_crt.value, tf_ingresso.value)
    # Il momento in cui c'e' davvero una possibilita' concreta: un CRT trovato
    # e non ancora scartato da nessuna regola. Fino a qui Telegram taceva
    # sempre - avvisava solo su un ordine mandato o bloccato - e un'attesa di
    # ore o minuti (l'ingresso vero arriva su un timeframe diverso) passava
    # inosservata a chi non tiene aperto il pannello.
    verso = "rialzista" if direzione is Bias.LONG else "ribassista"
    notifier.invia_appena_possibile(
        f"{strumento}: setup {verso} armato su {_nome_tf(tf_crt)}.\n"
        f"Spazzato {_prezzo(strumento, estremo_sweep)}, "
        f"primo bersaglio {_prezzo(strumento, eq_range)}.\n"
        f"Ora aspetta il rientro nello squilibrio su {_nome_tf(tf_ingresso)}: "
        f"finche' non arriva non parte nessun ordine."
    )
    return int(cur.lastrowid or 0)


def armati(strumento: Optional[str] = None) -> list[SetupArmato]:
    prepara_tabella()
    with storage.connessione() as conn:
        if strumento:
            righe = conn.execute(
                "SELECT * FROM setup_armato WHERE stato='armato' AND strumento=?"
                " ORDER BY id_setup", (strumento,)).fetchall()
        else:
            righe = conn.execute(
                "SELECT * FROM setup_armato WHERE stato='armato' ORDER BY id_setup"
            ).fetchall()
    return [SetupArmato(
        int(r["id_setup"]), str(r["strumento"]), Bias(str(r["direzione"])),
        str(r["tf_crt"]), str(r["tf_ingresso"]), float(r["estremo_sweep"]),
        float(r["eq_range"]), float(r["lato_opposto"]),
        r["livello_cisd"], r["fvg_inf"], r["fvg_sup"],
        int(r["barre_attesa"]), str(r["armato_utc"]),
    ) for r in righe]


def _adesso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chiudi(id_setup: int, stato: str, motivo: str) -> None:
    prepara_tabella()
    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "UPDATE setup_armato SET stato=?, chiuso_utc=?, motivo=?"
            " WHERE id_setup=? AND stato='armato'",
            (stato, _adesso(), motivo[:300], id_setup))


# ===========================================================================
# Il controllo a ogni chiusura del timeframe di ingresso
# ===========================================================================


@dataclass(frozen=True)
class Ingresso:
    """L'ingresso trovato: prezzo, stop, bersagli. Pronto per il motore."""

    id_setup: int
    strumento: str
    direzione: Bias
    prezzo: float
    stop: float
    bersaglio_1: float        # EQ del range (CRT-16, GEST-07)
    bersaglio_2: float        # il lato opposto
    tf_crt: str


def fvg(barre: Sequence[Candela], direzione: Bias) -> Optional[tuple[float, float]]:
    """DEF-10/DEF-11 — il vuoto lasciato dal movimento di conferma.

    Tre barre dove la prima e la terza **non si toccano**. Si restituisce
    l'ultimo trovato, non il primo: e' quello piu' vicino al prezzo, quindi
    quello che il ritorno incontrera' per primo.
    """
    trovato = None
    for i in range(len(barre) - 2):
        a, c = barre[i], barre[i + 2]
        if direzione is Bias.LONG and c.minimo > a.massimo:
            trovato = (a.massimo, c.minimo)
        elif direzione is Bias.SHORT and c.massimo < a.minimo:
            trovato = (c.massimo, a.minimo)
    return trovato


def controlla(
    setup: SetupArmato, basse: Sequence[Candela]
) -> tuple[Optional[Ingresso], str]:
    """Su questa chiusura del TF basso: si entra, si aspetta, o si lascia?

    Restituisce `(ingresso oppure None, motivo)`. Il motivo finisce in
    archivio: un setup che decade deve dire perche', altrimenti fra un mese
    nessuno sa se il bot stesse funzionando o tacendo.

    I tre passi di CRT-13, nell'ordine, e ognuno deve essere avvenuto perche'
    il successivo conti:

        1. **CISD** — una barra CHIUDE oltre l'apertura della prima candela
           dell'ultima serie di consegna contraria. Il livello si calcola
           sulle barre PRECEDENTI: includere la barra che rompe svuota la
           serie e rende la regola inerte (misurato: 16 CISD su 3622).
        2. **FVG** — il movimento che ha prodotto il CISD lascia un vuoto.
        3. **ritorno** — il prezzo rientra nel vuoto. Li' si entra.
    """
    if not basse:
        return None, "nessuna candela sul timeframe di ingresso"
    if setup.barre_attesa >= ATTESA_MASSIMA_BARRE:
        return None, (f"SETUP-04: {ATTESA_MASSIMA_BARRE} barre senza ingresso, "
                      "il contesto che lo motivava non c'e' piu'")

    direzione = setup.direzione

    # --- 1. il CISD --------------------------------------------------------
    livello = setup.livello_cisd
    if livello is None:
        precedenti = basse[-(FINESTRA_CISD + 1):-1]
        candidato = cisd(precedenti, direzione)
        if candidato is None:
            return None, "nessuna serie di consegna contraria da rompere"
        ultima = basse[-1]
        rotto = (ultima.chiusura > candidato if direzione is Bias.LONG
                 else ultima.chiusura < candidato)
        if not rotto:
            return None, f"CISD a {candidato:.5f} non ancora rotto"
        livello = candidato
        _annota(setup.id_setup, livello_cisd=livello)

    # --- 2. il vuoto -------------------------------------------------------
    inf, sup = setup.fvg_inf, setup.fvg_sup
    if inf is None or sup is None:
        vuoto = fvg(basse[-5:], direzione)
        if vuoto is None:
            return None, "CISD avvenuto ma nessun FVG da ritestare"
        inf, sup = vuoto
        if sup <= inf:
            return None, "FVG degenere"
        _annota(setup.id_setup, fvg_inf=inf, fvg_sup=sup)
        return None, f"FVG trovato fra {inf:.5f} e {sup:.5f}, attendo il ritorno"

    # --- 3. il ritorno -----------------------------------------------------
    ultima = basse[-1]
    if not (ultima.minimo <= sup and ultima.massimo >= inf):
        return None, f"il prezzo non e' ancora tornato fra {inf:.5f} e {sup:.5f}"

    # Si entra al bordo del vuoto piu' vicino al prezzo: e' il primo che il
    # ritorno tocca, non il centro.
    prezzo = sup if direzione is Bias.LONG else inf
    rischio = abs(prezzo - setup.estremo_sweep)
    if rischio <= 0:
        return None, "PRIN-99: ingresso coincidente con lo stop"

    # CRT-16: prima l'EQ del range, poi il lato opposto. Se l'EQ e' gia' stato
    # superato il primo bersaglio diventa il lato opposto.
    primo = setup.eq_range
    oltre = (primo <= prezzo if direzione is Bias.LONG else primo >= prezzo)
    if oltre:
        primo = setup.lato_opposto
    ancora_oltre = (primo <= prezzo if direzione is Bias.LONG else primo >= prezzo)
    if ancora_oltre:
        return None, "PRIN-99: nessun bersaglio davanti al prezzo di ingresso"

    # --- GEST-01, qui e non all'armamento ---------------------------------
    #
    # Il rapporto rischio/rendimento va misurato sul prezzo a cui l'ordine
    # parte davvero. Con l'ingresso a due tempi quel prezzo e' QUESTO -- il
    # bordo dell'FVG appena ritestato -- non la chiusura di `N2`, che e' dove
    # il motore lo calcolava finora perche' era l'unico prezzo che aveva.
    #
    # La differenza non e' una sfumatura: fra la chiusura di `N2` e il ritorno
    # nel vuoto il prezzo torna INDIETRO verso lo sweep, quindi si avvicina
    # allo stop e si allontana dal bersaglio. Il rapporto vero e' molto
    # migliore di quello stimato all'armamento.
    #
    # Misurato il 2026-09-21 su `D1 -> H1`, sei strumenti: all'armamento il
    # rapporto risultava **incalcolabile nel 68% dei casi** -- il prezzo aveva
    # gia' passato la meta' del range e il bersaglio restava indietro -- e
    # GEST-01 fermava 292 CRT su 298. Non per la soglia: perche' il numero non
    # esisteva. Era il filtro giusto applicato al prezzo sbagliato.
    rapporto = abs(primo - prezzo) / rischio
    if rapporto < RR_MINIMO:
        return None, (f"GEST-01: rapporto {rapporto:.2f} sotto {RR_MINIMO} "
                      f"sul prezzo d'ingresso {prezzo:.5f}")

    return Ingresso(
        setup.id_setup, setup.strumento, direzione, prezzo,
        setup.estremo_sweep, primo, setup.lato_opposto, setup.tf_crt,
    ), (f"CRT-13: ingresso a {prezzo:.5f} sul ritorno nell'FVG, "
        f"rapporto {rapporto:.2f}")


def _annota(id_setup: int, **campi) -> None:
    """Salva i passi gia' compiuti, cosi' il riavvio non li perde."""
    if not campi:
        return
    prepara_tabella()
    pezzi = ", ".join(f"{k}=?" for k in campi)
    with storage.connessione(scrittura=True) as conn:
        conn.execute(f"UPDATE setup_armato SET {pezzi} WHERE id_setup=?",
                     (*campi.values(), id_setup))


def avanza_attesa(id_setup: int) -> None:
    """Una barra in piu' senza ingresso."""
    prepara_tabella()
    with storage.connessione(scrittura=True) as conn:
        conn.execute(
            "UPDATE setup_armato SET barre_attesa = barre_attesa + 1"
            " WHERE id_setup=? AND stato='armato'", (id_setup,))


def valuta_armati(
    strumento: str, tf_ingresso: TF, basse: Sequence[Candela]
) -> list[Ingresso]:
    """Alla chiusura di una candela del TF basso: quali setup fanno scattare.

    E' il secondo dei due momenti di CRT-13. Il primo — il CRT sulla candela
    di range — e' gia' avvenuto e ha lasciato un setup armato in archivio.

    Ogni setup che non entra avanza di una barra; oltre `ATTESA_MASSIMA_BARRE`
    decade (SETUP-04). Un setup che entra viene chiuso come `eseguito`: non
    puo' produrre due ordini.
    """
    fuori: list[Ingresso] = []
    for setup in armati(strumento):
        if setup.tf_ingresso != tf_ingresso.value:
            continue
        ingresso, motivo = controlla(setup, basse)
        if ingresso is not None:
            chiudi(setup.id_setup, "eseguito", motivo)
            fuori.append(ingresso)
            continue
        avanza_attesa(setup.id_setup)
        if setup.barre_attesa + 1 >= ATTESA_MASSIMA_BARRE:
            chiudi(setup.id_setup, "decaduto", motivo)
            log.info("setup %s decaduto: %s", setup.id_setup, motivo)
            notifier.invia_appena_possibile(
                f"CRT-13 decaduto: {setup.strumento} {setup.direzione.value} "
                f"su {setup.tf_crt} senza ingresso entro {ATTESA_MASSIMA_BARRE} "
                f"barre su {setup.tf_ingresso}. {motivo}"
            )
    return fuori
