"""La squadra intelligente al lavoro nel bot dal vivo (`vivo.py`): chi la accende, le riunioni sulle
occasioni del giro, i piani da rivedere, i messaggi in equipe in parole semplici.

La squadra e' nostra (nessuna AI esterna) e decide da sola: si spegne solo da
`nvm/vivo/scelte.json` con `"squadra_intelligente": false`.
"""

from __future__ import annotations

import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from datetime import datetime

from nvm.agenti.cacciatore import Verso
from nvm.dati.candele import costruisci
from nvm.intelligenti import metodo, pareri as P
from nvm.intelligenti.squadra import MASSIMO_PER_GIRO, SOGLIA_PUNTI, Squadra, Verdetto
from nvm.prova.campo import Operazione, Uscita, simula
from nvm.tempo import NEW_YORK, TF


def crea(cartella: Path, scelte: dict) -> Optional[Squadra]:
    if scelte.get("squadra_intelligente") is False:
        return None
    return Squadra(cartella / "intelligenti")


def _dati(op) -> Optional[dict]:
    if op is None:
        return None
    d = asdict(op)
    d["verso"] = op.verso.value
    return d


def _gemello(strumento: str, basi: dict):
    """Le ore del mercato gemello per l'SMT (V8 22:00), se il bot le ha: solo le coppie di Romeo."""
    g = metodo.GEMELLI.get(strumento)
    if not g or g[0] not in basi:
        return None
    return basi[g[0]], g[1]


def riunioni(squadra: Squadra, decisioni, basi: dict, fini: dict, esposizione: float = 0.0,
             per_strumento: Optional[dict] = None, contesto: Optional[P.Contesto] = None,
             occupati=()) -> dict[str, Verdetto]:
    """La squadra si riunisce su ogni occasione del giro: le domande del metodo (`metodo.py`), il parere di ognuno
    (`pareri.py`), poi decide il Capo. Alla fine il Capo sceglie le migliori del giro (`scegli`): il riassunto della
    scelta resta in `squadra.ultima_scelta`. Restituisce i verdetti per chiave; manca solo l'occasione su cui qualcosa
    si e' rotto (l'errore resta in `squadra.ultimo_errore`). `per_strumento`: la parte del conto gia' a rischio su
    ogni strumento, per il Rischio; `contesto`: la previsione della domenica; `occupati`: gli strumenti con
    un'operazione gia' aperta."""
    fatte = {}
    ctx = contesto or P.Contesto()
    squadra.ultima_scelta = ""
    for d in decisioni:
        s = d.r.strumento
        try:
            pareri = None
            if getattr(d, "foto", None):
                m = metodo.valuta_foto(d)
                prev = previsione_di(squadra, s, d.foto["quadro"], int(d.r.quando))
                pareri = P.tutti(d, ctx, prev)
            else:
                m = metodo.valuta(d, basi[s], fini.get(s), _gemello(s, basi))
            piani = getattr(d, "piani_romeo", None) or None
            seguire = {"strumento": s, "basso": d.r.basso_tf.value, "scadenza": int(d.scadenza),
                       "piani": [_dati(op) for op in piani]} if piani else None
            v = squadra.riunione(d.chiave, s, m, int(d.r.quando), piani, esposizione, seguire, d.op,
                                 stesso=(per_strumento or {}).get(s, 0.0), pareri=pareri)
            v.metodo = m
            fatte[d.chiave] = v
        except Exception:
            squadra.ultimo_errore = traceback.format_exc()[-1500:]
    try:
        squadra.ultima_scelta = scegli(squadra, decisioni, fatte, ctx, set(occupati))
    except Exception:
        squadra.ultimo_errore = traceback.format_exc()[-1500:]
    squadra.salva()
    return fatte


def previsione_di(squadra: Squadra, strumento: str, q, t: int) -> P.Previsione:
    """La previsione del Bias per oggi su `strumento`: quella gia' fatta, o la fa adesso con le candele chiuse
    all'apertura del giorno (e' la stessa a qualunque ora la si faccia) e la tiene fino a sera."""
    giorno = P.apertura_giorno(t, strumento)
    d = squadra.memoria.previsioni.get(strumento)
    if d is not None and int(d.get("giorno", 0)) == giorno:
        return P.Previsione.da_dati(d)
    p = P.previsione(q, t)
    squadra.memoria.previsioni[strumento] = p.come_dati()
    return p


