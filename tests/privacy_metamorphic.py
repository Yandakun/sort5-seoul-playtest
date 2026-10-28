import sys, copy, random, threading
sys.path.insert(0,'tests')
from sim_common import *
import server as s

def clone(room):
    memo={id(room.lock):threading.RLock()}
    return copy.deepcopy(room,memo)

def scramble_hidden(room, obs, rng):
    # 1) permute hidden (non-public, non-start) cards among other players' hands
    others=[j for j in range(4) if j!=obs]
    slots=[(j,k) for j in others for k,c in enumerate(room.players[j].hand)
           if c!='start' and c not in room.public]
    cards=[room.players[j].hand[k] for j,k in slots]
    rng.shuffle(cards)
    for (j,k),c in zip(slots,cards): room.players[j].hand[k]=c
    # 2) other players' private AI state
    for j in others:
        p=room.players[j]
        p.goal=rng.choice(s.COLORS)
        p.observed_offers=[dict(o,color=rng.choice(s.COLORS)) for o in p.observed_offers]
        if p.last_received not in (None,'start'): p.last_received=rng.choice(s.COLORS)+'-%d'%rng.randint(1,5)
    # 3) evidence / events that the observer could not see the card of
    for ev in room.evidence:
        if ev['sender']!=obs and ev['to']!=obs and not ev['public']:
            ev['color']=rng.choice(s.COLORS); ev['card']=rng.choice(s.COLORS)+'-%d'%rng.randint(1,5)
    for ev in room.turn_events:
        if ev['from']!=obs and ev['to']!=obs and not ev['face_up']:
            ev['number']=rng.randint(1,5)
    return room

def outputs(room,obs):
    random.seed(777)
    d={}
    d['beliefs']=s.bot_color_beliefs(room,obs)
    d['goal']=s.bot_goal(room,obs)
    d['choice']=s.bot_choice(room,obs) if room.phase=='turn' else None
    return d

tests=0; diffs=[]
rng=random.Random(5)
for (city,m) in M:
    for seed in range(20):
        r=setup(city,m,seed)
        for _ in range(180):
            if r.phase=='ended': break
            if r.phase=='turn' and r.players[r.turn].bot:
                obs=r.turn
                a=outputs(clone(r),obs)
                b=outputs(scramble_hidden(clone(r),obs,rng),obs)
                tests+=1
                if a!=b: diffs.append((city,m,seed,r.move_count,a['choice'],b['choice']))
            step(r)
print("decision points tested:",tests,"| decisions that changed when hidden info was scrambled:",len(diffs))
for d in diffs[:10]: print(d)
