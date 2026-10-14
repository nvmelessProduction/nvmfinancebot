"""La mappa di Nameless (fase 2b): i livelli e i gap che un trader segna sul grafico, a ogni ora.

Nella fase 2 la rete ha imparato CRT, key level e candele, ma non la direzione ne' il target finale: dipendono da gap e
livelli di mesi e anni prima, toccati o no ora per ora, che nelle sue 40 candele per timeframe non vede. Qui glieli si
da' come sensi, come le linee che il proprietario disegna su TradingView: non sono le decisioni delle regole (quelle
le deve imparare la rete), sono i fatti del grafico. A ogni ora `j` (cioe' a `prossimo[j]`, come gli occhi):

- **i key level** (`foto.livelli_prima`): massimo e minimo dell'ultimo giorno, settimana, mese, 3 e 12 mesi chiusi,
  e se il prezzo li ha gia' presi dopo la fine del periodo;
- **le accettazioni** (`foto.accettazione`) di giorno, settimana, mese, 3 e 12 mesi: il verso, il livello, se e'
  gia' preso;
- **i gap** (`foto.gap_di`, `foto.fase`) di giorno, settimana, mese, 3, 6 e 12 mesi, nella finestra delle regole
  (`foto.GAP_INDIETRO`): per lato (rialzisti sotto, ribassisti sopra) il piu' vicino intatto la cui terza candela ha
  accettato (un muro) e il piu' vicino intatto che no (un target), e il piu' vicino toccato e non ancora riempito,
  con la sua fase (aggressione, reazione automatica, liquidazione) e l'estremo dell'aggressione.

Le tavole (`tavole`) si fanno una volta per pezzo di mercato, col processore; a ogni gruppo di ore la scheda grafica
ne legge quello che vale in quel momento (`Lettore.mappa` in `nvm/nameless/occhi.py`). Ogni elemento della mappa e'
un gettone di 6 numeri (`CAMPI`): due prezzi (in scala, come le candele), tre segni, e se c'e'.
"""

from __future__ import annotations

import numpy as np

from nvm.agenti import foto
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO, Minuti
from nvm.tempo import TF

TF_KL = foto.TF_KL                       # D1, W1, MN, 3M, 12M
TF_ACCETTA = foto.TF_ACCETTA             # D1, W1, MN, 3M, 12M
TF_GAP = foto.TF_GAP                     # D1, W1, MN, 3M, 6M, 12M
MAI = np.iinfo(np.int64).max
CAMPI = 6
# I gettoni della mappa, nell'ordine.
ELEMENTI = tuple([f"{tf.value} {lato}" for tf in TF_KL for lato in ("massimo", "minimo")] +
                 [f"accettazione {tf.value}" for tf in TF_ACCETTA] +
                 [f"gap {tf.value} {quale}" for tf in TF_GAP for quale in
                  ("rialzista muro", "rialzista target", "ribassista muro", "ribassista target", "rialzista toccato",
                   "ribassista toccato")])


def _primo_oltre(valori: np.ndarray, da: np.ndarray, soglie: np.ndarray, come: str) -> np.ndarray:
    """Per ogni coppia (da, soglia), il primo indice >= da col valore oltre la soglia (`come`: ">", ">=", "<", "<=");
    MAI se mai. Gli stessi confronti delle regole delle foto."""
    fuori = np.full(len(da), MAI, np.int64)
    confronto = {">": np.greater, ">=": np.greater_equal, "<": np.less, "<=": np.less_equal}[come]
    for n, (a, s) in enumerate(zip(da.tolist(), soglie.tolist())):
        oltre = confronto(valori[a:], s)
        if len(oltre) and oltre.any():
            fuori[n] = a + int(np.argmax(oltre))
    return fuori


def _ore_da(prossimo: np.ndarray, istanti: np.ndarray) -> np.ndarray:
    """La prima ora a cui l'istante e' gia' passato (prossimo >= istante); MAI per gli istanti MAI."""
    fuori = np.searchsorted(prossimo, np.minimum(istanti, np.iinfo(np.int64).max - 1), side="left").astype(np.int64)
    return np.where((istanti == MAI) | (fuori >= len(prossimo)), MAI, fuori)


