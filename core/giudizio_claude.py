"""Il trader discrezionale: Claude che accetta o rifiuta un setup gia' approvato.

## Cosa fa, e soprattutto cosa NON fa

Questo strato gira **dopo** `motore.valuta`, cioe' su un'operazione che tutte
le regole hanno gia' approvato. Puo' fare una cosa sola: **rifiutarla**.

    regole -> BUY/SELL -> giudizio -> BUY/SELL, oppure NIENTE

Non puo' autorizzare cio' che le regole vietano, non puo' cambiare direzione,
size, stop o bersaglio. E' un **veto**, non un secondo motore.

La ragione non e' prudenza generica. Un trader discrezionale che possa
scavalcare `RISK-07` — il limite di perdita giornaliero — non e' un trader
discrezionale: e' un bug con una buona spiegazione. Tutto l'apparato di
`docs/05_rischio.md` esiste perche' nessuno, nemmeno chi ha ragione, possa
aggirarlo nel momento in cui gli sembra di avere ragione.

Il giudizio aggiunge quello che le regole non sanno esprimere: se questo CRT
somigli a quelli che funzionano o a quelli che non funzionano. E' il punto 14
della bibbia — *«non si prende ogni istanza, il contesto del timeframe alto
decide quali istanze valgono»* — che e' l'unica regola di Romeo che dice
esplicitamente che serve discrezionalita'.

## Fallisce chiuso, sempre

Chiave assente, rete giu', timeout, risposta malformata, modello che rifiuta:
**ogni** esito diverso da un ACCETTA esplicito e ben formato vale come
astensione. E' `PRIN-99` applicato a un componente nuovo: se non si sa, non si
opera.

E' l'unica scelta difendibile. Un giudizio che in caso di guasto lasciasse
passare l'operazione trasformerebbe un'interruzione di rete in un ordine non
sorvegliato da nessuna intelligenza — che e' peggio del bot senza giudizio,
perche' nessuno se ne accorgerebbe.

## Si registra tutto, per poterlo misurare

Ogni verdetto finisce in archivio col suo motivo. Senza questo, fra sei mesi
nessuno potra' dire se il giudizio abbia aggiunto valore o solo latenza —
esattamente come `PA-44` non poteva chiudersi perche' il dato non si
raccoglieva. Il confronto che conta e' fra gli esiti degli ACCETTA e quelli
dei RIFIUTA: se i rifiutati fossero andati meglio, il giudizio toglie valore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from core.config import impostazioni
from core.log import diario

log = diario("giudizio")

# La libreria e' facoltativa: senza di essa il bot funziona, e non giudica.
try:
    import anthropic
except ImportError:                                    # pragma: no cover
    anthropic = None                                   # type: ignore[assignment]


MODELLO = "claude-opus-5"

# Il verdetto e' JSON validato dallo schema, non prosa da interpretare. Una
# risposta che dicesse "direi di si', ma..." andrebbe interpretata, e
# interpretare una risposta e' il punto in cui si perde il fallimento chiuso.
SCHEMA_VERDETTO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdetto": {
            "type": "string",
            "enum": ["ACCETTA", "RIFIUTA"],
        },
        "motivo": {
            "type": "string",
            "description": (
                "Una o due frasi sul perche'. Deve citare almeno un dato "
                "concreto del dossier, non una massima generale."
            ),
        },
        "fiducia": {
            "type": "string",
            "enum": ["bassa", "media", "alta"],
        },
    },
    "required": ["verdetto", "motivo", "fiducia"],
    "additionalProperties": False,
}


ISTRUZIONI = """\
Sei il filtro discrezionale di un bot che opera la Candle Range Theory di
@Romeotpt. Ricevi un setup che **tutte le regole hanno gia' approvato** e devi
dire se eseguirlo o lasciarlo passare.

# Il tuo potere, e il suo limite

Puoi solo RIFIUTARE. Non puoi autorizzare, non puoi cambiare direzione, size,
stop o bersaglio: quelli li hanno gia' decisi le regole e non sono in
discussione. Se accetti, l'ordine parte esattamente com'e' descritto.

