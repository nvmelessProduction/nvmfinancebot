"""Le entrate di Romeo contro i prezzi veri e contro il bot.

    python romeo.py                 # il periodo di studio (fino al 2023)
    python romeo.py --righe         # anche il dettaglio riga per riga

Per il periodo di studio: la lettura regge, com'e' andata, se il Cacciatore
vedeva il CRT e se il bot ha fatto la stessa entrata. Del 2024-2026 si
controlla solo che la lettura regga (il prezzo e' passato dall'ingresso
letto): esiti e confronto col bot aspettano la Fase G.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nvm.agenti.cacciatore import Verso, caccia
from nvm.agenti.capo import COLONNE, Capo, pesi_per_eta
from nvm.agenti.capo import riga as colonne_del_capo
from nvm.agenti.conferme import SOPRA, contesto, key_level, orario
from nvm.dati.candele import costruisci
from nvm.dati.minuti import PUNTO
from nvm.dati.ore import carica as carica_ore
from nvm.prova.base import SETTIMANA, opera
from nvm.prova.cammino import Tabella
from nvm.prova.romeo import Entrata, al_prezzo, armati, confronta, esito, leggi
from nvm.tempo import TF, come_testo

RADICE = Path(__file__).resolve().parent
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))


def _istante(anno: int, mese: int = 1) -> int:
    return int(datetime(anno, mese, 1, tzinfo=timezone.utc).timestamp())


def _capo_del_2023() -> Capo:
    """Il Capo come l'avrebbe avuto il bot a inizio 2023: allenato sulle
    operazioni della base chiuse prima, pesando di piu' le recenti."""
    t = Tabella.carica(RADICE / "dati" / "tabelle" / "conf1.npz")
    # La colonna della coppia 4 ore -> 15 minuti nello storico vale zero.
    t.x = np.c_[t.x, np.zeros((len(t), len(COLONNE) - t.x.shape[1]))]
    prima = t.chiusa < _istante(2023)
    return Capo.allena(t.x[prima], t.tp1[prima], t.tp2[prima], pesi=pesi_per_eta(t.chiusa[prima], _istante(2023)))


def _opposta(e: Entrata) -> Entrata:
    v = Verso.SHORT if e.verso is Verso.LONG else Verso.LONG
    return Entrata(**{**e.__dict__, "verso": v})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalogo", default=str(RADICE / "casi" / "entrate-romeo.csv"))
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--righe", action="store_true")
    a = parser.parse_args()
    radice = Path(a.cartella)
    tutte = leggi(Path(a.catalogo))
    fuori = [e for e in tutte if e.strumento not in PUNTO]
    nostre = [e for e in tutte if e.strumento in PUNTO]
    print(f"{len(tutte)} entrate nel catalogo; {len(fuori)} su strumenti non ancora nei dati "
          f"({', '.join(sorted({e.strumento for e in fuori}))}).")

    capo = _capo_del_2023()
    lette_male, esiti, vs_romeo = [], Counter(), Counter()
    per_coppia, opposto, ritrovate, vicine, righe = Counter(), Counter(), [], [], []
    ritrovate_capo = []
    bot_settimane, capo_settimane, romeo_settimane = defaultdict(int), defaultdict(int), defaultdict(int)
    for strumento in sorted({e.strumento for e in nostre}):
        mie = [e for e in nostre if e.strumento == strumento]
        base, _ = carica_ore(radice, strumento, _istante(2022, 6), _istante(2026, 10))
        fine = int(base.t[-1]) + base.passo
        ore = costruisci(base, TF.H1).chiuse_entro(fine)
        studio = [e for e in mie if e.periodo == "studio"]
        operazioni, scelte, crt = [], [], {}
        for alto, basso in COPPIE:
            alte = costruisci(base, alto).chiuse_entro(fine)
            basse = costruisci(base, basso).chiuse_entro(fine)
            sopra = costruisci(base, SOPRA[alto]).chiuse_entro(fine)
            crt[(alto, basso)] = caccia(alte, basse)
            ops = opera(alte, basse, _istante(2023), _istante(2024))
            operazioni += ops
            if ops:
                x = np.array([colonne_del_capo(r, key_level(r.scatto, sopra, basse), orario(r.scatto, basse),
                                   contesto(r.scatto, alte, sopra)) for r in ops])
                atteso = capo.valore_atteso(x, np.array([r.rr1 for r in ops]), np.array([r.rr2 for r in ops]),
                                            np.array([r.costo_erre for r in ops]))
                scelte += [r for r, a in zip(ops, atteso) if a > 0]
        for op in operazioni:
            bot_settimane[op.quando // SETTIMANA] += 1
        for op in scelte:
            capo_settimane[op.quando // SETTIMANA] += 1
        for e in mie:
            quando = al_prezzo(e, ore)
            if e.ingresso is not None and quando is None:
                lette_male.append(e)
            if e.periodo != "studio":
                continue
            romeo_settimane[e.dal // SETTIMANA] += 1
            riga = [f"{e.id} {e.strumento} {e.verso.value:5} {e.tipo:10} {come_testo(e.dal)}"]
            if quando is not None:
                x = esito(e, ore, quando)
                esiti[x] += 1
                if e.esito_romeo and x in ("target", "stop"):
                    vs_romeo["uguale" if x == e.esito_romeo else "diverso"] += 1
                riga.append(f"esito {x}")
            viste = [f"{al.value}-{ba.value}" for (al, ba), cc in crt.items() if armati(e, cc)]
            for v in viste:
                per_coppia[v] += 1
            per_coppia["almeno una"] += bool(viste)
            opposto["almeno una"] += any(armati(_opposta(e), cc) for cc in crt.values())
            conf_capo = confronta(e, scelte)
            if conf_capo and conf_capo[0].ritrovata:
                ritrovate_capo.append(e)
            riga.append("CRT armati: " + (", ".join(viste) or "nessuno"))
            conf = confronta(e, operazioni)
            if conf:
                c = conf[0]
                if c.ritrovata:
                    ritrovate.append(e)
                vicine.append(e)
                d = "?" if c.distanza is None else f"{c.distanza:.1f}"
                riga.append(f"bot: {c.operazione.alto_tf.value}-{c.operazione.basso_tf.value} "
                            f"a {c.operazione.ingresso:.5g}, distanza {d} rischi")
            else:
                riga.append("bot: niente")
            righe.append("  ".join(riga))

    studio = [e for e in nostre if e.periodo == "studio"]
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
    print(f"CRT armato nello stesso verso durante la finestra di Romeo: "
          + ", ".join(f"{k} {v}" for k, v in per_coppia.items()) + f" (su {len(studio)}); "
          f"nel verso opposto, almeno una: {opposto['almeno una']}")
    print(f"Il bot entra nello stesso verso nella finestra: {len(vicine)}; "
          f"entro meta' del rischio di Romeo: {len(ritrovate)} su {len(con_rischio)} con lo stop letto")
    print(f"Con il Capo del 2023 (sceglie solo E > 0): entro meta' del rischio {len(ritrovate_capo)}")
    settimane = list(romeo_settimane)
    n_romeo = sum(romeo_settimane[s] for s in settimane)
    for nome, conti in (("tutte le operazioni della base", bot_settimane), ("le scelte del Capo", capo_settimane)):
        n = sum(conti[s] for s in settimane)
        print(f"Nelle settimane con entrate di Romeo, {nome}: {n} contro {n_romeo} di Romeo "
              f"({n / max(n_romeo, 1):.1f} per ognuna; il PIANO chiede al massimo 3)")
    if a.righe:
        print("\n" + "\n".join(righe))


if __name__ == "__main__":
    main()
