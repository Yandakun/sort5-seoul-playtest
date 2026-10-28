"""Bounded randomized full-turn progression checks (not proof of solvability)."""
import random
import pytest
import server
from mission_rules import M


def setup(city, mission, seed):
    random.seed(seed)
    r = server.Room(code=f'AUD{seed:03}', humans=1, city=city, mission=mission, debug=False)
    r.players = [server.Player(name='Human', token='H', seat=0)]
    server.start_game(r)
    r.players[0].char = 0
    server.assign_bot_characters(r)
    return r


def progress(r):
    if r.phase=='reveal':
        for p in r.players:
            if not p.reveal_done:
                card=next(c for c in p.hand if c!='start')
                r.public.add(card);p.reveal_done=True
        server.start_turn(r)
    elif r.phase=='initial_pass':
        for i,p in enumerate(r.players):
            if str(i) not in r.initial_passes:
                r.initial_passes[str(i)]=next(c for c in p.hand if c!='start')
        server.resolve_initial_pass(r)
    elif r.phase=='offer_choice':
        server.choose_offer(r,r.pending['to'],random.randrange(2))
    elif r.phase=='guess':
        server.guess_received_card(r,r.pending['to'],random.randint(1,5))
    elif r.phase=='feedback':
        server.apply_feedback(r,r.pending['to'],random.choice([True,False]))
    elif r.phase=='turn':
        if r.players[r.turn].bot:
            server.advance_bot(r)
        else:
            i=r.turn;p=r.players[i]
            options=[(c,j) for c in p.hand for j in range(4) if server.can_pass(r,i,c,j)]
            if not options:
                server.finish(r,False,'No legal human action');return
            c,j=random.choice(options)
            if p.char in server.rule(r).two_cards:
                pair=next((d for d in p.hand if d!=c and server.can_pass(r,i,d,j)),None)
                if pair is None:
                    server.finish(r,False,'No legal offer pair');return
                server.offer_cards(r,i,[c,pair],j)
            else:
                server.pass_card(r,i,c,j)
    else:
        raise AssertionError(f'Unrecognized phase {r.phase}')

@pytest.mark.parametrize('city,mission',list(M))
def test_bounded_complete_game_flow(city,mission):
    for seed in range(20):
        r=setup(city,mission,seed)
        for turn in range(180):
            if r.phase=='ended':break
            progress(r)
            ids=[c for p in r.players for c in p.hand if c!='start']+[p.held_card for p in r.players if p.held_card]
            assert len(ids)==len(set(ids)),(city,mission,seed,r.phase)
            assert len(ids)==20,(city,mission,seed,r.phase)
            assert sum('start' in p.hand for p in r.players)==1
            assert r.phase in {'turn','feedback','initial_pass','reveal','offer_choice','guess','ended'}
        assert r.phase=='ended',(city,mission,seed,'stuck',r.phase,r.move_count)
        assert r.result in {'success','failure'}

@pytest.mark.parametrize('city,mission',list(M))
def test_all_missions_hide_other_players_unseen_cards(city,mission):
    r=setup(city,mission,100)
    for view in range(4):
        state=server.snapshot(r,view)
        for other in range(4):
            if view==other:continue
            for card,entry in zip(r.players[other].hand,state['players'][other]['hand']):
                if card not in r.public:
                    assert entry['id'] is None,(city,mission,view,other)
                    assert entry['visible'] is False
        assert all('number' not in e for e in state['turn_events'])

@pytest.mark.parametrize('city,mission',list(M))
def test_invalid_cannot_take_unowned_card(city,mission):
    r=setup(city,mission,101)
    if r.phase=='turn':
        i=r.turn
        target=(i+1)%4
        illegal=next(c for c in r.players[target].hand if c not in r.players[i].hand)
        assert not server.can_pass(r,i,illegal,target)

@pytest.mark.parametrize('city,mission',list(M))
def test_mission_completion_constraints_have_valid_order(city,mission):
    """There is at least one ordering of people/colors satisfying rule registry."""
    import itertools
    cfg=M[city,mission]
    fixed=dict(cfg.completion_positions)
    required_colors=dict(cfg.color_positions)
    chars=range(4)
    colors=('blue','brown','green','magenta')
    feasible=False
    for ordered_chars in itertools.permutations(chars):
        if any(ordered_chars[where-1]!=char for char,where in fixed.items()):
            continue
        for ordered_colors in itertools.permutations(colors):
            if any(ordered_colors[where-1]!=color for color,where in required_colors.items()):
                continue
            feasible=True
            break
        if feasible:break
    assert feasible,(city,mission,'contradictory completion constraints')
