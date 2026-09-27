"""Il Capo alla prova (Fase F): le quattro configurazioni di `spec/capo.md`.

    python capo.py                      # tutte e quattro, poi il giudizio
    python capo.py --spread 1.5         # la prova di robustezza, stesso giudizio
    python capo.py --configurazioni 1
    python capo.py --configurazioni 5,6,7,8   # la variante "un gradino sotto"

La prima volta costruisce le tabelle delle operazioni (qualche minuto per
configurazione) e le lascia in dati/tabelle; le volte dopo le riprende.
Ogni giudizio va scritto in `registro/tentativi.md`, anche quando va male.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from nvm.agenti import inventate, manopole
from nvm.agenti.cacciatore import Variante
from nvm.agenti.capo import COLONNE, INVENTATE, Capo, pesi_per_eta
from nvm.agenti import portafoglio
from nvm.agenti.portafoglio import Operazioni
from nvm.cervello import scuola
from nvm.agenti.rischio import esiti, impara_parte, kelly
from nvm.dati.minuti import PUNTO, Minuti, carica_periodo
from nvm.dati.strumenti import BASE
from nvm.dati.ore import carica as carica_ore
from nvm.prova.cammino import Tabella, cammino, costruisci_tabella, giudica
from nvm.prova.campo import Uscita
from nvm.prova.romeo import candidati, etichette, leggi
from nvm.tempo import TF

RADICE = Path(__file__).resolve().parent
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
# La variante "un gradino sotto" (spec/grilletto.md). Il giornaliero -> 15
# minuti aspetta i minuti di vent'anni: finche' mancano, queste
# configurazioni si misurano su mensile e settimanale, contro la base delle
# stesse coppie.
GRADINO = ((TF.MN, TF.H4), (TF.W1, TF.H1))
CONFIGURAZIONI = {
    1: (Variante.MANUALE, False),
    2: (Variante.MANUALE, True),
    3: (Variante.CHIUSURA_DENTRO, False),
    4: (Variante.CHIUSURA_DENTRO, True),
}
CONFIGURAZIONI |= {n + 4: v for n, v in CONFIGURAZIONI.items()}
K = len(CONFIGURAZIONI)
MINIMO_SCELTE = 300
SOGLIA = 0.10
DAL, AL = 2006, 2023
PRIMO_GIUDICATO = 2008


def _istante(anno: int) -> int:
    return int(datetime(anno, 1, 1, tzinfo=timezone.utc).timestamp())


def tabella(numero: int, spread: float, radice: Path) -> Tabella:
    # Il nome porta l'impronta delle manopole degli agenti e dei quarti d'ora usati: una
    # tabella fatta con manopole o dati diversi non si riusa mai per sbaglio.
    quarti = quarti_storici(radice) if numero <= 4 else {}
    nome = (f"conf{numero}" + (f"-spread{spread:g}" if spread != 1 else "")
            + f"-{manopole.impronta()}{inventate.impronta(INVENTATE)}{impronta_quarti(quarti)}.npz")
    percorso = RADICE / "dati" / "tabelle" / nome
    if percorso.exists():
        t = Tabella.carica(percorso)
        # Le tabelle di prima del 27/09/2026 non hanno strumento e verso, ne' (quella del bot)
        # cosa vedeva ogni agente: si rifanno.
        if t.strumento is not None and (numero != 1 or (t.viste is not None and t.piani is not None)):
            return t
    variante, stretto = CONFIGURAZIONI[numero]
    if numero == 1:
        variante = None     # la configurazione del bot: la variante e' quella della manopola del Cacciatore
    t = costruisci_tabella(ore_storiche(radice), GRADINO if numero > 4 else COPPIE, _istante(DAL), _istante(AL + 1),
                           variante, stretto, spread, dire=lambda testo: print(f"  conf {numero} {testo}", flush=True),
                           quarti=quarti, con_viste=numero == 1)
    t.salva(percorso)
    return t


def ore_storiche(radice: Path) -> dict:
    """Le ore di ogni strumento per il periodo della tabella, con il margine per i CRT a cavallo."""
    dal, al = _istante(DAL), _istante(AL + 1)
    fuori = {}
    for s in PUNTO:
        ore = carica_ore(radice, s, dal - 70 * 86400, al + 70 * 86400)[0]
        if len(ore):
            fuori[s] = ore
    return fuori


def quarti_storici(radice: Path) -> dict:
    """I quarti d'ora di ogni strumento arrivati dalla VPS (`importa_vps.py`), per il periodo
    della tabella: ci nasce la coppia 4 ore -> 15 minuti. Vuoto finche' non arrivano."""
    dal, al = _istante(DAL) - 70 * 86400, _istante(AL + 1) + 70 * 86400
    fuori = {}
    for s in PUNTO:
        pezzi = [Minuti.carica(f).fra(dal, al) for f in sorted((radice / "quarti" / s).glob(f"{s}-*.npz"))]
        pezzi = [p for p in pezzi if len(p)]
        if pezzi:
            fuori[s] = Minuti.unisci(pezzi)
    return fuori


