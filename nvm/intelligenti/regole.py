"""Quello che ogni agente sa: le regole di Romeo (`bibbia.md`), divise per mestiere.

Ogni regola guarda i fatti dell'occasione (`fatti.py`) e dice: a favore (+1), contro (-1), o niente
da dire (0), con il perché scritto in parole, citando Romeo. Il peso di partenza viene da quanto conta
per Romeo (*"2 & 1 are more important than 3"*); poi ogni agente lo cambia da solo, con quello che
vede dal vivo (`squadra.py`). Le regole segnate `lista` sono le cinque domande di Romeo ("Enter a
trade?"): un solo no e non si entra.

Nessuna regola viene dai test sui vent'anni: vengono tutte da Romeo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Regola:
    nome: str
    agente: str
    peso: float
    romeo: str                      # le sue parole, o dove lo dice
    guarda: Callable                # fatti -> (esito, perche')
    lista: Optional[str] = None     # quale domanda della lista di Romeo, se lo e'


def _si_no(x, si: str, no: str, contro_se_no: bool = True):
    if x is None:
        return 0, ""
    return (1, si) if x else ((-1, no) if contro_se_no else (0, ""))


def _candela(f):
    if f["candela"] == 2:
        return -1, "siamo ancora nella candela 2: Romeo dice di aspettare che chiuda"
    if f["candela 2 chiusa dentro"] is False:
        return -1, "la candela 2 ha chiuso fuori dal range: era una rottura, non un turtle soup"
    if f["candela 2 chiusa dentro"]:
        return 1, f"siamo nella candela {f['candela']} e la candela 2 ha chiuso dentro il range"
    return 0, ""


def _corpo(f):
    c = f["corpo della candela 1"]
    if c <= -0.5:
        return 1, "la candela 1 è spessa e va verso il key level, come la disegna Romeo"
    return 0, ""


def _profondita(f):
    p = f["profondità della manipolazione"]
    if p >= 0.1:
        return 1, f"la manipolazione è entrata a fondo oltre il lato ({p:.0%} del range)"
    if p < 0.02:
        return -1, f"la manipolazione ha appena toccato il lato ({p:.0%}): non è un turtle soup convincente"
    return 0, ""


def _spessore(f):
    s = f["spessore del turtle soup"]
    if s >= 1.5:
        return 1, f"la candela del turtle soup è spessa ({s:.1f} volte la media)"
    if 0 < s < 0.8:
        return -1, f"la candela del turtle soup è sottile ({s:.1f} volte la media)"
    return 0, ""


def _apertura(f):
    x = f["dalla parte giusta dell'apertura"]
    if x is None:
        return 0, ""
    lato = "sotto" if f["verso"] == "acquisto" else "sopra"
    return (1, f"entriamo {lato} l'apertura della candela, dove Romeo cerca l'entrata") if x else \
        (-1, f"non siamo {lato} l'apertura della candela in corso")


def _smt(f):
    if not f["smt col gemello"]:
        return 0, ""
    sopra = f["bias dal grafico sopra"]
    if sopra is True:
        return 1, "c'è SMT col gemello, e va nel verso del grafico grande"
    return 0, ""


def _rr(f):
    if f["rr2"] >= 3:
        return 1, f"il lato opposto vale {f['rr2']:.1f} volte il rischio"
    if f["rr2"] < 2:
        return -1, f"il lato opposto vale solo {f['rr2']:.1f} volte il rischio"
    return 0, ""


def _costi(f):
    if f["costi in R"] > 0.15:
        return -1, f"i costi si mangiano {f['costi in R']:.2f} R"
    return 0, ""


def _mob(f):
    if f["livello intatto prima del 50%"] is not None:
        return -1, f"prima del 50% c'è un livello intatto del grafico sopra ({f['livello intatto prima del 50%']:g}) che può bloccare l'obiettivo"
    return 1, "fino al 50% la strada è libera"


def _key_level(f):
    if f["key level"]:
        return 1, f"la manipolazione è arrivata a un key level del grafico sopra ({f['tipo di key level']})"
    return -1, "nessun key level del grafico sopra: con Romeo senza key level non si opera"


def _fondo_finto(f):
    x = f["livello intatto oltre l'estremo"]
    if x is not None:
        return -1, (f"oltre l'estremo c'è ancora un livello intatto ({x:g}): il fondo può essere finto, "
                    "il prezzo di solito ci va prima di girare")
    return 0, ""


def _ore(f):
    if f["ore di Londra"] or f["ore di New York"]:
        quali = "Londra" if f["ore di Londra"] else "New York"
        return 1, f"è l'ora di {quali} ({f['ora di New York']} a New York)"
    return -1, f"sono le {f['ora di New York']} a New York: fuori dalle ore di Romeo"


def _giorno(f):
    if f["giorno"] in ("martedì", "mercoledì"):
        return 1, f"è {f['giorno']}: per Romeo i giorni migliori della settimana"
    if f["giorno"] == "venerdì":
        return -1, "è venerdì: la settimana di solito ha già fatto i suoi estremi"
    return 0, ""


def _settimana(f):
    x = f["estremo della settimana fra lunedì e mercoledì"]
    if x:
        return 1, "la manipolazione ha fatto l'estremo della settimana fra lunedì e mercoledì, come vuole Romeo"
    return 0, ""


def _bias(nome, testo_si, testo_no):
    def guarda(f):
        return _si_no(f[nome], testo_si, testo_no)
    return guarda


def _grandi(f):
    if f["CRT grandi contro"] > 0 and f["CRT grandi nello stesso verso"] == 0:
        return -1, "un CRT del grafico grande punta dall'altra parte: sulla strada verso il suo obiettivo si ignora tutto il resto"
    if f["CRT grandi nello stesso verso"] > 0:
        return 1, "c'è un CRT del grafico grande nello stesso verso: il micro dentro il macro"
    return 0, ""


def _allineati(f):
    a, c = f["timeframe grandi a favore"], f["timeframe grandi contro"]
    if a - c >= 2:
        return 1, f"{a} grafici grandi su 4 sono a favore"
    if c - a >= 2:
        return -1, f"{c} grafici grandi su 4 sono contro"
    return 0, ""


def _orderflow(f):
    """La seconda domanda di Romeo: allineato all'orderflow del timeframe alto? No solo se è contro."""
    if f["bias dal grafico sopra"] is False or f["timeframe grandi contro"] - f["timeframe grandi a favore"] >= 2:
        return -1, "l'operazione va contro l'orderflow del grafico grande"
    return 1, "l'orderflow del grafico grande non è contro"


