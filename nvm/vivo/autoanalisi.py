"""Ogni agente si chiede dove ha sbagliato (l'utente, 25/09/2026: *"voglio che
siano i vari agenti a chiedersi dove hanno sbagliato. Il bot deve essere
intelligente"*).

Quando una decisione finisce (presa o seguita sulla carta):

- **Livelli e Grilletto** rifanno l'operazione sugli stessi prezzi con le loro
  scelte vicine (un passo di ogni manopola) e dicono se una li avrebbe
  salvati. Il risultato va nel diario delle alternative: il sabato ognuno
  dice cosa, dal vivo, gli avrebbe reso di piu'.
- **Gli agenti dei segnali** (Cacciatore, Key level, Orario, Bias) guardano
  se avevano spinto dalla parte sbagliata, e quanto vale di solito quel loro
  segnale, sui vent'anni e dal vivo: una perdita dove di solito si vince puo'
  capitare; una perdita dove si perde spesso vuol dire che il Capo li deve
  ascoltare meno li'.
- **Il Capo** confronta la sua stima col risultato, su tutte le decisioni dal
  vivo con una stima simile.
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np

from nvm.agenti import manopole
from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import Candele
from nvm.prova.campo import Operazione, simula
from nvm.vivo.dialogo import BINARIE, firma

# Le manopole che si possono rifare sui prezzi di un'operazione gia' fatta.
RIFACIBILI = {
    "Livelli": ("stop minimo", "secondo obiettivo oltre il lato", "pareggio", "tempo"),
    "Grilletto": ("invalidazione",),
}
# Sotto questa differenza un'alternativa "non cambiava niente".
POCO = 0.2


def _operazione(s, stop_minimo: float, oltre: float, pareggio_a: float, invalida: int, tempo: int) -> Optional[Operazione]:
    """L'operazione della decisione, con le scelte dei Livelli e del Grilletto date."""
    if s.crt_alto is None or s.crt_basso is None or s.estremo is None:
        return None
    short = s.verso == "short"
    ampiezza = s.crt_alto - s.crt_basso
    stop = max(s.estremo, s.ingresso + stop_minimo * ampiezza) if short else min(s.estremo, s.ingresso - stop_minimo * ampiezza)
    tp2 = s.crt_basso - oltre * ampiezza if short else s.crt_alto + oltre * ampiezza
    try:
        return Operazione(s.strumento, Verso(s.verso), s.quando, s.ingresso, stop, s.tp1, tp2,
                          pareggio_a=pareggio_a, livello_model1=s.livello, invalida_candele=invalida, tempo_candele=tempo)
    except ValueError:
        return None


CHIAVI = {"stop minimo": "stop_minimo", "secondo obiettivo oltre il lato": "oltre", "pareggio": "pareggio_a",
          "tempo": "tempo", "invalidazione": "invalida"}