def impronta_quarti(quarti: dict) -> str:
    """Un nome corto per i quarti d'ora usati (quali strumenti, da quando a quando)."""
    if not quarti:
        return ""
    import hashlib
    testo = "|".join(f"{s}:{int(m.t[0])}:{int(m.t[-1])}:{len(m)}" for s, m in sorted(quarti.items()))
    return "-q" + hashlib.sha1(testo.encode()).hexdigest()[:6]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--configurazioni", default="1,2,3,4")
    parser.add_argument("--spread", type=float, default=1.0)
    parser.add_argument("--cartella", default=str(RADICE / "dati" / "grezzi"))
    parser.add_argument("--vivo", action="store_true",
                        help="allena il Capo su tutto il 2006-2023 (configurazione 1) e lo salva per il bot dal vivo")
    a = parser.parse_args()
    radice = Path(a.cartella)
    manopole.carica_e_applica()
    if a.vivo:
        salva_per_il_vivo(tabella(1, 1.0, radice))
        return

    base = tabella(1, a.spread, radice)
    giudicati = _giudicati(base)
    # Le operazioni della base con il range giornaliero (colonna "coppia D1-H1").
    giornaliero = base.x[:, COLONNE.index("coppia D1-H1")] == 1
    for numero in map(int, a.configurazioni.split(",")):
        t = base if numero == 1 else tabella(numero, a.spread, radice)
        c = cammino(t, PRIMO_GIUDICATO, AL)
        # Il metro e' sempre la base vera (configurazione 1, senza Capo), negli
        # stessi anni e, per il gradino sotto, sulle stesse coppie.
        metro = giudicati & ~giornaliero if numero > 4 else giudicati
        g = giudica(t.quando[c.scelte], t.erre[c.scelte], base.quando[metro], base.erre[metro], k=K)
        variante, stretto = CONFIGURAZIONI[numero]
        passa = (g.n_scelte >= MINIMO_SCELTE and g.differenza >= SOGLIA and g.basso > 0 and g.anni_concordi >= 0.8)
        print(f"\n== configurazione {numero}: {variante.value}, {'stop stretto' if stretto else 'stop all estremo'}"
              + (", un gradino sotto (solo mensile e settimanale)" if numero > 4 else "")
              + (f", spread x{a.spread:g}" if a.spread != 1 else ""))
        print(f"  tutte le operazioni della configurazione negli anni giudicati: {int(c.giudicati.sum())}, "
              f"R medio {t.erre[c.giudicati].mean():+.3f}")
        print("  " + g.testo())
        print(f"  cancello: {'PASSA' if passa else 'non passa'}")
        ultimo = max(c.fiducia)
        print(f"  fiducia del Capo nel {ultimo} (peso su p1 / su q, colonne standardizzate):")
        for nome, w1, w2 in c.fiducia[ultimo]:
            print(f"    {nome:28} {w1:+.3f} / {w2:+.3f}")


