"""Quello che ogni agente sa quando nasce: le regole di Romeo (`bibbia.md`), divise per mestiere.

Ogni regola guarda i fatti dell'occasione (`fatti.py`) e dice: a favore (+1), contro (-1), o niente
da dire (0), con il perche' in parole semplici (sono le frasi che arrivano su Telegram). Il peso di
partenza viene da quanto conta per Romeo (*"2 & 1 are more important than 3"*). Non sono obblighi:
sono quello che l'agente crede il primo giorno. Poi ognuno impara dal vivo quanto valgono davvero
(`squadra.py`), e puo' arrivare a crederci di piu', di meno, o per niente.

Le regole segnate `lista` sono le domande di Romeo prima di entrare ("Enter a trade?"): il Capo nasce
credendo che un solo no basti a non entrare, e impara dal vivo se e' vero.
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
    # Come si chiama in breve quando dice si' e quando dice no (per le idee nuove degli agenti).
    si: str = ""
    no: str = ""


def _compra(f) -> bool:
    return f["verso"] == "acquisto"


def _v(f, compra: str, vende: str) -> str:
    return compra if _compra(f) else vende


def _candela(f):
    if f["candela"] == 2:
        return -1, "è ancora la seconda candela: Romeo dice di aspettare che si chiuda"
    if f["candela 2 chiusa dentro"] is False:
        return -1, "la seconda candela ha chiuso fuori dalla candela di riferimento: il prezzo è scappato davvero, non era una finta"
    if f["candela 2 chiusa dentro"]:
        return 1, "la seconda candela ha richiuso dentro la candela di riferimento: la finta è confermata"
    return 0, ""


def _profondita(f):
    p = f["profondità della manipolazione"]
    if p >= 0.1:
        return 1, f"la finta è andata ben oltre il {_v(f, 'minimo', 'massimo')} e il prezzo è tornato indietro con forza"
    if p < 0.02:
        return -1, f"la finta ha appena sfiorato il {_v(f, 'minimo', 'massimo')}: poco convincente"
    return 0, ""


def _spessore(f):
    s = f["spessore del turtle soup"]
    if s >= 1.5:
        return 1, f"la candela della finta è grande ({s:.1f} volte il normale): segnale forte di inversione".replace(".", ",", 1)
    if 0 < s < 0.8:
        return -1, "la candela della finta è piccola: segnale debole"
    return 0, ""


def _apertura(f):
    x = f["dalla parte giusta dell'apertura"]
    if x is None:
        return 0, ""
    if x:
        return 1, _v(f, "compriamo sotto il prezzo di apertura della candela: a sconto, come fa Romeo",
                     "vendiamo sopra il prezzo di apertura della candela: caro, come fa Romeo")
    return -1, _v(f, "compriamo sopra il prezzo di apertura della candela: più caro di come vuole Romeo",
                  "vendiamo sotto il prezzo di apertura della candela: più a buon mercato di come vuole Romeo")


def _smt(f):
    if f["smt col gemello"] and f["bias dal grafico sopra"] is True:
        return 1, "il mercato gemello non ha fatto la stessa finta e il grafico più grande è d'accordo: segnale di forza"
    return 0, ""


def _volte(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _rr(f):
    if f["rr2"] >= 3:
        return 1, f"se va tutto bene guadagniamo {_volte(f['rr2'])} volte quello che rischiamo"
    if f["rr2"] < 2:
        return -1, f"anche se va tutto bene guadagniamo solo {_volte(f['rr2'])} volte quello che rischiamo"
    return 0, ""


def _costi(f):
    if f["costi in R"] > 0.15:
        return -1, "i costi (spread e commissioni) si mangiano una parte grossa del guadagno"
    return 0, ""


def _mob(f):
    if f["livello intatto prima del 50%"] is not None:
        return -1, "prima del primo obiettivo c'è un livello mai toccato che può fermare il prezzo"
    return 1, "fino al primo obiettivo la strada è libera"


_ZONE = {"vecchio massimo/minimo preso": "un vecchio massimo o minimo",
         "rejection block": "una zona dove il prezzo era già stato respinto", "FVG": "un vuoto lasciato dal prezzo"}


def _key_level(f):
    if f["key level"]:
        quale = " e ".join(_ZONE.get(x, x) for x in str(f["tipo di key level"]).split(", ") if x)
        return 1, f"il prezzo è arrivato su una zona importante del grafico più grande ({quale}): lì di solito gira"
    return -1, "non c'è nessuna zona importante del grafico più grande: Romeo senza zona non entra"


def _fondo_finto(f):
    if f["livello intatto oltre l'estremo"] is not None:
        return -1, (f"poco più in là c'è ancora un {_v(f, 'minimo', 'massimo')} mai toccato: il prezzo potrebbe "
                    f"andarci prima di girare ({_v(f, 'il finto fondo', 'il finto tetto')} di Romeo)")
    return 0, ""


def _ore(f):
    ora = f["ora di New York"]
    if f["ore di Londra"]:
        return 1, f"sono le {ora} a New York: è l'apertura di Londra, un'ora di Romeo"
    if f["ore di New York"]:
        return 1, f"sono le {ora} a New York: è l'apertura di New York, un'ora di Romeo"
    return -1, f"sono le {ora} a New York: fuori dalle ore di Romeo"


def _giorno(f):
    if f["giorno"] in ("martedì", "mercoledì"):
        return 1, f"è {f['giorno']}: per Romeo i giorni migliori della settimana"
    if f["giorno"] == "venerdì":
        return -1, "è venerdì: di solito la settimana ha già fatto il suo massimo e il suo minimo"
    return 0, ""


def _settimana(f):
    if f["estremo della settimana fra lunedì e mercoledì"]:
        return 1, f"il {_v(f, 'minimo', 'massimo')} della settimana si è formato fra lunedì e mercoledì, come dice Romeo"
    return 0, ""


def _bias_range(f):
    x = f["bias dalla candela del range"]
    if x is None:
        return 0, ""
    return (1, "la candela di riferimento spinge nella nostra direzione") if x else \
        (-1, "la candela di riferimento spinge contro di noi")


def _grandi(f):
    if f["CRT grandi contro"] > 0 and f["CRT grandi nello stesso verso"] == 0:
        return -1, "sul grafico più grande c'è un movimento che punta dall'altra parte"
    if f["CRT grandi nello stesso verso"] > 0:
        return 1, "anche sul grafico più grande c'è un movimento nello stesso verso"
    return 0, ""


def _allineati(f):
    a, c = f["timeframe grandi a favore"], f["timeframe grandi contro"]
    if a - c >= 2:
        return 1, f"{a} grafici grandi su 4 (4 ore, giorno, settimana, mese) vanno nella nostra direzione"
    if c - a >= 2:
        return -1, f"{c} grafici grandi su 4 (4 ore, giorno, settimana, mese) vanno contro di noi"
    return 0, ""


def _orderflow(f):
    """La seconda domanda di Romeo: allineato alla direzione del grafico grande? No solo se e' contro."""
    if f["bias dal grafico sopra"] is False or f["timeframe grandi contro"] - f["timeframe grandi a favore"] >= 2:
        return -1, "il grafico più grande va nella direzione opposta"
    return 1, "il grafico più grande non va contro di noi"


