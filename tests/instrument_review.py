import sys, itertools, collections, json
sys.path.insert(0,'tests')
from sim_common import *
import server as s
N=int(sys.argv[1]) if len(sys.argv)>1 else 120
COLORS=s.COLORS
def full_set(info):
    for c in COLORS:
        if {s.num(x) for x in info if s.col(x)==c}=={1,2,3,4,5} and sum(s.col(x)==c for x in info)==5: return c
    return None

def ceiling(r, semantics):
    cfg=s.rule(r)
    cnt=[collections.Counter(s.col(c) for c in (p.hand+([p.held_card] if p.held_card else [])) if c!='start') for p in r.players]
    best=False
    for perm in itertools.permutations(COLORS):
        m=[5-cnt[i][perm[i]] for i in range(4)]
        for need in itertools.combinations(range(4),cfg.target_sets):
            if cfg.pool is not None:
                cap=cfg.pool - (1 if semantics=='engine' else 0) + 1
                if sum(m[i] for i in need)<=cap: return True
                continue
            ok=False
            for L in need:
                if all(m[i] <= r.players[i].chips - (1 if semantics=='engine' else 0) + (1 if i==L else 0) for i in need): ok=True;break
            if ok: return True
    return False

rows={}
for (city,m) in M:
    A=collections.Counter(); 
    for seed in range(N):
        stats=collections.Counter()
        r=setup(city,m,seed)
        A['ceil_engine']+=ceiling(r,'engine'); A['ceil_alt']+=ceiling(r,'alt')
        # t=0 goals
        goals=[p.goal for p in r.players]
        A['t0_distinct_goals_eq4']+=len(set(goals))==4
        cnt=[collections.Counter(s.col(c) for c in (p.hand+([p.held_card] if p.held_card else [])) if c!='start') for p in r.players]
        orc=max(itertools.permutations(COLORS),key=lambda pm:sum(cnt[i][pm[i]] for i in range(4)))
        A['t0_goal_matches_oracle_players']+=sum(goals[i]==orc[i] for i in range(4))
        A['t0_oracle_in_place']+=sum(cnt[i][orc[i]] for i in range(4))
        A['t0_goals_in_place']+=sum(cnt[i][goals[i]] for i in range(4))
        prev_goal=list(goals); prev_holder={}; flips=0; coll=0; dec=0
        orig=s.pass_card
        def wrapped(room,i,card,target,_o=orig):
            nonlocal_stats=stats
            p=room.players[i]; info=[c for c in p.hand if c!='start']
            fs=full_set(info) if len(info)>=5 else None
            nonlocal_stats['passes']+=1
            if fs and s.col(card)==fs: nonlocal_stats['set_break']+=1
            if prev_holder.get(card)==target: nonlocal_stats['bounce']+=1
            if card!='start' and s.col(card)==p.goal: nonlocal_stats['goal_card_given']+=1
            prev_holder[card]=i
            return _o(room,i,card,target)
        s.pass_card=wrapped
        try:
            for _ in range(180):
                if r.phase=='ended': break
                act=[p for p in r.players if not p.done]
                g=[p.goal for p in act]
                if r.phase=='turn':
                    dec+=1; coll+= len(set(g))<len(g)
                for i,p in enumerate(r.players):
                    if p.goal!=prev_goal[i]: flips+=1; prev_goal[i]=p.goal
                step(r)
        finally: s.pass_card=orig
        ev=r.turn_events
        A['games']+=1; A['win']+=r.result=='success'
        A['passes']+=stats['passes']; A['bounce']+=stats['bounce']; A['set_break']+=stats['set_break']
        A['games_with_set_break']+=stats['set_break']>0
        A['goal_card_given']+=stats['goal_card_given']
        A['flips']+=flips; A['coll_steps']+=coll; A['dec_steps']+=dec
        react=[e for e in ev if e['reaction']]; A['green']+=sum(e['reaction']=='positive' for e in react); A['react']+=len(react)
        if r.result!='success':
            A['fail']+=1
            A['completed_at_fail']+=len(r.completion_order)
            act=[p for p in r.players if not p.done]
            if r.shared_chips is None: A['leftover_chips_at_fail']+=sum(p.chips for p in act)
            if 'chip' in r.reason.lower(): A['fail_chip']+=1
            else: A[('fail_other:'+r.reason[:40])]+=1
    rows[f'{city}#{m}']=A
out={}
print(f"{'mission':10}{'win':>5}{'ceilE':>6}{'ceilA':>6} | {'pass':>5}{'bncR':>6}{'brk/g':>6}{'g_brk':>6}{'givGoal':>8} | {'flip/g':>6}{'coll%':>6}{'distinct0':>10}{'inPlace0':>9}{'orcInPl':>8}{'green%':>7}{'leftChip':>9}{'doneAtF':>8}")
for k,A in rows.items():
    g=A['games']; f=max(1,A['fail'])
    print(f"{k:10}{A['win']:>5}{A['ceil_engine']:>6}{A['ceil_alt']:>6} | {A['passes']/g:5.1f}{A['bounce']/max(1,A['passes']):6.2f}{A['set_break']/g:6.2f}{A['games_with_set_break']:>6}{A['goal_card_given']/max(1,A['passes']):8.2f} | {A['flips']/g:6.2f}{100*A['coll_steps']/max(1,A['dec_steps']):6.1f}{A['t0_distinct_goals_eq4']:>10}{A['t0_goals_in_place']/g:9.1f}{A['t0_oracle_in_place']/g:8.1f}{100*A['green']/max(1,A['react']):7.1f}{A['leftover_chips_at_fail']/f:9.1f}{A['completed_at_fail']/f:8.2f}")
json.dump({k:{str(a):b for a,b in v.items()} for k,v in rows.items()},open('review_instrument.json','w'),ensure_ascii=False,indent=1)
