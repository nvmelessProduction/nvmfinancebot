"""L'equipe al lavoro, scritta per essere letta sul telefono.

## Perche' esiste

Per venti giorni la domanda ricorrente e' stata *"perche' il bot ha aperto
quella?"*, e la risposta stava in un archivio SQLite che leggeva una persona
sola. Un sistema che decide e non sa raccontare perche' non e' controllabile,
e uno che nessuno controlla non merita di operare.

Qui ogni agente dice la sua riga: cosa ha visto, cosa ha deciso, e **con quale
numero** -- quello del manuale o quello che si e' guadagnato. Chi legge non
deve sapere cosa sia un CISD.

## Cosa NON e'

Non e' il cavo. I pareri viaggiano in memoria, dentro lo stesso processo, e
questo modulo li **guarda passare**. Se le decisioni dipendessero da un
servizio di chat, una candela da un minuto basterebbe a perderne una: latenza,
messaggi persi, limiti di frequenza.

E non e' un consiglio di amministrazione. Gli agenti non si parlano fra loro e
non si influenzano: ognuno risponde alla sua domanda e passa il parere a chi
decide. Quello che si vede qui e' il verbale, non la riunione.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

# Cosa dice ciascuna conferma, in italiano corrente. La tabella e' quella del
# notifier: importarla invece di ricopiarla, o le due versioni finiranno per
# descrivere la stessa conferma in due modi diversi.
from core.notifier import _IN_PAROLE


def _voce(regola: str, esito: Optional[bool]) -> str:
    """Una conferma in italiano, col suo segno."""
    si, no = _IN_PAROLE.get(regola, (regola, regola))
    if esito is True:
        return f"✅ {si}"
    if esito is False:
        return f"❌ {no}"
    return "⬜ non ha potuto dirlo"


def riga_ricerca(lettura: Optional[Mapping[str, Any]]) -> list[str]:
    """L'agente che cerca il CRT."""
    if not lettura:
        return ["🔍 <b>ricerca</b> — nessun CRT nella forma"]
    coppia = lettura.get("coppia") or lettura.get("tf_crt") or "?"
    livello = lettura.get("key_level")
    testo = f"🔍 <b>ricerca</b> — CRT su {coppia}"
    if livello is not None:
        testo += f", ha spazzato <code>{livello:g}</code>"
    return [testo]


def righe_conferme(responso: Optional[Mapping[str, Optional[bool]]]) -> list[str]:
    """Gli otto pareri, uno per riga.

    Ci sono **tutti**, anche quelli che non bloccano e anche quelli che non
    hanno saputo rispondere. E' il punto: un ordine partito con tre pareri
    favorevoli e uno partito con sette sono due fatti molto diversi, e finche'
    il messaggio diceva solo "aperto" erano indistinguibili.
    """
    if not responso:
        return ["🗣 <b>conferme</b> — nessun parere raccolto"]
    righe = ["🗣 <b>conferme</b>"]
    favore = sum(1 for v in responso.values() if v is True)
    contro = sum(1 for v in responso.values() if v is False)
    muti = sum(1 for v in responso.values() if v is None)
    righe.append(f"   {favore} a favore · {contro} contro · {muti} non lo so")
    for regola in sorted(responso):
        righe.append(f"   {_voce(regola, responso[regola])}")
    return righe


def righe_livelli(ingresso: Optional[float], stop: Optional[float],
                  tp1: Optional[float], target: Optional[float]) -> list[str]:
    """L'agente dei livelli: dove si entra, dove si muore, dove si esce."""
    if stop is None and target is None:
        return ["📐 <b>livelli</b> — non calcolati"]
    pezzi = []
    if ingresso is not None:
        pezzi.append(f"entra <code>{ingresso:g}</code>")
    if stop is not None:
        pezzi.append(f"stop <code>{stop:g}</code>")
    if tp1 is not None:
        pezzi.append(f"parziale <code>{tp1:g}</code>")
    if target is not None:
        pezzi.append(f"bersaglio <code>{target:g}</code>")
    righe = ["📐 <b>livelli</b> — " + " · ".join(pezzi)]
    if ingresso is not None and stop is not None and target is not None:
        rischio = abs(ingresso - stop)
        if rischio > 0:
            righe.append(
                f"   rapporto <b>{abs(target - ingresso) / rischio:.1f}</b> a 1")
    return righe


