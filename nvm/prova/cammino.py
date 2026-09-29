"""Il cammino anno per anno (Fase F): il Capo giudicato su anni che non ha visto.

Per ogni anno Y il Capo si allena sulle operazioni **chiuse** prima del 1°
gennaio di Y, e sceglie fra quelle di Y. Poi il cancello della Fase F
(`spec/capo.md`): le scelte contro tutta la base negli stessi anni.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from nvm.agenti import capo as capo_mod
from nvm.agenti.cacciatore import Verso
from nvm.agenti.capo import COLONNE, Capo, esiti, riga
from nvm.prova.base import SETTIMANA, Risultato
from nvm.prova.campo import Uscita
from nvm.tempo import TF

# La coppia che nasce dai quarti d'ora, come `COPPIA_VELOCE` del bot dal vivo.
COPPIA_QUARTI = (TF.H4, TF.M15)


def _anno(t: np.ndarray) -> np.ndarray:
    return np.array([datetime.fromtimestamp(int(x), tz=timezone.utc).year for x in t])


def _inizio_anno(a: int) -> int:
    return int(datetime(a, 1, 1, tzinfo=timezone.utc).timestamp())


@dataclass
class Tabella:
    """Le operazioni con tutto quello che serve al Capo e al cancello."""

    x: np.ndarray
    quando: np.ndarray
    chiusa: np.ndarray
    erre: np.ndarray
    tp1: np.ndarray
    tp2: np.ndarray
    rr1: np.ndarray
    rr2: np.ndarray
    costi: np.ndarray
    # Le operazioni chiuse dal tetto di sicurezza invece che da stop o target:
    # l'allenamento degli agenti le tiene d'occhio (`spec/allenamento.md`).
    scaduta: Optional[np.ndarray] = None
    # Lo strumento e il verso (+1 acquisto, -1 vendita) di ogni operazione: servono al Rischio
    # per il conto intero, con le operazioni aperte insieme (`nvm/agenti/portafoglio.py`).
    strumento: Optional[np.ndarray] = None
    verso: Optional[np.ndarray] = None
    # Cosa vedeva ogni agente all'ingresso (`nvm/cervello/viste.py`), per allenare i cervelli.
    viste: Optional[dict] = None
    # Come sarebbe finita ogni operazione con ognuno dei piani fra cui i cervelli scelgono
    # (`nvm/cervello/piani.py`), in R: una colonna per piano.
    piani: Optional[np.ndarray] = None

    def __len__(self) -> int:
        return len(self.quando)

    @property
    def anno(self) -> np.ndarray:
        return _anno(self.quando)

    @classmethod
    def da(cls, risultati: list[Risultato], pareri: list) -> "Tabella":
        x = np.array([riga(r, *p) for r, p in zip(risultati, pareri)]).reshape(len(risultati), len(COLONNE))
        e = np.array([esiti(r) for r in risultati], bool).reshape(len(risultati), 2)
        return cls(
            x=x,
            quando=np.array([r.quando for r in risultati], np.int64),
            chiusa=np.array([r.chiusa_quando for r in risultati], np.int64),
            erre=np.array([r.erre for r in risultati]),
            tp1=e[:, 0], tp2=e[:, 1],
            rr1=np.array([r.rr1 for r in risultati]),
            rr2=np.array([r.rr2 for r in risultati]),
            costi=np.array([r.costo_erre for r in risultati]),
            scaduta=np.array([r.uscita is Uscita.SCADUTA for r in risultati], bool),
            strumento=np.array([r.strumento for r in risultati], str),
            verso=np.array([-1 if r.verso is Verso.SHORT else 1 for r in risultati], np.int8),
        )

    def salva(self, percorso: Path) -> None:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        dati = {k: v for k, v in self.__dict__.items() if v is not None and k != "viste"}
        dati |= {f"vista {a}": v for a, v in (self.viste or {}).items()}
        np.savez_compressed(percorso, **dati)

    @classmethod
    def carica(cls, percorso: Path) -> "Tabella":
        with np.load(percorso) as f:
            viste = {k[len("vista "):]: f[k] for k in f.files if k.startswith("vista ")}
            return cls(**{k: f[k] for k in f.files if not k.startswith("vista ")}, viste=viste or None)


def coppie_di(base, quarti, coppie) -> list:
    """Le coppie di uno strumento con le candele da cui nascono: le ore per le coppie orarie e,
    se ci sono i quarti d'ora, anche il 4 ore -> 15 minuti, come fa il bot dal vivo."""
    fuori = [(alto, basso, base) for alto, basso in coppie]
    if quarti is not None and len(quarti):
        fuori.append((*COPPIA_QUARTI, quarti))
    return fuori


