"""La strategia del libro del socio (`spec/metodo_libro.md`): struttura, inducement, EPA, MSU.

Le tre regole, sempre tutte e in quest'ordine (libro, cap. 2.4): **presa di inducement**, **prezzo in zona di
EPA**, **MSU** come conferma e ingresso. Stop sotto la EPA (sopra in short), obiettivo il massimo (minimo) della
struttura. Tutto sulle sole candele gia' chiuse; i prezzi sono il bid, come sui grafici.

Le scelte vengono dal libro (le pagine in `spec/metodo_libro.md`); dove il libro lascia fare all'occhio, qui
c'e' una costante dichiarata, da tarare sui vent'anni:
- un massimo (minimo) conta se e' il piu' alto (basso) di `LATO` candele per parte (`punti`);
- la struttura si rompe con una **chiusura** oltre il punto (`struttura`);
- la EPA va dal punto A al massimo dell'ultima candela ribassista fino ad A (l'ultimo sell prima del buy);
- l'MSU si legge un timeframe sotto: presa di un minimo piccolo e chiusura sopra il massimo di prima (`msu`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nvm.dati.candele import Candele
from nvm.dati.minuti import APERTURA, CHIUSURA, MASSIMO, MINIMO

# Quante candele per parte deve battere un massimo (minimo) per contare: il libro li segna a occhio (p58).
LATO = 2
# Quante candele prima di A si cerca l'ultima candela ribassista (rialzista in short) della EPA.
EPA_INDIETRO = 5

# I cambi della struttura, candela per candela.
NIENTE, ROTTURA_SU, ROTTURA_GIU, CAMBIO_SU, CAMBIO_GIU = 0, 1, -1, 2, -2


def punti(alti: np.ndarray, bassi: np.ndarray, lato: int = LATO) -> tuple[np.ndarray, np.ndarray]:
    """I massimi e i minimi: `massimo[i]` vero se la candela i batte le `lato` prima (strettamente) e le `lato`
    dopo (o le pareggia: di due massimi uguali conta il primo). Si sa solo alla chiusura della candela i+lato."""
    n = len(alti)
    massimo = np.zeros(n, bool)
    minimo = np.zeros(n, bool)
    for i in range(lato, n - lato):
        prima_a, dopo_a = alti[i - lato:i], alti[i + 1:i + lato + 1]
        prima_b, dopo_b = bassi[i - lato:i], bassi[i + 1:i + lato + 1]
        massimo[i] = alti[i] > prima_a.max() and alti[i] >= dopo_a.max()
        minimo[i] = bassi[i] < prima_b.min() and bassi[i] <= dopo_b.min()
    return massimo, minimo


@dataclass
class Struttura:
    """La struttura esterna com'era alla chiusura di ogni candela (array lunghi come le candele).

    In rialzo (`verso` +1): `a` e' il punto A, il minimo da cui e' partita l'ultima rottura (una chiusura sotto e
    la struttura cambia); `b` e' il punto B, il massimo raggiunto dopo A; `idm` e' l'inducement, l'ultimo minimo
    (dei massimi e minimi piccoli) che ha generato B. Finche' l'inducement non e' preso B si sposta col prezzo;
    preso l'inducement (`idm_preso`), B resta fermo e siamo nel ritracciamento: la chiusura oltre B e' la
    rottura (BOS) e il minimo del ritracciamento diventa il nuovo A (libro p95-96: *"solo dopo la presa
    dell'Inducement, il mercato può fornire un segnale valido"*). `epa_alto` e' il lato della EPA lontano da A
    (A e' l'altro lato). In ribasso lo specchio. `cambio` dice cosa e' successo su quella candela; `rotture`
    quante rotture nello stesso verso dalla nascita della struttura.
    """
    verso: np.ndarray
    a: np.ndarray
    a_i: np.ndarray
    b: np.ndarray
    b_i: np.ndarray
    idm: np.ndarray
    idm_preso: np.ndarray
    epa_alto: np.ndarray
    cambio: np.ndarray
    rotture: np.ndarray


def _epa(aperture: np.ndarray, chiusure: np.ndarray, alti: np.ndarray, bassi: np.ndarray, a_i: int,
         verso: int) -> float:
    """Il lato lontano della EPA: l'ultimo sell prima del buy (in long: l'ultima candela ribassista fino ad A)."""
    for j in range(a_i, max(-1, a_i - EPA_INDIETRO - 1), -1):
        if verso > 0 and chiusure[j] < aperture[j]:
            return float(alti[j])
        if verso < 0 and chiusure[j] > aperture[j]:
            return float(bassi[j])
    return float(alti[a_i] if verso > 0 else bassi[a_i])


def struttura(c: Candele, lato: int = LATO) -> Struttura:
    """Una passata sulle candele chiuse. I massimi e minimi piccoli (`punti`) danno l'inducement; la struttura
    esterna cambia con una chiusura oltre A (CHoCH) e si rompe con una chiusura oltre B dopo l'inducement (BOS)."""
    ap, al, ba, ch = (c.bid[:, k].astype(np.float64) for k in (APERTURA, MASSIMO, MINIMO, CHIUSURA))
    n = len(c)
    mx, mn = punti(al, ba, lato)
    fuori = {k: np.full(n, np.nan) for k in ("a", "b", "idm", "epa_alto")}
    verso_v, a_iv, b_iv = np.zeros(n, int), np.full(n, -1), np.full(n, -1)
    preso_v, cambio, rotture_v = np.zeros(n, bool), np.zeros(n, int), np.zeros(n, int)

    verso, rotture = 0, 0
    a = b = idm = np.nan
    a_i = b_i = -1
    preso = False
    massimi: list[int] = []
    minimi: list[int] = []

    def nasce(v: int, i: int, da: int) -> None:
        """La struttura nuova nel verso v: A e' l'estremo opposto fra `da` e i, B il prezzo di adesso."""
        nonlocal verso, a, a_i, b, b_i, idm, preso
        if v > 0:
            j = da + int(np.argmin(ba[da:i + 1]))
            a, b = float(ba[j]), float(al[i])
        else:
            j = da + int(np.argmax(al[da:i + 1]))
            a, b = float(al[j]), float(ba[i])
        verso, a_i, b_i, idm, preso = v, j, i, np.nan, False

    for i in range(n):
        k = i - lato  # il punto piccolo che si conferma adesso
        if k >= 0:
            if mx[k]:
                massimi.append(k)
            if mn[k]:
                minimi.append(k)
        evento = NIENTE
        if verso == 0:
            # La prima struttura: una chiusura oltre l'ultimo massimo (minimo) piccolo.
            if massimi and ch[i] > al[massimi[-1]]:
                nasce(1, i, massimi[-1])
                rotture, evento = 1, CAMBIO_SU
            elif minimi and ch[i] < ba[minimi[-1]]:
                nasce(-1, i, minimi[-1])
                rotture, evento = 1, CAMBIO_GIU
        elif (ch[i] - a) * verso < 0:
            # Chiusura oltre A: la struttura cambia; il nuovo A e' B (l'estremo da cui si e' girati).
            v = -verso
            nasce(v, i, b_i)
            rotture, evento = 1, CAMBIO_SU if v > 0 else CAMBIO_GIU
        elif preso and (ch[i] - b) * verso > 0:
            # Chiusura oltre B dopo l'inducement: rottura; il nuovo A e' l'estremo del ritracciamento.
            nasce(verso, i, b_i)
            rotture, evento = rotture + 1, ROTTURA_SU if verso > 0 else ROTTURA_GIU
        elif not preso:
            # Prima dell'inducement B segue il prezzo.
            if verso > 0 and al[i] > b:
                b, b_i = float(al[i]), i
            elif verso < 0 and ba[i] < b:
                b, b_i = float(ba[i]), i
        if verso != 0 and not preso:
            # L'inducement: l'ultimo minimo (massimo) piccolo fra A e B; preso quando il prezzo ci passa sotto.
            opposti = minimi if verso > 0 else massimi
            fra = [x for x in opposti[-12:] if a_i < x < b_i]
            idm = (ba[fra[-1]] if verso > 0 else al[fra[-1]]) if fra else np.nan
            estremo = ba[i] if verso > 0 else al[i]
            if not np.isnan(idm) and evento == NIENTE and (estremo - idm) * verso < 0:
                preso = True
        cambio[i], verso_v[i], rotture_v[i], preso_v[i] = evento, verso, rotture, preso
        if verso == 0:
            continue
        fuori["a"][i], a_iv[i], fuori["b"][i], b_iv[i], fuori["idm"][i] = a, a_i, b, b_i, idm
        fuori["epa_alto"][i] = _epa(ap, ch, al, ba, a_i, verso)
    return Struttura(verso_v, fuori["a"], a_iv, fuori["b"], b_iv, fuori["idm"], preso_v, fuori["epa_alto"],
                     cambio, rotture_v)


