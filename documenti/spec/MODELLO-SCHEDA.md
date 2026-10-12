# Scheda agente: <nome>

Copia questo file in `documenti/spec/<nome>.md` e riempilo. Parole semplici e numeri
precisi: se una regola si può leggere in due modi, prima o poi il codice
sceglierà quello sbagliato.

## La domanda

Una frase sola. Esempio: "C'è un CRT su questa coppia di timeframe, adesso?"

## Cosa guarda

Solo dati: quali candele, di quali timeframe, quali prezzi. Mai i pareri
degli altri agenti (l'unica eccezione è il Capo).

## La regola del manuale

Passi numerati, ognuno controllabile su un grafico. Ogni soglia con il suo
numero.

1. …
2. …

## Cosa risponde

Esempio: sì / no / non so, più i valori (livelli, orari).

"Non so" è una risposta vera, diversa da "no": va usata quando mancano i
dati per decidere.

## I casi

Gli id dei casi in `documenti/casi/` che mostrano la regola: quelli in cui risponde sì,
quelli in cui risponde no, e quelli al limite.

## Cosa può imparare

- **Il numero che può muovere:** …
- **Entro quali limiti:** …
- **Come si misura se è migliorato:** …
- **Casi minimi e miglioramento minimo per il cancello:** …

## Da dove viene

La fonte di ogni regola: video di Romeo (titolo e minuto), tuo appunto,
libro.

## Approvazione

- [ ] Approvata da te il ____
