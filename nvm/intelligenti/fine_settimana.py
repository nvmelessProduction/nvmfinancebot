"""Il sabato e la domenica di Romeo (CRTology episode 1, V14; `documenti/spec/metodo_romeo.md` 10).

- **Sabato**, sugli strumenti che abbiamo operato: il giorno e l'ora esatta del massimo e del minimo
  della settimana, la forma della candela settimanale, il key level che l'ha fatta girare, gli errori di
  esecuzione, e se la previsione di domenica era giusta.
- **Domenica**: com'e' andata la settimana rispetto a quella prima, i massimi e i minimi da portare
  avanti (sono i pool di liquidita' della settimana nuova) e la previsione della prossima candela
  settimanale, con le regole della candela di Romeo (V1 35:12).

Solo candele gia' chiuse. I messaggi sono in parole semplici.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from nvm.agenti.conferme import Bias, bias
from nvm.dati.candele import costruisci
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import NEW_YORK, TF

GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
# Se nessuna operazione in settimana: gli strumenti da guardare comunque.
DI_BASE = ("EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "NAS100")
MASSIMI_STRUMENTI = 8


def _ny(t: int) -> datetime:
    return datetime.fromtimestamp(int(t), tz=NEW_YORK)


def _prezzo(x: float) -> str:
    cifre = 2 if x >= 100 else 5 if x < 20 else 3
    return f"{x:.{cifre}f}".replace(".", ",")


def forma(c: np.ndarray, prima: Optional[np.ndarray] = None) -> str:
    """La forma della candela settimanale, fra le sei di Romeo (V14 07:05)."""
    o, h, l, cl = (float(c[k]) for k in (APERTURA, MASSIMO, MINIMO, CHIUSURA))
    r = h - l
    if r <= 0:
        return "piatta"
    if prima is not None and h <= float(prima[MASSIMO]) and l >= float(prima[MINIMO]):
        return "interna (dentro quella di prima)"
    corpo = abs(cl - o) / r
    sotto = (min(o, cl) - l) / r
    sopra = (h - max(o, cl)) / r
    if corpo >= 0.6:
        return "piena rialzista" if cl > o else "piena ribassista"
    if sotto >= 0.5 and sotto >= 2 * sopra:
        return "giù e poi su (ombra lunga sotto)"
    if sopra >= 0.5 and sopra >= 2 * sotto:
        return "su e poi giù (ombra lunga sopra)"
    return "indecisa"


def _settimana(ore, adesso: int):
    """L'ultima settimana chiusa: la candela, quella prima, e le orarie dentro."""
    sett = costruisci(ore, TF.W1).chiuse_entro(adesso)
    if len(sett) < 2:
        return None
    oo = costruisci(ore, TF.H1).chiuse_entro(adesso)
    a, b = np.searchsorted(oo.inizio, [sett.inizio[-1], sett.fine[-1]])
    if b <= a:
        return None
    return sett, oo.inizio[a:b], oo.bid[a:b]


def _key_level(sett, alto: bool) -> str:
    """Il livello che ha fatto girare la settimana: un massimo (o minimo) di una settimana prima, non
    ancora ripreso, superato di poco dall'estremo."""
    n = len(sett)
    estremo = float(sett.bid[-1, MASSIMO] if alto else sett.bid[-1, MINIMO])
    ampiezza = float(sett.bid[-1, MASSIMO] - sett.bid[-1, MINIMO])
    for j in range(n - 2, max(n - 14, -1), -1):
        livello = float(sett.bid[j, MASSIMO] if alto else sett.bid[j, MINIMO])
        dopo = sett.bid[j + 1:n - 1]
        ripreso = len(dopo) and (dopo[:, MASSIMO].max() > livello if alto else dopo[:, MINIMO].min() < livello)
        if ripreso:
            continue
        oltre = (estremo - livello) if alto else (livello - estremo)
        if 0 <= oltre <= 0.35 * ampiezza:
            quando = _ny(int(sett.inizio[j]))
            return (f"ha preso il {'massimo' if alto else 'minimo'} della settimana del {quando:%d/%m} e si è girata: "
                    "era il key level")
    return f"il {'massimo' if alto else 'minimo'} non ha preso nessun livello di una settimana prima"