def msu(c: Candele, lato: int = LATO) -> tuple[np.ndarray, np.ndarray]:
    """L'MSU candela per candela (libro p99-101, figure dei tipi 1, 2 e 3): +1 quando, dopo l'ultimo massimo
    piccolo, il prezzo ha preso il minimo piccolo che c'era prima (la liquidita', ✗) e adesso chiude sopra quel
    massimo (la rottura, ✓); -1 lo specchio. Il secondo array e' l'estremo della presa (dove sta lo stop piccolo).
    Ogni massimo (minimo) si rompe una volta sola."""
    al, ba, ch = (c.bid[:, k].astype(np.float64) for k in (MASSIMO, MINIMO, CHIUSURA))
    n = len(c)
    mx, mn = punti(al, ba, lato)
    segnale, estremo = np.zeros(n, int), np.full(n, np.nan)
    massimi: list[int] = []
    minimi: list[int] = []
    rotto_su = rotto_giu = -1
    for i in range(n):
        k = i - lato
        if k >= 0:
            if mx[k]:
                massimi.append(k)
            if mn[k]:
                minimi.append(k)
        if massimi and massimi[-1] != rotto_su and ch[i] > al[massimi[-1]]:
            sh = massimi[-1]
            rotto_su = sh
            prima = [x for x in minimi[-12:] if x < sh]
            fondo = float(ba[sh:i + 1].min())
            if prima and fondo < ba[prima[-1]]:
                segnale[i], estremo[i] = 1, fondo
        if minimi and minimi[-1] != rotto_giu and ch[i] < ba[minimi[-1]]:
            sl = minimi[-1]
            rotto_giu = sl
            prima = [x for x in massimi[-12:] if x < sl]
            cima = float(al[sl:i + 1].max())
            if prima and cima > al[prima[-1]]:
                segnale[i], estremo[i] = -1, cima
    return segnale, estremo


