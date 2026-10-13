"""I pareri della squadra: ognuno guarda l'occasione col suo mestiere e dice la sua, col perche'.

Il proprietario, 07/10/2026: *"Iniziamo a far sì che gli agenti ragionino realmente e che decidano realmente. Sono
una squadra. Ognuno dà le proprie opinioni e poi il capo decide ma tutti vengono presi in considerazione ... Che
restino fedeli alle loro previsioni e a ciò che analizzano ... L'agente rischio deve migliorarsi e il capo deve
selezionare i crt"*.

Ogni agente da' un voto da -2 (forte contro) a +2 (forte a favore) con le ragioni del suo mestiere, in parole
semplici. Il Capo pesa tutti i voti (`squadra.py`) e decide lui. Il Rischio non vota: decide quanto puntare.

Il Bias e' fedele alla sua previsione: la fa all'apertura del giorno (le 17 di New York) leggendo la candela
precedente di giorno, settimana, mese, 3 mesi e anno, e la tiene tutto il giorno. Non cambia idea a meta' giornata:
se il livello della previsione viene preso, la previsione e' compiuta e per quel giorno non spinge piu'.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from nvm.dati.candele import weekend, calendario
from nvm.dati.minuti import CHIUSURA, MASSIMO, MINIMO
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import NEW_YORK, ORDINE, TF, inizio_candela

# Chi vota, nell'ordine in cui parla in equipe.
VOTANO = ("Cacciatore", "Key level", "Bias", "Gap", "DXY", "Orario", "Livelli", "Grilletto")

TF_GRANDI = (TF.D1, TF.W1, TF.MN)
# I timeframe di cui il Bias legge la candela precedente, dal piu' grande (comanda) al piu' piccolo.
TF_PREVISIONE = (TF.Y1, TF.Q3, TF.MN, TF.W1, TF.D1)
NOMI = {TF.H1: "a 1 ora", TF.H4: "a 4 ore", TF.H6: "a 6 ore", TF.H12: "a 12 ore", TF.D1: "giornaliero",
        TF.W1: "settimanale", TF.MN: "mensile", TF.Q3: "dei 3 mesi", TF.S6: "dei 6 mesi", TF.Y1: "annuale"}
CANDELA = {TF.D1: "il giorno", TF.W1: "la settimana", TF.MN: "il mese", TF.Q3: "il trimestre", TF.Y1: "l'anno"}

# Spread e commissione, in parte del rischio.
COSTO_ALTO = 0.15
COSTO_TROPPO = 0.30
# Un TP1 oltre 3 volte il rischio arriva di rado (la riunione del sabato: *"primo target oltre 3 R" 0 su 5*).
TP1_LONTANO = 3.0


QUANTO = {2: "Forte a favore", 1: "A favore", 0: "Neutro", -1: "Contro", -2: "Forte contro"}


def _segno(voto: int) -> str:
    return "✅" if voto > 0 else "❌" if voto < 0 else "➖"


@dataclass
class Parere:
    agente: str
    voto: int
    ragioni: list[str] = field(default_factory=list)
    # Cosa ha visto, in breve: serve ai colleghi nel secondo giro ("inside bar", "rsi"...).
    segni: set = field(default_factory=set)
    # Il voto del primo giro (solo il suo mestiere) e cosa ha detto dopo aver sentito un collega.
    primo: Optional[int] = None
    sentito: str = ""
    # Un no che il Capo non puo' superare: la squadra non va contro la sua previsione della domenica.
    veto: str = ""

    @property
    def segno(self) -> str:
        return _segno(self.voto)

    def frase(self) -> str:
        primo = self.voto if self.primo is None else self.primo
        testo = "; ".join(self.ragioni) if self.ragioni else "niente di particolare dal mio mestiere"
        fuori = f"{_segno(primo)} {QUANTO[primo]} ({primo:+d}). {testo[:1].upper() + testo[1:]}."
        if self.sentito:
            fuori += f" 🔁 {self.sentito}: passo a {self.voto:+d}."
        return fuori


@dataclass
class Previsione:
    """La previsione del Bias su uno strumento, fatta all'apertura del giorno e tenuta fino a sera."""
    giorno: int                 # l'apertura del giorno (le 17 di New York), UTC
    verso: int                  # +1 rialzista, -1 ribassista, 0 nessuna direzione
    livello: Optional[float] = None
    tf: Optional[str] = None
    tipo: str = ""              # "accetta" o "turtle soup"
    motivo: str = ""            # perche', in parole semplici

    @property
    def testo(self) -> str:
        if not self.verso:
            return f"nessuna direzione: {self.motivo}" if self.motivo else "nessuna direzione"
        return f"{'⬆ rialzista' if self.verso > 0 else '⬇ ribassista'} verso {_numero(self.livello)}: {self.motivo}"

    def come_dati(self) -> dict:
        return {"giorno": self.giorno, "verso": self.verso, "livello": self.livello, "tf": self.tf, "tipo": self.tipo,
                "motivo": self.motivo}

    @classmethod
    def da_dati(cls, d: dict) -> "Previsione":
        return cls(int(d["giorno"]), int(d["verso"]), d.get("livello"), d.get("tf"), d.get("tipo", ""),
                   d.get("motivo", ""))


