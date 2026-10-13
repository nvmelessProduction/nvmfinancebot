"""Nameless, il cervello unico (`documenti/PROGETTO-NAMELESS.md`).

Si costruisce una fase alla volta, ognuna con il suo esame. Fase 1, gli occhi:

- `sensi.py`: le candele di tutti i timeframe con gli orari di TradingView, in fila per la scheda grafica (solo numpy);
- `occhi.py`: la rete che legge tutti i timeframe insieme e indovina le candele nascoste (PyTorch).

L'allenamento e l'esame sono su Kaggle (`kaggle_rete/occhi.py`). Il bot dal vivo non usa ancora Nameless: lo prende
nella fase 5, prima in ombra.
"""