def previsioni_del_giorno(squadra: Squadra, quadri: dict, adesso: int) -> str:
    """Il Bias all'apertura del giorno: le sue previsioni su tutti gli strumenti, una volta al giorno. Le tiene fino a
    sera: cambia solo quando il livello viene preso. "" se le ha gia' dette oggi."""
    giorno = P.apertura_giorno(adesso)
    if squadra.memoria.previsioni_dette == giorno or not quadri:
        return ""
    su, giu, niente = [], [], []
    for s, q in sorted(quadri.items()):
        try:
            p = previsione_di(squadra, s, q, adesso)
        except Exception:
            continue
        (su if p.verso > 0 else giu if p.verso < 0 else niente).append((s, p))
    squadra.memoria.previsioni_dette = giorno
    squadra.salva()
    data = datetime.fromtimestamp(giorno + 6 * 3600, tz=NEW_YORK).strftime("%d/%m")
    righe = [f"Le mie previsioni per oggi ({data}). Le tengo tutto il giorno: cambio idea solo quando il livello "
             "viene preso. Contro queste voto no."]
    righe += [f"⬆ {s} verso {P._numero(p.livello)}: {p.motivo}" for s, p in su]
    righe += [f"⬇ {s} verso {P._numero(p.livello)}: {p.motivo}" for s, p in giu]
    if niente:
        righe.append(f"➖ Senza direzione: {', '.join(s for s, _ in niente)}")
    return "\n".join(righe)


def scegli(squadra: Squadra, decisioni, verdetti: dict, ctx: P.Contesto, occupati: set) -> str:
    """Il Capo sceglie le migliori del giro: in ordine di probabilita', al massimo `MASSIMO_PER_GIRO`, niente sugli
    strumenti gia' occupati. Quelle lasciate non si aprono (si seguono sulla carta e la squadra impara lo stesso).
    Restituisce il riassunto per l'equipe ("" se nel giro non c'era niente con tutte le regole del metodo)."""
    per_chiave = {d.chiave: d for d in decisioni}
    giri: dict = {}
    for k, v in verdetti.items():
        if v.a_piu and v.pareri_squadra and k in per_chiave:
            giri.setdefault(int(per_chiave[k].r.quando), []).append((k, v))
    testi = [_scegli_nel_giro(squadra, per_chiave, giri[q], ctx, set(occupati)) for q in sorted(giri)]
    return "\n\n".join(x for x in testi if x)


def _scegli_nel_giro(squadra: Squadra, per_chiave: dict, a_piu: list, ctx: P.Contesto, occupati: set) -> str:
    # Il Capo sceglie i CRT con piu' probabilita' (il proprietario, 07/10/2026: *"il capo deve decidere quali CRT
    # hanno più probabilità"*).
    a_piu.sort(key=lambda kv: (-kv[1].fiducia, -kv[1].punti))
    scelte, lasciate = [], []
    for k, v in a_piu:
        d = per_chiave[k]
        s = d.r.strumento
        segno = -1 if d.r.verso is Verso.SHORT else 1
        motivo = ""
        if not v.entra:
            veto = v.pareri.get("Capo", {}).get("veto", "")
            if veto:
                motivo = veto
            elif v.punti < SOGLIA_PUNTI:
                contro = sorted((x for x in v.pareri_squadra if x.voto < 0), key=lambda x: x.voto)
                motivo = "la squadra non è convinta" + (": contro " + ", ".join(f"{x.agente} ({x.voto:+d})"
                                                                                  for x in contro[:3]) if contro else "")
            else:
                motivo = "il Rischio non trova una puntata possibile"
        elif s in occupati:
            motivo = f"su {s} c'è già un'operazione aperta"
        elif any(s == x for x, _, _ in scelte):
            motivo = f"su {s} ho già scelto un'altra occasione in questo giro"
        elif len(scelte) >= MASSIMO_PER_GIRO:
            motivo = f"ho già scelto le {MASSIMO_PER_GIRO} migliori di questo giro"
        if motivo:
            if v.entra:
                v.entra = False
                v.lasciata = motivo
                squadra.annulla(k)
            lasciate.append((s, segno, v.fiducia, motivo))
            continue
        scelte.append((s, segno, v.fiducia))
    ora = datetime.fromtimestamp(int(min(per_chiave[k].r.quando for k, _ in a_piu)), tz=NEW_YORK).strftime("%H:%M")
    freccia = lambda segno: "🟢" if segno > 0 else "🔴"
    righe = [f"Giro delle {ora} di New York: {len(a_piu)} CRT con tutte le regole del metodo. Li metto in ordine di "
             "quanto spesso stimo che vadano bene, dopo aver sentito la squadra, e prendo i migliori."]
    if scelte:
        righe.append("Scelgo: " + "; ".join(f"{s} {freccia(g)} ({_p(x)})" for s, g, x in scelte) + ".")
    else:
        righe.append("Non scelgo niente.")
    if lasciate:
        righe.append("Lascio:")
        righe += [f"• {s} {freccia(g)} ({_p(x)}): {m}" for s, g, x, m in lasciate[:10]]
        if len(lasciate) > 10:
            righe.append(f"• e altre {len(lasciate) - 10}")
    return "\n".join(righe)


