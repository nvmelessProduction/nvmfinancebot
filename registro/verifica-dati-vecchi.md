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

---

## Le orarie di vent'anni del vecchio archivio (24/09/2026, sera)

L'altra sessione ha esportato dal database della VPS le candele del vecchio
bot (`dati/candele/` sul vecchio branch). Le orarie con origine "dukascopy"
coprono tutti e sei gli strumenti dal 2006 al 16/09/2026.

| Verifica | Esito |
|---|---|
| Confronto con il BID scaricato oggi da Dukascopy, EURUSD gen–lug 2006 | **3.627 ore su 3.627 identiche**, nessuna in più o in meno |
| Ask | **non c'è**: il vecchio archivio teneva un prezzo solo |
| Controlli (`nvm/dati/controlli.py`) sui vent'anni | vedi sotto |

Cosa dicono i controlli:

- **Salti:** sono eventi veri (crisi del 2008, franco svizzero nel 2011,
  notte della Brexit il 23/06/2016), non errori.
- **Buchi a Natale e Capodanno, e nelle feste americane per l'oro:**
  chiusure vere del mercato.
- **AUDUSD 2007–2010:** molti buchi (69 nel 2007, 42 nel 2008). Sono nei
  dati di Dukascopy di quegli anni: si tiene conto che AUDUSD è meno
  affidabile prima del 2011.
- **Mesi mancanti del tutto:** USDJPY 2016-03 e 2020-12; XAUUSD 2022-07 e
  2022-11 (più 2025-04 e 2026-03, nel periodo chiuso). Si scaricano interi
  da Dukascopy.

Come si usano: in `dati/grezzi/ore_bid/` (fuori da git), completati con
l'ask vero da `scarica.py --solo-ask`. Nei mesi non ancora completati
l'ask è il bid più lo spread misurato nello stesso strumento, anno e ora
(`nvm/dati/spread.py`), e ogni misura dice quanti mesi sono esatti e
quanti stimati.

---

## Bid e ask dai file grezzi del vecchio bot (24/09/2026, sera)

L'altra sessione ha decodificato anche i file `.bi5` in cache sulla VPS
(`dati/candele/grezzi/` sul vecchio branch): bid **e ask** orari, sei
strumenti, gennaio 2006 – agosto 2026, tutte le ore.

| Verifica | Esito |
|---|---|
| Confronto con i mesi scaricati direttamente da Dukascopy (EURUSD gen–ott 2006, GBPUSD gen 2006) | **bid e ask identici** su tutti e 11 i mesi |
| Mesi mancanti prima del 2024 | USDJPY 2016-03, 2017-01, 2020-12; XAUUSD 2022-07, 2022-11 |
| Spread mediano | EURUSD 1,0 pip (2006) → 0,3 (dal 2015); GBPUSD 2,0 → 1,0; USDJPY 2,0 → 0,3–0,6; XAUUSD 0,3–0,5 $ |
| Ask sotto il bid | 73 ore su AUDUSD nel 2007: dati sporchi di quegli anni |
| Spread enormi | eventi veri: franco svizzero il 15/01/2015, Covid a marzo 2020 |

Importati in `dati/grezzi/ore/` con `importa_grezzi.py`. Lo spread stimato
di `nvm/dati/spread.py` non serve più per questi anni.