def _sconto(f):
    x = f["a sconto nella settimana"]
    if x is None:
        return 0, ""
    if x:
        return 1, _v(f, "compriamo nella metà bassa della settimana scorsa: a sconto",
                     "vendiamo nella metà alta della settimana scorsa: caro")
    return -1, _v(f, "compriamo nella metà alta della settimana scorsa: caro",
                  "vendiamo nella metà bassa della settimana scorsa: a sconto")


def _weekend(f):
    x = f["gap del weekend"]
    if x is None:
        return 0, ""
    return (1, "c'è da chiudere il buco del fine settimana, ed è nella nostra direzione") if x else \
        (-1, "c'è da chiudere il buco del fine settimana, ma è nella direzione opposta")


def _se(chiave, testo):
    return lambda f: (1, testo) if f[chiave] else (0, "")


def _rottura(f):
    if f["vera rottura di struttura"]:
        return 1, f"il prezzo ha anche rotto l'ultimo {_v(f, 'massimo', 'minimo')}: ha girato davvero"
    return 0, ""


def _contraria(f):
    if f["apertura della candela contraria toccata"]:
        return 1, ("il prezzo si è fermato sull'apertura dell'ultima candela contraria del grafico grande: "
                   + _v(f, "un supporto vero per Romeo", "una resistenza vera per Romeo"))
    return 0, ""


