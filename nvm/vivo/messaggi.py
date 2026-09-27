"""Le parole del bot: cosa scrive sui due canali, in italiano semplice.

Stile (riscritti il 24/09/2026 su richiesta dell'utente): frasi brevi, una
cosa per riga, "compro/vendo" invece di long/short, i prezzi come li mostra
MT5, le altre cifre all'italiana. Ogni decisione e' una scheda sola: cosa dice
ogni agente, cosa decide il Capo, chi ha pesato di piu'.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import Bias, Contesto
from nvm.dati.strumenti import STRUMENTI
from nvm.tempo import NEW_YORK, TF
from nvm.vivo.giro import Decisione
from nvm.vivo.romeo_vivo import PIP as PIP_ROMEO

CIFRE = {n: s.cifre for n, s in STRUMENTI.items()}
NOMI_TF = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H4: "4 ore", TF.H1: "1 ora",
           TF.M15: "15 minuti", TF.M5: "5 minuti", TF.M1: "1 minuto"}
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")
# Sotto questa spinta (in R di guadagno atteso) un agente conta "quasi niente".
POCO = 0.015


# --- numeri e parole -----------------------------------------------------------

def prezzo(strumento: str, x: float) -> str:
    """Un prezzo come lo mostra MT5."""
    return f"{x:.{CIFRE.get(strumento, 5)}f}"


def _it(x: float, cifre: int = 2) -> str:
    """Un numero all'italiana: virgola per i decimali, punto per le migliaia."""
    testo = f"{x:,.{cifre}f}"
    return testo.replace(",", "§").replace(".", ",").replace("§", ".")


def quando(t: int) -> str:
    """Un istante in ora di New York, come lo legge un trader: '09/09 03:00 NY'."""
    return datetime.fromtimestamp(int(t), tz=timezone.utc).astimezone(NEW_YORK).strftime("%d/%m %H:%M NY")


def erre(x: float) -> str:
    """Un risultato in R, cioè in volte il rischio: '+1,50 R'."""
    return ("+" if x >= 0 else "−") + _it(abs(x)) + " R"


def qualita(x: float) -> str:
    """Una qualita' attesa (guadagno diviso per quanto oscilla), senza unita': '+0,31'."""
    return ("+" if x >= 0 else "−") + _it(abs(x))


def _capo(d) -> str:
    """Come decide il Capo: sulla qualita' attesa, contro la sua soglia."""
    from nvm.agenti.capo import SOGLIA
    if d.qualita is None:
        return f"guadagno atteso {erre(d.atteso)}"
    return (f"qualità attesa {qualita(d.qualita)} (la mia soglia è {qualita(SOGLIA)}), "
            f"in media {erre(d.atteso)} a operazione")


def euro(x: float, valuta: str) -> str:
    return ("+" if x >= 0 else "−") + _it(abs(x)) + f" {valuta}"


def fa(verso: Verso) -> str:
    return "VENDO" if verso is Verso.SHORT else "COMPRO"


def direzione(verso: Verso) -> str:
    return "vendita" if verso is Verso.SHORT else "acquisto"


def coppia(d: Decisione) -> str:
    return f"{NOMI_TF[d.r.alto_tf]} → {NOMI_TF[d.r.basso_tf]}"


def leggibile(d: Decisione) -> str:
    """Come si chiama una decisione nei messaggi dopo: "EURUSD vendita · giornaliero → 1 ora · 09/09 03:00 NY · CRT 1.0850–1.0900"."""
    k = d.r.strumento
    crt = d.r.scatto.crt if d.r.scatto is not None else None
    fascia = f" · CRT {prezzo(k, crt.crt_low)}–{prezzo(k, crt.crt_high)}" if crt is not None else ""
    return f"{k} {direzione(d.r.verso)} · {coppia(d)} · {quando(d.r.quando)}{fascia}"


def _candela_range(d: Decisione) -> str:
    t = datetime.fromtimestamp(d.r.scatto.crt.range_inizio + 7 * 3600, tz=timezone.utc).astimezone(NEW_YORK)
    if d.r.alto_tf is TF.MN:
        return f"la candela mensile di {MESI[t.month - 1]} {t.year}"
    if d.r.alto_tf is TF.W1:
        return f"la candela settimanale del {t:%d/%m}"
    if d.r.alto_tf is TF.H4:
        return f"la candela a 4 ore del {t:%d/%m %H:%M}"
    return f"la candela giornaliera del {t:%d/%m}"


# --- canale operativo -----------------------------------------------------------

def avvio(login: int, server: str, saldo: float, valuta: str, strumenti: list[str], scarto: int) -> str:
    return "\n".join([
        "🟢 Bot acceso",
        f"Conto demo {login} · {server} · saldo {_it(saldo)} {valuta}",
        f"Guardo {', '.join(strumenti)}",
        "Coppie: mensile → giornaliero · settimanale → 4 ore · giornaliero → 1 ora · 4 ore → 15 minuti",
        "Le decisioni le racconta l'équipe, qui solo quello che succede sul conto.",
    ])