@dataclass
class Contesto:
    """Quello che la squadra sa oltre l'occasione."""
    # La previsione della domenica (`fine_settimana.domenica`): strumento -> "rialzista" / "ribassista". Per gli
    # strumenti che non ci sono, il Bias la rilegge lui dalla candela della settimana (`settimana`).
    domenica: dict = field(default_factory=dict)


def _numero(x: Optional[float]) -> str:
    if x is None or not math.isfinite(x):
        return "?"
    return f"{x:,.5g}".replace(",", "§").replace(".", ",").replace("§", ".")


def _virgola(x: float, cifre: int = 2) -> str:
    return f"{x:.{cifre}f}".replace(".", ",")


def _ny(t: int) -> datetime:
    return datetime.fromtimestamp(int(t), tz=NEW_YORK)


def apertura_giorno(t: int, strumento: str = "") -> int:
    """L'apertura del giorno di sessione (le 17 di New York; per le crypto la mezzanotte UTC) che contiene `t`."""
    return int(inizio_candela(np.array([int(t)], np.int64), TF.D1, calendario(strumento))[0])


# --- il Bias: la previsione del giorno -------------------------------------------------------------------

def segnale(q, tf: TF, t: int) -> Optional[tuple]:
    """Cosa dice la candela precedente di `tf` a `t`: (verso, livello, compiuto, tipo, indice) o None.

    - ha chiuso oltre la candela prima (accetta): va a prendere il suo estremo (le foto del proprietario);
    - ha preso un lato e richiuso dentro (turtle soup): va dall'altra parte, almeno al 50% della candela prima
      (Romeo: *"a candle that receives a turtle soup almost always goes at least to the 50%"*);
    - inside bar: vale la candela prima; ha preso tutti e due i lati: niente.
    Compiuto: il prezzo ha gia' preso il livello (dalla chiusura della candela fino a `t`)."""
    c = q.candele.get(tf)
    if c is None or len(c) < 2:
        return None
    j = int(np.searchsorted(c.fine, t, side="right")) - 1
    for _ in range(4):
        if j < 1:
            return None
        p, x = c.bid[j - 1], c.bid[j]
        if x[CHIUSURA] > p[MASSIMO]:
            verso, livello, tipo = 1, float(x[MASSIMO]), "accetta"
            break
        if x[CHIUSURA] < p[MINIMO]:
            verso, livello, tipo = -1, float(x[MINIMO]), "accetta"
            break
        su, giu = x[MASSIMO] > p[MASSIMO], x[MINIMO] < p[MINIMO]
        if su and not giu:
            verso, livello, tipo = -1, float((p[MASSIMO] + p[MINIMO]) / 2), "turtle soup"
            break
        if giu and not su:
            verso, livello, tipo = 1, float((p[MASSIMO] + p[MINIMO]) / 2), "turtle soup"
            break
        if not su and not giu:
            j -= 1
            continue
        return None
    else:
        return None
    x = c.bid[j]
    if tipo == "turtle soup" and ((x[CHIUSURA] <= livello) if verso < 0 else (x[CHIUSURA] >= livello)):
        return verso, livello, True, tipo, j
    return verso, livello, preso(q, verso, livello, int(c.fine[j]), t), tipo, j


