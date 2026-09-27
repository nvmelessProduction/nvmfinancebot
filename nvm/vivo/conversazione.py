"""L'equipe come una chat fra professionisti (l'utente, 27/09/2026: *"voglio un'equipe
di professionisti, non un posto dove non si capisce niente"*).

Regole:
- parla solo chi ha qualcosa di rilevante: le operazioni aperte davvero, le chiusure,
  il riepilogo della sera. Le occasioni scartate non fanno messaggi: si contano la sera;
- una cosa per voce, in italiano semplice, senza sigle interne; ogni affermazione
  con il suo numero (quante volte, sui vent'anni, in casi cosi' e' arrivato il primo
  obiettivo);
- il Capo chiude.

Le frasi nascono dai dati dell'agente, non da un modello di linguaggio: sono vere, ma
costruite, non una conversazione libera.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from nvm.agenti.cacciatore import Verso
from nvm.tempo import NEW_YORK
from nvm.vivo.dialogo import BINARIE, firma

VOLTI = {"Cacciatore": "🔭", "Grilletto": "🎯", "Livelli": "📏", "Key level": "🧱", "Orario": "🕐", "Bias": "🧭",
         "Allineamento": "🪜", "Gap": "🕳", "Rischio": "🛡", "Capo": "👔", "Romeo": "🎓"}
# Sotto questa spinta (sulla qualita' attesa) un agente non ha pesato davvero: non parla.
PESO = 0.03
# Da quanti casi sui vent'anni un numero si dice.
CASI = 100


@dataclass(frozen=True)
class Voce:
    chi: str
    testo: str

    def riga(self) -> str:
        return f"{VOLTI.get(self.chi, '•')} {self.chi}: {self.testo}"


def insieme(voci: list[Voce]) -> str:
    """Le voci in un messaggio solo, quando gli agenti parlano dallo stesso bot."""
    return "\n".join(v.riga() for v in voci)


# --- Le prove: quante volte, in casi cosi', e' arrivato il primo obiettivo -----------------------

def prove(x: np.ndarray, tp1: np.ndarray) -> dict:
    """Per agente e segnale, sui vent'anni: (casi, quante volte il primo obiettivo). Sotto "" il totale."""
    tp1 = np.asarray(tp1, bool)
    fuori: dict = {"": {"": (len(tp1), float(tp1.mean()) if len(tp1) else 0.0)}}
    for nome in list(BINARIE) + ["Livelli"]:
        conti: dict[str, list] = {}
        for riga, t in zip(x, tp1):
            v = conti.setdefault(firma(nome, riga), [0, 0])
            v[0] += 1
            v[1] += int(t)
        fuori[nome] = {f: (n, k / n) for f, (n, k) in conti.items() if n}
    return fuori


def _su_cento(p: float) -> str:
    return f"{round(100 * p)} volte su 100"


def _prova(nome: str, f: str, storia: Optional[dict], a_favore: Optional[bool] = None) -> str:
    """Il numero che sostiene quello che l'agente dice. Se il numero dice il contrario (per
    esempio: a favore, ma in casi cosi' il primo obiettivo arriva meno del solito), non si cita:
    un professionista non porta prove che lo smentiscono."""
    # Per Livelli quante volte arriva il primo obiettivo non dice niente da solo: un obiettivo
    # lontano arriva meno spesso ma vale di piu'. Il suo numero sarebbe fuorviante.
    if not storia or nome == "Livelli" or nome not in storia or f not in storia[nome]:
        return ""
    n, p = storia[nome][f]
    if n < CASI:
        return ""
    base = storia[""][""][1]
    if a_favore is not None and (p > base) != a_favore:
        return ""
    return f" In vent'anni, in casi così, il primo obiettivo è arrivato {_su_cento(p)} (di solito {round(100 * base)})."


# --- Ogni agente dice il suo segnale a parole --------------------------------------------------

_ORE = {"21–01 NY": "fra le 21 e l'1 di New York", "01–05 NY": "fra l'1 e le 5 di New York (Londra)",
        "05–09 NY": "fra le 5 e le 9 di New York", "09–13 NY": "fra le 9 e le 13 di New York",
        "13–17 NY": "fra le 13 e le 17 di New York", "17–21 NY": "fra le 17 e le 21 di New York"}


