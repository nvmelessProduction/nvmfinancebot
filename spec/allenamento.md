# Scheda: l'allenamento degli agenti

> **Stato:** in uso dal 25/09/2026. Codice in `nvm/agenti/manopole.py`
> (il mansionario), `nvm/prova/allenamento.py` (la palestra), `allena.py`
> (la settimana). Memoria in `nvm/vivo/allenamento.json`, valori in uso in
> `nvm/vivo/agenti.json`.

## Perché

L'utente, 25/09/2026: *"tutti devono imparare, tutti devono migliorarsi,
non solo tre"*; *"come un neolaureato: piano piano, facendo esperienza,
capendo dai propri errori, confrontandosi con i colleghi, crescerà"*.
Fino a qui imparavano da soli solo il Capo, la voce di Romeo e il Rischio;
i sei specialisti erano regole ferme, cambiate a mano.

## Le manopole, senza recinti **[D]**

Ogni specialista ha le sue manopole: i numeri e le scelte che prima erano
scritti a mano. L'utente, 25/09/2026: *"non dobbiamo limitarli né dargli
regole fisse, vanno addestrati"*. Ogni settimana ognuna si sposta di un
passo, in su o in giù, senza un recinto; i soli confini sono quelli della
definizione (un'ora fra 0 e 24, una frazione fra 0 e 1, almeno una candela).

| Agente | Manopola | Passo | All'inizio |
|---|---|---|---|
| Cacciatore | variante | manuale / chiusura dentro | manuale |
| Grilletto | colpi sullo stesso CRT | 1 | 3 |
| Grilletto | lato della liquidità (candele per lato) | 1 | 2 |
| Livelli | secondo obiettivo oltre il lato (ampiezze del CRT) | 0,25 | 0,5 |
| Livelli | pareggio (frazione del cammino verso il primo obiettivo) | 0,25 | 1 = al primo obiettivo |
| Livelli | stop minimo (frazione del range) | 0,05 | 0,25 |
| Key level | candele guardate | 6 | 24 |
| Key level | vicinanza | 0,05 | 0,1 |
| Key level | lato dello swing | 1 | 2 |
| Orario | ora di Londra (NY) | un'ora, per lato | 1–5 |
| Orario | ora di New York (NY) | un'ora, per lato | 8–11 |
| Bias | sconto | 0,1 | 0,5 |

## La settimana in palestra **[D]**

1. **Esperienza.** Ogni agente rilegge le scelte del Capo dei vent'anni e
   dice con quali suoi segnali va meglio e con quali peggio.
2. **Ipotesi.** Prova da solo a spostare di un passo ognuna delle sue
   manopole.
3. **Prova.** Con la modifica si rifà la tabella dei vent'anni (2006–2023)
   e il Capo si riallena anno per anno, come nel cammino di `capo.py`.
4. **Esame: le prestazioni, non il guadagno.** L'utente: *"una modifica
   resta se migliora le prestazioni del bot"*, non se fa guadagnare di più
   (si guadagna di più anche puntando di più o aprendo di più). La misura
   è la **qualità** delle operazioni scelte dal Capo: il rendimento medio
   diviso per quanto oscilla. Non cambia con la puntata né col numero di
   operazioni; uno stop enorme la porta verso zero da solo (le operazioni
   non rendono più niente). La modifica resta se la qualità sale con
   certezza (le stesse settimane ricampionate a blocchi di un trimestre,
   livello 10% diviso per il numero di prove della settimana) e in almeno
   il 70% degli anni.
5. **Nessun divieto.** Operazioni scadute, durata, drawdown, numero di
   operazioni, guadagno ed entrate di Romeo ritrovate si scrivono nel
   rapporto, ma non decidono.
6. **I colleghi.** Se più agenti migliorano, si prova la squadra con tutte
   le modifiche insieme: se insieme non migliora, resta solo la migliore.
   Per ogni modifica tenuta il rapporto dice chi, fra i colleghi, ci
   guadagna e chi ci perde.
7. **Memoria.** Ogni prova, tenuta o scartata, resta in
   `nvm/vivo/allenamento.json`. Una prova scartata non si ripete per 8
   settimane.
8. **Il bot.** `agenti.json` si riscrive, il Capo del bot si riaddestra
   sulle manopole in uso. Il bot sulla VPS si aggiorna da solo e manda il
   rapporto sul canale équipe (ogni allenamento ha il suo numero).

## Le invenzioni **[D]**

L'utente, 25/09/2026: *"perché non dargli la possibilità di inventare?"*.
Ogni specialista ha dei mattoni del suo mestiere (`nvm/agenti/inventate.py`):

| Agente | Mattoni |
|---|---|
| Key level | l'estremo di una candela passata (4 ore, giorno, settimana, mese; 1, 2 o 3 candele fa); il massimo o minimo di una sessione di New York qualunque (inizio e durata) |
| Bias | dove si entra nel range di una candela passata (giorno, settimana, mese; 25, 50, 75%); se la candela passata va a favore o contro (4 ore … mese) |
| Orario | una fascia d'ore qualunque; un giorno della settimana |
| Cacciatore | l'ampiezza del CRT rispetto alla media delle candele prima (10, 20, 50; 0,5 … 2 volte; più o meno) |
| Livelli | lo stop rispetto alla volatilità delle ore prima (14, 50; 0,5 … 4 volte; più o meno) |
| Grilletto | quante candele fra il turtle soup e il Model#1 |

Ogni settimana ognuno inventa 2 domande a caso fra quelle che non ha mai
provato. La palestra le prova come colonna in più del Capo, con lo stesso
esame delle manopole. Una domanda che passa (la migliore di ogni agente, poi
tutte insieme sulla squadra finale) entra nel Capo come colonna nuova
(`nvm/vivo/domande.json`), e il bot dal vivo la fa a ogni decisione. Ogni
invenzione provata resta in memoria e non si riprova.

## L'asticella cresce con tutte le prove fatte **[D]**

La storia dei vent'anni è la stessa ogni settimana: chi prova tante volte
sugli stessi dati, prima o poi trova qualcosa per caso. Per questo il
margine dell'esame non si divide per le prove della settimana, ma per
**tutte le prove fatte da sempre** (manopole e invenzioni). Più il bot ha
provato, più una novità deve essere solida per entrare. I dati nuovi (le
settimane dal vivo, e il 2024–2026 dopo la Fase G) abbassano il rischio di
imparare il caso.

Anche il Rischio, che sceglie quanto puntare, non ha tetti fissi: impara
dai risultati la parte del Kelly che fa crescere di più il conto nel lungo
periodo, cioè quella che non lo espone a perdite che lo rovinano.

## Chi la fa girare

Una Routine di Claude Code, ogni domenica mattina (UTC), in questa sessione:
`python allena.py`, poi le prove automatiche e la pubblicazione. Servono i
dati dei vent'anni sulla macchina; se il contenitore li perde, si
reimportano (`importa_grezzi.py` dall'archivio) prima di allenare.

## Cosa non fa (ancora)

- **Idee nuove.** Gli agenti girano le manopole che hanno; non inventano
  domande nuove. Le idee nuove (dalle fonti di Romeo, e dalle strategie che
  l'utente porterà) entrano come domande o manopole nuove, provate col
  banco (`banco.py`) e scritte nel registro.
- **L'esperienza dal vivo nella palestra.** La palestra usa 2006–2023; il
  2024–2026 resta chiuso fino alla Fase G. Le decisioni dal vivo le usano
  già il Capo, la voce di Romeo e il Rischio nella riunione del sabato.
  Quando si accumulano settimane nuove dopo il 25/09/2026, si aggiungono.
