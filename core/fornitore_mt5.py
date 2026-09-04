"""Il fornitore che collega il motore ai dati veri di MetaTrader 5.

E' il pezzo che mancava fra l'alert di TradingView e le regole. L'alert dice
**quando** rivalutare; questo file costruisce il **cosa**, leggendo le candele
dal terminale.

## Cosa fa

1. traduce il timeframe dell'alert in uno dei dieci di `DEF-01`;
2. legge da MT5 le barre di ogni timeframe, converte gli orari di apertura in
   orari di chiusura e scarta la barra in formazione;
3. aggrega `TF_3M`, `TF_6M` e `TF_12M`, che MT5 non ha;
4. legge conto, posizioni e P&L dei tre periodi;
5. consegna la `Fotografia` a `motore.valuta()`.

## Il limite da tenere davanti agli occhi

`DEF-32`, come corretta da `REV-13`, impone che ogni OHLC venga dal **future
CME**. Questo fornitore legge da MT5, e MT5 di FP Markets serve **CFD**.

Non e' un dettaglio tecnico: e' una **non conformita' dichiarata**. Il bot
gira, riceve, decide, esegue e notifica su dati veri di mercato vero, ma i
prezzi su cui ragiona non sono quelli che la strategia prescrive. Serve a far
funzionare la macchina e a scoprire i problemi pratici; **non** serve a
misurare se la strategia funziona.

Per questo `NON_CONFORMITA` non e' un commento ma un valore che il sistema
porta con se': finisce nel log all'avvio, in `/salute`, e nel motivo di ogni
decisione. Il giorno che colleghi un feed CME cambia solo questo file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core import broker
from core.aggregazione import costruisci_superiori
from core.definizioni import Bias, Candela
from core.log import diario
from core.models import AlertIn
from core.motore import Fotografia
from core.parametri import LOOKBACK_ANNI, TF, UNIVERSO
from core.stato import Conto, costruisci_fotografia

log = diario("fornitore")

NON_CONFORMITA: str = (
    "DEF-32/REV-13: i prezzi vengono dal CFD di MT5, non dal future CME. "
    "La macchina gira su dati veri, ma i risultati non misurano la strategia."
)

# I timeframe che MT5 fornisce direttamente. I valori sono quelli del modulo
# MetaTrader5; si leggono a runtime per non importarlo qui.
NOMI_TIMEFRAME_MT5: dict[TF, str] = {
    TF.H1: "TIMEFRAME_H1",
    TF.H4: "TIMEFRAME_H4",
    TF.H6: "TIMEFRAME_H6",
    TF.H12: "TIMEFRAME_H12",
    TF.D1: "TIMEFRAME_D1",
    TF.W1: "TIMEFRAME_W1",
    TF.M1: "TIMEFRAME_MN1",
}

# Quante barre chiedere per timeframe. I valori coprono i cinque anni di
# DEF-26 dove e' possibile; dove non lo e' il fornitore lo dichiara invece di
# tacere.
BARRE_DA_CHIEDERE: dict[TF, int] = {
    TF.H1: 20000,     # circa 3 anni di ore di mercato
    TF.H4: 10000,     # circa 6 anni
    TF.H6: 8000,
    TF.H12: 5000,
    TF.D1: 2000,      # circa 5,5 anni
    TF.W1: 400,       # circa 7 anni
    TF.M1: 150,       # 12 anni: servono anche a TF_12M
}

# Timeframe dell'alert TradingView -> timeframe della strategia.
# Solo quelli su cui DEF-01 ammette un trigger: gli altri non innescano nulla.
TIMEFRAME_ALERT: dict[str, TF] = {
    "60": TF.H1, "1H": TF.H1, "H1": TF.H1,
    "240": TF.H4, "4H": TF.H4, "H4": TF.H4,
    "D": TF.D1, "1D": TF.D1, "1440": TF.D1,
    "W": TF.W1, "1W": TF.W1,
    "M": TF.M1, "1M": TF.M1,
}


def carica_calendario(adesso: datetime):
    """Legge il calendario news dal percorso configurato (PA-54).

    Restituisce (eventi, eta_in_ore, motivo). Con eventi a None il motore si
    astiene per PA-55, ed e' voluto: operare senza sapere se fra due minuti
    esce un dato a tre stelle e' peggio che saltare la giornata.
    """
    from core import calendario
    from core.parametri import PERCORSO_CALENDARIO_NEWS

    return calendario.carica(PERCORSO_CALENDARIO_NEWS, adesso)


class SimboloNonTrovato(LookupError):
    """Lo strumento di PRIN-08 non esiste con quel nome sul broker."""


@dataclass
class FornitoreMT5:
    """Costruisce la Fotografia leggendo il terminale.

    `suffisso` copre i nomi dei broker che aggiungono un suffisso agli
    strumenti (`EURUSD.a`, `XAUUSD.pro`). Viene provato solo se il nome nudo
    non esiste.
    """

    suffisso: str = ""
    _simboli: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._simboli is None:
            self._simboli = {}

    # -- simboli ----------------------------------------------------------
    def simbolo_broker(self, strumento: str) -> str:
        """Il nome con cui il broker conosce uno strumento di PRIN-08."""
        if strumento in self._simboli:
            return self._simboli[strumento]
        candidati = [strumento]
        if self.suffisso:
            candidati.append(f"{strumento}{self.suffisso}")
        for nome in candidati:
            ok, _, _ = broker.specifiche_simbolo(nome)
            if ok:
                self._simboli[strumento] = nome
                return nome
        raise SimboloNonTrovato(
            f"{strumento} non trovato sul broker (provati: {', '.join(candidati)}). "
            "Se il tuo broker usa un suffisso, impostalo in MT5_SUFFISSO_SIMBOLI."
        )

    # -- candele ----------------------------------------------------------
    def candele_di(self, simbolo: str, tf: TF, quante: int) -> tuple[Candela, ...]:
        """Le candele **chiuse** di un timeframe, con gli orari corretti.

        Due conversioni, ed entrambe sono trappole da lookahead:

        - MT5 marca ogni barra con l'istante di **apertura**; `Candela.orario`
          e' la **chiusura** (DEF-02). La chiusura della barra `i` e'
          l'apertura della barra `i+1`.
        - l'ultima barra e' quella **in formazione**: non ha un successore,
          quindi non ha chiusura nota, e viene scartata (ESCL-13).
        """
        import MetaTrader5 as mt5  # type: ignore[import-not-found]

        nome_costante = NOMI_TIMEFRAME_MT5.get(tf)
        if nome_costante is None:
            raise ValueError(f"{tf.value} non e' un timeframe nativo di MT5")

        ok, barre, messaggio = broker.candele(simbolo, getattr(mt5, nome_costante), quante)
        if not ok:
            log.warning("%s %s: %s", simbolo, tf.value, messaggio)
            return ()

        chiuse: list[Candela] = []
        for indice in range(len(barre) - 1):        # l'ultima e' in formazione
            barra = barre[indice]
            chiusura = barre[indice + 1]["apertura_utc"]
            try:
                chiuse.append(Candela(
                    orario=chiusura,
                    apertura=barra["open"],
                    massimo=barra["high"],
                    minimo=barra["low"],
                    chiusura=barra["close"],
                ))
            except ValueError as errore:
                # Una barra incoerente non deve far cadere l'intero storico.
                log.warning("%s %s: barra scartata: %s", simbolo, tf.value, errore)
        return tuple(chiuse)

    def storico(self, strumento: str) -> dict[TF, tuple[Candela, ...]]:
        """Lo storico completo di uno strumento, sui dieci timeframe."""
        simbolo = self.simbolo_broker(strumento)
        storico: dict[TF, tuple[Candela, ...]] = {}

        for tf, quante in BARRE_DA_CHIEDERE.items():
            storico[tf] = self.candele_di(simbolo, tf, quante)

        # I tre che MT5 non ha, dai mensili.
        for tf, candele in costruisci_superiori(storico.get(TF.M1, ())).items():
            storico[tf] = candele

        self._segnala_storia_corta(strumento, storico)
        return storico

    def _segnala_storia_corta(self, strumento: str, storico: dict) -> None:
        """DEF-26 vuole cinque anni: dove non ci sono, va detto.

        Un timeframe con meno storia produce meno livelli strutturali, quindi
        target piu' vicini. Non e' un errore ma cambia il comportamento, e
        tacerlo lo renderebbe inspiegabile.
        """
        soglia = datetime.now(timezone.utc) - timedelta(days=365 * LOOKBACK_ANNI)
        for tf, candele in storico.items():
            if not candele:
                log.warning("%s %s: nessuna candela", strumento, tf.value)
                continue
            if candele[0].orario > soglia:
                anni = (candele[-1].orario - candele[0].orario).days / 365.0
                log.warning(
                    "%s %s: solo %.1f anni di storia, DEF-26 ne vuole %d",
                    strumento, tf.value, anni, LOOKBACK_ANNI,
                )

    # -- conto -------------------------------------------------------------
    def conto(self, prezzo_cfd: float, valore_punto: float, passo: float, spread: float) -> Conto:
        """Equity, posizioni e P&L dei tre periodi, letti dal terminale."""
        ok_conto, dati, messaggio = broker.info_conto()
        if not ok_conto or dati is None:
            raise RuntimeError(f"conto non leggibile: {messaggio}")

        _, posizioni, _ = broker.posizioni_per_strumento()

        adesso = datetime.now(timezone.utc)
        inizio_giorno = adesso.replace(hour=0, minute=0, second=0, microsecond=0)
        inizio_settimana = inizio_giorno - timedelta(days=inizio_giorno.weekday())
        inizio_mese = inizio_giorno.replace(day=1)

        _, giornaliero, _ = broker.pnl_chiuso(inizio_giorno)
        _, settimanale, _ = broker.pnl_chiuso(inizio_settimana)
        _, mensile, _ = broker.pnl_chiuso(inizio_mese)

        equity = float(dati["equity"])
        return Conto(
            equity=equity,
            prezzo_cfd=prezzo_cfd,
            valore_punto=valore_punto,
            passo_broker=passo,
            spread=spread,
            posizioni_aperte_per_strumento=posizioni,
            pnl_giornaliero=giornaliero,
            # L'equity di inizio periodo si ricava da quella attuale meno il
            # P&L gia' realizzato: e' il riferimento che RISK-07/08/09 vogliono.
            equity_inizio_giornata=equity - giornaliero,
            pnl_settimanale=settimanale,
            equity_inizio_settimana=equity - settimanale,
            pnl_mensile=mensile,
            equity_inizio_mese=equity - mensile,
        )

    # -- fotografia --------------------------------------------------------
    def costruisci(self, alert: AlertIn) -> Optional[tuple[Fotografia, TF]]:
        """Da un alert alla Fotografia. None se non e' possibile costruirla."""
        strumento = alert.simbolo.upper()
        if strumento not in UNIVERSO:
            log.info("alert su %s: fuori da PRIN-08, ignorato", strumento)
            return None

        tf_trigger = TIMEFRAME_ALERT.get(alert.tf.upper())
        if tf_trigger is None:
            log.info("alert su %s con timeframe %r: non e' un trigger di DEF-01",
                     strumento, alert.tf)
            return None

        try:
            simbolo = self.simbolo_broker(strumento)
        except SimboloNonTrovato as errore:
            log.error("%s", errore)
            return None

        ok_specifiche, specifiche, messaggio = broker.specifiche_simbolo(simbolo)
        if not ok_specifiche or specifiche is None:
            log.error("specifiche di %s non leggibili: %s", simbolo, messaggio)
            return None

        ok_prezzo, tick, messaggio = broker.prezzo_corrente(simbolo)
        if not ok_prezzo or tick is None:
            log.warning("nessuna quotazione per %s: %s", simbolo, messaggio)
            return None

        try:
            conto = self.conto(
                # Prezzo di mezzo: la direzione non e' ancora nota, quindi
                # non si sa se si entrera' in ask o in bid. L'esecuzione vera
                # dista mezzo spread da qui, e CTX-03 accetta esplicitamente
                # di non filtrare sullo spread.
                prezzo_cfd=(tick["bid"] + tick["ask"]) / 2,
                valore_punto=specifiche["valore_punto"],
                passo=specifiche["volume_step"],
                spread=tick["ask"] - tick["bid"],
            )
        except RuntimeError as errore:
            log.error("%s", errore)
            return None

        # Il calendario news e' obbligatorio: senza, PA-55 impone astensione
        # e il bot non opererebbe mai. Va caricato, non dimenticato.
        adesso = datetime.now(timezone.utc)
        eventi, eta, motivo = carica_calendario(adesso)
        if eventi is None:
            log.error("calendario news non utilizzabile: %s", motivo)

        # Le fasi del gap appartengono alla sorveglianza (DEF-43, DEF-45):
        # dipendono dai prezzi scambiati fra una chiusura e l'altra, che uno
        # storico di candele non contiene. Finche' la sentinella non le
        # traccia restano a zero, e SETUP-09 blocca gli ingressi da gap: e'
        # il comportamento prudente, non un difetto silenzioso.
        foto = costruisci_fotografia(
            istante=adesso,
            strumento=strumento,
            storico=self.storico(strumento),
            conto=conto,
            eventi_news=eventi or (),
            eta_calendario_ore=eta,
        )
        return foto, tf_trigger


def collega(suffisso: str = "") -> FornitoreMT5:
    """Registra il fornitore nella strategia e restituisce l'istanza.

    Da questo momento il webhook fa girare il motore su dati veri. La non
    conformita' viene scritta nel log ogni volta che si collega: e' una cosa
    che non deve poter passare inosservata.
    """
    from core import strategy

    fornitore = FornitoreMT5(suffisso=suffisso)
    strategy.registra_fornitore(fornitore.costruisci)
    log.warning("fornitore MT5 collegato — %s", NON_CONFORMITA)
    return fornitore
