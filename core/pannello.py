"""Il pannello: far vedere cosa il bot guarda, cosa decide e perche'.

Un motore che si astiene e scrive "PRIN-99, CTX-02" nel log e' corretto e
illeggibile. Per capire se la strategia e' interpretata come la si intendeva
non basta il testo: serve vedere le candele su cui la decisione e' stata
presa, con sopra i livelli che ha calcolato e l'elenco delle regole che hanno
parlato.

Le pagine sono due:

  `/`              lo stato di adesso, e l'elenco delle ultime decisioni
  `/decisione/N`   una decisione sola, con il grafico delle candele che il
                   motore aveva davanti in quel momento

Il grafico e' SVG generato qui: nessuna libreria, nessuna rete. Il pannello
deve funzionare anche su una macchina che non ha altro che il bot.

**Le candele disegnate sono quelle vere.** Non vengono ricostruite ne'
approssimate: si rileggono dall'archivio fino all'istante della decisione,
con la stessa barriera anti-lookahead del motore, cosi' quello che vedi e'
esattamente quello che ha visto lui.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from core import storage
from core.simboli import future_da_ticker, timeframe_da_intervallo

# Quante candele mostrare attorno alla decisione.
CANDELE_NEL_GRAFICO = 60

_STILE = """
:root{--fondo:#0e1211;--carta:#161b19;--riga:#2a3230;--testo:#e2e8e4;
--tenue:#93a09b;--accento:#3fbba2;--su:#3fbba2;--giu:#ee7a55;--giallo:#d9a63a}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--testo);
font:14px/1.55 "IBM Plex Sans",-apple-system,Segoe UI,sans-serif}
a{color:var(--accento);text-decoration:none}
a:hover{text-decoration:underline}
.foglio{max-width:1100px;margin:0 auto;padding:1.5rem 1.25rem 4rem}
h1{font-size:1.5rem;margin:0 0 .2rem;letter-spacing:-.02em}
h2{font-size:1rem;margin:2rem 0 .6rem;color:var(--tenue);
text-transform:uppercase;letter-spacing:.09em;font-weight:600}
.sotto{color:var(--tenue);margin:0 0 1.5rem;font-size:.85rem}
.mono{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}
.righello{display:flex;flex-wrap:wrap;gap:.6rem;margin-bottom:1.4rem}
.tessera{background:var(--carta);border:1px solid var(--riga);border-radius:6px;
padding:.6rem .85rem;min-width:8.5rem}
.tessera .eti{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;
color:var(--tenue)}
.tessera .val{font-size:1.25rem;font-family:"IBM Plex Mono",monospace;
font-variant-numeric:tabular-nums}
.pillola{display:inline-block;padding:.1rem .5rem;border-radius:99px;
font-size:.72rem;font-weight:600;letter-spacing:.04em}
.ok{background:#122b26;color:var(--accento)}
.attenzione{background:#2a2110;color:var(--giallo)}
.male{background:#2e1913;color:var(--giu)}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;
color:var(--tenue);padding:.4rem .6rem;border-bottom:1px solid var(--riga)}
td{padding:.5rem .6rem;border-bottom:1px solid var(--riga);vertical-align:top}
tr:hover td{background:#1b211f}
.scorre{overflow-x:auto}
.regola{display:inline-block;background:#1b211f;border:1px solid var(--riga);
border-radius:3px;padding:.05rem .35rem;margin:.1rem .15rem .1rem 0;
font-family:"IBM Plex Mono",monospace;font-size:.72rem}
.regola.blocca{border-color:var(--giu);color:var(--giu)}
.regola.usata{border-color:var(--accento);color:var(--accento)}
.motivo{color:var(--tenue);font-size:.82rem}
.vuoto{color:var(--tenue);padding:2rem;text-align:center}
"""


def _t(valore: Any) -> str:
    return html.escape(str(valore if valore is not None else "—"))


def _intestazione(titolo: str, sottotitolo: str, aggiorna: int = 15) -> str:
    return (
        f"<!doctype html><html lang='it'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv='refresh' content='{aggiorna}'>"
        f"<title>{_t(titolo)}</title><style>{_STILE}</style></head><body>"
        f"<div class='foglio'><h1>{_t(titolo)}</h1>"
        f"<p class='sotto'>{sottotitolo}</p>"
    )


_CHIUSURA = "</div></body></html>"


# ===========================================================================
# Il grafico
# ===========================================================================
def grafico(
    candele: Sequence[dict],
    stop: Optional[float] = None,
    target: Optional[float] = None,
    larghezza: int = 1000,
    altezza: int = 420,
) -> str:
    """Disegna le candele in SVG, con stop e target se ci sono.

    Le ultime due candele — N1 e N2, quelle su cui il setup si decide —
    vengono evidenziate: sono le sole che il motore guarda per il pattern, e
    vederle distinte dalle altre e' meta' del lavoro di capire una decisione.
    """
    if len(candele) < 2:
        return "<p class='vuoto'>Non ci sono abbastanza candele da disegnare.</p>"

    margine_sx, margine_dx, margine_su, margine_giu = 8, 78, 14, 26
    area_l = larghezza - margine_sx - margine_dx
    area_a = altezza - margine_su - margine_giu

    valori = [c["massimo"] for c in candele] + [c["minimo"] for c in candele]
    for livello in (stop, target):
        if livello is not None:
            valori.append(livello)
    alto, basso = max(valori), min(valori)
    if alto == basso:
        alto, basso = alto + 1, basso - 1
    respiro = (alto - basso) * 0.06
    alto, basso = alto + respiro, basso - respiro

    def y(prezzo: float) -> float:
        return margine_su + (alto - prezzo) / (alto - basso) * area_a

    passo = area_l / len(candele)
    corpo = max(1.4, passo * 0.62)

    pezzi: list[str] = [
        f"<svg viewBox='0 0 {larghezza} {altezza}' width='100%' "
        f"style='background:#0e1211;border:1px solid #2a3230;border-radius:6px'>"
    ]

    # Griglia e scala dei prezzi.
    for frazione in (0, 0.25, 0.5, 0.75, 1):
        prezzo = basso + (alto - basso) * frazione
        yy = y(prezzo)
        pezzi.append(
            f"<line x1='{margine_sx}' y1='{yy:.1f}' x2='{larghezza - margine_dx}' "
            f"y2='{yy:.1f}' stroke='#2a3230' stroke-width='1'/>"
            f"<text x='{larghezza - margine_dx + 6}' y='{yy + 4:.1f}' fill='#93a09b' "
            f"font-size='11' font-family='monospace'>{prezzo:.5g}</text>"
        )

    ultime_due = len(candele) - 2
    for indice, candela in enumerate(candele):
        x = margine_sx + passo * (indice + 0.5)
        sale = candela["chiusura"] >= candela["apertura"]
        colore = "#3fbba2" if sale else "#ee7a55"
        opacita = "1" if indice >= ultime_due else "0.55"
        y_alto, y_basso = y(candela["massimo"]), y(candela["minimo"])
        y_ap, y_ch = y(candela["apertura"]), y(candela["chiusura"])
        cima, fondo = min(y_ap, y_ch), max(y_ap, y_ch)
        pezzi.append(
            f"<line x1='{x:.1f}' y1='{y_alto:.1f}' x2='{x:.1f}' y2='{y_basso:.1f}' "
            f"stroke='{colore}' stroke-width='1' opacity='{opacita}'/>"
            f"<rect x='{x - corpo / 2:.1f}' y='{cima:.1f}' width='{corpo:.1f}' "
            f"height='{max(1.0, fondo - cima):.1f}' fill='{colore}' opacity='{opacita}'/>"
        )

    # Etichette N1 e N2 sulle due candele che formano il setup.
    for scarto, nome in ((2, "N1"), (1, "N2")):
        indice = len(candele) - scarto
        if indice < 0:
            continue
        x = margine_sx + passo * (indice + 0.5)
        pezzi.append(
            f"<text x='{x:.1f}' y='{altezza - 8}' fill='#e2e8e4' font-size='11' "
            f"font-family='monospace' text-anchor='middle'>{nome}</text>"
        )

    for livello, nome, colore in ((stop, "stop", "#ee7a55"), (target, "TP1", "#3fbba2")):
        if livello is None:
            continue
        yy = y(livello)
        pezzi.append(
            f"<line x1='{margine_sx}' y1='{yy:.1f}' x2='{larghezza - margine_dx}' "
            f"y2='{yy:.1f}' stroke='{colore}' stroke-width='1.2' stroke-dasharray='5 4'/>"
            f"<text x='{larghezza - margine_dx + 6}' y='{yy + 4:.1f}' fill='{colore}' "
            f"font-size='11' font-family='monospace'>{nome} {livello:.5g}</text>"
        )

    pezzi.append("</svg>")
    return "".join(pezzi)


# ===========================================================================
# Le regole, estratte dal motivo
# ===========================================================================
def regole_dal_motivo(motivo: str) -> list[str]:
    """Gli identificativi che il motore ha messo fra parentesi quadre."""
    if not motivo or "[" not in motivo:
        return []
    dentro = motivo[motivo.rindex("[") + 1: motivo.rindex("]")] if "]" in motivo else ""
    return [pezzo.strip() for pezzo in dentro.split(",") if pezzo.strip()]


def _regole_html(motivo: str, azione: str) -> str:
    regole = regole_dal_motivo(motivo)
    if not regole:
        return "<span class='motivo'>—</span>"
    classe = "blocca" if azione == "NONE" else "usata"
    return "".join(f"<span class='regola {classe}'>{_t(r)}</span>" for r in regole)


def _senza_regole(motivo: str) -> str:
    return motivo.split("[")[0].strip() if motivo else ""


# ===========================================================================
# Pagina principale
# ===========================================================================
def pagina_principale(stato: dict, decisioni: Sequence[dict]) -> str:
    cfg_modo = stato.get("modalita", "?")
    conto = stato.get("conto", {}) or {}
    mercato = (stato.get("fornitore_dati") or {}).get("mercato") or {}
    conteggi = stato.get("conteggi") or {}

    classe_modo = {"dry_run": "ok", "semi": "attenzione", "auto": "male"}.get(cfg_modo, "")
    pezzi = [_intestazione(
        "nvmfinancebot",
        f"<span class='pillola {classe_modo}'>{_t(cfg_modo)}</span> &nbsp; "
        f"aggiornato {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC "
        f"&middot; la pagina si ricarica da sola",
    )]

    def tessera(etichetta: str, valore: Any) -> str:
        return (f"<div class='tessera'><div class='eti'>{_t(etichetta)}</div>"
                f"<div class='val'>{_t(valore)}</div></div>")

    pezzi.append("<div class='righello'>")
    pezzi.append(tessera("candele", f"{conteggi.get('candela', 0):,}".replace(",", ".")))
    pezzi.append(tessera("decisioni", conteggi.get("decisione", 0)))
    pezzi.append(tessera("posizioni", stato.get("posizioni_aperte_archivio", 0)))
    pezzi.append(tessera("giri di mercato", mercato.get("giri", "—")))
    pezzi.append(tessera("equity", conto.get("equity", "—")))
    pezzi.append("</div>")

    # Stato dei collegamenti.
    pezzi.append("<h2>Collegamenti</h2><div class='scorre'><table><tbody>")
    for etichetta, acceso, dettaglio in (
        ("MetaTrader 5", stato.get("mt5_connesso"), stato.get("mt5_dettaglio", "")),
        ("Ciclo di mercato", mercato.get("in_funzione"),
         f"ogni {mercato.get('intervallo_sec', '?')}s, "
         f"{mercato.get('candele_raccolte', 0)} candele raccolte, "
         f"{mercato.get('valutazioni', 0)} valutazioni"),
        ("Sentinella", (stato.get("sentinella") or {}).get("attiva"),
         f"{(stato.get('sentinella') or {}).get('giri', 0)} giri, "
         f"{(stato.get('sentinella') or {}).get('chiusure', 0)} chiusure"),
        ("Telegram", stato.get("telegram_configurato"), ""),
    ):
        pillola = ("<span class='pillola ok'>acceso</span>" if acceso
                   else "<span class='pillola male'>spento</span>")
        pezzi.append(f"<tr><td>{_t(etichetta)}</td><td>{pillola}</td>"
                     f"<td class='motivo'>{_t(dettaglio)}</td></tr>")
    pezzi.append("</tbody></table></div>")

    errore = mercato.get("ultimo_errore")
    if errore:
        pezzi.append(f"<p class='motivo'>ultimo errore del mercato: {_t(errore)}</p>")

    # Le decisioni.
    pezzi.append("<h2>Ultime decisioni</h2>")
    if not decisioni:
        pezzi.append("<p class='vuoto'>Nessuna decisione ancora. "
                     "Arrivano alla chiusura di ogni candela.</p>")
    else:
        pezzi.append("<div class='scorre'><table><thead><tr>"
                     "<th>quando</th><th>strumento</th><th>tf</th><th>azione</th>"
                     "<th>regole</th><th>perche'</th><th></th>"
                     "</tr></thead><tbody>")
        for d in decisioni:
            motivo = d.get("motivo") or ""
            azione = d.get("azione", "NONE")
            colore = {"BUY": "ok", "SELL": "attenzione"}.get(azione, "")
            pezzi.append(
                f"<tr><td class='mono'>{_t(str(d.get('creata_utc', ''))[:16])}</td>"
                f"<td class='mono'>{_t(d.get('simbolo'))}</td>"
                f"<td class='mono'>{_t(d.get('tf'))}</td>"
                f"<td><span class='pillola {colore}'>{_t(azione)}</span></td>"
                f"<td>{_regole_html(motivo, azione)}</td>"
                f"<td class='motivo'>{_t(_senza_regole(motivo))[:160]}</td>"
                f"<td><a href='/decisione/{d.get('id')}'>vedi &rarr;</a></td></tr>"
            )
        pezzi.append("</tbody></table></div>")

    # Archivio.
    copertura = (stato.get("fornitore_dati") or {}).get("archivio") or []
    if copertura:
        pezzi.append("<h2>Archivio</h2><div class='scorre'><table><thead><tr>"
                     "<th>strumento</th><th>tf</th><th>candele</th><th>dalla</th>"
                     "<th>all'ultima</th></tr></thead><tbody>")
        for r in copertura:
            pezzi.append(
                f"<tr><td class='mono'>{_t(r.get('strumento'))}</td>"
                f"<td class='mono'>{_t(r.get('tf'))}</td>"
                f"<td class='mono'>{_t(r.get('quante'))}</td>"
                f"<td class='mono'>{_t(str(r.get('dalla', ''))[:10])}</td>"
                f"<td class='mono'>{_t(str(r.get('alla', ''))[:16])}</td></tr>"
            )
        pezzi.append("</tbody></table></div>")

    pezzi.append(_CHIUSURA)
    return "".join(pezzi)


# ===========================================================================
# Pagina di una decisione
# ===========================================================================
def candele_della_decisione(decisione: dict, quante: int = CANDELE_NEL_GRAFICO) -> list[dict]:
    """Le candele che il motore aveva davanti quando ha deciso.

    Si rileggono dall'archivio fermandosi alla candela dell'alert: quelle
    arrivate dopo il motore non le aveva, e disegnarle darebbe l'impressione
    che abbia deciso guardando il futuro.
    """
    future = future_da_ticker(str(decisione.get("alert_simbolo") or ""))
    tf = timeframe_da_intervallo(str(decisione.get("alert_tf") or ""))
    if future is None or tf is None:
        return []

    limite = str(decisione.get("chiusura_candela_utc") or "")
    righe = storage.candele_archiviate(future, tf.value)
    fino_a = [r for r in righe if str(r["chiusura_utc"]) <= limite] if limite else righe
    return fino_a[-quante:]


def pagina_decisione(decisione: dict, candele: Sequence[dict]) -> str:
    motivo = decisione.get("motivo") or ""
    azione = decisione.get("azione", "NONE")
    simbolo = decisione.get("alert_simbolo", "?")
    tf = decisione.get("alert_tf", "?")

    pezzi = [_intestazione(
        f"{simbolo} {tf} — {azione}",
        f"<a href='/'>&larr; torna al pannello</a> &nbsp;&middot;&nbsp; "
        f"decisione #{_t(decisione.get('id'))} del "
        f"{_t(str(decisione.get('creata_utc', ''))[:19])}",
        aggiorna=120,
    )]

    pezzi.append(grafico(
        candele,
        stop=decisione.get("sl"),
        target=decisione.get("tp"),
    ))
    if candele:
        pezzi.append(
            f"<p class='motivo'>{len(candele)} candele chiuse fino a "
            f"{_t(str(decisione.get('chiusura_candela_utc', ''))[:19])}. "
            f"N2 e' l'ultima chiusa, N1 quella prima: sono le due su cui il "
            f"setup si decide. Le candele arrivate dopo non sono disegnate "
            f"perche' il motore non le aveva.</p>"
        )

    pezzi.append("<h2>Perche'</h2>")
    testo = _senza_regole(motivo)
    pezzi.append(f"<p>{_t(testo) if testo else 'nessun motivo registrato'}</p>")
    regole = regole_dal_motivo(motivo)
    if regole:
        etichetta = ("Regole che hanno impedito l'operazione" if azione == "NONE"
                     else "Regole applicate")
        pezzi.append(f"<h2>{etichetta}</h2><p>{_regole_html(motivo, azione)}</p>")

    pezzi.append("<h2>Dati</h2><div class='scorre'><table><tbody>")
    for etichetta, valore in (
        ("azione", azione),
        ("esito", decisione.get("esito")),
        ("dettaglio", decisione.get("dettaglio")),
        ("volume", decisione.get("volume")),
        ("stop", decisione.get("sl")),
        ("target", decisione.get("tp")),
        ("ticket", decisione.get("ticket")),
        ("candela dell'alert", decisione.get("chiusura_candela_utc")),
    ):
        pezzi.append(f"<tr><td class='motivo'>{_t(etichetta)}</td>"
                     f"<td class='mono'>{_t(valore)}</td></tr>")
    pezzi.append("</tbody></table></div>")

    pezzi.append(_CHIUSURA)
    return "".join(pezzi)
