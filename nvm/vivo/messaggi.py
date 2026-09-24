"""Le parole del bot: cosa scrive sui due canali, in italiano semplice."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from nvm.agenti.cacciatore import Verso
from nvm.agenti.conferme import Bias, Contesto
from nvm.tempo import NEW_YORK, TF
from nvm.vivo.giro import Decisione

CIFRE = {"EURUSD": 5, "GBPUSD": 5, "AUDUSD": 5, "USDCHF": 5, "USDJPY": 3, "XAUUSD": 2}
NOMI_TF = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H4: "4 ore", TF.H1: "1 ora", TF.M15: "15 minuti"}
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")


def prezzo(strumento: str, x: float) -> str:
    return f"{x:.{CIFRE.get(strumento, 5)}f}"


def quando(t: int) -> str:
    """Un istante in ora di New York, come lo legge un trader: '09/09 03:00 NY'."""
    return datetime.fromtimestamp(int(t), tz=timezone.utc).astimezone(NEW_YORK).strftime("%d/%m %H:%M NY")


def erre(x: float) -> str:
    return f"{x:+.2f} R".replace(".", ",")


def _candela_range(d: Decisione) -> str:
    t = datetime.fromtimestamp(d.r.scatto.crt.range_inizio + 7 * 3600, tz=timezone.utc).astimezone(NEW_YORK)
    if d.r.alto_tf is TF.MN:
        return f"la candela mensile di {MESI[t.month - 1]} {t.year}"
    if d.r.alto_tf is TF.W1:
        return f"la candela settimanale che parte il {t:%d/%m}"
    return f"la candela giornaliera del {t:%d/%m}"


def coppia(d: Decisione) -> str:
    return f"{NOMI_TF[d.r.alto_tf]} → {NOMI_TF[d.r.basso_tf]}"


def _perche(d: Decisione) -> str:
    s, crt = d.r.scatto, d.r.scatto.crt
    k = d.r.strumento
    short = d.r.verso is Verso.SHORT
    estremo = crt.estremo_a(s.quando)
    righe = [
        f"Il range è {_candela_range(d)}: da {prezzo(k, crt.crt_low)} a {prezzo(k, crt.crt_high)}.",
        f"Dal {quando(crt.manipolazione_inizio)} il prezzo è {'salito sopra il massimo' if short else 'sceso sotto il minimo'}"
        + (f", fino a {prezzo(k, estremo)}" if estremo is not None else "") + ", e ci è rientrato.",
        f"Alle {quando(s.quando)[6:]} una candela da {NOMI_TF[d.r.basso_tf]} ha chiuso {'sotto' if short else 'sopra'} "
        f"{prezzo(k, s.livello)}, l'apertura del turtle soup: è il Model#1 di Romeo.",
    ]
    if d.r.colpo > 1:
        righe.append(f"È il colpo n. {d.r.colpo} su questo CRT: il precedente è stato stoppato.")
    return "\n".join(righe)


def _bias(b: Bias, verso: Verso) -> str:
    lato = Contesto.dalla_parte(b, verso)
    return "neutro" if lato is None else ("a favore" if lato else "contro")


def pareri(d: Decisione) -> str:
    """Quello che ogni agente dice di questa decisione: il canale equipe."""
    k, op, r = d.r.strumento, d.op, d.r
    kl = d.key_level
    if kl is None:
        testo_kl = "non so, mancano candele sopra"
    else:
        visti = [n for n, v in (("massimo preso", kl.massimo), ("arriva al massimo", kl.tocca),
                                ("rejection block", kl.rejection_block), ("FVG", kl.fvg)) if v]
        testo_kl = ", ".join(visti) if visti else "nessuna zona del timeframe sopra"
    ctx = d.contesto
    testo_bias = "non so" if ctx is None else (
        f"la candela del range è {_bias(ctx.range, r.verso)}, il timeframe sopra è {_bias(ctx.sopra, r.verso)}")
    return "\n".join([
        f"🗂 {k} {r.verso.value.upper()}, {coppia(d)} — {quando(r.quando)}",
        f"• Cacciatore: CRT {r.verso.value} armato dal {quando(r.scatto.crt.armato_quando)}, "
        f"range {prezzo(k, r.scatto.crt.crt_low)}–{prezzo(k, r.scatto.crt.crt_high)}.",
        f"• Grilletto: Model#1, livello {prezzo(k, r.scatto.livello)}" + (f", colpo {r.colpo}." if r.colpo > 1 else "."),
        f"• Livelli: ingresso {prezzo(k, op.ingresso)}, stop {prezzo(k, op.stop)}, "
        f"target {prezzo(k, op.tp1)} e {prezzo(k, op.tp2)} (RR {r.rr1:.1f} e {r.rr2:.1f}).".replace(".0 ", " "),
        f"• Key level: {testo_kl}.",
        f"• Orario: scatto alle {d.orario.ora_scatto}:00 NY, "
        + ("dentro la golden candle (9–13)." if d.orario.gct else "fuori dalla golden candle (9–13)."),
        f"• Bias: {testo_bias}" + _sconto(d) + ".",
        _romeo(d),
        f"• Capo: primo target {d.p1:.0%}, secondo {d.q:.0%} → guadagno atteso {erre(d.atteso)}. "
        + ("Entro." if d.entra else "Non entro."),
    ])


def _sconto(d: Decisione) -> str:
    ar = d.alla_romeo
    if ar is None or ar.sconto is None:
        return ""
    compra = d.r.verso.value == "long"
    if ar.sconto:
        return "; " + ("compriamo a sconto" if compra else "vendiamo a premio") + " sulla settimana"
    return "; " + ("compriamo caro" if compra else "vendiamo a sconto") + " sulla settimana"


def _romeo(d: Decisione) -> str:
    ar = d.alla_romeo
    if ar is None:
        return "• Alla Romeo: non so."
    ora = "ora di Londra di Romeo" if ar.londra else ("ora di New York di Romeo" if ar.new_york else "fuori dalle ore di Romeo")
    grande = "dentro un CRT più grande" if ar.annidato else "nessun CRT più grande nello stesso verso"
    simile = "" if d.romeo is None else f"; somiglia alle sue entrate al {d.romeo:.0%}"
    return f"• Alla Romeo: {ora}, {grande}{simile}."


def apertura(d: Decisione, volume: float, prezzo_vero: float, rischio: float, valuta: str, singola: bool) -> str:
    k, op, r = d.r.strumento, d.op, d.r
    freccia = "📉" if r.verso is Verso.SHORT else "📈"
    righe = [
        f"{freccia} APRO {r.verso.value.upper()} {k} ({coppia(d)})",
        f"Ingresso {prezzo(k, prezzo_vero)} · stop {prezzo(k, op.stop)} · "
        + (f"target {prezzo(k, op.tp1)}" if singola else f"target {prezzo(k, op.tp1)} (metà) e {prezzo(k, op.tp2)}"),
        f"Volume {volume:g} lotti, rischio {rischio:.2f} {valuta}".replace(".", ","),
        "",
        "Perché:",
        _perche(d),
        f"Il Capo stima {d.p1:.0%} di arrivare al primo target: guadagno atteso {erre(d.atteso)}.",
    ]
    return "\n".join(righe)


def primo_target(k: str, verso: Verso, ingresso: float) -> str:
    return f"🎯 {k} {verso.value.upper()}: primo target preso, metà chiusa. Stop del resto a pareggio ({prezzo(k, ingresso)})."


def chiusa(k: str, verso: Verso, netto: float, r: float, valuta: str, motivo: str) -> str:
    segno = "✅" if netto > 0 else ("➖" if abs(r) < 0.05 else "❌")
    return f"{segno} Chiusa {k} {verso.value.upper()}: {motivo}, {erre(r)} ({netto:+.2f} {valuta})".replace(".", ",", 1)


def avvio(login: int, server: str, saldo: float, valuta: str, strumenti: list[str], scarto: int) -> str:
    return "\n".join([
        "🟢 Bot avviato.",
        f"Conto demo {login} su {server}, saldo {saldo:,.2f} {valuta}.".replace(",", " "),
        f"Strumenti: {', '.join(strumenti)}. Coppie: mensile → giornaliero, settimanale → 4 ore, giornaliero → 1 ora.",
        "Apre le entrate che il Capo approva, con la puntata che sceglie il Rischio. Tutte le decisioni le racconta l'équipe.",
        f"(Ora del server del broker: UTC{scarto:+d}.)",
    ])


def collegamento(prove: list[tuple[str, bool, str]], aperte: int) -> str:
    """La prova del collegamento con MT5 all'avvio: nessun ordine mandato, solo il controllo del broker."""
    righe = ["🔌 Prova del collegamento con MT5 (nessun ordine mandato: chiedo solo al broker se lo accetterebbe)."]
    righe += [f"{'✅' if ok else '❌'} {strumento}: {testo}." for strumento, ok, testo in prove]
    if all(ok for _, ok, _ in prove):
        righe.append("Il collegamento per aprire funziona su tutti gli strumenti.")
    righe.append(f"Operazioni del bot aperte adesso su MT5: {aperte}.")
    return "\n".join(righe)


def saltata(d: Decisione, motivo: str) -> str:
    return f"⏭ {d.r.strumento} {d.r.verso.value.upper()} ({coppia(d)}): il Capo entrerebbe, ma non apro: {motivo}."


def allarme(testo: str) -> str:
    return f"⚠️ {testo}"


def ora_utc(t: int) -> Optional[str]:
    return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def armati(crt: list) -> str:
    """Il Cacciatore annuncia i CRT che si sono armati nell'ultimo giro."""
    righe = ["🔔 Cacciatore: CRT armati adesso."]
    for c in crt[:20]:
        k = c.strumento
        short = c.verso is Verso.SHORT
        righe.append(
            f"  {k} {c.verso.value.upper()}, {NOMI_TF[c.alto_tf]} → {NOMI_TF[c.basso_tf]}: alle {quando(c.armato_quando)[6:]} il prezzo è "
            f"{'salito sopra il massimo' if short else 'sceso sotto il minimo'} del range "
            f"({prezzo(k, c.crt_high if short else c.crt_low)})."
        )
    if len(crt) > 20:
        righe.append(f"  … e altri {len(crt) - 20}.")
    righe.append("Grilletto: aspetto il Model#1 su questi. — Cacciatore e Grilletto")
    return "\n".join(righe)