REGOLE: tuple[Regola, ...] = (
    # Cacciatore: il CRT stesso.
    Regola("candela 3", "Cacciatore", 1.5,
           "\"Avoid candle 2 as a beginner. Shift your entire focus on candle number three.\"",
           _candela, si="la finta confermata dalla chiusura", no="la finta non confermata"),
    Regola("candele interne", "Cacciatore", 0.5, "più candele interne dopo il range, meglio è",
           lambda f: (1, "dopo la candela di riferimento il prezzo è rimasto fermo qualche candela: ha caricato la molla")
           if f["candele interne"] >= 1 else (0, ""), si="le candele ferme prima"),
    Regola("candela 1 spessa", "Cacciatore", 0.5,
           "prima del key level di solito una candela spessa (la candela 1), poi la manipolazione",
           lambda f: (1, "la candela di riferimento è grande e va verso la zona importante")
           if f["corpo della candela 1"] <= -0.5 else (0, ""), si="la candela di riferimento grande"),
    Regola("micro dentro macro", "Cacciatore", 0.7, "\"There is always a micro CRT within the macro CRT.\"",
           _se("dentro un CRT più grande", "questo movimento sta dentro uno più grande nello stesso verso"),
           si="dentro un movimento più grande"),

    # Grilletto: l'entrata.
    Regola("turtle soup convincente", "Grilletto", 1.0, "\"You want to see them stab real hard into the old high.\"",
           _profondita, si="la finta profonda", no="la finta appena accennata"),
    Regola("candela spessa", "Grilletto", 1.0, "\"Thick up-close candle that liquidated an old high = bearish orderblock.\"",
           _spessore, si="la candela della finta grande", no="la candela della finta piccola"),
    Regola("FVG col Model#1", "Grilletto", 0.7, "\"If model number one comes with an FVG, it becomes a higher probability trade.\"",
           _se("fvg col Model#1", "la conferma è partita di scatto, lasciando un vuoto nel prezzo"),
           si="la conferma partita di scatto"),
    Regola("vera rottura di struttura", "Grilletto", 0.7,
           "\"Every single entry is either a model#1 or a true market structure shift.\"", _rottura,
           si="la rottura della struttura"),
    Regola("sotto l'apertura", "Grilletto", 1.0,
           "\"All the breakers, all the order blocks, all the turtle soups happen above and below the open.\"",
           _apertura, si="l'entrata dalla parte giusta dell'apertura", no="l'entrata dalla parte sbagliata dell'apertura"),
    Regola("SMT", "Grilletto", 0.7, "\"Only look for bullish SMTs in a higher time frame bullish market.\"", _smt,
           si="il mercato gemello che non conferma"),
    Regola("manipolazione a fine candela", "Grilletto", 0.5,
           "se la manipolazione avviene alla fine della candela prima, la candela dopo distribuisce subito",
           _se("manipolazione a fine candela", "la finta è arrivata alla fine della candela: di solito ora parte il movimento"),
           si="la finta a fine candela"),
    Regola("liquidità prima della manipolazione", "Grilletto", 0.5,
           "\"3. Mark a pre-manipulation swing high/low. 2 & 1 are more important than 3.\"",
           _se("liquidità presa prima", "la finta ha preso gli ordini lasciati prima (dove molti avevano lo stop)"),
           si="gli ordini presi prima"),

    # Livelli: stop e obiettivi.
    Regola("lato opposto", "Livelli", 1.0, "\"Your target is the opp. end of the range (1:3 in the very least).\"", _rr,
           si="un guadagno possibile grande", no="un guadagno possibile piccolo"),
    Regola("costi", "Livelli", 0.7, "il rischio si gestisce: niente operazioni mangiate dai costi", _costi,
           no="i costi alti"),
    Regola("strada libera fino al 50%", "Livelli", 1.0,
           "MOB: \"If respected, it will block the target… scratch the trade idea.\"", _mob, lista="draw_on_liquidity",
           si="la strada libera", no="un livello che blocca la strada"),

    # Key level.
    Regola("key level", "Key level", 2.0, "\"Trading CRT with no key level is a beginner mistake.\"", _key_level,
           lista="key_level", si="la zona importante del grafico grande", no="nessuna zona importante"),
    Regola("fondo finto", "Key level", 1.5,
           "andando verso un key level non toccato i CRT falliscono: \"they give you a fake bottom always\"", _fondo_finto,
           no="un livello mai toccato poco più in là"),
    Regola("si ferma sul livello", "Key level", 0.7,
           "il disegno del suo manuale: la manipolazione arriva alla linea del key level e crolla",
           _se("si ferma sul livello", "la finta si è fermata proprio sulla zona importante"),
           si="la finta ferma sulla zona"),
    Regola("apertura della candela contraria", "Key level", 0.7,
           "\"Look at down close candles as support, true support, and up close candles as resistance.\"", _contraria,
           si="l'apertura della candela contraria"),

    # Orario.
    Regola("ore di Romeo", "Orario", 2.0, "\"Time is more important than price.\" Londra 3-5, New York 9:30, 13:30.",
           _ore, lista="ore_giuste", si="le ore di Romeo", no="fuori dalle ore di Romeo"),
    Regola("golden candle time", "Orario", 0.5, "\"GCT: Golden candle time (9am-1pm NY time).\"",
           _se("golden candle time", "siamo fra le 9 e le 13 di New York, le ore migliori per Romeo"),
           si="fra le 9 e le 13 di New York"),
    Regola("giorno della settimana", "Orario", 0.7, "\"Tuesdays and Wednesdays are the highest probability days of the week.\"",
           _giorno, si="martedì o mercoledì", no="il venerdì"),
    Regola("estremo della settimana", "Orario", 0.7,
           "il massimo (o il minimo) della settimana si forma lunedì-mercoledì, l'altro estremo giovedì-venerdì", _settimana,
           si="l'estremo della settimana a inizio settimana"),

    # Bias.
    Regola("bias della candela del range", "Bias", 1.0,
           "\"Close above = higher prices. Close below = lower prices. Wick above = lower prices. Wick below = higher prices.\"",
           _bias_range, si="la candela di riferimento a favore", no="la candela di riferimento contro"),
    Regola("orderflow del grafico sopra", "Bias", 1.5, "\"Is it aligned with the HTF orderflow?\"", _orderflow,
           lista="orderflow_alto", si="il grafico grande non contro", no="il grafico grande contro"),
    Regola("obiettivo del grafico grande", "Bias", 1.5, "\"We ignore all bullish patterns on the way down to a bearish target.\"",
           _grandi, si="il movimento grande nello stesso verso", no="il movimento grande dall'altra parte"),
    Regola("range lows are for buying", "Bias", 0.5, "\"Range lows are for buying or watching only, not selling.\"",
           _sconto, si="il prezzo a sconto nella settimana", no="il prezzo caro nella settimana"),

    # Allineamento.
    Regola("grafici grandi d'accordo", "Allineamento", 1.0, "\"Pick bottoms in bullish markets. Don't pick tops in bullish markets.\"",
           _allineati, si="i grafici grandi d'accordo", no="i grafici grandi contro"),

    # Gap.
    Regola("FVG davanti", "Gap", 0.5, "il prezzo si muove per prendere liquidità o per riempire un vuoto",
           _se("FVG davanti", "verso l'obiettivo c'è un vuoto nel prezzo da riempire: il prezzo ci va volentieri"),
           si="un vuoto da riempire davanti"),
    Regola("FVG alle spalle", "Gap", 0.7, "un vuoto alle spalle può riportare il prezzo contro di noi",
           lambda f: (-1, "dietro di noi, vicino, c'è un vuoto nel prezzo: potrebbe tornarci") if f["FVG alle spalle vicino"] else (0, ""),
           no="un vuoto vicino alle spalle"),
    Regola("gap del weekend", "Gap", 0.5, "il gap del weekend tende a chiudersi", _weekend,
           si="il buco del weekend a favore", no="il buco del weekend contro"),
)

