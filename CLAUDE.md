# Prima di tutto

Leggi **`documenti/RECAP.md`**: è il passaggio di consegne, con tutto quello che serve per ripartire (regole del
proprietario, stato del bot, decisioni aperte, lavoro in corso coi passi esatti). **Aggiornalo prima di chiudere ogni
sessione.**

Le regole che non si violano mai (i dettagli sono in RECAP §2):

- **Segreti:** mai leggere o stampare il `.env` della VPS, mai chiedere chiavi in chat, mai segreti nel repository.
- **Git:**
  - si lavora e si fa push solo su `claude/zealous-albattani-394cd9`: è il ramo che il bot dal vivo scarica da solo
    ogni 2 minuti, quindi ogni push di codice arriva al bot vero;
  - prima di ogni push: `git fetch` (lavora anche Codex) e le prove (`python -m pytest -q`);
  - mai force push o riscrittura della storia, mai cancellare `claude/trading-bot-infrastructure-5rht0h`;
  - niente pull request se il proprietario non la chiede.
- **Nel repository:** mai il nome del socio né il titolo del suo libro; niente screenshot di WhatsApp.
- **Lingua:** si scrive in italiano semplice, coi numeri veri anche quando vanno male. Il proprietario spesso ascolta
  le risposte mentre guida.

