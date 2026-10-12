"""Il giro di ogni ora: con le orarie chiuse fino ad adesso, cosa dice l'equipe.

E' la stessa catena delle prove sullo storico (`nvm/prova/base.opera`, con la
configurazione 1: manuale, stop all'estremo), chiamata sui soli dati gia'
chiusi. Per questo il bot dal vivo decide come avrebbe deciso sullo storico:
`tests/test_vivo.py` lo controlla ora per ora.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from nvm.agenti import foto
from nvm.agenti.cacciatore import CRT, Variante, Verso, caccia
from nvm.agenti.grilletto import Scatto
from nvm.agenti.capo import Capo, riga
from nvm.agenti.conferme import SOPRA, AllaRomeo, Contesto, KeyLevel, Liquidita, Orario, tutti_i_pareri
from nvm.agenti.livelli import piani_romeo, piano, scadenza
from nvm.dati.candele import costruisci
from nvm.dati.minuti import Minuti
from nvm.prova.base import Risultato, opera, opera_candela_3
from nvm.prova.campo import COMMISSIONE, Operazione, Uscita
from nvm.agenti import capo as capo_mod, inventate, manopole, panorama
from nvm.agenti.conferme import GRANDEZZA, Grandi
from nvm.cervello.piani import tutti as piani_di
from nvm.cervello.viste import COMPAGNI, viste
from nvm.tempo import NEW_YORK, ORDINE, TF

# Le coppie che si guardano con le orarie, ogni ora.
COPPIE = ((TF.MN, TF.D1), (TF.W1, TF.H4), (TF.D1, TF.H1))
# La quarta coppia di Romeo si guarda con i quarti d'ora di MT5, ogni quarto d'ora.
COPPIA_VELOCE = (TF.H4, TF.M15)
# Come nascono le occasioni: "foto" e' il metodo delle foto del proprietario (`spec/metodo_foto.md`, dal
# 06/10/2026: entrata all'apertura della candela 3, stop oltre la 2, TP1 l'altro lato del range, target finale
# il gap o il key level); "candela 3" il metodo dei video (`spec/metodo_romeo.md`); "model1" quello di prima.
METODO = "foto"
# Fino a quando si segue un'occasione del metodo delle foto sulla carta, per timeframe del CRT: i target finali
# sono gap e key level dei timeframe grandi, possono servire mesi.
TETTO_FOTO = {TF.H1: 10 * 86400, TF.H4: 30 * 86400, TF.H6: 40 * 86400, TF.D1: 90 * 86400,
              TF.W1: 300 * 86400, TF.MN: 800 * 86400}


@dataclass
class Decisione:
    r: Risultato
    op: Operazione
    scadenza: int
    key_level: Optional[KeyLevel]
    orario: Orario
    contesto: Optional[Contesto]
    p1: float
    q: float
    atteso: float
    # Le colonne del Capo per questa decisione: servono al riaddestramento.
    x: np.ndarray
    # Le risposte alla Romeo, e quanto il Capo pensa che somigli a una sua
    # entrata: un parere per l'equipe, non un obbligo.
    alla_romeo: Optional[AllaRomeo] = None
    romeo: Optional[float] = None
    # La somiglianza di un candidato medio, per dire se questa e' sopra o sotto.
    romeo_medio: Optional[float] = None
    # La risposta del Grilletto sulla liquidita' presa dalla manipolazione.
    liquidita: Optional[Liquidita] = None
    # Cosa vedono Allineamento e Gap dai timeframe grandi.
    sguardo: Optional[panorama.Sguardo] = None
    # La qualita' attesa: il guadagno atteso diviso per quanto l'operazione puo' oscillare.
    qualita: Optional[float] = None
    # Cosa vedeva ogni agente (`nvm/cervello/viste.py`): lo giudicano i loro cervelli.
    viste: Optional[dict] = None
    # Le operazioni di tutti i piani fra cui i cervelli scelgono (`nvm/cervello/piani.py`).
    piani: Optional[list] = None
    # Su quante grandezze piu' grandi c'e' un CRT armato contro e nello stesso verso (la direzione del
    # grafico grande per il metodo dei video).
    grandi_contro: int = 0
    grandi_con: int = 0
    # I piani di Livelli per la squadra, tutti come li vuole Romeo (`livelli.PIANI_ROMEO`).
    piani_romeo: Optional[list] = None
    # Il metodo delle foto: il setup, il quadro dei timeframe, il target finale, il setup del DXY.
    foto: Optional[dict] = None

    @property
    def entra(self) -> bool:
        """Il Capo entra quando la qualita' attesa supera la sua soglia (`nvm/agenti/capo.py`)."""
        if self.qualita is None:
            return self.atteso > 0
        return self.qualita > capo_mod.SOGLIA

    @property
    def chiave(self) -> str:
        # Due CRT uno dentro l'altro possono scattare sullo stesso turtle soup: sono due decisioni,
        # e le distingue l'inizio del range.
        r = self.r
        crt = f" crt {r.scatto.crt.range_inizio}" if r.scatto is not None else ""
        return f"{r.strumento} {r.alto_tf.value}-{r.basso_tf.value} {r.verso.value} {r.quando} colpo {r.colpo}{crt}"


