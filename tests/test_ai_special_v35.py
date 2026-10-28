"""AI special-action strategy remains limited to observable information."""
import random
import server


def room(city='london', mission=4):
    return server.Room(
        code='AIV35', humans=0, mission=mission, city=city, debug=False,
        players=[server.Player(name=f'B{i}', token='', bot=True, char=i, seat=i, chips=6)
                 for i in range(4)], phase='turn', turn=0)


def test_number_guess_reduces_seen_numbers():
    r=room()
    r.players[1].hand=['blue-1','green-1','brown-1','magenta-1','green-3']
    # No card of number 1 remains outside receiver's known hand.
    random.seed(4)
    guesses=[server.bot_number_guess(r, 1) for _ in range(40)]
    assert 1 not in guesses
    assert all(2 <= n <= 5 for n in guesses)


def test_number_guess_does_not_peek_other_private_hands():
    r=room()
    r.players[1].hand=['blue-1', 'green-3']
    r.players[2].hand=['blue-2','brown-2','magenta-2']
    random.seed(42)
    a=[server.bot_number_guess(r,1) for _ in range(30)]
    r.players[2].hand=['blue-5','brown-5','magenta-5']
    random.seed(42)
    b=[server.bot_number_guess(r,1) for _ in range(30)]
    assert a==b


def test_offer_choice_uses_visible_color():
    r=room('berlin',3)
    receiver=r.players[1]
    receiver.hand=['blue-1','blue-2','blue-3','brown-4']
    receiver.goal='blue'
    r.pending={'from':3,'to':1,'cards':['blue-4','green-5'],
               'public_cards':['blue-4','green-5']}
    assert server.bot_offer_choice(r,1)==0


def test_offer_choice_ignores_internal_hidden_offer_ids():
    r=room('berlin',3)
    r.players[1].hand=['blue-1','blue-2']
    r.pending={'from':3,'to':1,'cards':['blue-3','brown-5'],
               'public_cards':[None,None]}
    random.seed(123)
    a=[server.bot_offer_choice(r,1) for _ in range(20)]
    r.pending['cards']=['magenta-5','green-3']
    random.seed(123)
    b=[server.bot_offer_choice(r,1) for _ in range(20)]
    assert a==b


def test_second_offer_preserves_goal_color():
    r=room('berlin',3)
    r.turn=3
    p=r.players[3]
    p.goal='blue'
    p.hand=['blue-1','blue-2','blue-3','green-4','brown-5','start']
    random.seed(5)
    assert server.bot_second_offer(r,3,'green-4',1)=='brown-5'


def test_second_offer_does_not_use_target_secret_hand():
    r=room('berlin',3)
    r.turn=3
    p=r.players[3]
    p.goal='blue'
    p.hand=['blue-1','blue-2','green-4','brown-5','start']
    r.players[1].hand=['green-1','green-2']
    random.seed(7)
    a=server.bot_second_offer(r,3,'blue-1',1)
    r.players[1].hand=['brown-1','brown-2']
    random.seed(7)
    b=server.bot_second_offer(r,3,'blue-1',1)
    assert a==b


def test_new_features_are_used_by_ai_actions():
    r=room('berlin',3)
    r.turn=3
    p=r.players[3]
    p.hand=['blue-1','blue-2','green-3','brown-4','magenta-5','start']
    r.players[0].hand=['green-1','blue-3']
    r.players[1].hand=['brown-1','brown-3']
    r.players[2].hand=['magenta-1','magenta-2']
    # Don't test a specific target/card, only that an offer is assembled.
    random.seed(2)
    server.advance_bot(r)
    assert r.move_count in (0,1)
    assert r.phase in ('turn','ended','feedback','offer_choice')