def parole(nome: str, f: str) -> str:
    """Il segnale di un agente (la sua "firma") in una frase semplice."""
    if nome == "Cacciatore":
        return f"Il range viene dal grafico {f.split(' → ')[0]}, l'ingresso è sul grafico {f.split(' → ')[1]}."
    if nome == "Grilletto":
        colpo, liq = f.split(", ", 1)
        tentativo = {"primo colpo": "È il primo tentativo su questo range", "secondo colpo": "È il secondo tentativo "
                     "su questo range (il primo è stato stoppato)", "terzo colpo": "È il terzo tentativo su questo range"}[colpo]
        presa = {"liquidità presa prima": "e il prezzo ha preso la liquidità lasciata prima",
                 "liquidità ripresa fuori dal CRT": "e il prezzo è tornato a prendere un massimo lasciato fuori dal range",
                 "senza liquidità presa": "ma il prezzo non ha preso liquidità prima"}[liq]
        return f"{tentativo}, {presa}."
    if nome == "Key level":
        if f in ("nessuna zona", "non so"):
            return "Qui non c'è nessun livello importante del grafico più grande."
        cose = {"massimo preso": "ha preso un estremo importante del grafico più grande",
                "arriva al massimo": "arriva su un estremo importante", "rejection block": "reagisce su un rejection block",
                "FVG": "reagisce su un FVG"}
        return "Il prezzo " + " e ".join(cose[c] for c in f.split(", ") if c in cose) + "."
    if nome == "Orario":
        return f"Siamo {_ORE.get(f, f)}."
    if nome == "Bias":
        if f == "bias neutro":
            return "La direzione del mercato non è chiara."
        parti = f.split(", ")
        rng = "a favore" if "range a favore" in parti else ("contro" if "range contro" in parti else None)
        sopra = "a favore" if "sopra a favore" in parti else ("contro" if "sopra contro" in parti else None)
        dire = {"a favore": "nella nostra direzione", "contro": "contro di noi"}
        if rng and rng == sopra:
            return f"La candela del range e il grafico più grande vanno {dire[rng]}."
        pezzi = ([f"la candela del range va {dire[rng]}"] if rng else []) + ([f"il grafico più grande va {dire[sopra]}"] if sopra else [])
        testo = ", ".join(pezzi)
        return testo[:1].upper() + testo[1:] + "."
    if nome == "Livelli":
        return {"primo target sotto 1 R": "Il primo obiettivo è vicino: vale meno del rischio.",
                "primo target fra 1 e 2 R": "Il primo obiettivo vale fra 1 e 2 volte il rischio.",
                "primo target fra 2 e 3 R": "Il primo obiettivo vale fra 2 e 3 volte il rischio.",
                "primo target oltre 3 R": "Il primo obiettivo è lontano: oltre 3 volte il rischio."}.get(f, f)
    return f


def _volte(x: float) -> str:
    return (f"{x:+.2f}".replace(".", ",").replace("-", "−")) + " volte il rischio"


def _pct(x: float) -> str:
    return f"{x:.1%}".replace(".", ",")


# --- Un'operazione aperta ---------------------------------------------------------------------