# Le candele e i CRT gia' costruiti: il bot li rifarebbe uguali a ogni giro e a
# ogni quarto d'ora. Si riusano finche' le candele di base sono le stesse.
_MEMORIA: dict = {}
_MEMORIA_MASSIMA = 256


def _ricorda(chiave, fai):
    if chiave not in _MEMORIA:
        if len(_MEMORIA) >= _MEMORIA_MASSIMA:
            _MEMORIA.pop(next(iter(_MEMORIA)))
        _MEMORIA[chiave] = fai()
    return _MEMORIA[chiave]


def _impronta(base: Minuti) -> tuple:
    """Le candele di base sono le stesse se hanno lo stesso strumento, passo, numero, inizio, fine e ultima chiusura."""
    return (base.strumento, base.passo, len(base), int(base.t[0]), int(base.t[-1]), int(base.bid[-1, 3]))


def _candele(base: Minuti, tf: TF, adesso: int):
    return _ricorda(("candele", _impronta(base), tf, adesso), lambda: costruisci(base, tf).chiuse_entro(adesso))


def _crt(base: Minuti, alto: TF, basso: TF, adesso: int):
    return _ricorda(("crt", _impronta(base), alto, basso, adesso, manopole.impronta()),
                    lambda: caccia(_candele(base, alto, adesso), _candele(base, basso, adesso)))


def _crt3(base: Minuti, alto: TF, basso: TF, adesso: int):
    """I CRT del metodo dei video: la candela 2 ha fatto la finta e ha chiuso dentro."""
    return _ricorda(("crt3", _impronta(base), alto, basso, adesso),
                    lambda: caccia(_candele(base, alto, adesso), _candele(base, basso, adesso), Variante.CHIUSURA_DENTRO))


def _occasioni(alte, basse, base, alto, basso, dal, adesso, metodo, orarie=None):
    if metodo == "candela 3":
        return opera_candela_3(alte, basse, dal, adesso + 1, trovati=_crt3(base, alto, basso, adesso), orarie=orarie)
    return opera(alte, basse, dal, adesso + 1, trovati=_crt(base, alto, basso, adesso))


def _grandi3(ore: Minuti, adesso: int):
    """I CRT confermati (candela 2 chiusa dentro) delle coppie, ancora in viaggio verso l'obiettivo: la
    direzione del grafico grande per il metodo dei video (V16 01:43, V10 13:43)."""
    return _ricorda(("grandi3", _impronta(ore), adesso),
                    lambda: Grandi.da([c for alto, basso in COPPIE for c in _crt3(ore, alto, basso, adesso)]))


