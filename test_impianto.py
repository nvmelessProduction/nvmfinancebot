"""Collaudo automatico dell'impianto. Si lancia con:

    python -m unittest test_impianto -v

Nessuna dipendenza in piu': solo `unittest` della libreria standard e il
TestClient di FastAPI.

Il punto interessante e' il MetaTrader5 finto: il pacchetto vero esiste solo
su Windows e vuole un conto aperto, quindi qui viene sostituito da un doppione
che risponde come risponderebbe il terminale. Cosi' il percorso degli ordini
- quello che un giorno muovera' soldi veri - viene davvero eseguito, anche su
una macchina senza MT5.
"""

import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Ambiente isolato: archivio e log in una cartella temporanea, mai nel progetto.
# Va fatto PRIMA di importare i moduli, perche' la configurazione si legge
# all'avvio.
# --------------------------------------------------------------------------
_CARTELLA = tempfile.mkdtemp(prefix="collaudo-impianto-")
os.environ.update(
    {
        "DB_PATH": os.path.join(_CARTELLA, "collaudo.db"),
        "LOG_FILE": os.path.join(_CARTELLA, "collaudo.log"),
        "LOG_LIVELLO": "CRITICAL",
        "WEBHOOK_SECRET": "segreto-di-collaudo",
        "MODE": "dry_run",
        "TELEGRAM_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        # Le credenziali vuote qui sopra gia' bastano, ma non sono una
        # chiusura: bastava che un collaudo futuro ne valorizzasse una per
        # ritrovarsi a spedire sul telefono di qualcuno. Questa lo vieta e
        # basta. Vedi `core.notifier.in_prova`.
        "NVMBOT_NIENTE_TELEGRAM": "1",
        "FILE_BLOCCO": os.path.join(_CARTELLA, "STOP"),
        "SENTINELLA_ATTIVA": "false",
        # Isolamento dal .env vero: su una macchina con un broker gia'
        # configurato, MT5_SUFFISSO_SIMBOLI non vuoto filtrerebbe nei
        # collaudi che assumono il simbolo senza suffisso.
        "MT5_SUFFISSO_SIMBOLI": "",
        # Il ciclo di mercato va a prendere candele vere da internet: nei
        # collaudi non deve partire mai. Le sue prove usano risposte finte.
        "FORNITORE_DATI": "nessuno",
    }
)


# ==========================================================================
# Il MetaTrader5 finto
# ==========================================================================
class Oggetto:
    """Contenitore generico: imita gli oggetti che restituisce MT5."""

    def __init__(self, **campi: object) -> None:
        self.__dict__.update(campi)


class FintoMT5(types.ModuleType):
    """Doppione del modulo MetaTrader5, quanto basta per il collaudo."""

    # Costanti, con gli stessi valori del modulo vero.
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    DEAL_ENTRY_OUT = 1
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_H6 = 16390
    TIMEFRAME_H12 = 16396
    TIMEFRAME_D1 = 16408
    TIMEFRAME_W1 = 32769
    TIMEFRAME_MN1 = 49153

    def __init__(self) -> None:
        super().__init__("MetaTrader5")
        self.azzera()

    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def azzera(self) -> None:
        # Quante letture di prezzo tornano vuote prima della prima buona:
        # e' cosi' che si comporta il terminale con un simbolo appena
        # aggiunto all'Osservazione del mercato.
        self.tick_vuoti_iniziali = 0
        self.avviato = False
        self.trading_abilitato = True
        self.modo_conto = 0                 # demo
        self.bid = 1.10000
        self.ask = 1.10010
        self.posizioni: list[Oggetto] = []
        self.ordini_inviati: list[dict] = []
        self.prossimo_ticket = 1000
        self.ordine_fallisce = False
        self.barre_per_timeframe: dict[int, list[dict]] = {}
        self.deal: list[Oggetto] = []

    # -- ciclo di vita --
    def initialize(self, **_: object) -> bool:
        self.avviato = True
        return True

    def shutdown(self) -> None:
        self.avviato = False

    def last_error(self) -> tuple[int, str]:
        return (0, "nessun errore")

    def terminal_info(self):
        if not self.avviato:
            return None
        return Oggetto(trade_allowed=self.trading_abilitato)

    def account_info(self):
        if not self.avviato:
            return None
        return Oggetto(
            login=123456, server="FPMarkets-Demo", currency="EUR",
            balance=10000.0, equity=10050.0, margin_free=9800.0,
            leverage=30, trade_allowed=True, trade_mode=self.modo_conto,
        )

    # -- simboli e prezzi --
    def symbol_select(self, simbolo: str, _abilita: bool = True) -> bool:
        return simbolo != "SIMBOLO-INESISTENTE"

    def symbol_info_tick(self, simbolo: str):
        if simbolo == "SIMBOLO-INESISTENTE":
            return None
        # Il terminale vero risponde con bid e ask a zero finche' non ha
        # ricevuto il primo prezzo di un simbolo appena selezionato.
        if self.tick_vuoti_iniziali > 0:
            self.tick_vuoti_iniziali -= 1
            return Oggetto(bid=0.0, ask=0.0)
        return Oggetto(bid=self.bid, ask=self.ask)

    def symbol_info(self, simbolo: str):
        if simbolo == "SIMBOLO-INESISTENTE":
            return None
        return Oggetto(
            name=simbolo, description=f"prova {simbolo}", digits=5,
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=50.0,
            trade_tick_size=0.00001, trade_tick_value=0.1,
            trade_contract_size=100000.0, spread=12,
        )

    # -- storico --
    def copy_rates_from_pos(self, simbolo: str, timeframe: int, inizio: int, quante: int):
        """Come MT5: `time` e' l'APERTURA della barra, e l'ultima e' in corso."""
        barre = self.barre_per_timeframe.get(timeframe)
        if barre is None:
            return None
        return barre[-quante:] if quante else barre

    def history_deals_get(self, da, a):
        return tuple(self.deal)

    # -- posizioni e ordini --
    def positions_get(self, symbol: str | None = None, ticket: int | None = None):
        if ticket is not None:
            return tuple(p for p in self.posizioni if p.ticket == ticket)
        if symbol is not None:
            return tuple(p for p in self.posizioni if p.symbol == symbol)
        return tuple(self.posizioni)

    def order_send(self, richiesta: dict):
        self.ordini_inviati.append(richiesta)
        if self.ordine_fallisce:
            return Oggetto(retcode=10004, comment="Requote", order=0, price=0.0)

        if "position" in richiesta:  # chiusura, totale o parziale
            # MT5 vero: una chiusura con volume inferiore a quello aperto e'
            # un PARZIALE. Il ticket resta, il volume residuo si aggiorna. Il
            # finto lo imita, altrimenti il parziale del 25% di GEST-04 non
            # sarebbe collaudabile qui dentro.
            residue = []
            for p in self.posizioni:
                if p.ticket != richiesta["position"]:
                    residue.append(p)
                    continue
                resto = round(p.volume - richiesta["volume"], 8)
                if resto > 0:
                    p.volume = resto
                    residue.append(p)
            self.posizioni = residue
            return Oggetto(
                retcode=self.TRADE_RETCODE_DONE, order=richiesta["position"],
                price=richiesta["price"], comment="chiusa",
            )

        self.prossimo_ticket += 1
        self.posizioni.append(
            Oggetto(
                ticket=self.prossimo_ticket, symbol=richiesta["symbol"],
                type=richiesta["type"], volume=richiesta["volume"],
                price_open=richiesta["price"], price_current=richiesta["price"],
                profit=0.0, magic=richiesta["magic"],
            )
        )
        return Oggetto(
            retcode=self.TRADE_RETCODE_DONE, order=self.prossimo_ticket,
            price=richiesta["price"], comment="eseguito",
        )


finto = FintoMT5()
sys.modules["MetaTrader5"] = finto

# --------------------------------------------------------------------------
# Ora si importano i moduli: broker trovera' il MetaTrader5 finto.
# --------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from core import broker, sentinella as modulo_sentinella, storage  # noqa: E402
from core.config import impostazioni  # noqa: E402
from core.models import AlertIn, Decision  # noqa: E402
from core.parametri import TF  # noqa: E402
from core.simboli import FUTURE_A_CFD  # noqa: E402
from core.strategy import valuta  # noqa: E402

import main  # noqa: E402


def alert_finto(**modifiche: object) -> dict:
    """Un payload TradingView valido, modificabile campo per campo."""
    adesso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {
        "secret": "segreto-di-collaudo",
        "symbol": "EURUSD",
        "tf": "15",
        "candle_close_time_utc": adesso,
        "open": 1.10000,
        "high": 1.10500,
        "low": 1.09500,
        "close": 1.10250,
    }
    base.update(modifiche)
    return base


def riconfigura(**variabili: str) -> None:
    """Cambia la configurazione e forza la rilettura."""
    os.environ.update(variabili)
    impostazioni.cache_clear()


class BaseCollaudo(unittest.TestCase):
    """Archivio pulito prima di ogni prova."""

    def setUp(self) -> None:
        for coda in ("", "-wal", "-shm"):
            percorso = os.environ["DB_PATH"] + coda
            if os.path.exists(percorso):
                os.remove(percorso)
        blocco = os.environ["FILE_BLOCCO"]
        if os.path.exists(blocco):
            os.remove(blocco)
        riconfigura(MODE="dry_run", SENTINELLA_ATTIVA="false")
        finto.azzera()
        storage.inizializza()


