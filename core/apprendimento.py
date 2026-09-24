"""Cosa un agente puo' imparare, e come si prova che l'ha imparato.

## L'obiezione che era sbagliata, e perche'

Per un po' ho sostenuto che l'apprendimento dovesse stare in **un punto solo**,
e l'argomento era: 16.463 CRT divisi per dieci agenti non bastano a nessuno
dei dieci.

L'argomento e' sbagliato perche' presuppone che tutti gli agenti vogliano
imparare la **stessa domanda** -- "questa operazione vince?" -- che e' la
domanda del modello centrale e ha un bit di risposta per CRT. Gli agenti non
hanno quella domanda. Ne hanno una ciascuno, e diverse hanno molti piu' dati:

    il modello centrale   "questo CRT vince?"          1 bit x 16.463
    la sentinella         "a che punto muovere lo stop?" una CURVA x 16.463
    i livelli             "quanto dista il rumore?"      una misura x 16.463
    il rischio            "quanto costera' davvero?"     ogni tick campionato
    il DXY                "la bias del dollaro predice?" 20 anni di serie

Una curva per CRT non e' un bit per CRT. La sentinella vede, per ogni
operazione, **tutto il percorso** fra ingresso ed esito: quanto e' andata
contro prima di andare a favore, dove si e' fermata, quando. Da li' si stima
una soglia continua con molta piu' precisione di quanta ne serva a un
classificatore binario.

Quindi: **ogni agente impara, ma ognuno una domanda sua, con dati suoi.**
Quello che resta vietato e' dieci agenti che imparano la stessa cosa dallo
stesso campione, e un agente che impara da cio' che gli altri **dicono**
invece che da cio' che **succede**.

## La regola che tiene insieme tutto: il predefinito e' la regola di oggi

Ogni competenza ha un valore **predefinito**, ed e' esattamente la costante
che il bot usa adesso. Un modello assente, scaduto, o che non ha superato il
protocollo, non fa comportare il bot in modo strano: lo fa comportare **come
oggi**.

E' la proprieta' che rende sicuro attivare l'apprendimento un agente per
volta. Senza, ogni agente che impara e' un agente che puo' rompersi in un modo
nuovo.

## Il cancello e' lo stesso per tutti

Un valore appreso entra in produzione solo se:

    ha almeno `campioni_minimi` casi fuori campione
    migliora il suo bersaglio di almeno `guadagno_minimo`
    l'intervallo al 95% a blocchi esclude lo zero
    il segno e' stabile fra le finestre

Sono i criteri della Fase 2, applicati a una domanda piu' piccola. Non piu'
deboli perche' la domanda e' piu' piccola: un agente che impara male fa danno
esattamente come un modello che impara male, e lo fa in un punto dove nessuno
sta guardando.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class Competenza:
    """Una domanda che un agente puo' imparare a rispondere.

    Si dichiara una volta, in chiaro, e non cambia mentre si guardano i
    risultati. E' lo stesso motivo per cui i criteri della Fase 2 stanno in
    cima al file: un cancello che si sposta non e' un cancello.
    """

    # Quale agente. Il nome e' quello della funzione nel motore, cosi' chi
    # legge un messaggio sa dove andare a guardare.
    agente: str
    # Cosa impara, in italiano. Serve al canale: un agente che non sa dire
    # cosa sta imparando non e' controllabile da nessuno.
    domanda: str
    # Su cosa si misura il miglioramento.
    bersaglio: str
    # Da dove vengono i dati, e quanti sono.
    fonte: str
    # Il valore che il bot usa OGGI. Un modello assente o bocciato riporta
    # qui, e il bot si comporta come si comporta adesso.
    predefinito: float
    # Il cancello.
    campioni_minimi: int
    guadagno_minimo: float
    unita: str = "R"

    def __post_init__(self) -> None:
        if self.campioni_minimi < 1:
            raise ValueError(f"{self.agente}: campioni_minimi dev'essere >= 1")
        if self.guadagno_minimo <= 0:
            raise ValueError(
                f"{self.agente}: un guadagno minimo di zero non e' un cancello")


@dataclass(frozen=True)
class Appreso:
    """Cosa un agente ha imparato, e se ha diritto di usarlo."""

    competenza: str
    valore: float
    # Il cancello, pezzo per pezzo. Si tengono tutti anche quando uno fallisce:
    # sapere QUALE criterio ha fermato un candidato e' meta' dell'informazione.
    campioni: int
    guadagno: float
    intervallo: tuple[float, float]
    stabilita: float
    quando: str = ""
    note: str = ""

    def esclude_lo_zero(self) -> bool:
        basso, alto = self.intervallo
        return basso > 0.0 or alto < 0.0

    def promosso(self, competenza: Competenza, stabilita_minima: float = 0.80
                 ) -> bool:
        """Ha superato il cancello, tutto intero?

        `and` e non "la maggioranza": ogni criterio copre un modo diverso di
        sbagliarsi, e passarne tre su quattro significa essere esposti al
        quarto.
        """
        return (self.campioni >= competenza.campioni_minimi
                and self.guadagno >= competenza.guadagno_minimo
                and self.esclude_lo_zero()
                and self.stabilita >= stabilita_minima)

    def perche_no(self, competenza: Competenza,
                  stabilita_minima: float = 0.80) -> list[str]:
        """I criteri che NON passano, in italiano.

        Un candidato bocciato senza motivo scritto diventa, dopo una
        settimana, un candidato che "non ha funzionato" -- e nessuno sa piu'
        se il problema era il campione o l'idea.
        """
        mancano: list[str] = []
        if self.campioni < competenza.campioni_minimi:
            mancano.append(
                f"casi fuori campione {self.campioni} < "
                f"{competenza.campioni_minimi}")
        if self.guadagno < competenza.guadagno_minimo:
            mancano.append(
                f"guadagno {self.guadagno:+.4f} {competenza.unita} < "
                f"{competenza.guadagno_minimo:+.4f}")
        if not self.esclude_lo_zero():
            basso, alto = self.intervallo
            mancano.append(
                f"l'intervallo [{basso:+.4f}, {alto:+.4f}] contiene lo zero")
        if self.stabilita < stabilita_minima:
            mancano.append(
                f"stabilita' {self.stabilita:.0%} < {stabilita_minima:.0%}")
        return mancano


def valore_da_usare(
    competenza: Competenza, appreso: Optional[Appreso],
    stabilita_minima: float = 0.80,
) -> tuple[float, str]:
    """Il numero che l'agente usa adesso, e da dove viene.

    **E' l'unico cancello fra cio' che si e' imparato e cio' che opera.** Nessun
    agente legge `Appreso.valore` da solo: se lo facesse, un candidato bocciato
    finirebbe in produzione per distrazione, e nessuno se ne accorgerebbe
    finche' i soldi non sono gia' andati.

    Torna sempre `(valore, provenienza)`, e la provenienza va nel diario: una
    decisione presa con un numero appreso e una presa col predefinito devono
    essere distinguibili a mesi di distanza.
    """
    if appreso is None:
        return competenza.predefinito, "predefinito (nessun modello)"
    if not appreso.promosso(competenza, stabilita_minima):
        motivi = "; ".join(appreso.perche_no(competenza, stabilita_minima))
        return competenza.predefinito, f"predefinito (bocciato: {motivi})"
    return appreso.valore, (
        f"appreso su {appreso.campioni:,} casi, "
        f"{appreso.guadagno:+.4f} {competenza.unita}")


# ===========================================================================
# Il registro: chi impara cosa
# ===========================================================================
#
# Sta qui e non sparso negli agenti perche' la domanda "cosa sta imparando
# questo bot?" deve avere una risposta in un posto solo. Un agente che impara
# senza essere in questo elenco e' un agente che impara di nascosto.

REGISTRO: dict[str, Competenza] = {}


def dichiara(competenza: Competenza) -> Competenza:
    """Mette una competenza nel registro. Due volte lo stesso nome e' un errore."""
    if competenza.agente in REGISTRO:
        raise ValueError(
            f"competenza gia' dichiarata: {competenza.agente}. Due agenti che "
            f"imparano la stessa cosa divergono nel punto che muove i soldi.")
    REGISTRO[competenza.agente] = competenza
    return competenza


