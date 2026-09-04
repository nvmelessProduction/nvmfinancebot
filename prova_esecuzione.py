"""Prova di esecuzione su conto DEMO: il collaudo del percorso dei soldi.

`prova_impianto.py` verifica che i tre collegamenti esistano. Questo verifica
che il percorso che muove denaro funzioni davvero, dall'inizio alla fine:

    ordine inviato -> posizione registrata in archivio -> sorvegliata dalla
    sentinella -> chiusa -> notificata su Telegram

E' la prova che vuoi aver fatto **prima** di fidarti del bot, e non dopo.

Uso, su Windows con MT5 aperto e loggato su un conto demo:

    python prova_esecuzione.py              # sola lettura, non invia nulla
    python prova_esecuzione.py --ordine     # invia davvero un ordine minimo

Senza `--ordine` non viene inviato niente: si leggono solo conto e specifiche
di contratto. Le specifiche servono comunque, perche' contengono il
`valore_punto` che RISK-03 richiede e che chiude PA-62 con numeri misurati sul
tuo conto invece che stimati.

**Non parte su un conto reale.** Il controllo e' esplicito e non e'
aggirabile da riga di comando: un ordine di prova su un conto reale non e' una
prova, e' un'operazione.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from core import broker, notifier, storage
from core.config import impostazioni
from core.log import configura as configura_log
from core.parametri import UNIVERSO
from core.sentinella import Sentinella

OK = "OK     "
KO = "ERRORE "
NOTA = "       "


def intestazione(titolo: str) -> None:
    print()
    print("=" * 72)
    print(titolo)
    print("=" * 72)


# ---------------------------------------------------------------------------
# 1. Il terminale
# ---------------------------------------------------------------------------
def verifica_terminale() -> bool:
    intestazione("1. TERMINALE E CONTO")

    if not broker.disponibile():
        print(f"{KO} MetaTrader5 non importabile")
        print(f"{NOTA} {broker.MOTIVO_INDISPONIBILE}")
        return False

    connesso, messaggio = broker.connetti()
    print(f"{OK if connesso else KO} connessione: {messaggio}")
    if not connesso:
        return False

    permesso, messaggio = broker.trading_permesso()
    print(f"{OK if permesso else KO} trading da programma: {messaggio}")
    if not permesso:
        print(f"{NOTA} attiva il pulsante 'Algo Trading' nella barra di MT5")
        return False

    demo, messaggio = broker.conto_e_demo()
    print(f"{OK if demo else KO} tipo di conto: {messaggio}")
    if not demo:
        print(f"{NOTA} questa prova invia ordini: non la eseguo su un conto reale")
        return False

    ok_conto, conto, _ = broker.info_conto()
    if ok_conto and conto:
        print(f"{NOTA} equity {conto['equity']} {conto['valuta']}, "
              f"margine libero {conto['margine_libero']}, leva 1:{conto['leva']}")
    return True


# ---------------------------------------------------------------------------
# 2. Le specifiche di contratto — anche senza inviare nulla
# ---------------------------------------------------------------------------
def leggi_specifiche() -> dict[str, dict]:
    """Legge le specifiche dei sei strumenti di PRIN-08.

    E' la parte piu' utile della prova in sola lettura: `valore_punto` entra
    nel calcolo della size (RISK-03) e va misurato sul conto, non stimato.
    """
    intestazione("2. SPECIFICHE DI CONTRATTO (PRIN-08)")
    print(f"{NOTA} {'strumento':<10} {'vol min':>8} {'passo':>8} "
          f"{'tick size':>11} {'tick value':>11} {'valore punto':>13}")
    print(f"{NOTA} {'-' * 66}")

    trovate: dict[str, dict] = {}
    for cfd in UNIVERSO:
        ok, specifiche, messaggio = broker.specifiche_simbolo(cfd)
        if not ok or specifiche is None:
            print(f"{KO} {cfd:<10} {messaggio}")
            continue
        trovate[cfd] = specifiche
        print(f"{NOTA} {cfd:<10} {specifiche['volume_min']:>8} "
              f"{specifiche['volume_step']:>8} {specifiche['trade_tick_size']:>11} "
              f"{specifiche['trade_tick_value']:>11} {specifiche['valore_punto']:>13.2f}")

    mancanti = sorted(set(UNIVERSO) - set(trovate))
    if mancanti:
        print()
        print(f"{KO} strumenti non trovati sul broker: {', '.join(mancanti)}")
        print(f"{NOTA} i nomi su FP Markets possono avere un suffisso "
              f"(EURUSD.a, XAUUSD.pro...). Vanno mappati prima di operare.")
    else:
        print()
        print(f"{OK} tutti e sei gli strumenti di PRIN-08 sono raggiungibili")

    print()
    print(f"{NOTA} Questi `valore_punto` sono cio' che serve a RISK-03 e chiudono")
    print(f"{NOTA} PA-62 con numeri misurati sul tuo conto invece che stimati.")
    return trovate


# ---------------------------------------------------------------------------
# 3. Il percorso completo, con un ordine vero su demo
# ---------------------------------------------------------------------------
def prova_ordine(strumento: str, specifiche: dict) -> bool:
    """Invia un ordine minimo, lo registra, lo fa vedere alla sentinella, lo chiude."""
    intestazione(f"3. PERCORSO COMPLETO SU {strumento} (CONTO DEMO)")

    volume = specifiche["volume_min"]
    print(f"{NOTA} volume: {volume} (il minimo consentito dal broker)")

    ok_prezzo, tick, messaggio = broker.prezzo_corrente(strumento)
    if not ok_prezzo or tick is None:
        print(f"{KO} nessuna quotazione: {messaggio}")
        print(f"{NOTA} mercato chiuso? La prova va fatta a mercato aperto.")
        return False
    print(f"{NOTA} quotazione: bid {tick['bid']}, ask {tick['ask']}, "
          f"spread {tick['ask'] - tick['bid']:.5f}")

    # --- invio ---
    esito = broker.invia_ordine(strumento, "BUY", volume, commento="prova esecuzione")
    print(f"{OK if esito.ok else KO} invio ordine: {esito.messaggio}")
    if not esito.ok or esito.ticket is None:
        return False
    ticket = esito.ticket

    # --- registrazione in archivio ---
    try:
        id_posizione = storage.registra_posizione(
            simbolo=strumento,
            direzione="BUY",
            volume=volume,
            ticket=ticket,
            prezzo_ingresso=esito.prezzo,
            # Livelli volutamente irraggiungibili: la sentinella deve vederla
            # aperta e non chiuderla da sola prima che lo facciamo noi.
            sl=(esito.prezzo or 0) * 0.5,
            tp=(esito.prezzo or 0) * 1.5,
        )
        print(f"{OK} registrata in archivio, id {id_posizione}")
    except Exception as errore:
        print(f"{KO} registrazione in archivio fallita: {errore!r}")
        print(f"{NOTA} ATTENZIONE: la posizione {ticket} e' APERTA e non sorvegliata.")
        print(f"{NOTA} Chiudila a mano su MT5.")
        return False

    # --- la sentinella la vede? ---
    sentinella = Sentinella()
    risultato = sentinella.giro()
    vista = risultato.get("controllate", 0) >= 1
    print(f"{OK if vista else KO} sentinella: {risultato}")
    if risultato.get("chiuse"):
        print(f"{KO} la sentinella l'ha chiusa subito: i livelli di prova erano sbagliati")

    # --- notifica ---
    inviata, dettaglio = notifier.invia(
        f"Prova di esecuzione: {strumento} BUY {volume} a {esito.prezzo}, ticket {ticket}."
    )
    print(f"{OK if inviata else NOTA} Telegram: {dettaglio}")

    # --- chiusura ---
    time.sleep(1)
    chiusura = broker.chiudi_posizione(ticket)
    print(f"{OK if chiusura.ok else KO} chiusura: {chiusura.messaggio}")
    if chiusura.ok:
        storage.chiudi_posizione(id_posizione, chiusura.prezzo, "prova di esecuzione")
        print(f"{OK} archivio allineato")
    else:
        print(f"{NOTA} ATTENZIONE: la posizione {ticket} e' rimasta aperta. Chiudila a mano.")
        return False

    ok_posizioni, aperte, _ = broker.posizioni_broker(strumento)
    residue = [p for p in aperte if p["ticket"] == ticket]
    print(f"{OK if not residue else KO} nessuna posizione residua sul broker")

    return chiusura.ok and not residue


# ---------------------------------------------------------------------------
def main() -> int:
    argomenti = argparse.ArgumentParser(
        description="Prova di esecuzione su conto MT5 demo.",
    )
    argomenti.add_argument(
        "--ordine", action="store_true",
        help="invia davvero un ordine minimo e lo richiude (solo su conto demo)",
    )
    argomenti.add_argument(
        "--strumento", default="XAUUSD",
        help="strumento su cui provare l'ordine (default: XAUUSD)",
    )
    opzioni = argomenti.parse_args()

    configura_log()
    storage.inizializza()
    cfg = impostazioni()

    print("=" * 72)
    print("PROVA DI ESECUZIONE — percorso dei soldi, su conto demo")
    print(f"modalita' impianto: {cfg.MODE}   archivio: {cfg.DB_PATH}")
    if cfg.bloccato:
        print(f"ATTENZIONE: freno a mano tirato (file {cfg.FILE_BLOCCO})")
    print("=" * 72)

    if not verifica_terminale():
        print()
        print(f"{KO} Non proseguo: sistema prima il terminale.")
        return 1

    specifiche = leggi_specifiche()

    if not opzioni.ordine:
        print()
        print("=" * 72)
        print("  Sola lettura: nessun ordine e' stato inviato.")
        print("  Per provare il percorso completo:  python prova_esecuzione.py --ordine")
        print("=" * 72)
        return 0

    if opzioni.strumento not in specifiche:
        print()
        print(f"{KO} {opzioni.strumento} non e' fra gli strumenti raggiungibili.")
        return 1

    riuscito = prova_ordine(opzioni.strumento, specifiche[opzioni.strumento])

    print()
    print("=" * 72)
    if riuscito:
        print("  Percorso completo verificato: invio, archivio, sentinella,")
        print("  notifica e chiusura. L'impianto sa muovere denaro.")
    else:
        print("  Il percorso si e' interrotto. Guarda sopra dove, e sistema")
        print("  quello prima di andare avanti.")
    print("=" * 72)
    return 0 if riuscito else 1


if __name__ == "__main__":
    sys.exit(main())