def preso(q, verso: int, livello: float, dal: int, al: int) -> bool:
    """Il prezzo ha toccato `livello` (sopra se `verso` > 0, sotto se < 0) fra `dal` e `al`, sulle orarie."""
    ore = q.ore
    a = int(np.searchsorted(ore.inizio, dal))
    b = int(np.searchsorted(ore.inizio, al))
    if b <= a:
        return False
    if verso > 0:
        return bool(ore.bid[a:b, MASSIMO].max() >= livello)
    return bool(ore.bid[a:b, MINIMO].min() <= livello)


def previsione(q, t: int) -> Previsione:
    """La previsione del Bias per il giorno che contiene `t`, con le sole candele chiuse alla sua apertura: comanda
    il timeframe piu' grande con un movimento non ancora compiuto (Romeo: *"the higher timeframe is always more
    important"*; il proprietario: *"la candela trimestrale ha accettato a ribasso quindi ci aspettiamo che il minimo
    trimestrale venga preso e solo dopo ha senso cercare buy"*)."""
    giorno = apertura_giorno(t, q.strumento)
    for tf in TF_PREVISIONE:
        x = segnale(q, tf, giorno)
        if x is None or x[2]:
            continue
        verso, livello, _, tipo, _ = x
        come = ((f"ha chiuso {'sopra il massimo' if verso > 0 else 'sotto il minimo'} della candela prima")
                if tipo == "accetta" else
                (f"ha preso il {'minimo' if verso > 0 else 'massimo'} della candela prima e ha richiuso dentro "
                 "(turtle soup)"))
        return Previsione(giorno, verso, livello, tf.value, tipo, f"{CANDELA.get(tf, NOMI[tf])} {come}")
    return Previsione(giorno, 0, None, None, "", "i movimenti dei timeframe grandi sono già compiuti")


def settimana(q, t: int) -> Optional[str]:
    """La previsione della domenica per la settimana che contiene `t` (`fine_settimana.previsione`, V14 24:04): la
    candela della settimana passata rispetto a quella prima. "rialzista", "ribassista" o None."""
    from nvm.agenti.conferme import Bias as B, bias as bias_candela
    c = q.candele.get(TF.W1)
    if c is None or len(c) < 2:
        return None
    inizio = int(inizio_candela(np.array([int(t)], np.int64), TF.W1, calendario(q.strumento))[0])
    k = int(np.searchsorted(c.fine, inizio, side="right")) - 1
    if k < 1:
        return None
    return {B.RIALZISTA: "rialzista", B.RIBASSISTA: "ribassista"}.get(bias_candela(c.bid[k - 1], c.bid[k]))


def compiuta(q, p: Previsione, t: int) -> bool:
    """Il livello della previsione e' stato preso fra l'apertura del giorno e `t`."""
    if not p.verso or p.livello is None:
        return False
    return preso(q, p.verso, float(p.livello), p.giorno, t)


# --- i pareri ---------------------------------------------------------------------------------------

def _voto(punti: float) -> int:
    return int(max(-2, min(2, round(punti + (1e-9 if punti > 0 else -1e-9 if punti < 0 else 0)))))


def _ordina(ragioni: list[tuple[float, str]]) -> list[str]:
    return [r for _, r in sorted(ragioni, key=lambda x: -abs(x[0]))]


def cacciatore(s, allineati) -> Parere:
    """Il CRT: se altri timeframe fanno il CRT nello stesso verso, se il range ha caricato (inside bar)."""
    punti, rag = 0.0, []
    if allineati:
        punti += 1
        rag.append((1, f"anche il CRT {', '.join(NOMI.get(x, x.value) for x in allineati[:3])} va nello stesso verso"))
    if s.dentro:
        punti += 0.5
        rag.append((0.5, f"il range è una candela madre con {s.dentro} inside bar: il prezzo ha caricato"))
    if not rag:
        rag.append((0, f"CRT {NOMI.get(s.tf, s.tf.value)}, senza altri timeframe allineati"))
    return Parere("Cacciatore", _voto(punti), _ordina(rag), segni={"inside bar"} if s.dentro else set())


