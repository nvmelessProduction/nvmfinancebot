"""Livelli: dove vanno stop, primo target e target finale.

Il manuale (`documenti/spec/grilletto.md`, "Da passare agli altri agenti"):

- **stop** appena oltre l'estremo del turtle soup: "turtle soup high has to
  be the ceiling" (Romeo, msg 163); ma mai piu' vicino all'ingresso di un
  quarto del range: "Your stoploss is 25% of the range, if it hits it you're
  wrong" (04/02/2023). Gli stop piu' stretti li mangiano il rumore e i costi
  (`STOP_MINIMO`, `documenti/registro/tentativi.md`, 25/09/2026);
- **primo target** al 50% del range: "the 50% is almost always guaranteed"
  (msg 6561);
- **target finale** oltre il lato opposto del range, di meta' dell'ampiezza
  del CRT (`OLTRE`). Il manuale dice "take profit at 50% and then CRTH/L";
  ma dove si leggono i suoi target del 2023 stanno oltre il lato, fra 1,2 e
  1,8 volte il range, e sui vent'anni il target oltre il lato rende di piu'
  (`documenti/registro/tentativi.md`, 25/09/2026);
- **niente operazione** se l'ingresso e' gia' oltre il 50%: il primo target
  starebbe alle spalle.

L'operazione non ha un'uscita a tempo: esce con lo stop o col target, e dopo
il primo target il pareggio protegge il resto. Romeo non parla mai di
chiudere per tempo, e due suoi casi hanno smentito le durate provate prima:
nel CRT mensile di EURUSD (msg 5623) il target 2 arriva nella candela 3,
nel giornaliero di dicembre 2024 (msg 5730) nella candela 4. Per la
simulazione resta solo un tetto di sicurezza, largo (`TETTO`), e chi misura
conta quante operazioni ci arrivano.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti.grilletto import Scatto
from nvm.dati.candele import Candele
from nvm.dati.minuti import CHIUSURA
from nvm.prova.campo import Operazione
from nvm.tempo import TF


# Il target finale sta oltre il lato opposto del CRT di questa frazione della
# sua ampiezza. Fino al 25/09/2026 era sul lato (0): provati 0,27, 0,5 e 1 sui
# vent'anni, 0,5 e' quello che somiglia ai target di Romeo (registro).
OLTRE = 0.5
# Lo stop va a pareggio arrivati a questa frazione del cammino fra ingresso e
# primo target: 1 = al primo target, come fino al 25/09/2026. La manopola la
# gira l'allenamento (`documenti/spec/allenamento.md`).
PAREGGIO = 1.0
# Le uscite prima dello stop (spente all'inizio, le accende l'allenamento se
# migliorano le prestazioni): dopo tante candele basse di fila chiuse oltre il
# livello del Model#1 dalla parte sbagliata, e se il primo target non arriva
# entro tante candele basse. 0 = mai.
INVALIDAZIONE = 0
TEMPO = 0
# Lo stop sta almeno a questa frazione dell'ampiezza del CRT dall'ingresso.
# Fino al 25/09/2026 non c'era: sui vent'anni, col Capo, le scelte passano da
# -0,011 a +0,009 R e battono la base in tutti gli anni (registro).
STOP_MINIMO = 0.25
# Lo stop stretto sta oltre il livello del Model#1 di questa frazione
# dell'escursione della candela del turtle soup.
MARGINE_STOP_STRETTO = 0.10


def piano(
    s: Scatto, basse: Candele, parziale: float = 0.5, pareggio: bool = True,
    stop_stretto: bool = False,
) -> Optional[Operazione]:
    """L'operazione del manuale per uno scatto, o None se non si puo' fare.

    `stop_stretto` e' la variante dichiarata: lo stop appena oltre il livello
    del Model#1 (l'apertura della candela del turtle soup) invece che oltre
    l'estremo. E' quello che Romeo fa nelle operazioni che ha pubblicato:
    stop di 1-5 pip su EURUSD e GBPUSD, e sull'oro il 17/07/2024 stop a 2474
    con il livello a 2473,26 (`documenti/casi/CASO-004.md`).
    """
    crt = s.crt
    short = crt.verso is Verso.SHORT
    # Si vende in bid e si compra in ask, alla chiusura della candela che scatta.
    ingresso = float((basse.bid if short else basse.ask)[s.indice, CHIUSURA])
    margine = MARGINE_STOP_STRETTO * (s.turtle_soup_massimo - s.turtle_soup_minimo)
    if stop_stretto:
        stop = s.livello + margine if short else s.livello - margine
    elif s.punta is not None:
        # L'entrata dei video nella candela 3: stop appena oltre la punta della candela del turtle
        # soup (V3 15:30, V11 15:07), senza il quarto di range dei post.
        stop = s.punta + margine if short else s.punta - margine
    else:
        stop = crt.estremo_a(s.quando)
    if stop is None:
        return None
    ampiezza = crt.crt_high - crt.crt_low
    if not stop_stretto and s.punta is None:
        stop = max(stop, ingresso + STOP_MINIMO * ampiezza) if short else min(stop, ingresso - STOP_MINIMO * ampiezza)
    oltre = OLTRE * ampiezza
    tp1, tp2 = crt.crt_50, (crt.crt_low - oltre if short else crt.crt_high + oltre)
    if s.modello == "kiss of death":
        # Il 50% e' gia' alle spalle: l'obiettivo e' il lato opposto del range, tutto li' (V4 07:01).
        tp1 = tp2 = crt.crt_low if short else crt.crt_high
        parziale = 1.0
    segno = -1 if short else 1
    if segno * (ingresso - stop) <= 0 or segno * (tp1 - ingresso) <= 0:
        return None
    return Operazione(
        strumento=crt.strumento, verso=crt.verso, quando=s.quando,
        ingresso=ingresso, stop=stop, tp1=tp1, tp2=tp2,
        parziale=parziale, pareggio=pareggio, pareggio_a=PAREGGIO,
        livello_model1=s.livello, invalida_candele=INVALIDAZIONE, tempo_candele=TEMPO,
    )


# Il tetto di sicurezza della simulazione, per timeframe del range: circa
# dieci candele alte.
TETTO = {TF.MN: 300 * 86400, TF.W1: 70 * 86400, TF.D1: 14 * 86400, TF.H4: 3 * 86400}


def scadenza(s: Scatto) -> int:
    """Il tetto di sicurezza: dopo, l'operazione si chiude al prezzo del momento."""
    return s.quando + TETTO[s.crt.alto_tf]