def _grandi(ore: Minuti, adesso: int):
    """I CRT delle coppie sulle ore, per "dentro un CRT piu' grande?": gli stessi del giro orario."""
    return _ricorda(("grandi", _impronta(ore), adesso, manopole.impronta()),
                    lambda: Grandi.da([c for alto, basso in COPPIE for c in _crt(ore, alto, basso, adesso)]))


def _viste(r, alte, basse, sopra, settimane, x, grandi=None, compagno=None, quadro=None) -> Optional[dict]:
    """Quello che vede ogni agente; se qualcosa non torna, niente viste (decide il Capo come sempre)."""
    try:
        return viste(r, alte, basse, sopra, settimane, x, grandi, compagno, quadro)
    except Exception:
        return None


def _compagno(strumento: str, gemelli: Optional[dict], orarie: dict):
    """Le ore dello strumento gemello per l'SMT (`viste.COMPAGNI`), se il bot le ha."""
    gemello = COMPAGNI.get(strumento)
    if not gemello:
        return None
    ore = (gemelli or orarie).get(gemello[0])
    return (ore, gemello[1]) if ore is not None else None


def _piani_romeo(r, basse) -> Optional[list]:
    try:
        return piani_romeo(r.scatto, basse)
    except Exception:
        return None


def _piani(r, basse) -> Optional[list]:
    try:
        return piani_di(r.scatto, basse)
    except Exception:
        return None


def giro(basi: dict[str, Minuti], dal: int, adesso: int, capo: Capo, coppie=COPPIE,
         orarie: Optional[dict[str, Minuti]] = None, gemelli: Optional[dict[str, Minuti]] = None,
         metodo: Optional[str] = None, lunghe: Optional[dict[str, Minuti]] = None) -> list[Decisione]:
    """Le decisioni con lo scatto in [dal, adesso], su candele chiuse entro `adesso`.

    `orarie` sono le ore di ogni strumento, se `basi` sono i quarti d'ora: da
    li' vengono il timeframe sopra, la settimana e i CRT piu' grandi. `lunghe`: le giornaliere di tanti anni
    (per i 3, 6 e 12 mesi del metodo delle foto).
    """
    orarie = basi if orarie is None else orarie
    metodo = METODO if metodo is None else metodo
    if metodo == "foto":
        decisioni = []
        for strumento, base in basi.items():
            ore = orarie.get(strumento, base)
            if ore.passo > 3600:
                continue
            decisioni += occasioni_foto(strumento, ore, dal, adesso, capo, gemelli or orarie,
                                        (lunghe or {}).get(strumento), (lunghe or {}).get("DXY"),
                                        (lunghe or {}).get("TOTAL"))
        decisioni.sort(key=lambda d: (d.r.quando, d.r.strumento))
        return decisioni
    decisioni = []
    for strumento, base in basi.items():
        ore = orarie.get(strumento, base)
        if not len(base) or not len(ore):
            continue
        # Le ore cambiano una volta l'ora: fino ad allora i CRT grandi e la settimana sono gli stessi.
        fine_ore = min(adesso, int(ore.t[-1]) + ore.passo)
        g = _grandi(ore, fine_ore)
        g3 = _grandi3(ore, fine_ore)
        settimane = _candele(ore, TF.W1, fine_ore)
        idee = capo_mod.INVENTATE
        # Le candele grandi: per Allineamento e Gap, e per le domande inventate.
        ctx_idee = _ricorda(("idee", _impronta(ore), fine_ore, manopole.impronta()),
                            lambda: inventate.Contesto.da(ore, fine_ore, g))
        for alto, basso in coppie:
            alte = _candele(base, alto, adesso)
            basse = _candele(base, basso, adesso)
            sopra = _candele(ore, SOPRA[alto], fine_ore)
            ore_h1 = _candele(ore, TF.H1, fine_ore) if ore.passo <= 3600 else None
            for r in _occasioni(alte, basse, base, alto, basso, dal, adesso, metodo, ore_h1):
                op = piano(r.scatto, basse)
                kl, ora, ctx, ar, liq = tutti_i_pareri(r.scatto, alte, basse, sopra, settimane, g)
                x = riga(r, kl, ora, ctx, ar, liq, inventate.rispondi_tutte(idee, r, ctx_idee))[None]
                p1, q = capo.probabilita(x)
                atteso = capo.valore_atteso(x, np.array([r.rr1]), np.array([r.rr2]), np.array([r.costo_erre]))
                decisioni.append(Decisione(
                    r, op, scadenza(r.scatto), kl, ora, ctx, float(p1[0]), float(q[0]), float(atteso[0]), x[0],
                    ar, float(capo.somiglianza(x)[0]) if capo.romeo is not None else None,
                    float(1 / (1 + np.exp(-capo.romeo_logit_media))) if capo.romeo is not None else None, liq,
                    panorama.sguardo(r, ctx_idee),
                    float(capo_mod.qualita_attesa(p1[0], q[0], r.rr1, r.rr2, r.costo_erre)),
                    _viste(r, alte, basse, sopra, settimane, x[0], g, _compagno(strumento, gemelli, orarie), ctx_idee),
                    _piani(r, basse),
                    g3.livelli(Verso.LONG if r.verso is Verso.SHORT else Verso.SHORT, GRANDEZZA.get(alto, 0), r.quando),
                    g3.livelli(r.verso, GRANDEZZA.get(alto, 0), r.quando),
                    _piani_romeo(r, basse)))
    decisioni.sort(key=lambda d: (d.r.quando, d.r.strumento))
    return decisioni


