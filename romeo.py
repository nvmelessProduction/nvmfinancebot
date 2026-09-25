"""Le entrate di Romeo contro i prezzi veri e contro il bot.

    python romeo.py                          # il periodo di studio (2023), configurazione 1
    python romeo.py --configurazioni 1-8     # tutte le configurazioni di capo.py
    python romeo.py --righe                  # anche il dettaglio riga per riga
    python romeo.py --imita                  # quanto il Capo riconosce le scelte di Romeo, fuori campione

Per il periodo di studio: la lettura regge, com'e' andata, se il Cacciatore
vedeva il CRT e, per ogni configurazione, se il bot ha fatto la stessa
entrata, con e senza il Capo. Del 2024-2026 si controlla solo che la lettura
regga (il prezzo e' passato dall'ingresso letto): esiti e confronto col bot
aspettano la Fase G.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from capo import CONFIGURAZIONI, COPPIE, GRADINO, tabella
from nvm.agenti import manopole
from nvm.agenti.cacciatore import Verso, caccia
from nvm.agenti import inventate
from nvm.agenti.capo import COLONNE, INVENTATE, Capo, pesi_per_eta
from nvm.agenti.capo import riga as colonne_del_capo
from nvm.agenti.conferme import SOPRA, tutti_i_pareri
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO, Minuti, carica_periodo
from nvm.dati.ore import carica as carica_ore
from nvm.prova.base import SETTIMANA, Risultato, opera
from nvm.prova.cammino import Tabella
from nvm.prova.campo import Uscita
from nvm.prova.romeo import Entrata, al_prezzo, armati, candidati, confronta, esito, etichette, grandi, leggi
from nvm.tempo import TF, come_testo

RADICE = Path(__file__).resolve().parent
# Un pip, per dividere le entrate di Romeo: sotto i 15 pip di stop entra sul
# timeframe basso (1-15 minuti), che senza i minuti il bot non vede.
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4, "USDCHF": 1e-4, "USDJPY": 1e-2, "XAUUSD": 1.0}
STOP_ALTO = 15
# Le coppie che scendono ai 15 minuti, dove ci sono i minuti: quella del
# manuale e quella un gradino sotto (`spec/grilletto.md`).
COPPIA_MINUTI = {False: (TF.H4, TF.M15), True: (TF.D1, TF.M15)}


def _istante(anno: int, mese: int = 1) -> int:
    return int(datetime(anno, mese, 1, tzinfo=timezone.utc).timestamp())


def _capo_del_2023(numero: int) -> Capo:
    """Il Capo come l'avrebbe avuto il bot a inizio 2023: allenato sulle
    operazioni della configurazione chiuse prima, pesando di piu' le recenti."""
    t = tabella(numero, 1.0, RADICE / "dati" / "grezzi")
    # La colonna della coppia 4 ore -> 15 minuti nello storico vale zero.
    t.x = np.c_[t.x, np.zeros((len(t), len(COLONNE) - t.x.shape[1]))]
    prima = t.chiusa < _istante(2023)
    return Capo.allena(t.x[prima], t.tp1[prima], t.tp2[prima], pesi=pesi_per_eta(t.chiusa[prima], _istante(2023)))


def _opposta(e: Entrata) -> Entrata:
    v = Verso.SHORT if e.verso is Verso.LONG else Verso.LONG
    return Entrata(**{**e.__dict__, "verso": v})


def _numeri(testo: str) -> list[int]:
    if "-" in testo:
        a, b = map(int, testo.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in testo.split(",")]


@dataclass
class Bot:
    """Le operazioni del 2023 di una configurazione, tutte e quelle scelte dal Capo."""

    tutte: list[Risultato] = field(default_factory=list)
    scelte: list[Risultato] = field(default_factory=list)