def apertura(d, per: dict[str, float], storia: Optional[dict], rischio: float, aperte: int, rischio_totale: float,
             ingresso: Optional[float] = None, da_sola: float = 0.0, legate: tuple = ()) -> list[Voce]:
    """La discussione su un'operazione appena aperta: chi ha visto il segnale e dove, chi ha pesato
    di piu' a favore e contro, il Rischio, il Capo. `rischio` e `rischio_totale` in frazione del
    conto; `ingresso` il prezzo vero dell'ordine (lo stesso del canale operativo); `da_sola` quanto
    avrebbe rischiato il Rischio senza le altre aperte, `legate` quelle che vanno insieme a lei."""
    from nvm.vivo.messaggi import NOMI_TF, prezzo
    k = d.r.strumento
    short = d.r.verso is Verso.SHORT
    ingresso = d.op.ingresso if ingresso is None else ingresso
    crt = d.r.scatto.crt
    lato, livello = ("il massimo", crt.crt_high) if short else ("il minimo", crt.crt_low)
    dentro = ingresso < livello if short else ingresso > livello
    colpo = " È il secondo tentativo su questo range." if d.r.colpo == 2 else (
        " È il terzo tentativo su questo range." if d.r.colpo >= 3 else "")
    voci = [Voce("Grilletto", f"Segnale di {'vendita' if short else 'acquisto'} su {k} a {prezzo(k, ingresso)}. Il prezzo "
                              f"ha preso {lato} del range {NOMI_TF[d.r.alto_tf]} ({prezzo(k, livello)})"
                              + (" ed è rientrato dentro; sul grafico " if dentro else "; sul grafico ")
                              + f"{NOMI_TF[d.r.basso_tf]} è arrivata la conferma dell'inversione.{colpo}")]
    x = d.x
    pesati = sorted(((n, v) for n, v in per.items() if n in BINARIE or n == "Livelli"), key=lambda a: -abs(a[1]))
    favore = next(((n, v) for n, v in pesati if v >= PESO and n != "Grilletto"), None)
    contro = next(((n, v) for n, v in pesati if v <= -PESO), None)
    # Ognuno dice cosa vede e cosa ne dice l'esperienza dei vent'anni (il Capo l'ha imparata da li'):
    # a volte un segnale che sembra buono, nei dati, e' andato peggio del solito, e va detto cosi'.
    if favore:
        f = firma(favore[0], x)
        prova = _prova(favore[0], f, storia, True)
        voci.append(Voce(favore[0], parole(favore[0], f) + (prova or " Nei vent'anni, casi così sono andati meglio del solito.")))
    if contro:
        f = firma(contro[0], x)
        prova = _prova(contro[0], f, storia, False)
        voci.append(Voce(contro[0], "Attenzione. " + parole(contro[0], f)
                         + (prova or " Nei vent'anni, però, casi così sono andati peggio del solito.")))
    if aperte <= 1:
        insieme_a = "È l'unica operazione aperta."
    else:
        insieme_a = f"Con questa, {aperte} operazioni aperte: {_pct(rischio_totale)} del conto a rischio in tutto."
    perche = ""
    if legate and da_sola > rischio * 1.05:
        perche = (f" Da sola sarebbe {_pct(da_sola)}, ma è legata a {' e '.join(legate)}, già apert"
                  f"{'a' if len(legate) == 1 else 'e'}: quando va male una, di solito va male anche l'altra.")
    elif da_sola and rischio > da_sola * 1.05:
        perche = f" È il lotto minimo: un po' più della puntata giusta ({_pct(da_sola)})."
    voci.append(Voce("Rischio", f"Metto a rischio {_pct(rischio)} del conto.{perche} {insieme_a}"))
    capo = (f"Entriamo. Stimo {round(100 * d.p1)} possibilità su 100 di arrivare al primo obiettivo; "
            f"in media l'operazione rende {_volte(d.atteso)}.")
    if contro:
        capo += f" Ho sentito {contro[0]}: il resto della squadra pesa di più."
    voci.append(Voce("Capo", capo))
    return voci


# --- Un'operazione chiusa ---------------------------------------------------------------------

