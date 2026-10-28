"""Special feedback needs to match the mission, without hidden card IDs."""
from tests.test_30_missions_engine import launch
import server


def test_berlin_five_auto_count_public_but_color_hidden():
    room, tokens, act, _ = launch('berlin',5)
    card = next(x for x in room.players[0].hand if x != 'start')
    result=act(0,'pass',card=card,target=1)
    event=result['turn_events'][-1]
    assert result['phase']=='turn'
    assert event['reaction']=='negative'
    assert event['announced_count']==sum(server.col(x)==server.col(card) for x in room.players[1].hand)
    assert event['card'] is None
    assert 'cards of the received color' in result['history'][-1]['text']


def test_paris_two_no_green_red_response():
    room, tokens, act, _ = launch('paris',2)
    i=0
    cards=[x for x in room.players[i].hand if x!='start'][:2]
    s=act(i,'offer',cards=cards,target=1)
    assert s['phase']=='offer_choice'
    s=act(1,'choose_offer',choice='0')
    assert s['phase']=='turn'
    assert s['turn_events'][-1]['reaction']=='negative'


def test_paris_five_triangle_auto_red_other_humans_choose_feedback():
    room, tokens, act, _ = launch('paris',5)
    # Circle can only pass left; triangle receives and is forced to show red.
    room.turn=1
    target=server.relative_seat(room,1,'left',skip_done=True)
    # Construct seating where the left player is triangle.
    assert target==0
    card=next(x for x in room.players[1].hand if x!='start')
    s=act(1,'pass',card=card,target=0)
    assert s['phase']=='turn' and s['turn_events'][-1]['reaction']=='negative'
    # Triangle can pass to square; square must choose ordinary chip feedback.
    card=next(x for x in room.players[0].hand if x!='start')
    s=act(0,'pass',card=card,target=2)
    assert s['phase']=='feedback'