def operazioni(numero: int, base, fine: int, capo: Capo, minuti: Minuti) -> Bot:
    variante, stretto = CONFIGURAZIONI[numero]
    bot = Bot()
    coppie = [(alto, basso, base) for alto, basso in (GRADINO if numero > 4 else COPPIE)]
    g = grandi(base, fine)
    settimane = costruisci(base, TF.W1).chiuse_entro(fine)
    idee = INVENTATE
    ctx = inventate.Contesto.da(base, fine, g) if idee else None
    if len(minuti):
        alto, basso = COPPIA_MINUTI[numero > 4]
        coppie.append((alto, basso, minuti))
    for alto, basso, dati in coppie:
        fine_dati = int(dati.t[-1]) + dati.passo
        alte = costruisci(dati, alto).chiuse_entro(fine_dati)
        basse = costruisci(dati, basso).chiuse_entro(fine_dati)
        sopra = costruisci(base, SOPRA[alto]).chiuse_entro(fine)
        ops = opera(alte, basse, _istante(2023), _istante(2024), variante, stretto)
        if not ops:
            continue
        x = np.array([colonne_del_capo(r, *tutti_i_pareri(r.scatto, alte, basse, sopra, settimane, g),
                                       inventate.rispondi_tutte(idee, r, ctx)) for r in ops])
        prese = capo.entra(x, np.array([r.rr1 for r in ops]), np.array([r.rr2 for r in ops]),
                           np.array([r.costo_erre for r in ops]))
        bot.tutte += ops
        bot.scelte += [r for r, a in zip(ops, prese) if a]
    return bot