def salva_per_il_vivo(t: Tabella) -> None:
    """Il Capo e il Rischio di partenza del bot dal vivo, e lo storico su cui si
    riaddestrano ogni fine settimana.

    Il Capo si allena su tutto il 2006-2023, pesando di piu' i casi recenti.
    Il Rischio impara quanta parte del Kelly usare dal cammino anno per anno:
    il Capo di ogni anno allenato solo sugli anni prima, le sue puntate e i
    risultati veri.
    """
    cartella = RADICE / "nvm" / "vivo"
    if t.x.shape[1] < len(COLONNE):
        # Colonne aggiunte dopo (la coppia 4 ore -> 15 minuti): nello storico valgono zero.
        t.x = np.c_[t.x, np.zeros((len(t), len(COLONNE) - t.x.shape[1]))]
    fine = int(t.chiusa.max())
    capo = Capo.allena(t.x, t.tp1, t.tp2, pesi=pesi_per_eta(t.chiusa, fine))
    op = operazioni_del_capo(t)
    kelly_f, kelly_r = op.kelly, op.erre
    rischio = impara_il_conto(op)
    parte = rischio["parte"]
    (cartella / "rischio.json").write_text(json.dumps(rischio), encoding="utf-8")
    if t.viste is not None:
        # I cervelli degli agenti: a scuola sui vent'anni, e l'esame contro il Capo di oggi.
        kelly_capo, entra_capo = stime_del_capo(t)
        cervelli = scuola.per_il_vivo(t, kelly_capo, entra_capo)
        (cartella / "cervelli.json").write_text(json.dumps(cervelli), encoding="utf-8")
    romeo = candidati_di_romeo()
    capo = capo.impara_romeo(romeo["romeo_x"], romeo["romeo_y"]).impara_fiducia(romeo["romeo_x"], romeo["romeo_tp1"])
    (cartella / "capo.json").write_text(json.dumps(capo.come_dati()), encoding="utf-8")
    np.savez_compressed(cartella / "storico.npz", x=t.x, tp1=t.tp1, tp2=t.tp2, erre=t.erre, quando=t.chiusa,
                        kelly_f=kelly_f, kelly_r=kelly_r, k_entrata=op.entrata, k_chiusa=op.chiusa,
                        k_strumento=op.strumento, k_verso=op.verso, **romeo)
    print(f"Capo allenato su {len(t)} operazioni; il Rischio usa {parte:.2f} del Kelly "
          f"(imparato su {len(kelly_f)} puntate 2008-2023). Somiglianza a Romeo imparata su "
          f"{len(romeo['romeo_y'])} candidati del 2023, {int(romeo['romeo_y'].sum())} le sue scelte; "
          f"fiducia in Romeo imparata dai risultati {capo.fiducia_in_romeo:+.3f}. "
          f"Salvati in {cartella}")


def stime_del_capo(t: Tabella) -> tuple[np.ndarray, np.ndarray]:
    """Per ogni operazione del 2008-2023: la puntata di Kelly piena e la scelta del Capo,
    allenato ogni anno solo sugli anni prima. Fuori da quegli anni: zero e no."""
    anni = t.anno
    k, entra = np.zeros(len(t)), np.zeros(len(t), bool)
    for a in range(PRIMO_GIUDICATO, AL + 1):
        oggi = np.flatnonzero(anni == a)
        if not len(oggi):
            continue
        passato = t.chiusa < _istante(a)
        c = Capo.allena(t.x[passato], t.tp1[passato], t.tp2[passato], pesi=pesi_per_eta(t.chiusa[passato], _istante(a)))
        p1, q = c.probabilita(t.x[oggi])
        entra[oggi] = c.entra(t.x[oggi], t.rr1[oggi], t.rr2[oggi], t.costi[oggi])
        k[oggi] = [kelly(esiti(p1[j], q[j], t.rr1[i], t.rr2[i], t.costi[i])) for j, i in enumerate(oggi)]
    return k, entra


