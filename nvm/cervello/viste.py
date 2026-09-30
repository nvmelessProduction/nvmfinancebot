"""Cosa vede ogni agente: il mercato nel suo campo, in numeri, al momento dell'ingresso.

Ogni agente ha i suoi occhi. Non riceve piu' una risposta si'/no scritta da noi (per esempio
"c'e' un FVG"): vede le candele e le misure del suo mestiere e il suo cervello (`rete.py`)
impara da solo cosa conta. Le viste sono le stesse sullo storico e dal vivo: si calcolano
solo con le candele gia' chiuse all'ingresso.

Tutto e' nel verso dell'operazione (in acquisto su vuol dire a favore, in vendita giu' vuol
dire a favore) e in unita' della sua scala (l'ampiezza del range, o la candela media), cosi'
EURUSD, oro e indici parlano la stessa lingua.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import Candele
from nvm.tempo import NEW_YORK, TF

# Gli agenti con un cervello, e quante candele guardano.
AGENTI = ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Allineamento", "Gap")
ALTE = 5
BASSE = 12
SOPRA = 10
MEDIA = 20
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1), (TF.H4, TF.M15))


def _ampiezza_media(c: Candele, n: int = MEDIA) -> float:
    if not len(c):
        return float("nan")
    b = c.bid[-n:]
    return float(np.mean(b[:, 1] - b[:, 2])) or float("nan")


def _candele(c: Candele, n: int, zero: float, scala: float, segno: int) -> np.ndarray:
    """Le ultime `n` candele (apertura, estremo a favore, estremo contro, chiusura) rispetto al
    prezzo d'ingresso, nel verso dell'operazione. Mancano? Zeri."""
    fuori = np.zeros((n, 4))
    b = c.bid[-n:]
    if len(b) and np.isfinite(scala) and scala > 0:
        v = segno * (b - zero) / scala
        fuori[n - len(b):] = np.c_[v[:, 0], np.maximum(v[:, 1], v[:, 2]), np.minimum(v[:, 1], v[:, 2]), v[:, 3]]
    return fuori.ravel()


def _log(x: float) -> float:
    return float(np.log(max(x, 1e-9)))


def _ritorno(c: Candele, indietro: int, scala: float, zero: float, segno: int) -> float:
    """Di quanto il prezzo d'ingresso e' andato, nel verso dell'operazione, dalla chiusura di
    `indietro` candele fa (0 = l'ultima chiusa), in unita' di `scala`."""
    if len(c) <= indietro or not np.isfinite(scala) or scala <= 0:
        return 0.0
    return float(segno * (zero - c.bid[-1 - indietro, 3]) / scala)


def _rottura(basse: Candele, da: int, segno: int, ampiezza: float) -> tuple[float, float]:
    """La vera rottura di struttura di Romeo sulle candele basse, per l'acquisto: un minimo, un
    massimo, un minimo piu' basso, poi una chiusura sopra quel massimo (per la vendita lo specchio).
    Il minimo piu' basso e' il punto piu' lontano dalla manipolazione in poi. C'e' stata (1)? E di
    quanto la chiusura migliore dopo il minimo e' oltre quel massimo (+) o sotto (-), in ampiezze
    del range."""
    i = int(np.searchsorted(basse.inizio, da))
    i0 = max(0, i - BASSE)
    b = basse.bid[i0:]
    if i >= len(basse.bid) or len(b) < 3:
        return 0.0, 0.0
    # Nel verso dell'acquisto: per la vendita i massimi diventano minimi e il prezzo si rovescia.
    bassi, alti, chiuse = (b[:, 2], b[:, 1], b[:, 3]) if segno > 0 else (-b[:, 1], -b[:, 2], -b[:, 3])
    k = (i - i0) + int(np.argmin(bassi[i - i0:]))
    if k == 0 or k + 1 >= len(b):
        return 0.0, 0.0
    primo = int(np.argmin(bassi[:k]))
    if bassi[k] >= bassi[primo]:
        return 0.0, 0.0
    alto = float(alti[primo:k].max())
    oltre = (float(chiuse[k + 1:].max()) - alto) / ampiezza
    return float(oltre > 0), float(np.clip(oltre, -3, 3))


def _tempo_della_finta(crt, alte: Candele, quando: int) -> tuple[float, float]:
    """A che punto della sua candela grande la manipolazione ha fatto il suo estremo (0 = appena
    aperta, 1 = alla chiusura), e se si entra in una candela grande successiva (1)."""
    j = int(np.searchsorted(crt.estremo_istanti, quando, side="right"))
    if j == 0 or not len(alte):
        return 0.5, 0.0
    valori = crt.estremo_valori[:j]
    t = int(crt.estremo_istanti[int(np.flatnonzero(valori == valori[-1])[0])])
    m = int(np.searchsorted(alte.inizio, t - 1, side="right")) - 1
    if m < 0:
        return 0.5, 0.0
    if t > int(alte.fine[m]):
        # L'estremo e' nella candela grande ancora aperta: si entra nella stessa candela.
        inizio, durata, dopo = int(alte.fine[-1]), int(alte.fine[-1] - alte.inizio[-1]), 0.0
    else:
        inizio, durata, dopo = int(alte.inizio[m]), int(alte.fine[m] - alte.inizio[m]), float(quando > alte.fine[m])
    return float(np.clip((t - inizio) / max(durata, 1), 0.0, 1.0)), dopo


def viste(r, alte: Candele, basse: Candele, sopra: Candele, settimane: Candele, x: np.ndarray,
          grandi=None, compagno=None, quadro=None) -> dict[str, np.ndarray]:
    """Le viste degli agenti su un'operazione `r` (un `Risultato` con lo scatto), dalle candele
    chiuse entro l'ingresso. `x` sono le risposte di oggi al Capo: qualcuna resta come
    indizio, finche' i cervelli non imparano a farne a meno. `grandi`: i CRT dei grafici grandi
    (`conferme.Grandi`); `compagno`: (le ore dello strumento gemello, +1 se si muove insieme,
    -1 se al contrario), per l'SMT; `quadro`: le candele grandi dello strumento
    (`panorama.Contesto`), per Allineamento e Gap. In fondo a ogni vista, le cose insegnate da
    Romeo nei suoi video (`spec/FONTI-ROMEO.md`, "Dai video")."""
    quando = r.quando
    alte, basse = alte.chiuse_entro(quando), basse.chiuse_entro(quando)
    sopra, settimane = sopra.chiuse_entro(quando), settimane.chiuse_entro(quando)
    s = r.scatto
    crt = s.crt
    segno = -1 if r.verso is Verso.SHORT else 1
    zero = float(r.ingresso) if r.ingresso else float(basse.bid[-1, 3])
    ampiezza = max(crt.crt_high - crt.crt_low, 1e-12)
    lato = crt.crt_high if segno < 0 else crt.crt_low
    x = np.asarray(x, float)
    rr = np.log1p([max(r.rr1, 0.0), max(r.rr2, 0.0)])
    ny = datetime.fromtimestamp(quando, tz=NEW_YORK)

    # Il Cacciatore: il range, la sua misura, le ultime candele grandi.
    coppia = [float((r.alto_tf, r.basso_tf) == c) for c in COPPIE]
    media_alte = _ampiezza_media(alte)
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    candela_range = alte.bid[k] if k < len(alte) and alte.inizio[k] == crt.range_inizio else None
    corpo = segno * (candela_range[3] - candela_range[0]) / ampiezza if candela_range is not None else 0.0
    # Romeo: piu' candele interne dopo il range, meglio e'; e l'ora in cui nasce il range conta.
    interne = 0
    for j in range(k + 1, len(alte)):
        if alte.bid[j, 1] <= crt.crt_high and alte.bid[j, 2] >= crt.crt_low:
            interne += 1
        else:
            break
    ora_range = datetime.fromtimestamp(crt.range_inizio, tz=NEW_YORK).hour
    cacciatore = np.r_[coppia, _log(ampiezza / media_alte) if np.isfinite(media_alte) else 0.0,
                       segno * (zero - lato) / ampiezza, corpo, x[24], rr[0],
                       _candele(alte, ALTE, zero, ampiezza, segno),
                       np.log1p(min(interne, 6)), np.sin(2 * np.pi * ora_range / 24), np.cos(2 * np.pi * ora_range / 24)]

    # Il Grilletto: come il prezzo e' arrivato all'ingresso, sulle candele piccole.
    estremo = crt.estremo_a(quando)
    profondita = segno * (lato - estremo) / ampiezza if estremo is not None else 0.0
    dall_inizio = max(quando - crt.manipolazione_inizio, 0) / max(basse.fine[-1] - basse.inizio[-1], 1) if len(basse) else 0.0
    colpo = [float(r.colpo == 1), float(r.colpo == 2), float(r.colpo >= 3)]
    # Romeo: meglio aspettare che la candela 2 chiuda ed entrare nella 3, dalla parte giusta della
    # sua apertura; la candela del turtle soup "spessa"; il Model#1 con un FVG; l'SMT col gemello.
    dopo = int((alte.inizio > crt.range_inizio).sum())
    apertura_corrente = 0.0
    if len(alte) and len(basse):
        j = int(np.searchsorted(basse.inizio, alte.fine[-1]))
        if j < len(basse):
            apertura_corrente = segno * (zero - float(basse.bid[j, 0])) / ampiezza
    media_basse_g = _ampiezza_media(basse)
    spessore = ((s.turtle_soup_massimo - s.turtle_soup_minimo) / media_basse_g
                if np.isfinite(media_basse_g) and media_basse_g > 0 else 0.0)
    fvg = 0.0
    if len(basse) >= 3:
        b = basse.bid
        gap = (b[-1, 2] - b[-3, 1]) if segno > 0 else (b[-3, 2] - b[-1, 1])
        fvg = max(float(gap), 0.0) / ampiezza
    smt, smt_quanto = _smt(crt, alte, k, quando, segno, compagno)
    # Romeo (CRT secrets 6 e 9): l'ingresso e' un Model#1 o una vera rottura di struttura; se la finta
    # arriva alla fine della sua candela, la candela dopo distribuisce subito; l'SMT conta solo a
    # favore del grafico sopra.
    media_sopra = _ampiezza_media(sopra)
    sopra_a_favore = _ritorno(sopra, 4, media_sopra, zero, segno) > 0
    grilletto = np.r_[colpo, profondita, np.log1p(dall_inizio), x[26], x[27], rr[0],
                      _candele(basse, BASSE, zero, ampiezza, segno),
                      float(dopo == 0), np.log1p(dopo), apertura_corrente, np.log1p(max(spessore, 0.0)), fvg,
                      smt, smt_quanto,
                      _rottura(basse, crt.manipolazione_inizio, segno, ampiezza),
                      _tempo_della_finta(crt, alte, quando),
                      smt * float(sopra_a_favore), smt * float(not sopra_a_favore)]

    # I Livelli: dove sono stop e obiettivi, rispetto al range e alla candela piccola media.
    stop = abs(zero - r.stop) if r.stop else ampiezza * max(r.stop_su_ampiezza, 1e-6)
    media_basse = _ampiezza_media(basse)
    livelli = np.r_[rr, r.stop_su_ampiezza, r.costo_erre,
                    _log(stop / media_basse) if np.isfinite(media_basse) else 0.0, _log(stop / ampiezza)]

    # Key level: il grafico sopra, con i suoi massimi e minimi recenti.
    if len(sopra) and np.isfinite(media_sopra):
        b = sopra.bid[-MEDIA:]
        alto, basso = float(b[:, 1].max()), float(b[:, 2].min())
        verso_alto, verso_basso = (alto, basso) if segno > 0 else (basso, alto)
        distanze = [segno * (verso_alto - zero) / media_sopra, segno * (zero - verso_basso) / media_sopra]
    else:
        distanze = [0.0, 0.0]
    key = np.r_[x[0:5], distanze, rr[0], _candele(sopra, SOPRA, zero, media_sopra, segno)]

    # Romeo: la posizione nella settimana in corso (i massimi e minimi della settimana hanno i loro
    # giorni), e l'obiettivo del grafico grande ancora da prendere: contro di lui si ignora tutto.
    settimana, parte = 0.5, 0.5
    if len(settimane) and len(basse):
        corrente = basse.bid[int(np.searchsorted(basse.inizio, settimane.fine[-1])):]
        parte = float(np.clip((quando - settimane.fine[-1]) / (5 * 86400), 0.0, 1.2))
        if len(corrente):
            alto_s, basso_s = float(corrente[:, 1].max()), float(corrente[:, 2].min())
            if alto_s > basso_s:
                settimana = (zero - basso_s) / (alto_s - basso_s)
                settimana = settimana if segno > 0 else 1 - settimana

    # L'Orario: l'ora di New York e il giorno della settimana. Romeo (CRT secrets 1, CRTology, "What
    # is CRT?"): il massimo e il minimo della settimana hanno i loro giorni; l'Orario vede anche dove
    # sta il prezzo nella settimana e quanta settimana e' passata, per legare il giorno al prezzo.
    ora = ny.hour + ny.minute / 60
    orario = np.r_[np.sin(2 * np.pi * ora / 24), np.cos(2 * np.pi * ora / 24),
                   [float(ny.weekday() == g) for g in range(5)], x[22], x[23], rr[0], settimana, parte]

    # Il Bias: dove e' andato il prezzo, sul grafico sopra e sulla settimana.
    def ritorno(c: Candele, indietro: int, scala: float) -> float:
        return _ritorno(c, indietro, scala, zero, segno)
    media_sett = _ampiezza_media(settimane, 13)
    stesso = contro = 0
    if grandi is not None:
        from nvm.agenti.conferme import GRANDEZZA
        g = GRANDEZZA.get(r.alto_tf, 0)
        stesso = grandi.livelli(r.verso, g, quando)
        contro = grandi.livelli(Verso.LONG if r.verso is Verso.SHORT else Verso.SHORT, g, quando)
    bias = np.r_[[ritorno(sopra, k, media_sopra) for k in (0, 4, 19)],
                 [ritorno(settimane, k, media_sett) for k in (0, 3, 12)], corpo, x[10:14], x[25], rr[0],
                 settimana, stesso, contro]

    # Allineamento: i timeframe grandi sono d'accordo? Gap: i buchi di prezzo ancora aperti.
    obiettivo = crt.crt_low if segno < 0 else crt.crt_high
    return {"Cacciatore": cacciatore, "Grilletto": grilletto, "Livelli": livelli, "Key level": key,
            "Orario": orario, "Bias": bias, "Allineamento": _allineamento(quadro, quando, zero, segno, r.verso),
            "Gap": _gap(quadro, quando, zero, segno, ampiezza, obiettivo)}


def _allineamento(quadro, quando: int, zero: float, segno: int, verso) -> np.ndarray:
    """Su 4 ore, giorno, settimana e mese: il bias di Romeo sulle ultime due candele chiuse (+1 a
    favore, -1 contro, 0 neutro), il corpo dell'ultima candela e dove sta il prezzo nelle ultime
    cinque, nel verso dell'operazione. Poi quanti timeframe sono a favore e quanti contro."""
    from nvm.agenti.panorama import GRANDI, a_favore, bias_a
    fuori, favore, contro = [], 0, 0
    for tf in GRANDI:
        c = quadro.candele[tf].chiuse_entro(quando) if quadro is not None else None
        if c is None or len(c) < 2:
            fuori += [0.0, 0.0, 0.5]
            continue
        f = a_favore(bias_a(c, quando), verso)
        lato = 0.0 if f is None else (1.0 if f else -1.0)
        favore, contro = favore + (lato > 0), contro + (lato < 0)
        media = _ampiezza_media(c)
        corpo = segno * float(c.bid[-1, 3] - c.bid[-1, 0]) / media if np.isfinite(media) and media > 0 else 0.0
        b = c.bid[-5:]
        alto, basso = float(b[:, 1].max()), float(b[:, 2].min())
        dove = (zero - basso) / (alto - basso) if alto > basso else 0.5
        fuori += [lato, float(np.clip(corpo, -3, 3)), float(np.clip(dove if segno > 0 else 1 - dove, -1, 2))]
    return np.r_[fuori, favore, contro]


def _gap(quadro, quando: int, zero: float, segno: int, ampiezza: float, obiettivo: float) -> np.ndarray:
    """Per 1 ora, 4 ore, giorno e settimana: c'e' un fair value gap ancora aperto fra l'ingresso e
    l'obiettivo (davanti), e uno alle spalle (fino a due ampiezze del range contro)? E quanto e'
    vicino, in ampiezze del range. Poi il gap del weekend ancora aperto: chiuderlo va a favore (+1)
    o contro (-1), quanto e' grande (in giorni medi) e dove sta rispetto all'ingresso."""
    from nvm.agenti.panorama import aperti, gap_della_settimana
    fuori = []
    for tf in (TF.H1, TF.H4, TF.D1, TF.W1):
        if quadro is None:
            fuori += [0.0, 0.0, 0.0, 0.0]
            continue
        c, b = quadro.tf(tf), quadro.buchi(tf)
        for fin_dove in (obiettivo, zero - segno * 2 * ampiezza):
            trovati = aperti(b, c, quando, 100, zero, fin_dove)
            if len(trovati):
                distanza = np.abs((b.alto[trovati] + b.basso[trovati]) / 2 - zero).min() / ampiezza
                fuori += [1.0, float(np.clip(distanza, 0, 5))]
            else:
                fuori += [0.0, 0.0]
    settimana = [0.0, 0.0, 0.0]
    if quadro is not None:
        ap = quadro.aperture()
        j = gap_della_settimana(ap, quando)
        if j is not None and ap.chiuso[j] > quando and ap.giorno_medio[j] > 0:
            chiuderlo = 1.0 if (ap.apertura[j] > ap.prima[j]) == (segno < 0) else -1.0
            settimana = [chiuderlo, float(np.clip(abs(ap.apertura[j] - ap.prima[j]) / ap.giorno_medio[j], 0, 3)),
                         float(np.clip(segno * (ap.prima[j] - zero) / ampiezza, -5, 5))]
    return np.r_[fuori, settimana]


def dimensioni() -> dict[str, int]:
    """Quanti numeri vede ogni agente."""
    return {"Cacciatore": 4 + 5 + ALTE * 4 + 3, "Grilletto": 3 + 5 + BASSE * 4 + 7 + 6, "Livelli": 6,
            "Key level": 5 + 3 + SOPRA * 4, "Orario": 2 + 5 + 3 + 2, "Bias": 3 + 3 + 1 + 5 + 1 + 3,
            "Allineamento": 4 * 3 + 2, "Gap": 4 * 4 + 3}


# Lo strumento gemello per l'SMT (Romeo: "when you trade Bitcoin, you have to watch Ethereum"),
# con +1 se si muovono insieme, -1 se al contrario.
COMPAGNI = {"EURUSD": ("GBPUSD", 1), "GBPUSD": ("EURUSD", 1), "AUDUSD": ("NZDUSD", 1), "NZDUSD": ("AUDUSD", 1),
            "USDCHF": ("EURUSD", -1), "USDCAD": ("EURUSD", -1), "USDJPY": ("EURUSD", -1),
            "XAUUSD": ("XAGUSD", 1), "XAGUSD": ("XAUUSD", 1), "USOIL": ("UKOIL", 1), "UKOIL": ("USOIL", 1),
            "SPX500": ("NAS100", 1), "NAS100": ("SPX500", 1), "US30": ("SPX500", 1), "GER40": ("SPX500", 1),
            "UK100": ("GER40", 1), "JPN225": ("SPX500", 1), "BTCUSD": ("ETHUSD", 1), "ETHUSD": ("BTCUSD", 1),
            "EURGBP": ("EURCHF", 1), "EURJPY": ("GBPJPY", 1), "GBPJPY": ("EURJPY", 1), "AUDJPY": ("NZDJPY", 1),
            "NZDJPY": ("AUDJPY", 1), "EURAUD": ("GBPAUD", 1), "GBPAUD": ("EURAUD", 1), "EURCAD": ("GBPCAD", 1),
            "GBPCAD": ("EURCAD", 1), "EURCHF": ("GBPCHF", 1), "GBPCHF": ("EURCHF", 1), "EURNZD": ("GBPNZD", 1),
            "GBPNZD": ("EURNZD", 1), "AUDCAD": ("NZDCAD", 1), "NZDCAD": ("AUDCAD", 1), "AUDCHF": ("NZDCHF", 1),
            "NZDCHF": ("AUDCHF", 1), "AUDNZD": ("AUDCAD", 1), "CADCHF": ("CADJPY", 1), "CADJPY": ("CADCHF", 1),
            "CHFJPY": ("CADJPY", 1)}


def _smt(crt, alte: Candele, k: int, quando: int, segno: int, compagno) -> tuple[float, float]:
    """L'SMT col gemello: quando il nostro strumento ha preso il lato del range, il gemello ha
    preso il suo (nello stesso intervallo di tempo)? Se no, e' una divergenza che conferma
    l'inversione (1). E di quanto il gemello e' andato oltre il suo lato (+) o e' rimasto dentro
    (-), in ampiezze del suo range. Senza gemello: 0, 0."""
    if compagno is None or k >= len(alte):
        return 0.0, 0.0
    ore, verso_relazione = compagno
    if ore is None or not len(ore):
        return 0.0, 0.0
    t = ore.t
    fine_range = int(alte.fine[k])
    nel_range = (t >= crt.range_inizio) & (t < fine_range)
    dopo = (t >= fine_range) & (t < quando)
    if not nel_range.any() or not dopo.any():
        return 0.0, 0.0
    b = ore.bid
    alto_r, basso_r = float(b[nel_range, 1].max()), float(b[nel_range, 2].min())
    largo = max(alto_r - basso_r, 1e-12)
    # Il lato che il gemello avrebbe dovuto prendere: lo stesso nostro se va insieme, l'opposto se al contrario.
    lato_basso = (segno > 0) == (verso_relazione > 0)
    if lato_basso:
        oltre = (basso_r - float(b[dopo, 2].min())) / largo
    else:
        oltre = (float(b[dopo, 1].max()) - alto_r) / largo
    return float(oltre <= 0), float(np.clip(oltre, -3, 3))