REGOLE: tuple[Regola, ...] = (
    # Cacciatore: il CRT stesso.
    Regola("candela 3", "Cacciatore", 1.5,
           "\"Avoid candle 2 as a beginner. Shift your entire focus on candle number three.\" Aspetta che la candela 2 chiuda.",
           _candela),
    Regola("candele interne", "Cacciatore", 0.5, "più candele interne dopo il range, meglio è",
           lambda f: (1, f"dopo il range ci sono {f['candele interne']} candele interne") if f["candele interne"] >= 1 else (0, "")),
    Regola("candela 1 spessa", "Cacciatore", 0.5,
           "prima del key level di solito una candela spessa (la candela 1), poi la manipolazione", _corpo),
    Regola("micro dentro macro", "Cacciatore", 0.7, "\"There is always a micro CRT within the macro CRT.\"",
           lambda f: (1, "è un CRT dentro un CRT più grande nello stesso verso") if f["dentro un CRT più grande"] else (0, "")),

    # Grilletto: l'entrata.
    Regola("turtle soup convincente", "Grilletto", 1.0, "\"You want to see them stab real hard into the old high.\"",
           _profondita),
    Regola("candela spessa", "Grilletto", 1.0, "\"Thick up-close candle that liquidated an old high = bearish orderblock.\"",
           _spessore),
    Regola("FVG col Model#1", "Grilletto", 0.7, "\"If model number one comes with an FVG, it becomes a higher probability trade.\"",
           lambda f: (1, "il Model#1 ha lasciato un FVG") if f["fvg col Model#1"] else (0, "")),
    Regola("vera rottura di struttura", "Grilletto", 0.7,
           "\"Every single entry is either a model#1 or a true market structure shift.\"",
           lambda f: (1, "c'è anche la vera rottura di struttura") if f["vera rottura di struttura"] else (0, "")),
    Regola("sotto l'apertura", "Grilletto", 1.0,
           "\"All the breakers, all the order blocks, all the turtle soups happen above and below the open.\"",
           _apertura),
    Regola("SMT", "Grilletto", 0.7, "\"Only look for bullish SMTs in a higher time frame bullish market.\"", _smt),
    Regola("manipolazione a fine candela", "Grilletto", 0.5,
           "se la manipolazione avviene alla fine della candela prima, la candela dopo distribuisce subito",
           lambda f: (1, "la manipolazione è arrivata alla fine della candela: ora la distribuzione") if f["manipolazione a fine candela"] else (0, "")),
    Regola("liquidità prima della manipolazione", "Grilletto", 0.5,
           "\"3. Mark a pre-manipulation swing high/low. 2 & 1 are more important than 3.\"",
           lambda f: (1, "la manipolazione ha preso la liquidità lasciata prima") if f["liquidità presa prima"] else (0, "")),

    # Livelli: stop e obiettivi.
    Regola("lato opposto", "Livelli", 1.0, "\"Your target is the opp. end of the range (1:3 in the very least).\"", _rr),
    Regola("costi", "Livelli", 0.7, "il rischio si gestisce: niente operazioni mangiate dai costi", _costi),
    Regola("strada libera fino al 50%", "Livelli", 1.0,
           "MOB: \"If respected, it will block the target… scratch the trade idea.\"", _mob, lista="draw_on_liquidity"),

    # Key level.
    Regola("key level", "Key level", 2.0, "\"Trading CRT with no key level is a beginner mistake.\"", _key_level,
           lista="key_level"),
    Regola("fondo finto", "Key level", 1.5,
           "andando verso un key level non toccato i CRT falliscono: \"they give you a fake bottom always\"", _fondo_finto),
    Regola("si ferma sul livello", "Key level", 0.7,
           "il disegno del suo manuale: la manipolazione arriva alla linea del key level e crolla",
           lambda f: (1, "la manipolazione si è fermata proprio sul livello") if f["si ferma sul livello"] else (0, "")),
    Regola("apertura della candela contraria", "Key level", 0.7,
           "\"Look at down close candles as support, true support, and up close candles as resistance.\"",
           lambda f: (1, "la manipolazione è arrivata all'apertura dell'ultima candela contraria del grafico sopra")
           if f["apertura della candela contraria toccata"] else (0, "")),

    # Orario.
    Regola("ore di Romeo", "Orario", 2.0, "\"Time is more important than price.\" Londra 3-5, New York 9:30, 13:30.",
           _ore, lista="ore_giuste"),
    Regola("golden candle time", "Orario", 0.5, "\"GCT: Golden candle time (9am-1pm NY time).\"",
           lambda f: (1, "siamo nella golden candle time (9-13 New York)") if f["golden candle time"] else (0, "")),
    Regola("giorno della settimana", "Orario", 0.7, "\"Tuesdays and Wednesdays are the highest probability days of the week.\"",
           _giorno),
    Regola("estremo della settimana", "Orario", 0.7,
           "il massimo (o il minimo) della settimana si forma lunedì-mercoledì, l'altro estremo giovedì-venerdì", _settimana),

    # Bias.
    Regola("bias della candela del range", "Bias", 1.0,
           "\"Close above = higher prices. Close below = lower prices. Wick above = lower prices. Wick below = higher prices.\"",
           _bias("bias dalla candela del range", "il bias della candela del range è a favore",
                 "il bias della candela del range è contro")),
    Regola("orderflow del grafico sopra", "Bias", 1.5, "\"Is it aligned with the HTF orderflow?\"", _orderflow,
           lista="orderflow_alto"),
    Regola("obiettivo del grafico grande", "Bias", 1.5, "\"We ignore all bullish patterns on the way down to a bearish target.\"",
           _grandi),
    Regola("range lows are for buying", "Bias", 0.5, "\"Range lows are for buying or watching only, not selling.\"",
           lambda f: _si_no(f["a sconto nella settimana"], "siamo nella metà giusta della settimana chiusa",
                            "siamo nella metà sbagliata della settimana chiusa")),

    # Allineamento.
    Regola("grafici grandi d'accordo", "Allineamento", 1.0, "\"Pick bottoms in bullish markets. Don't pick tops in bullish markets.\"",
           _allineati),

    # Gap.
    Regola("FVG davanti", "Gap", 0.5, "il prezzo si muove per prendere liquidità o per riempire un vuoto",
           lambda f: (1, "c'è un FVG aperto verso l'obiettivo che attira il prezzo") if f["FVG davanti"] else (0, "")),
    Regola("FVG alle spalle", "Gap", 0.7, "un vuoto alle spalle può riportare il prezzo contro di noi",
           lambda f: (-1, "c'è un FVG aperto vicino alle spalle") if f["FVG alle spalle vicino"] else (0, "")),
    Regola("gap del weekend", "Gap", 0.5, "il gap del weekend tende a chiudersi",
           lambda f: _si_no(f["gap del weekend"], "chiudere il gap del weekend va a favore",
                            "chiudere il gap del weekend va contro")),
)

AGENTI = ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Allineamento", "Gap")
# La quarta domanda di Romeo (la conferma sul timeframe basso) e' il Model#1: c'e' sempre, e' da li'
# che nasce ogni occasione.
LISTA = ("key_level", "orderflow_alto", "draw_on_liquidity", "conferma_basso", "ore_giuste")
