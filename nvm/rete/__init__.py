"""La rete neurale che impara a leggere i grafici come il proprietario (`spec/rete.md`).

Il proprietario, 11/10/2026: *"iniziamo creando la rete neurale"*. Il piano (08/10/2026): prima la rete impara a
leggere i grafici sui vent'anni di Dukascopy (scuola 1), poi il metodo delle foto dalle regole degli agenti (scuola
2), poi l'occhio del proprietario dai suoi esempi (scuola 3); va sul demo solo se passa l'esame sugli anni che non ha
mai visto. Il bot dal vivo non la usa: si allena e si prova a parte.

- `finestre.py`: quello che la rete vede, le ultime candele chiuse di ogni timeframe a un istante (solo numpy);
- `etichette.py`: le risposte giuste della scuola 2, date dagli agenti del metodo delle foto (solo numpy);
- `modello.py` e `scuola.py`: la rete e l'allenamento (PyTorch, `requirements-rete.txt`, non va sulla VPS).
"""