def _p(x: float) -> str:
    return f"{x:.0%}"


def _punti(x: float) -> str:
    return f"{x:+.1f}".replace(".", ",")




def valuta_piani(squadra: Squadra, basi: dict, fini: dict, adesso: int) -> int:
    """Livelli rivede i piani delle occasioni passate: come sarebbe andato ogni stop e ogni uscita.
    Quando sono finiti tutti (o e' scaduta l'occasione) li impara. Restituisce quante ne ha imparate."""
    with squadra._lucchetto:
        return _valuta_piani(squadra, basi, fini, adesso)


def _valuta_piani(squadra: Squadra, basi: dict, fini: dict, adesso: int) -> int:
    candele: dict = {}
    imparate = 0
    for chiave, d in list(squadra.memoria.da_vedere.items()):
        try:
            sorgente = fini if TF(d["basso"]) is TF.M15 else basi
            if d["strumento"] not in sorgente:
                continue
            k = (d["strumento"], d["basso"])
            if k not in candele:
                candele[k] = costruisci(sorgente[d["strumento"]], TF(d["basso"])).chiuse_entro(adesso)
            finiti = d.setdefault("finiti", {})
            for j, p in enumerate(d["piani"]):
                if p is None or str(j) in finiti:
                    continue
                op = Operazione(**{**p, "verso": Verso(p["verso"])})
                e = simula(op, candele[k], d["scadenza"])
                if e.uscita is not Uscita.SCADUTA or adesso >= d["scadenza"]:
                    finiti[str(j)] = float(e.erre)
            if all(p is None or str(j) in finiti for j, p in enumerate(d["piani"])):
                squadra.impara_piani(chiave, [finiti.get(str(j)) for j in range(len(d["piani"]))])
                imparate += 1
        except Exception:
            squadra.ultimo_errore = traceback.format_exc()[-1500:]
            squadra.memoria.da_vedere.pop(chiave, None)
    return imparate


# --- I messaggi in equipe, in parole semplici ---------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:.2%}".replace(".", ",")


def _euro(x: float, valuta: str) -> str:
    testo = f"{abs(x):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return ("−" if x < 0 else "") + testo + f" {valuta}"


def voci(v: Verdetto, rischio: Optional[float] = None, valuta: str = "EUR", quota: Optional[float] = None,
         aperte: int = 0, quota_totale: float = 0.0) -> list:
    """La discussione della squadra su un'operazione aperta, come chat fra colleghi. Il Rischio dice
    quanto ha messo in gioco davvero (in soldi e in parte del conto)."""
    from nvm.vivo.conversazione import Voce
    fuori = []
    for chi, testo in v.voci:
        if not testo:
            continue
        if chi == "Rischio" and rischio is not None:
            testo = f"Metto in gioco {_euro(rischio, valuta)}" + (f" ({_pct(quota)} del conto)" if quota else "") + ". " + testo
            if aperte > 1:
                testo += f" Con le altre aperte, in tutto è in gioco {_pct(quota_totale)} del conto."
        fuori.append(Voce(chi, testo))
    return fuori


def tema(v: Verdetto) -> str:
    """Di quale operazione si parla, per la riga in testa ai messaggi in equipe."""
    from nvm.vivo.conversazione import tema as riga
    f = v.metodo.fatti if v.metodo is not None else {}
    return riga(f.get("strumento", ""), f.get("verso", ""), f.get("coppia", ""))