# I piani di Livelli per la squadra: tutti come li vuole Romeo. Lo stop sta sempre alla punta del turtle
# soup (V3 20:02, V11 16:30) e al 50% si prende sempre qualcosa: *"always taking profits at the 50% mark.
# Always"* (V1 18:32, V8 20:01, V16 23:30). Cambia solo dove va il resto.
PIANI_ROMEO = (
    ("tutto al 50%", "chiudo tutto al 50%: Romeo dice che basta per una carriera (V10 13:01)"),
    ("metà al 50% e il resto al lato opposto", "metà al 50% e il resto al lato opposto del range (V1 18:01)"),
    ("metà al 50% e il resto oltre il lato", "metà al 50% e il resto oltre il lato, sulla liquidità dopo (V9 24:30)"),
)
PIANO_ROMEO = 1
# Di quanto oltre il lato opposto va il resto nel terzo piano, in ampiezze del range.
OLTRE_PIANO = 0.5


def piani_romeo(s: Scatto, basse: Candele) -> list[Optional[Operazione]]:
    """I piani fra cui Livelli sceglie, nell'ordine di `PIANI_ROMEO` (None se un piano non si puo' fare).
    Per il kiss of death ce n'e' uno solo: tutto al lato opposto."""
    base = piano(s, basse)
    if base is None:
        return [None] * len(PIANI_ROMEO)
    if s.modello == "kiss of death":
        return [None, base, None]
    crt = s.crt
    short = crt.verso is Verso.SHORT
    ampiezza = crt.crt_high - crt.crt_low
    lato = crt.crt_low if short else crt.crt_high
    oltre = lato - OLTRE_PIANO * ampiezza if short else lato + OLTRE_PIANO * ampiezza
    fuori = []
    for parziale, tp2 in ((1.0, lato), (0.5, lato), (0.5, oltre)):
        try:
            fuori.append(replace(base, parziale=parziale, tp2=tp2, pareggio=parziale < 1.0))
        except ValueError:
            fuori.append(None)
    return fuori