# --- il metodo delle foto (`nvm/agenti/foto.py`) ----------------------------------------------------------

# I quadri dei timeframe pesano qualche MB l'uno: se ne tengono pochi (il DXY si riusa per tutte le coppie
# col dollaro nello stesso giro).
_QUADRI: dict = {}
_QUADRI_MASSIMI = 12


def _ricorda_quadro(chiave, fai):
    if chiave not in _QUADRI:
        if len(_QUADRI) >= _QUADRI_MASSIMI:
            _QUADRI.pop(next(iter(_QUADRI)))
        _QUADRI[chiave] = fai()
    return _QUADRI[chiave]


def _quadro(ore: Minuti, adesso: int, lunghe: Optional[Minuti] = None):
    return _ricorda_quadro(("quadro", _impronta(ore), adesso,
                            None if lunghe is None or not len(lunghe) else _impronta(lunghe)),
                           lambda: foto.Quadro.da(ore, adesso, lunghe))


def _dxy(gemelli: Optional[dict], adesso: int, lunghe: Optional[Minuti] = None, nome: str = "DXY"):
    """Il quadro del DXY: il grafico del broker (su FP Markets USDX), sotto la chiave "DXY" di `gemelli`. Non si
    calcola piu' dalle coppie (il proprietario, 08/10/2026): se il grafico non c'e', il DXY non c'e'. Con `nome`
    "TOTAL", la TOTAL di TradingView per le crypto."""
    m = (gemelli or {}).get(nome)
    if m is None or len(m) < 200:
        return None
    return _quadro(m, adesso, lunghe)


def setup_buono(s) -> bool:
    """Il CRT a 1 ora vale solo se ha preso il key level giornaliero e il massimo (minimo) a 4 ore: *"se il
    prezzo prende kl daily e sbilancia un max minimo h4 e si forma un crt h1"* (il proprietario, 06/10/2026)."""
    if s.tf is not TF.H1:
        return True
    return s.h4_preso is not None and any(l.tf is TF.D1 and not l.oggi for l in s.presi)