def benvenuto(strumenti: int) -> str:
    return (f"Guardiamo {strumenti} mercati col metodo delle foto del proprietario (la strategia CRT di Romeo come la "
            "fa lui). Entriamo all'apertura della candela 3, a qualunque ora, quando: la candela 2 ha preso un lato del "
            "range (la candela 1, o la madre se ci sono inside bar) ed è rientrata; la finta ha preso un key level "
            "(massimo o minimo del giorno, della settimana, del mese, dei 3 mesi, dell'anno prima); il timeframe di "
            "comando è dalla nostra parte (ogni giorno, settimana, mese, 3 e 12 mesi si guarda la candela precedente: se ha "
            "accettato contro di noi si aspetta che prenda il suo livello). Stop oltre la candela 2. TP1 all'altro lato del "
            "range, con il 25% chiuso e il pareggio; il resto al gap del timeframe grande (mai un gap già toccato, né "
            "uno la cui terza candela ha accettato), o al key level se il gap non c'è. Lavoriamo su 1 ora "
            "(solo quando prende il key level del giorno e il massimo o minimo delle 4 ore), 4 ore, 6 ore, giorno, "
            "settimana e mese; il DXY vale per tutte le coppie col dollaro. Se manca una regola, aspettiamo. Mai "
            "senza stop.\n"
            "Come lavoriamo: ognuno guarda l'occasione col suo mestiere e vota, da -2 a +2, dicendo perché. Il "
            "Cacciatore guarda se altri timeframe fanno il CRT nello stesso verso e le inside bar, il Key level che "
            "liquidità ha preso, il Bias la sua previsione del giorno (la dice all'apertura e la tiene fino a sera) e "
            "quella della domenica, il Gap i gap, il DXY il dollaro, l'Orario l'ora, Livelli i costi e i target, il "
            "Grilletto la finta. Poi ci sentiamo fra colleghi: chi ha un motivo cambia voto e lo dice. Il Capo ascolta "
            "tutti, pesa ognuno per quanto ci ha preso dal vivo, ed entra solo con almeno "
            f"{_punti(SOGLIA_PUNTI)} punti a favore e mai contro la previsione della domenica; in ogni giro mette i CRT "
            f"in ordine di probabilità e sceglie al massimo i {MASSIMO_PER_GIRO} migliori, e dice cosa prende e cosa "
            "lascia. Decide lui e se ne prende la responsabilità; dopo ogni operazione impara di chi fidarsi di più. "
            "Il Rischio parte dall'1% del conto e si corregge coi risultati. Non siamo un'intelligenza artificiale che "
            "parla: siamo il metodo, il mestiere di ognuno e numeri che si correggono coi fatti.")


def lezioni_in_breve(lezioni: list[dict], nome: str, erre: float) -> str:
    """Quello che la squadra impara da un'operazione chiusa: chi si era sbagliato, il Capo, il Rischio."""
    come = "è andata bene" if erre > 0.05 else "è finita in pari" if erre > -0.05 else "è andata male"
    righe = [f"📓 {nome}: {come}. Cosa impariamo:"]
    sbagliati = [l for l in lezioni if l["agente"] not in ("Capo", "Rischio") and not l.get("giusto")][:3]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in sbagliati]
    righe += [f"• {l['agente']}: {l['lezione']}" for l in lezioni if l["agente"] in ("Capo", "Rischio")]
    giusti = [l["agente"] for l in lezioni if l["agente"] not in ("Capo", "Rischio") and l.get("giusto")]
    if giusti:
        righe.append(f"• Avevano visto giusto: {', '.join(giusti)}.")
    return "\n".join(righe)


def manuali_in_breve(cambi: list[tuple[str, str, str]]) -> str:
    if not cambi:
        return ("🧠 Revisione della settimana: nessuno ha cambiato idea. Non abbiamo ancora visto abbastanza "
                "per cambiare quello che dice Romeo.")
    righe = ["🧠 Revisione della settimana: cosa abbiamo imparato dal vivo."]
    righe += [f"• {a}: {cosa}" for a, cosa, _ in cambi]
    return "\n".join(righe)


def come_va(squadra: Squadra) -> list[str]:
    """Righe per il riepilogo della sera: la puntata del Rischio e chi ci prende di piu'."""
    m = squadra.memoria
    righe = [f"• Il Rischio adesso punta in media {_pct(m.rischio['base'])} del conto a operazione"]
    n, somma, vinte = m.a_piu
    if n:
        righe.append(f"• Occasioni con tutte le regole del metodo finite finora: {n}, andate bene {vinte}")
    voti = [(a, *m.ci_prende(a)) for a in m.voti]
    voti = [(a, g, n) for a, g, n in voti if n >= 5]
    if voti:
        a, g, n = max(voti, key=lambda x: x[1] / x[2])
        righe.append(f"• Chi ci prende di più: {a} ({g} volte su {n})")
    if m.idee:
        righe.append(f"• Idee inventate dalla squadra finora: {len(m.idee)}")
    return righe
