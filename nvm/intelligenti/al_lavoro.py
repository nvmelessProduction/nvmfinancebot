"""La squadra intelligente al lavoro nel bot dal vivo (`vivo.py`): chi la accende, le riunioni sulle
occasioni del giro, i messaggi in equipe, le lezioni quando un'occasione finisce.

La squadra e' nostra (nessuna AI esterna) e decide da sola: si spegne solo da
`nvm/vivo/scelte.json` con `"squadra_intelligente": false`.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from nvm.intelligenti.fatti import fatti
from nvm.intelligenti.squadra import PARTE_MASSIMA, Squadra, Verdetto


def crea(cartella: Path, scelte: dict) -> Optional[Squadra]:
    if scelte.get("squadra_intelligente") is False:
        return None
    return Squadra(cartella / "intelligenti")


def riunioni(squadra: Squadra, decisioni, basi: dict, fini: dict) -> dict[str, Verdetto]:
    """La squadra si riunisce su ogni occasione del giro. Restituisce i verdetti per chiave; manca solo
    l'occasione su cui qualcosa si e' rotto (l'errore resta in `squadra.ultimo_errore`)."""
    fatte = {}
    for d in decisioni:
        s = d.r.strumento
        try:
            f = fatti(d, basi[s], fini.get(s))
            fatte[d.chiave] = squadra.riunione(d.chiave, s, f)
        except Exception:
            squadra.ultimo_errore = traceback.format_exc()[-1500:]
    return fatte


def voci(v: Verdetto) -> list:
    """La discussione della squadra, come messaggi di colleghi nel canale equipe."""
    from nvm.vivo.conversazione import Voce
    return [Voce(chi, testo) for chi, testo in v.voci if testo]


def benvenuto(strumenti: int) -> str:
    return (f"Da oggi decidiamo noi, da soli, su {strumenti} strumenti. Ognuno di noi ha le regole di Romeo del suo "
            "mestiere; votiamo, discutiamo, e io entro solo se le cinque domande di Romeo sono tutte sì e la "
            f"squadra è d'accordo. Ogni operazione rischia al massimo l'{PARTE_MASSIMA:.0%} del conto. Impariamo solo "
            "da quello che succede dal vivo, e il sabato ognuno rivede le sue regole.")


def lezioni_in_breve(lezioni: list[dict], chiave: str, erre: float) -> str:
    righe = [f"📓 {chiave.split(' crt ')[0]} finita {erre:+.2f} R. Cosa impariamo:"]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in lezioni if l["agente"] == "Capo" or not l.get("giusto")][:5]
    giusti = [l["agente"] for l in lezioni if l["agente"] != "Capo" and l.get("giusto")]
    if giusti:
        righe.append(f"• Avevano visto giusto: {', '.join(giusti)}.")
    return "\n".join(righe)


def manuali_in_breve(cambi: list[tuple[str, str, str]]) -> str:
    if not cambi:
        return ("🧠 Revisione del sabato: nessuno cambia le sue regole, il vivo non ha ancora dato abbastanza "
                "esperienze per cambiare quello che dice Romeo.")
    righe = ["🧠 Revisione del sabato: ognuno ha rivisto le sue regole con quello che è successo dal vivo."]
    for a, cosa, proposta in cambi:
        righe.append(f"• {a}: {cosa}" + (f" Propone: {proposta}." if proposta.strip() else ""))
    return "\n".join(righe)


def imparato_oggi(squadra: Squadra) -> str:
    """Una riga per il riepilogo della sera: quanto sa la squadra dal vivo."""
    m = squadra.memoria
    n = sum(e.get("n", 0) for e in m.agenti.values())
    if not n:
        return "• La squadra non ha ancora occasioni finite da cui imparare."
    migliore = max(m.agenti, key=m.credito)
    return (f"• La squadra ha imparato da {n} voti dal vivo; chi ci prende di più: {migliore} "
            f"(credito {m.credito(migliore):.2f}).")