def sabato(ore_per: dict, adesso: int, operazioni: list, previsioni: Optional[dict] = None) -> str:
    """La revisione del sabato. `operazioni`: quelle prese in settimana, (strumento, verso, R, rischio sul
    conto o None). `previsioni`: quelle di domenica scorsa, per strumento."""
    previsioni = previsioni or {}
    strumenti = list(dict.fromkeys([o[0] for o in operazioni if o[0] in ore_per]))
    if not strumenti:
        strumenti = [s for s in DI_BASE if s in ore_per]
    righe = ["📘 Il sabato di Romeo: rivediamo la settimana."]
    for s in strumenti[:MASSIMI_STRUMENTI]:
        w = _settimana(ore_per[s], adesso)
        if w is None:
            continue
        sett, tempi, bid = w
        c, prima = sett.bid[-1], sett.bid[-2]
        i_alto, i_basso = int(np.argmax(bid[:, MASSIMO])), int(np.argmin(bid[:, MINIMO]))
        t_alto, t_basso = _ny(int(tempi[i_alto])), _ny(int(tempi[i_basso]))
        f = forma(c, prima)
        righe.append(f"• {s}: candela {f}. Massimo {_prezzo(float(c[MASSIMO]))} {GIORNI[t_alto.weekday()]} alle "
                     f"{t_alto:%H}:00, minimo {_prezzo(float(c[MINIMO]))} {GIORNI[t_basso.weekday()]} alle "
                     f"{t_basso:%H}:00 (ora di New York).")
        # L'estremo fatto per primo e' la manipolazione: quello e' da spiegare col key level.
        primo_alto = tempi[i_alto] < tempi[i_basso]
        righe.append(f"  Il {'massimo' if primo_alto else 'minimo'} è venuto prima: {_key_level(sett, primo_alto)}.")
        p = previsioni.get(s)
        if p:
            su = float(c[CHIUSURA]) > float(prima[MASSIMO]) or float(c[MINIMO]) < float(prima[MINIMO]) <= float(c[CHIUSURA])
            giu = float(c[CHIUSURA]) < float(prima[MINIMO]) or float(c[MASSIMO]) > float(prima[MASSIMO]) >= float(c[CHIUSURA])
            reale = "rialzista" if su and not giu else "ribassista" if giu and not su else "senza direzione"
            giusta = p == reale or (p == "senza direzione" and reale == "senza direzione")
            righe.append(f"  Domenica avevamo previsto una settimana {p}: è stata {reale}. "
                         + ("Previsione giusta." if giusta else "Previsione sbagliata: lo segniamo nel diario."))
    n = len(operazioni)
    righe.append("Gli errori di esecuzione (V14):")
    if not n:
        righe.append("• nessuna operazione: il setup completo di Romeo non si è presentato. Nessun errore.")
    else:
        vinte = sum(1 for o in operazioni if o[2] > 0.05)
        totale = sum(o[2] for o in operazioni)
        rischi = [o[3] for o in operazioni if o[3]]
        righe.append(f"• {n} operazion{'e' if n == 1 else 'i'}, tutte col setup completo: {vinte} andat"
                     f"{'a' if vinte == 1 else 'e'} bene, in tutto {totale:+.1f} volte il rischio.".replace(".", ",", 1))
        if rischi:
            righe.append(f"• la puntata più alta è stata {max(rischi):.2%} del conto".replace(".", ",")
                         + (": attenti a non esagerare." if max(rischi) > 0.03 else ": nessuna leva eccessiva."))
        righe.append("• nessuna operazione per noia: entriamo solo quando c'è il setup.")
    return "\n".join(righe)


def previsione(ore, adesso: int) -> Optional[tuple[str, float, float, str]]:
    """La previsione della prossima settimana (V14 24:04): (direzione, massimo e minimo della settimana
    passata da portare avanti, perche')."""
    w = _settimana(ore, adesso)
    if w is None:
        return None
    sett = w[0]
    prima, ultima = sett.bid[-2], sett.bid[-1]
    b = bias(prima, ultima)
    alto, basso = float(ultima[MASSIMO]), float(ultima[MINIMO])
    cl = float(ultima[CHIUSURA])
    if cl > float(prima[MASSIMO]):
        perche = "ha chiuso sopra il massimo della settimana prima"
    elif cl < float(prima[MINIMO]):
        perche = "ha chiuso sotto il minimo della settimana prima"
    elif alto > float(prima[MASSIMO]):
        perche = "è andata sopra il massimo della settimana prima e ha richiuso dentro (ombra sopra)"
    elif basso < float(prima[MINIMO]):
        perche = "è andata sotto il minimo della settimana prima e ha richiuso dentro (ombra sotto)"
    else:
        perche = "è rimasta dentro la settimana prima"
    direzione = {Bias.RIALZISTA: "rialzista", Bias.RIBASSISTA: "ribassista"}.get(b, "senza direzione")
    return direzione, alto, basso, perche


def domenica(ore_per: dict, adesso: int, strumenti: list) -> tuple[str, dict]:
    """Il messaggio della domenica e le previsioni per strumento (da controllare sabato prossimo)."""
    scelti = [s for s in dict.fromkeys(list(strumenti) + list(DI_BASE)) if s in ore_per][:MASSIMI_STRUMENTI]
    righe = ["🗓️ La domenica di Romeo: prepariamo la settimana. Segniamo il lunedì e portiamo avanti massimi "
             "e minimi della settimana passata: sono gli ordini che il mercato andrà a cercare."]
    previsioni = {}
    for s in scelti:
        p = previsione(ore_per[s], adesso)
        if p is None:
            continue
        direzione, alto, basso, perche = p
        previsioni[s] = direzione
        attesa = {"rialzista": "ci aspettiamo prezzi più alti", "ribassista": "ci aspettiamo prezzi più bassi"}.get(
            direzione, "nessuna direzione chiara: guardiamo come reagisce ai livelli")
        righe.append(f"• {s}: la settimana {perche}: {attesa}. Livelli da guardare: massimo {_prezzo(alto)}, "
                     f"minimo {_prezzo(basso)}.")
    return "\n".join(righe), previsioni
