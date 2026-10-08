"""I pareri della squadra (`nvm/intelligenti/pareri.py`): ognuno vota col suo mestiere e dice perche'; il Bias resta
fedele alla previsione del giorno; il Capo pesa tutti, decide, sceglie le migliori del giro e impara di chi
fidarsi; il Rischio guarda la stessa valuta, il tetto e la giornata."""

from types import SimpleNamespace as NS

from nvm.agenti.cacciatore import Verso
from nvm.agenti.foto import Livello, Quadro
from nvm.intelligenti import al_lavoro, pareri as P
from nvm.intelligenti.metodo import Domanda, Metodo
from nvm.intelligenti.squadra import FIDUCIA_VOTO, MASSIMO_PER_GIRO, SOGLIA_PUNTI, Squadra
from nvm.tempo import TF, utc
from tests.test_vivo import ore_finte

# Martedi' 6 gennaio 2026, alle 3 di New York (le 8 UTC): sessione di Londra.
LONDRA = utc(2026, 1, 6, 8)


def _setup(tf=TF.H4, short=False, strumento="EURUSD", ingresso=1.1000, stop=1.0960, tp1=1.1060, alto=1.1060,
           basso=1.0980, n2=(1.0955, 1.1040, 1.1010), n3=LONDRA, presi=(), dentro=0, spread=0.0001):
    n2_basso, n2_alto, n2_chiusura = n2
    return NS(tf=tf, short=short, verso=Verso.SHORT if short else Verso.LONG, strumento=strumento, ingresso=ingresso,
              entrata=ingresso, stop=stop, tp1=tp1, range_alto=alto, range_basso=basso, n2_basso=n2_basso,
              n2_alto=n2_alto, n2_chiusura=n2_chiusura, n3_inizio=n3, presi=list(presi), dentro=dentro, spread=spread,
              dal_dxy=False)


def test_il_cacciatore_preferisce_i_grafici_grandi():
    assert P.cacciatore(_setup(tf=TF.D1), []).voto == 2
    da_solo = P.cacciatore(_setup(tf=TF.H4), [])
    assert da_solo.voto == -1 and "da solo" in da_solo.ragioni[0]
    assert P.cacciatore(_setup(tf=TF.H4), [TF.D1]).voto == 1


def test_il_key_level_pesa_quanto_e_grande_il_periodo():
    trimestre = Livello(TF.Q3, False, 1.0950, 0)
    assert P.key_level(_setup(presi=[trimestre])).voto == 2
    assert P.key_level(_setup(presi=[Livello(TF.D1, False, 1.0990, 0)])).voto == 0
    assert P.key_level(_setup(presi=[Livello(TF.D1, False, 1.0990, 0, oggi=True)])).voto == -1


def test_l_orario_sa_dell_apertura_di_wall_street_e_del_rollover():
    nove = utc(2026, 1, 6, 14)            # le 9 di New York
    indice = P.orario(_setup(strumento="NAS100", n3=nove))
    assert indice.voto == -2 and "Wall Street" in indice.ragioni[0]
    assert P.orario(_setup(n3=LONDRA)).voto == 1
    sedici = utc(2026, 1, 6, 21)          # le 16 di New York
    assert "rollover" in P.orario(_setup(n3=sedici)).ragioni[0]
    # Per il CRT del giorno l'ora la fa il grafico.
    assert P.orario(_setup(tf=TF.D1, n3=sedici)).voto == 0


def test_livelli_non_vuole_stop_che_prende_il_rumore():
    # CADJPY del 07/10: lo stop a 0,06 del range.
    stretto = P.livelli(_setup(ingresso=1.0985, stop=1.0982, alto=1.1035, basso=1.0985, tp1=1.1035), None, 0.0)
    assert stretto.voto == -2 and "0,06 del range" in stretto.ragioni[0]
    giusto = P.livelli(_setup(ingresso=1.1000, stop=1.0970, alto=1.1045, basso=1.0975, tp1=1.1045), None, 0.0)
    assert giusto.voto == 1


def test_il_grilletto_guarda_quanto_e_rientrata_la_candela_2():
    assert P.grilletto(_setup(n2=(1.0955, 1.1040, 1.1040))).voto == 1
    assert P.grilletto(_setup(n2=(1.0955, 1.1040, 1.0984))).voto == -1