def tavole(ore: Minuti) -> dict:
    """Le tavole della mappa di un pezzo di mercato. Gli orari di TradingView (`candele.SESSIONI`) vanno messi prima.
    Indici delle ore e delle candele locali al pezzo (nell'ordine dei sensi: `sensi.candele_di`)."""
    q = foto.Quadro.da(ore, int(ore.t[-1]) + 3600)
    h1 = q.ore
    prossimo = np.maximum(np.r_[h1.inizio[1:], h1.fine[-1:]], h1.fine).astype(np.int64)
    alti, bassi = h1.bid[:, MASSIMO], h1.bid[:, MINIMO]
    fuori = {"ore": len(h1)}
    # I key level: da quale ora il prezzo ha preso il massimo (il minimo) di ogni candela, dopo la sua fine.
    for tf in TF_KL:
        c = q.candele[tf]
        da = np.searchsorted(h1.inizio, c.fine).astype(np.int64)
        fuori[f"kl {tf.value}"] = {
            "fine": c.fine.astype(np.int64),
            "preso alto": _primo_oltre(alti, da, c.bid[:, MASSIMO], ">"),
            "preso basso": _primo_oltre(bassi, da, c.bid[:, MINIMO], "<")}
    # Le accettazioni: per ogni candela (quando e' l'ultima chiusa) il verso, il livello e da quale ora e' preso.
    for tf in TF_ACCETTA:
        c = q.candele[tf]
        n = len(c)
        verso, livello, preso = np.zeros(n, np.int8), np.zeros(n), np.full(n, MAI, np.int64)
        for k in range(n):
            j, dentro = k, 0
            while j >= 1 and dentro <= 3:
                p, x = c.bid[j - 1], c.bid[j]
                if x[CHIUSURA] > p[MASSIMO]:
                    verso[k], livello[k] = 1, x[MASSIMO]
                    break
                if x[CHIUSURA] < p[MINIMO]:
                    verso[k], livello[k] = -1, x[MINIMO]
                    break
                if not (x[MASSIMO] <= p[MASSIMO] and x[MINIMO] >= p[MINIMO]):
                    break
                j, dentro = j - 1, dentro + 1
            if verso[k]:
                a = int(np.searchsorted(h1.inizio, int(c.fine[j])))
                preso[k] = _primo_oltre(alti if verso[k] > 0 else bassi, np.array([a]), np.array([livello[k]]),
                                        ">" if verso[k] > 0 else "<")[0]
        fuori[f"accettazione {tf.value}"] = {"fine": c.fine.astype(np.int64), "verso": verso, "livello": livello,
                                             "preso": preso}
    # I gap: tutti, con quando entrano e escono dalla finestra delle regole, quando sono toccati e riempiti, le fasi.
    for tf in TF_GAP:
        c = q.candele[tf]
        w = foto.GAP_INDIETRO.get(tf, 100)
        h, l = c.bid[:, MASSIMO], c.bid[:, MINIMO]
        fase_c = q.candele[foto.TF_FASE.get(tf, TF.H1)]
        righe = []
        for i in range(2, len(c)):
            chiude, apre = float(c.bid[i, CHIUSURA]), float(c.bid[i, APERTURA])
            diretta = abs(chiude - apre) >= foto.CORPO_ACCETTA * (h[i] - l[i])
            if h[i - 2] < l[i]:
                rialzista, basso, alto = True, float(h[i - 2]), float(l[i])
                accetta = chiude > h[i - 1] and chiude > apre and diretta
            elif l[i - 2] > h[i]:
                rialzista, basso, alto = False, float(h[i]), float(l[i - 2])
                accetta = chiude < l[i - 1] and chiude < apre and diretta
            else:
                continue
            a = int(np.searchsorted(h1.inizio, int(c.fine[i])))
            if rialzista:
                tocco = _primo_oltre(bassi, np.array([a]), np.array([alto]), "<=")[0]
                pieno = _primo_oltre(bassi, np.array([a]), np.array([basso]), "<")[0]
            else:
                tocco = _primo_oltre(alti, np.array([a]), np.array([basso]), ">=")[0]
                pieno = _primo_oltre(alti, np.array([a]), np.array([alto]), ">")[0]
            reazione = liquidazione = MAI
            estremo = np.nan
            if tocco != MAI:
                # Le fasi (`foto.fase`) sulle candele del suo timeframe di fase, dalla candela del primo tocco.
                f0 = int(np.searchsorted(fase_c.fine, int(h1.inizio[tocco]), side="right"))
                segno = 1.0 if rialzista else -1.0
                b = fase_c.bid[f0:, MINIMO] if rialzista else -fase_c.bid[f0:, MASSIMO]
                al = fase_c.bid[f0:, MASSIMO] if rialzista else -fase_c.bid[f0:, MINIMO]
                ch = fase_c.bid[f0:, CHIUSURA] * segno
                k_min, r = 0, None
                for jj in range(len(b)):
                    if b[jj] <= b[k_min]:
                        k_min = jj
                    elif ch[jj] > al[k_min]:
                        r = jj
                        break
                if r is not None:
                    reazione = int(fase_c.fine[f0 + r])
                    estremo = float(b[k_min] * segno)
                    dopo = np.flatnonzero(b[r + 1:] < b[k_min])
                    if len(dopo):
                        liquidazione = int(fase_c.fine[f0 + r + 1 + dopo[0]])
            scade = int(c.fine[i + w]) if i + w < len(c) else MAI
            righe.append((int(c.fine[i]), scade, rialzista, basso, alto, accetta, tocco, pieno, reazione,
                          liquidazione, estremo))
        if righe:
            nato, scade, rialzista, basso, alto, accetta, tocco, pieno, reazione, liquidazione, estremo = \
                (np.array(v) for v in zip(*righe))
        else:
            nato = scade = tocco = pieno = reazione = liquidazione = np.zeros(0, np.int64)
            rialzista = accetta = np.zeros(0, bool)
            basso = alto = estremo = np.zeros(0)
        fuori[f"gap {tf.value}"] = {
            "nato": _ore_da(prossimo, nato.astype(np.int64)), "scade": _ore_da(prossimo, scade.astype(np.int64)),
            "rialzista": rialzista.astype(bool), "basso": basso.astype(np.float64), "alto": alto.astype(np.float64),
            "accetta": accetta.astype(bool), "tocco": tocco.astype(np.int64), "pieno": pieno.astype(np.int64),
            "reazione": _ore_da(prossimo, reazione.astype(np.int64)),
            "liquidazione": _ore_da(prossimo, liquidazione.astype(np.int64)), "estremo": estremo.astype(np.float64)}
    return fuori
