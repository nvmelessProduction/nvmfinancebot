"""Il backtest completo: sei strumenti, dal segnale all'esito.

Quello che NON e' modellato, e va letto insieme ai numeri:
  - spread e commissioni sono zero;
  - il calendario news e' vuoto, quindi CTX-02 non ferma mai nulla (dal vivo
    toglie operazioni, non ne aggiunge);
  - l'ingresso e' la chiusura di N2 sul future, non l'apertura di N3 sul CFD;
  - `TF_H4` e' ricostruito dalle orarie (core.aggregazione.aggrega_orarie);
  - `target_raggiunto_per_tf` e' vuoto: nessun target di timeframe risulta mai
    raggiunto, quindi SETUP-06 sceglie sempre il timeframe piu' alto con una
    bias e SETUP-08 non ammette mai un reversal.
"""
from __future__ import annotations

import sys
from bisect import bisect_right
from collections import Counter
from dataclasses import replace

from archivio import FUTURE, carica, finestra, indice_temporale
from esiti import APERTA, PAREGGIO, PRIMO, STOP, TARGET, simula
from fasi import Sorveglianza, mitigazione_del_gap
from memoria import memoizza_gap
from scansione import FINESTRA, Segnale, _chiave_contesto
from core import motore
from core.definizioni import Bias
from core.parametri import TF, UNIVERSO
from core.stato import Conto, costruisci_fotografia, key_level_presi

TRIGGER = (TF.H1, TF.H4, TF.D1)
MAX_APERTE = 1        # una posizione per strumento alla volta


def scansiona(strumento: str, future: str, storico, tempi):
    istanti = sorted(
        ((c.orario, tf) for tf in TRIGGER for c in storico.get(tf, ())),
        key=lambda x: (x[0], x[1].value),
    )
    # I gap dipendono solo dai timeframe di contesto: calcolarli a ogni
    # chiusura H4 significa rifare sei volte al giorno lo stesso lavoro.
    memoizza_gap(lambda istante: _chiave_contesto(tempi, istante))

    chiave = None
    contesto = None
    mitig = None
    sorveglianza = Sorveglianza()
    ultima = -1
    orarie = storico[TF.H1]
    funnel = Counter()
    segnali = []

    for istante, tf in istanti:
        nuova = _chiave_contesto(tempi, istante) + (bisect_right(tempi[TF.H4], istante),)
        if nuova != chiave:
            ridotto = {t: finestra(storico[t], tempi[t], istante, FINESTRA[t])
                       for t in FINESTRA if t in storico}
            contesto = costruisci_fotografia(
                istante=istante, strumento=strumento, storico=ridotto,
                conto=Conto(equity=100_000.0, prezzo_cfd=1.0, valore_punto=1.0),
                eventi_news=(), eta_calendario_ore=0.0,
            )
            mitig = mitigazione_del_gap(contesto.gap_reazione, ridotto)
            chiave = nuova

        fino = bisect_right(tempi[TF.H1], istante)
        while ultima + 1 < fino:
            ultima += 1
            sorveglianza.osserva(contesto.gap_reazione, orarie[ultima])

        recenti = finestra(storico[tf], tempi[tf], istante, 2)
        if len(recenti) < 2:
            continue
        foto = replace(contesto, istante=istante, candele_per_tf={tf: recenti},
                       prezzo_cfd=recenti[-1].chiusura,
                       gap_fase=sorveglianza.fase, mitigazione=mitig)
        decisione = motore.valuta(foto, tf)

        if "SETUP-02A" in decisione.regole_applicate or "SETUP-02B" in decisione.regole_applicate:
            funnel["CRT formati"] += 1
            for regola in decisione.regole_che_bloccano:
                funnel[f"  bloccati da {regola}"] += 1
        if decisione.azione == "NONE":
            continue
        funnel["operabili"] += 1
        segnali.append(Segnale(
            strumento=strumento, tf_trigger=tf, istante=istante,
            direzione=decisione.direzione, ingresso=foto.prezzo_cfd,
            stop=decisione.livello_stop, tp1=decisione.tp1,
            rapporto=decisione.rapporto_su_tp1, target=decisione.target_finale,
        ))
    return segnali, funnel