def key_level(s) -> Parere:
    """Il key level preso dalla finta: piu' e' grande il periodo, piu' liquidita' c'era."""
    veri = [l for l in s.presi if not l.oggi]
    rag, punti = [], 0.0
    if not veri:
        if s.presi:
            return Parere("Key level", -1, ["la finta ha preso solo un livello di oggi, non del periodo prima"])
        return Parere("Key level", -1, ["la finta non ha preso un key level"])
    grande = max(veri, key=lambda l: ORDINE.index(l.tf))
    if grande.tf in (TF.Q3, TF.S6, TF.Y1):
        punti += 2
        rag.append((2, f"ha preso il {grande.nome} ({_numero(grande.prezzo)}): liquidità di mesi"))
    elif grande.tf in (TF.W1, TF.MN):
        punti += 1
        rag.append((1, f"ha preso il {grande.nome} ({_numero(grande.prezzo)})"))
    else:
        rag.append((0, f"ha preso solo il {grande.nome}: un key level normale"))
    tfs = {l.tf for l in veri}
    if len(tfs) >= 2:
        punti += 0.5
        rag.append((0.5, f"ne ha presi {len(tfs)} insieme"))
    return Parere("Key level", _voto(punti), _ordina(rag))


def bias(s, q, p: Optional[Previsione], domenica: Optional[str], p_dxy: Optional[Previsione] = None,
         qd=None, domenica_dxy: Optional[str] = None) -> Parere:
    """Fedele alla previsione del giorno (e a quella della domenica): a favore se l'operazione va dove ha detto,
    contro se va dall'altra parte. Non cambia idea a meta' giornata.

    Sulle coppie forex col dollaro comanda il DXY (il proprietario, 08/10/2026: *"il dxy comanda la bias di tutti gli
    asset forex usd"*): la previsione del giorno del DXY (`p_dxy`, sul suo grafico `qd`) pesa 2 e quella della coppia
    conta solo se il DXY oggi non ha una direzione; la domenica vale quella del DXY (`domenica_dxy`); e nei timeframe
    alti il DXY e' ribassista (`foto.FONDO_DXY`), che pesa 1."""
    from nvm.agenti import foto
    segno = -1 if s.short else 1
    rag, punti = [], 0.0
    col_dxy = foto.segno_col_dxy(s.strumento) if s.strumento in foto.FOREX_DOLLARO else 0
    dxy_decide = False
    if col_dxy:
        f = foto.FONDO_DXY * col_dxy
        dove = "su" if f > 0 else "giù"
        rag.append((f * segno, f"nei timeframe alti ci aspettiamo il DXY "
                               f"{'ribassista' if foto.FONDO_DXY < 0 else 'rialzista'} nei prossimi anni: "
                               f"{s.strumento} di fondo va {dove}"))
        punti += f * segno
    if col_dxy and p_dxy is not None and qd is not None:
        if not p_dxy.verso:
            rag.append((0, f"il DXY oggi non ha una direzione ({p_dxy.motivo})" if p_dxy.motivo
                        else "il DXY oggi non ha una direzione"))
        elif compiuta(qd, p_dxy, s.n3_inizio):
            rag.append((0, f"la previsione di oggi sul DXY ({p_dxy.testo}) si è già compiuta"))
        else:
            dxy_decide = True
            v = p_dxy.verso * col_dxy
            dove = "sale" if p_dxy.verso > 0 else "scende"
            if v == segno:
                punti += 2
                rag.append((2, f"il DXY all'apertura del giorno l'ho detto {p_dxy.testo}: se il dollaro {dove}, "
                               f"{s.strumento} va dove va l'operazione"))
            else:
                punti -= 2
                rag.append((-2, f"il DXY all'apertura del giorno l'ho detto {p_dxy.testo}: se il dollaro {dove}, "
                                f"{s.strumento} va contro l'operazione"))
    if p is not None and p.verso and not dxy_decide:
        if compiuta(q, p, s.n3_inizio):
            rag.append((0, f"la mia previsione di oggi ({p.testo}) si è già compiuta: per oggi non ho più una direzione"))
        elif p.verso == segno:
            punti += 2
            rag.append((2, f"all'apertura del giorno ho detto {p.testo}: l'operazione va dove ho detto"))
        else:
            punti -= 2
            rag.append((-2, f"all'apertura del giorno ho detto {p.testo}: resto della mia idea, questa va contro"))
    elif p is not None and not dxy_decide:
        rag.append((0, f"per oggi non ho una direzione: {p.motivo}" if p.motivo else "per oggi non ho una direzione"))
    veto = ""
    da = ""
    if col_dxy and domenica_dxy in ("rialzista", "ribassista"):
        v = (1 if domenica_dxy == "rialzista" else -1) * col_dxy
        domenica = "rialzista" if v > 0 else "ribassista"
        da = f" (il DXY domenica l'abbiamo detto {domenica_dxy})"
    if domenica in ("rialzista", "ribassista"):
        v = 1 if domenica == "rialzista" else -1
        if v == segno:
            punti += 0.5
            rag.append((0.5, f"e domenica la settimana di {s.strumento} l'abbiamo detta {domenica}{da}"))
        else:
            # Il proprietario, 07/10/2026: la squadra non deve andare contro le previsioni che fa la domenica.
            punti -= 4
            veto = (f"domenica abbiamo detto {s.strumento} {domenica} per la settimana{da}: non andiamo contro la "
                    "nostra previsione")
            rag.append((-4, veto))
    segni = {"contro previsione"} if punti < 0 else set()
    return Parere("Bias", _voto(punti), _ordina(rag), segni=segni, veto=veto)


