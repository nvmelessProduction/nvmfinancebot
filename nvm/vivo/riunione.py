"""La riunione del fine settimana, sul canale equipe: piu' approfondita del
confronto che gli agenti fanno dopo ogni decisione.

1. com'e' andata la settimana, prese e scartate;
2. le pagelle: quante volte ognuno aveva ragione quando si e' schierato, e la carriera;
3. i consigli fra agenti: le coppie di pareri che insieme cambiano il risultato;
4. il Capo si riaddestra su storico + dal vivo, e prova subito i consigli.

La versione nuova entra in uso subito: gli agenti si addestrano, non si
bloccano (decisione dell'utente, 24/09/2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from nvm.agenti.capo import COLONNE, Capo, pesi_per_eta
from nvm.agenti import portafoglio
from nvm.agenti.portafoglio import Operazioni
from nvm.agenti.rischio import esiti, kelly
from nvm.vivo.autoanalisi import riassunto
from nvm.vivo.dialogo import AGENTI, ascolto, chi_aveva_ragione, consigli, grado
from nvm.vivo.messaggi import erre, qualita
from nvm.vivo.romeo_vivo import META_RISCHIO, EntrataDiRomeo, confronta, etichette, presa_vicina
from nvm.vivo.stato import Seguita


@dataclass
class Storico:
    x: np.ndarray
    tp1: np.ndarray
    tp2: np.ndarray
    erre: Optional[np.ndarray] = None
    quando: Optional[np.ndarray] = None
    # Le puntate di Kelly del cammino anno per anno e i loro risultati: il Rischio impara da qui.
    kelly_f: Optional[np.ndarray] = None
    kelly_r: Optional[np.ndarray] = None
    # I candidati del 2023 e le scelte di Romeo fra loro: il Capo impara da qui
    # quanto un'operazione somiglia a Romeo (`spec/capo.md`).
    romeo_x: Optional[np.ndarray] = None
    romeo_y: Optional[np.ndarray] = None
    romeo_tp1: Optional[np.ndarray] = None
    # Le stesse puntate con ingresso, uscita, strumento e verso: il Rischio le rigioca sul conto intero.
    k_entrata: Optional[np.ndarray] = None
    k_chiusa: Optional[np.ndarray] = None
    k_strumento: Optional[np.ndarray] = None
    k_verso: Optional[np.ndarray] = None

    @classmethod
    def carica(cls, percorso) -> "Storico":
        with np.load(percorso) as f:
            c = lambda k: f[k] if k in f.files else None
            return cls(f["x"], f["tp1"].astype(bool), f["tp2"].astype(bool), c("erre"), c("quando"), c("kelly_f"), c("kelly_r"),
                       c("romeo_x"), None if c("romeo_y") is None else f["romeo_y"].astype(bool),
                       None if c("romeo_tp1") is None else f["romeo_tp1"].astype(bool),
                       c("k_entrata"), c("k_chiusa"), c("k_strumento"), c("k_verso"))


def _x(s: Seguita) -> list[float]:
    """Le colonne di una decisione, allungate se e' stata registrata prima di una colonna nuova."""
    return list(s.x) + [0.0] * (len(COLONNE) - len(s.x))


def _media(v: list[float]) -> str:
    return f"{len(v)} ({erre(float(np.mean(v)))})" if v else "0"