def chiusura(s, alt: dict, torto: list[str], storia: Optional[dict]) -> list[Voce]:
    """Com'e' andata un'operazione aperta davvero, e chi impara qualcosa."""
    r = float(s.esito["erre"])
    k = s.strumento
    # Senza numero: quello vero, in euro e in R, e' sul canale operativo.
    if s.esito.get("tp2"):
        esito = "in guadagno: presi tutti e due gli obiettivi"
    elif abs(r) < 0.05:
        esito = "a pareggio"
    elif r > 0:
        esito = "in guadagno" + (": preso il primo obiettivo" if s.esito.get("tp1") else "")
    else:
        esito = "in perdita" + (": preso lo stop" if s.esito.get("uscita") == "stop" else ", prima dello stop")
    ragione = [n for n, v in s.spinte.items() if abs(v) >= PESO and (v > 0) == (r > 0) and n != "Romeo"]
    voci = [Voce("Capo", f"{k} chiusa {esito}." + (f" Avevano visto giusto: {', '.join(ragione)}." if ragione and r > 0 else ""))]
    # Chi poteva fare meglio lo dice, una volta sola: la scelta vicina che avrebbe reso di piu'.
    migliore = None
    for agente, voci_alt in alt.items():
        nome, v, ra = max(voci_alt, key=lambda a: a[2])
        if ra > r + 0.2 and (migliore is None or ra - r > migliore[3] - r):
            migliore = (agente, nome, v, ra)
    if migliore:
        from nvm.vivo.autoanalisi import scelta
        agente, nome, v, ra = migliore
        voci.append(Voce(agente, f"Con «{scelta(nome, v)}» sarebbe finita {_volte(ra)}. Lo segno: se succede spesso, "
                                 "in palestra provo a cambiare."))
    elif r < 0:
        sbagliati = [n for n in torto if n in BINARIE]
        if sbagliati:
            n = sbagliati[0]
            f = firma(n, s.x)
            voci.append(Voce(n, f"Avevo spinto a entrare, ma questa volta è andata male. {parole(n, f)}"
                                f"{_prova(n, f, storia, True)}"))
    return voci


def benvenuto(strumenti: int) -> str:
    return (f"La squadra è al lavoro su {strumenti} strumenti. Qui ci sentite quando apriamo o chiudiamo "
            "un'operazione, ogni sera alle 17 di New York con il riepilogo della giornata, e il sabato con la "
            "riunione della settimana. Le occasioni che lasciamo non fanno rumore: le contiamo la sera.")


# --- Il riepilogo della sera ------------------------------------------------------------------

def riepilogo(seguite: list, dal: int, al: int, aperte: int, rischio_totale: float, lezioni: list[str],
              saltate: Optional[dict] = None, chiuse: Optional[list] = None) -> str:
    """Un messaggio solo, a fine giornata: cosa si e' deciso, com'e' andata, cosa ricordare.
    Vuoto se non e' successo niente (il fine settimana, per esempio): niente messaggio."""
    decise = [s for s in seguite if dal <= s.quando < al]
    prese = [s for s in decise if s.entrata]
    finite = [s for s in seguite if s.esito is not None and dal <= s.esito["quando"] < al]
    if not decise and not finite and not aperte and not chiuse:
        return ""
    # I risultati veri del conto, gli stessi del canale operativo; senza, quelli seguiti sulla carta.
    vere = list(chiuse) if chiuse is not None else [float(s.esito["erre"]) for s in finite if s.entrata]
    carta = [float(s.esito["erre"]) for s in finite if not s.entrata]
    giorno = datetime.fromtimestamp(al - 1, tz=NEW_YORK).strftime("%d/%m")
    righe = [f"📋 Riepilogo del {giorno}", "",
             f"• Occasioni guardate: {len(decise)} · prese: {len(prese)} · lasciate: {len(decise) - len(prese)}"]
    if saltate:
        quante = sum(saltate.values())
        perche = ", ".join(f"{n} {m}" for m, n in sorted(saltate.items(), key=lambda a: -a[1]))
        righe.append(f"• Il Capo ne voleva altr{'a' if quante == 1 else 'e'} {quante}, non apert{'a' if quante == 1 else 'e'}: {perche}")
    if vere:
        vinte = sum(r > 0.05 for r in vere)
        righe.append(f"• Operazioni chiuse: {len(vere)} ({vinte} in guadagno) · in tutto {_volte(sum(vere))}")
    else:
        righe.append("• Nessuna operazione chiusa oggi")
    if carta:
        giudizio = ("ha fatto bene a lasciarle" if sum(carta) <= 0 else "avrebbe fatto meglio a prenderne qualcuna")
        righe.append(f"• Le occasioni lasciate, se prese, avrebbero fatto {_volte(sum(carta))}: il Capo {giudizio}")
    righe.append(f"• Aperte adesso: {aperte} · {_pct(rischio_totale)} del conto a rischio")
    if lezioni:
        righe += ["", "Da ricordare"] + [f"• {x}" for x in lezioni[:3]]
    return "\n".join(righe)
