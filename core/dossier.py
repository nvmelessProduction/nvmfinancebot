"""Il quadro numerico che il trader discrezionale riceve.

Numeri, non prosa. Una descrizione a parole di un setup e' una descrizione che
qualcuno ha gia' interpretato, e l'interpretazione e' esattamente il lavoro
che si sta chiedendo di fare a chi legge.

Contiene solo cio' che e' noto **al momento dell'ingresso**. Niente che venga
dopo: un dossier con dentro il futuro produrrebbe un giudizio brillante e
inutile, che e' il quinto errore di questo progetto e non sara' il sesto.
"""

from __future__ import annotations

from typing import Any

from core.definizioni import Bias, cisd, peso_ombre
from core.motore import Decisione, Fotografia
from core.parametri import TF
from core.stato import candele_visibili


def _pip(strumento: str) -> float:
    """Quanto vale un pip su questo strumento.

    Convenzione, non misura: sui cambi e' il quarto decimale, sulle coppie in
    yen il secondo, sull'oro il secondo. Serve solo a rendere leggibili le
    distanze -- i calcoli restano sui prezzi -- ma va scritta da qualche
    parte, perche' lasciarla indovinare e' gia' costato un verdetto.
    """
    if strumento.endswith("JPY"):
        return 0.01
    if strumento.startswith("XAU"):
        return 0.01
    return 0.0001


