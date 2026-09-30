"""La squadra intelligente al lavoro nel bot dal vivo (`vivo.py`): chi la accende, le riunioni sulle
occasioni del giro, i messaggi in equipe, le lezioni quando un'occasione finisce.

Si accende da sola se nel `.env` della VPS c'e' `ANTHROPIC_API_KEY` e il pacchetto `anthropic` e'
installato; si spegne da `nvm/vivo/scelte.json` con `"squadra_intelligente": false`. Se le menti non
rispondono (rete, chiave sbagliata, credito finito), il bot decide come prima e lo dice una volta.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from nvm.cervello.viste import COMPAGNI
from nvm.intelligenti.dossier import dossier
from nvm.intelligenti.mente import Mente
from nvm.intelligenti.squadra import Squadra, Verdetto

# Quante riunioni insieme al massimo (ognuna ha gia' otto menti in parallelo).
RIUNIONI_INSIEME = 4


def crea(radice: Path, cartella: Path, scelte: dict) -> Optional[Squadra]:
    if scelte.get("squadra_intelligente") is False:
        return None
    mente = Mente.dal_env(radice, scelte.get("modello"))
    if not mente.disponibile():
        return None
    return Squadra(mente, cartella / "intelligenti")


def _conto(conto, vive) -> str:
    if conto is None:
        return ""
    aperte = [f"{v.strumento} {v.verso}" for v in vive if not getattr(v, "pareggio_fatto", False)]
    return (f"Conto demo: saldo {conto.saldo:.0f} {conto.valuta}; operazioni aperte a rischio: "
            f"{', '.join(aperte) if aperte else 'nessuna'}.")


def manca_a_romeo(d) -> str:
    """Le due domande della lista di Romeo che il sistema sa gia': c'e' un key level del grafico sopra?
    Siamo nelle sue ore (Londra o New York)? Se no, non si entra e la squadra non si riunisce nemmeno
    (sui vent'anni queste occasioni rendono meno in 14 anni su 18). Restituisce cosa manca, o ""."""
    kl, ar = getattr(d, "key_level", None), getattr(d, "alla_romeo", None)
    mancano = []
    if kl is None or not (kl.massimo or kl.rejection_block or kl.fvg):
        mancano.append("nessun key level del grafico sopra")
    if ar is None or not (ar.londra or ar.new_york):
        mancano.append("fuori dalle ore di Londra e New York")
    return " e ".join(mancano)


def _scartata(motivo: str) -> Verdetto:
    return Verdetto(False, -1, 0.0, 0.0, [], {"lista di Romeo": motivo}, {}, 0.0, 0)


def riunioni(squadra: Squadra, decisioni, basi: dict, fini: dict, giudizi: dict, conto=None,
             vive=(), filtro_romeo: bool = True) -> dict[str, Verdetto]:
    """La squadra si riunisce su ogni occasione del giro che passa le domande di Romeo che il sistema
    sa gia' (`manca_a_romeo`), piu' occasioni insieme; le altre sono un no senza riunione. Restituisce
    i verdetti per chiave; manca chi non ha avuto risposta dalle menti."""
    def una(d):
        s = d.r.strumento
        gemello = COMPAGNI.get(s)
        g = (basi.get(gemello[0]), gemello[1]) if gemello and basi.get(gemello[0]) is not None else None
        fiducia = (giudizi.get(d.chiave) or {}).get("fiducia")
        testo = dossier(d, basi[s], fini.get(s), g, fiducia)
        return d.chiave, squadra.riunione(d.chiave, s, testo, _conto(conto, vive))
    fatte = {}
    da_discutere = []
    for d in decisioni:
        motivo = manca_a_romeo(d) if filtro_romeo else ""
        if motivo:
            fatte[d.chiave] = _scartata(motivo)
        else:
            da_discutere.append(d)
    if not da_discutere:
        return fatte
    with ThreadPoolExecutor(min(RIUNIONI_INSIEME, len(da_discutere))) as pool:
        for chiave, v in pool.map(una, da_discutere):
            if v is not None:
                fatte[chiave] = v
    return fatte


def voci(v: Verdetto) -> list:
    """La discussione della squadra, come messaggi di colleghi nel canale equipe."""
    from nvm.vivo.conversazione import Voce
    return [Voce(chi, testo) for chi, testo in v.voci if testo]


def lezioni_in_breve(lezioni: list[dict], chiave: str, erre: float) -> str:
    righe = [f"📓 Lezioni da {chiave.split(' crt ')[0]} ({erre:+.2f} R):"]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in lezioni]
    return "\n".join(righe)


def manuali_in_breve(cambi: list[tuple[str, str, str]]) -> str:
    if not cambi:
        return ""
    righe = ["🧠 Revisione del sabato: ognuno ha riscritto il suo manuale."]
    for a, cosa, proposta in cambi:
        righe.append(f"• {a}: {cosa}" + (f" Propone: {proposta}" if proposta.strip() else ""))
    return "\n".join(righe)


def costo_in_breve(squadra: Squadra, prima: tuple = (0, 0.0, 0)) -> tuple[str, tuple]:
    """Quanto ha pensato la squadra da `prima` (chiamate, dollari, errori) a oggi, e il punto nuovo."""
    c = squadra.mente.consumo
    adesso = (c.chiamate, c.dollari(), c.errori)
    n, dollari, errori = (adesso[i] - prima[i] for i in range(3))
    testo = (f"🧠 Oggi la squadra intelligente ha pensato {n} volte (circa ${dollari:.2f}"
             + (f", {errori} risposte mancate" if errori else "") + ").")
    return testo, adesso
