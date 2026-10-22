# Analisi di tutto il codice (22/10/2026)

Il proprietario, 22/10/2026: *"ho bisogno che facciamo una pulizia di tutte le cose che non ci servono più e di tutte
le cose che vanno in conflitto, anche cose silenziose ... che tu mi analizzi letteralmente tutto il codice"*.

## Come è stata fatta

1. **La mappa degli import** da `vivo.py`, anche quelli dentro le funzioni: quali file il bot dal vivo carica.
2. **Il bot intero fatto girare per una giornata**, con MT5, TradingView e Telegram finti ma la squadra e la rete
   neurale vere, sui prezzi veri del 21/10 alle 12 (il CRT short a 4 e 6 ore del DXY): avvio, giro, ordini,
   sorveglianza, TP1 e pareggio, chiusura, quarto d'ora, riepilogo della sera, sabato, domenica. Misurato quali righe
   girano davvero.
3. **Letto il percorso dal CRT all'ordine**, controllo per controllo, cercando quelli che dicono no senza dirlo.

## I numeri

- Nel repo ci sono circa 32.000 righe di Python, test compresi.
- Il bot dal vivo ne carica circa 19.000, in 70 moduli. Il resto sono la ricerca su Kaggle (rete neurale Nameless) e
  gli script che si lanciano a mano.
- Circa 7.000 righe, fra moduli che il bot carica e script collegati, servono solo a metodi e modalità spenti: il
  metodo dei video, il Capo vecchio, i cervelli degli agenti, l'allenamento sui vent'anni, Romeo. Con le scelte di
  oggi non decidono niente.
- Altri circa 7 MB di file di dati servono solo a quelle modalità spente.

## Il percorso vero, dal grafico all'ordine

| Passo | Cosa fa | Dove |
|---|---|---|
| 1 | Ogni ora le candele da TradingView: 10 strumenti, il DXY e la TOTAL. I quarti d'ora da MT5 | `vivo.Bot.giro`, `tradingview.Fonte` |
| 2 | I CRT del DXY e della TOTAL che hanno preso un key level (dal 22/10). Quello a 1 ora solo se prende il key level del giorno e il massimo o minimo a 4 ore. L'oro e l'argento coi loro CRT (dal 22/10) | `foto.trova`, `giro.setup_buono`, `giro.occasioni_foto` |
| 3 | Per ogni CRT della guida, il setup sullo strumento negli orari della guida (dal 22/10): stop oltre la sua candela 2, TP1 l'altro lato del suo range, target finale il key level opposto. Se lo strumento fa anche lui il CRT nel verso, ★ | `foto.dal_dxy`, `foto.dal_totale`, `foto.crt_propri`, `foto.obiettivo_finale` |
| 4 | Il piano: 25% al TP1 e il resto al target; senza target (o sotto 1 R) tutto al TP1; se neanche il TP1 vale 1 R, niente | `giro._decisione_foto`, `giro.piani_foto` |
| 5 | Messaggio 📐 sul canale operativo: su quali strumenti nasce l'occasione e, dove no, perché | `messaggi.guide` |
| 6 | La squadra: regole del metodo (il CRT della guida col key level preso), voti (solo un parere), previsione della settimana della guida (può dire no), il Rischio (quanto puntare) | `metodo.valuta_foto`, `pareri`, `squadra.Squadra.riunione` |
| 7 | Il Capo: tutte le occasioni, una per strumento | `al_lavoro.scegli` |
| 8 | La rete neurale: sui setup del DXY e della TOTAL scrive solo il suo parere | `rete_vivo.Rete.giudica` |
| 9 | L'ordine su MT5, entro 10 minuti dall'apertura della candela 3, coi controlli del broker | `esecutore.Esecutore.apri` |
| 10 | Messaggio ⏸ sul canale operativo per ogni occasione non aperta, col perché | `vivo.Bot._decidi`, `_perche_no` |
| 11 | La gestione: al TP1 il 25% e lo stop a pareggio con le commissioni coperte; stop e target finale stanno sul broker | `esecutore.Esecutore.sorveglia` |

## I controlli fra il CRT e l'ordine

Ognuno può dire no. Ora tutti lo dicono, col 📐 o col ⏸.

| Controllo | Quando dice no | Da quando lo dice |
|---|---|---|
| CRT valido | la candela 2 non rientra, tocca l'altro lato o sfora | è la definizione del CRT |
| CRT a 1 ora | non ha preso il key level del giorno e il massimo o minimo a 4 ore | regola del 06/10 |
| Pattern della guida | il CRT del DXY (della TOTAL) non ha preso un key level, o è lo stesso movimento di un CRT di prima | 📐 dal 22/10 |
| Prezzi dello strumento | nelle ore delle candele della guida l'ingresso non sta fra stop e TP1 | 📐 dal 22/10 (prima: «candele non confrontabili», e il 22/10 alle 10 ha fermato tutte le coppie) |
| Piano | né il target né il TP1 valgono 1 R | 📐 dal 21/10 |
| Previsione della settimana | il bot ha detto la guida dall'altra parte, la domenica | ⏸ dal 21/10 |
| Rischio | non trova una puntata possibile | ⏸ dal 21/10 |
| Uno per strumento | c'è già un'operazione aperta su quello strumento | ⏸ dal 21/10 |
| Arrivato tardi | la candela 3 è aperta da più di 10 minuti | ⏸ dal 21/10 |
| Broker | conto non demo, Algo Trading spento, prezzo già oltre stop o TP1, stop troppo vicino, lotto minimo troppo grande | ⏸ dal 21/10 |