def piani_foto(s, ob, altro, quando: int) -> list:
    """I piani di Livelli, nell'ordine di `foto.PIANI`: tutto al TP1; il 25% al TP1 e il resto al target finale
    (quello delle foto, di partenza); il 25% al TP1 e il resto al target dopo. None se non si puo' fare, o se al suo
    ultimo target non rende almeno `foto.RR_MINIMO` volte il rischio."""
    fuori = []
    rischio = abs(s.ingresso - s.stop)
    for parziale, tp2 in ((1.0, s.tp1), (foto.PARZIALE, ob.prezzo), (foto.PARZIALE, None if altro is None else altro.prezzo)):
        if tp2 is None or (parziale < 1.0 and tp2 == s.tp1) or not rischio or \
                abs(tp2 - s.ingresso) < foto.RR_MINIMO * rischio - 1e-12:
            fuori.append(None)
            continue
        try:
            fuori.append(Operazione(s.strumento, s.verso, quando, s.ingresso, s.stop, s.tp1, tp2,
                                    parziale=parziale, pareggio=parziale < 1.0))
        except ValueError:
            fuori.append(None)
    return fuori


def _decisione_foto(s, q, capo: Capo, dxy=None, allineati=(), quadro_dxy=None, totale=None,
                    quadro_totale=None) -> Optional[Decisione]:
    """Il setup delle foto come `Decisione`, con gli stessi oggetti che il resto del bot usa gia'."""
    ob = foto.obiettivo_finale(q, s)
    altro = foto.target_dopo(q, s, ob)
    piani = piani_foto(s, ob, altro, s.n3_inizio)
    op = piani[1] or piani[0]
    if op is None:
        return None
    crt = s.crt(TF.H1)
    ore = q.ore
    indice = min(int(np.searchsorted(ore.inizio, s.n3_inizio)), max(len(ore) - 1, 0))
    scatto = Scatto(crt, s.n3_inizio, indice, s.tp1, s.n2_inizio, s.n2_alto, s.n2_basso,
                    modello="dal DXY" if s.dal_dxy else "dalla TOTAL" if s.dal_totale else "apertura N3",
                    punta=s.n2_alto if s.short else s.n2_basso,
                    apertura_3=s.entrata)
    rischio = op.rischio
    costo = COMMISSIONE.get(s.strumento, 0.0) / rischio if rischio > 0 else 0.0
    r = Risultato(s.strumento, s.tf, TF.H1, s.verso, s.n3_inizio, 0.0, Uscita.SCADUTA, False, costo, rischio, scatto,
                  colpo=1, rr1=abs(op.tp1 - op.ingresso) / rischio, rr2=abs(op.tp2 - op.ingresso) / rischio,
                  stop_su_ampiezza=rischio / max(s.range_alto - s.range_basso, 1e-12), chiusa_quando=0,
                  ingresso=op.ingresso, stop=op.stop)
    ora = Orario(int(datetime.fromtimestamp(s.n3_inizio, tz=NEW_YORK).hour),
                 int(datetime.fromtimestamp(s.n2_inizio, tz=NEW_YORK).hour))
    x = np.zeros(len(capo.media)) if getattr(capo, "media", None) is not None else np.zeros(1)
    return Decisione(r, op, s.n3_inizio + TETTO_FOTO.get(s.tf, 30 * 86400), None, ora, None, 0.5, 0.0, 0.0, x,
                     piani_romeo=piani,
                     foto={"setup": s, "quadro": q, "obiettivo": ob, "dopo": altro, "dxy": dxy, "quadro_dxy": quadro_dxy,
                           "totale": totale, "quadro_totale": quadro_totale,
                           "allineati": list(allineati)})


