"""Il collegamento alle API funziona? Una chiamata vera, con un setup finto.

Costa qualche centesimo e risponde alla sola domanda che conta prima di
accendere: **quando il bot chiedera' un giudizio, arrivera' una risposta?**

Senza questa prova il primo fallimento si scoprirebbe in produzione, e si
vedrebbe come un'astensione: il giudizio fallisce chiuso, quindi una chiave
sbagliata non da' un errore rumoroso — da' un bot che non apre mai nulla.

Il dossier qui e' inventato ma ha la forma di quelli veri, cosi' la prova
esercita lo stesso percorso: stesse istruzioni, stesso schema del verdetto,
stesso modo di leggere la risposta.
"""

from __future__ import annotations

import sys

from core.config import impostazioni
from core.giudizio_claude import MODELLO, giudica

# Un setup plausibile: CRT short su quattro ore, CISD presente, ombre larghe.
# E' il profilo che la misura dice buono, quindi un ACCETTA e' la risposta
# attesa — ma la prova riesce comunque se risponde RIFIUTA con un motivo:
# quello che si sta verificando e' il collegamento, non il giudizio.
DOSSIER = {
    "strumento": "EURUSD",
    "istante_utc": "2026-09-16T18:00:00+00:00",
    "timeframe_crt": "TF_H4",
    "azione_proposta": "SELL",
    "direzione_sul_future": "SHORT",
    "prezzo_ingresso": 1.0854,
    "livello_stop": 1.0871,
    "tp1": 1.0820,
    "target_finale": 1.0790,
    "rapporto_su_tp1": 2.0,
    "volume_lotti": 0.12,
    "spread_corrente": 0.00003,
    "peso_ombre_n2": 0.71,
    "n2_su_n1": 0.42,
    "sweep_oltre_n1": 0.0009,
    "cisd_presente": True,
    "cisd_timeframe": "TF_M15",
    "bias_dxy": "LONG",
    "conferme_di_romeo": {
        "CRT-06": "non valutabile",
        "CRT-10": "non valutabile",
        "CRT-11": "si",
        "CRT-12": "si",
        "CRT-15": "si",
        "CRT-17": "non valutabile",
        "CRT-18": "si",
        "CRT-20": "si",
    },
    "conferme_favorevoli": 5,
    "conferme_contrarie": 0,
}


def main() -> int:
    cfg = impostazioni()
    chiave = getattr(cfg, "ANTHROPIC_API_KEY", "")

    print("configurazione:")
    print(f"  GIUDIZIO_ATTIVO      {cfg.GIUDIZIO_ATTIVO}")
    print(f"  ANTHROPIC_API_KEY    "
          f"{'presente (' + chiave[:9] + '...)' if chiave else 'ASSENTE'}")
    print(f"  modello              {MODELLO}")

    if not cfg.GIUDIZIO_ATTIVO:
        print("\nGIUDIZIO_ATTIVO non e' true nel .env: il bot non chiedera' mai "
              "un giudizio.\nMettilo a true e rilancia.")
        return 1
    if not chiave:
        print("\nLa chiave non c'e'. Mettila con:  python metti_chiave.py")
        return 1

    print("\nchiamata in corso (qualche secondo, costa circa 6 centesimi)...\n")
    verdetto = giudica(DOSSIER)

    if verdetto.errore:
        print(f"NON HA FUNZIONATO: {verdetto.errore}\n")
        print("Le cause piu' comuni, in ordine:")
        print("  - chiave sbagliata o revocata        -> rigenerala sulla console")
        print("  - crediti finiti                     -> console.anthropic.com")
        print("  - rete o proxy che blocca l'uscita   -> prova `curl https://api.anthropic.com`")
        print("  - libreria assente                   -> python -m pip install anthropic")
        return 1

    print("HA FUNZIONATO.\n")
    print(f"  verdetto   {'ACCETTA' if verdetto.accetta else 'RIFIUTA'}")
    print(f"  fiducia    {verdetto.fiducia}")
    print(f"  modello    {verdetto.modello}")
    print(f"  motivo     {verdetto.motivo}")
    print("\nIl bot puo' chiedere giudizi. Un RIFIUTA qui non e' un problema:")
    print("si stava verificando il collegamento, non la decisione.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