Non rifiutare per ragioni che le regole coprono gia' — limiti di rischio,
finestre news, festivita', tetto di posizioni. Se il setup e' arrivato fino a
te, quei controlli sono gia' passati. Ripeterli e' rumore.

# Cosa sai davvero di questa strategia

Queste sono misure su 1,5 milioni di candele orarie con BID e ASK veri, non
opinioni:

- Il CRT porta informazione reale ma **piccola**: circa +0,02 R di vantaggio
  medio, contro 0,15-0,35 R di costo dello spread. Da solo perde.
- **Il CISD e' l'unica conferma che regge.** Con CISD disponibile sul
  timeframe basso il rendimento passa da +0,017 a +0,089 R; senza, e'
  **negativo** (-0,045 R). Positivo in tutte e sei le epoche misurate,
  placebo a zero. Se il dossier dice che il CISD non c'e', e' il singolo
  segnale piu' forte contro l'operazione.
- **Le ombre piccole su N2 sono peggiori**: 33,6% di winrate contro il 59,6%
  della base. Uno sweep "pulito", con poca coda, e' un cattivo segno per
  un'operazione di mean-reversion come questa.
- Divergenza SMT, Double Purge e finestre orarie sono state misurate e **non
  mostrano nulla**. Non usarle come motivo: le fonti le celebrano, i dati no.
- Un rapporto rischio/rendimento alto **non** compensa un CISD mancante: sono
  due cose indipendenti e la seconda e' quella misurata.

# Il responso delle conferme

Il dossier porta `conferme_di_romeo`: cosa ha detto CIASCUNA delle sue otto
regole su questo setup. Non sono filtri gia' applicati — sono il quadro su
cui devi decidere, ed e' questo il tuo lavoro.

Pesale insieme, non una per una. Usate come veti in AND bloccano tutto: su
360 valutazioni dell'archivio reale, con tutte accese, si trovano 18 CRT e se
ne bloccano 18. Il bot tace del tutto. Il motivo per cui esisti e' che
qualcuno sappia distinguere "tre conferme contrarie su otto, ma le tre che
contano sono favorevoli" da "tre contrarie e sono quelle che contano".

Quali contano, per quel che dice la misura:

- `CRT-20` e' l'unica che con l'ingresso di CRT-13 migliora il risultato da
  sola: dal 57,4% al 62,4% di winrate.
- `CRT-11` e' **intrinseca**: il CISD e' il primo passo dell'ingresso, quindi
  se il setup e' arrivato fino a te il CISD c'e' gia'.
- `CRT-10`, `CRT-12`, `CRT-15`, `CRT-17`, `CRT-18`, `CRT-06` non sono state
  misurate insieme a questo ingresso. `non valutabile` su di esse e' comune e
  non e' un segnale negativo.

# Come decidere

Rifiuta quando il dossier somiglia ai casi che perdono: niente CISD, ombre
strette su N2, sweep marginale rispetto al range di N1, bias di comando che
viene da un timeframe lontanissimo rispetto a quello operativo.

Accetta quando il quadro e' coerente: CISD presente, sweep netto con coda
lunga, N2 stretta rispetto a N1, allineamento fra i timeframe.

Nel dubbio, RIFIUTA. Un'operazione non fatta costa zero; una fatta male costa
un R. Non c'e' simmetria e non devi cercarla.

Cita sempre almeno un numero del dossier nel motivo. "Il contesto non
convince" non e' un motivo: e' un modo di non darne uno.\
"""


@dataclass(frozen=True)
class Verdetto:
    """Cosa ha deciso il giudizio, e perche'."""

    accetta: bool
    motivo: str
    fiducia: str
    modello: str
    errore: Optional[str] = None

    @property
    def registrabile(self) -> str:
        """Una riga per l'archivio e per Telegram."""
        stato = "ACCETTA" if self.accetta else "RIFIUTA"
        if self.errore:
            return f"{stato} (fallimento chiuso: {self.errore})"
        return f"{stato} [{self.fiducia}] {self.motivo}"


def _astieniti(motivo: str) -> Verdetto:
    """Ogni strada che non arriva a un ACCETTA esplicito passa di qui."""
    log.warning("giudizio non disponibile, mi astengo: %s", motivo)
    return Verdetto(
        accetta=False,
        motivo="PRIN-99: giudizio non disponibile, astensione",
        fiducia="bassa",
        modello=MODELLO,
        errore=motivo,
    )