def occasioni_foto(strumento: str, ore: Minuti, dal: int, adesso: int, capo: Capo,
                   gemelli: Optional[dict] = None, lunghe: Optional[Minuti] = None,
                   lunghe_dxy: Optional[Minuti] = None, lunghe_totale: Optional[Minuti] = None) -> list[Decisione]:
    """Le occasioni del metodo delle foto con la candela 3 che apre in [dal, adesso], su uno strumento.

    Se piu' timeframe danno lo stesso verso alla stessa apertura, l'occasione e' una (quella del timeframe
    piu' grande) e gli altri sono i "timeframe allineati". Sulle coppie col dollaro anche i setup del DXY
    (*"se lui ci forma un setup long possiamo shortare tutte le coppie ... con il dollaro al denominatore"*)."""
    if not len(ore):
        return []
    q = _quadro(ore, adesso, lunghe)
    trovati = [s for tf in foto.TF_CRT for s in foto.trova(q, tf, dal, adesso) if setup_buono(s)]
    qd = _dxy(gemelli, adesso, lunghe_dxy) if strumento in foto.DOLLARO_SOTTO + foto.DOLLARO_SOPRA else None
    dxy_setup = []
    if qd is not None:
        dxy_setup = [s for tf in foto.TF_CRT for s in foto.trova(qd, tf, dal, adesso) if setup_buono(s)]
        for sd in dxy_setup:
            if not sd.presi:
                continue
            gia = any(s.tf is sd.tf and s.n3_inizio == sd.n3_inizio for s in trovati)
            # Un setup del DXY ne fa uno sulla coppia solo sul forex (correlazione piena): oro e indici a volte vanno
            # con il dollaro, li' il DXY da' solo il parere.
            if not gia and strumento in foto.FOREX_DOLLARO:
                x = foto.dal_dxy(q, sd)
                if x is not None:
                    trovati.append(x)
    # Le crypto con la TOTAL (il proprietario, 12/10/2026): un suo setup fa entrare su BTC ed ETH dalla stessa parte.
    qt = _dxy(gemelli, adesso, lunghe_totale, "TOTAL") if strumento in foto.CRYPTO_TOTALE else None
    tot_setup = []
    if qt is not None:
        tot_setup = [s for tf in foto.TF_CRT for s in foto.trova(qt, tf, dal, adesso) if setup_buono(s)]
        for st in tot_setup:
            if not st.presi or any(s.tf is st.tf and s.n3_inizio == st.n3_inizio for s in trovati):
                continue
            x = foto.dal_totale(q, st)
            if x is not None:
                trovati.append(x)
    # Una sola occasione per apertura e verso: quella del timeframe piu' grande.
    gruppi: dict = {}
    for s in trovati:
        gruppi.setdefault((s.n3_inizio, s.verso), []).append(s)
    decisioni = []
    for (n3, verso), gruppo in sorted(gruppi.items(), key=lambda g: g[0][0]):
        gruppo.sort(key=lambda s: -ORDINE.index(s.tf))
        s = gruppo[0]
        qq = q.taglia(s.n3_inizio) if s.n3_inizio < adesso else q
        stessi = [x.tf for x in gruppo[1:]]
        dxy = next((sd for sd in dxy_setup if sd.tf is s.tf and sd.n3_inizio == s.n3_inizio), None)
        totale = next((st for st in tot_setup if st.tf is s.tf and st.n3_inizio == s.n3_inizio), None)
        try:
            d = _decisione_foto(s, qq, capo, dxy, stessi, qd, totale, qt)
        except Exception:
            d = None
        if d is not None:
            decisioni.append(d)
    return decisioni


def armati(basi: dict[str, Minuti], dal: int, adesso: int, coppie=COPPIE) -> list[CRT]:
    """I CRT che il Cacciatore ha visto armarsi in [dal, adesso]."""
    trovati = []
    for base in basi.values():
        if not len(base):
            continue
        for alto, basso in coppie:
            trovati += [c for c in _crt(base, alto, basso, adesso) if dal <= c.armato_quando <= adesso]
    trovati.sort(key=lambda c: (c.armato_quando, c.strumento))
    return trovati