AGENTI = ("Cacciatore", "Grilletto", "Livelli", "Key level", "Orario", "Bias", "Allineamento", "Gap")
PER_NOME = {r.nome: r for r in REGOLE}
# La quarta domanda di Romeo (la conferma sul timeframe basso) e' il Model#1: c'e' sempre, e' da li'
# che nasce ogni occasione.
LISTA = ("key_level", "orderflow_alto", "draw_on_liquidity", "conferma_basso", "ore_giuste")

_NOMI_STRUMENTI = {"XAUUSD": "sull'oro", "XAGUSD": "sull'argento"}
_COPPIE = {"MN-D1": "sul mensile", "W1-H4": "sul settimanale", "D1-H1": "sul giornaliero", "H4-M15": "sulle 4 ore"}


def atomi(f: dict) -> list[str]:
    """I mattoni delle idee nuove: cosa dice ogni regola di Romeo su questa occasione, e i fatti
    semplici (strumento, grafico, tentativo, giorno, ora, verso). Un'idea nuova e' uno di questi, o
    due insieme."""
    fuori = []
    for r in REGOLE:
        try:
            esito, _ = r.guarda(f)
        except Exception:
            continue
        if esito:
            fuori.append(f"{r.nome}={int(esito)}")
    fuori += [f"strumento={f['strumento']}", f"coppia={f['coppia']}", f"colpo={f['colpo']}", f"giorno={f['giorno']}",
              f"ora={str(f['ora di New York'])[:2]}", f"verso={f['verso']}"]
    return fuori


def in_parole(atomo: str) -> str:
    """Un mattone in parole semplici, per dire l'idea su Telegram."""
    chi, _, valore = atomo.partition("=")
    if chi in PER_NOME:
        r = PER_NOME[chi]
        return (r.si if valore == "1" else r.no) or chi
    if chi == "strumento":
        return _NOMI_STRUMENTI.get(valore, f"su {valore}")
    if chi == "coppia":
        return _COPPIE.get(valore, valore)
    if chi == "colpo":
        return {"1": "al primo tentativo", "2": "al secondo tentativo"}.get(valore, "dal terzo tentativo in poi")
    if chi == "giorno":
        return f"di {valore}"
    if chi == "ora":
        return f"verso le {int(valore)} di New York"
    if chi == "verso":
        return "quando compriamo" if valore == "acquisto" else "quando vendiamo"
    return atomo


def di_chi(atomo: str) -> str:
    """Di quale agente e' il mestiere di un mattone."""
    chi = atomo.partition("=")[0]
    if chi in PER_NOME:
        return PER_NOME[chi].agente
    return "Orario" if chi in ("giorno", "ora") else "Cacciatore"