def main() -> int:
    totale = Counter()
    per_strumento = {}
    tutti = []

    for strumento, dati in UNIVERSO.items():
        future = dati.future
        storico = carica(future)
        tempi = indice_temporale(storico)
        segnali, funnel = scansiona(strumento, future, storico, tempi)

        def contesto(istante, storico=storico, tempi=tempi):
            ridotto = {t: finestra(storico[t], tempi[t], istante, FINESTRA[t])
                       for t in FINESTRA if t in storico}
            return key_level_presi(ridotto, istante)

        esiti = []
        libera_da = None
        for segnale in segnali:
            if libera_da is not None and segnale.istante < libera_da:
                continue                       # RISK-06: una posizione alla volta
            esito = simula(segnale, storico, tempi, contesto)
            esiti.append(esito)
            indice = bisect_right(tempi[TF.H1], segnale.istante) + esito.barre
            if indice < len(storico[TF.H1]):
                libera_da = storico[TF.H1][indice].orario
        per_strumento[strumento] = (funnel, esiti)
        tutti.extend(esiti)
        print(f"{strumento} ({future}): {len(segnali)} segnali, {len(esiti)} eseguibili",
              flush=True)

    _stampa(per_strumento, tutti)
    return 0


def _stampa(per_strumento, tutti) -> None:
    print("\n" + "=" * 72)
    print("IMBUTO  (quante volte ciascuna regola ha impedito un'operazione)")
    print("=" * 72)
    somma = Counter()
    for _, (funnel, _) in per_strumento.items():
        somma.update(funnel)
    for voce, quante in somma.most_common():
        print(f"{quante:8d}  {voce}")

    print("\n" + "=" * 72)
    print("ESITI")
    print("=" * 72)
    intest = f"{'strumento':10s} {'op.':>4s} {'stop':>5s} {'be':>4s} {'tp1':>5s} {'targ':>5s} {'aperte':>7s} {'winrate':>8s} {'R tot':>8s}"
    print(intest)
    print("-" * len(intest))
    for strumento, (_, esiti) in per_strumento.items():
        print(_riga(strumento, esiti))
    print("-" * len(intest))
    print(_riga("TOTALE", tutti))

    chiuse = [e for e in tutti if e.esito != APERTA]
    if chiuse:
        print(f"\nOperazioni chiuse: {len(chiuse)}")
        print(f"R totale: {sum(e.erre for e in chiuse):+.2f}")
        print(f"R medio per operazione: {sum(e.erre for e in chiuse)/len(chiuse):+.3f}")
    for esito in sorted(tutti, key=lambda e: e.segnale.istante):
        s = esito.segnale
        print(f"  {s.istante:%Y-%m-%d %H:%M}  {s.strumento:7s} {s.tf_trigger.value:6s} "
              f"{s.direzione.value:5s}  in {s.ingresso:>10.4f} stop {s.stop:>10.4f} "
              f"tp1 {s.tp1:>10.6f}  R{s.rapporto:>5.2f}  ->  {esito.esito:6s} {esito.erre:+.2f}")


def _riga(nome, esiti) -> str:
    conta = Counter(e.esito for e in esiti)
    chiuse = [e for e in esiti if e.esito != APERTA]
    vincenti = conta[PRIMO] + conta[TARGET]
    winrate = f"{100*vincenti/len(chiuse):.1f}%" if chiuse else "n/d"
    return (f"{nome:10s} {len(esiti):4d} {conta[STOP]:5d} {conta[PAREGGIO]:4d} "
            f"{conta[PRIMO]:5d} {conta[TARGET]:5d} {conta[APERTA]:7d} {winrate:>8s} "
            f"{sum(e.erre for e in chiuse):+8.2f}")


if __name__ == "__main__":
    sys.exit(main())
