import random, server
from mission_rules import M

def play(city,mission,seed):
    random.seed(900000 + list(M).index((city,mission))*1000 + seed)
    r=server.Room(code='BENCH',humans=0,city=city,mission=mission,debug=False)
    server.start_game(r)
    server.assign_bot_characters(r)
    for _ in range(140):
        if r.phase=='ended':return r.result
        if r.phase=='reveal':
            for p in r.players:
                if not p.reveal_done:
                    r.public.add(random.choice([c for c in p.hand if c!='start']));p.reveal_done=True
            server.start_turn(r)
        elif r.phase=='initial_pass':
            for i,p in enumerate(r.players):
                if str(i) not in r.initial_passes:
                    r.initial_passes[str(i)]=random.choice([c for c in p.hand if c!='start'])
            server.resolve_initial_pass(r)
        elif r.phase=='offer_choice':server.choose_offer(r,r.pending['to'],server.bot_offer_choice(r,r.pending['to']))
        elif r.phase=='guess':server.guess_received_card(r,r.pending['to'],server.bot_number_guess(r,r.pending['to']))
        elif r.phase=='feedback':server.apply_feedback(r,r.pending['to'],server.bot_need(r.players[r.pending['to']],r.pending['card']))
        elif r.phase=='turn':server.advance_bot(r)
        else:raise Exception((city,mission,r.phase))
    return 'stalled'

for city in ('seoul','berlin','new_york','tokyo','london','paris'):
    out=[]
    for mission in range(1,6):
        n=sum(play(city,mission,seed)=='success' for seed in range(35))
        out.append(n)
    print(city,*out,'total',sum(out),flush=True)
