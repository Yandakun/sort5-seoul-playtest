"""Public-state scheduler: does not peek at other hands; defaults off."""
import copy, random
import server
from mission_rules import M

def make(city='paris',mission=1,seed=2):
    random.seed(seed)
    r=server.Room(code='TEST', humans=0, city=city,mission=mission,debug=False)
    server.start_game(r)
    server.assign_bot_characters(r)
    return r

def test_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv('SORT5_SCHEDULER', raising=False)
    assert server.os.getenv('SORT5_SCHEDULER','off')=='off'

def test_order_uses_public_constraints():
    r=make()
    schedules=server.ai_public_completion_schedules(r)
    assert schedules
    assert all([r.players[i].char for i in o]==[0,1,2,3] for o in schedules)

def test_scheduler_ignores_hidden_hands_and_goals():
    r=make('tokyo',4)
    observer=0
    beliefs={i:{c:0.25 for c in server.COLORS} for i in range(4)}
    a=(server.ai_public_completion_schedules(r),server.ai_scheduler_value(r,observer,1,'green',beliefs))
    for j,p in enumerate(r.players):
        if j!=observer:
            p.hand=list(reversed(p.hand))
            p.goal='blue' if p.goal!='blue' else 'green'
    b=(server.ai_public_completion_schedules(r),server.ai_scheduler_value(r,observer,1,'green',beliefs))
    assert a==b

def test_scheduler_respects_character_rank():
    for (city,mission),cfg in M.items():
        if not cfg.completion_positions: continue
        r=make(city,mission)
        for order in server.ai_public_completion_schedules(r):
            assert all(order[rank-1]==next(i for i,p in enumerate(r.players) if p.char==ch)
                       for ch,rank in cfg.completion_positions)
