"""Il libro delle operazioni vere: il registro da mostrare, a prova di manomissione.

Ogni apertura e ogni chiusura sul conto finisce qui (`dati/vivo/libro.jsonl`), una riga per
evento, con l'impronta (SHA-256) della riga prima: cambiare, togliere o inserire una riga
passata rompe la catena, e `verifica` lo trova. Dal libro esce il rendiconto (`rendiconto`):
operazioni, vinte, R, euro, calo peggiore, mese per mese.

Serve per un track record credibile. Per chi compra, la prova piu' forte resta anche un
servizio esterno collegato al conto (per esempio Myfxbook), che il bot non puo' toccare.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LIBRO = "libro.jsonl"
INIZIO = "0" * 64


def _impronta(riga: dict) -> str:
    return hashlib.sha256(json.dumps(riga, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _righe(cartella: Path) -> list[dict]:
    p = cartella / LIBRO
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def scrivi(cartella: Path, evento: str, quando: Optional[int] = None, **dati) -> dict:
    """Aggiunge un evento in fondo al libro, legato all'impronta del precedente."""
    righe = _righe(cartella)
    riga = {"n": len(righe) + 1, "evento": evento, "quando": int(quando if quando is not None else datetime.now(timezone.utc).timestamp()),
            **dati, "prima": righe[-1]["impronta"] if righe else INIZIO}
    riga["impronta"] = _impronta(riga)
    cartella.mkdir(parents=True, exist_ok=True)
    with (cartella / LIBRO).open("a", encoding="utf-8") as f:
        f.write(json.dumps(riga, ensure_ascii=False) + "\n")
    return riga


def verifica(cartella: Path) -> tuple[bool, str]:
    """Il libro e' integro? Controlla la catena delle impronte, riga per riga."""
    prima = INIZIO
    for i, riga in enumerate(_righe(cartella), start=1):
        copia = {k: v for k, v in riga.items() if k != "impronta"}
        if riga.get("n") != i or riga.get("prima") != prima or _impronta(copia) != riga.get("impronta"):
            return False, f"il libro è stato toccato alla riga {i}"
        prima = riga["impronta"]
    return True, "il libro è integro"


def rendiconto(cartella: Path) -> str:
    """I risultati veri del conto, dal libro."""
    ok, stato = verifica(cartella)
    chiuse = [r for r in _righe(cartella) if r["evento"] == "chiusura"]
    righe = ["📒 Rendiconto delle operazioni vere", f"({stato})", ""]
    if not chiuse:
        return "\n".join(righe + ["Nessuna operazione chiusa finora."])
    erre = [float(r["erre"]) for r in chiuse]
    netto = [float(r.get("netto", 0.0)) for r in chiuse]
    vinte = sum(x > 0.05 for x in erre)
    saldi = [float(r["saldo"]) for r in chiuse if r.get("saldo") is not None]
    calo = 0.0
    if saldi:
        massimo = saldi[0] - netto[0]
        for s in saldi:
            massimo = max(massimo, s)
            calo = max(calo, 1 - s / massimo if massimo > 0 else 0.0)
    valuta = chiuse[-1].get("valuta", "")

    def v(x):
        return f"{x:+.2f}".replace(".", ",").replace("-", "−")
    righe += [f"• Operazioni chiuse: {len(chiuse)} · in guadagno: {vinte} ({vinte / len(chiuse):.0%})",
              f"• Risultato: {v(sum(erre))} volte il rischio · {v(sum(netto))} {valuta}",
              f"• Calo peggiore del conto: {calo:.1%}".replace(".", ","), "", "Mese per mese"]
    mesi: dict[str, list] = {}
    for r in chiuse:
        m = datetime.fromtimestamp(r["quando"], tz=timezone.utc).strftime("%m/%Y")
        mesi.setdefault(m, []).append(r)
    for m, rr in mesi.items():
        righe.append(f"• {m}: {len(rr)} operazioni, {v(sum(float(x['erre']) for x in rr))} R, "
                     f"{v(sum(float(x.get('netto', 0.0)) for x in rr))} {valuta}")
    return "\n".join(righe)