def _auc(p: np.ndarray, y: np.ndarray) -> float:
    """La probabilita' che una scelta di Romeo abbia una somiglianza piu' alta di un altro candidato."""
    o = np.argsort(p)
    r = np.empty(len(p))
    r[o] = np.arange(1, len(p) + 1)
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def imita(radice: Path, entrate: list[Entrata]) -> None:
    """Quanto il Capo riconosce le scelte di Romeo (`spec/capo.md`), fuori
    campione: per ogni trimestre del 2023 impara la somiglianza sugli altri tre.
    E cosa sceglie il bot, che decide con la qualita' attesa."""
    capo = _capo_del_2023(1)
    ops, xs, ys = [], [], []
    for strumento in sorted({e.strumento for e in entrate}):
        ore, _ = carica_ore(radice, strumento, _istante(2021), _istante(2024, 3))
        minuti = carica_periodo(radice / "minuti", strumento, _istante(2023), _istante(2024))
        o, x = candidati(ore, minuti, _istante(2023), _istante(2024))
        ops += o
        xs.append(x)
        ys.append(etichette([e for e in entrate if e.strumento == strumento], o))
    x, y = np.vstack(xs), np.concatenate(ys)
    trimestre = np.array([datetime.fromtimestamp(o.quando, tz=timezone.utc).month - 1 for o in ops]) // 3
    rr1, rr2 = np.array([o.rr1 for o in ops]), np.array([o.rr2 for o in ops])
    costi = np.array([o.costo_erre for o in ops])
    tp1 = np.array([o.tp1_preso or o.uscita is Uscita.TARGET for o in ops])
    erre = np.array([o.erre for o in ops])
    simile = np.zeros(len(ops))
    con_romeo = np.zeros(len(ops), bool)
    fiducia = []
    for k in range(4):
        prova = trimestre == k
        c = capo.impara_romeo(x[~prova], y[~prova]).impara_fiducia(x[~prova], tp1[~prova])
        simile[prova] = c.somiglianza(x[prova])
        con_romeo[prova] = c.entra(x[prova], rr1[prova], rr2[prova], costi[prova])
        fiducia.append(f"{c.fiducia_in_romeo:+.3f}")
    atteso = capo.entra(x, rr1, rr2, costi)
    settimane_romeo = Counter(e.dal // SETTIMANA for e in entrate)
    alte = {e.id for e in entrate if e.rischio and e.rischio / PIP[e.strumento] >= STOP_ALTO}
    print(f"\nLa somiglianza a Romeo, fuori campione per trimestre: {len(ops)} candidati del 2023, "
          f"{int(y.sum())} sono le scelte di Romeo. Le riconosce al {_auc(simile, y):.2f} (0,50 = a caso); "
          f"somiglianza media delle sue scelte {simile[y].mean():.1%}, degli altri {simile[~y].mean():.1%}.")
    print(f"  Fiducia in Romeo imparata dai risultati, trimestre per trimestre: {', '.join(fiducia)}")
    for nome, scelta in (("tutte le operazioni", np.ones(len(ops), bool)), ("il Capo senza la voce di Romeo", atteso),
                         ("il Capo con la voce di Romeo", con_romeo)):
        prese = [o for o, v in zip(ops, scelta) if v]
        vicine = {e.id for e in entrate if confronta(e, prese)}
        trovate = {e.id for e in entrate if (c := confronta(e, prese)) and c[0].ritrovata}
        per_romeo = sum(Counter(o.quando // SETTIMANA for o in prese)[w] for w in settimane_romeo) / len(entrate)
        print(f"  {nome:34} prese {len(prese):5}  R medio {erre[scelta].mean():+.3f}  scelte di Romeo {int(y[scelta].sum())}/{int(y.sum())}"
              f"  vicine {len(vicine):3}  ritrovate {len(trovate):2} (timeframe alto {len(trovate & alte)}/{len(alte)})"
              f"  per ognuna di Romeo {per_romeo:5.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalogo", default=str(RADICE / "casi" / "entrate-romeo.csv"))
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--configurazioni", default="1")
    parser.add_argument("--righe", action="store_true")
    parser.add_argument("--imita", action="store_true")
    a = parser.parse_args()
    manopole.carica_e_applica()
    radice = Path(a.cartella)
    if a.imita:
        imita(radice, [e for e in leggi(Path(a.catalogo)) if e.periodo == "studio" and e.strumento in PUNTO])
        return
    numeri = _numeri(a.configurazioni)
    capi = {n: _capo_del_2023(n) for n in numeri}
    tutte = leggi(Path(a.catalogo))
    fuori = [e for e in tutte if e.strumento not in PUNTO]
    nostre = [e for e in tutte if e.strumento in PUNTO]
    studio = [e for e in nostre if e.periodo == "studio"]
    print(f"{len(tutte)} entrate nel catalogo; {len(fuori)} su strumenti non ancora nei dati "
          f"({', '.join(sorted({e.strumento for e in fuori}))}).")

    lette_male, esiti, vs_romeo = [], Counter(), Counter()
    per_coppia, opposto, righe = Counter(), Counter(), []
    romeo_settimane = Counter(e.dal // SETTIMANA for e in studio)
    # Per configurazione: ritrovate (tutte, Capo), vicine, operazioni per settimana (tutte, Capo).
    ritrovate = {n: [set(), set()] for n in numeri}
    vicine = {n: set() for n in numeri}
    settimane = {n: [defaultdict(int), defaultdict(int)] for n in numeri}
    coperti: dict[str, tuple[int, int]] = {}
    for strumento in sorted({e.strumento for e in nostre}):
        mie = [e for e in nostre if e.strumento == strumento]
        base, _ = carica_ore(radice, strumento, _istante(2022, 6), _istante(2026, 10))
        fine = int(base.t[-1]) + base.passo
        ore = costruisci(base, TF.H1).chiuse_entro(fine)
        crt = {(al, ba): caccia(costruisci(base, al).chiuse_entro(fine), costruisci(base, ba).chiuse_entro(fine))
               for al, ba in COPPIE}
        minuti = carica_periodo(radice / "minuti", strumento, _istante(2023), _istante(2024))
        if len(minuti):
            coperti[strumento] = (int(minuti.t[0]), int(minuti.t[-1]))
        bot = {n: operazioni(n, base, fine, capi[n], minuti) for n in numeri}
        for n, b in bot.items():
            for k, ops in enumerate((b.tutte, b.scelte)):
                for op in ops:
                    settimane[n][k][op.quando // SETTIMANA] += 1
        for e in mie:
            quando = al_prezzo(e, ore)
            if e.ingresso is not None and quando is None:
                lette_male.append(e)
            if e.periodo != "studio":
                continue
            riga = [f"{e.id} {e.strumento} {e.verso.value:5} {e.tipo:10} {come_testo(e.dal)}"]
            if quando is not None:
                x = esito(e, ore, quando)
                esiti[x] += 1
                if e.esito_romeo in ("target", "stop") and x in ("target", "stop"):
                    vs_romeo["uguale" if x == e.esito_romeo else "diverso"] += 1
                riga.append(f"esito {x}")
            viste = [f"{al.value}-{ba.value}" for (al, ba), cc in crt.items() if armati(e, cc)]
            for v in viste:
                per_coppia[v] += 1
            per_coppia["almeno una"] += bool(viste)
            opposto["almeno una"] += any(armati(_opposta(e), cc) for cc in crt.values())
            riga.append("CRT armati: " + (", ".join(viste) or "nessuno"))
            for n, b in bot.items():
                for k, ops in enumerate((b.tutte, b.scelte)):
                    c = confronta(e, ops)
                    if c and c[0].ritrovata:
                        ritrovate[n][k].add(e.id)
                    if k == 0 and c:
                        vicine[n].add(e.id)
                if n == numeri[0]:
                    c = confronta(e, b.tutte)
                    if c:
                        op, d = c[0].operazione, c[0].distanza
                        riga.append(f"bot {n}: {op.alto_tf.value}-{op.basso_tf.value} a {op.ingresso:.5g}, "
                                    f"distanza {'?' if d is None else f'{d:.1f}'} rischi")
                    else:
                        riga.append(f"bot {n}: niente")
            righe.append("  ".join(riga))

    con_prezzo = [e for e in studio if e.ingresso is not None]
    con_rischio = [e for e in studio if e.rischio]
    print(f"\nPeriodo di studio (2023), strumenti nostri: {len(studio)} entrate, "
          f"{len(con_prezzo)} con l'ingresso letto, {len(con_rischio)} anche con lo stop.")
    print(f"Letture che non reggono (il prezzo non e' mai passato dall'ingresso): "
          f"{len(lette_male)} su {sum(e.ingresso is not None for e in nostre)}")
    for e in lette_male:
        print(f"  {e.id} {e.periodo} {e.strumento} {e.verso.value} {e.ingresso} {come_testo(e.dal)}")
    print(f"Esiti misurati sulle ore (studio): {dict(esiti)}; "
          f"rispetto a quello che dice Romeo: {dict(vs_romeo)}")
    print(f"CRT armato nello stesso verso durante la finestra di Romeo (coppie del manuale): "
          + ", ".join(f"{k} {v}" for k, v in per_coppia.items()) + f" (su {len(studio)}); "
          f"nel verso opposto, almeno una: {opposto['almeno una']}")

    n_romeo = sum(romeo_settimane.values())
    alte = {e.id for e in con_rischio if e.rischio / PIP[e.strumento] >= STOP_ALTO}
    print(f"\nIl cancello: ritrovate entro meta' del rischio su {len(con_rischio)} con lo stop letto "
          f"(ne servono 7 su 10), e operazioni del bot per ognuna di Romeo nelle stesse settimane "
          f"(al massimo 3; Romeo {n_romeo}). Delle {len(con_rischio)}, {len(alte)} sono sul timeframe alto "
          f"(stop di {STOP_ALTO} pip o piu') e {len(con_rischio) - len(alte)} sul basso.")
    nei_minuti = {e.id for e in con_rischio if e.id not in alte and e.strumento in coperti
                  and coperti[e.strumento][0] <= e.dal and e.al <= coperti[e.strumento][1]}
    print("Minuti: " + (", ".join(f"{k} fino al {datetime.fromtimestamp(v[1], tz=timezone.utc):%d/%m/%Y}"
                                  for k, v in coperti.items()) or "nessuno")
          + f"; entrate sul timeframe basso coperte dai minuti: {len(nei_minuti)}")
    print(f"{'conf':>4}  {'variante':16} {'stop':8} {'coppie':13} {'vicine':>6} {'ritrovate':>9} {'di cui alto':>11} "
          f"{'di cui basso':>12} {'col Capo':>8} {'per Romeo':>9} {'col Capo':>8}")
    for n in numeri:
        variante, stretto = CONFIGURAZIONI[n]
        per_romeo = [sum(settimane[n][k][s] for s in romeo_settimane) / max(n_romeo, 1) for k in (0, 1)]
        print(f"{n:>4}  {variante.value:16} {'stretto' if stretto else 'estremo':8} "
              f"{'gradino sotto' if n > 4 else 'manuale':13} {len(vicine[n]):>6} {len(ritrovate[n][0]):>9} "
              f"{len(ritrovate[n][0] & alte):>11} {len(ritrovate[n][0] & nei_minuti):>12} {len(ritrovate[n][1]):>8} {per_romeo[0]:>9.1f} {per_romeo[1]:>8.1f}")
    if a.righe:
        print("\n" + "\n".join(righe))


if __name__ == "__main__":
    main()
