"""Il metodo di Romeo dai 17 video: le domande prima di ogni operazione (`spec/metodo_romeo.md`).

Ogni domanda dice di chi e' il mestiere, da quale video e minuto viene, la risposta (si' o no) e il
perche' in parole semplici (sono le frasi che arrivano su Telegram).

- Le **obbligatorie** sono il metodo: se anche una sola dice no, Romeo non entra, e non entriamo
  nemmeno noi. La squadra non le disimpara.
- Le **confluenze** sono i punti in piu' (*"it's a game of stacking confluences"*, V11 08:09): la
  squadra impara dal vivo quanto conta ognuna.

Tutto si calcola con le sole candele gia' chiuse al momento dell'entrata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import SOPRA, Bias, Contesto
from nvm.agenti.grilletto import MODELLI_ROMEO, SPESSORE
from nvm.dati.candele import Candele, costruisci, weekend
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import NEW_YORK, ORDINE as ORDINE_TF, TF, fine_candela, scarti_ny

GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
NOMI_TF = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H4: "a 4 ore", TF.H1: "orario"}
NOMI_COPPIA = {"MN-D1": "la candela del mese", "W1-H4": "la candela della settimana",
               "D1-H1": "la candela del giorno", "H4-M15": "la candela delle 4 ore"}

# I mercati gemelli per l'SMT, solo quelli che dice Romeo (V8 22:00): l'euro con la sterlina (il DXY i
# broker di solito non ce l'hanno), gli indici americani fra loro, Bitcoin ed Ethereum, oro e argento.
GEMELLI = {"EURUSD": ("GBPUSD", 1), "GBPUSD": ("EURUSD", 1), "XAUUSD": ("XAGUSD", 1), "XAGUSD": ("XAUUSD", 1),
           "SPX500": ("NAS100", 1), "NAS100": ("SPX500", 1), "US30": ("NAS100", 1),
           "BTCUSD": ("ETHUSD", 1), "ETHUSD": ("BTCUSD", 1)}
# La manipolazione "alla fine della candela" (V8 07:28): nell'ultimo quarto della candela 2.
FINE_CANDELA = 0.75


@dataclass
class Domanda:
    nome: str
    agente: str
    video: str
    si: Optional[bool]
    perche: str

    def riga(self) -> str:
        segno = "✅" if self.si else "❌" if self.si is False else "➖"
        return f"{segno} {self.perche}"


@dataclass
class Metodo:
    obbligatorie: list[Domanda] = field(default_factory=list)
    confluenze: list[Domanda] = field(default_factory=list)
    # I fatti semplici dell'occasione, per le idee nuove della squadra.
    fatti: dict = field(default_factory=dict)
    # Quello che vede ogni agente, in numeri: e' da qui che ognuno impara il suo giudizio (`squadra.py`).
    numeri: dict = field(default_factory=dict)

    @property
    def a_piu(self) -> bool:
        """Tutte le obbligatorie dicono si': l'operazione A+ di Romeo."""
        return bool(self.obbligatorie) and all(d.si for d in self.obbligatorie)

    @property
    def mancano(self) -> list[Domanda]:
        return [d for d in self.obbligatorie if not d.si]

    @property
    def presenti(self) -> list[str]:
        return [d.nome for d in self.confluenze if d.si]

    def atomi(self) -> list[str]:
        """I mattoni delle idee nuove: le confluenze presenti e i fatti semplici."""
        f = self.fatti
        return [f"{n}=1" for n in self.presenti] + [
            f"strumento={f.get('strumento')}", f"coppia={f.get('coppia')}", f"giorno={f.get('giorno')}",
            f"ora={f.get('ora')}", f"verso={f.get('verso')}", f"modello={f.get('modello')}"]


def _ny(t: int) -> datetime:
    return datetime.fromtimestamp(int(t), tz=NEW_YORK)


def _ore_toccate(inizio: int, fine: int) -> set[int]:
    passi = np.arange(inizio, max(fine, inizio + 1), 900, dtype=np.int64)
    return set(((passi + scarti_ny(passi)) % 86400 // 3600).tolist())


def _intatti(sopra: Candele, verso_basso: bool, quante: int = 30) -> np.ndarray:
    """I minimi (o massimi) delle ultime candele del grafico sopra mai ripresi dopo."""
    b = sopra.bid[max(0, len(sopra) - quante):]
    fuori = []
    for j in range(len(b)):
        dopo = b[j + 1:]
        if verso_basso:
            if not len(dopo) or dopo[:, MINIMO].min() > b[j, MINIMO]:
                fuori.append(b[j, MINIMO])
        elif not len(dopo) or dopo[:, MASSIMO].max() < b[j, MASSIMO]:
            fuori.append(b[j, MASSIMO])
    return np.array(fuori, float)


def _v(short: bool, compra: str, vende: str) -> str:
    return vende if short else compra


def _numero(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def valuta(d, ore, quarti=None, gemello=None) -> Metodo:
    """Le domande di Romeo sull'occasione `d` (una `giro.Decisione` nata dalla candela 3).

    `ore` sono le orarie dello strumento, `quarti` i 15 minuti (per la coppia 4 ore -> 15 minuti),
    `gemello` le orarie dello strumento gemello e il verso della relazione (per l'SMT)."""
    r, op = d.r, d.op
    s = r.scatto
    crt = s.crt
    q = int(s.quando)
    short = r.verso is Verso.SHORT
    segno = -1 if short else 1
    amp = crt.crt_high - crt.crt_low
    base = quarti if (r.basso_tf is TF.M15 and quarti is not None) else ore
    alte = costruisci(base, r.alto_tf).chiuse_entro(q)
    basse = costruisci(base, r.basso_tf).chiuse_entro(q)
    tf_sopra = SOPRA[r.alto_tf]
    sopra = costruisci(ore, tf_sopra).chiuse_entro(q)
    estremo = crt.estremo_a(q)
    estremo = float(estremo) if estremo is not None else (crt.crt_high if short else crt.crt_low)
    coppia = f"{r.alto_tf.value}-{r.basso_tf.value}"
    candela = NOMI_COPPIA.get(coppia, "la candela")
    ny = _ny(q)
    m = Metodo(fatti={"strumento": r.strumento, "coppia": coppia, "verso": "vendita" if short else "acquisto",
                      "giorno": GIORNI[ny.weekday()], "ora": f"{ny.hour:02d}"})
    ob, co = m.obbligatorie, m.confluenze

    # 1. Candela 3 (Cacciatore).
    modello = getattr(s, "modello", "")
    kod = modello == "kiss of death"
    c3 = modello in MODELLI_ROMEO
    ob.append(Domanda("candela 3", "Cacciatore", "V5 00:31, V9 05:58", c3,
                      f"{candela} di prima ha fatto la finta ed è già chiusa dentro il range: entriamo nella "
                      "candela 3, come vuole Romeo" if c3 else
                      "siamo ancora nella candela della finta: Romeo dice di aspettare che chiuda"))

    # 2. La finta oltre l'apertura della candela 3 (Grilletto): l'apertura di Romeo, a mezzanotte di New
    # York per giorno, settimana e mese (V1 21:31). Il kiss of death viene dopo il 50%: la sua finta e'
    # l'ultimo turtle soup prima dell'obiettivo (V4 06:30).
    a3 = getattr(s, "apertura_3", None)
    estremo_finta = s.punta if getattr(s, "punta", None) is not None else s.livello
    if kod:
        oltre = True
        perche = (_v(short, "il prezzo ha già preso il 50% e ora fa l'ultima finta in giù, sotto un vecchio minimo: "
                           "il kiss of death prima dell'obiettivo", "il prezzo ha già preso il 50% e ora fa l'ultima "
                           "finta in su, sopra un vecchio massimo: il kiss of death prima dell'obiettivo"))
    else:
        oltre = a3 is not None and (estremo_finta >= a3 if short else estremo_finta <= a3)
        perche = (_v(short, "la finta è scesa sotto il prezzo di apertura della candela 3 (mezzanotte di New York): "
                            "compriamo a sconto",
                     "la finta è salita sopra il prezzo di apertura della candela 3 (mezzanotte di New York): vendiamo caro")
                  if oltre else
                  _v(short, "la finta non è scesa sotto l'apertura della candela 3: non è a sconto",
                     "la finta non è salita sopra l'apertura della candela 3: non è caro"))
    ob.append(Domanda("oltre l'apertura", "Grilletto", "V1 21:31, V9 06:31, V4 06:30", oltre, perche))

    # 3. Il modello d'entrata (Grilletto): Model#1 con la candela spessa che si infila in un vecchio massimo
    # e la chiusura oltre il corpo, o la vera rottura di struttura col ritorno nella zona (V11 14:30).
    k = float(getattr(s, "spessore", 0.0))
    if modello == "vera rottura":
        entrata = True
        perche = (f"il prezzo ha fatto la finta su un vecchio {_v(short, 'minimo', 'massimo')}, ha rotto la struttura "
                  f"chiudendo oltre il {_v(short, 'massimo', 'minimo')} che l'aveva fatta, ed è tornato nella zona: "
                  "è la seconda entrata di Romeo (vera rottura di struttura), stop al turtle soup")
    else:
        entrata = k >= SPESSORE
        perche = (f"la candela della finta si è infilata in un vecchio {_v(short, 'minimo', 'massimo')}, è spessa "
                  f"({_numero(k)} volte il normale) e il prezzo ha chiuso {_v(short, 'sopra', 'sotto')} il suo corpo: "
                  "è la conferma di Romeo (Model#1)" if entrata else
                  "la candela della finta è sottile: Romeo si fida solo di quella spessa")
    ob.append(Domanda("modello d'entrata", "Grilletto", "V1 37:32, V3 10:00, V11 14:30", entrata, perche))
    m.fatti["modello"] = modello

    # 4. Il key level (Key level): nei video e' sul grafico della candela che si opera (V9: il vecchio
    # minimo del giornaliero per il CRT giornaliero; V8: l'apertura dell'ultima candela ribassista del
    # giornaliero; V7: il vecchio minimo del 4 ore), o su quello sopra.
    tipi, finto, prezzi = _key_level(alte, crt, estremo, short, amp)
    if prezzi:
        # Il key level piu' vicino alla finta, per disegnarlo sul grafico.
        m.fatti["key level"] = min(prezzi, key=lambda x: abs(x[1] - estremo))
    kl = getattr(d, "key_level", None)
    nome_tf = NOMI_TF.get(r.alto_tf, "grande")
    nome_sopra = NOMI_TF.get(tf_sopra, "grande")
    if kl is not None and (kl.massimo or kl.fvg):
        tipi.append(f"{_v(short, 'un vecchio minimo', 'un vecchio massimo') if kl.massimo else 'un vuoto'} "
                    f"del grafico {nome_sopra}")
    chiave = bool(tipi) and not finto
    if chiave:
        perche = f"la finta è arrivata su {' e '.join(tipi[:2])}: un livello importante (key level)"
    elif finto:
        perche = (f"poco più in là c'è ancora {_v(short, 'un minimo', 'un massimo')} del grafico {nome_tf} mai "
                  f"toccato: questo è il {_v(short, 'fondo finto', 'tetto finto')} di Romeo, il prezzo ci andrà prima")
    else:
        perche = (f"la finta non è arrivata su nessun livello importante del grafico {nome_tf}: Romeo senza "
                  "key level non entra")
    ob.append(Domanda("key level", "Key level", "V9 02:43, V7 13:05, V8 17:10", chiave, perche))

    # 5. La direzione del grafico grande (Bias).
    ctx = getattr(d, "contesto", None)
    b_sopra = Contesto.dalla_parte(ctx.sopra, r.verso) if ctx is not None and ctx.sopra is not None else None
    contro = int(getattr(d, "grandi_contro", 0) or 0)
    con = int(getattr(d, "grandi_con", 0) or 0)
    if b_sopra is False:
        dire, perche = False, f"il grafico {nome_sopra} spinge dall'altra parte: Romeo non va contro"
    elif contro > con:
        dire, perche = False, ("sul grafico più grande c'è un movimento che punta dall'altra parte: "
                               "finché non arriva, Romeo ignora le occasioni contrarie")
    else:
        dire = True
        perche = (f"il grafico {nome_sopra} spinge nella nostra direzione" if b_sopra else
                  f"il grafico {nome_sopra} non va contro di noi")
    ob.append(Domanda("direzione", "Bias", "V16 01:43, V10 13:43, V1 35:12", dire, perche))

    # 6. L'ora giusta (Orario), sull'ora della finta: *"time is more important than price"* (V3 23:02).
    ora_ok, perche = _ora_giusta(r, s, kod)
    ob.append(Domanda("ora giusta", "Orario", "V3 24:31, V11 10:32, V17 14:00, V1 16:00", ora_ok, perche))

    # 7. L'obiettivo ancora da prendere (Livelli): se il 50% e' gia' preso, il CRT ha gia' funzionato
    # (V10 12:01) e resta solo il kiss of death verso il lato opposto (V4 07:01).
    rr1 = abs(op.tp1 - op.ingresso) / op.rischio if op.rischio > 0 else 0.0
    strada = segno * (op.tp1 - op.ingresso) > 0
    if kod:
        perche = (f"il 50% è già preso: l'obiettivo è il lato opposto del range, ancora da prendere; fino a lì "
                  f"guadagniamo {_numero(rr1)} volte quello che rischiamo" if strada else
                  "il prezzo ha già preso anche il lato opposto: il movimento c'è già stato")
    else:
        perche = (f"la metà della candela di riferimento (il primo obiettivo) è ancora da prendere: fino a lì "
                  f"guadagniamo {_numero(rr1)} volte quello che rischiamo, poi il resto all'altro lato" if strada else
                  "il prezzo ha già preso la metà della candela di riferimento: il movimento c'è già stato")
    ob.append(Domanda("obiettivo da prendere", "Livelli", "V1 17:39, V10 12:10, V4 07:01", strada, perche))

    # --- Le confluenze ---
    n = len(basse) - 1
    if n >= 2:
        fvg = (basse.bid[n, MASSIMO] < basse.bid[n - 2, MINIMO]) if short else (basse.bid[n, MINIMO] > basse.bid[n - 2, MASSIMO])
        co.append(Domanda("FVG col Model#1", "Grilletto", "V3 16:01", bool(fvg),
                          "la conferma è partita di scatto lasciando un vuoto nel prezzo" if fvg else
                          "la conferma non ha lasciato vuoti"))
    mss = _rottura(basse, s, short)
    if mss is not None:
        co.append(Domanda("vera rottura di struttura", "Grilletto", "V11 14:02, V5 11:46", mss,
                          f"il prezzo ha anche rotto l'ultimo {_v(short, 'massimo', 'minimo')}: ha girato davvero" if mss else
                          "la struttura non è ancora rotta"))
    # L'SMT si prende sul serio solo nel verso del grafico grande e con le due conferme: il Model#1 (c'e',
    # e' l'entrata) e la vera rottura di struttura (V8 28:06-31:01, V11 13:31).
    smt = _smt(crt, r.alto_tf, gemello, q, short)
    if smt is not None:
        confermato = bool(smt and dire and (mss or modello == "vera rottura"))
        co.append(Domanda("SMT", "Grilletto", "V8 02:04, V8 30:03, V11 13:31", confermato,
                          "il mercato gemello non ha fatto la stessa finta, con la rottura di struttura a confermarlo"
                          if confermato else
                          "il mercato gemello ha fatto la stessa finta" if not smt else
                          "il mercato gemello diverge, ma contro il grafico grande: non conta" if not dire else
                          "il mercato gemello diverge, ma manca la rottura di struttura che lo conferma"))
    fine_c2 = _fine_candela_2(crt, basse, short)
    if fine_c2 is not None:
        co.append(Domanda("finta a fine candela", "Grilletto", "V8 07:28", fine_c2,
                          "la finta è arrivata alla fine della candela 2: di solito ora parte subito" if fine_c2 else
                          "la finta è arrivata a metà della candela 2"))
    c1 = _candela_1(alte, crt, short)
    if c1 is not None:
        co.append(Domanda("candela 1 spessa", "Cacciatore", "V9 02:43", c1,
                          "la candela di riferimento era grande e andava verso il livello importante: la molla carica" if c1 else
                          "la candela di riferimento era normale"))
    ar = getattr(d, "alla_romeo", None)
    if ar is not None:
        co.append(Domanda("dentro un CRT più grande", "Cacciatore", "V5 13:30, V11 08:09", bool(ar.annidato),
                          "questo movimento sta dentro uno più grande nello stesso verso" if ar.annidato else
                          "nessun movimento più grande nello stesso verso"))
    li = getattr(d, "liquidita", None)
    if li is not None:
        co.append(Domanda("liquidità presa", "Grilletto", "V4 07:36, V5 07:26", bool(li.presa),
                          "la finta ha preso gli ordini lasciati prima (dove molti avevano lo stop)" if li.presa else
                          "la finta non ha preso ordini lasciati prima"))
    if kl is not None and kl.tocca:
        co.append(Domanda("ferma sul key level", "Key level", "V7 13:05", bool(kl.tocca),
                          "la finta si è fermata proprio sul livello importante" if kl.tocca else
                          "la finta è andata oltre il livello importante"))
    if a3 is not None:
        sconto = (op.ingresso >= a3) if short else (op.ingresso <= a3)
        co.append(Domanda("entrata oltre l'apertura", "Grilletto", "V9 24:20", bool(sconto),
                          _v(short, "entriamo ancora sotto l'apertura della candela 3", "entriamo ancora sopra l'apertura della candela 3")
                          if sconto else "la conferma ci fa entrare dall'altra parte dell'apertura"))
    # --- Quello che vede ogni agente, in numeri (per il suo giudizio, che impara dal vivo) ---
    presenti = set(m.presenti)
    ore_finta = _ny(int(getattr(s, "turtle_soup_inizio", 0) or q))
    m.numeri = {
        "Cacciatore": {"candela 1 spessa": float("candela 1 spessa" in presenti),
                       "dentro un CRT più grande": float("dentro un CRT più grande" in presenti),
                       **{f"coppia {c}": float(coppia == c) for c in NOMI_COPPIA}},
        "Grilletto": {"spessore": min(k, 5.0) / 5.0, "vera rottura": float(modello == "vera rottura"),
                      "kiss of death": float(kod), "FVG": float("FVG col Model#1" in presenti),
                      "rottura di struttura": float("vera rottura di struttura" in presenti),
                      "finta a fine candela": float("finta a fine candela" in presenti),
                      "liquidità presa": float("liquidità presa" in presenti), "SMT": float("SMT" in presenti),
                      "entrata oltre l'apertura": float("entrata oltre l'apertura" in presenti)},
        "Key level": {"livelli": min(len(tipi), 3) / 3.0, "ferma sul key level": float("ferma sul key level" in presenti),
                      "fondo finto": float(finto)},
        "Bias": {"grafico sopra a favore": float(b_sopra is True), "CRT grandi a favore": min(con, 3) / 3.0,
                 "CRT grandi contro": min(contro, 3) / 3.0},
        "Orario": {"Londra": float(1 <= ore_finta.hour < 5), "New York": float(8 <= ore_finta.hour < 11),
                   **{f"di {GIORNI[g]}": float(ore_finta.weekday() == g) for g in range(5)}},
        "Livelli": {"guadagno al primo obiettivo": min(rr1, 6.0) / 6.0,
                    "rischio sul range": min(op.rischio / amp, 2.0) / 2.0 if amp > 0 else 0.0},
    }
    return m


# Le ore delle sessioni in cui Romeo entra, in ore di New York: Londra (V11 10:32, martedi' a Londra) e la
# mattina di New York (V17 14:00: l'obiettivo alle 9:30). Fuori ci sono le ore di consolidamento (V1 42:31).
SESSIONI = ((1, 5), (8, 11))
# La settimana: il suo estremo si forma fra lunedi' e mercoledi', l'altro giovedi'-venerdi' (V3 24:31).
GIORNI_FINTA = (0, 1, 2)
# Il mese: settimana 1 accumulazione, settimana 2 manipolazione, il resto distribuzione (V1 16:00).
GIORNI_DEL_MESE = 14


def _in_sessione(ore: set[int]) -> bool:
    return any(a <= h < b for h in ore for a, b in SESSIONI)


def _ora_giusta(r, s, kod: bool) -> tuple[bool, str]:
    """L'Orario: la finta e' arrivata quando Romeo dice che si formano i massimi e i minimi?"""
    t = int(s.turtle_soup_inizio) if getattr(s, "turtle_soup_inizio", 0) else int(s.quando)
    ny = _ny(t)
    quando = f"{GIORNI[ny.weekday()]} alle {ny:%H:%M} di New York"
    durata = {TF.M15: 900, TF.H1: 3600, TF.H4: 4 * 3600, TF.D1: 86400}.get(r.basso_tf, 3600)
    ore = _ore_toccate(t, t + durata)
    if r.alto_tf is TF.MN:
        ok = ny.day <= GIORNI_DEL_MESE or kod
        return ok, (f"la finta è del {ny.day} del mese: nelle prime due settimane, quando Romeo dice che il mese "
                    "manipola" if ok else f"la finta è del {ny.day} del mese: troppo tardi, la manipolazione del mese "
                    "si fa nelle prime due settimane")
    if r.alto_tf is TF.W1:
        giorno_ok = ny.weekday() in GIORNI_FINTA or kod
        sessione = _in_sessione(ore)
        ok = giorno_ok and sessione
        if ok:
            return True, (f"è {quando}: " + ("il kiss of death arriva verso fine settimana, quando la settimana "
                                             "distribuisce" if kod else "lunedì-mercoledì, quando si fa l'estremo della "
                                             "settimana") + ", nelle ore di Londra o New York")
        if not giorno_ok:
            return False, f"è {quando}: l'estremo della settimana si fa fra lunedì e mercoledì, non dopo"
        return False, f"è {quando}: fuori dalle ore di Londra e New York, ore di consolidamento"
    ok = _in_sessione(ore)
    return ok, (f"è {quando}: nella sessione di Londra o la mattina di New York, le ore di Romeo" if ok else
                f"è {quando}: fuori dalle ore di Londra e New York, ore di consolidamento")

def _smt(crt, alto: TF, gemello, q: int, short: bool) -> Optional[bool]:
    """L'SMT della candela (V10 07:25): la candela 2 del nostro strumento ha preso il lato della candela 1,
    quella del gemello no. None se il gemello manca."""
    if gemello is None or gemello[0] is None or not len(gemello[0]):
        return None
    ore_g, relazione = gemello
    alte_g = costruisci(ore_g, alto).chiuse_entro(q)
    k = int(np.searchsorted(alte_g.inizio, crt.range_inizio))
    if k + 1 >= len(alte_g) or alte_g.inizio[k] != crt.range_inizio:
        return None
    c1, c2 = alte_g.bid[k], alte_g.bid[k + 1]
    # Per il gemello inverso (il dollaro contro l'euro) il lato e' l'altro.
    lato_alto = short if relazione > 0 else not short
    preso = c2[MASSIMO] > c1[MASSIMO] if lato_alto else c2[MINIMO] < c1[MINIMO]
    return not bool(preso)


def _rottura(basse: Candele, s, short: bool) -> Optional[bool]:
    """La vera rottura di struttura (V11 15:07): la chiusura dello scatto oltre il punto da cui era partita
    la spinta del turtle soup (il minimo prima del massimo della finta, per vendere)."""
    t = int(np.searchsorted(basse.inizio, s.turtle_soup_inizio))
    n = len(basse) - 1
    if t <= 1 or t >= n:
        return None
    a = max(0, t - 12)
    tratto = basse.bid[a:t + 1]
    if short:
        # Il massimo che la finta ha superato, e il minimo fra lui e la finta.
        i = int(np.argmax(tratto[:-1, MASSIMO]))
        punto = float(tratto[i:, MINIMO].min())
        return bool(basse.bid[n, CHIUSURA] < punto)
    i = int(np.argmin(tratto[:-1, MINIMO]))
    punto = float(tratto[i:, MASSIMO].max())
    return bool(basse.bid[n, CHIUSURA] > punto)


def _fine_candela_2(crt, basse: Candele, short: bool) -> Optional[bool]:
    """L'estremo della candela 2 e' arrivato nel suo ultimo quarto?"""
    fine_2 = int(crt.armato_quando)
    # La candela 2 comincia dove finisce la candela 1 (il range).
    inizio_c2 = min(int(fine_candela(int(crt.range_inizio), crt.alto_tf, weekend(crt.strumento))),
                    int(crt.manipolazione_inizio))
    a = int(np.searchsorted(basse.inizio, inizio_c2))
    b = int(np.searchsorted(basse.inizio, fine_2))
    if b <= a or fine_2 <= inizio_c2:
        return None
    tratto = basse.bid[a:b, MASSIMO] if short else -basse.bid[a:b, MINIMO]
    i = a + int(np.argmax(tratto))
    return bool((int(basse.inizio[i]) - inizio_c2) / (fine_2 - inizio_c2) >= FINE_CANDELA)


def _candela_1(alte: Candele, crt, short: bool) -> Optional[bool]:
    """La candela 1 grande (almeno 1,2 volte il corpo medio delle 10 prima) e diretta verso il key level."""
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    if k >= len(alte) or alte.inizio[k] != crt.range_inizio or k < 3:
        return None
    corpi = np.abs(alte.bid[max(0, k - 10):k, CHIUSURA] - alte.bid[max(0, k - 10):k, APERTURA])
    o, c = float(alte.bid[k, APERTURA]), float(alte.bid[k, CHIUSURA])
    verso_giusto = (c > o) if short else (c < o)
    return bool(verso_giusto and len(corpi) and abs(c - o) >= 1.2 * float(corpi.mean()))


def _key_level(alte: Candele, crt, estremo: float, short: bool, amp: float) -> tuple[list[str], bool, list]:
    """I key level del grafico della candela presi dalla finta, e se c'e' un fondo (tetto) finto.

    Si guardano le candele prima della candela 1: i massimi di swing (per vendere) non ancora ripresi,
    che la finta ha superato di poco o ha raggiunto (*"stab into the old high"*); l'apertura dell'ultima
    candela rialzista (V8 17:10: le rialziste sono resistenza, le ribassiste supporto); i vuoti non
    riempiti in cui la finta entra. Fondo finto (V7 13:05): un massimo di swing mai ripreso appena oltre
    la finta. Tutto scritto per vendere; per comprare e' lo specchio."""
    k = int(np.searchsorted(alte.inizio, crt.range_inizio))
    if k < 5 or amp <= 0:
        return [], False, []
    s = 1.0 if short else -1.0
    b = alte.bid[max(0, k - 40):k + 1]
    o, c = b[:, APERTURA] * s, b[:, CHIUSURA] * s
    h = (b[:, MASSIMO] if short else b[:, MINIMO]) * s
    lo = (b[:, MINIMO] if short else b[:, MASSIMO]) * s
    e = estremo * s
    n = len(b) - 1                      # l'ultima e' la candela 1
    tipi, finto, prezzi = [], False, []
    for i in range(2, n - 1):
        if not (h[i] > h[i - 2:i].max() and h[i] > h[i + 1:i + 3].max()):
            continue
        if h[i + 1:n + 1].max() >= h[i]:
            continue                    # gia' ripreso prima della finta
        if -0.1 * amp <= e - h[i] <= 0.5 * amp:
            tipi.append(_v(short, "un vecchio minimo", "un vecchio massimo") + " mai ripreso")
            prezzi.append((_v(short, "vecchio minimo", "vecchio massimo"), float(h[i] * s)))
        elif 0 < h[i] - e <= 0.25 * amp:
            finto = True
    for i in range(n - 1, -1, -1):
        if c[i] > o[i]:
            if -0.1 * amp <= e - o[i] <= 0.5 * amp:
                tipi.append(_v(short, "l'apertura dell'ultima candela ribassista", "l'apertura dell'ultima candela rialzista"))
                prezzi.append((_v(short, "apertura dell'ultima candela ribassista", "apertura dell'ultima candela rialzista"),
                               float(o[i] * s)))
            break
    for j in range(n - 2):
        fondo, cima = h[j + 2], lo[j]
        if fondo < cima and h[j + 3:n + 1].max(initial=-np.inf) < cima and e > fondo:
            tipi.append("un vuoto lasciato dal prezzo")
            prezzi.append(("vuoto lasciato dal prezzo", float(fondo * s)))
            break
    return list(dict.fromkeys(tipi)), finto, prezzi


# --- Il metodo delle foto del proprietario (06/10/2026, `spec/metodo_foto.md`) --------------------------

FOTO = "le foto del proprietario"
NOMI_TF_FOTO = {TF.H1: "a 1 ora", TF.H4: "a 4 ore", TF.H6: "a 6 ore", TF.H12: "a 12 ore", TF.D1: "giornaliero",
                TF.W1: "settimanale", TF.MN: "mensile"}
CANDELA_FOTO = {TF.H1: "la candela di un'ora", TF.H4: "la candela delle 4 ore", TF.H6: "la candela delle 6 ore",
                TF.D1: "la candela del giorno", TF.W1: "la candela della settimana", TF.MN: "la candela del mese"}
# Le fasce di New York in cui apre la candela 3: l'Orario non decide (*"non c'è limite di orario"*), impara.
FASCE = (("Asia", 18, 2), ("Londra", 2, 8), ("New York", 8, 12), ("pomeriggio", 12, 18))


def _fascia(ora: int, a: int, b: int) -> bool:
    return a <= ora < b if a < b else (ora >= a or ora < b)


def _gap_a_favore(q, s):
    """Il gap del timeframe alto in cui la candela 2 e' entrata e che spinge dalla nostra parte: per comprare
    un gap rialzista sotto (il CRT a supporto di gap, cartella 5), per vendere uno ribassista sopra."""
    from nvm.agenti import foto
    for tf in foto.TF_GAP:
        for g in foto.gap_di(q, tf, s.n3_inizio):
            if g.toccato is None or g.riempito is not None or g.rialzista == s.short:
                continue
            dentro = (s.n2_alto >= g.basso) if s.short else (s.n2_basso <= g.alto)
            if dentro:
                return g, foto.fase(q, g, s.n3_inizio)
    return None, None


def valuta_foto(d) -> Metodo:
    """Le domande del metodo delle foto su un'occasione (`giro.occasioni_foto`). Obbligatorie: il CRT, il key
    level, la direzione. Il resto sono confluenze: la squadra impara dal vivo quanto conta ognuna."""
    from nvm.agenti import foto
    info = d.foto
    s, q, ob = info["setup"], info["quadro"], info["obiettivo"]
    sd = info.get("dxy")
    st = info.get("totale")
    dal_totale = getattr(s, "dal_totale", False)
    short = s.short
    segno = -1 if short else 1
    amp = s.range_alto - s.range_basso
    ny = _ny(s.n3_inizio)
    m = Metodo(fatti={"strumento": s.strumento, "coppia": s.tf.value, "verso": "vendita" if short else "acquisto",
                      "giorno": GIORNI[ny.weekday()], "ora": f"{ny.hour:02d}",
                      "modello": "dal DXY" if s.dal_dxy else "dalla TOTAL" if dal_totale else "apertura N3"})
    ob_ = m.obbligatorie
    co = m.confluenze
    candela = CANDELA_FOTO.get(s.tf, "la candela")
    lato = _v(short, "il minimo", "il massimo")
    numero = foto.numero

    # 1. Il CRT (Cacciatore): la candela 2 ha preso un lato del range ed e' rientrata.
    madre = f" (il range è la candela madre: dopo ci sono {s.dentro} inside bar)" if s.dentro else ""
    if s.dal_dxy:
        x = sd
        testo = (f"il DXY ha fatto il CRT {NOMI_TF_FOTO.get(s.tf, '')}: la candela 2 ha preso "
                 f"{_v(x.short, 'il minimo', 'il massimo') if x is not None else 'un lato'} del range ed è rientrata. "
                 f"Il dollaro {'sale' if x is not None and not x.short else 'scende'}: su {s.strumento} "
                 f"{'vendiamo' if short else 'compriamo'} all'apertura della candela 3")
    elif dal_totale:
        testo = (f"la TOTAL (tutte le crypto insieme) ha fatto il CRT {NOMI_TF_FOTO.get(s.tf, '')}: la candela 2 ha "
                 f"preso {_v(short, 'il minimo', 'il massimo')} del range ed è rientrata. Il mercato crypto "
                 f"{'scende' if short else 'sale'}: su {s.strumento} {'vendiamo' if short else 'compriamo'} "
                 "all'apertura della candela 3")
    else:
        testo = (f"{candela} di prima ha preso {lato} del range ({numero(s.range_alto if short else s.range_basso)})"
                 f"{madre} ed è rientrata: entriamo all'apertura della candela 3, come nelle foto")
    ob_.append(Domanda("CRT", "Cacciatore", FOTO, True, testo))

    # 2. Il key level (Key level): il massimo o minimo del periodo prima preso dal CRT.
    presi = (sd.presi if (s.dal_dxy and sd is not None) else st.presi if (dal_totale and st is not None)
             else s.presi)
    if s.tf is TF.H1:
        kl_ok = bool(s.h4_preso is not None and any(l.tf is TF.D1 and not l.oggi for l in presi))
        perche = (f"il CRT a 1 ora ha preso il {', il '.join(l.nome for l in presi if l.tf is TF.D1)} e il "
                  f"{_v(short, 'minimo', 'massimo')} delle 4 ore ({numero(s.h4_preso)}): entriamo sulla terza candela "
                  "di un'ora, che anticipa la candela a 4 ore dopo" if kl_ok else
                  "il CRT a 1 ora vale solo se prende il key level giornaliero e il massimo (minimo) a 4 ore")
    else:
        kl_ok = bool(presi)
        perche = (f"la finta ha preso {' e '.join(f'il {l.nome} ({numero(l.prezzo)})' for l in presi[:3])}: un key "
                  "level, dove c'era la liquidità" if kl_ok else
                  "la finta non ha preso nessun key level (massimo o minimo del giorno, della settimana, del mese, "
                  "dei 3 mesi, dell'anno prima)")
    ob_.append(Domanda("key level", "Key level", FOTO, kl_ok, perche))
    if presi:
        k = presi[-1]
        m.fatti["key level"] = (k.nome, float(k.prezzo))

    # 3. La direzione (Bias): il timeframe di comando.
    dz = foto.direzione(q, s)
    ob_.append(Domanda("direzione", "Bias", FOTO, dz.ok,
                       dz.testo if dz.ok else dz.testo + ": nelle foto si entra solo col comando dalla nostra parte"))

    # --- Le confluenze ---
    allineati = list(info.get("allineati", [])) + [tf for tf in foto.allineati(q, s) if tf not in info.get("allineati", [])]
    co.append(Domanda("timeframe allineati", "Cacciatore", FOTO, bool(allineati),
                      f"anche {', '.join(NOMI_TF_FOTO.get(t, t.value) for t in allineati[:3])} "
                      f"{'fa' if len(allineati) == 1 else 'fanno'} il CRT nello stesso verso" if allineati else
                      "gli altri timeframe non fanno il CRT nello stesso verso"))
    co.append(Domanda("inside bar", "Cacciatore", FOTO, s.dentro > 0,
                      f"il range è una candela madre con {s.dentro} inside bar dopo: il prezzo ha caricato" if s.dentro
                      else "nessuna inside bar nel range"))
    alti = [l for l in presi if l.tf in (TF.W1, TF.MN, TF.Q3, TF.Y1)]
    co.append(Domanda("key level grande", "Key level", FOTO, bool(alti),
                      f"la finta ha preso anche il {alti[0].nome}" if alti else "solo key level giornalieri"))
    g, f = _gap_a_favore(q, s)
    co.append(Domanda("dentro un gap a favore", "Gap", FOTO, g is not None,
                      f"la finta è entrata nel {g.nome} ({numero(g.basso)}–{numero(g.alto)}): {f.testo}" if g is not None
                      else "la finta non è dentro un gap che ci spinge"))
    if g is not None:
        co.append(Domanda("continuazione col RSI", "Gap", FOTO, bool(f.divergenza),
                          "nel gap l'RSI conferma la continuazione (minimi decrescenti sul grafico, crescenti sull'RSI)"
                          if f.divergenza else "nel gap l'RSI non dà ancora la divergenza della continuazione"))
    co.append(Domanda("target sul gap", "Livelli", FOTO, ob.tipo in ("gap", "liquidazione"),
                      f"il target finale è {ob.nome} ({numero(ob.prezzo)})"))
    dxy_con = dxy_contro = False
    if sd is not None and not s.dal_dxy:
        verso_coppia = foto.verso_dal_dxy(s.strumento, sd.verso)
        dxy_con = verso_coppia is s.verso
        dxy_contro = verso_coppia is not None and verso_coppia is not s.verso
    if s.dal_dxy:
        dxy_con = True
    if s.strumento in foto.DOLLARO_SOTTO + foto.DOLLARO_SOPRA:
        co.append(Domanda("DXY a favore", "DXY", FOTO, dxy_con,
                          "il DXY ha fatto il CRT che ci dà ragione" if dxy_con else
                          "il DXY fa il CRT dall'altra parte" if dxy_contro else "il DXY non ha fatto un CRT ora"))

    # --- I numeri che vede ogni agente: da qui ognuno impara il suo giudizio ---
    presenti = set(m.presenti)
    b = foto.biases(q, s.n3_inizio)
    sopra = [v for tf, (v, _) in b.items() if ORDINE_TF.index(tf) > ORDINE_TF.index(s.tf)]
    rr1 = abs(s.tp1 - s.ingresso) / max(abs(s.ingresso - s.stop), 1e-12)
    rr2 = abs(ob.prezzo - s.ingresso) / max(abs(s.ingresso - s.stop), 1e-12)
    finta = ((s.n2_alto - s.range_alto) if short else (s.range_basso - s.n2_basso)) / amp if amp > 0 else 0.0
    rientro = ((s.range_alto - s.n2_chiusura) if short else (s.n2_chiusura - s.range_basso)) / amp if amp > 0 else 0.0
    m.numeri = {
        "Cacciatore": {**{f"CRT {NOMI_TF_FOTO[t]}": float(s.tf is t) for t in foto.TF_CRT},
                       "inside bar": min(s.dentro, 3) / 3.0, "allineati": min(len(allineati), 4) / 4.0,
                       "dal DXY": float(s.dal_dxy)},
        "Grilletto": {"finta oltre il range": min(max(finta, 0.0), 1.0), "rientro nel range": min(max(rientro, 0.0), 1.0),
                      "rischio sul range": min(abs(s.ingresso - s.stop) / amp, 2.0) / 2.0 if amp > 0 else 0.0},
        "Key level": {**{f"preso {k}": float(any(l.tf is t and not l.oggi for l in presi))
                         for k, t in (("D", TF.D1), ("W", TF.W1), ("M", TF.MN), ("3 mesi", TF.Q3), ("anno", TF.Y1))},
                      "preso di oggi": float(any(l.oggi for l in presi)), "quanti": min(len(presi), 4) / 4.0},
        "Bias": {"sopra a favore": sum(1 for v in sopra if v == segno) / max(len(sopra), 1),
                 "sopra contro": sum(1 for v in sopra if v == -segno) / max(len(sopra), 1),
                 "ritracciamento": float(dz.ok and not dz.a_favore)},
        "Gap": {"dentro un gap a favore": float("dentro un gap a favore" in presenti),
                **{f"fase {n}": float(f is not None and f.numero == n) for n in (1, 2, 3, 4)},
                "RSI": float("continuazione col RSI" in presenti), "target sul gap": float("target sul gap" in presenti)},
        "DXY": {"DXY a favore": float(dxy_con), "DXY contro": float(dxy_contro)},
        "Orario": {**{n: float(_fascia(ny.hour, a, b_)) for n, a, b_ in FASCE},
                   **{f"di {GIORNI[g_]}": float(ny.weekday() == g_) for g_ in range(5)}},
        "Livelli": {"guadagno al TP1": min(rr1, 6.0) / 6.0, "guadagno al target finale": min(rr2, 15.0) / 15.0,
                    **{f"target {t}": float(ob.tipo == t) for t in ("gap", "liquidazione", "key level", "range")}},
    }
    m.fatti["rr"] = round(0.5 * rr1 + 0.5 * rr2, 4) if ob.prezzo != s.tp1 else round(rr1, 4)
    m.fatti["obiettivo"] = (ob.nome, float(ob.prezzo))
    return m
