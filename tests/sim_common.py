import sys, random, os
ROOT=os.environ.get('P', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT)
try:
    import fastapi  # noqa
except ImportError:  # offline sandbox: use tiny stubs (engine-only testing)
    sys.path.insert(0,os.environ.get('STUBS','/home/claude/stubs'))
import server
from mission_rules import M, CITY_ORDER
def setup(city,mission,seed):
    random.seed(1600000+list(M).index((city,mission))*5000+seed)
    r=server.Room(code='X',humans=0,city=city,mission=mission,debug=False)
    server.start_game(r); server.assign_bot_characters(r)
    return r
def step(r):
    s=server
    if r.phase=='reveal':
        for p in r.players:
            if not p.reveal_done:
                r.public.add(random.choice([c for c in p.hand if c!='start'])); p.reveal_done=True
        s.start_turn(r)
    elif r.phase=='initial_pass':
        for i,p in enumerate(r.players):
            if str(i) not in r.initial_passes:
                r.initial_passes[str(i)]=random.choice([c for c in p.hand if c!='start'])
        s.resolve_initial_pass(r)
    elif r.phase=='offer_choice': s.choose_offer(r,r.pending['to'],s.bot_offer_choice(r,r.pending['to']))
    elif r.phase=='guess': s.guess_received_card(r,r.pending['to'],s.bot_number_guess(r,r.pending['to']))
    elif r.phase=='feedback': s.apply_feedback(r,r.pending['to'],s.bot_need(r.players[r.pending['to']],r.pending['card']))
    elif r.phase=='turn': s.advance_bot(r)
    else: raise Exception(r.phase)
def play(city,mission,seed,hook=None):
    r=setup(city,mission,seed)
    for _ in range(180):
        if r.phase=='ended': break
        if hook: hook(r)
        step(r)
    return r