def righe_modello(
    probabilita: Optional[float], rapporto: Optional[float],
    costo_in_erre: Optional[float], valore_atteso: Optional[float],
) -> list[str]:
    """L'algoritmo grande, con l'aritmetica in chiaro.

    Si mostra il conto e non solo il verdetto. `p x RR - (1 - p) - costi` e'
    una riga di aritmetica: chi legge deve poterla rifare a mano, o "il
    modello dice di no" diventa un oracolo, e da un oracolo non ci si difende.
    """
    if probabilita is None:
        return ["🧠 <b>modello</b> — nessun peso stimato: decidono le regole"]
    righe = [f"🧠 <b>modello</b> — probabilita' {probabilita:.0%}"]
    if rapporto is not None and costo_in_erre is not None:
        atteso = (valore_atteso if valore_atteso is not None
                  else probabilita * rapporto - (1 - probabilita) - costo_in_erre)
        righe.append(
            f"   {probabilita:.2f} × {rapporto:.2f} − {1 - probabilita:.2f}"
            f" − {costo_in_erre:.2f} = <b>{atteso:+.2f} R</b>")
        righe.append("   " + ("conviene" if atteso > 0 else "non conviene"))
    return righe


def righe_rischio(volume: Optional[float], rischio: Optional[float]) -> list[str]:
    if volume is None:
        return ["⚖️ <b>rischio</b> — nessuna size calcolata"]
    testo = f"⚖️ <b>rischio</b> — {volume:g} lotti"
    if rischio is not None:
        testo += f", {rischio:g} a rischio"
    return [testo]


def righe_carriera(appresi: Mapping[str, Any],
                   registro: Optional[Mapping[str, Any]] = None) -> list[str]:
    """Con che numero sta lavorando ciascun agente, e da dove viene.

    E' la riga che distingue un bot che applica il manuale da uno che ha
    imparato qualcosa, e senza di essa le due cose sono indistinguibili da
    fuori -- che e' esattamente lo stato in cui questo progetto ha passato
    venti giorni.
    """
    from core.apprendimento import REGISTRO, valore_da_usare

    elenco = registro if registro is not None else REGISTRO
    if not elenco:
        return []
    righe = ["🎓 <b>chi ha imparato cosa</b>"]
    for nome in sorted(elenco):
        competenza = elenco[nome]
        valore, provenienza = valore_da_usare(competenza, appresi.get(nome))
        corto = provenienza.split(" (")[0]
        righe.append(f"   {nome}: {valore:g} — {corto}")
    return righe


def verbale(
    titolo: str,
    lettura: Optional[Mapping[str, Any]] = None,
    responso: Optional[Mapping[str, Optional[bool]]] = None,
    ingresso: Optional[float] = None,
    stop: Optional[float] = None,
    tp1: Optional[float] = None,
    target: Optional[float] = None,
    probabilita: Optional[float] = None,
    rapporto: Optional[float] = None,
    costo_in_erre: Optional[float] = None,
    valore_atteso: Optional[float] = None,
    volume: Optional[float] = None,
    rischio: Optional[float] = None,
    appresi: Optional[Mapping[str, Any]] = None,
    conclusione: str = "",
) -> str:
    """Il verbale completo di una decisione, agente per agente."""
    righe: list[str] = [titolo, ""]
    righe += riga_ricerca(lettura)
    righe += righe_conferme(responso)
    righe += righe_livelli(ingresso, stop, tp1, target)
    righe += righe_modello(probabilita, rapporto, costo_in_erre, valore_atteso)
    righe += righe_rischio(volume, rischio)
    carriera = righe_carriera(appresi or {})
    if carriera:
        righe += [""] + carriera
    if conclusione:
        righe += ["", f"<b>{conclusione}</b>"]
    return "\n".join(righe)
