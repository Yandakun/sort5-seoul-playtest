import sys, collections
sys.path.insert(0,'tests')
from sim_common import *
import server as s
N=120
targets=[('paris',1),('paris',3),('paris',4),('paris',5),('tokyo',1),('tokyo',3),('tokyo',4),('berlin',1),('berlin',4),('new_york',4)]
SYM='▲●■★'
for city,m in targets:
    cfg=M[(city,m)]
    first_char=next((ch for ch,pos in cfg.completion_positions if pos==1),None)
    rec=collections.Counter(); tot=0; drain=collections.Counter(); comp=collections.Counter(); fails=0
    first_done_before_chip_half=0; sets_by_pos=collections.Counter()
    for seed in range(N):
        r=play(city,m,seed)
        for e in r.turn_events:
            rec[r.players[e['to']].char]+=1; tot+=1
        comp[len(r.completion_order)]+=1
        if r.result!='success':
            fails+=1
            # drained player = one whose chips hit 0 (individual) 
            if r.shared_chips is None:
                z=[p.char for p in r.players if not p.done and p.chips==0]
                for c in z: drain[c]+=1
            else: drain['pool']+=1
    sh={SYM[c]:round(rec[c]/tot,2) for c in range(4)}
    print(f"{city}#{m} first-required={SYM[first_char] if first_char is not None else '-'}  recv-share={sh}  drained(at fail)={ {SYM[k] if k!='pool' else 'pool':v for k,v in drain.items()} }  completed-sets-dist={dict(sorted(comp.items()))}")
