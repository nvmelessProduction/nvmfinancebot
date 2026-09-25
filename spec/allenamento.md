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

## Il mansionario **[D]**

Ogni specialista ha delle manopole, e per ognuna i valori ammessi: i limiti
vengono dalle fonti di Romeo, e fuori da lì non si va, anche se i numeri
tentano. L'esempio che li ha fatti scrivere: uno stop sempre più largo
avvicina il risultato a zero, ma solo perché le operazioni non si fermano
più e scadono (17% scadute con lo stop a 4 volte il range, contro l'1%),
cioè soldi fermi e rischio nascosto (`registro/tentativi.md`, 25/09/2026).

| Agente | Manopola | Valori ammessi | In uso all'inizio |
|---|---|---|---|
| Cacciatore | variante | manuale, chiusura dentro | manuale |
| Grilletto | colpi sullo stesso CRT | 1, 2, 3 | 3 |
| Grilletto | lato della liquidità (candele per lato) | 1, 2, 3 | 2 |
| Livelli | secondo obiettivo oltre il lato (ampiezze) | 0, 0,25, 0,5, 0,75, 1 | 0,5 |
| Livelli | stop minimo (frazione del range) | 0,15, 0,2, 0,25, 0,33, 0,5 | 0,25 |
| Key level | candele guardate | 12, 24, 48 | 24 |
| Key level | vicinanza | 0,05, 0,1, 0,2 | 0,1 |
| Key level | lato dello swing | 1, 2, 3 | 2 |
| Orario | ora di Londra (NY) | 0–4, 1–4, 1–5, 2–5, 2–6 | 1–5 |
| Orario | ora di New York (NY) | 7–10, 8–11, 8–12, 9–12, 9–13 | 8–11 |
| Bias | sconto | 0,3, 0,4, 0,5 | 0,5 |

## La settimana in palestra **[D]**

1. **Esperienza.** Ogni agente rilegge le scelte del Capo dei vent'anni e
   dice con quali suoi segnali va meglio e con quali peggio.
2. **Ipotesi.** Prova da solo a girare di un passo ognuna delle sue
   manopole (i valori vicini a quello in uso): si cresce piano.
3. **Prova.** Con la modifica si rifà la tabella dei vent'anni (2006–2023)
   e il Capo si riallena anno per anno, come nel cammino di `capo.py`. Si
   confronta il guadagno delle scelte del Capo **settimana per settimana**
   con quello di oggi: stesso mercato, stesse settimane.
4. **Esame.** La modifica passa se il guadagno in più a settimana è sopra
   zero con certezza: intervallo ricampionato a blocchi di un trimestre, al
   livello 10% diviso per il numero di prove della settimana (più prove,
   asticella più alta); e se fa meglio in almeno il 70% degli anni.
5. **Paletti.** Non passa comunque se: le operazioni scadute crescono di
   più di un punto; la durata mediana cresce più di una volta e mezza; il
   drawdown cresce più del 10%; il Capo ritrova più di una entrata di Romeo
   del 2023 in meno (lo stesso conto di `romeo.py`).
6. **I colleghi.** Se più agenti hanno una modifica che passa, si prova la
   squadra con tutte insieme: se insieme non passa, resta solo la migliore.
   Per ogni modifica tenuta il rapporto dice chi, fra i colleghi, ci
   guadagna e chi ci perde.
7. **Memoria.** Ogni prova, tenuta o scartata, resta in
   `nvm/vivo/allenamento.json`. Una prova scartata non si ripete per 8
   settimane.
8. **Il bot.** Se qualcosa cambia, `agenti.json` si riscrive, la tabella si
   rifà e il Capo del bot si riaddestra. Il bot sulla VPS si aggiorna da
   solo e, al primo avvio, manda il rapporto sul canale équipe.

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