def test_il_rischio_non_vuole_tre_scommesse_sullo_stesso_yen():
    # Il 07/10: CADJPY e NZDJPY comprati insieme, poi ancora CADJPY.
    ctx = P.Contesto(saldo=1000.0, aperte=[("CADJPY", 1, 0.01), ("NZDJPY", 1, 0.01)])
    r = P.rischio(_setup(strumento="AUDJPY"), ctx, 0.01)
    assert r.voto == -2 and "stessa valuta" in r.ragioni[0]
    libero = P.rischio(_setup(strumento="EURUSD"), P.Contesto(saldo=1000.0), 0.01)
    assert libero.voto == 1
    pieno = P.rischio(_setup(), P.Contesto(saldo=1000.0, aperte=[("XAUUSD", 1, 0.045)]), 0.01)
    assert pieno.voto <= -1 and any("tetto" in x for x in pieno.ragioni)
    giornata = P.rischio(_setup(), P.Contesto(saldo=1000.0, perso_oggi=0.035), 0.01)
    assert any("già perso" in x for x in giornata.ragioni)


def test_il_bias_resta_fedele_alla_previsione_del_giorno():
    ore = ore_finte(giorni=500)
    q = Quadro.da(ore, int(ore.t[-1]) + 3600)
    giorno = P.apertura_giorno(int(ore.t[-24 * 5]))
    # La previsione e' la stessa a qualunque ora del giorno la si faccia.
    a = P.previsione(q.taglia(giorno + 2 * 3600), giorno + 2 * 3600)
    b = P.previsione(q.taglia(giorno + 15 * 3600), giorno + 15 * 3600)
    assert a == b and a.giorno == giorno
    contro = P.Previsione(giorno, -1, 1e9 * -1, "3M", "accetta", "il trimestre ha chiuso sotto il minimo")
    vota = P.bias(_setup(n3=giorno + 3600), q, contro, None)
    assert vota.voto == -2 and "resto della mia idea" in vota.ragioni[0]
    assert P.bias(_setup(short=True, n3=giorno + 3600), q, contro, None).voto == 2
    # Se il livello e' gia' stato preso la previsione e' compiuta: non spinge piu', e non cambia verso.
    compiuta = P.Previsione(giorno, -1, 1e9, "3M", "accetta", "prova")
    assert P.bias(_setup(n3=giorno + 5 * 3600), q, compiuta, None).voto == 0
    # Gia' fatta oggi, resta quella anche se la si chiede di nuovo (la memoria della squadra la tiene).
    sq = Squadra.__new__(Squadra)
    sq.memoria = NS(previsioni={})
    p1 = al_lavoro.previsione_di(sq, "EURUSD", q.taglia(giorno + 3600), giorno + 3600)
    sq.memoria.previsioni["EURUSD"]["motivo"] = "detta stamattina"
    assert al_lavoro.previsione_di(sq, "EURUSD", q.taglia(giorno + 9 * 3600), giorno + 9 * 3600).motivo == "detta stamattina"
    assert p1.giorno == giorno


def _metodo(strumento="EURUSD", verso="acquisto") -> Metodo:
    ob = [Domanda(n, a, "le foto", True, f"risposta su {n}") for n, a in
          (("CRT", "Cacciatore"), ("key level", "Key level"), ("direzione", "Bias"))]
    return Metodo(ob, [], {"strumento": strumento, "coppia": "H4", "verso": verso, "giorno": "martedì", "ora": "03",
                           "modello": "apertura N3"}, {})


def _op():
    return NS(stop=1.0950, ingresso=1.1000, tp1=1.1050, tp2=1.1050, parziale=0.25)


def _pareri(**voti) -> list:
    return [P.Parere(a, voti.get(a.replace(" ", "_"), 0), [f"ragione di {a}"]) for a in P.VOTANO]


def test_il_capo_pesa_tutti_e_decide_lui(tmp_path):
    sq = Squadra(tmp_path)
    convinti = _pareri(Cacciatore=2, Key_level=1, Bias=2, Livelli=-1)
    v = sq.riunione("si", "EURUSD", _metodo(), LONDRA, op=_op(), pareri=convinti, contesto=P.Contesto(saldo=1000.0))
    assert v.punti == 4.0 and v.entra and v.puntata > 0
    chi = [c for c, _ in v.voci]
    assert chi == [a for a in P.VOTANO if a != "Rischio"] + ["Capo", "Rischio"]
    capo = v.voci[-2][1]
    assert "Contro: Livelli (-1)" in capo and "la responsabilità è mia" in capo
    poco = _pareri(Cacciatore=2, Bias=-2, Orario=-1)
    v2 = sq.riunione("no", "EURUSD", _metodo(), LONDRA, op=_op(), pareri=poco, contesto=P.Contesto(saldo=1000.0))
    assert v2.a_piu and not v2.entra and v2.punti < SOGLIA_PUNTI and "non è convinta" in v2.voci[-2][1]


