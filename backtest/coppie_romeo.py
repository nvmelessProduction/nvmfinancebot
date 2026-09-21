"""Le coppie di CRT-04 misurate con l'ingresso di Romeo, sui dati veri.

## Perche' serviva riscriverla

`esegui.py` registra i segnali cosi':

    decisione = motore.valuta(foto, tf)
    if decisione.azione == "NONE":
        continue

Con `INGRESSO_ROMEO` attivo il motore, davanti a un CRT valido, **arma** e
restituisce NONE: l'ordine arrivera' piu' tardi, alla chiusura di una candela
del timeframe basso, se e quando il prezzo rientra nel vuoto. Quindi quella
riga scarta esattamente le operazioni che vogliamo misurare, e una scansione
fatta oggi con quell'impalcatura darebbe zero segnali su qualunque coppia.

Non e' un difetto di chi l'ha scritta: misurava l'ingresso alla chiusura di
N2, che era la strategia di allora. La differenza fra i due ingressi e' la
cosa piu' grossa che il progetto abbia misurato -- da -0,0782 a +0,3613 R --
quindi una misura fatta sull'ingresso vecchio non dice niente su quello nuovo.

E i suoi trigger sono `H1`, `H4`, `D1`: tre delle sei coppie di CRT-04
innescano su `M15`, `M5` e `M1min` e non venivano guardate affatto.

## Cosa fa questa

Per ogni coppia `range -> ingresso` di `COPPIE_CRT`, ad ogni chiusura del
timeframe di range:

1. chiede al motore cosa farebbe, con la Fotografia costruita sui soli dati
   visibili a quell'istante (`candele_visibili` fa il resto);
2. se il motore ARMA, ripercorre le candele del timeframe di ingresso e
   chiede a `ingresso_ltf.controlla` -- la stessa funzione che gira dal vivo
   -- se e quando si entra;
3. se si entra, segue il prezzo fino allo stop o al bersaglio e conta l'R.

Nessuna regola viene riscritta qui: il motore e l'ingresso sono quelli veri,
presi per riferimento. L'unica liberta' e' sul calcolo.

## I dati

Si legge sotto i nomi **CFD** e non sotto quelli dei future, perche' e' li'
che stanno i vent'anni: le serie `6E`/`GC` in archivio coprono 2,4 anni su
`H1` e `H4`. Sono anche le candele su cui il bot opera adesso, quindi
`analisi_in_scala_cfd` e' vero e i livelli non vanno riconvertiti.

## Onesta' sul campione

`M15`, `M5` e `M1min` esistono in archivio solo da giugno 2026: le tre coppie
veloci si possono misurare su tre mesi, non su venti anni, e il numero va
letto con quella riserva. Le tre lente -- `M1->D1`, `W1->H4`, `D1->H1` --
hanno vent'anni di dati.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from typing import Optional, Sequence

# Nessun messaggio, nessuna chiamata a pagamento, nessun ordine: questa e' una
# misura, non una sessione operativa.
os.environ["NVMBOT_IN_PROVA"] = "1"
# Qui si misura la strategia MECCANICA: il giudizio discrezionale e' un'altra
# domanda e si misura a parte, confrontando gli accettati coi rifiutati.
os.environ["GIUDIZIO_ATTIVO"] = "false"
os.environ["GIUDIZIO_SULLE_OBIEZIONI"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ingresso_ltf, motore                       # noqa: E402
from core.definizioni import Bias, Candela                  # noqa: E402
from core.parametri import COPPIE_CRT, TF, UNIVERSO         # noqa: E402
from core.stato import Conto, costruisci_fotografia         # noqa: E402


def _spegni(quali: str) -> list[str]:
    """Disattiva le regole indicate, per misurare quanto costano.

    Non si tocca il codice delle regole: si spegne l'interruttore che le
    rende veti. `CRT-20` ha gia' il suo in `CONFERME_ROMEO` -- sette conferme
    su otto sono spente cosi' da prima di me, proprio perche' usate in AND
    bloccavano tutto. `RISK-05` non ce l'ha, e si sostituisce il predicato
    che decide l'eleggibilita': e' l'unico modo di misurare cosa filtra senza
    riscrivere il motore.

    Restituisce l'elenco di quel che ha spento davvero, per stamparlo accanto
    al risultato: un numero senza la sua configurazione non si puo' rileggere.
    """
    from core import parametri, rischio
    spente = []
    for regola in (q.strip().upper() for q in quali.split(",") if q.strip()):
        if regola.startswith("CRT-"):
            # Si modifica il dizionario SUL POSTO: `blocca_da_sola` lo legge
            # ad ogni chiamata, mentre `setup.py` importa la funzione per
            # nome -- riassegnare il dizionario non arriverebbe a lei.
            parametri.CONFERME_CHE_BLOCCANO_DA_SOLE[regola] = False
            spente.append(regola)
        elif regola == "GEST-01":
            # La soglia sta in `contesto.RR_MINIMO` e viene letta ad ogni
            # chiamata. Con l'ingresso a due tempi il rapporto viene
            # calcolato sulla chiusura di N2, mentre l'ordine parte molto
            # dopo al rientro nell'FVG, cioe' piu' vicino allo stop: e' un
            # filtro applicato a un prezzo che non e' quello d'ingresso.
            # `raccogli.py` lo azzerava gia', per la stessa ragione.
            from core import contesto
            contesto.RR_MINIMO = 0.0
            # Azzerare la soglia non basta: `filtri_attivi` blocca anche
            # quando il rapporto e' INCALCOLABILE, e alla chiusura di N2 lo e'
            # nel 68% dei casi perche' il prezzo ha gia' superato la meta' del
            # range e il bersaglio resta indietro. Al rientro nell'FVG sarebbe
            # di nuovo davanti: e' il filtro giusto applicato al prezzo
            # sbagliato. Qui si toglie del tutto la voce dal risultato.
            vera = contesto.filtri_attivi

            def senza_gest01(**k):
                return tuple(f for f in vera(**k) if f.regola != "GEST-01")

            contesto.filtri_attivi = senza_gest01
            spente.append("GEST-01")
        elif regola == "RISK-05":
            rischio.strumento_eleggibile = lambda **k: True
            spente.append("RISK-05")
        else:
            raise SystemExit(f"non so spegnere {regola}")
    return spente

# Quante candele di contesto passare al motore per ciascun timeframe. Sono le
# stesse di `backtest/scansione.py`: bastano ai livelli strutturali e tengono
# il giro praticabile.
FINESTRA = {
    TF.M12: 8, TF.M6: 12, TF.M3: 24, TF.M1: 70,
    TF.W1: 300, TF.D1: 1300, TF.H4: 200, TF.H1: 200,
    TF.MIN15: 200, TF.MIN5: 200, TF.MIN1: 200,
}


@dataclass(frozen=True)
class Operazione:
    strumento: str
    coppia: str
    direzione: Bias
    ingresso: float
    stop: float
    bersaglio: float
    uscita: float
    esito: str          # "vinta", "persa", "aperta"
    erre: float


def _carica(nome: str, db: str) -> dict[TF, tuple[Candela, ...]]:
    """Le serie di uno strumento, per timeframe, in ordine cronologico."""
    import sqlite3

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    fuori: dict[TF, tuple[Candela, ...]] = {}
    for tf in TF:
        righe = con.execute(
            "SELECT chiusura_utc, apertura, massimo, minimo, chiusura FROM candela "
            "WHERE strumento=? AND tf=? ORDER BY chiusura_utc", (nome, tf.value),
        ).fetchall()
        if not righe:
            continue
        from datetime import datetime, timezone
        serie = []
        for r in righe:
            q = datetime.fromisoformat(str(r["chiusura_utc"]).replace("Z", "+00:00"))
            if q.tzinfo is None:
                q = q.replace(tzinfo=timezone.utc)
            serie.append(Candela(q, float(r["apertura"]), float(r["massimo"]),
                                 float(r["minimo"]), float(r["chiusura"])))
        fuori[tf] = tuple(serie)
    con.close()
    return fuori


def _finestra(serie: Sequence[Candela], fino, quante: int) -> tuple[Candela, ...]:
    """Le ultime `quante` candele chiuse entro `fino`."""
    from bisect import bisect_right
    tempi = [c.orario for c in serie]
    i = bisect_right(tempi, fino)
    return tuple(serie[max(0, i - quante):i])


def _esito(ingresso: float, stop: float, bersaglio: float, direzione: Bias,
           dopo: Sequence[Candela]) -> tuple[str, float, float]:
    """Segue il prezzo barra per barra: prima lo stop o prima il bersaglio?

    Dentro la stessa barra non si sa quale dei due sia arrivato prima, e
    assumere il bersaglio e' il modo classico di gonfiare un backtest. Qui
    vince lo stop: e' la lettura prudente, ed e' quella che non regala niente.
    """
    rischio = abs(ingresso - stop)
    if rischio <= 0:
        return "scartata", ingresso, 0.0
    for c in dopo:
        if direzione is Bias.LONG:
            if c.minimo <= stop:
                return "persa", stop, -1.0
            if c.massimo >= bersaglio:
                return "vinta", bersaglio, (bersaglio - ingresso) / rischio
        else:
            if c.massimo >= stop:
                return "persa", stop, -1.0
            if c.minimo <= bersaglio:
                return "vinta", bersaglio, (ingresso - bersaglio) / rischio
    if not dopo:
        return "aperta", ingresso, 0.0
    ultima = dopo[-1].chiusura
    erre = ((ultima - ingresso) if direzione is Bias.LONG else (ingresso - ultima)) / rischio
    return "aperta", ultima, erre


def misura(strumento: str, storico, tf_range: TF, tf_ing: TF,
           quante_max: Optional[int] = None,
           imbuto=None) -> list[Operazione]:
    """Tutte le operazioni di una coppia su uno strumento."""
    if imbuto is None:
        from collections import Counter
        imbuto = Counter()
    if tf_range not in storico or tf_ing not in storico:
        imbuto["serie mancanti"] += 1
        return []

    # `arma()` scrive in archivio e notifica: qui interessa solo COSA il
    # motore ha deciso di armare, quindi la si intercetta. E' l'unico punto
    # in cui il codice di produzione viene sostituito, ed e' sostituito con
    # una registrazione, non con un'altra logica.
    armati: list[dict] = []

    def _finto_arma(strumento, direzione, tf_crt, tf_ingresso,
                    estremo_sweep, eq_range, lato_opposto):
        armati.append(dict(
            strumento=strumento, direzione=direzione, tf_crt=tf_crt,
            tf_ingresso=tf_ingresso, estremo_sweep=estremo_sweep,
            eq_range=eq_range, lato_opposto=lato_opposto))
        return len(armati)

    vero_arma = ingresso_ltf.arma
    ingresso_ltf.arma = _finto_arma
    operazioni: list[Operazione] = []
    try:
        serie_range = storico[tf_range]
        serie_ing = storico[tf_ing]
        inizio = max(0, len(serie_range) - quante_max) if quante_max else 0
        for candela in serie_range[inizio:]:
            istante = candela.orario
            ridotto = {t: _finestra(storico[t], istante, FINESTRA.get(t, 100))
                       for t in storico}
            if len(ridotto.get(tf_range, ())) < 3:
                continue
            armati.clear()
            foto = costruisci_fotografia(
                istante=istante, strumento=strumento, storico=ridotto,
                conto=Conto(equity=100_000.0,
                            prezzo_cfd=candela.chiusura, valore_punto=1.0),
                eventi_news=(), eta_calendario_ore=0.0,
                analisi_in_scala_cfd=True,
            )
            imbuto["valutazioni"] += 1
            try:
                d = motore.valuta(foto, tf_range)
            except Exception as e:
                imbuto[f"eccezione: {type(e).__name__}"] += 1
                continue
            if "SETUP-02A" in d.regole_applicate or "SETUP-02B" in d.regole_applicate:
                imbuto["CRT formati"] += 1
                for regola in d.regole_che_bloccano:
                    imbuto[f"  fermati da {regola}"] += 1
            if not armati:
                continue
            imbuto["ARMATI"] += 1

            a = armati[-1]
            setup = ingresso_ltf.SetupArmato(
                id_setup=0, strumento=a["strumento"], direzione=a["direzione"],
                tf_crt=a["tf_crt"].value, tf_ingresso=a["tf_ingresso"].value,
                estremo_sweep=a["estremo_sweep"], eq_range=a["eq_range"],
                lato_opposto=a["lato_opposto"], livello_cisd=None,
                fvg_inf=None, fvg_sup=None, barre_attesa=0, armato_utc="",
            )
            # Le candele del timeframe di ingresso DOPO la chiusura del range.
            from bisect import bisect_right
            tempi_ing = [c.orario for c in serie_ing]
            j = bisect_right(tempi_ing, istante)
            finestra_ing = serie_ing[j:j + ingresso_ltf.ATTESA_MASSIMA_BARRE]
            if len(finestra_ing) < 4:
                imbuto["  senza candele di ingresso"] += 1
                continue

            # `controlla` e' STATEFUL: trovato il CISD lo salva con `_annota`
            # e al passaggio dopo se lo ritrova, poi fa lo stesso con l'FVG.
            # I tre passi di CRT-13 avvengono su candele DIVERSE, quindi
            # ricreare il setup vuoto ad ogni giro lo farebbe ripartire dal
            # primo passo per sempre -- che e' esattamente il difetto per cui
            # nove setup armati non producevano un solo ingresso.
            stato: dict = {}
            vero_annota = ingresso_ltf._annota
            ingresso_ltf._annota = lambda _id, **campi: stato.update(campi)
            ingresso_trovato = None
            try:
                for k in range(3, len(finestra_ing) + 1):
                    setup_k = replace(setup, barre_attesa=k - 1, **stato)
                    trovato, _ = ingresso_ltf.controlla(setup_k, finestra_ing[:k])
                    if trovato is not None:
                        ingresso_trovato = (trovato, j + k)
                        break
            finally:
                ingresso_ltf._annota = vero_annota
            if ingresso_trovato is None:
                imbuto["  armati senza ingresso (CRT-13)"] += 1
                continue
            imbuto["INGRESSI"] += 1

            ing, indice_uscita = ingresso_trovato
            dopo = serie_ing[indice_uscita:indice_uscita + 500]
            esito, uscita, erre = _esito(
                ing.prezzo, ing.stop, ing.bersaglio_1, ing.direzione, dopo)
            if esito == "scartata":
                continue
            operazioni.append(Operazione(
                strumento=strumento, coppia=f"{tf_range.value}->{tf_ing.value}",
                direzione=ing.direzione, ingresso=ing.prezzo, stop=ing.stop,
                bersaglio=ing.bersaglio_1, uscita=uscita, esito=esito, erre=erre))
    finally:
        ingresso_ltf.arma = vero_arma
    return operazioni


def main() -> int:
    db = os.environ.get("DB_PATH", "bot.db")
    solo = os.environ.get("COPPIA", "")
    quante = int(os.environ.get("QUANTE", "0")) or None
    spente = _spegni(os.environ.get("SPEGNI", ""))
    print("regole spente:", ", ".join(spente) if spente else "nessuna")

    coppie = [(r, i) for r, i in COPPIE_CRT.items()
              if not solo or f"{r.value}->{i.value}" == solo]

    print(f"archivio: {db}")
    tutte: dict[str, list[Operazione]] = {}
    for tf_range, tf_ing in coppie:
        nome = f"{tf_range.value}->{tf_ing.value}"
        ops: list[Operazione] = []
        from collections import Counter
        imbuto = Counter()
        for strumento in UNIVERSO:
            storico = _carica(strumento, db)
            ops += misura(strumento, storico, tf_range, tf_ing, quante, imbuto)
            print(f"  {nome:<22} {strumento:<8} {len(ops):>5} operazioni", flush=True)
        tutte[nome] = ops
        print(f"  --- imbuto {nome} ---")
        for k, v in imbuto.most_common(14):
            print(f"      {k:<42} {v:>7}")

    print()
    print(f"{'coppia':<22} {'n':>6} {'winrate':>8} {'R medio':>9} {'R totale':>10}")
    print("-" * 60)
    for nome, ops in tutte.items():
        chiuse = [o for o in ops if o.esito in ("vinta", "persa")]
        if not chiuse:
            print(f"{nome:<22} {len(ops):>6}   nessuna operazione chiusa")
            continue
        vinte = sum(1 for o in chiuse if o.esito == "vinta")
        somma = sum(o.erre for o in chiuse)
        print(f"{nome:<22} {len(chiuse):>6} {100*vinte/len(chiuse):>7.1f}% "
              f"{somma/len(chiuse):>+9.4f} {somma:>+10.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
