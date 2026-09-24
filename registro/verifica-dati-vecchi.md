# Verifica dei dati del vecchio branch

_24/09/2026._ Il vecchio branch `claude/trading-bot-infrastructure-5rht0h`
contiene un solo pacchetto di prezzi, `dati/pacchetto-2026-09.csv.gz`: sei
strumenti, dal 2 agosto al 16 settembre 2026, un solo prezzo per candela
(niente ask). Lo storico di vent'anni del vecchio bot stava in un database
sulla VPS, non nel repository.

## Cosa è giusto

| Cosa | Verifica | Esito |
|---|---|---|
| Minuti (1–16 settembre) | confrontati con il file BID scaricato oggi da Dukascopy per EURUSD del 10/09 | **identici** su tutti i 1.434 minuti in comune |
| Minuti, tutti gli strumenti | controlli di `nvm/dati/controlli.py` | nessuna anomalia, a parte la pausa giornaliera dell'oro e il Labor Day del 7/09, che sono veri |
| Candele orarie | ricostruite dai minuti del pacchetto | **identiche** (285 su 285 per EURUSD, lo stesso per gli altri) |

## Cosa è sbagliato

| Cosa | Nel pacchetto | Come dovrebbe essere (`spec/dati.md`) | Conseguenza |
|---|---|---|---|
| Candele a 4 ore | chiudono alle 0, 4, 8, 12, 16, 20 **UTC**: a settembre aprono alle 20, 0, 4, 8, 12, 16 di New York | aprono alle 17, 21, 1, 5, 9, 13 di New York | **nessuna** delle 71 candele a 4 ore coincide. I CRT su 4 ore del vecchio bot erano cercati su candele diverse da quelle di Romeo |
| Giornaliere dei cambi | chiudono alle 22:00 UTC anche d'estate, cioè alle 18:00 di New York | chiudono alle 17:00 di New York (21:00 UTC d'estate) | d'estate il giorno era spostato di un'ora |
| Giornaliere dell'oro | chiudono alle 21:00 UTC | idem | giuste, ma **diverse dai cambi nello stesso archivio** |

## Cosa si usa

- **Minuti e candele orarie del pacchetto:** sono giusti, si possono usare per
  le prove.
- **Candele a 4 ore, giornaliere, settimanali e mensili del pacchetto:** si
  buttano e si ricostruiscono dai minuti o dalle orarie.
- **Lo storico di vent'anni:** si riscarica da Dukascopy con `scarica.py`
  sulla VPS, al minuto con bid e ask. Serve comunque: il vecchio archivio
  aveva solo tre mesi di candele sotto l'ora, e la coppia 4 ore → 15 minuti
  ha bisogno dei quindici minuti di vent'anni.
