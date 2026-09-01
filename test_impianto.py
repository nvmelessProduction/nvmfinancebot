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
        "FILE_BLOCCO": os.path.join(_CARTELLA, "STOP"),
        "SENTINELLA_ATTIVA": "false",
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

    def __init__(self) -> None:
        super().__init__("MetaTrader5")
        self.azzera()

    def azzera(self) -> None:
        self.avviato = False
        self.trading_abilitato = True
        self.bid = 1.10000
        self.ask = 1.10010
        self.posizioni: list[Oggetto] = []
        self.ordini_inviati: list[dict] = []
        self.prossimo_ticket = 1000
        self.ordine_fallisce = False

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
            leverage=30, trade_allowed=True,
        )

    # -- simboli e prezzi --
    def symbol_select(self, simbolo: str, _abilita: bool = True) -> bool:
        return simbolo != "SIMBOLO-INESISTENTE"

    def symbol_info_tick(self, simbolo: str):
        if simbolo == "SIMBOLO-INESISTENTE":
            return None
        return Oggetto(bid=self.bid, ask=self.ask)

    def symbol_info(self, simbolo: str):
        if simbolo == "SIMBOLO-INESISTENTE":
            return None
        return Oggetto(filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=50.0)

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

        if "position" in richiesta:  # chiusura
            self.posizioni = [p for p in self.posizioni if p.ticket != richiesta["position"]]
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
# 2. La strategia deve restare uno stub
# ==========================================================================
class ProvaStrategia(BaseCollaudo):
    def test_restituisce_sempre_none(self) -> None:
        for chiusura in (1.0, 1.5, 99.0, 0.0001):
            decisione = valuta(AlertIn.model_validate(alert_finto(close=chiusura)))
            self.assertEqual(decisione.azione, "NONE")
            self.assertIsNone(decisione.volume)

    def test_alert_valido_non_apre_nulla(self) -> None:
        riconfigura(MODE="auto")
        with TestClient(main.app) as c:
            corpo = c.post("/webhook", json=alert_finto()).json()
        self.assertEqual(corpo["azione"], "NONE")
        self.assertEqual(corpo["esito"], "ignorato")
        self.assertEqual(len(finto.ordini_inviati), 0, "con la strategia stub non deve partire nessun ordine")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
