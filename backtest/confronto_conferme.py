"""La strategia di Romeo COMPLETA contro la parte misurata positiva.
Stesso motore, stesse candele, stesso costo. Cambia solo quali conferme."""
import bisect, math, pickle, sys
from pathlib import Path
sys.path.insert(0, "/home/user/nvmfinancebot")
from core.definizioni import (Bias, cisd, divergenza_smt, double_purge,
    meta_ombra, meta_tenuta, peso_ombre, verso_del_double_purge)
from core.contesto import dentro_finestra_crt
from core.parametri import COMPAGNE_SMT, TF

SCR = Path("/tmp/claude-0/-home-user-nvmfinancebot/524092c4-5c76-5af6-a985-c494bd565758/scratchpad/bt")
S = pickle.load(open(SCR/"duka_serie.pickle","rb"))
STRUM = ["EURUSD","GBPUSD","AUDUSD","USDCHF","USDJPY","XAUUSD"]

def sigma(v):
    n=len(v)
    if n<2: return 0.0
    m=sum(v)/n; var=sum((x-m)**2 for x in v)/(n-1)
    return m/math.sqrt(var/n) if var>0 else 0.0

def segnali(alte, mult=3.0):
    out=[]
    for i in range(1,len(alte)):
        n1,n2=alte[i-1],alte[i]
        meta=(n1.massimo+n1.minimo)/2
        if not (n1.minimo <= n2.chiusura <= n1.massimo): continue
        if n2.massimo>n1.massimo and n2.chiusura>meta: d,stop=Bias.SHORT,n2.massimo
        elif n2.minimo<n1.minimo and n2.chiusura<meta: d,stop=Bias.LONG,n2.minimo
        else: continue
        ing=n2.chiusura; r=abs(ing-stop)
        if r<=0: continue
        bers = ing - mult*r if d is Bias.SHORT else ing + mult*r
        out.append((i,d,ing,stop,bers,n1,n2))
    return out

def prova(attive):
    res=[]; bloccati={k:0 for k in attive}
    for st in STRUM:
        bid=S[st]["BID"].get("M1",()); ask=S[st]["ASK"].get("M1",())
        bb=S[st]["BID"].get("D1",())
        if len(bid)<30 or len(bb)<30 or len(ask)<30: continue
        t_bid=[c.orario for c in bid]; t_ask=[c.orario for c in ask]; t_bb=[c.orario for c in bb]
        comp={c: S[c]["BID"].get("M1",()) for c in COMPAGNE_SMT.get(st,()) if c in S}
        for (i,d,ing,stop,bers,n1,n2) in segnali(bid):
            j=bisect.bisect_right(t_bb,n2.orario)
            ingr=bb[max(0,j-12):j]
            bloc=[]
            if attive.get("CRT-20"):
                p=peso_ombre(n2)
                if p is not None and p<0.6: bloc.append("CRT-20")
            if attive.get("CRT-11") and ingr and cisd(ingr,d) is None: bloc.append("CRT-11")
            if attive.get("CRT-12") and comp:
                vs = Bias.LONG if d is Bias.SHORT else Bias.SHORT
                g=[]
                for cn,cs in comp.items():
                    tc=[c.orario for c in cs]; k=bisect.bisect_right(tc,n2.orario)
                    e=divergenza_smt(st,bid[:i+1],cs[:k],cn,vs)
                    if e is not None: g.append(e)
                if g and not any(g): bloc.append("CRT-12")
            if attive.get("CRT-10") and double_purge(n1,n2):
                v=verso_del_double_purge(n2)
                if v is not Bias.NESSUNA and v is not d: bloc.append("CRT-10")
            if attive.get("CRT-15"):
                if dentro_finestra_crt(n2.orario, TF.D1) is False: bloc.append("CRT-15")
            if attive.get("CRT-17") and ingr:
                t=meta_tenuta(n1,ingr)
                if t is not None and t is not Bias.NESSUNA and t is not d: bloc.append("CRT-17")
            if attive.get("CRT-18"):
                m=meta_ombra(n2, superiore=(d is Bias.SHORT))
                if m is not None:
                    if (d is Bias.SHORT and n2.chiusura>m) or (d is Bias.LONG and n2.chiusura<m):
                        bloc.append("CRT-18")
            if bloc:
                for b in bloc:
                    if b in bloccati: bloccati[b]+=1
                continue
            ka=bisect.bisect_right(t_ask,n2.orario)-1; kb=bisect.bisect_right(t_bid,n2.orario)-1
            if ka<0 or kb<0: continue
            sp=ask[ka].chiusura-bid[kb].chiusura
            r=abs(ing-stop)
            if not (0<sp<r): continue
            costo=(2*sp)/r; erre=abs(bers-ing)/r
            esito=None
            for b in bb[j:j+30]:
                if d is Bias.SHORT:
                    if b.massimo>=stop: esito=-1.0; break
                    if b.minimo<=bers: esito=erre; break
                else:
                    if b.minimo<=stop: esito=-1.0; break
                    if b.massimo>=bers: esito=erre; break
            if esito is None:
                seg=bb[j:j+30]
                if not seg: continue
                sn=1 if d is Bias.LONG else -1
                esito=sn*(seg[-1].chiusura-ing)/r
            res.append(esito-costo)
    return res, bloccati

TUTTE={k:True for k in ["CRT-10","CRT-11","CRT-12","CRT-15","CRT-17","CRT-18","CRT-20"]}
MISURATE={"CRT-11":True,"CRT-20":True}

for nome, att in [("STRATEGIA COMPLETA (tutte accese)",TUTTE),
                  ("solo CISD + ombre (misurate)",MISURATE),
                  ("CRT base (nessuna conferma)",{})]:
    r,b = prova(att)
    if not r: print(f"{nome:<38} nessuna operazione"); continue
    v=sum(1 for x in r if x>0)
    print(f"{nome:<38} n={len(r):>4}  win={100*v/len(r):>5.1f}%  "
          f"R netto={sum(r)/len(r):>+7.4f}  σ={sigma(r):>+5.1f}")
    if att and b:
        print(f"{'':38} bloccati: " + ", ".join(f"{k}:{n}" for k,n in sorted(b.items()) if n))