def mancanti(strumenti: list[str], guardati: int) -> str:
    return (f"ℹ️ Il broker non ha {', '.join(strumenti)} su questo conto: li salto. "
            f"Opero su {guardati} strumenti.")


def aggiornato(titolo: str) -> str:
    return f"🔄 Aggiornato e ripartito: {titolo}"


def collegamento(prove: list[tuple[str, bool, str]], aperte: int) -> str:
    """La prova del collegamento con MT5: nessun ordine mandato, solo il controllo del broker."""
    righe = ["🔌 Collegamento con MT5 (controllo senza aprire niente)"]
    if all(ok for _, ok, _ in prove):
        righe.append(f"✅ Il broker accetta gli ordini su tutti e {len(prove)} gli strumenti")
    else:
        righe += [f"{'✅' if ok else '❌'} {strumento}: {testo}" for strumento, ok, testo in prove]
    righe.append(f"Operazioni del bot aperte adesso: {aperte}")
    return "\n".join(righe)


def _perche(d: Decisione) -> str:
    s, crt = d.r.scatto, d.r.scatto.crt
    k = d.r.strumento
    short = d.r.verso is Verso.SHORT
    lato = "massimo" if short else "minimo"
    testo = (f"CRT sul{_candela_range(d)} ({prezzo(k, crt.crt_low)}–{prezzo(k, crt.crt_high)}). "
             f"Il prezzo ha preso il {lato} ed è rientrato; alle {quando(s.quando)[6:]} il Model#1 "
             f"sul grafico a {NOMI_TF[d.r.basso_tf]}.")
    if d.r.colpo > 1:
        testo += f" È il colpo n. {d.r.colpo}: il precedente è stato stoppato."
    return testo


def apertura(d: Decisione, volume: float, prezzo_vero: float, rischio: float, valuta: str, singola: bool,
             quota: Optional[float] = None) -> str:
    """Il canale operativo: solo i fatti dell'operazione, sempre nello stesso ordine. Il perche'
    lo discute l'equipe."""
    k, op, r = d.r.strumento, d.op, d.r
    freccia = "📉 VENDITA" if r.verso is Verso.SHORT else "📈 ACQUISTO"
    obiettivi = prezzo(k, op.tp1) if singola else f"{prezzo(k, op.tp1)} (metà) e {prezzo(k, op.tp2)}"
    parte = f" ({quota:.1%} del conto)".replace(".", ",") if quota else ""
    return "\n".join([
        f"{freccia} · {k}",
        f"Ingresso {prezzo(k, prezzo_vero)} · Stop {prezzo(k, op.stop)}",
        f"Obiettivi {obiettivi}",
        f"{_it(volume, 2)} lotti · rischio {_it(rischio)} {valuta}{parte}",
        f"Probabilità di arrivare al primo obiettivo: {d.p1:.0%}",
    ])


def primo_target(k: str, verso: Verso, ingresso: float, a_pareggio: bool = True, livello: Optional[float] = None) -> str:
    testa = f"🎯 {k}: primo obiettivo preso, chiusa metà."
    if a_pareggio:
        return f"{testa} Il resto è a pareggio (stop a {prezzo(k, ingresso)})."
    return f"{testa} Il resto tiene lo stop: va a pareggio quando il prezzo arriva a {prezzo(k, livello)}."


def uscita_anticipata(k: str, verso: Verso, motivo: str) -> str:
    return f"✋ {k}: chiudo prima dello stop, {motivo}."


def pareggio(k: str, verso: Verso, ingresso: float) -> str:
    return f"🛡 {k}: stop spostato a pareggio ({prezzo(k, ingresso)}). Da qui l'operazione non può più perdere."


def chiusa(k: str, verso: Verso, netto: float, r: float, valuta: str, motivo: str) -> str:
    if abs(r) < 0.05:
        return f"➖ {k} chiusa a pareggio ({motivo})"
    segno, come = ("✅", "in guadagno") if netto > 0 else ("❌", "in perdita")
    return f"{segno} {k} chiusa {come}: {euro(netto, valuta)} ({erre(r)}) · {motivo}"


def saltata(d: Decisione, motivo: str) -> str:
    return f"⏭ {d.r.strumento} {direzione(d.r.verso)}: il Capo voleva entrare, ma non apro: {motivo}."


def allarme(testo: str) -> str:
    return f"⚠️ {testo}"


def ora_utc(t: int) -> Optional[str]:
    return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --- canale équipe ---------------------------------------------------------------