def giudica(dossier: dict[str, Any], timeout_sec: float = 60.0) -> Verdetto:
    """Chiede a Claude se eseguire questo setup. Rifiuta in ogni caso dubbio.

    `dossier` e' il quadro numerico costruito da `core/dossier.py`. Va passato
    come JSON e non come prosa: una descrizione a parole di un setup e' una
    descrizione che qualcuno ha gia' interpretato, e l'interpretazione e'
    proprio il lavoro che si sta chiedendo di fare.

    `timeout_sec` a 60 e' generoso perche' il bot valuta alla chiusura di
    candele orarie o superiori: un minuto su un'ora e' nulla. Su timeframe
    piu' bassi andrebbe rivisto, e con esso l'idea stessa di chiamare un
    modello dentro il percorso dell'ordine.
    """
    if anthropic is None:
        return _astieniti("libreria anthropic non installata")

    cfg = impostazioni()
    if not getattr(cfg, "GIUDIZIO_ATTIVO", False):
        return _astieniti("GIUDIZIO_ATTIVO non abilitato")

    # La chiave si passa ESPLICITAMENTE dalla configurazione. Lasciare che la
    # libreria la cerchi nell'ambiente funzionerebbe solo se qualcuno l'avesse
    # esportata a mano: `pydantic-settings` legge il `.env` dentro
    # `impostazioni()` e non lo riversa in `os.environ`.
    chiave = getattr(cfg, "ANTHROPIC_API_KEY", "") or None
    if chiave is None:
        return _astieniti("ANTHROPIC_API_KEY assente dal .env")

    try:
        cliente = anthropic.Anthropic(
            api_key=chiave, timeout=timeout_sec, max_retries=1)
    except Exception as errore:
        return _astieniti(f"client non costruibile: {errore!r}")

    try:
        risposta = cliente.messages.create(
            model=MODELLO,
            max_tokens=2000,
            # Le istruzioni non cambiano mai: si mettono in cache e il costo
            # per giudizio scende a quello del solo dossier.
            system=[{
                "type": "text",
                "text": ISTRUZIONI,
                "cache_control": {"type": "ephemeral"},
            }],
            # Il verdetto e' una decisione con soldi dietro: vale la pena che
            # ci pensi. Su candele orarie il tempo non e' un vincolo.
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {
                    "type": "json_schema",
                    "schema": SCHEMA_VERDETTO,
                },
            },
            messages=[{
                "role": "user",
                "content": (
                    "Ecco il dossier del setup. Rispondi col verdetto.\n\n"
                    + json.dumps(dossier, indent=2, ensure_ascii=False, sort_keys=True)
                ),
            }],
        )
    except anthropic.APIStatusError as errore:              # type: ignore[union-attr]
        return _astieniti(f"API {errore.status_code}: {errore.message}")
    except anthropic.APIConnectionError:                     # type: ignore[union-attr]
        return _astieniti("rete non raggiungibile")
    except Exception as errore:                              # pragma: no cover
        return _astieniti(f"errore imprevisto: {errore!r}")

    # Un rifiuto del modello e' un'astensione come le altre, non un ACCETTA.
    if risposta.stop_reason == "refusal":
        return _astieniti("il modello ha rifiutato di rispondere")
    if risposta.stop_reason == "max_tokens":
        return _astieniti("risposta troncata: verdetto non affidabile")

    testo = next((b.text for b in risposta.content if b.type == "text"), None)
    if not testo:
        return _astieniti("nessun blocco di testo nella risposta")

    try:
        dati = json.loads(testo)
    except json.JSONDecodeError as errore:
        return _astieniti(f"verdetto non e' JSON valido: {errore}")

    verdetto = dati.get("verdetto")
    if verdetto not in ("ACCETTA", "RIFIUTA"):
        return _astieniti(f"verdetto non riconosciuto: {verdetto!r}")

    return Verdetto(
        accetta=(verdetto == "ACCETTA"),
        motivo=str(dati.get("motivo", ""))[:500],
        fiducia=str(dati.get("fiducia", "bassa")),
        modello=risposta.model,
    )
