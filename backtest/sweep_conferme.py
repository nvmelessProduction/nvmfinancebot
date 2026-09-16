"""Tutti i 128 sottoinsiemi delle conferme di Romeo. Quale e' il piu' grande
che resta positivo?"""
import itertools, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-nvmfinancebot/524092c4-5c76-5af6-a985-c494bd565758/scratchpad")
from completa import prova, sigma

REGOLE = ["CRT-10","CRT-11","CRT-12","CRT-15","CRT-17","CRT-18","CRT-20"]
righe = []
for k in range(len(REGOLE)+1):
    for combo in itertools.combinations(REGOLE, k):
        att = {r: True for r in combo}
        r, _ = prova(att)
        if len(r) < 40:      # meno di due operazioni l'anno: non e' un bot
            continue
        netto = sum(r)/len(r)
        righe.append((len(combo), netto, sigma(r), len(r), combo))

# Ordina: prima quante regole di Romeo, poi il rendimento.
righe.sort(key=lambda x: (-x[0], -x[1]))
print(f"{'#':>2} {'n':>5} {'R netto':>9} {'σ':>6}  regole attive")
print("="*76)
visto = set()
for nreg, netto, sg, n, combo in righe:
    if nreg in visto and netto <= 0: continue
    if nreg not in visto:
        visto.add(nreg)
    if netto > 0 or nreg not in [x[0] for x in righe if x[1] > 0]:
        print(f"{nreg:>2} {n:>5} {netto:>+9.4f} {sg:>+5.1f}σ  {', '.join(combo) or '(nessuna)'}")

print("\n--- LE MIGLIORI IN ASSOLUTO ---")
for nreg, netto, sg, n, combo in sorted(righe, key=lambda x: -x[1])[:6]:
    print(f"{nreg:>2} regole  n={n:>4}  R={netto:>+8.4f}  σ={sg:>+5.1f}  {', '.join(combo) or '(nessuna)'}")