def armati(crt: list) -> str:
    """Il Cacciatore annuncia i CRT che si sono armati nell'ultimo giro."""
    righe = ["🔔 Nuovi CRT armati"]
    for c in crt[:15]:
        k = c.strumento
        short = c.verso is Verso.SHORT
        righe.append(
            f"• {k} {direzione(c.verso)} · {NOMI_TF[c.alto_tf]} → {NOMI_TF[c.basso_tf]}: "
            f"{'sopra il massimo' if short else 'sotto il minimo'} {prezzo(k, c.crt_high if short else c.crt_low)} "
            f"alle {quando(c.armato_quando)[6:]}"
        )
    if len(crt) > 15:
        righe.append(f"… e altri {len(crt) - 15}")
    righe.append("Ora aspetto il Model#1. — Cacciatore")
    return "\n".join(righe)


def _bias(b: Bias, verso: Verso) -> str:
    lato = Contesto.dalla_parte(b, verso)
    return "neutro" if lato is None else ("a favore" if lato else "contro")


def _key_level(d: Decisione) -> str:
    kl = d.key_level
    if kl is None:
        return "non so, mancano candele sopra"
    visti = [n for n, v in (("massimo preso", kl.massimo), ("arriva al livello", kl.tocca),
                            ("rejection block", kl.rejection_block), ("FVG", kl.fvg)) if v]
    return ", ".join(visti) if visti else "nessuna zona del timeframe sopra"


def _orario(d: Decisione) -> str:
    ar = d.alla_romeo
    testo = f"{d.orario.ora_scatto:02d}:00 NY"
    if ar is not None and ar.londra:
        return testo + ", ora di Londra di Romeo"
    if ar is not None and ar.new_york:
        return testo + ", ora di New York di Romeo"
    return testo + (", golden candle" if d.orario.gct else ", fuori dalle ore di Romeo")


def _bias_riga(d: Decisione) -> str:
    ctx, ar = d.contesto, d.alla_romeo
    parti = ["non so"] if ctx is None else [f"range {_bias(ctx.range, d.r.verso)}", f"sopra {_bias(ctx.sopra, d.r.verso)}"]
    if ar is not None and ar.sconto is not None:
        compra = d.r.verso is Verso.LONG
        if ar.sconto:
            parti.append("compriamo a sconto" if compra else "vendiamo a premio")
        else:
            parti.append("compriamo caro" if compra else "vendiamo a sconto")
    return ", ".join(parti)


def _romeo_riga(d: Decisione) -> str:
    if d.romeo is None:
        return "non ho ancora imparato niente"
    if not d.romeo_medio:
        return f"gli somiglia al {d.romeo:.1%}".replace(".", ",")
    volte = d.romeo / d.romeo_medio
    giudizio = ("molto più della media" if volte >= 2 else "più della media" if volte >= 1.2
                else "come la media" if volte > 0.8 else "meno della media")
    return f"gli somiglia {giudizio} ({d.romeo:.1%} contro {d.romeo_medio:.1%})".replace(".", ",")


def _pesi(per: dict[str, float]) -> str:
    """Chi ha pesato di piu' sulla decisione, sulla qualita' attesa."""
    forti = sorted(((n, v) for n, v in per.items() if abs(v) >= POCO), key=lambda a: -abs(a[1]))
    if not forti:
        return "Nessuno ha pesato davvero: decide la geometria dell'operazione."
    testo = " · ".join(f"{'👍' if v > 0 else '👎'} {n} {qualita(v)}" for n, v in forti[:4])
    deboli = len(per) - len(forti)
    return f"Chi ha pesato: {testo}" + (f" · gli altri {deboli} quasi niente" if deboli else "")


def _liquidita(d: Decisione) -> str:
    """La terza gamba di Romeo, detta dal Grilletto."""
    liq = d.liquidita
    if liq is None:
        return ""
    if liq.sopra_il_crt:
        estremo = "massimo" if d.r.verso is Verso.SHORT else "minimo"
        return f"; la manipolazione ha ripreso un {estremo} lasciato fuori dal CRT"
    if liq.presa:
        return "; la manipolazione ha preso la liquidità lasciata prima"
    return "; nessuna liquidità presa prima della manipolazione"


_GRANDI_BREVI = ("4 ore", "giorno", "settimana", "mese")


def _in_prova(agente: str) -> str:
    """Un agente nuovo parla, ma finche' la palestra non gli tiene una domanda il Capo non lo ascolta."""
    from nvm.agenti.capo import INVENTATE
    return "" if any(x.agente == agente for x in INVENTATE) else " (sto imparando: il Capo non mi ascolta ancora)"