Nei giorni scorsi due controlli dicevano no **in silenzio**. Erano proprio quelli che bloccavano tutto:

- la squadra voleva la direzione dello strumento dalla sua parte anche sui setup della guida: il 21/10 alle 22 ha
  scartato così BTC ed ETH dopo il CRT della TOTAL. Tolto alle 23:26 dello stesso giorno;
- la rete neurale lasciava i setup del DXY e della TOTAL, che nello studio non ha mai visto: il 22/10, sui prezzi del
  21/10 alle 12, ne lasciava 7 su 8, oro compreso. Tolto il 22/10.

## Regole in conflitto: servono le tue decisioni

1. **La previsione della domenica.** Il 07/10 si era deciso: *"la squadra non deve andare contro le previsioni che fa
   la domenica"*. Oggi è la previsione che il bot fa sul DXY o sulla TOTAL, e può ancora fermare un CRT del DXY. Con
   la regola *"solo ed esclusivamente quando il DXY dà il pattern"* la toglierei.
2. **Una sola operazione per strumento.** Nel codice c'è (07/10: *"vorrei che apri una sola operazione"*).
   `nvm/vivo/scelte.json` dice invece *"sullo stesso strumento decide il Rischio"*. Quale delle due vale?
3. **La rete neurale di adesso.** Sui setup del DXY e della TOTAL non decide più, scrive solo il suo parere e manda i
   «Correggi». Va bene tenerla così finché non arriva quella nuova (Nameless), o la togliamo dal bot?
4. **Le foto.** 9 prove delle 24 foto falliscono col target finale "key level opposto" (16/10, confermato il 20/10).
   Le foto sono anche il materiale da cui impara la rete: aggiorniamo le prove delle foto alla regola nuova?
5. **Il metodo dei video (Romeo).** Il 06/10: *"resta nel codice ma il bot usa le foto"*. Lo togliamo?

## Codice che non serve più

Con le scelte di oggi (`nvm/vivo/scelte.json`: decide la squadra; `giro.METODO = "foto"`) questo codice si carica ma
non decide niente. Alcune parti girano lo stesso, a ogni avvio o a ogni giro (caricano file, fanno conti), senza
decidere niente.

| Gruppo | File | Righe |
|---|---|---|
| I cervelli degli agenti (rete sui vent'anni, evoluzione settimanale) | `nvm/cervello/` tutto, `nvm/vivo/cervelli.json`, `genomi.json`, `ricordi.npz` | ~2.000 + 4 MB |
| Il Capo vecchio e i suoi agenti | `nvm/agenti/capo.py`, `inventate.py`, `panorama.py`, `alberi.py`, `struttura.py`, `manopole.py`, `nvm/vivo/riunione.py`, `capo.json`, `rischio.json`, `agenti.json`, `storico.npz` | ~1.800 + 2 MB |
| L'allenamento e le prove sui vent'anni del metodo vecchio | `nvm/prova/allenamento.py`, `cammino.py`, `domande.py`, `confronto.py`, `strumenti/allena.py`, `capo.py`, `banco.py`, `misura.py`, `strumenti/lavagna/`, `allenamento.json` | ~2.000 |
| Romeo e il metodo dei video | `nvm/vivo/romeo_vivo.py`, `nvm/prova/romeo.py`, `strumenti/romeo.py`, `strumenti/video.py`, il comando /romeo, il ramo "candela 3" e "model1" di `giro.giro` | ~1.000 |
| L'autoanalisi degli agenti vecchi | `nvm/vivo/autoanalisi.py` | ~200 |
| I loro test | circa 50 prove in `tests/` | ~2.000 |

Restano da tenere, ma da alleggerire, alcuni pezzi dei moduli vecchi usati ancora dal metodo delle foto come semplici
"tipi": `Verso` e `CRT` (`agenti/cacciatore.py`), `Scatto` (`agenti/grilletto.py`), `Risultato` (`prova/base.py`),
`Operazione` e `simula` (`prova/campo.py`), `USCITE` e `kelly` (`agenti/rischio.py`), `Bias` (`agenti/conferme.py`).
Si spostano in un modulo piccolo e il resto di quei file si toglie.

Fuori dal bot e da tenere: `kaggle_rete/` e `nvm/nameless/` (la rete nuova), `nvm/dati/` (dati storici), gli script
che si lanciano coi `.bat` (`scarica`, `consegna`, `tradingview_accesso`).

## Il piano di pulizia

Ogni passo si prova con tutti i test e con la giornata intera simulata del bot, prima di caricarlo: ogni caricamento
arriva subito al bot dal vivo.

1. **Togliere le modalità spente da `vivo.py` e da `giro.py`**: i cervelli, il Capo vecchio, l'allenamento,
   l'autoanalisi, il metodo dei video. Poi i loro moduli, i test e i file di dati.
2. **Spostare i pochi tipi ancora usati** in un modulo solo e togliere il resto dei moduli vecchi.
3. **Applicare le decisioni 1–5** qui sopra.
4. **Riscrivere `documenti/STATO.md`, il README e la scheda del metodo** perché dicano solo quello che il bot fa.
5. **Poi il Modello 1** con l'ordine limite (richiesta del 20/10), su una base pulita.
