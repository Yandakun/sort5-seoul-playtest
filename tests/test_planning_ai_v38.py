"""Strategic v3.8: legal two-hop routes, private-information safety, chip risk."""
import random
import server


def make_room(city='tokyo', mission=1):
    return server.Room(code='TEST38', humans=0, city=city, mission=mission,
                       debug=False, phase='turn', turn=0,
                       players=[server.Player(name=f'BOT {i}', token='', bot=True,
                                              char=i, seat=i, chips=6)
                                for i in range(4)])


def test_two_turn_routes_do_not_use_any_teammate_private_cards():
    r = make_room('tokyo',1)
    r.players[0].hand=['green-1','blue-1','brown-1','magenta-1','start']
    b=server.bot_color_beliefs(r,0)
    old=server.ai_two_turn_value(r,0,1,'green',b)
    for j in [1,2,3]:
        r.players[j].hand=[f'blue-{j}',f'green-{j}']
        r.players[j].goal='blue'
    assert server.ai_two_turn_value(r,0,1,'green',b)==old
    random.seed(44)
    first=server.bot_choice(r,0)
    for j in [1,2,3]:
        r.players[j].hand=[f'brown-{j}',f'magenta-{j}']
        r.players[j].goal='magenta'
    random.seed(44)
    assert server.bot_choice(r,0)==first


def test_fixed_opposite_is_not_next_hop():
    r=make_room('tokyo',1)
    assert 2 not in server.ai_transfer_routes(r,0)
    assert 1 in server.ai_transfer_routes(r,0)
    assert 3 in server.ai_transfer_routes(r,0)


def test_completed_left_neighbor_is_skipped_for_future_route():
    r=make_room('berlin',2)
    # star is constrained to pass left; it is seated at 3, seat 2 is done.
    r.players[3].done=False
    r.players[2].done=True
    assert server.ai_transfer_routes(r,3)==[1]
    assert r.players[2].seat==2


def test_goal_beliefs_are_sharper_than_noninformative_prior():
    r=make_room('seoul',5)
    r.players[0].hand=['green-1','green-2','green-3','blue-1','brown-1']
    r.players[1].hand=[]
    r.public.update([])
    b=server.bot_color_beliefs(r,0)
    assert b[0]['green']>b[0]['blue']
    for color in server.COLORS:
        assert abs(sum(b[i][color] for i in range(4))-1.0) < 1e-7


def test_bot_avoids_one_chip_receiver_if_other_routes_available():
    r=make_room('seoul',5)
    r.players[0].hand=['green-1','green-2','green-3','brown-4','start']
    r.players[0].goal='green'
    r.players[1].chips=1
    r.players[2].chips=6
    r.players[3].chips=6
    random.seed(56)
    card,target=server.bot_choice(r,0)
    assert card in r.players[0].hand
    assert target in (2,3)


def test_two_hop_forecast_values_a_good_relay_without_hidden_hands():
    r=make_room('berlin',2)
    r.players[3].done=True
    # sender 0 -> receiver 1; receiver 1 can pass to player 2.
    guesses={j:{c:0.25 for c in server.COLORS} for j in range(4)}
    guesses[1]['green']=0.1
    guesses[2]['green']=0.8
    with_route=server.ai_two_turn_value(r,0,1,'green',guesses)
    guesses[2]['green']=0.1
    without_route=server.ai_two_turn_value(r,0,1,'green',guesses)
    assert with_route>without_route


def test_ai_defers_completion_that_would_strand_opposite_teammates():
    r=make_room('tokyo',1)
    r.players[2].done=True
    r.completion_order=[{'player':2,'character':2,'color':'brown','position':1}]
    r.players[0].hand=[f'blue-{n}' for n in range(1,6)]+['green-1']
    r.players[0].goal='blue'
    assert not server.ai_safe_to_leave_table(r,0)
    random.seed(43)
    card,target=server.bot_choice(r,0)
    assert server.col(card)=='blue'  # do not finish now and strand seats 1 and 3
    assert not server.info_set([x for x in r.players[0].hand if x!=card])


def test_finishing_when_remaining_players_are_adjacent_is_allowed():
    r=make_room('tokyo',1)
    r.players[3].done=True
    assert server.ai_safe_to_leave_table(r,0)  # seats 1 and 2 are adjacent