def operazioni_del_capo(t: Tabella) -> Operazioni:
    """Le operazioni che il Capo avrebbe preso nel 2008-2023, ogni anno allenato solo sugli anni
    prima, con la sua puntata di Kelly piena e il risultato vero."""
    anni = t.anno
    scelte, f = [], []
    for a in range(PRIMO_GIUDICATO, AL + 1):
        oggi = np.flatnonzero(anni == a)
        if not len(oggi):
            continue
        passato = t.chiusa < _istante(a)
        c = Capo.allena(t.x[passato], t.tp1[passato], t.tp2[passato], pesi=pesi_per_eta(t.chiusa[passato], _istante(a)))
        p1, q = c.probabilita(t.x[oggi])
        prese = c.entra(t.x[oggi], t.rr1[oggi], t.rr2[oggi], t.costi[oggi])
        for k in np.flatnonzero(prese):
            i = oggi[k]
            scelte.append(i)
            f.append(kelly(esiti(p1[k], q[k], t.rr1[i], t.rr2[i], t.costi[i])))
    i = np.array(scelte, int)
    return Operazioni(t.quando[i], t.chiusa[i], t.strumento[i], t.verso[i], np.array(f), t.erre[i])


def impara_il_conto(op: Operazioni, dire=print) -> dict:
    """Il Rischio sul conto intero (`nvm/agenti/portafoglio.py`): la fiducia minima per metterci
    soldi, la parte del Kelly e se guardare le operazioni legate, scelte simulando il conto con
    tutte le operazioni dei vent'anni, aperte insieme, anche nelle storie sfortunate. Scrive il
    confronto col modo di prima (ogni operazione come se fosse sola)."""
    corr = portafoglio.correlazioni(op)
    s = portafoglio.scegli(op, corr)
    vecchia = impara_parte(op.kelly, op.erre)
    prima = portafoglio.simula(op, vecchia, None)

    def riga(nome, c):
        return (f"  {nome}: {c.prese} operazioni, crescita {np.expm1(c.crescita):+.1%} l'anno, calo peggiore "
                f"{c.peggior_calo:.0%}, giornata peggiore {-c.peggior_giorno:+.1%}, al massimo "
                f"{c.massimo_a_rischio:.0%} del conto a rischio insieme")
    dire("Il conto intero 2008-2023, con le operazioni aperte insieme:")
    dire(riga(f"prima (parte {vecchia:.2f} del Kelly, ognuna da sola)", prima))
    dire(riga(f"adesso (fiducia minima {s.minimo:g}, parte {s.parte:g}"
              f"{', con le legate' if s.correlazioni else ''})", s.conto))
    dire(f"  nelle storie sfortunate (anni rimescolati, il 10% peggiore): calo {s.calo_sfortunato:.0%}, crescita "
         f"{np.expm1(s.crescita_sfortunata):+.1%} l'anno; profilo: calo massimo {portafoglio.CALO_MASSIMO:.0%}")
    dire("  quanto vanno insieme, per quello che hanno in comune: "
         + ", ".join(f"{c:+g} → {r:+.2f}" for c, r in corr.items()))
    return portafoglio.come_dati(s, corr, prima=(vecchia, prima))


def candidati_di_romeo(radice: Path = RADICE / "dati" / "grezzi") -> dict[str, np.ndarray]:
    """I candidati del periodo di studio per la somiglianza a Romeo (`spec/capo.md`):
    le operazioni del 2023 delle coppie del bot dal vivo, e quali sono le sue scelte."""
    entrate = [e for e in leggi(RADICE / "casi" / "entrate-romeo.csv")
               if e.periodo == "studio" and e.strumento in BASE]
    xs, ys, tp1 = [], [], []
    for strumento in BASE:
        ore, _ = carica_ore(radice, strumento, _istante(2021), _istante(2024) + 60 * 86400)
        minuti = carica_periodo(radice / "minuti", strumento, _istante(2023), _istante(2024))
        ops, x = candidati(ore, minuti, _istante(2023), _istante(2024))
        xs.append(x)
        ys.append(etichette([e for e in entrate if e.strumento == strumento], ops))
        tp1 += [o.tp1_preso or o.uscita is Uscita.TARGET for o in ops]
    return {"romeo_x": np.vstack(xs), "romeo_y": np.concatenate(ys), "romeo_tp1": np.array(tp1, bool)}


def _giudicati(t: Tabella) -> np.ndarray:
    anni = t.anno
    return (anni >= PRIMO_GIUDICATO) & (anni <= AL)


if __name__ == "__main__":
    main()