def salva(appresi: dict[str, Appreso], percorso: Path) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps({
        "scritto": datetime.now(timezone.utc).isoformat(),
        "appresi": {
            nome: {
                "competenza": a.competenza, "valore": a.valore,
                "campioni": a.campioni, "guadagno": a.guadagno,
                "intervallo": list(a.intervallo), "stabilita": a.stabilita,
                "quando": a.quando, "note": a.note,
            } for nome, a in appresi.items()},
    }, indent=2), encoding="utf-8")


def carica(percorso: Path) -> dict[str, Appreso]:
    """Cio' che gli agenti hanno imparato, o un registro vuoto.

    Un file illeggibile non ferma il bot: torna vuoto, e ogni agente usa il
    suo predefinito, cioe' la regola di oggi. Un errore di lettura non deve
    poter cambiare come si opera.
    """
    if not percorso.exists():
        return {}
    try:
        dato = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    fuori: dict[str, Appreso] = {}
    for nome, a in (dato.get("appresi") or {}).items():
        try:
            basso, alto = a["intervallo"]
            fuori[nome] = Appreso(
                competenza=str(a.get("competenza", nome)),
                valore=float(a["valore"]), campioni=int(a["campioni"]),
                guadagno=float(a["guadagno"]),
                intervallo=(float(basso), float(alto)),
                stabilita=float(a["stabilita"]),
                quando=str(a.get("quando", "")), note=str(a.get("note", "")))
        except (KeyError, TypeError, ValueError):
            continue            # una voce storta non invalida le altre
    return fuori


def riepilogo(appresi: dict[str, Appreso],
              stabilita_minima: float = 0.80) -> str:
    """Cosa sa il bot adesso, in italiano, agente per agente.

    E' il testo che va nel canale. Un sistema che impara e non sa raccontare
    cosa ha imparato e' un sistema di cui nessuno puo' fidarsi -- e questo
    progetto ha gia' passato venti giorni a non capire perche' il bot facesse
    quello che faceva.
    """
    if not REGISTRO:
        return "nessuna competenza dichiarata"
    righe: list[str] = []
    for nome, competenza in sorted(REGISTRO.items()):
        valore, provenienza = valore_da_usare(
            competenza, appresi.get(nome), stabilita_minima)
        righe.append(f"{nome}: {competenza.domanda}")
        righe.append(f"    usa {valore:g} {competenza.unita} — {provenienza}")
    return "\n".join(righe)
