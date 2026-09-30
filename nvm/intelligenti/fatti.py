"""I fatti di un'occasione, come li guarda Romeo: quello che gli agenti percepiscono dal mercato.

Ogni fatto e' una domanda della bibbia (`bibbia.md`) con la sua risposta, calcolata solo con le
candele gia' chiuse al momento della decisione: in che candela siamo, se la candela 2 ha chiuso
dentro, quanto e' spessa la candela del turtle soup, se c'e' un key level, se sotto c'e' ancora un
livello non toccato, l'ora, il giorno, il bias, i grafici grandi, i vuoti. Una parte viene dalle viste
degli agenti (`nvm/cervello/viste.py`, gli stessi occhi di sempre), il resto dalle candele.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import SOPRA, Bias
from nvm.dati.candele import Candele, costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import NEW_YORK, TF

GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")


def _vista(d, agente: str, i: int, altrimenti: float = 0.0) -> float:
    v = (getattr(d, "viste", None) or {}).get(agente)
    if v is None or i >= len(v):
        return altrimenti
    x = float(np.asarray(v, float).ravel()[i])
    return x if np.isfinite(x) else altrimenti


def _intatti(sopra: Candele, fino: int, verso_basso: bool) -> np.ndarray:
    """I minimi (o massimi) delle ultime 30 candele del grafico sopra mai ripresi dalle candele dopo."""
    b = sopra.bid[max(0, len(sopra) - 30):]
    fuori = []
    for j in range(len(b)):
        dopo = b[j + 1:]
        if verso_basso:
            if not len(dopo) or dopo[:, MINIMO].min() > b[j, MINIMO]:
                fuori.append(b[j, MINIMO])
        else:
            if not len(dopo) or dopo[:, MASSIMO].max() < b[j, MASSIMO]:
                fuori.append(b[j, MASSIMO])
    return np.array(fuori, float)


def fatti(d, ore, quarti=None) -> dict:
    """I fatti dell'occasione `d` (una `giro.Decisione`), con le ore dello strumento (e i 15 minuti
    per la coppia 4 ore -> 15 minuti). Un dizionario nome -> valore (numeri, vero/falso, testo)."""
    r, op = d.r, d.op
    s = r.scatto
    crt = s.crt
    q = int(r.quando)
    short = r.verso is Verso.SHORT
    segno = -1 if short else 1
    amp = crt.crt_high - crt.crt_low
    base = quarti if (r.basso_tf is TF.M15 and quarti is not None) else ore
    alte = costruisci(base, r.alto_tf).chiuse_entro(q)
    sopra = costruisci(ore, SOPRA[r.alto_tf]).chiuse_entro(q)
    estremo = float(crt.estremo_a(q))
    lato = crt.crt_high if short else crt.crt_low
    f: dict = {"strumento": r.strumento, "verso": "vendita" if short else "acquisto", "colpo": r.colpo,
               "coppia": f"{r.alto_tf.value}-{r.basso_tf.value}"}

    # Il CRT: in che candela siamo, e com'e' andata la candela 2.
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    dopo = int((alte.inizio > crt.range_inizio).sum())
    f["candela"] = 2 if dopo == 0 else dopo + 2
    f["candela 2 chiusa dentro"] = None
    if dopo >= 1 and k + 1 < len(alte):
        c2 = alte.bid[k + 1]
        f["candela 2 chiusa dentro"] = bool(crt.crt_low < c2[CHIUSURA] < crt.crt_high)
    f["candele interne"] = int(round(np.expm1(_vista(d, "Cacciatore", 29))))
    # Il corpo della candela 1 nel verso dell'operazione (negativo: la candela 1 andava contro, verso il key level).
    f["corpo della candela 1"] = _vista(d, "Cacciatore", 6)
    f["dentro un CRT più grande"] = bool(getattr(getattr(d, "alla_romeo", None), "annidato", False))

    # L'entrata sulle candele piccole.
    f["profondità della manipolazione"] = abs(estremo - lato) / amp if amp > 0 else 0.0
    f["spessore del turtle soup"] = float(np.expm1(_vista(d, "Grilletto", 59)))
    f["fvg col Model#1"] = _vista(d, "Grilletto", 60) > 0
    f["vera rottura di struttura"] = _vista(d, "Grilletto", 63) > 0
    f["dalla parte giusta dell'apertura"] = None
    if f["candela"] >= 3:
        # Per comprare sotto l'apertura della candela in corso, per vendere sopra (bibbia 3).
        f["dalla parte giusta dell'apertura"] = _vista(d, "Grilletto", 58) < 0
    f["smt col gemello"] = _vista(d, "Grilletto", 61) > 0
    f["manipolazione a fine candela"] = _vista(d, "Grilletto", 65, 0.5) >= 0.8 and _vista(d, "Grilletto", 66) > 0
    li = getattr(d, "liquidita", None)
    f["liquidità presa prima"] = bool(li.presa) if li is not None else False

    # Stop e obiettivi.
    f["rr1"] = abs(op.tp1 - op.ingresso) / op.rischio
    f["rr2"] = abs(op.tp2 - op.ingresso) / op.rischio
    f["costi in R"] = float(r.costo_erre)

    # Il key level del grafico sopra.
    kl = getattr(d, "key_level", None)
    f["key level"] = bool(kl is not None and (kl.massimo or kl.rejection_block or kl.fvg))
    f["tipo di key level"] = ", ".join(n for n, x in (("vecchio massimo/minimo preso", getattr(kl, "massimo", False)),
                                                        ("rejection block", getattr(kl, "rejection_block", False)),
                                                        ("FVG", getattr(kl, "fvg", False))) if x) or "nessuno"
    f["si ferma sul livello"] = bool(getattr(kl, "tocca", False))
    # Un livello del grafico sopra ancora intatto oltre l'estremo, entro un'ampiezza: il fondo finto (bibbia 7).
    oltre = _intatti(sopra, q, verso_basso=not short)
    oltre = oltre[(segno * (estremo - oltre) > 0) & (np.abs(estremo - oltre) <= amp)] if len(oltre) else oltre
    f["livello intatto oltre l'estremo"] = float(oltre[np.argmin(np.abs(estremo - oltre))]) if len(oltre) else None
    # Un livello intatto fra l'ingresso e il primo obiettivo: puo' bloccare l'obiettivo (MOB, bibbia 7).
    davanti = _intatti(sopra, q, verso_basso=short)
    davanti = davanti[(segno * (davanti - op.ingresso) > 0) & (segno * (op.tp1 - davanti) > 0)] if len(davanti) else davanti
    f["livello intatto prima del 50%"] = float(davanti[0]) if len(davanti) else None
    # L'apertura dell'ultima candela contraria del grafico sopra: supporto (o resistenza) vero (bibbia 7).
    f["apertura della candela contraria toccata"] = False
    for j in range(len(sopra) - 1, max(len(sopra) - 20, -1), -1):
        o, c = float(sopra.bid[j, APERTURA]), float(sopra.bid[j, CHIUSURA])
        if (not short and c < o) or (short and c > o):
            # Arrivata (entro un decimo del range) o appena oltre (meno di mezzo range), non sfondata.
            oltre_o = segno * (o - estremo)
            f["apertura della candela contraria toccata"] = bool(-0.1 * amp <= oltre_o <= 0.5 * amp)
            break

    # Il tempo.
    ny = datetime.fromtimestamp(q, tz=NEW_YORK)
    m_ny = datetime.fromtimestamp(int(crt.manipolazione_inizio), tz=NEW_YORK)
    ar = getattr(d, "alla_romeo", None)
    f["ore di Londra"] = bool(getattr(ar, "londra", False))
    f["ore di New York"] = bool(getattr(ar, "new_york", False))
    f["golden candle time"] = 9 <= ny.hour < 13
    f["giorno"] = GIORNI[ny.weekday()]
    f["ora di New York"] = f"{ny:%H:%M}"
    f["ora della manipolazione"] = f"{GIORNI[m_ny.weekday()]} {m_ny:%H:%M}"
    f["posizione nella settimana"] = _vista(d, "Orario", 10, 0.5)
    f["estremo della settimana fra lunedì e mercoledì"] = None
    sett = costruisci(ore, TF.W1).chiuse_entro(q)
    if len(sett):
        oo = costruisci(ore, TF.H1).chiuse_entro(q)
        cor = oo.bid[int(np.searchsorted(oo.inizio, sett.fine[-1])):]
        if len(cor):
            i_estremo = int(np.argmax(cor[:, MASSIMO])) if short else int(np.argmin(cor[:, MINIMO]))
            t_e = oo.inizio[int(np.searchsorted(oo.inizio, sett.fine[-1])) + i_estremo]
            giorno_e = datetime.fromtimestamp(int(t_e), tz=NEW_YORK).weekday()
            # L'estremo della settimana e' quello della manipolazione? E in che giorno.
            e_sett = float(cor[i_estremo, MASSIMO] if short else cor[i_estremo, MINIMO])
            f["estremo della settimana fra lunedì e mercoledì"] = (abs(e_sett - estremo) <= 0.05 * amp and giorno_e in (0, 1, 2, 6))

    # Il bias.
    c = getattr(d, "contesto", None)
    def dalla_parte(b):
        if b is None or b is Bias.NEUTRO:
            return None
        return (b is Bias.RIBASSISTA) == short
    f["bias dalla candela del range"] = dalla_parte(getattr(c, "range", None))
    f["bias dal grafico sopra"] = dalla_parte(getattr(c, "sopra", None))
    f["CRT grandi nello stesso verso"] = int(round(_vista(d, "Bias", 14)))
    f["CRT grandi contro"] = int(round(_vista(d, "Bias", 15)))
    f["a sconto nella settimana"] = getattr(ar, "sconto", None)

    # I grafici grandi: 4 ore, giorno, settimana, mese.
    sg = getattr(d, "sguardo", None)
    lati = tuple(getattr(sg, "lati", ()) or ())
    f["timeframe grandi a favore"] = sum(1 for x in lati if x is True)
    f["timeframe grandi contro"] = sum(1 for x in lati if x is False)
    f["settimana e mese"] = tuple(lati[2:4]) if len(lati) >= 4 else (None, None)

    # I vuoti.
    f["FVG davanti"] = any(_vista(d, "Gap", 4 * t) > 0 for t in range(4))
    dietro = [(_vista(d, "Gap", 4 * t + 3)) for t in range(4) if _vista(d, "Gap", 4 * t + 2) > 0]
    f["FVG alle spalle vicino"] = bool(dietro) and min(dietro) <= 0.5
    w = _vista(d, "Gap", 16)
    f["gap del weekend"] = None if w == 0 else w > 0
    return f