def costruisci_tabella(
    basi: dict, coppie, dal: int, al: int, variante=None, stretto: bool = False, spread: float = 1.0,
    dire: Optional[Callable[[str], None]] = None, quarti: Optional[dict] = None, con_viste: bool = False,
) -> Tabella:
    """Tutte le operazioni delle coppie con ingresso in [dal, al), con le risposte degli agenti.

    `basi` sono le ore di ogni strumento, `quarti` i quarti d'ora (dalla VPS, `consegna.py`)
    per la coppia 4 ore -> 15 minuti. E' la tabella su cui il Capo si allena (`capo.py`) e su
    cui gli agenti provano le loro manopole (`nvm/prova/allenamento.py`).
    """
    from nvm.agenti import capo as il_capo, inventate
    from nvm.agenti.conferme import SOPRA, tutti_i_pareri
    from nvm.dati.candele import costruisci
    from nvm.dati.spread import allarga
    from nvm.prova.base import opera
    from nvm.prova.romeo import grandi
    from nvm.tempo import TF

    risultati, pareri, occhi, piani = [], [], {}, []
    for strumento, base in basi.items():
        fine = int(base.t[-1]) + base.passo
        g = grandi(base, fine)
        settimane = costruisci(base, TF.W1).chiuse_entro(fine)
        # Per le domande inventate dagli agenti e tenute dalla palestra.
        idee = il_capo.INVENTATE
        ctx = inventate.Contesto.da(base, fine, g) if idee else None
        for alto, basso, dati in coppie_di(base, (quarti or {}).get(strumento), coppie):
            fine_dati = int(dati.t[-1]) + dati.passo
            alte = costruisci(dati, alto).chiuse_entro(fine_dati)
            basse = costruisci(dati, basso).chiuse_entro(fine_dati)
            sopra = costruisci(base, SOPRA[alto]).chiuse_entro(fine)
            if spread != 1:
                basse = allarga(basse, spread)
            r = opera(alte, basse, dal, al, variante, stretto)
            risultati += r
            nuovi = [tutti_i_pareri(x.scatto, alte, basse, sopra, settimane, g) + (inventate.rispondi_tutte(idee, x, ctx),)
                     for x in r]
            pareri += nuovi
            if con_viste:
                from nvm.agenti.capo import riga as riga_capo
                from nvm.cervello.viste import viste
                from nvm.cervello.piani import risultati as dei_piani
                from nvm.cervello.viste import COMPAGNI
                gemello = COMPAGNI.get(strumento)
                compagno = (basi.get(gemello[0]), gemello[1]) if gemello else None
                for x, p in zip(r, nuovi):
                    for a, v in viste(x, alte, basse, sopra, settimane, riga_capo(x, *p), g, compagno).items():
                        occhi.setdefault(a, []).append(v)
                    piani.append(dei_piani(x.scatto, basse))
            if dire:
                dire(f"{strumento} {alto.value}-{basso.value}: {len(r)} operazioni")
    t = Tabella.da(risultati, pareri)
    if con_viste:
        t.viste = {a: np.array(v) for a, v in occhi.items()}
        t.piani = np.array(piani).reshape(len(risultati), -1)
    return t


@dataclass
class Cammino:
    scelte: np.ndarray            # quali operazioni il Capo avrebbe preso
    atteso: np.ndarray            # il suo guadagno atteso, NaN fuori dagli anni giudicati
    giudicati: np.ndarray         # le operazioni negli anni giudicati
    fiducia: dict[int, list]      # i pesi del Capo, anno per anno
    qualita: Optional[np.ndarray] = None   # la qualita' attesa, su cui il Capo decide