def test_il_capo_impara_di_chi_fidarsi(tmp_path):
    sq = Squadra(tmp_path)
    voti = _pareri(Cacciatore=2, Key_level=2, Bias=1, Orario=-2)
    sq.riunione("k", "NAS100", _metodo("NAS100"), LONDRA, op=_op(), pareri=voti, contesto=P.Contesto(saldo=1000.0))
    lezioni = sq.rifletti("k", -1.0, preso=True)
    w = sq.memoria.capo["voti"]
    assert w["Orario"] > FIDUCIA_VOTO and w["Cacciatore"] < FIDUCIA_VOTO
    assert any(l["agente"] == "Orario" and l["giusto"] and "avevo ragione" in l["lezione"] for l in lezioni)
    capo = next(l for l in lezioni if l["agente"] == "Capo")
    assert "la responsabilità è mia" in capo["lezione"] and "Orario" in capo["lezione"]
    assert sq.memoria.pagella["Orario"]["no"] == [1, 1] and sq.memoria.pagella["Cacciatore"]["si"] == [1, 0]


def test_il_capo_sceglie_le_migliori_del_giro(tmp_path):
    sq = Squadra(tmp_path)
    n3 = LONDRA
    occasioni = [("CADJPY", 6), ("NZDJPY", 5), ("GBPUSD", 4), ("EURCHF", 4), ("AUDCAD", 3.5), ("USDCHF", 3)]
    decisioni, verdetti = [], {}
    for i, (s, forza) in enumerate(occasioni):
        v = sq.riunione(s, s, _metodo(s), n3, op=_op(), pareri=_pareri(Cacciatore=2, Key_level=1),
                        contesto=P.Contesto(saldo=1000.0))
        assert v.entra
        v.punti, v.fiducia = forza, forza / 10
        verdetti[s] = v
        decisioni.append(NS(chiave=s, r=NS(strumento=s, quando=n3, verso=Verso.LONG)))
    testo = al_lavoro.scegli(sq, decisioni, verdetti, P.Contesto(saldo=1000.0), {"USDCHF"})
    presi = [s for s, v in verdetti.items() if v.entra]
    # Una sola idea sullo yen (NZDJPY e' la stessa scommessa di CADJPY), al massimo tre, niente sugli occupati.
    assert presi == ["CADJPY", "GBPUSD", "EURCHF"] and len(presi) == MASSIMO_PER_GIRO
    assert "stessa scommessa di CADJPY" in verdetti["NZDJPY"].lasciata
    assert "già scelto le 3 migliori" in verdetti["AUDCAD"].lasciata
    assert testo.startswith("Giro delle 03:00 di New York") and "Scelgo: CADJPY" in testo and "Lascio:" in testo


def test_nel_secondo_giro_si_sentono_e_cambiano_idea_dicendo_perche():
    pareri = _pareri(Cacciatore=1, Bias=-2, Gap=1, Rischio=1)
    usati = P.confronto(pareri)
    per = {x.agente: x for x in pareri}
    assert per["Cacciatore"].voto == 0 and per["Cacciatore"].primo == 1 and "Sentito il Bias" in per["Cacciatore"].sentito
    assert per["Gap"].voto == 0 and "Sentito il Bias" in per["Gap"].sentito
    assert "passo a +0" in per["Cacciatore"].frase()
    assert ("Cacciatore sente Bias", -1) in usati and ("Rischio sente Bias", -1) in usati
    # Un ascolto che dal vivo non aiuta si spegne.
    pareri = _pareri(Cacciatore=1, Bias=-2)
    assert not P.confronto(pareri, {"Cacciatore sente Bias"}) and pareri[0].voto == 1


def test_la_squadra_non_va_mai_contro_la_previsione_della_domenica(tmp_path):
    ore = ore_finte(giorni=500)
    q = Quadro.da(ore, int(ore.t[-1]) + 3600)
    b = P.bias(_setup(), q, None, "ribassista")
    assert b.voto == -2 and b.veto and "domenica" in b.veto
    assert not P.bias(_setup(short=True), q, None, "ribassista").veto
    # Anche con tutti gli altri a favore il Capo non entra contro la previsione, e lo dice.
    sq = Squadra(tmp_path)
    voti = _pareri(Cacciatore=2, Key_level=2, Gap=2, DXY=1, Livelli=2, Grilletto=1)
    voti[2] = b
    v = sq.riunione("contro", "EURUSD", _metodo(), LONDRA, op=_op(), pareri=voti, contesto=P.Contesto(saldo=1000.0))
    assert v.a_piu and not v.entra and "non andiamo contro la nostra previsione" in v.voci[-2][1]
