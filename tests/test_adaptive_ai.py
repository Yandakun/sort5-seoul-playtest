"""Focused tests of v0.7 bot strategy without privileged hidden-hand access."""
import random
import server
from fastapi.testclient import TestClient


def make_room():
    return server.Room(code='ABCDEF', humans=0, mission=5, debug=False,
        players=[server.Player(name=f'BOT {i}', token='', bot=True,
                               char=i, chips=6) for i in range(4)], phase='turn')


def test_goal_changes_when_new_color_becomes_stronger():
    r = make_room()
    p = r.players[1]
    p.goal = 'brown'
    # The last green card arrives from another player, making green 3 vs brown 2.
    p.hand = ['brown-1','brown-2','green-1','green-2','green-3']
    r.turn = 1
    r.turn_events.append({'step':1,'from':0,'to':1,'card':None,'reaction':None})
    server.after_received(r, 1, 'green-3')
    assert p.goal == 'green'
    assert r.turn_events[-1]['reaction'] == 'positive'
    assert p.chips == 5


def test_prior_known_green_reaction_guides_who_receives_green_card():
    r = make_room()
    r.turn = 0
    r.players[0].hand = ['brown-1','brown-2','brown-3','green-5','blue-4','start']
    r.players[0].goal = 'brown'
    r.evidence = [
        {'sender':0,'to':2,'color':'green','positive':True,'public':False,'step':2},
        {'sender':0,'to':1,'color':'green','positive':False,'public':False,'step':2},
    ]
    r.move_count = 3
    # Strong positive evidence for target 2, negative for target 1.
    random.seed(101)
    assert server.bot_choice(r,0) == ('green-5',2)


def test_private_hand_cards_never_influence_ai_decision():
    r = make_room()
    r.turn = 0
    r.players[0].hand = ['green-2','green-3','brown-1','blue-4','magenta-5','start']
    r.players[0].goal = 'green'
    r.players[1].hand = ['brown-2','brown-3']
    r.players[2].hand = ['magenta-3','magenta-4']
    r.players[3].hand = ['blue-1','blue-2']
    random.seed(2026)
    decision_before = server.bot_choice(r,0)
    # Move private cards between rivals. The bot has not seen these cards.
    r.players[1].hand, r.players[2].hand = r.players[2].hand, r.players[1].hand
    random.seed(2026)
    decision_after = server.bot_choice(r,0)
    assert decision_before == decision_after


def test_private_third_party_feedback_cannot_inform_color_preference():
    r = make_room()
    r.turn = 0
    r.players[0].hand = ['green-2','green-3','brown-1','blue-4','magenta-5','start']
    r.players[0].goal = 'green'
    random.seed(312)
    before = server.bot_choice(r,0)
    r.evidence.append({'sender':1,'to':2,'color':'blue','positive':True,'public':False,'step':0})
    random.seed(312)
    after = server.bot_choice(r,0)
    assert before == after


def test_full_set_holding_start_card_always_sends_start():
    r = make_room()
    r.turn = 0
    r.players[0].hand = [f'blue-{j}' for j in range(1,6)] + ['start']
    r.players[0].goal = 'brown'
    chosen = server.bot_choice(r,0)
    assert chosen[0] == 'start'


def test_single_ai_click_still_advances_only_one_turn():
    client=TestClient(server.APP)
    created=client.post('/api/new',json={'name':'Human','humans':1,'mission':5}).json()
    payload={'code':created['code'],'token':created['token']}
    def send(action,**extra):
        response=client.post('/api/action',json={**payload,'type':action,**extra})
        assert response.status_code==200, response.text
        return response.json()
    send('begin'); start=send('character',character=1)
    assert start['ai_waiting']
    result=send('advance_ai')
    assert result['moves']==1
    assert len(result['turn_events'])==1


def test_simulated_four_bot_games_can_finish_without_deadlock():
    for mission in range(1,6):
        for seed in range(30):
            random.seed(mission*10000+seed)
            room = server.Room(code='BENCH',humans=0,mission=mission,debug=False)
            server.start_game(room)
            server.assign_bot_characters(room)
            for _ in range(120):
                if room.phase!='turn':
                    break
                server.advance_bot(room)
            assert room.phase=='ended', f'mission {mission} seed {seed} stalled'
            assert room.result in ('success','failure')