def cammino(t: Tabella, primo: int = 2008, ultimo: int = 2023) -> Cammino:
    anni = t.anno
    atteso = np.full(len(t), np.nan)
    qualita = np.full(len(t), np.nan)
    fiducia = {}
    for a in range(primo, ultimo + 1):
        oggi = anni == a
        if not oggi.any():
            continue
        passato = t.chiusa < _inizio_anno(a)
        capo = Capo.allena(t.x[passato], t.tp1[passato], t.tp2[passato])
        atteso[oggi] = capo.valore_atteso(t.x[oggi], t.rr1[oggi], t.rr2[oggi], t.costi[oggi])
        qualita[oggi] = capo.qualita(t.x[oggi], t.rr1[oggi], t.rr2[oggi], t.costi[oggi])
        fiducia[a] = capo.fiducia()
    giudicati = (anni >= primo) & (anni <= ultimo)
    # Il Capo entra quando la qualita' attesa supera la sua soglia (`nvm/agenti/capo.py`).
    return Cammino(giudicati & (qualita > capo_mod.SOGLIA), atteso, giudicati, fiducia, qualita)


@dataclass
class Giudizio:
    n_scelte: int
    n_base: int
    media_scelte: float
    media_base: float
    differenza: float
    basso: float
    alto: float
    livello: float
    anni_concordi: float
    per_anno: dict[int, tuple[int, float, int, float]]

    def testo(self) -> str:
        anni = "  ".join(f"{a}:{ms:+.2f}({ns})/{mb:+.2f}" for a, (ns, ms, nb, mb) in sorted(self.per_anno.items()))
        return (
            f"scelte {self.n_scelte} R medio {self.media_scelte:+.3f}  base {self.n_base} R medio {self.media_base:+.3f}\n"
            f"  differenza {self.differenza:+.3f}  IC{self.livello:.2%} [{self.basso:+.3f}, {self.alto:+.3f}]  "
            f"stesso segno in {self.anni_concordi:.0%} degli anni\n"
            f"  per anno (scelte R(n)/base R): {anni}"
        )


def giudica(
    scelte_quando: np.ndarray, scelte_erre: np.ndarray, base_quando: np.ndarray, base_erre: np.ndarray,
    k: int = 1, ripetizioni: int = 4000, seme: int = 0,
) -> Giudizio:
    """Le scelte contro la base, con l'intervallo al 1 - 5%/k a blocchi settimanali."""
    settimane = np.unique(np.r_[scelte_quando, base_quando] // SETTIMANA)
    gs = np.searchsorted(settimane, scelte_quando // SETTIMANA)
    gb = np.searchsorted(settimane, base_quando // SETTIMANA)
    w = len(settimane)
    ss, cs = np.bincount(gs, scelte_erre, w), np.bincount(gs, minlength=w).astype(float)
    sb, cb = np.bincount(gb, base_erre, w), np.bincount(gb, minlength=w).astype(float)
    rng = np.random.default_rng(seme)
    pesca = rng.integers(0, w, size=(ripetizioni, w))
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = ss[pesca].sum(1) / cs[pesca].sum(1) - sb[pesca].sum(1) / cb[pesca].sum(1)
    diff = diff[np.isfinite(diff)]
    alfa = 0.05 / k
    media_s, media_b = float(scelte_erre.mean()), float(base_erre.mean())
    d = media_s - media_b
    anni_s, anni_b = _anno(scelte_quando), _anno(base_quando)
    per_anno, segni = {}, []
    for a in np.unique(anni_b):
        s, b = scelte_erre[anni_s == a], base_erre[anni_b == a]
        per_anno[int(a)] = (len(s), float(s.mean()) if len(s) else float("nan"), len(b), float(b.mean()))
        if len(s):
            segni.append(np.sign(s.mean() - b.mean()) == np.sign(d))
    return Giudizio(
        len(scelte_erre), len(base_erre), media_s, media_b, d,
        float(np.percentile(diff, 100 * alfa / 2)), float(np.percentile(diff, 100 * (1 - alfa / 2))),
        1 - alfa, float(np.mean(segni)) if segni else float("nan"), per_anno,
    )