def gap(s, q, ob, dentro) -> Parere:
    """I gap: se la finta e' dentro un gap che ci spinge, se il target e' un gap intatto, se c'e' un gap contro
    davanti al TP1."""
    from nvm.agenti import foto
    rag, punti, segni = [], 0.0, set()
    g, f = dentro
    if g is not None:
        punti += 1
        segni.add("gap a favore")
        rag.append((1, f"la finta è entrata nel {g.nome} ({_numero(g.basso)}–{_numero(g.alto)}), che ci spinge"))
        if f is not None and getattr(f, "divergenza", False):
            punti += 0.5
            segni.add("rsi")
            rag.append((0.5, "e l'RSI conferma la continuazione"))
    if ob is not None and ob.tipo == "gap":
        punti += 0.5
        segni.add("target gap")
        rag.append((0.5, f"il target finale è un gap intatto ({_numero(ob.prezzo)})"))
    contro = foto.gap_contro(q, s)
    if contro:
        punti -= 1
        rag.append((-1, f"prima del TP1 c'è un {contro[0].nome} già toccato che spinge contro di noi"))
    if not rag:
        rag.append((0, "nessun gap che ci spinge o ci frena"))
    return Parere("Gap", _voto(punti), _ordina(rag), segni=segni)


def dxy(s, sd) -> Parere:
    """Il dollaro (il grafico USDX del broker). Sulle coppie forex col dollaro la correlazione e' piena e il DXY pesa
    2; su oro, argento, S&P 500, Dow e Nasdaq e' circa l'85% (*"a volte può capitare che il DXY va long e anche gold
    esempio va long"*) e pesa 1 (la foto delle correlazioni del proprietario, 08/10/2026)."""
    from nvm.agenti import foto
    if getattr(s, "dal_totale", False):
        return Parere("DXY", 2, ["il setup l'ha fatto la TOTAL: quando si muove tutto il mercato crypto, BTC ed ETH "
                                 "lo seguono"])
    if s.strumento not in foto.DOLLARO_SOTTO + foto.DOLLARO_SOPRA:
        return Parere("DXY", 0, [f"{s.strumento} non è legato al dollaro"])
    forex = s.strumento in foto.FOREX_DOLLARO
    peso = 2 if forex else 1
    nota = "" if forex else " (con il dollaro va di solito al contrario, non sempre)"
    if s.dal_dxy:
        return Parere("DXY", peso, ["il setup l'ha fatto il DXY: quando il dollaro si muove le coppie forex lo seguono"])
    if sd is None:
        return Parere("DXY", 0, ["il DXY adesso non fa un CRT"])
    verso = foto.verso_dal_dxy(s.strumento, sd.verso)
    if verso is s.verso:
        return Parere("DXY", peso, [f"il DXY fa il CRT {NOMI.get(sd.tf, '')} che ci dà ragione{nota}"])
    return Parere("DXY", -peso, [f"il DXY fa il CRT {NOMI.get(sd.tf, '')} dall'altra parte{nota}"])


