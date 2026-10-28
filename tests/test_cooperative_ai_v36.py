"""Rule-aware finishing/routing with no opponent private-hand access."""
import random
import server


def fixture(city='paris', mission=1, current=0):
    r = server.Room(code='ORDERV36', city=city, humans=0, mission=mission, debug=False,
                    phase='turn', turn=current,
                    players=[server.Player(name=f'Bot{i}', token='', bot=True,
                                           char=i, seat=i, chips=6)
                             for i in range(4)])
    return r


def test_paris_first_finisher_holds_start_card_until_right_turn():
    r=fixture('paris',1,1)
    p=r.players[1]
    p.hand=[f'blue-{n}' for n in range(1,6)]+['start']
    p.goal='blue'
    random.seed(33)
    choice=server.bot_choice(r,1)
    assert choice is not None
    assert choice[0]!='start', 'Circle must not declare completion before Triangle'


def test_paris_first_finisher_is_allowed_to_finish_now():
    r=fixture('paris',1,0)
    p=r.players[0]
    p.hand=[f'blue-{n}' for n in range(1,6)]+['start']
    p.goal='blue'
    assert server.bot_choice(r,0)[0]=='start'


def test_public_route_prioritizes_next_character_over_wrong_order():
    r=fixture('paris',1,2)
    p=r.players[2]
    p.hand=['blue-1','blue-2','blue-3','green-4','magenta-5','start']
    p.goal='blue'
    r.evidence=[{'sender':2,'to':1,'color':'green','positive':True,'public':False,'step':0},
                {'sender':2,'to':0,'color':'green','positive':True,'public':False,'step':0}]
    random.seed(19)
    card,target=server.bot_choice(r,2)
    assert card=='green-4' and target==0, (card,target)


def test_ai_order_ignores_hidden_opponent_hand_changes():
    r=fixture('paris',4,3)
    p=r.players[3]
    p.hand=['blue-1','blue-3','green-1','magenta-4','brown-5','start']
    p.goal='blue'
    r.players[0].hand=['magenta-1','magenta-2']
    r.players[1].hand=['green-2','green-3']
    random.seed(456)
    before=server.bot_choice(r,3)
    r.players[0].hand=['green-2','green-3']
    r.players[1].hand=['magenta-1','magenta-2']
    random.seed(456)
    after=server.bot_choice(r,3)
    assert before==after


def test_required_color_favored_at_correct_finish_position():
    r=fixture('new_york',1,1)
    p=r.players[1]
    p.hand=['green-1','green-2','green-3','blue-4','brown-5','start']
    p.goal='green'
    assert server.ai_can_finish_now(r,0,'blue')
    assert not server.ai_can_finish_now(r,0,'brown')
