"""Le parole del bot: cosa scrive sui due canali, in italiano semplice.

Stile (riscritti il 30/09/2026 su richiesta del proprietario): frasi brevi, una
cosa per riga, parole di tutti i giorni, "compro/vendo", i soldi in euro invece
delle sigle, i prezzi come li mostra MT5, le altre cifre all'italiana.
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
NOMI_TF = {TF.MN: "mensile", TF.W1: "settimanale", TF.D1: "giornaliero", TF.H12: "12 ore", TF.H6: "6 ore", TF.H4: "4 ore", TF.H1: "1 ora",
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
    if getattr(d, "foto", None):
        return f"CRT {NOMI_TF.get(d.r.alto_tf, d.r.alto_tf.value)}"
    return f"{NOMI_TF.get(d.r.alto_tf, d.r.alto_tf.value)} → {NOMI_TF.get(d.r.basso_tf, d.r.basso_tf.value)}"


def leggibile(d: Decisione) -> str:
    """Come si chiama una decisione nei messaggi dopo: "EURUSD vendita · giornaliero → 1 ora · 09/09 03:00 NY · CRT 1.0850–1.0900"."""
    k = d.r.strumento
    crt = d.r.scatto.crt if d.r.scatto is not None else None
    fascia = f" · CRT {prezzo(k, crt.crt_low)}–{prezzo(k, crt.crt_high)}" if crt is not None else ""
    return f"{k} {direzione(d.r.verso)} · {coppia(d)} · {quando(d.r.quando)}{fascia}"


def _candela_range(d: Decisione) -> str:
    t = datetime.fromtimestamp(d.r.scatto.crt.range_inizio + 6 * 3600, tz=timezone.utc).astimezone(NEW_YORK)
    if d.r.alto_tf is TF.MN:
        return f"la candela mensile di {MESI[t.month - 1]} {t.year}"
    if d.r.alto_tf is TF.W1:
        return f"la candela settimanale del {t:%d/%m}"
    if d.r.alto_tf is TF.H4:
        return f"la candela a 4 ore del {t:%d/%m %H:%M}"
    return f"la candela giornaliera del {t:%d/%m}"


# --- canale operativo -----------------------------------------------------------
# Riscritti il 30/09/2026 (il proprietario: *"così non capisco niente"*): parole di tutti i giorni,
# i soldi in euro invece delle sigle, una cosa per riga.

_MOTIVI = {"stop": "è arrivata allo stop", "target": "ha raggiunto l'obiettivo",
           "pareggio": "è tornata al prezzo d'entrata",
           "primo target e poi secondo target": "ha raggiunto tutti e due gli obiettivi",
           "primo target e poi pareggio": "metà chiusa al primo obiettivo, il resto è tornato al prezzo d'entrata"}


def avvio(login: int, server: str, saldo: float, valuta: str, strumenti: list[str], scarto: int) -> str:
    return "\n".join([
        "🟢 Il bot è acceso",
        f"Conto demo {login} ({server})",
        f"Saldo: {_it(saldo)} {valuta}",
        f"Guardo {len(strumenti)} mercati.",
        "Qui vedi solo cosa succede sul conto. Perché compriamo o vendiamo lo racconta la squadra nell'altro canale.",
    ])


def mancanti(strumenti: list[str], guardati: int) -> str:
    return f"ℹ️ Il broker non ha questi mercati: {', '.join(strumenti)}. Li salto: lavoro su {guardati} mercati."


def aggiornato(titolo: str) -> str:
    return f"🔄 Mi sono aggiornato e sono ripartito.\nNovità: {titolo}"


def collegamento(prove: list[tuple[str, bool, str]], aperte: int) -> str:
    """La prova del collegamento con MT5: nessun ordine mandato, solo il controllo del broker."""
    righe = ["🔌 Controllo il collegamento con MT5 (senza aprire niente)"]
    if all(ok for _, ok, _ in prove):
        righe.append(f"✅ Posso operare su tutti i {len(prove)} mercati")
    else:
        righe += [f"{'✅' if ok else '❌'} {strumento}: {testo}" for strumento, ok, testo in prove]
    righe.append(f"Operazioni aperte adesso: {aperte}")
    return "\n".join(righe)


def simboli_del_broker(simboli: list, usati: dict) -> list[str]:
    """La lista di tutti gli strumenti del broker, per cartella di MT5, coi nomi che il bot usa segnati ✅.
    `usati`: nome sul broker -> nome nel bot. In piu' messaggi se e' lunga."""
    cartelle: dict = {}
    for nome, cartella, descrizione in simboli:
        gruppo = cartella.replace("/", "\\").split("\\")[0] if cartella else "Altro"
        cartelle.setdefault(gruppo or "Altro", []).append((nome, descrizione))
    righe = [f"📋 Gli strumenti del broker: {len(simboli)} in tutto. ✅ = il bot li guarda ({len(usati)})."]
    for gruppo in sorted(cartelle, key=str.lower):
        voci = cartelle[gruppo]
        righe.append(f"\n{gruppo} ({len(voci)}):")
        riga = ""
        for n, _ in voci:
            nome = ("✅ " if n in usati else "") + n
            if riga and len(riga) + len(nome) + 2 > 3000:
                righe.append(riga)
                riga = ""
            riga = f"{riga}, {nome}" if riga else nome
        if riga:
            righe.append(riga)
    testi, pezzo = [], ""
    for r in righe:
        if len(pezzo) + len(r) + 1 > 3800:
            testi.append(pezzo)
            pezzo = ""
        pezzo += r + "\n"
    if pezzo:
        testi.append(pezzo)
    return testi


def apertura(d: Decisione, volume: float, prezzo_vero: float, rischio: float, valuta: str, uscita,
             quota: Optional[float] = None) -> str:
    """Il canale operativo: cosa ho fatto sul conto, quanto posso perdere e quanto posso guadagnare.
    `uscita`: "due meta'", "primo target" o "secondo target" (`nvm/agenti/rischio.USCITE`)."""
    k, op, r = d.r.strumento, d.op, d.r
    vende = r.verso is Verso.SHORT
    distanza = abs(prezzo_vero - op.stop) or 1e-12
    def guadagno(target: float, parte: float) -> str:
        return euro(rischio * parte * abs(target - prezzo_vero) / distanza, valuta)
    parte = f" ({_it(100 * quota)}% del conto)" if quota else ""
    righe = [f"{'🔴 HO VENDUTO' if vende else '🟢 HO COMPRATO'} {k}",
             f"Prezzo d'entrata: {prezzo(k, prezzo_vero)}",
             f"🛑 Stop: {prezzo(k, op.stop)} → se va male perdo {_it(rischio)} {valuta}{parte}"]
    if uscita == "primo target" or uscita is True:
        righe.append(f"🎯 Obiettivo: {prezzo(k, op.tp1)} → circa {guadagno(op.tp1, 1.0)}")
    elif uscita == "secondo target":
        righe.append(f"🎯 Obiettivo: {prezzo(k, op.tp2)} → circa {guadagno(op.tp2, 1.0)}")
        righe.append(f"🛡 A {prezzo(k, op.tp1)} sposto lo stop al prezzo d'entrata: da lì non può più perdere")
    elif getattr(d, "foto", None):
        ob = d.foto.get("obiettivo")
        righe.append(f"🎯 TP1 (l'altro lato del range): {prezzo(k, op.tp1)} → chiudo metà, circa {guadagno(op.tp1, 0.5)}, "
                     "e metto lo stop al prezzo d'entrata")
        righe.append(f"🎯 Target finale ({ob.nome if ob is not None else 'il resto'}): {prezzo(k, op.tp2)} → l'altra metà, "
                     f"circa {guadagno(op.tp2, 0.5)}")
    else:
        righe.append(f"🎯 Obiettivo 1: {prezzo(k, op.tp1)} → chiudo metà, circa {guadagno(op.tp1, 0.5)}")
        righe.append(f"🎯 Obiettivo 2: {prezzo(k, op.tp2)} → l'altra metà, circa {guadagno(op.tp2, 0.5)}")
    righe.append(f"Quantità: {_it(volume, 2)} lotti")
    return "\n".join(righe)


def primo_target(k: str, verso: Verso, ingresso: float, a_pareggio: bool = True, livello: Optional[float] = None) -> str:
    testa = f"🎯 {k}: primo obiettivo raggiunto, ho chiuso metà in guadagno."
    if a_pareggio:
        return f"{testa}\nSul resto lo stop ora è al prezzo d'entrata ({prezzo(k, ingresso)}): da qui non può più perdere."
    return f"{testa}\nSul resto lo stop andrà al prezzo d'entrata quando il prezzo arriva a {prezzo(k, livello)}."


def uscita_anticipata(k: str, verso: Verso, motivo: str) -> str:
    return f"✋ {k}: chiudo prima dello stop, {motivo}."


def pareggio(k: str, verso: Verso, ingresso: float) -> str:
    return f"🛡 {k}: ho spostato lo stop al prezzo d'entrata ({prezzo(k, ingresso)}). Da qui non può più perdere."


def chiusa(k: str, verso: Verso, netto: float, r: float, valuta: str, motivo: str) -> str:
    come = _MOTIVI.get(motivo, motivo)
    if abs(r) < 0.05:
        return f"➖ {k} chiusa in pari: {euro(netto, valuta)}\n{_cap(come)}."
    segno, esito = ("✅", "in guadagno") if netto > 0 else ("❌", "in perdita")
    return f"{segno} {k} chiusa {esito}: {euro(netto, valuta)}\n{_cap(come)}."


def saltata(d: Decisione, motivo: str) -> str:
    return f"⏭ {d.r.strumento}: la squadra voleva {'vendere' if d.r.verso is Verso.SHORT else 'comprare'}, ma non ho aperto: {motivo}."


def allarme(testo: str) -> str:
    return f"⚠️ {testo}"


def _cap(testo: str) -> str:
    return testo[:1].upper() + testo[1:] if testo else testo


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
        righe.append("L'avevo presa anch'io." if s.entrata else "Io non l'avevo presa.")
    righe.append("Non la copio: Romeo è il mio metro, non un ordine.")
    return "\n".join(righe)


def romeo_non_letta(motivo: str) -> str:
    return f"📥 Romeo: non ho capito il messaggio, {motivo}."