def orario(s) -> Parere:
    """L'ora dell'entrata: le sessioni di Romeo, le ore asiatiche, il venerdi'."""
    if s.tf in TF_GRANDI:
        apre = "a mezzanotte UTC" if weekend(s.strumento) else "alle 17 di New York"
        return Parere("Orario", 0, [f"la candela 3 del CRT {NOMI[s.tf]} apre {apre}: l'ora la fa il grafico"])
    ny = _ny(s.n3_inizio)
    h, giorno = ny.hour, ny.weekday()
    rag, punti = [], 0.0
    fam = STRUMENTI[s.strumento].famiglia if s.strumento in STRUMENTI else "forex"
    asiatica = any(v in s.strumento for v in ("JPY", "AUD", "NZD"))
    if 2 <= h < 5:
        punti += 1
        rag.append((1, f"sono le {h} di New York: sessione di Londra, le ore di Romeo"))
    elif 8 <= h < 11:
        punti += 1
        rag.append((1, f"sono le {h} di New York: la mattina di New York, le ore di Romeo"))
    elif (h >= 18 or h < 2) and not asiatica and fam == "forex":
        punti -= 1
        rag.append((-1, "ore asiatiche su una coppia che non è asiatica: consolidamento"))
    else:
        rag.append((0, f"sono le {h} di New York: ore normali"))
    if giorno == 4 and h >= 12:
        punti -= 1
        rag.append((-1, "è venerdì pomeriggio: il mercato si svuota prima del fine settimana"))
    return Parere("Orario", _voto(punti), _ordina(rag))


def livelli(s, ob, costo_erre: float) -> Parere:
    """I costi e i target: i costi non devono mangiare il rischio, il TP1 deve essere raggiungibile."""
    rischio = abs(s.ingresso - s.stop)
    amp = s.range_alto - s.range_basso
    rag, punti = [], 0.0
    if rischio <= 0 or amp <= 0:
        return Parere("Livelli", -2, ["lo stop non è dalla parte giusta"])
    costo = (s.spread + 0.0) / rischio + costo_erre
    rr1 = abs(s.tp1 - s.ingresso) / rischio
    if costo >= COSTO_TROPPO:
        punti -= 2
        rag.append((-2, f"spread e commissione si mangiano {_virgola(costo)} volte il rischio"))
    elif costo >= COSTO_ALTO:
        punti -= 1
        rag.append((-1, f"spread e commissione pesano {_virgola(costo)} volte il rischio"))
    if rr1 > TP1_LONTANO:
        punti -= 1
        rag.append((-1, f"il TP1 è a {_virgola(rr1, 1)} volte il rischio: lontano, ci arriva di rado"))
    if ob is not None and ob.tipo in ("gap", "key level") and not rag:
        rag.append((0, f"target finale {ob.nome} ({_numero(ob.prezzo)})"))
    if not rag:
        rag.append((0, f"TP1 a {_virgola(rr1, 1)} volte il rischio"))
    return Parere("Livelli", _voto(punti), _ordina(rag))


def grilletto(s) -> Parere:
    """Come la candela 2 ha fatto la finta: quanto e' rientrata nel range, se e' andata troppo oltre."""
    amp = s.range_alto - s.range_basso
    if amp <= 0:
        return Parere("Grilletto", 0, [])
    rientro = ((s.range_alto - s.n2_chiusura) if s.short else (s.n2_chiusura - s.range_basso)) / amp
    finta = ((s.n2_alto - s.range_alto) if s.short else (s.range_basso - s.n2_basso)) / amp
    rag, punti = [], 0.0
    if rientro >= 0.25:
        punti += 1
        rag.append((1, f"la candela 2 ha richiuso ben dentro il range ({round(100 * rientro)}%): il rifiuto è chiaro"))
    elif rientro < 0.10:
        punti -= 1
        rag.append((-1, f"la candela 2 ha richiuso appena dentro il range ({round(100 * rientro)}%): il rifiuto è debole"))
    if finta > 1.0:
        punti -= 1
        rag.append((-1, f"la finta è andata oltre il range di {_virgola(finta, 1)} volte la sua ampiezza: sembra più "
                        "una spinta che una finta"))
    if not rag:
        rag.append((0, f"la candela 2 ha richiuso dentro il range del {round(100 * rientro)}%: un rifiuto normale"))
    return Parere("Grilletto", _voto(punti), _ordina(rag))


# --- il secondo giro: si sentono fra colleghi --------------------------------------------------------------

