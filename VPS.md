# Scaricare lo storico sulla VPS

Serve una volta sola. Scarica vent'anni di prezzi al minuto, con bid e ask,
per i sei strumenti. **Non opera**: scarica soltanto.

Da un server condiviso Dukascopy blocca le richieste, dalla VPS no. Per
questo si fa lì.

## 1. Prendere il progetto nuovo

Apri **PowerShell** sulla VPS e scrivi:

```
cd $HOME
git clone -b claude/zealous-albattani-394cd9 https://github.com/nvmelessProduction/nvmfinancebot nvm-nuovo
```

Si crea la cartella `nvm-nuovo`, separata da quella del vecchio bot.

## 2. Avviare

Apri la cartella `nvm-nuovo` e fai **doppio clic su `scarica.bat`**.

- La prima volta prepara Python da solo: un paio di minuti.
- Poi scarica un mese alla volta e scrive a che punto è.
- **Ci mette parecchie ore.** Puoi chiudere la finestra quando vuoi: al
  prossimo doppio clic riprende da dove era.
- Occupa qualche GB nella cartella `dati\grezzi`.

## 3. Quando ha finito

Scrive `Finito` e il rapporto dei controlli finisce in
`dati\rapporto-dati.txt`. Dimmelo e mandami quel file: lo leggo e decidiamo
se i dati sono buoni.

## Se qualcosa va storto

| Cosa vedi | Cosa vuol dire |
|---|---|
| `TroppeRichieste` | Dukascopy ha smesso di rispondere per un po'. Aspetta mezz'ora e rilancia |
| `python non è riconosciuto` | manca Python. Installalo da python.org, spuntando "Add Python to PATH" |
| qualsiasi altro errore | mandami una foto della finestra |
