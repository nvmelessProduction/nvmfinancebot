"""Il primo accesso del bot a TradingView, una volta sola, sulla VPS (doppio clic su `tradingview_accesso.bat`).

Si apre il browser: entrate col vostro account TradingView e premete "Allow". Le chiavi vanno in
`dati/vivo/tradingview.json` (mai nel repository, mai stampate); da li' il bot rinnova l'accesso da solo.
Poi prova a leggere le candele di ogni grafico scelto nel `.env` (riga TRADINGVIEW_SIMBOLI) e dice come e' andata.

    python tradingview_accesso.py           login e prova
    python tradingview_accesso.py --prova   solo la prova (il login c'e' gia')
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from nvm.vivo.ambiente import impostazioni
from nvm.vivo.tradingview import Accesso, ErroreTradingView, TradingView, minuti

RADICE = Path(__file__).resolve().parent
CARTELLA = RADICE / "dati" / "vivo"


def prova(accesso: Accesso) -> bool:
    imp = impostazioni(RADICE)
    simboli = list(imp.tradingview) + ([(imp.tradingview_dxy, "DXY")] if imp.tradingview_dxy else []) + \
        ([(imp.tradingview_totale, "TOTAL")] if imp.tradingview_totale else [])
    if not simboli:
        print("Nel .env non c'e' ancora la riga TRADINGVIEW_SIMBOLI: provo solo con OANDA:EURUSD.")
        simboli = [("OANDA:EURUSD", "EURUSD")]
    for sbagliato in imp.tradingview_sbagliati:
        print(f"  ?? {sbagliato}: non capisco quale strumento sia (scrivilo cosi': OANDA:US30USD=US30)")
    tv = TradingView(accesso)
    tutto_ok = True
    for simbolo, nome in simboli:
        try:
            barre = tv.candele(simbolo, 3600, 6)
            m = minuti(nome, barre, 3600, time.time())
            if not len(m):
                raise ErroreTradingView("nessuna candela chiusa")
            ultima = datetime.fromtimestamp(int(m.t[-1]), tz=timezone.utc).strftime("%d/%m %H:%M UTC")
            print(f"  OK  {simbolo:<22} -> {nome:<8} ultima candela da 1 ora: {ultima}, "
                  f"chiusura {m.bid[-1, 3] * m.punto:g}")
        except Exception as errore:
            tutto_ok = False
            print(f"  NO  {simbolo:<22} -> {nome:<8} {errore}")
    return tutto_ok


def main() -> int:
    accesso = Accesso(CARTELLA)
    if "--prova" not in sys.argv:
        print("Collego il bot al vostro account TradingView.")
        try:
            accesso.primo_accesso()
        except ErroreTradingView as errore:
            print(f"Non e' andato: {errore}")
            return 1
        print("Accesso fatto e salvato. Il bot lo rinnova da solo.")
    elif not accesso.pronto:
        print("Manca l'accesso: lancia tradingview_accesso.bat senza --prova.")
        return 1
    print("Provo a leggere i grafici...")
    ok = prova(accesso)
    print("Tutto a posto: al prossimo avvio il bot analizza su TradingView." if ok else
          "Qualche grafico non va: mandami una foto di questa finestra.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