# Chi ascolta chi, quando, di quanto cambia, e perche' (le regole che legano i mestieri, dal metodo). Se dal vivo
# sentire un collega non aiuta, quell'ascolto si spegne (`squadra.py`).
def _ascolti():
    def p(x, a):
        return next(y for y in x if y.agente == a)
    return (
        ("Cacciatore", "Bias", lambda x: p(x, "Bias").voto <= -2 and p(x, "Cacciatore").voto > 0, -1,
         "il mio CRT va contro la sua previsione, e il comando lo dà il grafico grande"),
        ("Bias", "Gap", lambda x: p(x, "Bias").voto == 0 and p(x, "Gap").voto >= 1, 1,
         "senza una mia direzione, il gap che ci spinge conta (il CRT a supporto di gap, cartella 5)"),
        ("Bias", "DXY", lambda x: p(x, "DXY").voto <= -1 and p(x, "Bias").voto > 0, -1,
         "il dollaro va dall'altra parte: la mia previsione regge meno"),
        ("Gap", "Bias", lambda x: p(x, "Gap").voto >= 1 and p(x, "Bias").voto <= -2, -1,
         "il gap ci spinge, ma la previsione è contro: il gap può aspettare"),
        ("Key level", "Cacciatore", lambda x: "inside bar" in p(x, "Cacciatore").segni and 0 <= p(x, "Key level").voto < 2,
         1, "dopo le inside bar la finta prende più liquidità"),
        ("Livelli", "Gap", lambda x: {"rsi", "target gap"} <= p(x, "Gap").segni and p(x, "Livelli").voto < 2, 1,
         "con l'RSI che conferma la continuazione il target sul gap arriva più spesso"),
    )


ASCOLTI = _ascolti()


def chiave_ascolto(chi: str, da: str) -> str:
    return f"{chi} sente {da}"


def confronto(pareri: list[Parere], spenti=()) -> list[tuple[str, int]]:
    """Il secondo giro: ognuno sente i colleghi e, se il loro mestiere tocca il suo, cambia il voto e dice perche'
    (al massimo una volta, sentendo uno solo). Restituisce gli ascolti usati e di quanto hanno cambiato il voto."""
    primi = [Parere(x.agente, x.voto, x.ragioni, x.segni) for x in pareri]
    usati = []
    for chi, da, quando, quanto, perche in ASCOLTI:
        k = chiave_ascolto(chi, da)
        if k in spenti:
            continue
        try:
            vale = quando(primi)
        except StopIteration:
            continue
        x = next((y for y in pareri if y.agente == chi), None)
        if not vale or x is None or x.sentito:
            continue
        nuovo = max(-2, min(2, x.voto + quanto))
        if nuovo == x.voto:
            continue
        x.primo, x.voto = x.voto, nuovo
        x.sentito = f"Sentito {'il ' if da in ('Bias', 'Gap', 'DXY', 'Cacciatore', 'Grilletto', 'Rischio') else ''}{da}: {perche}"
        usati.append((k, quanto))
    return usati


def tutti(d, ctx: Contesto, p: Optional[Previsione], p_dxy: Optional[Previsione] = None) -> list[Parere]:
    """I pareri di tutta la squadra sull'occasione delle foto `d` (`giro.occasioni_foto`)."""
    from nvm.agenti import foto
    from nvm.intelligenti.metodo import _gap_a_favore
    info = d.foto
    s, q, ob = info["setup"], info["quadro"], info["obiettivo"]
    allineati = list(info.get("allineati", [])) + [t for t in foto.allineati(q, s) if t not in info.get("allineati", [])]
    costo = float(getattr(d.r, "costo_erre", 0.0) or 0.0)
    domenica = ctx.domenica.get(s.strumento) or settimana(q, s.n3_inizio)
    qd = info.get("quadro_dxy")
    domenica_dxy = (ctx.domenica.get("DXY") or settimana(qd, s.n3_inizio)) if qd is not None else None
    return [cacciatore(s, allineati), key_level(s), bias(s, q, p, domenica, p_dxy, qd, domenica_dxy),
            gap(s, q, ob, _gap_a_favore(q, s)), dxy(s, info.get("dxy")), orario(s), livelli(s, ob, costo),
            grilletto(s)]
