# Registro dei tentativi

Ogni misura, ogni candidato provato, ogni variante: qui, **anche quando va
male**. Serve per due motivi:

- sapere quanti tentativi sono stati fatti, perché più tentativi vogliono
  dire un'asticella più alta (`PIANO.md` §2, punto 5);
- non rifare due volte la stessa prova dimenticando com'era andata la prima.

| Data | Fase | Cosa si è provato | Criterio scritto prima | Risultato | Passa? |
|---|---|---|---|---|---|
| 24/09/2026 | A | Ricerca delle fonti sul CRT di Romeo: post su X, schemi, thread degli studenti. I video YouTube non sono raggiungibili da qui. | — | fonti in `spec/FONTI-ROMEO.md`, bozza in `spec/cacciatore.md` | — |
| 24/09/2026 | B | Verifica del pacchetto dati del vecchio branch contro Dukascopy e contro i suoi stessi minuti | minuti identici al BID di Dukascopy; candele ricostruite identiche | minuti e orarie giusti; 4 ore e giornaliere su confini sbagliati. Dettagli in `registro/verifica-dati-vecchi.md` | minuti e orarie sì, il resto no |
| 24/09/2026 | D | Prova della catena (Cacciatore → Grilletto → Livelli → campo di prova) su EURUSD, gen–lug 2006, coppie D1→H1 e W1→H4. **Non è una misura**: sette mesi, uno strumento | — | 185 operazioni, R medio −0,003, IC95 [−0,23; +0,23] | — |
| 24/09/2026 | A | Correzione di una regola nata da un caso: la durata dell'operazione passa da "fine della candela d'ingresso" a "fine della candela 3" | il caso di Romeo deve essere possibile con le regole | nel CRT mensile di EURUSD (canale, msg 5623) il target 2 arriva nella candela 3 | corretta |
| 24/09/2026 | A | Seconda correzione della durata, nata da CASO-002: da "fine della candela 3" a nessuna uscita a tempo (tetto di sicurezza di circa 10 candele alte) | il caso di Romeo deve essere possibile con le regole | nel giornaliero di EURUSD di dicembre 2024 il target 2 arriva nella candela 4 | corretta |
| 24/09/2026 | A | Verifica CASO-002 e CASO-003 sui dati | livelli entro pochi pip, stessa direzione, stessi momenti | CASO-002: range, ingresso (1.05788 contro 1.0580) e target giusti; CASO-003: range entro 1 pip e target giusti, niente Model#1 sulle giornaliere (c'è sulle 4 ore) | sì, con una nota sul Grilletto |
| 24/09/2026 | A | Verifica CASO-004 (XAUUSD giornaliero, luglio 2024) | ingresso e stop di Romeo ritrovati dal bot | ritrovati con due correzioni: tentativi del Grilletto (fino a 3, dopo uno stop con un turtle soup nuovo) e variante "stop stretto" (2474.47 contro 2474.00). Esito diverso per 30 centesimi di feed | sì, con due correzioni |
