"""Ogni operazione, riverificata contro l'archivio. Non contro il codice.

## Perche' esiste

Troppe volte la domanda "il bot segue la strategia?" ha avuto come risposta un
audit del codice contro se stesso: si guardava cosa il codice fa, si trovava
che lo fa coerentemente, e si dichiarava tutto a posto. Poi il bot perdeva, e
il problema lo trovava l'utente guardando il grafico.

Questo script fa l'opposto. Prende le operazioni **realmente aperte**, torna
sull'archivio al momento esatto dell'ingresso, e si chiede:

1. c'era davvero un CRT, li', in quel momento?
2. era nel verso in cui il bot e' entrato?
3. lo stop stava dove lo metterebbe il CRT trovato, o altrove?
4. quanto tempo e' passato fra la formazione del CRT e l'ingresso?
5. com'e' finita, e quanto ha reso in R?

Le risposte finiscono in `diario/operazioni.md`, che si riempie di esempi
concreti. E' quel file — non le opinioni di nessuno — la base da cui decidere
cosa correggere.

## Cosa NON fa

Non guarda il futuro. La verifica usa solo candele chiuse **prima**
dell'ingresso, esattamente come le vedeva il motore: se guardasse la barra
successiva troverebbe CRT perfetti ovunque e non servirebbe a niente.

Non tocca il bot, non scrive in archivio, non manda ordini. Si puo' lanciare
mentre il bot gira.

## Uso

    python diario_operazioni.py                # tutte le operazioni
    python diario_operazioni.py --giorni 3     # solo le ultime 72 ore
    python diario_operazioni.py --limite 50    # le 50 piu' recenti

Il file ha in cima una sezione scritta a mano, fra i marcatori, che lo script
non tocca mai: e' li' che si annotano le correzioni fatte, cosi' il diario
diventa la storia del lavoro e non solo una fotografia dell'ultimo minuto.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core import setup as stp
from core import simboli as sim
from core import stato
from core.config import impostazioni
from core.definizioni import Bias
from core.fornitore_tradingview import FornitoreTradingView
from core.motore import candele_visibili
from core.parametri import COPPIE_CRT, UNIVERSO, TF

INIZIO = "<!-- QUI SOPRA SCRIVO IO, LO SCRIPT NON TOCCA NULLA -->"
FINE = "<!-- DA QUI IN GIU' RIGENERA LO SCRIPT: NON SCRIVERE A MANO -->"

TESTA_A_MANO = f"""# Diario delle operazioni

Ogni operazione aperta dal bot, riverificata contro l'archivio: il CRT c'era
davvero? Nel verso giusto? Lo stop stava dove il CRT lo vuole? Com'e' finita?

## Correzioni fatte

