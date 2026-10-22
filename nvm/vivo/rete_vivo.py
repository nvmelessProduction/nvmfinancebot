"""La rete neurale dal vivo: guarda ogni setup del bot e dice se entrerebbe, con la sua spiegazione.

Il proprietario, 12/10/2026: *"voglio che sia la rete a decidere, così la addestriamo"*, e una sezione "Correggi" per
correggerla. La rete e' quella allenata su Kaggle (passo 2, `kaggle_rete/trader.py`): gli occhi leggono le candele di
1 ora, 4 ore, giorno, settimana e mese all'apertura della candela 3; la scheda dice cosa sa il bot del setup (timeframe,
verso, stop, TP1, target, key level, direzione). Stima quanti R porta e la probabilita' di chiudere in guadagno.
All'esame (2023-2026, mai visto) sopra il bot e' arrivata a pareggio: decide cosa proporre, non e' ancora brava.

Sui setup con tutte le regole delle foto (CRT, key level, direzione) entra sempre: il proprietario, 13/10/2026, sulle
sue foto: *"quelli sono i trade che il bot e la rete neurale devono fare. Sono esattamente quelli"*. Provata foto per
foto, la rete da sola ne lasciava 19 su 22 (la sua stima sui vent'anni era sotto la soglia): la stima resta scritta,
ma su quei setup non decide piu' lei. Sugli altri setup entra se la stima supera la soglia, come prima.

La spiegazione:
- **cosa vedono gli occhi**: le risposte della scuola 2 (direzione di giorno, settimana e mese; CRT e setup a 4 ore e
  del giorno), che si possono controllare sul grafico;
- **cosa pesa**: per ogni cosa che la rete guarda, quanto sposta la stima rispetto a un setup tipico del bot (la
  mediana dei setup A+ dello studio) e a un grafico piatto (gradienti integrati: le parti sommate fanno la differenza
  fra le due stime). E' una misura di cosa conta, non un ragionamento a parole.

Senza PyTorch (`rete_installa.bat`) o senza i pesi la rete non c'e' e il bot lavora come prima.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from nvm.agenti import foto
from nvm.agenti.cacciatore import Verso
from nvm.tempo import TF

PESI = Path(__file__).resolve().parent / "rete.pt"

NOMI_TF = {TF.H1: "1 ora", TF.H4: "4 ore", TF.H6: "6 ore", TF.D1: "giornaliero", TF.W1: "settimanale",
           TF.MN: "mensile"}
# Le domande degli occhi (`nvm/rete/etichette.DOMANDE`), in parole, con le loro risposte.
DIREZIONI = ("giù", "nessuna", "su")
LATI = ("niente", "acquisto", "vendita")
NOMI_DOMANDE = {"direzione D1": "Giorno", "direzione W1": "Settimana", "direzione MN": "Mese",
                "crt H4": "CRT 4 ore", "crt D1": "CRT del giorno", "setup H4": "Setup 4 ore",
                "setup D1": "Setup del giorno"}
# Le colonne della scheda (`kaggle_rete.esperienza.SCHEDA`) in parole.
NOMI_SCHEDA = {"vendita": "è una vendita", "stop": "quanto è largo lo stop", "tp1": "distanza del TP1",
               "target": "distanza del target finale", "rr tp1": "RR al TP1", "rr target": "RR al target finale",
               "key level": "key level preso", "direzione": "direzione a favore", "A+": "tutte le regole (A+)",
               "target gap": "target su un gap", "target key level": "target su un key level",
               "inside bar": "inside bar nel range"}
NOMI_GRAFICI = ("il grafico a 1 ora", "il grafico a 4 ore", "il grafico giornaliero", "il grafico settimanale",
                "il grafico mensile")

# Cosa si puo' correggere della rete con «Correggi», nell'ordine delle righe dei pulsanti: il trade e quello che
# vedono gli occhi (la direzione e i CRT; i "setup" degli occhi vengono da questi).
DA_CORREGGERE = (("trade", ("lasciare", "entrare")), ("direzione D1", DIREZIONI), ("direzione W1", DIREZIONI),
                 ("direzione MN", DIREZIONI), ("crt H4", LATI), ("crt D1", LATI))
NOMI_CORREZIONE = {"trade": "Il trade", **NOMI_DOMANDE}


def righe_correggi(ident: str, rete: dict) -> list:
    """Le righe dei pulsanti di «Correggi»: per ogni domanda le risposte possibili, quella della rete col punto."""
    righe = []
    for k, (nome, risposte) in enumerate(DA_CORREGGERE):
        sua = ("entrare" if rete.get("entra") else "lasciare") if nome == "trade" else \
            (rete.get("occhi", {}).get(nome) or [None])[0]
        titolo = NOMI_CORREZIONE.get(nome, nome)
        righe.append([(f"{'• ' if r == sua else ''}{titolo}: {r}", f"cr:{ident}:{k}:{j}")
                      for j, r in enumerate(risposte)])
    return righe


# In quante tappe si va dal setup tipico a questo, per misurare cosa pesa.
PASSI = 12
# Le cose che o ci sono o non ci sono: se mancano, si dice che mancano.
SI_NO = {"key level": "key level non preso", "direzione": "direzione non a favore", "A+": "non tutte le regole",
         "target gap": "target non su un gap", "target key level": "target non su un key level",
         "inside bar": "nessuna inside bar"}


def _nome_scheda(nome: str, valore: float) -> str:
    if nome in SI_NO and not valore:
        return SI_NO[nome]
    return NOMI_SCHEDA.get(nome, nome)


def _it(x: float, cifre: int = 2) -> str:
    return f"{x:+.{cifre}f}".replace(".", ",")


@dataclass
class Giudizio:
    """Il parere della rete su un setup."""

    entra: bool
    erre: float                 # R stimato a trade
    vince: float                # probabilita' di chiudere in guadagno
    soglia: float               # sopra questa stima la rete entra
    occhi: dict                 # domanda -> (risposta, probabilita')
    pesa: list                  # (cosa, quanto sposta la stima in R), dal piu' forte
    nuovo: str = ""             # se il setup e' di un tipo che la rete non ha mai visto
    esame: dict = field(default_factory=dict)
    # Quello che la rete ha visto (finestre, vuote, scheda): si salva con le correzioni, per riallenarla.
    ingressi: Optional[tuple] = field(default=None, repr=False)
    # Il setup ha tutte le regole delle foto (CRT, key level, direzione): allora la rete entra sempre.
    regole: bool = False

    def righe(self) -> list[str]:
        su = [f"{n} ({_it(v)} R)" for n, v in self.pesa if v > 0][:3]
        giu = [f"{n} ({_it(v)} R)" for n, v in self.pesa if v < 0][:3]
        occhi = [f"{NOMI_DOMANDE.get(k, k)}: {r} ({p:.0%})" for k, (r, p) in self.occhi.items()]
        if self.regole:
            fuori = ["🧠 LA RETE: ENTREREI. Il setup ha tutte le regole delle foto (CRT, key level, direzione): è un "
                     "trade da prendere, come quelli del proprietario.",
                     f"La mia stima sui vent'anni: {_it(self.erre)} R a trade, {self.vince:.0%} di chiudere in "
                     f"guadagno" + ("." if self.erre >= self.soglia else
                                     f" (sotto la mia soglia di {_it(self.soglia)} R: è solo un'informazione, "
                                     "decidono le regole delle foto).")]
        else:
            fuori = [f"🧠 LA RETE: {'ENTREREI' if self.entra else 'LASCEREI'}",
                     f"Stima {_it(self.erre)} R a trade, {self.vince:.0%} di chiudere in guadagno (entra da "
                     f"{_it(self.soglia)} R: i setup del bot che preferisce)."]
        if occhi:
            fuori.append("Gli occhi vedono: " + "; ".join(occhi) + ".")
        if su or giu:
            fuori.append("Rispetto a un setup tipico del bot:")
        if su:
            fuori.append("• la spinge: " + ", ".join(su) + ".")
        if giu:
            fuori.append("• la frena: " + ", ".join(giu) + ".")
        if self.nuovo:
            fuori.append(self.nuovo)
        return fuori

    def dati(self) -> dict:
        return {"entra": self.entra, "regole": self.regole, "erre": round(self.erre, 4), "vince": round(self.vince, 4),
                "soglia": round(self.soglia, 4), "occhi": {k: [r, round(p, 3)] for k, (r, p) in self.occhi.items()},
                "pesa": [[n, round(v, 4)] for n, v in self.pesa[:6]]}


class Rete:
    """La rete allenata, pronta a giudicare. `carica` la prende da `rete.pt`."""

    def __init__(self, rete, soglia: float, esame: dict, base_scheda=None):
        self.rete = rete
        self.soglia = soglia
        self.esame = esame
        self.base_scheda = None if base_scheda is None else np.asarray(base_scheda, np.float32)

    @classmethod
    def carica(cls, percorso: Path = PESI) -> tuple[Optional["Rete"], str]:
        """(la rete, '') oppure (None, perche' non c'e'). Non solleva mai: una rete che non parte non ferma il bot."""
        try:
            return cls._carica(percorso)
        except Exception as errore:
            return None, f"la rete non si carica ({type(errore).__name__}: {str(errore)[:150]})"

    @classmethod
    def _carica(cls, percorso: Path) -> tuple[Optional["Rete"], str]:
        try:
            import torch
        except ImportError:
            return None, "manca PyTorch sulla VPS: fai doppio clic su rete_installa.bat, poi riavvia il bot"
        except OSError:
            # Su Windows (WinError 1114, c10.dll): manca o e' vecchio il Visual C++ di Microsoft che PyTorch usa.
            return None, ("PyTorch è installato ma Windows non lo fa partire: manca il pacchetto Visual C++ di "
                          "Microsoft. Scarica e installa https://aka.ms/vs/17/release/vc_redist.x64.exe, poi "
                          "riavvia la VPS e il bot")
        if not percorso.exists():
            return None, f"mancano i pesi della rete ({percorso.name})"
        from kaggle_rete.esperienza import SCHEDA
        from kaggle_rete.trader import Trader
        from nvm.rete.modello import Occhi
        pacco = torch.load(percorso, map_location="cpu", weights_only=True)
        torch.set_num_threads(2)
        rete = Trader(Occhi(**pacco["forma"]), len(SCHEDA))
        rete.load_state_dict({k: v.float() if v.is_floating_point() else v for k, v in pacco["pesi"].items()})
        rete.eval()
        return cls(rete, float(pacco["soglia"]), dict(pacco.get("esame", {})), pacco.get("base_scheda")), ""

    @staticmethod
    def ingressi(d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Quello che la rete vede del setup `d` (una decisione del metodo delle foto): le finestre del grafico
        all'apertura della candela 3 e la scheda, calcolata come nello studio (`kaggle_rete.esperienza.casi`)."""
        from kaggle_rete.esperienza import SCHEDA, _kl_ok, _scala
        from nvm.rete.finestre import TF_RETE, Storia, finestre
        info = d.foto
        s, q, ob = info["setup"], info["quadro"], info["obiettivo"]
        n3 = int(s.n3_inizio)
        st = Storia(s.strumento, {tf: q.candele[tf] for tf in TF_RETE})
        x, v = finestre(st, np.array([n3], np.int64))
        sc = _scala(q.candele[TF.D1], n3)
        if not np.isfinite(sc) or sc <= 0:
            raise ValueError("il range medio del giorno non si calcola")
        ingresso = s.ingresso
        rischio = abs(ingresso - s.stop)
        if rischio <= 0:
            raise ValueError("stop sull'entrata")
        dz = foto.direzione(q, s)
        kl, ok = _kl_ok(s), bool(dz.ok)
        riga = [float(s.tf is tf) for tf in foto.TF_CRT] + [
            float(s.verso is Verso.SHORT), rischio / sc, abs(s.tp1 - ingresso) / sc, abs(ob.prezzo - ingresso) / sc,
            abs(s.tp1 - ingresso) / rischio, abs(ob.prezzo - ingresso) / rischio, float(kl), float(ok),
            float(kl and ok), float(ob.tipo == "gap"), float(ob.tipo == "key level"), float(getattr(s, "dentro", 0))]
        assert len(riga) == len(SCHEDA)
        return x, v, np.array([riga], np.float32)

    def giudica(self, d) -> Giudizio:
        import torch
        from kaggle_rete.esperienza import SCHEDA
        from kaggle_rete.trader import prepara_scheda, tf_rete
        from nvm.rete.etichette import DOMANDE
        x, v, grezza = self.ingressi(d)
        scheda = prepara_scheda(grezza)
        quale = torch.from_numpy(tf_rete(grezza))
        xt = torch.from_numpy(x).float()
        st = torch.from_numpy(scheda).float()
        vt = torch.from_numpy(v)
        with torch.no_grad():
            r, logit = self.rete(xt, vt, st, quale)
        erre, vince = float(r.item()), float(torch.sigmoid(logit).item())
        # Quanto sposta la stima ogni cosa che la rete guarda, rispetto a un setup tipico del bot sullo stesso
        # timeframe e nello stesso verso, e a un grafico piatto (gradienti integrati, `PASSI` tappe).
        base = st.clone()
        if self.base_scheda is not None:
            fisse = [k for k, n in enumerate(SCHEDA) if n.startswith("tf ") or n == "vendita"]
            b = torch.from_numpy(self.base_scheda).float()[None]
            b[:, fisse] = st[:, fisse]
            base = b
        somma_s, somma_x = torch.zeros_like(st), torch.zeros_like(xt)
        for a in (np.arange(PASSI) + 0.5) / PASSI:
            xi = (a * xt).requires_grad_(True)
            si = (base + a * (st - base)).requires_grad_(True)
            ri, _ = self.rete(xi, vt, si, quale)
            gx, gs = torch.autograd.grad(ri.sum(), (xi, si))
            somma_x += gx
            somma_s += gs
        pesa = []
        contributi = ((st - base) * somma_s / PASSI).numpy()[0]
        for k, nome in enumerate(SCHEDA):
            if nome.startswith("tf "):
                if grezza[0, k]:
                    tf = foto.TF_CRT[k]
                    pesa.append((f"il CRT {NOMI_TF.get(tf, tf.value)}", float(contributi[k])))
                continue
            if nome != "vendita":
                pesa.append((_nome_scheda(nome, grezza[0, k]), float(contributi[k])))
        grafici = (xt * somma_x / PASSI).sum(dim=(2, 3)).numpy()[0]
        pesa += [(NOMI_GRAFICI[i], float(g)) for i, g in enumerate(grafici)]
        pesa = [p for p in pesa if abs(p[1]) >= 0.005]
        pesa.sort(key=lambda p: -abs(p[1]))
        # Cosa vedono gli occhi.
        occhi = {}
        with torch.no_grad():
            riassunto, candele = self.rete.occhi(xt, vt)
            for (nome, _), logits in zip(DOMANDE, self.rete.occhi.rispondi(riassunto, candele)):
                p = torch.softmax(logits[0], dim=-1).numpy()
                k = int(np.argmax(p))
                occhi[nome] = ((DIREZIONI if nome.startswith("direzione") else LATI)[k], float(p[k]))
        s = d.foto["setup"]
        nuovo = ""
        if getattr(s, "dal_dxy", False) or getattr(s, "dal_totale", False):
            nuovo = (f"⚠️ Setup preso dal {'DXY' if s.dal_dxy else 'grafico della TOTAL'}: nello studio la rete "
                     "non ne ha mai visti, prendi il suo parere con le pinze.")
        # Sugli strumenti guidati le regole le da' il CRT del DXY (della TOTAL), non lo strumento: la rete non lo lascia
        # (il proprietario, 20/10/2026: *"solo ed esclusivamente quando il dxy da il pattern"*; il 21/10 lasciava in
        # équipe i setup di BTC ed ETH nati dal CRT della TOTAL, che nello studio non ha mai visto).
        regole = bool(grezza[0, SCHEDA.index("A+")]) or bool(nuovo)
        return Giudizio(regole or erre >= self.soglia, erre, vince, self.soglia, occhi, pesa, nuovo, self.esame,
                        (x, v, grezza), regole=regole)