def costruisci(
    foto: Fotografia,
    decisione: Decisione,
    tf_trigger: TF,
) -> dict[str, Any]:
    """Il dossier di un setup approvato dalle regole.

    Le due voci che contano davvero, perche' sono le uniche misurate:

    - `cisd_presente`: con CISD il rendimento passa da +0,017 a +0,089 R,
      senza e' negativo. E' il singolo dato piu' informativo del dossier.
    - `peso_ombre_n2`: le ombre piccole danno 33,6% di winrate contro il
      59,6% della base. Uno sweep "pulito" e' un cattivo segno.
    """
    candele = candele_visibili(foto.candele_per_tf.get(tf_trigger, ()), foto.istante)
    n1 = candele[-2] if len(candele) >= 2 else None
    n2 = candele[-1] if candele else None

    dossier: dict[str, Any] = {
        "strumento": foto.strumento,
        "istante_utc": foto.istante.isoformat(),
        "timeframe_crt": tf_trigger.value,
        "azione_proposta": decisione.azione,
        "direzione_sul_future": decisione.direzione.value if decisione.direzione else None,
        "prezzo_ingresso": round(foto.prezzo_cfd, 6),
        "livello_stop": round(decisione.livello_stop, 6) if decisione.livello_stop else None,
        "tp1": round(decisione.tp1, 6) if decisione.tp1 else None,
        "target_finale": round(decisione.target_finale, 6) if decisione.target_finale else None,
        "rapporto_su_tp1": round(decisione.rapporto_su_tp1, 3) if decisione.rapporto_su_tp1 else None,
        "volume_lotti": decisione.volume,
        "spread_corrente": round(foto.spread, 6),
        "bias_per_timeframe": {tf.value: b.value for tf, b in foto.bias_per_tf.items()},
        "bias_dxy": foto.bias_dxy.value,
        "posizioni_gia_aperte": dict(foto.posizioni_aperte_per_strumento),
        "regole_applicate": list(decisione.regole_applicate),
    }

    # --- Le due voci misurate ---------------------------------------------
    if n2 is not None:
        peso = peso_ombre(n2)
        dossier["peso_ombre_n2"] = round(peso, 3) if peso is not None else None
        dossier["n2"] = {
            "apertura": n2.apertura, "massimo": n2.massimo,
            "minimo": n2.minimo, "chiusura": n2.chiusura,
        }
    if n1 is not None and n2 is not None:
        range_n1 = n1.massimo - n1.minimo
        range_n2 = n2.massimo - n2.minimo
        dossier["n1"] = {
            "apertura": n1.apertura, "massimo": n1.massimo,
            "minimo": n1.minimo, "chiusura": n1.chiusura,
        }
        dossier["n2_su_n1"] = round(range_n2 / range_n1, 3) if range_n1 > 0 else None
        if decisione.direzione is Bias.SHORT:
            dossier["sweep_oltre_n1"] = round(n2.massimo - n1.massimo, 6)
        elif decisione.direzione is Bias.LONG:
            dossier["sweep_oltre_n1"] = round(n1.minimo - n2.minimo, 6)

    # --- Le stesse distanze, in unita' che non si possono fraintendere ----
    #
    # Il dossier dava solo prezzi grezzi, e chi legge doveva indovinare cosa
    # fosse un pip su quello strumento. Il 2026-09-21, in produzione, il
    # giudizio ha letto uno spread di `1.0e-05` su GBPUSD e l'ha chiamato
    # "1,0 pip": e' 0,1. Sbagliato di dieci volte, e nella direzione che fa
    # sembrare ogni setup non profittevole -- "range di 1,2 pip contro uno
    # spread di 1,0" invece di 1,2 contro 0,1. Quel rifiuto era motivato da
    # un numero che non esisteva.
    #
    # Le distanze si danno quindi anche in PIP, con la dimensione del pip
    # dichiarata accanto, e soprattutto in MULTIPLI DELLO SPREAD -- che non
    # ha bisogno di nessuna convenzione ed e' il rapporto che decide se
    # un'operazione puo' pagarsi.
    pip = _pip(foto.strumento)
    spread = float(foto.spread or 0.0)
    dossier["dimensione_pip"] = pip
    dossier["spread_in_pip"] = round(spread / pip, 2) if pip else None

    def _in_pip(valore):
        return round(valore / pip, 2) if (pip and valore is not None) else None

    def _in_spread(valore):
        return round(valore / spread, 1) if (spread > 0 and valore is not None) else None

    if n1 is not None and n2 is not None:
        dossier["range_n1_in_pip"] = _in_pip(n1.massimo - n1.minimo)
        dossier["range_n1_in_spread"] = _in_spread(n1.massimo - n1.minimo)
        if dossier.get("sweep_oltre_n1") is not None:
            dossier["sweep_in_pip"] = _in_pip(dossier["sweep_oltre_n1"])
            dossier["sweep_in_spread"] = _in_spread(dossier["sweep_oltre_n1"])

    if decisione.livello_stop and foto.prezzo_cfd:
        rischio = abs(foto.prezzo_cfd - decisione.livello_stop)
        dossier["distanza_stop_in_pip"] = _in_pip(rischio)
        dossier["distanza_stop_in_spread"] = _in_spread(rischio)
        # Quanto dell'R se ne va in spread. E' il numero che dice se
        # l'operazione puo' pagarsi: a 0,3 serve un winrate molto piu' alto.
        dossier["costo_spread_in_r"] = (
            round(spread / rischio, 3) if rischio > 0 else None)

    # --- Il responso di TUTTE le conferme di Romeo (CRT-14) ---------------
    #
    # E' la parte che conta per chi giudica. Ogni conferma dice `si`, `no`
    # oppure `non valutabile`, e le spente parlano come le accese: a un
    # trader discrezionale servono TUTTE INSIEME, pesate, non applicate una
    # per una come veti in AND.
    #
    # Misurato: usate come filtri rigidi, con tutte accese si trovano 18 CRT
    # su 360 valutazioni e se ne bloccano 18. Il bot tace del tutto. Come
    # informazione, invece, sono il quadro su cui si decide.
    if decisione.responso_romeo:
        dossier["conferme_di_romeo"] = {
            regola: ("si" if esito is True else
                     "no" if esito is False else "non valutabile")
            for regola, esito in sorted(decisione.responso_romeo.items())
        }
        dossier["conferme_favorevoli"] = sum(
            1 for e in decisione.responso_romeo.values() if e is True)
        dossier["conferme_contrarie"] = sum(
            1 for e in decisione.responso_romeo.values() if e is False)

    # Il CISD si cerca sul timeframe piu' basso disponibile nella fotografia:
    # e' li' che il cambio di consegna si vede.
    dossier["cisd_presente"] = None
    for tf in (TF.H1, TF.H4, TF.D1):
        if tf is tf_trigger:
            continue
        serie = candele_visibili(foto.candele_per_tf.get(tf, ()), foto.istante)
        if len(serie) < 3 or decisione.direzione is None:
            continue
        livello = cisd(serie[-12:], decisione.direzione)
        dossier["cisd_presente"] = livello is not None
        dossier["cisd_timeframe"] = tf.value
        if livello is not None:
            dossier["cisd_livello"] = round(livello, 6)
        break

    return dossier
