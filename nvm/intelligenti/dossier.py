"""Il dossier di un'occasione: tutto quello che la squadra vede, scritto come lo leggerebbe un trader.

Il cervello numerico vedeva numeri gia' misurati; un agente intelligente legge le candele vere
(apertura, massimo, minimo, chiusura, con data e ora di New York), i livelli, la settimana, il gemello
per l'SMT e i piani possibili, e ragiona da solo con la bibbia di Romeo. Solo candele gia' chiuse al
momento della decisione: il futuro non si guarda.
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

GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
NOMI_TF = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H4: "4 ore", TF.H1: "1 ora",
           TF.M15: "15 minuti"}
QUANTE_ALTE = 6
QUANTE_BASSE = 36
QUANTE_SOPRA = 10


def _ny(t: int) -> str:
    d = datetime.fromtimestamp(int(t), tz=NEW_YORK)
    return f"{GIORNI[d.weekday()]} {d:%d/%m/%Y %H:%M}"


def _cifre(strumento: str) -> int:
    try:
        from nvm.vivo.messaggi import CIFRE
        return int(CIFRE.get(strumento, 5))
    except Exception:
        return 5


def _tabella(c: Candele, n: int, cifre: int, titolo: str) -> str:
    b, ini = c.bid[-n:], c.inizio[-n:]
    if not len(b):
        return f"{titolo}: nessuna candela chiusa."
    righe = [f"{titolo} (apertura NY | apertura massimo minimo chiusura | colore):"]
    for t, (o, h, l, cl) in zip(ini, b):
        colore = "rialzista" if cl > o else ("ribassista" if cl < o else "doji")
        righe.append(f"  {_ny(t)} | {o:.{cifre}f} {h:.{cifre}f} {l:.{cifre}f} {cl:.{cifre}f} | {colore}")
    return "\n".join(righe)


def _bias(b) -> str:
    return {Bias.RIALZISTA: "rialzista", Bias.RIBASSISTA: "ribassista"}.get(b, "neutro")


def _favore(x: Optional[bool]) -> str:
    return "neutro" if x is None else ("a favore" if x else "contro")


def _livelli_liberi(sopra: Candele, prezzo: float, amp: float, cifre: int) -> str:
    """I massimi e minimi del grafico sopra (ultime 24 candele) mai ripresi dopo, entro 3 ampiezze del range."""
    b = sopra.bid[-24:]
    ini = sopra.inizio[-24:]
    alti, bassi = [], []
    for j in range(len(b)):
        dopo = b[j + 1:]
        if not len(dopo) or dopo[:, MASSIMO].max() < b[j, MASSIMO]:
            if abs(b[j, MASSIMO] - prezzo) <= 3 * amp:
                alti.append(f"{b[j, MASSIMO]:.{cifre}f} ({_ny(ini[j])[:14]})")
        if not len(dopo) or dopo[:, MINIMO].min() > b[j, MINIMO]:
            if abs(b[j, MINIMO] - prezzo) <= 3 * amp:
                bassi.append(f"{b[j, MINIMO]:.{cifre}f} ({_ny(ini[j])[:14]})")
    return (f"Massimi del grafico sopra ancora intatti vicino al prezzo: {', '.join(alti[-5:]) or 'nessuno'}.\n"
            f"Minimi del grafico sopra ancora intatti vicino al prezzo: {', '.join(bassi[-5:]) or 'nessuno'}.")


def _settimana(ore, quando: int, prezzo: float, cifre: int) -> str:
    sett = costruisci(ore, TF.W1).chiuse_entro(quando)
    ore = costruisci(ore, TF.H1).chiuse_entro(quando)
    if not len(sett):
        return "Settimana: dati insufficienti."
    inizio = int(sett.fine[-1])
    i = int(np.searchsorted(ore.inizio, inizio))
    j = int(np.searchsorted(ore.fine, quando, side="right"))
    cor = ore.bid[i:j]
    righe = [f"Settimana scorsa: massimo {sett.bid[-1, MASSIMO]:.{cifre}f}, minimo {sett.bid[-1, MINIMO]:.{cifre}f}, "
             f"apertura {sett.bid[-1, APERTURA]:.{cifre}f}, chiusura {sett.bid[-1, CHIUSURA]:.{cifre}f}."]
    if len(cor):
        k_alto, k_basso = int(np.argmax(cor[:, MASSIMO])), int(np.argmin(cor[:, MINIMO]))
        hi, lo = float(cor[k_alto, MASSIMO]), float(cor[k_basso, MINIMO])
        pos = (prezzo - lo) / (hi - lo) if hi > lo else 0.5
        parte = min(max((quando - inizio) / (5 * 86400), 0.0), 1.2)
        righe.append(f"Questa settimana finora: massimo {hi:.{cifre}f} ({_ny(ore.inizio[i + k_alto])}), minimo "
                     f"{lo:.{cifre}f} ({_ny(ore.inizio[i + k_basso])}); il prezzo è al {pos:.0%} del range della "
                     f"settimana (0% = minimo); è passato il {parte:.0%} della settimana.")
    return "\n".join(righe)


def dossier(d, ore, quarti=None, gemello=None, fiducia_numerica: Optional[float] = None) -> str:
    """Il dossier dell'occasione `d` (una `giro.Decisione`). `ore`: le ore dello strumento (Minuti);
    `quarti`: i 15 minuti, per la coppia 4 ore -> 15 minuti; `gemello`: (ore del gemello, +1/-1)."""
    r, op = d.r, d.op
    s = r.scatto
    crt = s.crt
    q = int(r.quando)
    cifre = _cifre(r.strumento)
    base_coppia = quarti if (r.basso_tf is TF.M15 and quarti is not None) else ore
    alte = costruisci(base_coppia, r.alto_tf).chiuse_entro(q)
    basse = costruisci(base_coppia, r.basso_tf).chiuse_entro(q)
    sopra = costruisci(ore, SOPRA[r.alto_tf]).chiuse_entro(q)
    orarie = costruisci(ore, TF.H1).chiuse_entro(q)
    short = r.verso is Verso.SHORT
    amp = crt.crt_high - crt.crt_low
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    dopo = int((alte.inizio > crt.range_inizio).sum())
    candela = "candela 2 (la manipolazione, ancora aperta)" if dopo == 0 else f"candela {dopo + 2} (la candela 2 ha chiuso)"
    chiusura_2 = ""
    if dopo >= 1:
        c2 = alte.bid[k + 1]
        dentro = crt.crt_low < c2[CHIUSURA] < crt.crt_high
        chiusura_2 = (f" La candela 2 ha chiuso a {c2[CHIUSURA]:.{cifre}f}: "
                      + ("dentro il range." if dentro else "FUORI dal range."))
    apertura_attuale = None
    if len(basse):
        j = int(np.searchsorted(basse.inizio, alte.fine[-1])) if len(alte) else 0
        if j < len(basse):
            apertura_attuale = float(basse.bid[j, APERTURA])
    estremo = crt.estremo_a(q)
    media_basse = float(np.mean(basse.bid[-20:, MASSIMO] - basse.bid[-20:, MINIMO])) if len(basse) else float("nan")
    spessore = (s.turtle_soup_massimo - s.turtle_soup_minimo) / media_basse if media_basse else float("nan")
    rr1 = abs(op.tp1 - op.ingresso) / op.rischio
    rr2 = abs(op.tp2 - op.ingresso) / op.rischio

    parti = [
        "=== OCCASIONE ===",
        f"Strumento {r.strumento}. CRT {NOMI_TF[r.alto_tf]} con entrata sul {NOMI_TF[r.basso_tf]}. "
        f"Verso proposto: {'VENDITA' if short else 'ACQUISTO'}. Tentativo numero {r.colpo} su questo CRT.",
        f"Ora della decisione: {_ny(q)} (New York).",
        f"Candela 1 (il range) aperta {_ny(crt.range_inizio)}: CRT high {crt.crt_high:.{cifre}f}, CRT low "
        f"{crt.crt_low:.{cifre}f}, 50% {crt.crt_50:.{cifre}f}, ampiezza {amp:.{cifre}f}.",
        f"Adesso siamo nella {candela}.{chiusura_2}"
        + (f" Apertura della candela grande in corso: {apertura_attuale:.{cifre}f}." if apertura_attuale is not None else ""),
        f"Manipolazione iniziata {_ny(crt.manipolazione_inizio)}; estremo raggiunto {estremo:.{cifre}f}"
        f" ({abs(estremo - (crt.crt_high if short else crt.crt_low)) / amp:.0%} del range oltre il lato).",
        f"Candela del turtle soup (aperta {_ny(s.turtle_soup_inizio)}): massimo {s.turtle_soup_massimo:.{cifre}f}, "
        f"minimo {s.turtle_soup_minimo:.{cifre}f}, spessa {spessore:.1f} volte la candela media.",
        f"Model#1: livello (apertura della candela del turtle soup) {s.livello:.{cifre}f}; la candela che ha "
        f"chiuso oltre il livello è chiusa {_ny(q)}.",
        f"Piano proposto: ingresso {op.ingresso:.{cifre}f}, stop {op.stop:.{cifre}f}, primo obiettivo {op.tp1:.{cifre}f} "
        f"(R:R {rr1:.1f}), secondo obiettivo {op.tp2:.{cifre}f} (R:R {rr2:.1f}); costi {r.costo_erre:.2f} R.",
        "",
        "=== CANDELE ===",
        _tabella(alte, QUANTE_ALTE, cifre, f"Ultime candele {NOMI_TF[r.alto_tf]} chiuse"),
        _tabella(sopra, QUANTE_SOPRA, cifre, f"Grafico sopra ({NOMI_TF[SOPRA[r.alto_tf]]})"),
        _tabella(basse, QUANTE_BASSE, cifre, f"Ultime candele {NOMI_TF[r.basso_tf]} fino all'ingresso"),
        "",
        "=== LIVELLI, TEMPO, BIAS ===",
        _livelli_liberi(sopra, op.ingresso, amp, cifre),
        _settimana(ore, q, op.ingresso, cifre),
    ]
    kl = getattr(d, "key_level", None)
    if kl is not None:
        parti.append(f"Key level trovato dal sistema sul grafico sopra: massimo/minimo preso {'sì' if kl.massimo else 'no'}, "
                     f"rejection block {'sì' if kl.rejection_block else 'no'}, FVG {'sì' if kl.fvg else 'no'}, "
                     f"la manipolazione si ferma sul livello {'sì' if kl.tocca else 'no'}.")
    else:
        parti.append("Key level trovato dal sistema sul grafico sopra: nessuno.")
    o = getattr(d, "orario", None)
    if o is not None:
        parti.append(f"Ora NY della candela d'ingresso {o.ora_scatto}:00, della manipolazione {o.ora_manipolazione}:00.")
    c = getattr(d, "contesto", None)
    if c is not None:
        parti.append(f"Bias di Romeo (chiusura/ombra): dalla candela del range {_bias(c.range)}, "
                     f"dal grafico sopra {_bias(c.sopra)}.")
    ar = getattr(d, "alla_romeo", None)
    if ar is not None:
        parti.append(f"Ora di Londra {'sì' if ar.londra else 'no'}, di New York {'sì' if ar.new_york else 'no'}; "
                     f"dentro un CRT più grande nello stesso verso {'sì' if ar.annidato else 'no'}; "
                     f"a sconto nella settimana chiusa prima: {'?' if ar.sconto is None else ('sì' if ar.sconto else 'no')}.")
    li = getattr(d, "liquidita", None)
    if li is not None:
        parti.append(f"La manipolazione ha preso la liquidità lasciata prima (massimo/minimo di swing): "
                     f"{'sì' if li.presa else 'no'}{', e stava oltre il CRT' if li.sopra_il_crt else ''}.")
    sg = getattr(d, "sguardo", None)
    if sg is not None:
        nomi = ("4 ore", "giorno", "settimana", "mese")
        parti.append("Allineamento (bias di Romeo sui grafici grandi rispetto al verso): "
                     + ", ".join(f"{n} {_favore(x)}" for n, x in zip(nomi, sg.lati))
                     + f"; CRT grandi armati nello stesso verso: {sg.livelli}.")
        if sg.fvg is not None:
            tf, lo, hi = sg.fvg
            parti.append(f"FVG aperto più vicino verso l'obiettivo: {getattr(tf, 'value', tf)} fra {lo:.{cifre}f} e {hi:.{cifre}f}.")
        if sg.weekend is not None:
            parti.append(f"Gap del weekend ancora aperto: venerdì chiuso a {sg.weekend[0]:.{cifre}f}, "
                         f"chiuderlo va {'a favore' if sg.weekend[1] else 'contro'}.")
    if gemello is not None:
        parti.append(_smt(r, crt, alte, gemello, q, cifre))
    piani = getattr(d, "piani", None)
    if piani:
        from nvm.cervello.piani import PIANI, nome
        parti += ["", "=== PIANI POSSIBILI (Livelli e Capo scelgono) ==="]
        for j, (p, o_) in enumerate(zip(PIANI, piani)):
            if o_ is None:
                continue
            parti.append(f"  piano {j}: {nome(p)}: stop {o_.stop:.{cifre}f}, obiettivi {o_.tp1:.{cifre}f} / "
                         f"{o_.tp2:.{cifre}f}, R:R {abs(o_.tp1 - o_.ingresso) / o_.rischio:.1f} / "
                         f"{abs(o_.tp2 - o_.ingresso) / o_.rischio:.1f}, parziale {o_.parziale:.0%}")
    if fiducia_numerica is not None:
        parti += ["", f"Parere dei vecchi cervelli numerici (uno strumento, non una legge): fiducia {fiducia_numerica:.0%}."]
    parti.append("")
    parti.append(_tabella(orarie, 12, cifre, "Ultime 12 candele da 1 ora"))
    return "\n".join(parti)


def _smt(r, crt, alte: Candele, gemello, q: int, cifre: int) -> str:
    """Il gemello nello stesso intervallo della manipolazione: ha preso il suo lato o no?"""
    ore_g, relazione = gemello
    try:
        alte_g = costruisci(ore_g, r.alto_tf).chiuse_entro(q)
        oreg = costruisci(ore_g, TF.H1)
    except Exception:
        return "SMT: dati del gemello non disponibili."
    k = int(np.searchsorted(alte_g.inizio, crt.range_inizio))
    if k >= len(alte_g) or alte_g.inizio[k] != crt.range_inizio:
        return "SMT: il gemello non ha la stessa candela del range."
    alto_g, basso_g = float(alte_g.bid[k, MASSIMO]), float(alte_g.bid[k, MINIMO])
    i = int(np.searchsorted(oreg.inizio, crt.manipolazione_inizio))
    j = int(np.searchsorted(oreg.fine, q, side="right"))
    seg = oreg.bid[i:j]
    if not len(seg):
        return "SMT: nessuna candela del gemello nella manipolazione."
    short = r.verso is Verso.SHORT
    # Il lato che il gemello dovrebbe prendere: lo stesso se si muove insieme, l'opposto se al contrario.
    prende_alto = short == (relazione > 0)
    preso = seg[:, MASSIMO].max() > alto_g if prende_alto else seg[:, MINIMO].min() < basso_g
    lato = "massimo" if prende_alto else "minimo"
    return (f"SMT col gemello ({'si muove insieme' if relazione > 0 else 'si muove al contrario'}): durante la "
            f"manipolazione il gemello {'HA' if preso else 'NON ha'} preso il {lato} della sua candela del range "
            f"({alto_g:.{cifre}f} / {basso_g:.{cifre}f})." + ("" if preso else " È una divergenza (SMT)."))