# ==========================================================================
# 0bis. La catena dal ciclo Dukascopy al motore
# ==========================================================================
class ProvaCatenaDukascopy(BaseCollaudo):
    """L'alert che il ciclo costruisce arriva davvero fino a una decisione?

    Per settimane non ci e' arrivato. `mercato_duka` costruiva `AlertIn` con
    i nomi sbagliati, pydantic rifiutava, un `except Exception` inghiottiva
    l'errore e il contatore `valutazioni` di /salute cresceva lo stesso. Da
    fuori si vedeva un bot al lavoro che non trovava setup; dentro, il motore
    non aveva mai ricevuto una candela.

    Nessuna prova esistente poteva accorgersene: erano tutte sull'alert di
    TradingView, che quella strada non la percorre.
    """

    ORIGINE = "dukascopy"

    def semina(self, strumento: str, tf, quante: int = 40,
               base: float = 100.0, passo: float = 1.0) -> None:
        """Una serie che sale in accettazione: DEF-16 ci legge una bias LONG."""
        from datetime import timedelta as td

        inizio = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0) - td(hours=quante)
        righe = []
        for n in range(quante):
            apertura = base + n * passo
            righe.append({
                "strumento": strumento, "tf": tf.value,
                "chiusura_utc": (inizio + td(hours=n)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apertura": apertura,
                "massimo": apertura + passo * 1.5,
                "minimo": apertura - passo * 0.2,
                "chiusura": apertura + passo * 1.2,
            })
        storage.salva_candele(righe, origine=self.ORIGINE)

    def semina_calendario(self) -> None:
        """PA-55 vuole un calendario compilato, o il motore si astiene prima
        ancora di guardare il grafico. Qui serve solo che ci sia: gli eventi
        stanno lontani dall'istante della prova.

        Scrive nella cartella isolata del collaudo, mai in `dati/news.csv`
        vero: quel file e' il calendario compilato a mano dall'autore, e
        scriverci sopra (per di piu' cancellandolo poi in cleanup) lo
        distruggerebbe ad ogni collaudo. Successo davvero una volta.
        """
        from datetime import timedelta as td
        from pathlib import Path
        from unittest.mock import patch

        percorso = Path(_CARTELLA) / "news.csv"
        adesso = datetime.now(timezone.utc)
        righe = ["data_ora_utc,valuta,stelle,descrizione"]
        for giorni in (-3, -1, 4, 9):
            quando = adesso + td(days=giorni)
            righe.append(f"{quando:%Y-%m-%dT%H:%M:%SZ},USD,3,evento di collaudo")
        percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")

        patcher = patch("core.parametri.PERCORSO_CALENDARIO_NEWS", str(percorso))
        patcher.start()
        self.addCleanup(patcher.stop)

    def semina_tutto(self) -> None:
        from core.duka_dxy import NOME_ARCHIVIO as DXY
        from core.mercato import TF_INGRESSO_OPERATIVI, TF_OPERATIVI
        from core.parametri import TF

        tutti = set(TF_OPERATIVI) | set(TF_INGRESSO_OPERATIVI) | {TF.W1}
        for tf in tutti:
            self.semina("EURUSD", tf)
            self.semina(DXY, tf, base=103.0, passo=0.05)

    def test_l_alert_del_ciclo_e_leggibile(self) -> None:
        """I tre campi che mancavano: apertura, massimo, minimo."""
        from core.definizioni import Candela
        from core.mercato_duka import _alert
        from core.parametri import TF
        from core.simboli import future_da_ticker, timeframe_da_intervallo

        candela = Candela(datetime(2026, 9, 16, 10, 15, tzinfo=timezone.utc),
                          1.10, 1.15, 1.05, 1.12)
        alert = _alert("EURUSD", TF.MIN15, candela, "segreto-di-collaudo")
        self.assertEqual((alert.apertura, alert.massimo, alert.minimo,
                          alert.chiusura), (1.10, 1.15, 1.05, 1.12))
        self.assertEqual(future_da_ticker(alert.simbolo), "6E")
        self.assertIs(timeframe_da_intervallo(alert.tf), TF.MIN15)

    def test_la_catena_arriva_al_motore(self) -> None:
        """Nessun timeframe deve fermarsi su PRIN-99: sarebbe un guasto, non
        un'astensione."""
        from core import strategy
        from core.definizioni import Candela
        from core.fornitore_tradingview import collega
        from core.mercato import TF_INGRESSO_OPERATIVI, TF_OPERATIVI
        from core.mercato_duka import _alert

        riconfigura(FORNITORE_DATI="dukascopy")
        try:
            self.semina_calendario()
            self.semina_tutto()
            collega()
            candela = Candela(datetime.now(timezone.utc), 140.0, 141.5, 139.8, 141.2)

            for tf in sorted(set(TF_OPERATIVI) | set(TF_INGRESSO_OPERATIVI),
                             key=lambda x: x.value):
                alert = _alert("EURUSD", tf, candela, "segreto-di-collaudo")
                decisione = strategy.valuta(alert)
                self.assertNotIn(
                    "PRIN-99", decisione.motivo or "",
                    f"{tf.value}: la catena si e' rotta, non astenuta -- "
                    f"{decisione.motivo}")
                self.assertNotIn("livello dati non collegato", decisione.motivo or "")
        finally:
            riconfigura(FORNITORE_DATI="tradingview")

    def test_senza_dxy_setup19_non_abilita_nulla(self) -> None:
        """Il blocco che teneva fermo il bot su cinque coppie su sei."""
        from core.fornitore_tradingview import FornitoreTradingView
        from core.duka_dxy import NOME_ARCHIVIO as DXY
        from core.stato import bias_comando_dxy

        riconfigura(FORNITORE_DATI="dukascopy")
        try:
            fornitore = FornitoreTradingView()
            vuoto = bias_comando_dxy(fornitore.storico(DXY),
                                     datetime.now(timezone.utc))
            self.assertEqual(vuoto.value, "NESSUNA",
                             "senza archivio del DXY la bias non puo' che mancare")

            self.semina_tutto()
            pieno = bias_comando_dxy(fornitore.storico(DXY),
                                     datetime.now(timezone.utc))
            self.assertNotEqual(
                pieno.value, "NESSUNA",
                "con l'archivio del DXY seminato la bias deve esserci, "
                "altrimenti SETUP-19 blocca comunque tutto")
        finally:
            riconfigura(FORNITORE_DATI="tradingview")

    def test_l_archivio_si_legge_col_nome_con_cui_e_scritto(self) -> None:
        """Dukascopy scrive `EURUSD`, l'analisi chiede `6E`: la traduzione
        deve esserci, o l'archivio risulta vuoto e DEF-26 fa tacere tutto."""
        from core.fornitore_tradingview import FornitoreTradingView
        from core.parametri import TF

        riconfigura(FORNITORE_DATI="dukascopy")
        try:
            self.semina("EURUSD", TF.D1)
            fornitore = FornitoreTradingView()
            self.assertEqual(fornitore.nome_in_archivio("6E"), "EURUSD")
            self.assertTrue(fornitore.storico("6E")[TF.D1],
                            "lo storico del future deve trovare le candele CFD")
        finally:
            riconfigura(FORNITORE_DATI="tradingview")


# ==========================================================================
# 1. Sicurezza del webhook
# ==========================================================================
class ProvaSicurezza(BaseCollaudo):
    def test_segreto_sbagliato_rifiutato_e_senza_traccia(self) -> None:
        with TestClient(main.app) as c:
            risposta = c.post("/webhook", json=alert_finto(secret="sbagliato"))
        self.assertEqual(risposta.status_code, 401)
        self.assertEqual(storage.conteggi()["alert"], 0, "un segreto errato non deve lasciare traccia")

    def test_segreto_vuoto_rifiutato(self) -> None:
        with TestClient(main.app) as c:
            risposta = c.post("/webhook", json=alert_finto(secret=""))
        self.assertEqual(risposta.status_code, 401)

    def test_senza_segreto_configurato_si_rifiuta_tutto(self) -> None:
        riconfigura(WEBHOOK_SECRET="")
        try:
            with TestClient(main.app) as c:
                risposta = c.post("/webhook", json=alert_finto(secret=""))
            self.assertEqual(risposta.status_code, 401, "senza segreto configurato non si accetta nulla")
        finally:
            riconfigura(WEBHOOK_SECRET="segreto-di-collaudo")

    def test_segreto_giusto_accettato(self) -> None:
        with TestClient(main.app) as c:
            risposta = c.post("/webhook", json=alert_finto())
        self.assertEqual(risposta.status_code, 200)
        self.assertEqual(storage.conteggi()["alert"], 1)

    def test_payload_malformato(self) -> None:
        with TestClient(main.app) as c:
            risposta = c.post("/webhook", json={"secret": "segreto-di-collaudo"})
        self.assertEqual(risposta.status_code, 422)
        self.assertEqual(storage.conteggi()["alert"], 0)


# ==========================================================================
# 2. La strategia senza livello dati non opera, e dice perche'
# ==========================================================================
class ProvaStrategia(BaseCollaudo):
    """Dalla v0.3 la strategia esiste: sta in core/motore.py.

    Quello che manca e' il livello dati che costruisce la Fotografia. Finche'
    nessuno lo collega il bot si astiene, e queste prove verificano che si
    astenga **dichiarando il motivo** invece di restituire un NONE muto che
    sembrerebbe una decisione di strategia.
    """

    def setUp(self) -> None:
        super().setUp()
        from core import strategy
        strategy.registra_fornitore(None)

    def test_senza_livello_dati_non_opera(self) -> None:
        for chiusura in (1.0, 1.5, 99.0, 0.0001):
            decisione = valuta(AlertIn.model_validate(alert_finto(close=chiusura)))
            self.assertEqual(decisione.azione, "NONE")
            self.assertIsNone(decisione.volume)
            self.assertIn("livello dati non collegato", decisione.motivo)

    def test_alert_valido_non_apre_nulla(self) -> None:
        riconfigura(MODE="auto")
        with TestClient(main.app) as c:
            corpo = c.post("/webhook", json=alert_finto()).json()
        self.assertEqual(corpo["azione"], "NONE")
        self.assertEqual(corpo["esito"], "ignorato")
        self.assertEqual(
            len(finto.ordini_inviati), 0,
            "senza livello dati non deve partire nessun ordine",
        )

    def test_il_motore_di_strategia_e_collegabile(self) -> None:
        """L'innesto funziona: registrato un fornitore, il motore decide."""
        from core import strategy
        from core.motore import Decisione

        def fornitore_finto(alert):
            return None            # sa di non poter costruire la fotografia

        strategy.registra_fornitore(fornitore_finto)
        try:
            self.assertTrue(strategy.fornitore_collegato())
            decisione = valuta(AlertIn.model_validate(alert_finto()))
            self.assertEqual(decisione.azione, "NONE")
            self.assertIn("PRIN-99", decisione.motivo)
        finally:
            strategy.registra_fornitore(None)

    def test_la_traduzione_conserva_le_regole(self) -> None:
        """L'archivio e Telegram devono poter dire quale regola ha deciso."""
        from core import strategy
        from core.motore import Decisione

        tradotta = strategy.traduci(
            Decisione(azione="NONE", strumento="EURUSD",
                      regole_che_bloccano=("SETUP-05",), motivo="non allineato")
        )
        self.assertIn("SETUP-05", tradotta.motivo)


# ==========================================================================
# 3. Consegne doppie
# ==========================================================================
class ProvaDuplicati(BaseCollaudo):
    def test_stesso_alert_due_volte(self) -> None:
        payload = alert_finto()
        with TestClient(main.app) as c:
            primo = c.post("/webhook", json=payload).json()
            secondo = c.post("/webhook", json=payload).json()
        self.assertEqual(primo["esito"], "ignorato")
        self.assertEqual(secondo["esito"], "duplicato")
        self.assertEqual(secondo["alert_id"], primo["alert_id"])
        self.assertEqual(storage.conteggi()["alert"], 1)
        self.assertEqual(storage.conteggi()["decisione"], 1, "un duplicato non genera una seconda decisione")

    def test_candela_diversa_non_e_duplicato(self) -> None:
        with TestClient(main.app) as c:
            c.post("/webhook", json=alert_finto(candle_close_time_utc="2026-01-01T00:00:00Z"))
            c.post("/webhook", json=alert_finto(candle_close_time_utc="2026-01-01T00:15:00Z"))
        self.assertEqual(storage.conteggi()["alert"], 2)


# ==========================================================================
# 4. Salvaguardie
# ==========================================================================
class ProvaSalvaguardie(BaseCollaudo):
    """Le salvaguardie si provano su una decisione finta: la strategia vera
    non esiste, ma il giorno che esistera' questi controlli devono reggere."""

    def _blocco(self, decisione: Decision, **payload: object) -> str | None:
        return main.salvaguardia_violata(AlertIn.model_validate(alert_finto(**payload)), decisione)

    def test_freno_a_mano(self) -> None:
        compra = Decision(action="BUY", volume=0.01)
        self.assertIsNone(self._blocco(compra))
        open(os.environ["FILE_BLOCCO"], "w").close()
        motivo = self._blocco(compra)
        self.assertIsNotNone(motivo)
        self.assertIn("freno a mano", motivo or "")

    def test_alert_vecchio_bloccato(self) -> None:
        vecchio = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        motivo = self._blocco(Decision(action="BUY", volume=0.01), candle_close_time_utc=vecchio)
        self.assertIn("vecchio", motivo or "")

    def test_orario_illeggibile_non_blocca(self) -> None:
        motivo = self._blocco(Decision(action="BUY", volume=0.01), candle_close_time_utc="boh")
        self.assertIsNone(motivo, "un formato di data strano non deve far perdere il segnale")

    def test_volume_oltre_il_tetto(self) -> None:
        riconfigura(VOLUME_MASSIMO="1.0")
        self.assertIsNone(self._blocco(Decision(action="BUY", volume=0.5)))
        motivo = self._blocco(Decision(action="BUY", volume=99.0))
        self.assertIn("tetto", motivo or "")

    def test_troppe_posizioni_aperte(self) -> None:
        riconfigura(MAX_POSIZIONI_APERTE="2")
        compra = Decision(action="BUY", volume=0.01)
        self.assertIsNone(self._blocco(compra))
        storage.registra_posizione("EURUSD", "BUY", 0.01, ticket=1)
        storage.registra_posizione("EURUSD", "BUY", 0.01, ticket=2)
        motivo = self._blocco(compra)
        self.assertIn("tetto", motivo or "")

    def test_il_consenso_al_reale_e_spento_di_fabbrica(self) -> None:
        """E' la proprieta' che conta: chi non ha mai sentito parlare di
        questa impostazione deve essere protetto lo stesso."""
        from core.config import Impostazioni

        self.assertFalse(Impostazioni.model_fields["CONSENTI_CONTO_REALE"].default)

    def test_auto_su_conto_non_demo_e_bloccato(self) -> None:
        """In auto il bot invia ordini veri, e dal log un demo e un conto con
        i soldi dentro sono identici. Il consenso al reale si da' per
        iscritto, una volta."""
        finto.modo_conto = finto.ACCOUNT_TRADE_MODE_REAL
        riconfigura(MODE="auto", CONSENTI_CONTO_REALE="false")
        try:
            alert = AlertIn(**alert_finto())
            blocco = main.salvaguardia_violata(
                alert, Decision(action="BUY", symbol="XAUUSD", volume=0.05))
            self.assertIsNotNone(blocco, "un conto reale non e' un demo")
            self.assertIn("CONSENTI_CONTO_REALE", blocco,
                          "il messaggio deve dire come sbloccarlo")
        finally:
            finto.modo_conto = finto.ACCOUNT_TRADE_MODE_DEMO
            riconfigura(MODE="dry_run", CONSENTI_CONTO_REALE="false")

    def test_col_consenso_esplicito_il_reale_passa(self) -> None:
        finto.modo_conto = finto.ACCOUNT_TRADE_MODE_REAL
        riconfigura(MODE="auto", CONSENTI_CONTO_REALE="true")
        try:
            blocco = main.salvaguardia_violata(
                AlertIn(**alert_finto()), Decision(action="BUY", symbol="XAUUSD", volume=0.05))
            self.assertIsNone(blocco, "il consenso e' stato dato: si procede")
        finally:
            finto.modo_conto = finto.ACCOUNT_TRADE_MODE_DEMO
            riconfigura(MODE="dry_run", CONSENTI_CONTO_REALE="false")

    def test_il_demo_non_richiede_consenso(self) -> None:
        riconfigura(MODE="auto", CONSENTI_CONTO_REALE="false")
        try:
            blocco = main.salvaguardia_violata(
                AlertIn(**alert_finto()), Decision(action="BUY", symbol="XAUUSD", volume=0.05))
            self.assertIsNone(blocco, "su demo si opera senza cerimonie")
        finally:
            riconfigura(MODE="dry_run")

    def test_niente_stop_senza_sentinella(self) -> None:
        con_livelli = Decision(action="BUY", volume=0.01, sl=1.09, tp=1.11)
        motivo = self._blocco(con_livelli)
        self.assertIn("sentinella", motivo or "", "non si apre con uno stop che nessuno sorveglia")

    def test_dry_run_segnala_ma_non_blocca(self) -> None:
        riconfigura(MODE="dry_run")
        open(os.environ["FILE_BLOCCO"], "w").close()
        esito, dettaglio, _, _ = main._esegui_decisione(
            AlertIn.model_validate(alert_finto()), Decision(action="BUY", volume=0.01), 1
        )
        self.assertEqual(esito, "simulato")
        self.assertIn("sarebbe stato bloccato", dettaglio)


# ==========================================================================
# 5. Il broker, con MT5 finto
# ==========================================================================
class ProvaBroker(BaseCollaudo):
    def setUp(self) -> None:
        super().setUp()
        broker.disconnetti()

    def test_connessione_e_conto(self) -> None:
        ok, messaggio = broker.connetti()
        self.assertTrue(ok, messaggio)
        ok, conto, _ = broker.info_conto()
        self.assertTrue(ok)
        self.assertEqual(conto["equity"], 10050.0)

    def test_ordine_eseguito(self) -> None:
        esito = broker.invia_ordine("EURUSD", "BUY", 0.10)
        self.assertTrue(esito.ok, esito.messaggio)
        self.assertIsNotNone(esito.ticket)
        self.assertEqual(finto.ordini_inviati[0]["volume"], 0.10)
        self.assertEqual(finto.ordini_inviati[0]["price"], finto.ask, "un BUY si esegue in ask")
        self.assertNotIn("sl", finto.ordini_inviati[0], "gli stop non vanno mandati al broker")
        self.assertNotIn("tp", finto.ordini_inviati[0])

    def test_la_prima_quotazione_puo_tardare(self) -> None:
        """Un simbolo appena messo in Osservazione non ha ancora un prezzo:
        il terminale deve prima riceverlo. La prima lettura torna con bid e
        ask a zero, che somiglia a "mercato chiuso" ma non lo e'.
        """
        finto.tick_vuoti_iniziali = 3
        try:
            ok, prezzi, messaggio = broker.prezzo_corrente("EURUSD")
            self.assertTrue(ok, messaggio)
            self.assertGreater(prezzi["bid"], 0)
        finally:
            finto.tick_vuoti_iniziali = 0

    def test_quotazione_davvero_assente(self) -> None:
        finto.tick_vuoti_iniziali = 99
        try:
            ok, _, messaggio = broker.prezzo_corrente("EURUSD")
            self.assertFalse(ok)
            self.assertIn("tentativi", messaggio)
        finally:
            finto.tick_vuoti_iniziali = 0

    def test_vendita_al_bid(self) -> None:
        broker.invia_ordine("EURUSD", "SELL", 0.10)
        self.assertEqual(finto.ordini_inviati[0]["price"], finto.bid, "un SELL si esegue in bid")

    def test_direzione_e_volume_non_validi(self) -> None:
        self.assertFalse(broker.invia_ordine("EURUSD", "COMPRA", 0.1).ok)
        self.assertFalse(broker.invia_ordine("EURUSD", "BUY", 0).ok)
        self.assertFalse(broker.invia_ordine("EURUSD", "BUY", -1).ok)

    def test_volume_sotto_il_minimo_del_simbolo(self) -> None:
        esito = broker.invia_ordine("EURUSD", "BUY", 0.001)
        self.assertFalse(esito.ok)
        self.assertIn("minimo", esito.messaggio)

    def test_algo_trading_spento(self) -> None:
        finto.trading_abilitato = False
        esito = broker.invia_ordine("EURUSD", "BUY", 0.1)
        self.assertFalse(esito.ok)
        self.assertIn("Algo Trading", esito.messaggio)
        finto.trading_abilitato = True

    def test_ordine_rifiutato_dal_broker(self) -> None:
        finto.ordine_fallisce = True
        esito = broker.invia_ordine("EURUSD", "BUY", 0.1)
        self.assertFalse(esito.ok)
        self.assertEqual(esito.codice_errore, 10004)
        finto.ordine_fallisce = False

    def test_simbolo_inesistente(self) -> None:
        self.assertFalse(broker.invia_ordine("SIMBOLO-INESISTENTE", "BUY", 0.1).ok)

    def test_riconnessione_se_il_terminale_sparisce(self) -> None:
        broker.connetti()
        finto.avviato = False  # l'utente ha chiuso MT5
        ok, conto, _ = broker.info_conto()
        self.assertTrue(ok, "il broker deve accorgersene e riconnettersi")
        self.assertTrue(finto.avviato)

    def test_chiusura_posizione(self) -> None:
        apertura = broker.invia_ordine("EURUSD", "BUY", 0.1)
        chiusura = broker.chiudi_posizione(apertura.ticket or 0)
        self.assertTrue(chiusura.ok, chiusura.messaggio)
        _, posizioni, _ = broker.posizioni_broker()
        self.assertEqual(len(posizioni), 0)


# ==========================================================================
# 5bis. Specifiche di contratto e tipo di conto
# ==========================================================================
class ProvaSpecifiche(BaseCollaudo):
    def setUp(self) -> None:
        super().setUp()
        broker.disconnetti()

    def test_specifiche_lette_dal_broker(self) -> None:
        ok, specifiche, messaggio = broker.specifiche_simbolo("EURUSD")
        self.assertTrue(ok, messaggio)
        self.assertEqual(specifiche["volume_min"], 0.01)
        self.assertEqual(specifiche["volume_step"], 0.01)

    def test_valore_punto_calcolato(self) -> None:
        """RISK-03 vuole il valore di 1 unita' di prezzo per 1 lotto.

        Con un tick da 0.00001 che vale 0.1, un punto intero vale 10000.
        E' il numero che chiude PA-62 misurandolo invece che stimandolo.
        """
        _, specifiche, _ = broker.specifiche_simbolo("EURUSD")
        self.assertAlmostEqual(specifiche["valore_punto"], 0.1 / 0.00001)

    def test_simbolo_inesistente(self) -> None:
        ok, specifiche, _ = broker.specifiche_simbolo("SIMBOLO-INESISTENTE")
        self.assertFalse(ok)
        self.assertIsNone(specifiche)

    def test_riconosce_il_conto_demo(self) -> None:
        finto.modo_conto = finto.ACCOUNT_TRADE_MODE_DEMO
        demo, messaggio = broker.conto_e_demo()
        self.assertTrue(demo, messaggio)
        self.assertIn("demo", messaggio)

    def test_rifiuta_il_conto_reale(self) -> None:
        """La prova di esecuzione non deve poter partire su un conto vero."""
        finto.modo_conto = finto.ACCOUNT_TRADE_MODE_REAL
        try:
            demo, messaggio = broker.conto_e_demo()
            self.assertFalse(demo)
            self.assertIn("REALE", messaggio)
        finally:
            finto.modo_conto = finto.ACCOUNT_TRADE_MODE_DEMO

    def test_rifiuta_anche_il_conto_contest(self) -> None:
        finto.modo_conto = finto.ACCOUNT_TRADE_MODE_CONTEST
        try:
            self.assertFalse(broker.conto_e_demo()[0])
        finally:
            finto.modo_conto = finto.ACCOUNT_TRADE_MODE_DEMO


# ==========================================================================
# 5ter. Il fornitore: analisi sul future di TradingView, esecuzione su CFD
# ==========================================================================
class ProvaSimboli(BaseCollaudo):
    """I tre mondi di nomi: TradingView, future di analisi, CFD operativo."""

    def test_ticker_tradingview_al_future(self) -> None:
        from core.simboli import future_da_ticker

        self.assertEqual(future_da_ticker("GC1!"), "GC")
        self.assertEqual(future_da_ticker("COMEX:GC1!"), "GC")
        self.assertEqual(future_da_ticker("CME:6J2!"), "6J")
        self.assertEqual(future_da_ticker("6E"), "6E")

    def test_ticker_sconosciuto(self) -> None:
        from core.simboli import future_da_ticker

        self.assertIsNone(future_da_ticker("AAPL"))
        self.assertIsNone(future_da_ticker("BTCUSD"))

    def test_future_al_cfd(self) -> None:
        """Si analizza su GC e si opera su XAUUSD (DEF-33)."""
        from core.simboli import cfd_di, future_di

        self.assertEqual(cfd_di("GC"), "XAUUSD")
        self.assertEqual(cfd_di("6J"), "USDJPY")
        self.assertEqual(future_di("EURUSD"), "6E")

    def test_il_dxy_e_di_sola_analisi(self) -> None:
        """PRIN-08: il DXY non e' uno strumento operativo."""
        from core.simboli import cfd_di, e_solo_analisi, future_da_ticker

        self.assertTrue(e_solo_analisi(future_da_ticker("ICEUS")))
        self.assertIsNone(cfd_di("ICEUS"))

    def test_intervallo_al_timeframe(self) -> None:
        from core.parametri import TF
        from core.simboli import timeframe_da_intervallo

        self.assertIs(timeframe_da_intervallo("60"), TF.H1)
        self.assertIs(timeframe_da_intervallo("240"), TF.H4)
        self.assertIs(timeframe_da_intervallo("1D"), TF.D1)
        self.assertIs(timeframe_da_intervallo("W"), TF.W1)

    def test_gli_intraday_di_crt04_sono_riconosciuti(self) -> None:
        """5 e 15 minuti sono timeframe di INGRESSO, non piu' scarti.

        Questa prova diceva il contrario, ed era il contrario giusto finche'
        valeva `DEF-01`. `CRT-04` accoppia quattro range a un ingresso sotto
        l'ora e quel vincolo e' stato sollevato: senza questi tre, quattro
        coppie di Romeo su sei non possono scattare.
        """
        from core.parametri import TF
        from core.simboli import timeframe_da_intervallo

        self.assertIs(timeframe_da_intervallo("1"), TF.MIN1)
        self.assertIs(timeframe_da_intervallo("5"), TF.MIN5)
        self.assertIs(timeframe_da_intervallo("15"), TF.MIN15)
        # La forma che manda il ciclo di mercato, non TradingView.
        self.assertIs(timeframe_da_intervallo("M15"), TF.MIN15)

    def test_intervallo_sconosciuto(self) -> None:
        """Un timeframe che il bot non tratta resta uno scarto."""
        from core.simboli import timeframe_da_intervallo

        self.assertIsNone(timeframe_da_intervallo("3"))
        self.assertIsNone(timeframe_da_intervallo("45"))
        self.assertIsNone(timeframe_da_intervallo("2H"))

    def test_suffisso_del_broker(self) -> None:
        from core.simboli import simbolo_esecuzione

        self.assertEqual(simbolo_esecuzione("EURUSD"), "EURUSD")
        self.assertEqual(simbolo_esecuzione("EURUSD", ".a"), "EURUSD.a")


class ProvaArchivioCandele(BaseCollaudo):
    """Le candele del future arrivano dagli alert e si accumulano."""

    def alert_candela(self, **modifiche) -> AlertIn:
        base = {
            "secret": "segreto-di-collaudo", "symbol": "GC1!", "tf": "1D",
            "candle_close_time_utc": "2026-03-10T22:00:00Z",
            "open": 4700.0, "high": 4750.0, "low": 4680.0, "close": 4730.0,
        }
        base.update(modifiche)
        return AlertIn.model_validate(base)

    def test_la_candela_viene_archiviata(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        archiviata, motivo = archivia_candela(self.alert_candela())
        self.assertTrue(archiviata, motivo)
        righe = storage.candele_archiviate("GC", "TF_1D")
        self.assertEqual(len(righe), 1)
        self.assertEqual(righe[0]["chiusura"], 4730.0)

    def test_lo_stesso_alert_non_duplica(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        archivia_candela(self.alert_candela())
        archivia_candela(self.alert_candela())
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_1D")), 1)

    def test_candele_diverse_si_accumulano(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        for giorno in (10, 11, 12):
            archivia_candela(self.alert_candela(
                candle_close_time_utc=f"2026-03-{giorno}T22:00:00Z"))
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_1D")), 3)

    def test_timeframe_separati(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        archivia_candela(self.alert_candela(tf="1D"))
        archivia_candela(self.alert_candela(tf="1W"))
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_1D")), 1)
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_1W")), 1)

    def test_strumento_fuori_da_prin08_non_archiviato(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        archiviata, motivo = archivia_candela(self.alert_candela(symbol="AAPL"))
        self.assertFalse(archiviata)
        self.assertIn("PRIN-08", motivo)

    def test_timeframe_sconosciuto_non_archiviato(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        archiviata, motivo = archivia_candela(self.alert_candela(tf="3"))
        self.assertFalse(archiviata)
        self.assertIn("DEF-01", motivo)

    def test_il_quarto_d_ora_ora_si_archivia(self) -> None:
        """Il timeframe di ingresso di `4h -> 15m` deve poter entrare."""
        from core.fornitore_tradingview import archivia_candela

        archiviata, motivo = archivia_candela(self.alert_candela(tf="15"))
        self.assertTrue(archiviata, motivo)
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_M15")), 1)

    def test_il_webhook_archivia_la_candela(self) -> None:
        """Il giro vero: alert dal webhook, candela in archivio."""
        riconfigura(FORNITORE_DATI="tradingview")
        try:
            with TestClient(main.app) as c:
                risposta = c.post("/webhook", json={
                    "secret": "segreto-di-collaudo", "symbol": "GC1!", "tf": "1D",
                    "candle_close_time_utc": "2026-03-10T22:00:00Z",
                    "open": 4700.0, "high": 4750.0, "low": 4680.0, "close": 4730.0,
                })
            self.assertEqual(risposta.status_code, 200)
            self.assertEqual(len(storage.candele_archiviate("GC", "TF_1D")), 1)
        finally:
            riconfigura(FORNITORE_DATI="nessuno")

    def test_copertura_dell_archivio(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        for giorno in range(10, 20):
            archivia_candela(self.alert_candela(
                candle_close_time_utc=f"2026-03-{giorno}T22:00:00Z"))
        copertura = storage.copertura_candele()
        self.assertEqual(len(copertura), 1)
        self.assertEqual(copertura[0]["quante"], 10)
        self.assertEqual(copertura[0]["strumento"], "GC")


class ProvaAllineamento(BaseCollaudo):
    """`high_c1`/`low_c1` verificano che grafico e archivio raccontino la stessa storia."""

    def prepara(self) -> None:
        from core.fornitore_tradingview import archivia_candela

        for giorno, (massimo, minimo) in enumerate(
            [(4750.0, 4680.0), (4760.0, 4700.0)], start=10
        ):
            archivia_candela(AlertIn.model_validate({
                "secret": "s", "symbol": "GC1!", "tf": "1D",
                "candle_close_time_utc": f"2026-03-{giorno}T22:00:00Z",
                "open": 4700.0, "high": massimo, "low": minimo, "close": 4730.0,
            }))

    def test_allineato(self) -> None:
        from core.fornitore_tradingview import verifica_allineamento
        from core.parametri import TF

        self.prepara()
        alert = AlertIn.model_validate({
            "secret": "s", "symbol": "GC1!", "tf": "1D",
            "candle_close_time_utc": "2026-03-12T22:00:00Z",
            "open": 4730.0, "high": 4770.0, "low": 4710.0, "close": 4750.0,
            "high_c1": 4750.0, "low_c1": 4680.0,
        })
        self.assertIsNone(verifica_allineamento(alert, "GC", TF.D1))

    def test_disallineato(self) -> None:
        """Se il grafico e l'archivio non concordano, uno dei due e' sbagliato."""
        from core.fornitore_tradingview import verifica_allineamento
        from core.parametri import TF

        self.prepara()
        alert = AlertIn.model_validate({
            "secret": "s", "symbol": "GC1!", "tf": "1D",
            "candle_close_time_utc": "2026-03-12T22:00:00Z",
            "open": 4730.0, "high": 4770.0, "low": 4710.0, "close": 4750.0,
            "high_c1": 9999.0, "low_c1": 4680.0,
        })
        motivo = verifica_allineamento(alert, "GC", TF.D1)
        self.assertIsNotNone(motivo)
        self.assertIn("9999", motivo)

    def test_c1_di_altra_provenienza_non_si_confronta(self) -> None:
        """Storico seminato da una fonte diversa: il confronto tace.

        Due fornitori ricostruiscono il contratto continuo con regole di
        rollover proprie. Pretendere che coincidano al decimale farebbe
        astenere il bot per sempre sulla giuntura fra storico seminato e alert
        dal vivo — cioe' esattamente al primo alert dopo l'installazione.
        """
        storage.salva_candele([
            {"strumento": "GC", "tf": "TF_1D", "chiusura_utc": "2026-03-10T00:00:00Z",
             "apertura": 100, "massimo": 110, "minimo": 90, "chiusura": 105},
            {"strumento": "GC", "tf": "TF_1D", "chiusura_utc": "2026-03-11T00:00:00Z",
             "apertura": 105, "massimo": 115, "minimo": 104, "chiusura": 112},
        ], origine="yahoo")
        alert = AlertIn(
            secret="segreto-di-collaudo", symbol="GC1!", tf="1D",
            candle_close_time_utc="2026-03-12T00:00:00Z",
            open=112, high=120, low=110, close=118,
            high_c1=999.0, low_c1=1.0,          # completamente diversi
        )
        from core.fornitore_tradingview import verifica_allineamento

        self.assertIsNone(
            verifica_allineamento(alert, "GC", TF.D1),
            "su una C1 di altra provenienza il controllo non deve scattare",
        )

    def test_senza_i_campi_non_si_verifica(self) -> None:
        """Sono facoltativi: senza, non e' un errore."""
        from core.fornitore_tradingview import verifica_allineamento
        from core.parametri import TF

        self.prepara()
        alert = AlertIn.model_validate({
            "secret": "s", "symbol": "GC1!", "tf": "1D",
            "candle_close_time_utc": "2026-03-12T22:00:00Z",
            "open": 4730.0, "high": 4770.0, "low": 4710.0, "close": 4750.0,
        })
        self.assertIsNone(verifica_allineamento(alert, "GC", TF.D1))


class ProvaFornitoreTradingView(BaseCollaudo):
    def setUp(self) -> None:
        super().setUp()
        broker.disconnetti()
        broker.connetti()

    def semina(self, quante: int = 40) -> None:
        """Riempie l'archivio come farebbe un'importazione da TradingView."""
        righe = []
        for tf in ("TF_1M", "TF_1W", "TF_1D", "TF_H12", "TF_H6", "TF_H4", "TF_H1"):
            for i in range(quante):
                righe.append({
                    "strumento": "6E", "tf": tf,
                    "chiusura_utc": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                    "apertura": 1.10 + i * 0.001, "massimo": 1.11 + i * 0.001,
                    "minimo": 1.09 + i * 0.001, "chiusura": 1.105 + i * 0.001,
                })
        storage.salva_candele(righe)

    def test_lo_storico_si_costruisce_dall_archivio(self) -> None:
        from core.fornitore_tradingview import FornitoreTradingView
        from core.parametri import TF

        self.semina()
        storico = FornitoreTradingView().storico("6E")
        self.assertGreater(len(storico[TF.D1]), 0)
        self.assertIn(TF.M3, storico, "i trimestrali si aggregano dai mensili")

    def test_le_candele_sono_in_ordine(self) -> None:
        from core.fornitore_tradingview import FornitoreTradingView
        from core.parametri import TF

        self.semina()
        candele = FornitoreTradingView().storico("6E")[TF.D1]
        orari = [c.orario for c in candele]
        self.assertEqual(orari, sorted(orari))

    def test_il_dxy_non_innesca_valutazioni(self) -> None:
        """PRIN-08: si analizza, non si opera."""
        from core.fornitore_tradingview import FornitoreTradingView

        alert = AlertIn.model_validate({
            "secret": "s", "symbol": "ICEUS", "tf": "1D",
            "candle_close_time_utc": "2026-03-10T22:00:00Z",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        })
        from core.fornitore_tradingview import FotografiaImpossibile

        with self.assertRaises(FotografiaImpossibile) as caso:
            FornitoreTradingView().costruisci(alert)
        self.assertIn("PRIN-08", str(caso.exception),
                      "il motivo dell'astensione deve arrivare a chi legge l'archivio")

    def test_la_catena_completa(self) -> None:
        """Alert sul future -> archivio -> motore -> decisione sul CFD."""
        from core import strategy
        from core.fornitore_tradingview import FornitoreTradingView

        self.semina()
        strategy.registra_fornitore(FornitoreTradingView().costruisci)
        try:
            decisione = valuta(AlertIn.model_validate({
                "secret": "s", "symbol": "6E1!", "tf": "60",
                "candle_close_time_utc": "2026-03-10T22:00:00Z",
                "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.105,
            }))
            self.assertIn(decisione.azione, ("NONE", "BUY", "SELL"))
            self.assertTrue(decisione.motivo)
        finally:
            strategy.registra_fornitore(None)

    def test_nessun_prezzo_di_analisi_arriva_da_mt5(self) -> None:
        """ESCL-12: i prezzi di analisi vengono dal future, non dal broker.

        Se il fornitore leggesse le candele da MT5, azzerare l'archivio non
        cambierebbe niente. Deve invece far tacere tutto.
        """
        from core.fornitore_tradingview import FornitoreTradingView
        from core.parametri import TF

        self.semina()
        pieno = FornitoreTradingView().storico("6E")
        self.assertGreater(len(pieno[TF.D1]), 0)

        with storage.connessione(scrittura=True) as conn:
            conn.execute("DELETE FROM candela")

        vuoto = FornitoreTradingView().storico("6E")
        self.assertEqual(len(vuoto[TF.D1]), 0,
                         "senza archivio non ci sono prezzi: non li prende da MT5")


# ==========================================================================
# 6. La sentinella
# ==========================================================================
class ProvaSentinella(BaseCollaudo):
    def setUp(self) -> None:
        super().setUp()
        broker.disconnetti()
        broker.connetti()
        self.sentinella = modulo_sentinella.Sentinella()

    def _apri_in_archivio(self, sl: float | None, tp: float | None) -> int:
        esito = broker.invia_ordine("EURUSD", "BUY", 0.1)
        return storage.registra_posizione(
            "EURUSD", "BUY", 0.1, ticket=esito.ticket, prezzo_ingresso=esito.prezzo, sl=sl, tp=tp
        )

    def test_stop_toccato_chiude(self) -> None:
        id_posizione = self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.bid, finto.ask = 1.09850, 1.09860  # il prezzo scende sotto lo stop
        risultato = self.sentinella.giro()
        self.assertEqual(risultato["chiuse"], 1)
        self.assertEqual(len(storage.posizioni_aperte()), 0)
        self.assertEqual(len(finto.posizioni), 0, "la posizione deve sparire anche dal broker")

    def test_target_toccato_chiude(self) -> None:
        self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.bid, finto.ask = 1.10600, 1.10610
        self.assertEqual(self.sentinella.giro()["chiuse"], 1)

    def test_prezzo_in_mezzo_non_chiude(self) -> None:
        self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.bid, finto.ask = 1.10200, 1.10210
        self.assertEqual(self.sentinella.giro()["chiuse"], 0)
        self.assertEqual(len(storage.posizioni_aperte()), 1)

    def test_posizione_senza_livelli_resta_aperta(self) -> None:
        self._apri_in_archivio(sl=None, tp=None)
        finto.bid, finto.ask = 0.5, 0.5
        self.assertEqual(self.sentinella.giro()["chiuse"], 0)

    def test_short_si_chiude_sullo_spread_giusto(self) -> None:
        """Short con stop a 1.10500: il bid e' ancora sotto, ma l'ask lo ha
        toccato. La posizione va chiusa: e' l'ask che ci fa uscire."""
        esito = broker.invia_ordine("EURUSD", "SELL", 0.1)
        storage.registra_posizione(
            "EURUSD", "SELL", 0.1, ticket=esito.ticket, prezzo_ingresso=esito.prezzo,
            sl=1.10500, tp=1.09000,
        )
        finto.bid, finto.ask = 1.10000, 1.10600
        self.assertEqual(self.sentinella.giro()["chiuse"], 1)

    def test_short_non_si_chiude_se_solo_il_bid_ha_toccato(self) -> None:
        esito = broker.invia_ordine("EURUSD", "SELL", 0.1)
        storage.registra_posizione(
            "EURUSD", "SELL", 0.1, ticket=esito.ticket, sl=1.10500, tp=1.09000,
        )
        finto.bid, finto.ask = 1.08900, 1.09100  # bid sotto il target, ask no
        self.assertEqual(self.sentinella.giro()["chiuse"], 0)

    def test_riconciliazione_chiusura_esterna(self) -> None:
        """Posizione chiusa a mano su MT5: l'archivio deve allinearsi."""
        self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.posizioni.clear()  # chiusa fuori dal bot
        self.sentinella.giro()
        aperte = storage.posizioni_aperte()
        self.assertEqual(len(aperte), 0)

    def test_chiusura_fallita_lascia_la_posizione_aperta(self) -> None:
        """Se la chiusura non riesce, l'archivio non deve mentire: al prossimo
        giro si deve riprovare."""
        self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.bid, finto.ask = 1.09000, 1.09010
        finto.ordine_fallisce = True
        try:
            self.assertEqual(self.sentinella.giro()["chiuse"], 0)
            self.assertEqual(len(storage.posizioni_aperte()), 1, "resta aperta, si riprova dopo")
        finally:
            finto.ordine_fallisce = False
        self.assertEqual(self.sentinella.giro()["chiuse"], 1, "al giro dopo la chiusura riesce")

    # -- TP1: il parziale del 25% e il break even (GEST-04, GEST-07) -------

    def _apri_con_tp1(self, direzione: str = "BUY", volume: float = 0.40) -> int:
        esito = broker.invia_ordine("EURUSD", direzione, volume)
        segno = 1 if direzione == "BUY" else -1
        return storage.registra_posizione(
            "EURUSD", direzione, volume, ticket=esito.ticket,
            prezzo_ingresso=1.10000,
            sl=1.10000 - segno * 0.00200,
            tp=1.10000 + segno * 0.00500,
            tp1=1.10000 + segno * 0.00200,
            tf_crt="TF_H4",
            spread_ingresso=0.00010,
        )

    def test_tp1_chiude_un_quarto_e_porta_a_pareggio(self) -> None:
        id_posizione = self._apri_con_tp1()
        finto.bid, finto.ask = 1.10250, 1.10260     # oltre TP1, sotto il target
        self.assertEqual(self.sentinella.giro()["chiuse"], 0, "TP1 non chiude tutto")

        aperte = storage.posizioni_aperte()
        self.assertEqual(len(aperte), 1)
        riga = aperte[0]
        self.assertAlmostEqual(riga["volume"], 0.30, places=6)
        self.assertEqual(riga["tp1_raggiunto"], 1)
        # Break even col buffer di PA-46: ingresso + k x spread d'ingresso.
        self.assertGreater(riga["sl"], 1.10000, "lo stop va sopra l'ingresso, non sotto")
        self.assertLess(riga["sl"], 1.10100)
        # E il broker ha davvero ridotto il volume, non chiuso tutto.
        self.assertEqual(len(finto.posizioni), 1)
        self.assertAlmostEqual(finto.posizioni[0].volume, 0.30, places=6)

    def test_tp1_avviene_una_volta_sola(self) -> None:
        """GEST-05 — dopo il break even lo stop non si muove piu'."""
        self._apri_con_tp1()
        finto.bid, finto.ask = 1.10250, 1.10260
        self.sentinella.giro()
        stop_dopo = storage.posizioni_aperte()[0]["sl"]

        finto.bid, finto.ask = 1.10400, 1.10410     # sale ancora
        self.sentinella.giro()
        riga = storage.posizioni_aperte()[0]
        self.assertAlmostEqual(riga["volume"], 0.30, places=6, msg="nessun secondo parziale")
        self.assertEqual(riga["sl"], stop_dopo, "lo stop non si muove piu'")

    def test_dopo_tp1_lo_stop_a_pareggio_chiude_il_residuo(self) -> None:
        self._apri_con_tp1()
        finto.bid, finto.ask = 1.10250, 1.10260
        self.sentinella.giro()
        finto.bid, finto.ask = 1.09990, 1.10000     # torna indietro sul pareggio
        self.assertEqual(self.sentinella.giro()["chiuse"], 1)
        self.assertEqual(len(storage.posizioni_aperte()), 0)

    def test_short_il_parziale_guarda_lask(self) -> None:
        self._apri_con_tp1(direzione="SELL")
        finto.bid, finto.ask = 1.09740, 1.09810     # bid sotto TP1, ask sopra
        self.sentinella.giro()
        self.assertEqual(storage.posizioni_aperte()[0]["tp1_raggiunto"], 0,
                         "e' l'ask che ci fa uscire da uno short")
        finto.bid, finto.ask = 1.09740, 1.09790
        self.sentinella.giro()
        riga = storage.posizioni_aperte()[0]
        self.assertEqual(riga["tp1_raggiunto"], 1)
        self.assertLess(riga["sl"], 1.10000, "su uno short il pareggio sta sotto l'ingresso")

    def test_stop_vince_su_tp1_nello_stesso_giro(self) -> None:
        """Fra due letture possibili si sceglie la peggiore."""
        self._apri_con_tp1()
        finto.bid, finto.ask = 1.09700, 1.09710     # sotto lo stop
        self.assertEqual(self.sentinella.giro()["chiuse"], 1)

    def test_size_minima_non_fa_parziale_ne_pareggio(self) -> None:
        """Un quarto di 0.01 lotti non esiste: la posizione prosegue intera.

        Applicare il break even senza aver incassato il parziale cambierebbe
        l'operazione in una che le regole non descrivono.
        """
        esito = broker.invia_ordine("EURUSD", "BUY", 0.01)
        storage.registra_posizione(
            "EURUSD", "BUY", 0.01, ticket=esito.ticket, prezzo_ingresso=1.10000,
            sl=1.09800, tp=1.10500, tp1=1.10200, spread_ingresso=0.00010,
        )
        finto.bid, finto.ask = 1.10250, 1.10260
        self.sentinella.giro()
        riga = storage.posizioni_aperte()[0]
        self.assertAlmostEqual(riga["volume"], 0.01, places=6)
        self.assertEqual(riga["sl"], 1.09800, "lo stop resta quello iniziale")
        self.assertEqual(riga["tp1_raggiunto"], 1, "ma non ci si riprova a ogni giro")

    def test_posizione_vecchia_senza_tp1_si_comporta_come_prima(self) -> None:
        """Le posizioni aperte prima della migrazione non hanno TP1: devono
        continuare a vivere con stop e target soli."""
        self._apri_in_archivio(sl=1.09900, tp=1.10500)
        finto.bid, finto.ask = 1.10200, 1.10210
        self.assertEqual(self.sentinella.giro()["chiuse"], 0)
        self.assertEqual(len(storage.posizioni_aperte()), 1)

    def test_un_giro_fallito_non_uccide_il_ciclo(self) -> None:
        self._apri_in_archivio(sl=1.09900, tp=None)
        originale = broker.posizioni_broker
        broker.posizioni_broker = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rete giu'"))
        try:
            self.sentinella._giro_protetto()
        finally:
            broker.posizioni_broker = originale
        self.assertIsNotNone(self.sentinella.ultimo_errore)
        # e il giro successivo torna a funzionare
        self.assertEqual(self.sentinella.giro()["chiuse"], 0)



# ==========================================================================
# 6bis. L'aritmetica dei livelli, caso per caso
# ==========================================================================
class ProvaLivelli(unittest.TestCase):
    """Il cuore della sentinella: quando un livello e' toccato davvero.

    I casi SELL sono quelli che contano: una posizione corta si chiude in
    ASK, non in bid. Confrontare lo stop col prezzo sbagliato fa scattare le
    uscite qualche pip prima o dopo, ogni volta, su ogni operazione.
    """

    CASI = [
        # (direzione, bid,     ask,     sl,      tp,      atteso)
        ("BUY",  1.09900, 1.09910, 1.09950, 1.10500, "sl"),
        ("BUY",  1.10000, 1.10010, 1.09950, 1.10500, None),
        ("BUY",  1.10550, 1.10560, 1.09950, 1.10500, "tp"),
        ("BUY",  1.09950, 1.09960, 1.09950, 1.10500, "sl"),   # esattamente sul livello
        # Su una short lo stop e' sopra: si guarda l'ask, non il bid.
        ("SELL", 1.10000, 1.10600, 1.10500, 1.09000, "sl"),   # bid sotto, ask sopra -> stop
        ("SELL", 1.10400, 1.10410, 1.10500, 1.09000, None),
        ("SELL", 1.08900, 1.08950, 1.10500, 1.09000, "tp"),   # ask sotto il target
        ("SELL", 1.08900, 1.09100, 1.10500, 1.09000, None),   # bid sotto ma ask no: non basta
        ("SELL", 1.10500, 1.10500, 1.10500, 1.09000, "sl"),   # esattamente sul livello
        # Un solo livello impostato.
        ("BUY",  1.09900, 1.09910, None,    1.10500, None),
        ("BUY",  1.09900, 1.09910, 1.09950, None,    "sl"),
        ("SELL", 1.10000, 1.10600, None,    1.09000, None),
        # Entrambi toccati nello stesso istante: vince lo stop.
        ("BUY",  1.09900, 1.09910, 1.09950, 1.09800, "sl"),
        ("SELL", 1.10600, 1.10600, 1.10500, 1.10700, "sl"),
        # Direzione sconosciuta: non si tocca niente.
        ("BOH",  1.00000, 1.00000, 1.00000, 1.00000, None),
    ]

    def test_tabella(self) -> None:
        for direzione, bid, ask, sl, tp, atteso in self.CASI:
            with self.subTest(direzione=direzione, bid=bid, ask=ask, sl=sl, tp=tp):
                self.assertEqual(
                    modulo_sentinella.livello_toccato(direzione, bid, ask, sl, tp), atteso
                )


# ==========================================================================
# 7. Archivio
# ==========================================================================
class ProvaArchivio(BaseCollaudo):
    def test_il_segreto_non_finisce_in_archivio(self) -> None:
        with TestClient(main.app) as c:
            c.post("/webhook", json=alert_finto())
        with storage.connessione() as conn:
            righe = conn.execute("SELECT payload_json FROM alert").fetchall()
        self.assertNotIn("segreto-di-collaudo", righe[0]["payload_json"])
        self.assertNotIn("secret", righe[0]["payload_json"])

    def test_migrazione_da_schema_precedente(self) -> None:
        """Un archivio creato dalla versione senza impronta deve sopravvivere."""
        import sqlite3

        percorso = os.path.join(_CARTELLA, "vecchio.db")
        for coda in ("", "-wal", "-shm"):
            if os.path.exists(percorso + coda):
                os.remove(percorso + coda)
        conn = sqlite3.connect(percorso)
        conn.executescript(
            """
            CREATE TABLE alert (id INTEGER PRIMARY KEY AUTOINCREMENT, ricevuto_utc TEXT NOT NULL,
              simbolo TEXT NOT NULL, tf TEXT NOT NULL, chiusura_candela_utc TEXT NOT NULL,
              apertura REAL NOT NULL, massimo REAL NOT NULL, minimo REAL NOT NULL,
              chiusura REAL NOT NULL, rsi REAL, nota TEXT, payload_json TEXT NOT NULL);
            INSERT INTO alert VALUES (NULL,'x','EURUSD','15','x',1,1,1,1,NULL,'vecchio','{}');
            """
        )
        conn.commit()
        conn.close()

        riconfigura(DB_PATH=percorso)
        try:
            storage.inizializza()
            self.assertEqual(storage.conteggi()["alert"], 1, "le righe vecchie non si perdono")
            nuovo, duplicato = storage.salva_alert(AlertIn.model_validate(alert_finto()))
            self.assertFalse(duplicato)
            self.assertEqual(storage.conteggi()["alert"], 2)
        finally:
            riconfigura(DB_PATH=os.path.join(_CARTELLA, "collaudo.db"))


# ==========================================================================
# 8. Endpoint di salute
# ==========================================================================
class ProvaSalute(BaseCollaudo):
    def test_riporta_lo_stato(self) -> None:
        with TestClient(main.app) as c:
            stato = c.get("/salute").json()
        for chiave in ("modalita", "mt5_disponibile", "equity", "posizioni_aperte_broker",
                       "sentinella", "salvaguardie", "posizioni_scoperte"):
            self.assertIn(chiave, stato)
        self.assertEqual(stato["modalita"], "dry_run")

    def test_segnala_le_posizioni_scoperte(self) -> None:
        storage.registra_posizione("EURUSD", "BUY", 0.1, ticket=999, sl=1.0)
        with TestClient(main.app) as c:
            stato = c.get("/salute").json()
        self.assertTrue(stato["posizioni_scoperte"], "posizioni aperte senza sentinella = allarme")


# ==========================================================================
# 9. Scaricamento automatico dello storico (nessuna rete: risposte finte)
# ==========================================================================
class ProvaScaricoStorico(BaseCollaudo):
    """La fonte gratuita non e' un'API con contratto: puo' rispondere altro.

    Il collaudo interessante e' quello sul passo delle barre. Chiedendo barre
    giornaliere su tutto lo storico, la fonte non risponde con un errore:
    risponde con **barre mensili**. Senza il controllo finirebbero in archivio
    con l'etichetta sbagliata e il motore ragionerebbe su una scala che non e'
    quella che crede — senza che nulla lo segnali.
    """

    GIORNO = 86_400
    MESE = 2_678_400

    def risposta(self, passo: int, quante: int = 6, buchi: bool = False) -> dict:
        base = 1_700_000_000
        orari = [base + i * passo for i in range(quante)]
        aperture = [100.0 + i for i in range(quante)]
        massimi = [110.0 + i for i in range(quante)]
        minimi = [90.0 + i for i in range(quante)]
        chiusure = [105.0 + i for i in range(quante)]
        if buchi:
            massimi[1] = None
            chiusure[2] = None
        return {"chart": {"result": [{
            "meta": {"symbol": "GC=F"},
            "timestamp": orari,
            "indicators": {"quote": [{
                "open": aperture, "high": massimi, "low": minimi, "close": chiusure,
            }]},
        }]}}

    def test_il_passo_giusto_passa(self) -> None:
        import scarica_storico as sc

        barre = sc.in_barre(self.risposta(self.GIORNO), sc.INTERVALLI[TF.D1])
        self.assertEqual(len(barre), 6)

    def test_barre_mensili_spacciate_per_giornaliere(self) -> None:
        """CASO CRITICO: e' successo davvero, alla prima esecuzione vera."""
        import scarica_storico as sc

        with self.assertRaises(sc.ScaricoFallito) as caso:
            sc.in_barre(self.risposta(self.MESE), sc.INTERVALLI[TF.D1])
        self.assertIn("secondi", str(caso.exception))

    def test_barre_giornaliere_spacciate_per_orarie(self) -> None:
        import scarica_storico as sc

        with self.assertRaises(sc.ScaricoFallito):
            sc.in_barre(self.risposta(self.GIORNO), sc.INTERVALLI[TF.H1])

    def test_il_prezzo_di_adesso_non_e_una_barra(self) -> None:
        """CASO CRITICO, trovato alla prima esecuzione vera sulle orarie.

        La fonte appende in coda una voce marcata con l'istante corrente
        invece che con l'inizio di un periodo. Siccome `in_candele` scarta
        sempre l'ultima voce, quella scartata sarebbe il segnaposto e la
        candela ANCORA IN FORMAZIONE passerebbe per chiusa, con un orario che
        non cade nemmeno su un'ora tonda. Lookahead di un periodo intero.
        """
        import scarica_storico as sc

        risposta = self.risposta(3_600, quante=6)
        risultato = risposta["chart"]["result"][0]
        # ... e in coda il prezzo di adesso, otto minuti dopo l'ultima ora.
        risultato["timestamp"].append(risultato["timestamp"][-1] + 531)
        for campo, valore in (("open", 1.0), ("high", 2.0), ("low", 0.5), ("close", 1.5)):
            risultato["indicators"]["quote"][0][campo].append(valore)

        barre = sc.in_barre(risposta, sc.INTERVALLI[TF.H1])
        self.assertEqual(len(barre), 6, "il segnaposto non e' una barra")
        for barra in barre:
            self.assertEqual(barra["apertura_utc"].minute, barra["apertura_utc"].minute,
                             "gli orari restano quelli del periodo")
        ultimo = barre[-1]["apertura_utc"]
        self.assertEqual((ultimo.minute, ultimo.second), (barre[0]["apertura_utc"].minute,
                                                          barre[0]["apertura_utc"].second),
                         "l'ultima barra e' allineata come le altre, non all'istante corrente")

    def test_una_barra_finale_regolare_non_viene_tolta(self) -> None:
        import scarica_storico as sc

        barre = sc.in_barre(self.risposta(3_600, quante=6), sc.INTERVALLI[TF.H1])
        self.assertEqual(len(barre), 6)

    def test_le_barre_senza_prezzi_si_scartano(self) -> None:
        """Giorni di chiusura e buchi della fonte: niente prezzo, niente candela."""
        import scarica_storico as sc

        barre = sc.in_barre(self.risposta(self.GIORNO, buchi=True), sc.INTERVALLI[TF.D1])
        self.assertEqual(len(barre), 4)

    def test_risposta_vuota(self) -> None:
        import scarica_storico as sc

        for corpo in ({"chart": {"result": []}}, {"chart": {"result": [{"meta": {}}]}}, {}):
            with self.assertRaises(sc.ScaricoFallito):
                sc.in_barre(corpo, sc.INTERVALLI[TF.D1])

    def test_ogni_strumento_di_prin08_ha_un_ticker(self) -> None:
        import scarica_storico as sc

        sc.verifica()
        self.assertEqual(set(sc.TICKER_FONTE), set(FUTURE_A_CFD) | {"ICEUS"})
        for ticker in sc.TICKER_FONTE.values():
            self.assertNotIn("XAU", ticker, "si scarica il future, non il CFD")
            self.assertNotIn("USD=X", ticker, "e nemmeno il cambio a pronti")

    def test_lo_stato_http_diventa_un_errore_parlante(self) -> None:
        import scarica_storico as sc

        class ClienteFinto:
            def get(self, url, params=None):
                return Oggetto(status_code=429, json=lambda: {})

        with self.assertRaises(sc.ScaricoFallito) as caso:
            sc.scarica("GC=F", sc.INTERVALLI[TF.D1], ClienteFinto())
        self.assertIn("429", str(caso.exception))

    def test_la_catena_completa_senza_rete(self) -> None:
        """Risposta finta -> barre -> candele chiuse -> archivio."""
        import scarica_storico as sc
        from importa_storico import in_candele

        class ClienteFinto:
            def __init__(self, corpo): self.corpo = corpo
            def get(self, url, params=None):
                return Oggetto(status_code=200, json=lambda: self.corpo)

        barre = sc.scarica("GC=F", sc.INTERVALLI[TF.D1],
                           ClienteFinto(self.risposta(self.GIORNO)))
        righe, riparate = in_candele(barre, "GC", TF.D1)
        self.assertEqual(len(righe), 5, "l'ultima barra e' quella in corso")
        self.assertEqual(riparate, 0)
        nuove, _ = storage.salva_candele(righe, origine=sc.ORIGINE)
        self.assertEqual(nuove, 5)
        archiviate = storage.candele_archiviate("GC", "TF_1D")
        self.assertEqual(archiviate[0]["origine"], "yahoo",
                         "la provenienza si registra: non tutti i dati vengono da TradingView")


# ==========================================================================
# 10. Si analizza sul future, si opera sul CFD: anche all'ultimo passo
# ==========================================================================
class ProvaSimboloDiEsecuzione(BaseCollaudo):
    """CASO CRITICO: la decisione nasce sul future e l'ordine deve partire
    sul CFD. Mandare al broker il ticker del future significa chiedergli un
    contratto che non quota, e l'ordine muore senza che sia chiaro perche'.
    """

    def test_la_decisione_porta_il_simbolo_di_esecuzione(self) -> None:
        from core.motore import Decisione as DecisioneMotore
        from core.strategy import traduci

        tradotta = traduci(DecisioneMotore(
            azione="BUY", strumento="XAUUSD", motivo="prova",
            volume=0.05, livello_stop=1.0, target_finale=2.0,
            regole_applicate=("SETUP-00",), regole_che_bloccano=(),
        ))
        self.assertEqual(tradotta.simbolo, "XAUUSD",
                         "il motore decide per il CFD: la traduzione non deve perderlo")

    def test_il_suffisso_del_broker_viene_aggiunto(self) -> None:
        riconfigura(MT5_SUFFISSO_SIMBOLI=".a")
        try:
            alert = AlertIn(secret="segreto-di-collaudo", symbol="GC1!", tf="1D",
                            candle_close_time_utc="2026-03-10T00:00:00Z",
                            open=1, high=2, low=1, close=2)
            decisione = Decision(action="BUY", symbol="XAUUSD", volume=0.05)
            self.assertEqual(main.simbolo_da_eseguire(alert, decisione), "XAUUSD.a")
        finally:
            riconfigura(MT5_SUFFISSO_SIMBOLI="")

    def test_senza_simbolo_non_si_ripiega_sull_alert(self) -> None:
        """Ripiegare su alert.simbolo manderebbe GC1! al broker."""
        alert = AlertIn(secret="segreto-di-collaudo", symbol="GC1!", tf="1D",
                        candle_close_time_utc="2026-03-10T00:00:00Z",
                        open=1, high=2, low=1, close=2)
        self.assertIsNone(main.simbolo_da_eseguire(alert, Decision(action="BUY", volume=0.05)))

    def test_al_broker_arriva_il_cfd_non_il_future(self) -> None:
        """Il giro vero, in modalita' auto, con il MetaTrader5 finto."""
        riconfigura(MODE="auto")
        finto.ordini_inviati.clear()
        try:
            adesso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            alert = AlertIn(secret="segreto-di-collaudo", symbol="GC1!", tf="1D",
                            candle_close_time_utc=adesso,
                            open=1, high=2, low=1, close=2)
            # Senza sl/tp: qui si collauda il simbolo, e una decisione con
            # livelli verrebbe giustamente bloccata dalla salvaguardia che
            # vuole la sentinella accesa (provata altrove).
            decisione = Decision(action="BUY", symbol="XAUUSD", volume=0.05,
                                 motivo="prova")
            id_alert, _ = storage.salva_alert(alert)
            esito, dettaglio, ticket, _ = main._esegui_decisione(alert, decisione, id_alert)
            self.assertEqual(esito, "eseguito", dettaglio)
            self.assertEqual(finto.ordini_inviati[-1]["symbol"], "XAUUSD",
                             "al broker non deve mai arrivare il ticker del future")
        finally:
            riconfigura(MODE="dry_run")


# ==========================================================================
# 11. Il bot si prende i dati da solo (nessuna rete: risposte finte)
# ==========================================================================
class ProvaMercato(BaseCollaudo):
    """Niente alert da configurare: e' il bot che va a cercare le candele.

    Le prove che contano sono due: che non si rivaluti il passato dopo uno
    spegnimento, e che ripassare sulla stessa candela non apra due ordini.
    """

    def setUp(self) -> None:
        super().setUp()
        from core.mercato import Mercato

        self.mercato = Mercato(intervallo_sec=0.0)
        self.visti: list = []
        self.mercato.su_candela = self.visti.append

    def cliente(self, quante: int = 6, passo: int = 86_400, base: int = 1_700_000_000):
        corpo = {"chart": {"result": [{
            "meta": {"symbol": "GC=F"},
            "timestamp": [base + i * passo for i in range(quante)],
            "indicators": {"quote": [{
                "open": [100.0 + i for i in range(quante)],
                "high": [110.0 + i for i in range(quante)],
                "low": [90.0 + i for i in range(quante)],
                "close": [105.0 + i for i in range(quante)],
            }]},
        }]}}

        class ClienteFinto:
            def get(self, url, params=None):
                return Oggetto(status_code=200, json=lambda: corpo)

        return ClienteFinto()

    # -- quando ha senso chiedere una serie --------------------------------
    def test_archivio_vuoto_si_chiede_sempre(self) -> None:
        adesso = datetime(2026, 3, 10, tzinfo=timezone.utc)
        self.assertTrue(self.mercato.serie_da_chiedere("GC", TF.D1, adesso))

    def test_serie_appena_aggiornata_non_si_richiede(self) -> None:
        storage.salva_candele([{
            "strumento": "GC", "tf": "TF_1D", "chiusura_utc": "2026-03-10T00:00:00Z",
            "apertura": 1, "massimo": 2, "minimo": 1, "chiusura": 2}], origine="mercato")
        adesso = datetime(2026, 3, 10, 6, tzinfo=timezone.utc)
        self.assertFalse(self.mercato.serie_da_chiedere("GC", TF.D1, adesso),
                         "chiedere di nuovo prima che il periodo sia finito e' rumore")

    def test_serie_scaduta_si_richiede(self) -> None:
        storage.salva_candele([{
            "strumento": "GC", "tf": "TF_1D", "chiusura_utc": "2026-03-10T00:00:00Z",
            "apertura": 1, "massimo": 2, "minimo": 1, "chiusura": 2}], origine="mercato")
        adesso = datetime(2026, 3, 12, tzinfo=timezone.utc)
        self.assertTrue(self.mercato.serie_da_chiedere("GC", TF.D1, adesso))

    # -- archiviazione ------------------------------------------------------
    def test_archivia_le_candele_chiuse(self) -> None:
        nuove = self.mercato.aggiorna("GC", TF.D1, self.cliente())
        self.assertEqual(len(nuove), 5, "sei barre, l'ultima e' in formazione")
        self.assertEqual(len(storage.candele_archiviate("GC", "TF_1D")), 5)

    def test_ripassare_non_riarchivia(self) -> None:
        self.mercato.aggiorna("GC", TF.D1, self.cliente())
        self.assertEqual(self.mercato.aggiorna("GC", TF.D1, self.cliente()), [])

    # -- CTX-10: non si valuta su un archivio superiore stantio -------------
    def test_ctx10_un_superiore_fallito_ferma_la_valutazione(self) -> None:
        """CTX-10 — l'analisi del timeframe chiuso va ricalcolata PRIMA di
        operare sui timeframe inferiori.

        Se lo scarico di TF_1D fallisce, la bias e i key level che il motore
        leggerebbe valutando TF_H1 sono quelli di prima. L'eccezione veniva
        loggata e la valutazione proseguiva lo stesso.
        """
        orarie = self.mercato.aggiorna("GC", TF.H1, self.cliente(passo=3600))
        self.mercato._valuta_le_ultime(orarie, falliti={("GC", TF.D1)})
        self.assertEqual(self.visti, [], "TF_1D non aggiornato: TF_H1 non si valuta")
        self.assertEqual(self.mercato.saltate_per_ctx10, 1)

    def test_ctx10_un_inferiore_fallito_non_ferma_nulla(self) -> None:
        """Il vincolo e' a senso unico: guarda in su, non in giu'."""
        giornaliere = self.mercato.aggiorna("GC", TF.D1, self.cliente())
        self.mercato._valuta_le_ultime(giornaliere, falliti={("GC", TF.H1)})
        self.assertEqual(len(self.visti), 1)

    def test_ctx10_un_altro_strumento_non_ferma_nulla(self) -> None:
        giornaliere = self.mercato.aggiorna("GC", TF.D1, self.cliente())
        self.mercato._valuta_le_ultime(giornaliere, falliti={("6E", TF.M1)})
        self.assertEqual(len(self.visti), 1)

    # -- valutazione --------------------------------------------------------
    def test_dopo_uno_spegnimento_valuta_solo_l_ultima(self) -> None:
        """CASO CRITICO: cinque candele arretrate non sono cinque ordini."""
        nuove = self.mercato.aggiorna("GC", TF.D1, self.cliente())
        self.mercato._valuta_le_ultime(nuove)
        self.assertEqual(len(self.visti), 1,
                         "le arretrate entrano in archivio, ma si decide solo sull'ultima")
        piu_recente = max(n.riga["chiusura_utc"] for n in nuove)
        self.assertEqual(self.visti[0].chiusura_candela_utc, piu_recente)

    def test_il_dxy_non_innesca_valutazioni(self) -> None:
        from core.mercato import Nuova

        self.mercato._valuta_le_ultime([Nuova("ICEUS", TF.D1, {
            "chiusura_utc": "2026-03-10T00:00:00Z", "apertura": 1,
            "massimo": 2, "minimo": 1, "chiusura": 2})])
        self.assertEqual(self.visti, [], "PRIN-08: sul DXY si analizza, non si opera")

    def test_la_mensile_ora_e_un_timeframe_di_ingresso(self) -> None:
        """CRT-04 — `M1 -> D1` e' la coppia canonica di Romeo.

        Fino a oggi la mensile aggiornava solo la bias e non innescava nulla.
        E' cambiato di proposito: `M1 -> D1` e' l'unica configurazione che
        risulta positiva al netto dello spread reale (+0,1008 R contro un
        costo di 0,071 R), perche' su stop larghi lo spread pesa molto meno
        che sulle coppie orarie.
        """
        from core.mercato import Nuova

        self.mercato._valuta_le_ultime([Nuova("GC", TF.M1, {
            "chiusura_utc": "2026-03-10T00:00:00Z", "apertura": 1,
            "massimo": 2, "minimo": 1, "chiusura": 2})])
        self.assertEqual(len(self.visti), 1, "la chiusura mensile innesca")
        self.assertEqual(self.visti[0].tf, "1M")

    def test_i_timeframe_di_sola_bias_non_innescano(self) -> None:
        """`TF_1W` e i trimestrali danno la bias di comando (SETUP-06) ma non
        sono coppie di CRT-04: non aprono nulla."""
        from core.mercato import Nuova

        self.mercato._valuta_le_ultime([Nuova("GC", TF.W1, {
            "chiusura_utc": "2026-03-10T00:00:00Z", "apertura": 1,
            "massimo": 2, "minimo": 1, "chiusura": 2})])
        self.assertEqual(self.visti, [], "la settimanale aggiorna la bias, non apre")

    # -- il ponte verso il resto dell'impianto ------------------------------
    def test_l_alert_costruito_e_comprensibile_al_motore(self) -> None:
        from core.mercato import Nuova, in_alert
        from core.simboli import future_da_ticker, timeframe_da_intervallo

        for tf in (TF.H1, TF.D1, TF.W1, TF.M1):
            alert = in_alert(Nuova("GC", tf, {
                "chiusura_utc": "2026-03-10T00:00:00Z", "apertura": 1.0,
                "massimo": 2.0, "minimo": 0.5, "chiusura": 1.5}))
            self.assertEqual(future_da_ticker(alert.simbolo), "GC")
            self.assertEqual(timeframe_da_intervallo(alert.tf), tf,
                             f"il motore deve riconoscere il timeframe {tf.value}")

    def test_la_stessa_candela_non_apre_due_ordini(self) -> None:
        """L'impronta protegge: il ciclo puo' ripassare quanto vuole."""
        from core.mercato import Nuova, in_alert

        nuova = Nuova("GC", TF.D1, {
            "chiusura_utc": "2026-03-10T00:00:00Z", "apertura": 1.0,
            "massimo": 2.0, "minimo": 0.5, "chiusura": 1.5})
        primo = main.processa_alert(in_alert(nuova))
        secondo = main.processa_alert(in_alert(nuova))
        self.assertEqual(secondo["esito"], "duplicato")
        self.assertNotEqual(primo["esito"], "duplicato")


if __name__ == "__main__":
    unittest.main(verbosity=2)