def _numero(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def scelta(nome: str, v) -> str:
    """Una scelta alternativa, in parole."""
    if nome == "stop minimo":
        return f"stop almeno a {_numero(v)} del range dall'ingresso"
    if nome == "secondo obiettivo oltre il lato":
        return f"secondo obiettivo {_numero(v)} range oltre il lato"
    if nome == "pareggio":
        return "pareggio al primo obiettivo" if v >= 1 else f"pareggio a {_numero(v)} del cammino verso il primo obiettivo"
    if nome == "tempo":
        return "nessuna uscita a tempo" if not v else f"fuori se il primo obiettivo non arriva in {v} candele"
    if nome == "invalidazione":
        return "nessuna uscita per invalidazione" if not v else f"fuori dopo {v} chiusur{'a' if v == 1 else 'e'} oltre il livello della conferma"
    return f"{nome} {_numero(v) if isinstance(v, float) else v}"


def alternative(s, basse: Candele) -> dict[str, list[tuple[str, float, float]]]:
    """Per Livelli e Grilletto: com'era finita l'operazione con ognuna delle loro scelte vicine.
    Per agente: (manopola, valore, R)."""
    base = dict(stop_minimo=s.stop_minimo, oltre=s.oltre, pareggio_a=s.pareggio_a,
                invalida=s.invalida_candele, tempo=s.tempo_candele)
    fuori: dict[str, list[tuple[str, float, float]]] = {}
    if base["stop_minimo"] is None or base["oltre"] is None:
        return fuori
    for agente, nomi in RIFACIBILI.items():
        for nome in nomi:
            for v in manopole.trova(agente, nome).vicini(base[CHIAVI[nome]]):
                op = _operazione(s, **{**base, CHIAVI[nome]: v})
                if op is None:
                    continue
                fuori.setdefault(agente, []).append((nome, v, float(simula(op, basse, s.scadenza).erre)))
    return fuori


def aggiorna(diario: dict, alt: dict[str, list[tuple[str, float, float]]], reale: float) -> None:
    """Il diario delle alternative: per agente e scelta ("manopola=valore"), [somma dei R con
    quella scelta, somma dei R veri, operazioni, somma dei quadrati delle differenze]."""
    tutte = diario.setdefault("alternative", {})
    for agente, voci in alt.items():
        for nome, v, r in voci:
            x = tutte.setdefault(agente, {}).setdefault(json.dumps([nome, v]), [0.0, 0.0, 0, 0.0])
            x[0] += r
            x[1] += reale
            x[2] += 1
            x[3] += (r - reale) ** 2


# Da quante operazioni dal vivo una scelta si racconta, e da quante (con che certezza) e' "solida".
RACCONTA, SOLIDA, CERTEZZA = 3, 20, 2.0


def riassunto(diario: dict) -> list[str]:
    """Le righe della riunione: per Livelli e Grilletto, cosa avrebbe reso di piu' dal vivo."""
    righe = []
    for agente, scelte in (diario or {}).get("alternative", {}).items():
        voci = []
        for k, (alt, vero, n, quadrati) in scelte.items():
            if n < RACCONTA:
                continue
            nome, v = json.loads(k)
            media = (alt - vero) / n
            sd = float(np.sqrt(max(quadrati / n - media ** 2, 0.0)))
            certezza = media / (sd / np.sqrt(n)) if sd > 0 else (float("inf") if media > 0 else 0.0)
            voci.append((media, n, nome, v, certezza))
        if not voci:
            continue
        media, n, nome, v, t = max(voci)
        if media <= 0:
            righe.append(f"• {agente}: dal vivo nessuna mia scelta vicina avrebbe fatto meglio di quelle in uso.")
            continue
        giudizio = ("è una differenza solida: se la palestra la ritrova sui vent'anni, cambio" if n >= SOLIDA and t >= CERTEZZA
                    else "ancora poco per dirlo, continuo a segnare")
        righe.append(f"• {agente}: dal vivo, su {n} operazioni, con «{scelta(nome, v)}» avrei fatto "
                     f"{_r(media)} R a operazione rispetto alle scelte in uso: {giudizio}.")
    return righe


def storia_dei_segnali(x: np.ndarray, erre_storico: np.ndarray) -> dict[str, dict[str, tuple[int, float]]]:
    """Per ogni agente e ogni suo segnale ("firma"), quante operazioni e che R medio sui vent'anni.
    Sotto la chiave "" il R medio di tutte: un segnale si giudica rispetto a quello."""
    fuori: dict[str, dict[str, tuple[int, float]]] = {"": {"": (len(erre_storico), float(np.mean(erre_storico)))}}
    for nome in BINARIE:
        somme: dict[str, list] = {}
        for riga, r in zip(x, erre_storico):
            f = firma(nome, riga)
            v = somme.setdefault(f, [0, 0.0])
            v[0] += 1
            v[1] += float(r)
        fuori[nome] = {f: (n, s / n) for f, (n, s) in somme.items() if n}
    return fuori


def _r(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",").replace("-", "−")


def rifletti(s, alt: dict[str, list[tuple[str, float, float]]], torto: list[str], diario: dict,
             storia: Optional[dict], capo_giusto: bool, simili: tuple[int, int]) -> str:
    """Il messaggio "🔍 Dove ho sbagliato": una riga per chi ha qualcosa da dire."""
    reale = float(s.esito["erre"])
    righe = []
    for agente, voci in alt.items():
        nome, v, r = max(voci, key=lambda a: a[2])
        if r > reale + POCO:
            righe.append(f"• {agente}: con «{scelta(nome, v)}» sarebbe finita {_r(r)} R invece di {_r(reale)} R. "
                         "Lo segno nel diario delle alternative: sabato dico com'è andata su tutte.")
        elif reale < 0:
            righe.append(f"• {agente}: nessuna mia scelta vicina l'avrebbe salvata: l'errore non è mio.")
    for nome in torto:
        if nome not in BINARIE:
            continue
        f = firma(nome, s.x)
        v, t = diario.get(nome, {}).get(f, [0, 0])
        storico = (storia or {}).get(nome, {}).get(f)
        spingeva = s.spinte.get(nome, 0.0) > 0
        dove = "a entrare" if spingeva else "a non entrare"
        testo = f"• {nome}: avevo spinto {dove} con «{f}»"
        if storico and storia.get(""):
            n, media = storico
            tutte = storia[""][""][1]
            testo += (f"; sui vent'anni con questo segnale le operazioni rendono {_r(media)} R, "
                      f"contro {_r(tutte)} R di tutte ({n} casi)")
            testo += (": di solito qui ho ragione, questa volta è andata male" if (media > tutte) == spingeva
                      else ": qui di solito sbaglio, il Capo farà bene ad ascoltarmi meno")
        if t:
            testo += f"; dal vivo {v} vinte su {t}"
            if t >= 3 and v / t < 0.4:
                testo += ", e dal vivo va peggio: sabato chiedo al Capo di ascoltarmi meno in questi casi"
        righe.append(testo + ".")
    n, giuste = simili
    stima = f"{s.p1:.0%}"
    if not capo_giusto:
        righe.append(f"• Capo: stimavo {stima} di arrivare al primo obiettivo" + (
            f"; dal vivo, su {n} decisioni con una stima simile, è arrivato nel {giuste / n:.0%}." if n >= 5 else
            "; ho ancora poche decisioni dal vivo per dire se sono troppo ottimista."))
    return ("🔍 Dove ho sbagliato\n" + "\n".join(righe)) if righe else ""


def stime_simili(seguite, p1: float, larghezza: float = 0.05) -> tuple[int, int]:
    """Quante decisioni finite avevano una stima del primo obiettivo vicina, e in quante e' arrivato."""
    vicine = [x for x in seguite if x.esito is not None and abs(x.p1 - p1) <= larghezza]
    return len(vicine), sum(bool(x.esito["tp1"]) for x in vicine)