@dataclass(frozen=True)
class Occasione:
    """Un'entrata con le tre regole: inducement preso, prezzo in EPA, MSU sul timeframe sotto."""
    verso: int        # +1 long, -1 short
    quando: int       # l'apertura della candela bassa dopo l'MSU: qui si entra
    ingresso: float   # il prezzo d'apertura di quella candela (bid; lo spread lo mette la simulazione)
    stop: float       # oltre A, cioe' oltre la EPA
    obiettivo: float  # B, il massimo (minimo) della struttura
    a: float
    b: float
    idm: float
    epa_alto: float
    msu_estremo: float  # il minimo (massimo) della struttura piccola prima dell'MSU
    sconto: float     # dove sta l'ingresso fra A (0) e B (1): sotto 0,5 e' discount (premium in short)
    rotture: int      # in che punto del ciclo siamo (1 = struttura appena nata)


def occasioni(alta: Candele, bassa: Candele, lato: int = LATO, lato_basso: int = LATO) -> list[Occasione]:
    """Le occasioni delle tre regole: la struttura sul timeframe alto, l'MSU sul timeframe basso.

    Per ogni candela bassa vale la struttura alta dell'ultima candela alta chiusa. Regola 1: l'inducement e'
    preso (`idm_preso`). Regola 2: dopo, il prezzo entra nella EPA (fra A e `epa_alto`) senza chiudere oltre A.
    Regola 3: l'MSU sul timeframe basso nel verso di quella alta (`msu`). Si entra all'apertura della candela
    bassa dopo; stop su A, obiettivo B. Un'occasione per ritracciamento: la prossima dopo una nuova rottura.
    """
    s = struttura(alta, lato)
    segnale, presa = msu(bassa, lato_basso)
    al, ba, ch = bassa.bid[:, MASSIMO], bassa.bid[:, MINIMO], bassa.bid[:, CHIUSURA]
    quale = np.searchsorted(alta.fine, bassa.inizio, side="right") - 1
    fuori: list[Occasione] = []
    chiave = usata = None
    in_epa = morta = False
    for k in range(len(bassa) - 1):
        h = int(quale[k])
        if h < 0 or s.verso[h] == 0 or not s.idm_preso[h]:
            continue
        v = int(s.verso[h])
        nuova = (v, int(s.a_i[h]), int(s.b_i[h]))
        if nuova != chiave:
            chiave, in_epa, morta = nuova, False, False
        if chiave == usata or morta:
            continue
        a, b, epa = float(s.a[h]), float(s.b[h]), float(s.epa_alto[h])
        if (ch[k] - a) * v < 0:
            morta = True  # chiusa oltre A sul timeframe basso: la struttura non regge
            continue
        estremo = ba[k] if v > 0 else al[k]
        if (estremo - epa) * v <= 0:
            in_epa = True
        if not in_epa or segnale[k] != v:
            continue
        ingresso = float(bassa.bid[k + 1, APERTURA])
        if (ingresso - a) * v <= 0 or (b - ingresso) * v <= 0:
            continue
        fuori.append(Occasione(
            verso=v, quando=int(bassa.inizio[k + 1]), ingresso=ingresso, stop=a, obiettivo=b, a=a, b=b,
            idm=float(s.idm[h]), epa_alto=epa, msu_estremo=float(presa[k]), sconto=(ingresso - a) / (b - a),
            rotture=int(s.rotture[h])))
        usata = chiave
    return fuori