def _peso(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


def _risposta(nome: str, diario: dict) -> str:
    """Cosa risponde un agente al Capo: il suo segnale migliore e il peggiore dal vivo."""
    voci = [(f, v, t) for f, (v, t) in (diario or {}).get(nome, {}).items() if t >= 2]
    if not voci:
        return "pochi casi dal vivo, continuo a raccogliere"
    migliore = max(voci, key=lambda a: a[1] / a[2])
    peggiore = min(voci, key=lambda a: a[1] / a[2])
    testo = f"meglio con «{migliore[0]}» ({migliore[1]}/{migliore[2]})"
    if peggiore[0] != migliore[0]:
        testo += f", peggio con «{peggiore[0]}» ({peggiore[1]}/{peggiore[2]}): pesatemi meno lì"
    return testo


def _romeo_dal_vivo(entrate: list[EntrataDiRomeo], seguite: list[Seguita], dal: int) -> list[str]:
    """Il metro del PIANO sulle entrate di Romeo mandate dal vivo: quante il bot ne ha ritrovate e prese."""
    for e in entrate:
        confronta(e, seguite)   # adesso si conoscono anche le decisioni arrivate dopo il messaggio
    def conta(gruppo):
        viste = sum(e.vista is not None for e in gruppo)
        ritrovate = sum(e.ritrovata for e in gruppo)
        prese = sum((d := presa_vicina(e, seguite)) is not None and d <= META_RISCHIO for e in gruppo)
        return viste, ritrovate, prese
    settimana = [e for e in entrate if e.quando >= dal]
    righe = []
    if settimana:
        v, r, p = conta(settimana)
        mie = sum(s.entrata for s in seguite if s.quando >= dal)
        per_ognuna = f"{mie / len(settimana):.1f}".replace(".", ",")
        righe.append(f"• Questa settimana me ne avete mandate {len(settimana)}: ne avevo viste {v}, ritrovate {r} entro "
                     f"metà del suo rischio, e {p} le avevo anche prese. Io ho aperto {mie} operazioni: "
                     f"{per_ognuna} per ognuna delle sue (se me le avete mandate tutte).")
    v, r, p = conta(entrate)
    righe.append(f"• Da quando me le mandate: {len(entrate)} sue entrate, ritrovate {r}, prese {p}. "
                 "Il metro del PIANO: 7 su 10 prese entro metà del suo rischio, e al massimo 3 mie per ognuna delle sue.")
    return righe


def riunione(
    seguite: list[Seguita], capo: Capo, storico: Storico, dal: int, settimana: str,
    pagelle: Optional[dict] = None, parte: float = 1.0, diario: Optional[dict] = None,
    romeo_vivo: Optional[list[EntrataDiRomeo]] = None, rischio: Optional[dict] = None,
) -> tuple[str, Capo, dict, str]:
    """La riunione del sabato: il Capo e il Rischio si riaddestrano sui dati dal vivo.
    Restituisce il resoconto breve per l'equipe, il Capo nuovo, quello che il Rischio ha
    imparato (`rischio.json`) e il verbale completo (per il registro)."""
    finite = [s for s in seguite if s.esito is not None]
    di_questa = [s for s in finite if s.esito["quando"] >= dal]
    nuove = [s for s in seguite if s.quando >= dal]
    prese = [s.esito["erre"] for s in di_questa if s.entrata]
    scartate = [s.esito["erre"] for s in di_questa if not s.entrata]
    righe = [
        f"📋 Riunione del sabato · settimana {settimana}",
        "",
        "La settimana",
        f"• {len(nuove)} decisioni, {sum(s.entrata for s in nuove)} prese",
        f"• Finite: prese {_media(prese)}, sulla carta {_media(scartate)}",
    ]
    if finite:
        stimato = float(np.mean([s.p1 for s in finite]))
        vero = float(np.mean([s.esito["tp1"] for s in finite]))
        giudizio = ("ero ottimista" if stimato > vero + 0.05 else ("ero prudente" if vero > stimato + 0.05 else "ci ho preso"))
        righe.append(f"• Stimavo il primo obiettivo al {stimato:.0%}, dal vivo è arrivato nel {vero:.0%}: {giudizio}")

    # Il riaddestramento, fatto subito: il Capo parla a ognuno sapendo gia' quanto lo ascoltera'.
    sx = storico.x if storico.x.shape[1] == len(COLONNE) else np.c_[storico.x, np.zeros((len(storico.x), len(COLONNE) - storico.x.shape[1]))]
    x = np.vstack([sx] + ([np.array([_x(s) for s in finite])] if finite else []))
    tp1 = np.r_[storico.tp1, [s.esito["tp1"] for s in finite]].astype(bool)
    tp2 = np.r_[storico.tp2, [s.esito["tp2"] for s in finite]].astype(bool)
    scelti = []
    if storico.erre is not None:
        scelti = consigli(x, np.r_[storico.erre, [s.esito["erre"] for s in finite]])
    pesi = None
    if storico.quando is not None:
        quando = np.r_[storico.quando, [s.esito["quando"] for s in finite]]
        pesi = pesi_per_eta(quando, int(quando.max()))
    nuovo = Capo.allena(x, tp1, tp2, interazioni=tuple(c for _, c in scelti), pesi=pesi)
    romeo = storico.romeo_x is not None and storico.romeo_x.shape[1] == len(COLONNE) and storico.romeo_y.any()
    # Le entrate di Romeo mandate dal vivo si aggiungono a quelle del 2023.
    casi_vivi, scelte_vive = etichette(romeo_vivo or [], seguite)
    if romeo:
        rx, ry = storico.romeo_x, storico.romeo_y
        if casi_vivi:
            rx = np.vstack([rx, np.array([_x(s) for s in casi_vivi])])
            ry = np.r_[ry, scelte_vive]
        nuovo = nuovo.impara_romeo(rx, ry)
        # La fiducia in Romeo: dai risultati dei candidati del 2023 e di tutte le decisioni dal vivo.
        casi_x, casi_tp1 = [], []
        if storico.romeo_tp1 is not None:
            casi_x.append(storico.romeo_x)
            casi_tp1.append(storico.romeo_tp1)
        if finite:
            casi_x.append(np.array([_x(s) for s in finite]))
            casi_tp1.append(np.array([bool(s.esito["tp1"]) for s in finite]))
        if casi_x:
            nuovo = nuovo.impara_fiducia(np.vstack(casi_x), np.concatenate(casi_tp1))
    # Quanto il Capo ascolta ognuno, prima e dopo, sugli stessi casi.
    casi = storico.romeo_x if storico.romeo_x is not None and storico.romeo_x.shape[1] == len(COLONNE) else sx[-3000:]
    prima, dopo = ascolto(capo, casi), ascolto(nuovo, casi)

    settimanali: dict[str, list[int]] = {}
    for s in di_questa:
        ragione, torto = chi_aveva_ragione(s.spinte, s.esito["erre"] > 0)
        for n in ragione:
            settimanali.setdefault(n, [0, 0])[0] += 1
            settimanali[n][1] += 1
        for n in torto:
            settimanali.setdefault(n, [0, 0])[1] += 1

    righe += ["", "Le pagelle"]
    for nome in list(AGENTI) + (["Romeo"] if "Romeo" in dopo else []):
        g, t = settimanali.get(nome, [0, 0])
        tot = (pagelle or {}).get(nome, [0, 0])
        verso = ("di più" if dopo.get(nome, 0) > prima.get(nome, 0) * 1.05 + 1e-4
                 else ("di meno" if dopo.get(nome, 0) < prima.get(nome, 0) * 0.95 - 1e-4 else "come prima"))
        riga = (f"• {nome} — questa settimana {g} giuste su {t}"
                + (f", in tutto {tot[0]} su {tot[1]} ({grado(*tot)})" if tot[1] else "")
                + f". Lo ascolto {verso}: {qualita(prima.get(nome, 0))[1:]} → {qualita(dopo.get(nome, 0))[1:]}.")
        if nome == "Romeo":
            riga += f" Fiducia {_peso(capo.fiducia_in_romeo)} → {_peso(nuovo.fiducia_in_romeo)}."
        righe.append(riga)
        if nome in AGENTI:
            righe.append(f"  ↳ {_risposta(nome, diario)}")

    alternative = riassunto(diario or {})
    if alternative:
        righe += ["", "Dove abbiamo sbagliato (le operazioni rifatte con le scelte vicine)"] + alternative

    righe += ["", "Consigli fra agenti (da oggi li provo)"]
    righe += [f"• {testo}" for testo, _ in scelti] or ["• nessuna coppia che cambi davvero il risultato"]

    # Il Rischio: rigioca il conto intero con le puntate dei vent'anni e quelle dal vivo, aperte
    # insieme (`nvm/agenti/portafoglio.py`). Senza lo storico completo resta com'era: la parte
    # imparata una puntata alla volta non vede le operazioni aperte insieme, e brucerebbe il conto.
    dal_vivo = [s for s in finite if s.presa_dal_capo]
    rischio = dict(rischio or {"parte": parte})
    nuovo_rischio, n_puntate = rischio, 0
    if storico.k_entrata is not None and storico.kelly_f is not None:
        op = Operazioni(
            np.r_[storico.k_entrata, [s.quando for s in dal_vivo]],
            np.r_[storico.k_chiusa, [s.esito["quando"] for s in dal_vivo]],
            np.r_[storico.k_strumento, [s.strumento for s in dal_vivo]],
            np.r_[storico.k_verso, [-1 if s.verso == "short" else 1 for s in dal_vivo]],
            np.r_[storico.kelly_f, [kelly(esiti(s.p1, s.q, s.rr1, s.rr2, s.costi)) for s in dal_vivo]],
            np.r_[storico.kelly_r, [s.esito["erre"] for s in dal_vivo]])
        corr = portafoglio.correlazioni(op)
        nuovo_rischio = portafoglio.come_dati(portafoglio.scegli(op, corr), corr)
        n_puntate = len(op)
    parte, nuova_parte = float(rischio["parte"]), float(nuovo_rischio["parte"])
    if romeo:
        pesi_romeo = sorted(nuovo.fiducia_romeo(), key=lambda a: -a[1])
        righe += ["", "Romeo",
                  f"• Ho ripassato le sue {int(storico.romeo_y.sum())} entrate del 2023: le sue scelte hanno soprattutto "
                  + ", ".join(n for n, w in pesi_romeo[:3] if w > 0)]
        if scelte_vive.any():
            righe.append(f"• E le {int(scelte_vive.sum())} che mi avete mandato dal vivo: le ho imparate insieme.")
        prese_simili = [s.romeo for s in nuove if s.entrata]
        scartate_simili = [s.romeo for s in nuove if not s.entrata]
        if prese_simili and scartate_simili:
            righe.append(f"• Le mie prese gli somigliavano al {np.mean(prese_simili):.1%}, le scartate al "
                         f"{np.mean(scartate_simili):.1%}".replace(".", ","))
    if romeo_vivo:
        righe += ["", "Romeo dal vivo"] + _romeo_dal_vivo(romeo_vivo, seguite, dal)
    rischio_riga = (f"Rischio: ho rigiocato il conto intero su {n_puntate} operazioni, {len(dal_vivo)} dal vivo: "
                    f"fiducia minima {nuovo_rischio.get('minimo', 0):g}, uso {_peso(nuova_parte)[1:]} del Kelly "
                    f"(era {_peso(parte)[1:]})."
                    + (f" Nelle storie sfortunate il conto cala al massimo del {nuovo_rischio['calo_sfortunato']:.0%}."
                       if "calo_sfortunato" in nuovo_rischio else "")
                    if n_puntate else "Rischio: senza lo storico completo resto com'ero.")
    righe += [
        "",
        rischio_riga,
        "",
        f"Capo: mi sono riaddestrato su {len(storico.x)} operazioni dello storico e {len(finite)} dal vivo. "
        "Da adesso lavoro così. Buon fine settimana.",
    ]
    breve = _breve(settimana, nuove, prese, scartate, finite, settimanali, prima, dopo, scelti, parte, nuova_parte,
                   len(storico.x), diario, capo, nuovo, romeo)
    if romeo_vivo:
        breve += "\n\nRomeo dal vivo\n" + "\n".join(_romeo_dal_vivo(romeo_vivo, seguite, dal))
    return breve, nuovo, nuovo_rischio, "\n".join(righe)


def _volte(x: float) -> str:
    return (f"{x:+.2f}".replace(".", ",").replace("-", "−")) + " volte il rischio"


def _breve(settimana, nuove, prese, scartate, finite, settimanali, prima, dopo, scelti, parte, nuova_parte,
           storici, diario, capo, nuovo, romeo) -> str:
    """Il resoconto della settimana per l'equipe: com'e' andata, chi ha lavorato meglio e peggio,
    cosa cambia da lunedi'. In parole semplici; i dettagli restano nel verbale."""
    aperte = sum(s.entrata for s in nuove)
    righe = [f"📊 Riunione del sabato · settimana {settimana}", "", "Com'è andata",
             f"• Operazioni aperte: {aperte} · chiuse: {len(prese)}"
             + (f" · risultato {_volte(sum(prese))}" if prese else "")]
    if scartate:
        giudizio = "bene averle lasciate" if sum(scartate) <= 0 else "qualcuna andava presa"
        righe.append(f"• Occasioni lasciate: {len(nuove) - aperte}; se prese avrebbero fatto {_volte(sum(scartate))}: {giudizio}")
    if finite:
        stimato = float(np.mean([s.p1 for s in finite]))
        vero = float(np.mean([s.esito["tp1"] for s in finite]))
        giudizio = ("era ottimista, si corregge" if stimato > vero + 0.05 else
                    ("era prudente, si corregge" if vero > stimato + 0.05 else "ci ha preso"))
        righe.append(f"• Il Capo stimava il primo obiettivo nel {stimato:.0%} dei casi, è arrivato nel {vero:.0%}: {giudizio}")
    giudicati = [(n, g, t) for n, (g, t) in settimanali.items() if t >= 5 and n in AGENTI]
    if giudicati:
        righe += ["", "La squadra"]
        meglio = max(giudicati, key=lambda a: a[1] / a[2])
        peggio = min(giudicati, key=lambda a: a[1] / a[2])
        righe.append(f"• Più affidabile: {meglio[0]} ({meglio[1]} giuste su {meglio[2]})")
        if peggio[0] != meglio[0]:
            meno = dopo.get(peggio[0], 0) < prima.get(peggio[0], 0)
            righe.append(f"• Meno affidabile: {peggio[0]} ({peggio[1]} giuste su {peggio[2]})"
                         + (": da lunedì il Capo lo ascolta meno" if meno else ""))
    righe += ["", "Cosa cambia da lunedì",
              f"• Il Capo si è riallenato su {storici} operazioni dei vent'anni e {len(finite)} dal vivo."]
    if nuova_parte < parte * 0.95:
        righe.append("• Il Rischio abbassa la dimensione delle operazioni.")
    elif nuova_parte > parte * 1.05:
        righe.append("• Il Rischio alza la dimensione delle operazioni.")
    else:
        righe.append("• La dimensione delle operazioni resta la stessa.")
    if scelti:
        righe.append(f"• {len(scelti)} nuov{'a' if len(scelti) == 1 else 'e'} regol{'a' if len(scelti) == 1 else 'e'} "
                     "di squadra: quando certi segnali arrivano insieme, il Capo se ne fida meno.")
    solide = [r for r in riassunto(diario or {}) if "solida" in r]
    righe += solide
    if romeo:
        righe.append(f"• La voce di Romeo: fiducia {_peso(capo.fiducia_in_romeo)} → {_peso(nuovo.fiducia_in_romeo)}.")
    return "\n".join(righe)