def _allineamento(d: Decisione) -> str:
    sg = d.sguardo
    if sg is None:
        return "non so"
    gruppi = {True: [], False: [], None: []}
    for nome, lato in zip(_GRANDI_BREVI, sg.lati):
        gruppi[lato].append(nome)
    parti = [f"{titolo} {', '.join(gruppi[k])}" for k, titolo in ((True, "a favore:"), (False, "contro:"), (None, "neutri:"))
             if gruppi[k]]
    testo = " · ".join(parti)
    if sg.livelli:
        testo += f"; CRT più grandi armati nello stesso verso su {sg.livelli} livell{'o' if sg.livelli == 1 else 'i'}"
    return testo + _in_prova("Allineamento")


def _gap(d: Decisione) -> str:
    sg = d.sguardo
    if sg is None:
        return "non so"
    k = d.r.strumento
    parti = []
    if sg.fvg is not None:
        tf, basso, alto = sg.fvg
        dove = "delle 4 ore" if tf is TF.H4 else "del giorno"
        parti.append(f"FVG {dove} aperto verso l'obiettivo a {prezzo(k, basso)}–{prezzo(k, alto)}")
    else:
        parti.append("nessun FVG aperto verso l'obiettivo")
    if sg.weekend is not None:
        venerdi, a_favore = sg.weekend
        parti.append(f"gap del weekend aperto (venerdì a {prezzo(k, venerdi)}), chiuderlo è "
                     + ("a favore" if a_favore else "contro"))
    return "; ".join(parti) + _in_prova("Gap")


def pareri(d: Decisione, per: Optional[dict[str, float]] = None) -> str:
    """La scheda di una decisione per il canale équipe: cosa dice ognuno, cosa decide il Capo."""
    k, op, r = d.r.strumento, d.op, d.r
    crt = r.scatto.crt
    grande = ", dentro un CRT più grande" if d.alla_romeo is not None and d.alla_romeo.annidato else ""
    righe = [
        f"🧠 {k} · {direzione(r.verso)} · {coppia(d)} · {quando(r.quando)}",
        f"Cacciatore — CRT {prezzo(k, crt.crt_low)}–{prezzo(k, crt.crt_high)}{grande}",
        f"Grilletto — Model#1 a {prezzo(k, r.scatto.livello)}" + (f", colpo n. {r.colpo}" if r.colpo > 1 else "")
        + _liquidita(d),
        f"Livelli — stop {prezzo(k, op.stop)} · obiettivi {prezzo(k, op.tp1)} e {prezzo(k, op.tp2)} "
        f"({_it(r.rr1, 1)} R e {_it(r.rr2, 1)} R)",
        f"Key level — {_key_level(d)}",
        f"Orario — {_orario(d)}",
        f"Bias — {_bias_riga(d)}",
        f"Allineamento — {_allineamento(d)}",
        f"Gap — {_gap(d)}",
        f"Romeo — {_romeo_riga(d)}",
        "",
        f"Capo: {d.p1:.0%} di arrivare al primo obiettivo, {_capo(d)} → "
        + ("ENTRO" if d.entra else "NON ENTRO"),
    ]
    if per:
        righe.append(_pesi(per))
    return "\n".join(righe)


# --- Romeo dal vivo (`nvm/vivo/romeo_vivo.py`) ---

def romeo_ricevuta(e, s) -> str:
    """La risposta a un /romeo: com'era la sua entrata e cosa aveva visto il bot."""
    k, verso = e.strumento, Verso(e.verso)
    testa = f"📥 Romeo · {k} · {direzione(verso)} a {prezzo(k, e.ingresso)}"
    if e.stop is not None:
        testa += f" · stop {prezzo(k, e.stop)} ({_it(e.rischio / PIP_ROMEO[k], 1)} pip)"
    if e.target is not None:
        testa += f" · target {prezzo(k, e.target)}"
    righe = [testa]
    if s is None:
        righe.append(f"Non l'avevo vista: nessuna mia decisione su {k} in {direzione(verso)} nelle ultime 24 ore.")
    else:
        quanto = (f"a {_it(e.distanza)} del suo rischio ({_it(e.pip, 1)} pip)" if e.distanza is not None
                  else f"a {_it(e.pip, 1)} pip")
        giudizio = " ✅ ritrovata" if e.ritrovata else (" — troppo lontana" if e.distanza is not None else "")
        righe.append(f"La mia più vicina: {s.leggibile or s.chiave}, ingresso {prezzo(k, s.ingresso)}, {quanto}.{giudizio}")
        righe.append("L'avevo presa." if s.entrata else
                     f"Non l'avevo presa: qualità attesa {qualita(s.qualita)}." if s.qualita is not None else
                     f"Non l'avevo presa: guadagno atteso {erre(s.atteso)}.")
    righe.append("Sabato imparo da questa. Non la copio: Romeo è il mio metro, non un ordine.")
    return "\n".join(righe)


def romeo_non_letta(motivo: str) -> str:
    return f"📥 Romeo: non ho capito il messaggio, {motivo}."

