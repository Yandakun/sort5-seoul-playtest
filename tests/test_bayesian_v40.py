import copy, random, threading
import server
from mission_rules import M

def make_room(city='seoul',mission=1):
    random.seed(4009)
    room=server.Room(code='TEST',humans=0,city=city,mission=mission,debug=False)
    server.start_game(room)
    server.assign_bot_characters(room)
    return room

def test_probabilities_normalized():
    for city,mission in M:
        room=make_room(city,mission)
        for i in range(4):
            posterior=server.bayesian_assignment_beliefs(room,i)
            for marginal in posterior.values():
                assert all(0 <= value <= 1 for value in marginal.values())
                assert abs(sum(marginal.values())-1)<1e-9

def test_no_other_hidden_hand_or_goal_access():
    room=make_room()
    before=server.bayesian_assignment_beliefs(room,0)
    changed=copy.deepcopy(room, {id(room.lock):threading.RLock()})
    others=[j for j in range(4) if j!=0]
    cards=[c for j in others for c in changed.players[j].hand if c!='start' and c not in changed.public]
    random.Random(99).shuffle(cards)
    it=iter(cards)
    for j in others:
        p=changed.players[j]
        p.hand=[next(it) if c!='start' and c not in changed.public else c for c in p.hand]
        p.goal=server.COLORS[j%4]
    assert server.bayesian_assignment_beliefs(changed,0)==before

def test_default_model_stays_baseline(monkeypatch):
    monkeypatch.delenv('SORT5_BELIEF_MODEL',raising=False)
    room=make_room()
    base=server.bot_color_beliefs(room,0)
    monkeypatch.setenv('SORT5_BELIEF_MODEL','baseline')
    assert server.bot_color_beliefs(room,0)==base