_(questa sezione la scrivo a mano man mano che si corregge qualcosa, con la
data e il caso concreto che l'ha fatta scoprire)_

{INIZIO}

{FINE}
"""


# ===========================================================================
# Leggere le operazioni
# ===========================================================================


@dataclass
class Operazione:
    id: int
    ticket: Optional[int]
    simbolo: str
    direzione: str
    volume: float
    ingresso: float
    # Lo stop dell'INGRESSO, preso dalla decisione. Confondere questo con
    # quello di adesso fa sembrare sbagliata ogni posizione andata a pareggio.
    stop: Optional[float]
    stop_adesso: Optional[float]
    target: Optional[float]
    tp1: Optional[float]
    tp1_raggiunto: bool
    aperta: datetime
    chiusa: Optional[datetime]
    uscita: Optional[float]
    motivo: Optional[str]
    tf_crt: Optional[str]

    @property
    def esito(self) -> str:
        if self.chiusa is None:
            return "aperta"
        m = (self.motivo or "").lower()
        if "tp" in m:
            return "target"
        if "sl" in m:
            # Stop a pareggio o stop vero? Lo dice il prezzo di uscita.
            if self.tp1_raggiunto:
                return "pareggio"
            return "stop"
        if "fuori" in m:
            return "chiusa fuori"
        return m or "ignoto"

    @property
    def erre(self) -> Optional[float]:
        """Quanto ha reso, in multipli del rischio iniziale."""
        if self.uscita is None or self.stop is None:
            return None
        rischio = abs(self.ingresso - self.stop)
        if rischio <= 0:
            return None
        guadagno = (self.uscita - self.ingresso if self.direzione == "BUY"
                    else self.ingresso - self.uscita)
        return guadagno / rischio

    @property
    def durata(self) -> Optional[timedelta]:
        if self.chiusa is None:
            return None
        return self.chiusa - self.aperta


def _quando(testo: Optional[str]) -> Optional[datetime]:
    if not testo:
        return None
    try:
        q = datetime.fromisoformat(str(testo).replace("Z", "+00:00"))
    except ValueError:
        return None
    return q.replace(tzinfo=timezone.utc) if q.tzinfo is None else q


def operazioni(giorni: Optional[int], limite: Optional[int]) -> list[Operazione]:
    conn = sqlite3.connect(impostazioni().DB_PATH)
    conn.row_factory = sqlite3.Row
    dove, parametri = "", []
    if giorni:
        soglia = datetime.now(timezone.utc) - timedelta(days=giorni)
        dove = "WHERE aperta_utc >= ?"
        parametri = [soglia.strftime("%Y-%m-%dT%H:%M:%S")]
    # Lo stop si legge dalla DECISIONE, non dalla posizione.
    #
    # `posizione.sl` viene RISCRITTO dalla sentinella quando porta a pareggio
    # dopo TP1: su uno short il pareggio sta sotto l'ingresso, quindi una
    # posizione sana e gestita bene sembra avere "lo stop dalla parte
    # sbagliata". E' successo il 2026-09-23 sul ticket 330022075 -- stop
    # deciso 4294,91 sopra l'ingresso 4293,00, poi TP1 preso e pareggio a
    # 4292,76 -- e l'ho segnalato come difetto quando era il contrario.
    sql = f"""
        SELECT p.*, d.sl AS sl_deciso, d.tp AS tp_deciso
        FROM posizione p LEFT JOIN decisione d ON d.id = p.decisione_id
        {dove.replace('aperta_utc', 'p.aperta_utc')}
        ORDER BY p.aperta_utc DESC
    """
    if limite:
        sql += f" LIMIT {int(limite)}"
    righe = conn.execute(sql, parametri).fetchall()
    conn.close()

    fuori = []
    for r in righe:
        aperta = _quando(r["aperta_utc"])
        if aperta is None:
            continue
        fuori.append(Operazione(
            id=r["id"], ticket=r["ticket"], simbolo=str(r["simbolo"]),
            direzione=str(r["direzione"]).upper(), volume=float(r["volume"] or 0),
            ingresso=float(r["prezzo_ingresso"] or 0),
            # `sl_deciso` quando c'e': e' lo stop con cui l'operazione e'
            # NATA. `p.sl` e' quello di adesso, che dopo TP1 e' il pareggio.
            stop=(r["sl_deciso"] if r["sl_deciso"] is not None else r["sl"]),
            stop_adesso=r["sl"],
            target=r["tp"], tp1=r["tp1"],
            tp1_raggiunto=bool(r["tp1_raggiunto"]),
            aperta=aperta, chiusa=_quando(r["chiusa_utc"]),
            uscita=r["prezzo_uscita"], motivo=r["motivo_chiusura"],
            tf_crt=r["tf_crt"],
        ))
    return list(reversed(fuori))


# ===========================================================================
# Riverificare il CRT: c'era, li', in quel momento?
# ===========================================================================


@dataclass
class Verifica:
    trovato: bool
    verso_giusto: Optional[bool] = None
    tf_range: Optional[str] = None
    tf_esecuzione: Optional[str] = None
    livello_range: Optional[float] = None
    estremo: Optional[float] = None
    rientro_a: Optional[datetime] = None
    barre_di_attesa: Optional[int] = None
    stop_coerente: Optional[bool] = None
    scarto_stop_in_r: Optional[float] = None
    nota: str = ""


def _strumento_di(simbolo_broker: str) -> Optional[str]:
    return sim.cfd_da_simbolo_esecuzione(
        simbolo_broker, impostazioni().MT5_SUFFISSO_SIMBOLI)


def verifica_crt(op: Operazione, fornitore: FornitoreTradingView) -> Verifica:
    """Il CRT c'era davvero, al momento dell'ingresso?

    Si rifa' esattamente il percorso del motore: candela di riferimento
    sull'ultimo timeframe alto chiuso, barre di esecuzione dopo di essa, e
    `cerca_crt` sulle stesse. Nessuna barra successiva all'ingresso entra nel
    calcolo — se entrasse, ogni CRT sembrerebbe perfetto.
    """
    strumento = _strumento_di(op.simbolo)
    if strumento is None or strumento not in UNIVERSO:
        return Verifica(False, nota=f"simbolo {op.simbolo} non riconducibile all'universo")

    # Si passa dal future e si lascia decidere a `nome_in_archivio` sotto quale
    # nome cercare: con MT5 le candele intraday stanno sotto il nome del CFD
    # (EURUSD) mentre l'archivio del future (6E) ha solo daily/settimanale/H1.
    # Chiedere direttamente "6E" non da' errore, da' un archivio senza barre di
    # esecuzione — cioe' "nessun CRT" su tutto, che sembra un verdetto e non lo e'.
    future = UNIVERSO[strumento].future
    try:
        storico = fornitore.storico(future)
    except Exception as errore:                      # pragma: no cover
        return Verifica(False, nota=f"archivio illeggibile: {errore!r}")

    # Quale coppia? `tf_crt` in archivio e' il timeframe del RANGE sul ramo
    # diretto e quello di ESECUZIONE sul ramo armato -- incoerenza nota, vedi
    # il riepilogo. Si provano quindi tutte le coppie e si tiene quella che
    # spiega davvero l'ingresso.
    try:
        presi = stato.key_level_presi(storico, op.aperta)
    except Exception as errore:                      # pragma: no cover
        return Verifica(False, nota=f"key level non calcolabili: {errore!r}")
    if not presi:
        return Verifica(False, nota="SETUP-00: nessun key level preso in quel momento")

    migliore: Optional[Verifica] = None
    for tf_range, tf_ese in COPPIE_CRT.items():
        alte = candele_visibili(storico.get(tf_range, ()), op.aperta)
        basse = candele_visibili(storico.get(tf_ese, ()), op.aperta)
        if len(alte) < 2 or not basse:
            continue
        c_rif = alte[-1]
        barre = [c for c in basse if c.orario > c_rif.orario]
        if not barre:
            continue
        # SETUP-00: senza key level presi `cerca_crt` non cerca nemmeno, e
        # restituirebbe None su tutto. Passare una lista vuota qui produceva
        # "nessun CRT" su ogni operazione: un verdetto dello script, non del
        # bot. Si calcolano come li calcola il motore.
        crt = stp.cerca_crt(c_rif, barre, tf_range, presi)
        if crt is None:
            continue

        corta = crt.direzione is Bias.SHORT
        # Il verso sul CFD puo' essere l'opposto di quello sul future (6J, 6S).
        atteso = "SELL" if corta else "BUY"
        verso_giusto = (atteso == op.direzione) or (
            strumento in ("USDCHF", "USDJPY") and atteso != op.direzione)

        livello = c_rif.massimo if corta else c_rif.minimo
        estremo = crt.n2.massimo if corta else crt.n2.minimo
        attesa = sum(1 for b in barre if b.orario <= crt.n2.orario)

        v = Verifica(
            trovato=True, verso_giusto=verso_giusto,
            tf_range=tf_range.value, tf_esecuzione=tf_ese.value,
            livello_range=livello, estremo=estremo,
            rientro_a=crt.n2.orario, barre_di_attesa=attesa,
        )

        # Lo stop del CRT sta appena oltre l'estremo della manipolazione. Se
        # quello messo dal bot e' altrove, l'ingresso non nasce da QUESTO CRT.
        # Se lo stop d'ingresso non e' leggibile dalla decisione si resta
        # zitti invece di giudicare su `posizione.sl`, che dopo TP1 e' il
        # pareggio: giudicarlo li' significa chiamare "difetto" una posizione
        # gestita bene. Vedi la nota in `operazioni()`.
        if op.stop is not None and op.stop != op.stop_adesso and op.tp1_raggiunto:
            v.nota = ("stop d'ingresso letto dalla decisione; quello attuale e' "
                      "il pareggio")
        if op.stop is not None and estremo:
            rischio = abs(op.ingresso - op.stop) or 1e-9
            v.scarto_stop_in_r = abs(op.stop - estremo) / rischio
            v.stop_coerente = v.scarto_stop_in_r < 0.25

        if migliore is None or (v.stop_coerente and not migliore.stop_coerente):
            migliore = v
        if v.stop_coerente:
            break

    if migliore is None:
        return Verifica(False, nota="nessun CRT su nessuna coppia, al momento dell'ingresso")
    return migliore


# ===========================================================================
# Scrivere
# ===========================================================================


def _r(valore: Optional[float], cifre: int = 2) -> str:
    return "—" if valore is None else f"{valore:.{cifre}f}"


def _durata(d: Optional[timedelta]) -> str:
    if d is None:
        return "aperta"
    s = int(d.total_seconds())
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}"


ESITO_SEGNO = {"target": "✅", "stop": "❌", "pareggio": "➖",
               "chiusa fuori": "⚪", "aperta": "🔵"}


def riga_tabella(op: Operazione, v: Verifica) -> str:
    if not v.trovato:
        crt = "**NO**"
    elif v.stop_coerente is False:
        crt = f"sì, ma stop a {_r(v.scarto_stop_in_r)}R dal suo"
    elif v.verso_giusto is False:
        crt = "sì, **verso opposto**"
    else:
        crt = f"sì ({v.tf_range}→{v.tf_esecuzione})"
    return (
        f"| {op.aperta:%d/%m %H:%M} | {op.simbolo} | {op.direzione} | "
        f"{ESITO_SEGNO.get(op.esito, '?')} {op.esito} | {_r(op.erre)}R | "
        f"{_durata(op.durata)} | {'sì' if op.tp1_raggiunto else 'no'} | {crt} |"
    )


def scheda(op: Operazione, v: Verifica) -> str:
    """Il caso concreto, disteso: serve per andarlo a guardare sul grafico."""
    fuori = [
        f"### {op.aperta:%d/%m/%Y %H:%M} · {op.simbolo} {op.direzione} "
        f"· {ESITO_SEGNO.get(op.esito, '?')} {op.esito} ({_r(op.erre)}R)",
        "",
        f"- ingresso `{op.ingresso:g}`, stop `{op.stop:g}`, target `{op.target:g}`"
        if op.stop and op.target else f"- ingresso `{op.ingresso:g}`",
        f"- durata {_durata(op.durata)}, parziale {'preso' if op.tp1_raggiunto else 'non preso'}",
    ]
    if v.trovato:
        fuori.append(
            f"- CRT trovato su **{v.tf_range} → {v.tf_esecuzione}**: bordo "
            f"`{_r(v.livello_range, 5)}`, spinta fino a `{_r(v.estremo, 5)}`, "
            f"rientro alle {v.rientro_a:%H:%M} dopo {v.barre_di_attesa} barre")
        if v.stop_coerente is False:
            fuori.append(
                f"- ⚠️ **lo stop del bot non e' quello del CRT**: dista "
                f"{_r(v.scarto_stop_in_r)}R dall'estremo della manipolazione")
        if v.verso_giusto is False:
            fuori.append("- ⚠️ **il verso non corrisponde** al CRT trovato")
    else:
        fuori.append(f"- ⚠️ **nessun CRT** al momento dell'ingresso: {v.nota}")
    fuori.append("")
    return "\n".join(fuori)


def riepilogo(coppie: list[tuple[Operazione, Verifica]]) -> str:
    n = len(coppie)
    if not n:
        return "Nessuna operazione nel periodo.\n"
    chiuse = [o for o, _ in coppie if o.chiusa]
    erre = [o.erre for o in chiuse if o.erre is not None]
    vinte = sum(1 for x in erre if x > 0)
    senza = sum(1 for _, v in coppie if not v.trovato)
    storti = sum(1 for _, v in coppie if v.trovato and v.stop_coerente is False)
    return "\n".join([
        f"- operazioni esaminate: **{n}** ({len(chiuse)} chiuse)",
        f"- esito: **{vinte} in utile** su {len(erre)}, "
        f"R totale **{_r(sum(erre))}**, R medio **{_r(sum(erre)/len(erre)) if erre else '—'}**"
        if erre else "- nessuna chiusa con R calcolabile",
        f"- parziale preso: {sum(1 for o, _ in coppie if o.tp1_raggiunto)}",
        "",
        "**Quello che conta per correggere:**",
        f"- ingressi **senza nessun CRT** ricostruibile: **{senza}** su {n}",
        f"- ingressi con CRT ma **stop in un altro posto**: **{storti}** su {n}",
        "",
    ])


def scrivi(coppie: list[tuple[Operazione, Verifica]], percorso: Path) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    testa = TESTA_A_MANO
    if percorso.exists():
        vecchio = percorso.read_text(encoding="utf-8")
        if FINE in vecchio:
            testa = vecchio.split(FINE)[0] + FINE + "\n"

    corpo = [
        "",
        f"_Rigenerato il {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC da "
        "`diario_operazioni.py`._",
        "",
        "## Riepilogo",
        "",
        riepilogo(coppie),
        "## Tutte le operazioni",
        "",
        "| quando | strumento | verso | esito | R | durata | parziale | c'era il CRT? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    corpo += [riga_tabella(o, v) for o, v in coppie]

    sospette = [(o, v) for o, v in coppie
                if not v.trovato or v.stop_coerente is False or v.verso_giusto is False]
    corpo += ["", "## I casi da guardare sul grafico", ""]
    if sospette:
        corpo += [
            f"Sono {len(sospette)}. Ognuno ha data, ora e livelli: si apre il "
            "grafico, si va li', e si vede chi ha ragione.", ""]
        corpo += [scheda(o, v) for o, v in sospette]
    else:
        corpo += ["Nessuno: ogni ingresso e' spiegato da un CRT ricostruibile "
                  "con lo stop al posto giusto.", ""]

    percorso.write_text(testa + "\n".join(corpo) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--giorni", type=int, default=None)
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--file", default="diario/operazioni.md")
    args = p.parse_args()

    ops = operazioni(args.giorni, args.limite)
    print(f"operazioni da esaminare: {len(ops)}")
    fornitore = FornitoreTradingView()
    coppie = []
    for i, op in enumerate(ops, 1):
        coppie.append((op, verifica_crt(op, fornitore)))
        if i % 25 == 0:
            print(f"  {i}/{len(ops)}")

    percorso = Path(args.file)
    scrivi(coppie, percorso)
    senza = sum(1 for _, v in coppie if not v.trovato)
    storti = sum(1 for _, v in coppie if v.trovato and v.stop_coerente is False)
    print(f"scritto {percorso}")
    print(f"  senza CRT ricostruibile: {senza}")
    print(f"  con stop fuori posto:    {storti}")


if __name__ == "__main__":
    main()
