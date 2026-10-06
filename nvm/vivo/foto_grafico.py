"""Le foto del grafico per Telegram, disegnate dal bot (non piu' fotografate da MT5).

Il proprietario, 07/10/2026: *"quando manda le foto non si legge un cazzo ... il colore, lo sfondo ... io così
non riesco a distinguere niente"*. Le foto di MT5 prendevano i colori del terminale, scritte minuscole e tutti i
disegni dello strumento insieme. Qui: sfondo bianco, candele verdi e rosse come su TradingView, scritte grandi,
solo l'operazione (il range, la candela 2 e la 3, la finta, il key level, l'entrata, lo stop, il TP1 e il target
finale), inquadrata sulle candele del suo timeframe. Le foto di MT5 non si mandano piu'.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np

from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO
from nvm.tempo import TF

ROMA = ZoneInfo("Europe/Rome")

# I colori di TradingView.
VERDE, ROSSO = "#089981", "#F23645"
BLU, ARANCIO, GRIGIO, NERO, VIOLA = "#2962FF", "#FF9800", "#787B86", "#131722", "#9C27B0"
NOMI_TF = {TF.M15: "15 minuti", TF.H1: "1 ora", TF.H4: "4 ore", TF.H6: "6 ore", TF.H12: "12 ore",
           TF.D1: "giornaliero", TF.W1: "settimanale", TF.MN: "mensile"}
LARGHEZZA, ALTEZZA, DPI = 12.8, 10.0, 100


def pronto() -> bool:
    """C'e' matplotlib (si installa con `requirements.txt`; se manca lo installa il bot, `vivo.prepara_foto`)."""
    import importlib
    importlib.invalidate_caches()
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class Linea:
    prezzo: float
    nome: str
    colore: str
    stile: str = "-"            # "-" piena, "--" tratteggiata, ":" puntini
    da: Optional[int] = None    # da quale istante parte (None: da sinistra)


@dataclass
class Quadro:
    """Cosa disegnare oltre alle candele."""

    titolo: str
    sottotitolo: str = ""
    linee: list[Linea] = field(default_factory=list)
    # Il range: (inizio della candela 1 o madre, inizio della candela 2, massimo, minimo, nome).
    range_: Optional[tuple] = None
    verticali: list[tuple] = field(default_factory=list)          # (istante, nome)
    # (istante, prezzo, testo, colore, "^"/"v"/"o", testo sotto)
    segni: list[tuple] = field(default_factory=list)


def _cifre(prezzi) -> int:
    p = float(np.nanmax(np.abs(prezzi))) if len(prezzi) else 1.0
    return 2 if p >= 100 else (3 if p >= 10 else 5)


def _etichetta_ora(t: int, tf: TF) -> str:
    d = datetime.fromtimestamp(int(t), tz=ROMA)
    if tf in (TF.MN,):
        return d.strftime("%m/%Y")
    if tf in (TF.D1, TF.W1):
        return d.strftime("%d/%m")
    return d.strftime("%d/%m %H:%M")


def _distanzia(ys: list[float], minimo: float) -> list[float]:
    """Le etichette a destra non si coprono: dal basso in alto, ognuna almeno `minimo` sopra quella prima."""
    ordine = sorted(range(len(ys)), key=lambda i: ys[i])
    fuori = list(ys)
    for a, b in zip(ordine, ordine[1:]):
        if fuori[b] - fuori[a] < minimo:
            fuori[b] = fuori[a] + minimo
    # Se si e' andati troppo in alto, si riabbassa tutto il gruppo attorno al centro di prima.
    if ordine:
        spinta = (sum(fuori) - sum(ys)) / len(ys)
        fuori = [y - spinta for y in fuori]
    return fuori


def disegna(c, q: Quadro, quante: int = 60, fino: Optional[int] = None, da: Optional[int] = None,
            vuote: int = 4) -> bytes:
    """Il PNG: le candele di `c` (fino a `fino`, se c'e'; da `quante` candele prima di `da`, o le ultime `quante`)
    con i disegni di `q`; `vuote` candele vuote a destra, per l'operazione e i nomi delle linee."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    if fino is not None:
        c = c.chiuse_entro(fino)
    n0 = max(0, len(c) - quante) if da is None else max(0, int(np.searchsorted(c.inizio, da)) - quante)
    inizio = c.inizio[n0:]
    b = c.bid[n0:]
    n = len(inizio)
    passo = int(np.median(np.diff(inizio))) if n > 1 else 3600

    def x_di(t: int) -> float:
        """La posizione sull'asse delle candele (anche oltre l'ultima, per la candela 3 appena aperta)."""
        k = int(np.searchsorted(inizio, t, side="right")) - 1
        if k < 0:
            return -0.5
        if k == n - 1 and t >= inizio[-1] + passo:
            return float(n)           # la candela dopo l'ultima (anche dopo il fine settimana)
        return float(k)

    fig, ax = plt.subplots(figsize=(LARGHEZZA, ALTEZZA), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    xs = np.arange(n)
    su = b[:, CHIUSURA] >= b[:, APERTURA]
    colori = np.where(su, VERDE, ROSSO)
    ax.vlines(xs, b[:, MINIMO], b[:, MASSIMO], colors=colori, linewidth=1.6, zorder=2)
    corpo = np.maximum(np.abs(b[:, CHIUSURA] - b[:, APERTURA]), 1e-12)
    ax.bar(xs, corpo, bottom=np.minimum(b[:, APERTURA], b[:, CHIUSURA]), width=0.7, color=colori,
           edgecolor=colori, zorder=3)

    destra = n + vuote        # spazio a destra per l'operazione e i nomi delle linee
    prezzi = [float(b[:, MINIMO].min()), float(b[:, MASSIMO].max())] if n else [0.0, 1.0]
    vicini = [l.prezzo for l in q.linee if "Target" not in l.nome]
    if q.range_ is not None:
        vicini += [q.range_[2], q.range_[3]]
    basso, alto = min(prezzi + vicini), max(prezzi + vicini)
    fuori = []
    for l in q.linee:
        if "Target" in l.nome and not (basso - 1.5 * (alto - basso) <= l.prezzo <= alto + 1.5 * (alto - basso)):
            fuori.append(l)
        else:
            basso, alto = min(basso, l.prezzo), max(alto, l.prezzo)
    margine = (alto - basso) * 0.08 or abs(alto) * 0.001
    ax.set_ylim(basso - margine, alto + margine)
    ax.set_xlim(-1, destra)
    cifre = _cifre(np.r_[prezzi, vicini])

    if q.range_ is not None:
        t1, t2, r_alto, r_basso, nome = q.range_
        x1, x2 = x_di(t1) - 0.45, x_di(t2) - 0.5
        ax.add_patch(Rectangle((x1, r_basso), max(x2 - x1, 0.9), r_alto - r_basso, facecolor=BLU, alpha=0.12,
                               edgecolor=BLU, linewidth=1.5, zorder=1))
        ax.text((x1 + x2) / 2, r_alto + margine * 0.15, nome, color=BLU, fontsize=13, fontweight="bold", va="bottom",
                ha="right", zorder=6, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.8))
    for t, nome in q.verticali:
        x = x_di(t) - 0.5
        ax.axvline(x, color=GRIGIO, linestyle="--", linewidth=1.3, zorder=1)
        ax.text(x + 0.15, alto + margine * 0.6, nome, color=GRIGIO, fontsize=13, va="top", ha="left", zorder=6)
    dentro = [l for l in q.linee if l not in fuori]
    ys = _distanzia([l.prezzo for l in dentro], (alto - basso + 2 * margine) * 0.05)
    for l, y in zip(dentro, ys):
        x0 = x_di(l.da) - 0.5 if l.da is not None else -1
        ax.hlines(l.prezzo, x0, destra, colors=l.colore, linestyles=l.stile, linewidth=2.2, zorder=4)
        ax.text(destra - 0.2, y, f"{l.nome}  {l.prezzo:.{cifre}f}", color="white", fontsize=14,
                fontweight="bold", ha="right", va="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=l.colore, edgecolor="none"))
    for t, p, testo, colore, marca, sotto in q.segni:
        x = x_di(t)
        ax.plot([x], [p], marker=marca, markersize=16, color=colore, zorder=8,
                markeredgecolor="white", markeredgewidth=1.5)
        if testo:
            ax.annotate(testo, (x, p), xytext=(-14, -22 if sotto else 22), textcoords="offset points",
                        color=colore, fontsize=14, fontweight="bold", va="center", ha="right", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=colore, alpha=0.9))
    for k, l in enumerate(fuori):
        sopra = l.prezzo > alto
        y = alto + margine * 0.2 if sopra else basso - margine * 0.2
        ax.text(destra - 0.2, y, f"{l.nome} {l.prezzo:.{cifre}f} {'↑ più in alto' if sopra else '↓ più in basso'}",
                color=l.colore, fontsize=14, fontweight="bold", ha="right", va="bottom" if not sopra else "top",
                zorder=7, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=l.colore))

    # Gli assi: il prezzo a destra, le ore italiane in basso.
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis="both", labelsize=13, colors=NERO)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter(f"%.{cifre}f"))
    tacche = np.linspace(0, max(n - 1, 0), num=min(6, max(n, 1))).astype(int) if n else []
    ax.set_xticks(tacche)
    ax.set_xticklabels([_etichetta_ora(int(inizio[k]), c.tf) for k in tacche])
    ax.grid(True, color="#E0E3EB", linewidth=0.8, zorder=0)
    for lato in ("top", "left"):
        ax.spines[lato].set_visible(False)
    for lato in ("right", "bottom"):
        ax.spines[lato].set_color("#B2B5BE")
    fig.suptitle(q.titolo, fontsize=22, fontweight="bold", color=NERO, x=0.02, ha="left", y=0.985)
    if q.sottotitolo:
        fig.text(0.02, 0.935, q.sottotitolo, fontsize=14, color=GRIGIO, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    uscita = io.BytesIO()
    fig.savefig(uscita, format="png", dpi=DPI, facecolor="white")
    plt.close(fig)
    return uscita.getvalue()


def operazione_foto(d, viva=None) -> bytes:
    """La foto di un'operazione del metodo delle foto, come le disegna il proprietario: il range, la candela 2 con la
    finta, la candela 3 con l'entrata, lo stop oltre la candela 2, il TP1 all'altro lato del range e il target
    finale."""
    info = d.foto
    s, q, ob = info["setup"], info["quadro"], info["obiettivo"]
    op = d.op
    c = q.candele[s.tf]
    vende = s.short
    ingresso = float(viva.ingresso) if viva is not None else float(op.ingresso)
    stop = float(viva.stop) if viva is not None else float(op.stop)
    ny = datetime.fromtimestamp(int(s.n3_inizio), tz=ROMA)
    quadro = Quadro(
        titolo=f"{s.strumento} · CRT {NOMI_TF.get(s.tf, s.tf.value)} · {'VENDITA' if vende else 'ACQUISTO'}",
        sottotitolo=f"Entrata all'apertura della candela 3: {ny.strftime('%d/%m/%Y %H:%M')} (ora italiana)",
        range_=(int(s.range_inizio), int(s.n2_inizio), float(s.range_alto), float(s.range_basso),
                "Range (candela madre)" if s.dentro else "Range (candela 1)"),
        verticali=[(int(s.n3_inizio), "Candela 3: entrata")],
        segni=[(int(s.n2_inizio), float(s.n2_alto if vende else s.n2_basso), "Finta (candela 2)", ROSSO, "o",
                not vende),
               (int(s.n3_inizio), ingresso, "", VIOLA, "v" if vende else "^", False)],
    )
    for l in s.presi[-1:]:
        quadro.linee.append(Linea(float(l.prezzo), f"Key level preso: {l.nome}", ARANCIO, ":"))
    quadro.linee += [
        Linea(stop, "Stop", ROSSO, "-", int(s.n3_inizio)),
        Linea(ingresso, "Entrata", NERO, "--", int(s.n3_inizio)),
        Linea(float(op.tp1), "TP1 (metà + pareggio)" if float(op.tp2) != float(op.tp1) else "TP1", VERDE, "--",
              int(s.n3_inizio)),
    ]
    if float(op.tp2) != float(op.tp1):
        quadro.linee.append(Linea(float(op.tp2), f"Target finale ({ob.nome})" if ob is not None else "Target finale",
                                  VERDE, "-", int(s.n3_inizio)))
    return disegna(c, quadro, quante=16, da=int(s.range_inizio), vuote=9)


def grafico(candele, strumento: str, aperte: list = ()) -> bytes:
    """Il comando /grafico: le ultime candele e le operazioni aperte su quello strumento."""
    q = Quadro(titolo=f"{strumento} · {NOMI_TF.get(candele.tf, candele.tf.value)}",
               sottotitolo=f"Aggiornato alle {datetime.now(ROMA).strftime('%d/%m %H:%M')} (ora italiana)")
    for v in aperte:
        vende = v.verso == "short"
        q.segni.append((int(v.quando), float(v.ingresso), "", VIOLA, "v" if vende else "^", False))
        q.linee.append(Linea(float(v.ingresso), "Entrata " + ("vendita" if vende else "acquisto"), NERO, "--",
                             int(v.quando)))
        q.linee += [Linea(float(v.stop), "Stop", ROSSO, "-", int(v.quando)),
                    Linea(float(v.tp1), "TP1", VERDE, "--", int(v.quando)),
                    Linea(float(v.tp2), "Target finale", VERDE, "-", int(v.quando))]
    return disegna(candele, q, quante=60, vuote=8)
